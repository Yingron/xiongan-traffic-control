"""Validate the real 30-junction REST/DQN control loop used by Unity.

Start ``server/api_server.py`` first, then run this script.  It validates the
same contract consumed by DqnControlClient: 660 state values, 30×4 masks,
30 predicted actions, and one atomic SUMO transition.
"""
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request


def request_json(base_url: str, path: str, method: str = "GET", payload: dict | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} -> HTTP {error.code}: {details}") from error


def main() -> None:
    parser = argparse.ArgumentParser(description="验证 Unity 使用的 DQN 控制闭环")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--scenario", default="real_offpeak")
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--step-seconds", type=int, default=5)
    args = parser.parse_args()

    health = request_json(args.base_url, "/health")
    if not health.get("sumo_available"):
        raise RuntimeError(f"SUMO is unavailable: {health}")

    session_id = None
    try:
        started = request_json(args.base_url, "/simulation/start", "POST", {"scenario": args.scenario, "use_gui": False})
        session_id = started["session_id"]
        assert started["intersection_order"] == [f"J{i:02d}" for i in range(1, 31)]
        assert started["state_dimension"] == 660

        state = request_json(args.base_url, f"/simulation/state?session_id={session_id}")
        assert len(state["state_vector"]) == 660
        assert len(state["intersections"]) == 30

        masks = request_json(args.base_url, f"/simulation/action-masks?session_id={session_id}")
        assert len(masks["action_masks"]) == 30 and all(len(mask) == 4 for mask in masks["action_masks"])

        prediction = request_json(
            args.base_url,
            "/model/predict",
            "POST",
            {"session_id": session_id, "model_id": args.model_id, "deterministic": True},
        )
        actions = prediction["actions"]
        assert set(actions) == {f"J{i:02d}" for i in range(1, 31)}
        assert all(isinstance(action, int) and 0 <= action <= 3 for action in actions.values())
        # This is the critical masked-DQN invariant: every selected action must
        # be currently legal for its corresponding intersection.
        for index, junction_id in enumerate(f"J{i:02d}" for i in range(1, 31)):
            assert masks["action_masks"][index][actions[junction_id]] == 1, (
                f"{junction_id} selected masked action {actions[junction_id]}"
            )

        applied = request_json(
            args.base_url,
            "/simulation/actions",
            "POST",
            {
                "session_id": session_id,
                "expected_transition_id": state["transition_id"],
                "actions": actions,
                "step_seconds": args.step_seconds,
            },
        )
        assert applied["transition_id"] == state["transition_id"] + 1
        print(json.dumps({
            "result": "PASS",
            "session_id": session_id,
            "state_dimension": len(state["state_vector"]),
            "mask_shape": [len(masks["action_masks"]), len(masks["action_masks"][0])],
            "action_count": len(actions),
            "all_actions_respect_masks": True,
            "inference_latency_ms": prediction["inference_latency_ms"],
            "transition_id": applied["transition_id"],
        }, ensure_ascii=False))
    finally:
        if session_id:
            try:
                request_json(args.base_url, "/simulation/stop", "POST", {"session_id": session_id})
            except RuntimeError:
                pass


if __name__ == "__main__":
    main()
