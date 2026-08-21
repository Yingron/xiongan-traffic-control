"""Tests for the shared REST/WebSocket 30-intersection contract."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SUMO_HOME = PROJECT_ROOT.parent / "tools" / "sumo-1.27.1" / "sumo-1.27.1"
os.environ.setdefault("SUMO_HOME", str(SUMO_HOME))

from server.api_server import ActionsRequest, ApiError, INTERSECTION_ORDER, STATE_DIMENSION, app
from server.websocket_server import WebSocketHub


def _state_payload(transition_id: int) -> dict[str, Any]:
    intersections = [
        {
            "id": intersection_id,
            "state_offset": index * 22,
            "phase": index % 4,
            "phase_name": "test",
            "queues": {},
            "wait_times": {},
            "occupancy": {},
            "overflow_risk": {},
        }
        for index, intersection_id in enumerate(INTERSECTION_ORDER)
    ]
    return {
        "type": "simulation.state",
        "session_id": "sim_test",
        "transition_id": transition_id,
        "timestamp": 1,
        "simulation_time": float(transition_id * 5),
        "state_layout_version": "v1-30x22",
        "intersection_order": list(INTERSECTION_ORDER),
        "state_vector": [0.0] * STATE_DIMENSION,
        "intersections": intersections,
        "reward_version": "v3",
        "rewards": {intersection_id: -0.1 for intersection_id in INTERSECTION_ORDER},
        "global_reward": -0.1,
    }


class FakeManager:
    def __init__(self) -> None:
        self.transition_id = 0

    async def stream_snapshot(self, session_id: str, channels: set[str]) -> dict[str, Any]:
        if session_id != "sim_test":
            raise ApiError(404, "SESSION_NOT_FOUND", "Simulation session was not found or has stopped.")
        payload = _state_payload(self.transition_id)
        if "state" not in channels:
            payload.pop("state_vector")
            payload.pop("intersections")
        if "reward" not in channels:
            payload.pop("reward_version")
            payload.pop("rewards")
            payload.pop("global_reward")
        return payload

    async def actions(self, request: ActionsRequest) -> dict[str, Any]:
        if request.expected_transition_id != self.transition_id:
            raise ApiError(409, "STALE_TRANSITION", "Actions were generated from an outdated state.")
        self.transition_id += 1
        return {
            "session_id": request.session_id,
            "transition_id": self.transition_id,
            "simulation_time": float(self.transition_id * request.step_seconds),
            "requested_actions": request.actions,
            "applied_actions": request.actions,
            "action_result": {
                intersection_id: {"accepted": True, "reason": None}
                for intersection_id in INTERSECTION_ORDER
            },
            "rewards_ready": True,
        }


@pytest.fixture
def websocket_client() -> TestClient:
    test_app = FastAPI()
    hub = WebSocketHub(FakeManager(), ActionsRequest, ApiError, heartbeat_seconds=3600)
    hub.register(test_app, "/api/v1/ws")
    with TestClient(test_app) as client:
        yield client


def test_subscribe_returns_thirty_intersections_and_660_values(websocket_client: TestClient) -> None:
    with websocket_client.websocket_connect("/api/v1/ws") as websocket:
        websocket.send_json(
            {
                "type": "subscribe",
                "request_id": "subscribe-1",
                "session_id": "sim_test",
                "channels": ["state", "reward"],
            }
        )

        confirmed = websocket.receive_json()
        snapshot = websocket.receive_json()

        assert confirmed["type"] == "subscription.confirmed"
        assert confirmed["request_id"] == "subscribe-1"
        assert snapshot["type"] == "simulation.state"
        assert len(snapshot["state_vector"]) == STATE_DIMENSION
        assert [item["id"] for item in snapshot["intersections"]] == list(INTERSECTION_ORDER)
        assert set(snapshot["rewards"]) == set(INTERSECTION_ORDER)


def test_websocket_actions_return_result_then_broadcast_snapshot(websocket_client: TestClient) -> None:
    actions = {intersection_id: index % 4 for index, intersection_id in enumerate(INTERSECTION_ORDER)}
    with websocket_client.websocket_connect("/api/v1/ws") as websocket:
        websocket.send_json(
            {"type": "subscribe", "session_id": "sim_test", "channels": ["state", "reward"]}
        )
        websocket.receive_json()
        websocket.receive_json()

        websocket.send_json(
            {
                "type": "simulation.actions",
                "request_id": "unity-001",
                "session_id": "sim_test",
                "expected_transition_id": 0,
                "actions": actions,
                "step_seconds": 5,
            }
        )

        action_result = websocket.receive_json()
        snapshot = websocket.receive_json()

        assert action_result["type"] == "simulation.action_result"
        assert action_result["request_id"] == "unity-001"
        assert action_result["transition_id"] == 1
        assert action_result["applied_actions"] == actions
        assert snapshot["transition_id"] == 1


def test_invalid_subscription_and_action_return_protocol_errors(websocket_client: TestClient) -> None:
    with websocket_client.websocket_connect("/api/v1/ws") as websocket:
        websocket.send_json(
            {"type": "subscribe", "session_id": "sim_test", "channels": ["model_prediction"]}
        )
        invalid_subscription = websocket.receive_json()
        assert invalid_subscription["error"]["code"] == "INVALID_SUBSCRIPTION"

        websocket.send_json(
            {
                "type": "simulation.actions",
                "request_id": "bad-actions",
                "session_id": "sim_test",
                "expected_transition_id": 0,
                "actions": {"J01": 0},
            }
        )
        invalid_actions = websocket.receive_json()
        assert invalid_actions["request_id"] == "bad-actions"
        assert invalid_actions["error"]["code"] == "INVALID_ACTION_SET"


def test_ping_and_stale_transition_errors(websocket_client: TestClient) -> None:
    actions = {intersection_id: 0 for intersection_id in INTERSECTION_ORDER}
    with websocket_client.websocket_connect("/api/v1/ws") as websocket:
        websocket.send_json({"type": "ping", "request_id": "ping-001"})
        pong = websocket.receive_json()
        assert pong["type"] == "pong"
        assert pong["request_id"] == "ping-001"

        websocket.send_json(
            {
                "type": "simulation.actions",
                "request_id": "stale-001",
                "session_id": "sim_test",
                "expected_transition_id": 99,
                "actions": actions,
            }
        )
        stale = websocket.receive_json()
        assert stale["request_id"] == "stale-001"
        assert stale["error"]["code"] == "STALE_TRANSITION"


@pytest.mark.integration
def test_rest_action_is_pushed_to_websocket_from_real_sumo() -> None:
    with TestClient(app) as client:
        started = client.post("/api/v1/simulation/start", json={"scenario": "morning_peak", "seed": 20260806})
        assert started.status_code == 201, started.text
        session_id = started.json()["session_id"]

        try:
            with client.websocket_connect("/api/v1/ws") as websocket:
                websocket.send_json(
                    {
                        "type": "subscribe",
                        "session_id": session_id,
                        "channels": ["state", "reward"],
                    }
                )
                assert websocket.receive_json()["type"] == "subscription.confirmed"
                initial = websocket.receive_json()
                assert len(initial["state_vector"]) == STATE_DIMENSION
                assert set(initial["rewards"]) == set(INTERSECTION_ORDER)

                actions = {item["id"]: item["phase"] for item in initial["intersections"]}
                response = client.post(
                    "/api/v1/simulation/actions",
                    json={
                        "session_id": session_id,
                        "expected_transition_id": initial["transition_id"],
                        "actions": actions,
                        "step_seconds": 5,
                    },
                )
                assert response.status_code == 200, response.text

                pushed = websocket.receive_json()
                assert pushed["type"] == "simulation.state"
                assert pushed["transition_id"] == response.json()["transition_id"]
                assert len(pushed["intersections"]) == len(INTERSECTION_ORDER)
                assert set(pushed["rewards"]) == set(INTERSECTION_ORDER)
        finally:
            client.post("/api/v1/simulation/stop", json={"session_id": session_id})
