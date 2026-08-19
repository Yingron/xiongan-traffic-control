"""Model API contract and formal-artifact acceptance tests."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SUMO_HOME = PROJECT_ROOT.parent / "tools" / "sumo-1.27.1" / "sumo-1.27.1"
os.environ.setdefault("SUMO_HOME", str(SUMO_HOME))

from server.api_server import app
from server.model_service import ModelServiceError, SB3ModelService, split_global_state
from configs.constants import INTERSECTION_ORDER, STATE_DIMENSION


ARCHIVED_MODEL_ID = "shared-dqn-generalization-100k-v1"
PEAK_MODEL_ID = "shared-dqn-real-peak-masked-1m-v2"
EVENING_MODEL_ID = "shared-dqn-real-evening-masked-1m-v1"
OFFPEAK_MODEL_ID = "shared-dqn-real-offpeak-via-evening-v1"
READY_MODEL_IDS = (PEAK_MODEL_ID, EVENING_MODEL_ID, OFFPEAK_MODEL_ID)
REGISTRY_PATH = PROJECT_ROOT / "configs" / "model_registry.json"


def test_split_global_state_preserves_thirty_ordered_slices() -> None:
    state = np.arange(STATE_DIMENSION, dtype=np.float32)

    observations = split_global_state(state)

    assert observations.shape == (30, 22)
    assert observations.dtype == np.float32
    assert observations[0].tolist() == state[:22].tolist()
    assert observations[-1].tolist() == state[-22:].tolist()


@pytest.mark.parametrize(
    "state",
    [np.zeros(STATE_DIMENSION - 1, dtype=np.float32), np.zeros((30, 22), dtype=np.float32)],
)
def test_split_global_state_rejects_non_contract_shapes(state: np.ndarray) -> None:
    with pytest.raises(ModelServiceError) as captured:
        split_global_state(state)

    assert captured.value.status_code == 422
    assert captured.value.code == "MODEL_CONTRACT_MISMATCH"


def test_registry_distinguishes_unknown_and_archived_models() -> None:
    service = SB3ModelService(REGISTRY_PATH, PROJECT_ROOT)

    with pytest.raises(ModelServiceError) as unknown:
        service.registry_entry("not-registered")
    assert unknown.value.status_code == 404
    assert unknown.value.code == "MODEL_NOT_FOUND"

    with pytest.raises(ModelServiceError) as archived:
        service.predict(
            ARCHIVED_MODEL_ID,
            np.zeros(STATE_DIMENSION, dtype=np.float32),
            INTERSECTION_ORDER,
            deterministic=True,
        )
    assert archived.value.status_code == 503
    assert archived.value.code == "MODEL_NOT_LOADED"
    assert archived.value.details["handoff_status"] == "archived"


@pytest.mark.parametrize("model_id", READY_MODEL_IDS)
def test_ready_models_load_and_return_deterministic_masked_actions(model_id: str) -> None:
    service = SB3ModelService(REGISTRY_PATH, PROJECT_ROOT)
    state = np.zeros(STATE_DIMENSION, dtype=np.float32)
    masks = np.zeros((len(INTERSECTION_ORDER), 4), dtype=np.float32)
    expected_actions = np.arange(len(INTERSECTION_ORDER), dtype=np.int64) % 4
    masks[np.arange(len(INTERSECTION_ORDER)), expected_actions] = 1.0

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

    assert first["model_contract_version"] == "shared-dqn-26x4-v1"
    assert len(first["actions"]) == len(INTERSECTION_ORDER)
    assert first["actions"] == second["actions"]
    assert list(first["actions"].values()) == expected_actions.tolist()
    assert first["inference_latency_ms"] >= 0


@pytest.mark.integration
def test_formal_model_predicts_and_closes_real_session_loop() -> None:
    with TestClient(app) as client:
        started = client.post("/api/v1/simulation/start", json={"scenario": "real_evening", "seed": 20260820})
        assert started.status_code == 201, started.text
        session_id = started.json()["session_id"]

        try:
            unknown = client.post(
                "/api/v1/model/predict",
                json={"session_id": session_id, "model_id": "not-registered", "deterministic": True},
            )
            assert unknown.status_code == 404
            assert unknown.json()["error"]["code"] == "MODEL_NOT_FOUND"

            predicted = client.post(
                "/api/v1/model/predict",
                json={"session_id": session_id, "model_id": EVENING_MODEL_ID, "deterministic": True},
            )
            assert predicted.status_code == 200, predicted.text
            body = predicted.json()
            assert set(body["actions"]) == set(INTERSECTION_ORDER)
            assert all(0 <= action < 4 for action in body["actions"].values())
            assert body["model_contract_version"] == "shared-dqn-26x4-v1"

            applied = client.post(
                "/api/v1/simulation/actions",
                json={
                    "session_id": session_id,
                    "expected_transition_id": body["transition_id"],
                    "actions": body["actions"],
                    "step_seconds": 5,
                },
            )
            assert applied.status_code == 200, applied.text
            assert applied.json()["transition_id"] == body["transition_id"] + 1
        finally:
            client.post("/api/v1/simulation/stop", json={"session_id": session_id})
