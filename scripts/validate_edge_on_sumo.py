"""Compare the recommended ONNX INT8 policy with its teacher on real SUMO states."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from edge_deploy.inference import EdgeInference
from env.single_intersection_env import SingleIntersectionEnv
from training.config import SCENARIO_CONFIG


SPECS = {
    "real_peak": {
        "teacher": PROJECT_ROOT / "models" / "dqn" / "dqn_multi_shared_real_peak_perf_1000000steps.zip",
        "edge_dir": PROJECT_ROOT / "models" / "edge" / "peak",
    },
    "real_offpeak": {
        "teacher": PROJECT_ROOT / "models" / "dqn" / "dqn_multi_shared_real_evening_perf_1000000steps.zip",
        "edge_dir": PROJECT_ROOT / "models" / "edge" / "evening",
    },
    "real_evening": {
        "teacher": PROJECT_ROOT / "models" / "dqn" / "dqn_multi_shared_real_evening_perf_1000000steps.zip",
        "edge_dir": PROJECT_ROOT / "models" / "edge" / "evening",
    },
}
DEFAULT_INTERSECTIONS = "J01,J05,J10,J15,J20,J21,J25,J30"


def validate_scenario(
    scenario: str,
    intersections: list[str],
    steps: int,
    seed: int,
    artifact: str,
) -> dict:
    from stable_baselines3 import DQN
    import training.masked_policy  # noqa: F401

    spec = SPECS[scenario]
    teacher = DQN.load(str(spec["teacher"]), device="cpu")
    edge_path = spec["edge_dir"] / artifact
    edge = EdgeInference(edge_path)
    matches = 0
    samples = 0
    by_intersection: dict[str, dict[str, float | int]] = {}

    for index, intersection in enumerate(intersections):
        env = SingleIntersectionEnv(
            intersection_id=intersection,
            sumo_cfg_path=SCENARIO_CONFIG[scenario]["sumo_cfg"],
            max_steps=steps,
            delta_time=5,
        )
        local_matches = 0
        local_samples = 0
        try:
            observation, _ = env.reset(seed=seed + index)
            done = False
            while not done and local_samples < steps:
                teacher_action, _ = teacher.predict(observation, deterministic=True)
                edge_action, _ = edge.predict(observation)
                teacher_action = int(teacher_action)
                local_matches += int(teacher_action == int(edge_action))
                local_samples += 1
                observation, _, terminated, truncated, _ = env.step(teacher_action)
                done = terminated or truncated
        finally:
            env.close()
        matches += local_matches
        samples += local_samples
        by_intersection[intersection] = {
            "samples": local_samples,
            "action_agreement": local_matches / max(local_samples, 1),
        }
        print(
            f"[{scenario}] {intersection}: "
            f"{by_intersection[intersection]['action_agreement']:.2%}",
            flush=True,
        )

    return {
        "teacher": str(spec["teacher"].relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "candidate": str(edge_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "samples": samples,
        "action_agreement": matches / max(samples, 1),
        "intersections": by_intersection,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate ONNX INT8 actions on real SUMO states")
    parser.add_argument("--scenarios", nargs="+", choices=sorted(SPECS), default=sorted(SPECS))
    parser.add_argument("--intersections", default=DEFAULT_INTERSECTIONS)
    parser.add_argument("--steps", type=int, default=120)
    parser.add_argument("--seed", type=int, default=20260820)
    parser.add_argument("--min-agreement", type=float, default=0.95)
    parser.add_argument("--artifact", default="model.onnx", help="Artifact filename inside each scenario edge directory")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "models" / "edge" / "real_state_validation.json")
    args = parser.parse_args()
    intersections = [value.strip() for value in args.intersections.split(",") if value.strip()]

    reports = {
        scenario: validate_scenario(scenario, intersections, args.steps, args.seed, args.artifact)
        for scenario in args.scenarios
    }
    passed = all(report["action_agreement"] >= args.min_agreement for report in reports.values())
    result = {
        "schema_version": "edge-real-state-validation-v1",
        "status": "PASS" if passed else "FAIL",
        "minimum_action_agreement": args.min_agreement,
        "steps_per_intersection": args.steps,
        "scenarios": reports,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
