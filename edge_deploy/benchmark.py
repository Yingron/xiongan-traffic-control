"""Validate fidelity, masks, size and latency of all edge artifacts."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import torch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from edge_deploy.inference import EdgeInference
from edge_deploy.modeling import (
    ACTION_DIM,
    MODEL_INPUT_DIM,
    STATE_DIM,
    copy_formal_teacher,
    make_calibration_observations,
)


MODEL_SPECS = {
    "peak": PROJECT_ROOT / "models" / "dqn" / "dqn_multi_shared_real_peak_perf_1000000steps.zip",
    "evening": PROJECT_ROOT / "models" / "dqn" / "dqn_multi_shared_real_evening_perf_1000000steps.zip",
}
CANDIDATE_FILES = (
    "model_fp32.pt",
    "model.onnx",
    "model_int8.pt",
    "model_int8.onnx",
    "model_pruned_fp32.pt",
    "model_pruned_int8.pt",
)


def teacher_actions(teacher, observations: np.ndarray) -> np.ndarray:
    output: list[np.ndarray] = []
    with torch.inference_mode():
        for start in range(0, len(observations), 2048):
            q_values = teacher(torch.from_numpy(observations[start:start + 2048]))
            output.append(q_values.argmax(dim=1).cpu().numpy())
    return np.concatenate(output)


def validate_candidate(
    path: Path,
    observations: np.ndarray,
    reference_actions: np.ndarray,
    *,
    iterations: int,
    min_agreement: float,
) -> dict[str, Any]:
    inference = EdgeInference(path, warmup=10)
    predicted, _ = inference.predict(observations)
    predicted = np.asarray(predicted)
    agreement = float(np.mean(predicted == reference_actions))

    forced = np.zeros((40, MODEL_INPUT_DIM), dtype=np.float32)
    expected = np.arange(40, dtype=np.int64) % ACTION_DIM
    forced[np.arange(40), STATE_DIM + expected] = 1.0
    forced_actions, _ = inference.predict(forced)
    mask_compliance = float(np.mean(np.asarray(forced_actions) == expected))

    benchmark = inference.benchmark(iterations=iterations)
    checks = {
        "model_size_le_1mb": path.stat().st_size <= 1024 * 1024,
        "action_disagreement_le_5pct": agreement >= min_agreement,
        "action_mask_compliance": mask_compliance == 1.0,
        "single_mean_le_5ms": benchmark["single"]["mean_ms"] <= 5.0,
        "single_p95_le_100ms": benchmark["single"]["p95_ms"] <= 100.0,
        "batch30_p95_le_500ms": benchmark["batch30"]["p95_ms"] <= 500.0,
    }
    return {
        "artifact": path.name,
        "backend": inference.backend,
        "size_bytes": path.stat().st_size,
        "size_kb": path.stat().st_size / 1024.0,
        "action_agreement": agreement,
        "action_disagreement": 1.0 - agreement,
        "mask_compliance": mask_compliance,
        "latency": {"single": benchmark["single"], "batch30": benchmark["batch30"]},
        "checks": checks,
        "passed": all(checks.values()),
    }


def validate_model(
    name: str,
    edge_root: Path,
    samples: int,
    iterations: int,
    seed: int,
    min_agreement: float,
) -> dict[str, Any]:
    from stable_baselines3 import DQN
    import training.masked_policy  # noqa: F401

    teacher_path = MODEL_SPECS[name]
    teacher = copy_formal_teacher(DQN.load(str(teacher_path), device="cpu"))
    observations = make_calibration_observations(samples, seed)
    reference = teacher_actions(teacher, observations)
    model_dir = edge_root / name
    candidates = []
    for filename in CANDIDATE_FILES:
        path = model_dir / filename
        if not path.is_file():
            raise FileNotFoundError(f"Missing edge artifact: {path}")
        print(f"[{name}] validating {filename}", flush=True)
        candidates.append(
            validate_candidate(
                path,
                observations,
                reference,
                iterations=iterations,
                min_agreement=min_agreement,
            )
        )

    by_name = {candidate["artifact"]: candidate for candidate in candidates}
    preferred_order = (
        "model.onnx",
        "model_int8.onnx",
        "model_int8.pt",
        "model_fp32.pt",
        "model_pruned_int8.pt",
        "model_pruned_fp32.pt",
    )
    recommended = next((name for name in preferred_order if by_name[name]["passed"]), None)
    return {
        "teacher": str(teacher_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "validation_samples": samples,
        "latency_iterations": iterations,
        "minimum_action_agreement": min_agreement,
        "recommended_artifact": recommended,
        "candidates": candidates,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark all lightweight DQN artifacts")
    parser.add_argument("--models", nargs="+", choices=sorted(MODEL_SPECS), default=sorted(MODEL_SPECS))
    parser.add_argument("--edge-root", type=Path, default=PROJECT_ROOT / "models" / "edge")
    parser.add_argument("--samples", type=int, default=10000)
    parser.add_argument("--iterations", type=int, default=500)
    parser.add_argument("--min-agreement", type=float, default=0.95)
    parser.add_argument("--seed", type=int, default=20260821)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    torch.set_num_threads(1)

    reports = {
        name: validate_model(
            name,
            args.edge_root.resolve(),
            args.samples,
            args.iterations,
            args.seed + index,
            args.min_agreement,
        )
        for index, name in enumerate(args.models)
    }
    passed = all(report["recommended_artifact"] is not None for report in reports.values())
    result = {
        "schema_version": "edge-validation-v1",
        "status": "PASS" if passed else "FAIL",
        "models": reports,
    }
    output = (args.output or (args.edge_root / "validation_report.json")).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
