"""C10 verification for the v1 REST contract.

The integration test uses the generated ``xiongan_rongdong_20`` assets and
therefore exercises the real SUMO/TraCI path rather than a mocked simulator.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SUMO_HOME = PROJECT_ROOT.parent / "tools" / "sumo-1.27.1" / "sumo-1.27.1"
SUMO_CONFIG = PROJECT_ROOT.parent / "xiongan_rongdong_20" / "sumo_files" / "xiongan.sumocfg"

os.environ.setdefault("SUMO_HOME", str(SUMO_HOME))
os.environ.setdefault("XIONGAN_SUMO_CONFIG", str(SUMO_CONFIG))

from server.api_server import INTERSECTION_ORDER, STATE_DIMENSION, app


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def test_health_reports_local_sumo(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["sumo_available"] is True
    assert response.json()["active_session_id"] is None


def test_actions_require_all_twenty_intersections(client: TestClient) -> None:
    response = client.post(
        "/api/v1/simulation/actions",
        json={"session_id": "missing", "expected_transition_id": 0, "actions": {"J01": 0}},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_ACTION_SET"


@pytest.mark.integration
def test_real_sumo_state_action_reward_cycle(client: TestClient) -> None:
    assert SUMO_CONFIG.exists(), f"SUMO config is missing: {SUMO_CONFIG}"

    started = client.post("/api/v1/simulation/start", json={"scenario": "morning_peak", "seed": 20260729})
    assert started.status_code == 201, started.text
    session_id = started.json()["session_id"]

    try:
        assert started.json()["state_dimension"] == STATE_DIMENSION
        assert started.json()["intersection_order"] == list(INTERSECTION_ORDER)

        state = client.get("/api/v1/simulation/state", params={"session_id": session_id})
        assert state.status_code == 200, state.text
        state_body = state.json()
        assert len(state_body["state_vector"]) == STATE_DIMENSION
        assert len(state_body["intersections"]) == len(INTERSECTION_ORDER)

        actions = {intersection["id"]: intersection["phase"] for intersection in state_body["intersections"]}
        applied = client.post(
            "/api/v1/simulation/actions",
            json={
                "session_id": session_id,
                "expected_transition_id": state_body["transition_id"],
                "actions": actions,
                "step_seconds": 5,
            },
        )
        assert applied.status_code == 200, applied.text
        assert applied.json()["transition_id"] == 1
        assert set(applied.json()["applied_actions"]) == set(INTERSECTION_ORDER)

        rewards = client.get(
            "/api/v1/simulation/rewards",
            params={"session_id": session_id, "transition_id": 1},
        )
        assert rewards.status_code == 200, rewards.text
        assert set(rewards.json()["rewards"]) == set(INTERSECTION_ORDER)
        assert isinstance(rewards.json()["global_reward"], float)
    finally:
        stopped = client.post("/api/v1/simulation/stop", json={"session_id": session_id})
        assert stopped.status_code == 200, stopped.text
