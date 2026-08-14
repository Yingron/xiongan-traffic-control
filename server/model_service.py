"""Stable-Baselines3 shared-DQN loading and inference support.

No fallback policy is provided.  A registry entry that is waiting for an
artifact remains unavailable until A's real model and contract metadata are
delivered and the entry is explicitly marked ``ready``.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np


SUPPORTED_FORMAT = "stable-baselines3-dqn"


class ModelServiceError(Exception):
    """Structured model error translated to the public API error envelope."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


def split_global_state(
    state: np.ndarray | list[float],
    *,
    intersection_count: int = 30,
    features_per_intersection: int = 22,
) -> np.ndarray:
    """Validate and split J01..J30 state into a float32 batch of local states."""
    array = np.asarray(state, dtype=np.float32)
    expected_dimension = intersection_count * features_per_intersection
    if array.shape != (expected_dimension,):
        raise ModelServiceError(
            422,
            "MODEL_CONTRACT_MISMATCH",
            "The simulation state does not match the shared-DQN input contract.",
            {
                "expected_global_shape": [expected_dimension],
                "actual_shape": list(array.shape),
                "expected_local_shape": [features_per_intersection],
            },
        )
    if not np.isfinite(array).all():
        raise ModelServiceError(
            422,
            "MODEL_CONTRACT_MISMATCH",
            "The simulation state contains non-finite values.",
        )
    return array.reshape(intersection_count, features_per_intersection)


class SB3ModelService:
    """Load registered SB3 DQN artifacts lazily and cache them for inference."""

    def __init__(self, registry_path: str | Path, project_root: str | Path) -> None:
        self.registry_path = Path(registry_path)
        self.project_root = Path(project_root).resolve()
        self._models: dict[str, Any] = {}
        self._lock = threading.RLock()

    def registry_entry(self, model_id: str) -> dict[str, Any]:
        registry = self._read_registry()
        entry = registry.get("models", {}).get(model_id)
        if not isinstance(entry, dict):
            raise ModelServiceError(
                404,
                "MODEL_NOT_FOUND",
                "The requested model_id is not registered.",
                {"model_id": model_id},
            )
        return entry

    def predict(
        self,
        model_id: str,
        global_state: np.ndarray,
        intersection_order: tuple[str, ...],
        *,
        deterministic: bool,
        action_masks: np.ndarray | None = None,
    ) -> dict[str, Any]:
        entry = self.registry_entry(model_id)
        # 公开状态契约恒为 22 维/路口（660 总维）；掩码模型（observation_dimension=26）
        # 在推理侧追加 4 维需求门控掩码，不改变对外状态契约。
        observations = split_global_state(
            global_state,
            intersection_count=len(intersection_order),
            features_per_intersection=22,
        )
        if action_masks is not None:
            # 掩码模型（observation_dimension=26）：为每个路口追加 4 维需求门控掩码
            masks = np.asarray(action_masks, dtype=np.float32)
            expected_masks = (len(intersection_order), int(entry.get("action_count", 4)))
            if masks.shape != expected_masks:
                raise ModelServiceError(
                    422,
                    "MODEL_CONTRACT_MISMATCH",
                    "Action masks do not match the registered observation contract.",
                    {"expected_mask_shape": list(expected_masks), "actual_mask_shape": list(masks.shape)},
                )
            observations = np.concatenate([observations, masks], axis=1)
        model = self._get_or_load(model_id, entry)

        started_ns = time.perf_counter_ns()
        try:
            raw_actions, _ = model.predict(observations, deterministic=deterministic)
        except Exception as error:
            raise ModelServiceError(
                500,
                "INFERENCE_FAILED",
                "The DQN model could not produce actions for the current state.",
                {"model_id": model_id, "reason": str(error)},
            ) from error
        latency_ms = (time.perf_counter_ns() - started_ns) / 1_000_000.0

        actions = np.asarray(raw_actions)
        expected_shape = (len(intersection_order),)
        action_count = int(entry.get("action_count", 4))
        if actions.shape != expected_shape or not np.issubdtype(actions.dtype, np.integer):
            raise ModelServiceError(
                500,
                "INVALID_MODEL_OUTPUT",
                "The DQN output does not contain one integer action per intersection.",
                {
                    "model_id": model_id,
                    "expected_shape": list(expected_shape),
                    "actual_shape": list(actions.shape),
                    "actual_dtype": str(actions.dtype),
                },
            )
        if np.any(actions < 0) or np.any(actions >= action_count):
            raise ModelServiceError(
                500,
                "INVALID_MODEL_OUTPUT",
                "The DQN output contains an action outside the registered action space.",
                {"model_id": model_id, "action_count": action_count},
            )

        return {
            "actions": {
                intersection_id: int(action)
                for intersection_id, action in zip(intersection_order, actions, strict=True)
            },
            "inference_latency_ms": round(latency_ms, 3),
            "model_contract_version": entry.get("model_contract_version", "shared-dqn-22x4-v1"),
        }

    def _get_or_load(self, model_id: str, entry: dict[str, Any]) -> Any:
        with self._lock:
            if model_id in self._models:
                return self._models[model_id]
            model = self._load(model_id, entry)
            self._models[model_id] = model
            return model

    def _load(self, model_id: str, entry: dict[str, Any]) -> Any:
        status = entry.get("status")
        if status != "ready":
            raise ModelServiceError(
                503,
                "MODEL_NOT_LOADED",
                "The registered model is waiting for A's artifact or contract confirmation.",
                {"model_id": model_id, "handoff_status": status or "unknown"},
            )
        if entry.get("format") != SUPPORTED_FORMAT:
            raise ModelServiceError(
                422,
                "MODEL_CONTRACT_MISMATCH",
                "Only Stable-Baselines3 DQN artifacts are supported by this model entry point.",
                {"model_id": model_id, "registered_format": entry.get("format")},
            )
        if entry.get("normalization") != "none":
            raise ModelServiceError(
                422,
                "MODEL_CONTRACT_MISMATCH",
                "The model normalization contract is not supported or has not been confirmed.",
                {"model_id": model_id, "normalization": entry.get("normalization")},
            )

        artifact_path = self._artifact_path(model_id, entry)
        if not artifact_path.is_file():
            raise ModelServiceError(
                503,
                "MODEL_NOT_LOADED",
                "The registered Stable-Baselines3 artifact has not been delivered.",
                {"model_id": model_id, "artifact_path": str(artifact_path)},
            )
        self._validate_checksum(model_id, artifact_path, entry.get("sha256"))

        try:
            from stable_baselines3 import DQN

            model = DQN.load(str(artifact_path), device="cpu")
        except Exception as error:
            raise ModelServiceError(
                503,
                "MODEL_LOAD_FAILED",
                "The Stable-Baselines3 DQN artifact could not be loaded.",
                {"model_id": model_id, "reason": str(error)},
            ) from error

        expected_observation = int(entry.get("observation_dimension", 22))
        expected_actions = int(entry.get("action_count", 4))
        actual_observation = getattr(getattr(model, "observation_space", None), "shape", None)
        actual_actions = getattr(getattr(model, "action_space", None), "n", None)
        if actual_observation != (expected_observation,) or actual_actions != expected_actions:
            raise ModelServiceError(
                422,
                "MODEL_CONTRACT_MISMATCH",
                "The delivered model spaces do not match the registered observation/action contract.",
                {
                    "model_id": model_id,
                    "expected_observation_shape": [expected_observation],
                    "actual_observation_shape": list(actual_observation) if actual_observation else None,
                    "expected_action_count": expected_actions,
                    "actual_action_count": actual_actions,
                },
            )
        return model

    def _artifact_path(self, model_id: str, entry: dict[str, Any]) -> Path:
        raw_path = entry.get("artifact_path")
        if not isinstance(raw_path, str) or not raw_path:
            raise ModelServiceError(
                503,
                "MODEL_NOT_LOADED",
                "No artifact path has been registered for the model.",
                {"model_id": model_id},
            )
        path = (self.project_root / raw_path).resolve()
        if not path.is_relative_to(self.project_root):
            raise ModelServiceError(
                503,
                "MODEL_REGISTRY_INVALID",
                "The registered artifact path must stay inside the project directory.",
                {"model_id": model_id},
            )
        return path

    def _read_registry(self) -> dict[str, Any]:
        try:
            content = json.loads(self.registry_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ModelServiceError(
                503,
                "MODEL_REGISTRY_INVALID",
                "The model registry could not be read.",
                {"registry_path": str(self.registry_path), "reason": str(error)},
            ) from error
        if not isinstance(content, dict) or not isinstance(content.get("models"), dict):
            raise ModelServiceError(
                503,
                "MODEL_REGISTRY_INVALID",
                "The model registry must contain a models object.",
                {"registry_path": str(self.registry_path)},
            )
        return content

    @staticmethod
    def _validate_checksum(model_id: str, artifact_path: Path, expected_sha256: Any) -> None:
        if not expected_sha256:
            raise ModelServiceError(
                422,
                "MODEL_CONTRACT_MISMATCH",
                "A SHA-256 checksum must be registered before the model can be loaded.",
                {"model_id": model_id},
            )
        digest = hashlib.sha256()
        with artifact_path.open("rb") as artifact:
            for chunk in iter(lambda: artifact.read(1024 * 1024), b""):
                digest.update(chunk)
        actual_sha256 = digest.hexdigest()
        if actual_sha256.lower() != str(expected_sha256).lower():
            raise ModelServiceError(
                503,
                "MODEL_LOAD_FAILED",
                "The delivered model checksum does not match the registry.",
                {"model_id": model_id, "actual_sha256": actual_sha256},
            )
