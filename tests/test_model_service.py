"""Model API contract tests that do not fabricate a DQN artifact."""

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


MODEL_ID = "shared-dqn-generalization-100k-v1"
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


def test_registry_distinguishes_unknown_and_waiting_models() -> None:
    service = SB3ModelService(REGISTRY_PATH, PROJECT_ROOT)

    with pytest.raises(ModelServiceError) as unknown:
        service.registry_entry("not-registered")
    assert unknown.value.status_code == 404
    assert unknown.value.code == "MODEL_NOT_FOUND"

    with pytest.raises(ModelServiceError) as waiting:
        service.predict(
            MODEL_ID,
            np.zeros(STATE_DIMENSION, dtype=np.float32),
            INTERSECTION_ORDER,
            deterministic=True,
        )
    assert waiting.value.status_code == 503
    assert waiting.value.code == "MODEL_NOT_LOADED"
    assert waiting.value.details["handoff_status"] == "waiting_for_A"


@pytest.mark.integration
def test_model_predict_reports_waiting_for_a_from_real_session() -> None:
    with TestClient(app) as client:
        started = client.post("/api/v1/simulation/start", json={"scenario": "morning_peak", "seed": 20260806})
        assert started.status_code == 201, started.text
        session_id = started.json()["session_id"]

        try:
            unknown = client.post(
                "/api/v1/model/predict",
                json={"session_id": session_id, "model_id": "not-registered", "deterministic": True},
            )
            assert unknown.status_code == 404
            assert unknown.json()["error"]["code"] == "MODEL_NOT_FOUND"

            waiting = client.post(
                "/api/v1/model/predict",
                json={"session_id": session_id, "model_id": MODEL_ID, "deterministic": True},
            )
            assert waiting.status_code == 503
            assert waiting.json()["error"]["code"] == "MODEL_NOT_LOADED"
            assert waiting.json()["error"]["details"]["handoff_status"] == "waiting_for_A"
        finally:
            client.post("/api/v1/simulation/stop", json={"session_id": session_id})
