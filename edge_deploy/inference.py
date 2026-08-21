"""Unified TorchScript/ONNX inference for 26-dimensional edge models."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import numpy as np

from edge_deploy.modeling import ACTION_DIM, MODEL_INPUT_DIM, STATE_DIM


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = PROJECT_ROOT / "models" / "edge" / "peak" / "model.onnx"


class EdgeInference:
    """Load a portable model and expose single/batched masked predictions."""

    def __init__(self, model_path: str | Path | None = None, *, warmup: int = 10) -> None:
        self.model_path = Path(model_path or DEFAULT_MODEL).resolve()
        if not self.model_path.is_file():
            raise FileNotFoundError(f"Edge model not found: {self.model_path}")
        self.backend = "onnx" if self.model_path.suffix.lower() == ".onnx" else "torchscript"
        self.model: Any = None
        self.input_name: str | None = None
        self.load_model()
        self.warmup(warmup)

    def load_model(self) -> None:
        if self.backend == "onnx":
            import onnxruntime as ort

            options = ort.SessionOptions()
            options.intra_op_num_threads = 1
            options.inter_op_num_threads = 1
            self.model = ort.InferenceSession(
                str(self.model_path),
                sess_options=options,
                providers=["CPUExecutionProvider"],
            )
            self.input_name = self.model.get_inputs()[0].name
        else:
            import torch

            self.model = torch.jit.load(str(self.model_path), map_location="cpu")
            self.model.eval()

    @staticmethod
    def prepare_observations(
        state: np.ndarray | list[float],
        action_mask: np.ndarray | list[float] | None = None,
    ) -> tuple[np.ndarray, bool]:
        observations = np.asarray(state, dtype=np.float32)
        was_single = observations.ndim == 1
        if was_single:
            observations = observations.reshape(1, -1)
        if observations.ndim != 2:
            raise ValueError("state must have shape (22,), (26,), (batch,22), or (batch,26)")

        if observations.shape[1] == STATE_DIM:
            if action_mask is None:
                raise ValueError("22-dimensional state requires a four-value action_mask")
            masks = np.asarray(action_mask, dtype=np.float32)
            if masks.ndim == 1:
                masks = masks.reshape(1, -1)
            if masks.shape == (1, ACTION_DIM) and len(observations) > 1:
                masks = np.repeat(masks, len(observations), axis=0)
            if masks.shape != (len(observations), ACTION_DIM):
                raise ValueError(f"action_mask must have shape ({len(observations)}, 4)")
            observations = np.concatenate([observations, masks], axis=1)
        elif observations.shape[1] != MODEL_INPUT_DIM:
            raise ValueError(f"expected 22 or 26 features, got {observations.shape[1]}")

        if not np.isfinite(observations).all():
            raise ValueError("observations contain NaN or infinity")
        masks = observations[:, STATE_DIM:]
        if np.any(masks < 0.0) or np.any(masks > 1.0) or np.any(masks.sum(axis=1) == 0):
            raise ValueError("each action mask must contain at least one valid value in [0,1]")
        return np.ascontiguousarray(observations, dtype=np.float32), was_single

    def predict_q(
        self,
        state: np.ndarray | list[float],
        action_mask: np.ndarray | list[float] | None = None,
    ) -> tuple[np.ndarray, float]:
        observations, was_single = self.prepare_observations(state, action_mask)
        started = time.perf_counter_ns()
        if self.backend == "onnx":
            q_values = self.model.run(None, {self.input_name: observations})[0]
        else:
            import torch

            with torch.inference_mode():
                q_values = self.model(torch.from_numpy(observations)).cpu().numpy()
        latency_ms = (time.perf_counter_ns() - started) / 1_000_000.0
        return (q_values[0] if was_single else q_values), latency_ms

    def predict(
        self,
        state: np.ndarray | list[float],
        action_mask: np.ndarray | list[float] | None = None,
    ) -> tuple[int | np.ndarray, float]:
        q_values, latency_ms = self.predict_q(state, action_mask)
        if q_values.ndim == 1:
            return int(np.argmax(q_values)), latency_ms
        return np.argmax(q_values, axis=1).astype(np.int64), latency_ms

    def warmup(self, iterations: int = 10) -> None:
        if iterations < 0:
            raise ValueError("warmup iterations must be non-negative")
        observations = np.zeros((30, MODEL_INPUT_DIM), dtype=np.float32)
        observations[:, STATE_DIM:] = 1.0
        for _ in range(iterations):
            self.predict(observations)

    def benchmark(self, iterations: int = 1000, seed: int = 20260820) -> dict[str, Any]:
        if iterations < 1:
            raise ValueError("iterations must be positive")
        rng = np.random.default_rng(seed)
        results: dict[str, Any] = {
            "model_path": str(self.model_path),
            "backend": self.backend,
            "model_size_bytes": self.model_path.stat().st_size,
        }
        for batch_size, label in ((1, "single"), (30, "batch30")):
            latencies: list[float] = []
            for _ in range(iterations):
                observations = rng.random((batch_size, MODEL_INPUT_DIM), dtype=np.float32)
                observations[:, STATE_DIM:] = 1.0
                _, latency = self.predict(observations)
                latencies.append(latency)
            values = np.asarray(latencies, dtype=np.float64)
            results[label] = {
                "mean_ms": float(values.mean()),
                "p50_ms": float(np.percentile(values, 50)),
                "p95_ms": float(np.percentile(values, 95)),
                "p99_ms": float(np.percentile(values, 99)),
                "max_ms": float(values.max()),
            }
        return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a portable 26-dimensional edge model")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--benchmark", action="store_true")
    parser.add_argument("--iterations", "--n", type=int, default=1000)
    args = parser.parse_args()

    inference = EdgeInference(args.model)
    if args.benchmark:
        print(json.dumps(inference.benchmark(args.iterations), ensure_ascii=False, indent=2))
        return

    state = np.zeros(STATE_DIM, dtype=np.float32)
    action, latency = inference.predict(state, np.ones(ACTION_DIM, dtype=np.float32))
    print(json.dumps({"action": action, "latency_ms": latency}, ensure_ascii=False))


if __name__ == "__main__":
    main()
