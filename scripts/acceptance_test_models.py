"""Validate every ready SB3 model and report CPU inference latency.

This is a model-service acceptance test, not an evaluation of traffic-control
quality.  It verifies registry/checksum/shape/mask/determinism contracts and
measures the cached model.predict call after warm-up.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from time import perf_counter

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from configs.constants import INTERSECTION_ORDER, STATE_DIMENSION
from server.model_service import SB3ModelService


REGISTRY_PATH = PROJECT_ROOT / "configs" / "model_registry.json"


def ready_model_ids() -> list[str]:
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    return [
        model_id
        for model_id, entry in registry["models"].items()
        if entry.get("status") == "ready"
    ]


def make_masks(rng: np.random.Generator) -> np.ndarray:
    masks = (rng.random((len(INTERSECTION_ORDER), 4)) > 0.35).astype(np.float32)
    empty_rows = np.flatnonzero(masks.sum(axis=1) == 0)
    masks[empty_rows, 0] = 1.0
    return masks


def percentile(values: list[float], q: float) -> float:
    return float(np.percentile(np.asarray(values, dtype=np.float64), q))


def validate_model(
    service: SB3ModelService,
    model_id: str,
    iterations: int,
    warmup: int,
    seed: int,
) -> dict[str, float | int | str]:
    rng = np.random.default_rng(seed)
    state = rng.random(STATE_DIMENSION, dtype=np.float32)
    masks = make_masks(rng)

    first = service.predict(
        model_id,
        state,
        INTERSECTION_ORDER,
        deterministic=True,
        action_masks=masks,
    )
    second = service.predict(
        model_id,
        state,
        INTERSECTION_ORDER,
        deterministic=True,
        action_masks=masks,
    )
    if first["actions"] != second["actions"]:
        raise AssertionError(f"{model_id}: deterministic predictions differ")
    if len(first["actions"]) != len(INTERSECTION_ORDER):
        raise AssertionError(f"{model_id}: output does not contain 30 actions")
    if first["model_contract_version"] != "shared-dqn-26x4-v1":
        raise AssertionError(f"{model_id}: unexpected model contract")

    forced = np.zeros((len(INTERSECTION_ORDER), 4), dtype=np.float32)
    expected = np.arange(len(INTERSECTION_ORDER), dtype=np.int64) % 4
    forced[np.arange(len(INTERSECTION_ORDER)), expected] = 1.0
    forced_result = service.predict(
        model_id,
        state,
        INTERSECTION_ORDER,
        deterministic=True,
        action_masks=forced,
    )
    if list(forced_result["actions"].values()) != expected.tolist():
        raise AssertionError(f"{model_id}: action mask was not enforced")

    for _ in range(warmup):
        service.predict(
            model_id,
            rng.random(STATE_DIMENSION, dtype=np.float32),
            INTERSECTION_ORDER,
            deterministic=True,
            action_masks=make_masks(rng),
        )

    model_latencies: list[float] = []
    service_latencies: list[float] = []
    for _ in range(iterations):
        sample_state = rng.random(STATE_DIMENSION, dtype=np.float32)
        sample_masks = make_masks(rng)
        started = perf_counter()
        result = service.predict(
            model_id,
            sample_state,
            INTERSECTION_ORDER,
            deterministic=True,
            action_masks=sample_masks,
        )
        service_latencies.append((perf_counter() - started) * 1000.0)
        model_latencies.append(float(result["inference_latency_ms"]))
        if not all(0 <= action < 4 for action in result["actions"].values()):
            raise AssertionError(f"{model_id}: action outside [0, 3]")

    return {
        "model_id": model_id,
        "iterations": iterations,
        "model_mean_ms": float(np.mean(model_latencies)),
        "model_p50_ms": percentile(model_latencies, 50),
        "model_p95_ms": percentile(model_latencies, 95),
        "model_p99_ms": percentile(model_latencies, 99),
        "service_mean_ms": float(np.mean(service_latencies)),
        "service_p95_ms": percentile(service_latencies, 95),
        "service_p99_ms": percentile(service_latencies, 99),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Accept all ready formal DQN models")
    parser.add_argument("--iterations", type=int, default=100)
    parser.add_argument("--warmup", type=int, default=10)
    parser.add_argument("--seed", type=int, default=20260820)
    args = parser.parse_args()
    if args.iterations < 1 or args.warmup < 0:
        parser.error("--iterations must be >= 1 and --warmup must be >= 0")

    model_ids = ready_model_ids()
    if not model_ids:
        raise SystemExit("No ready models found in configs/model_registry.json")

    service = SB3ModelService(REGISTRY_PATH, PROJECT_ROOT)
    reports = [
        validate_model(service, model_id, args.iterations, args.warmup, args.seed + index)
        for index, model_id in enumerate(model_ids)
    ]

    print(json.dumps({"status": "PASS", "models": reports}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
