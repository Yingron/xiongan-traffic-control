"""Verify the Unity visualization WebSocket closed-loop contract.

Run this while ``server/visualization_server.py`` is running.  It records
real SUMO snapshots without fabricating state, and fails if the 30-junction
traffic-light/action contract is broken.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path
from time import time
from typing import Any


async def collect(
    uri: str, seconds: float, switch_to: str | None, require_mask: bool,
    expected_model_id: str | None,
) -> dict[str, Any]:
    import websockets

    result: dict[str, Any] = {
        "uri": uri,
        "started_at_unix": time(),
        "seconds_requested": seconds,
        "connected": None,
        "scenario_switched": None,
        "states": 0,
        "ignored_non_target_states": 0,
        "validation_errors": [],
        "phase_histogram": Counter(),
        "vehicle_counts": [],
        "model_ids": [],
        "snapshot_samples": [],
    }
    async with websockets.connect(uri, open_timeout=10) as ws:
        connected = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
        if connected.get("type") != "connected":
            result["validation_errors"].append("first message was not connected")
        result["connected"] = connected
        target_scenario = switch_to or connected.get("scenario")

        if switch_to:
            await ws.send(json.dumps({"type": "switch_scenario", "scenario": switch_to}))

        deadline = asyncio.get_running_loop().time() + seconds
        while asyncio.get_running_loop().time() < deadline:
            try:
                message = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            except TimeoutError:
                result["validation_errors"].append("no message for 5 seconds")
                continue
            msg_type = message.get("type")
            if msg_type == "scenario_switched":
                result["scenario_switched"] = message
                continue
            if msg_type != "state":
                continue

            # A state frame can already be buffered when a switch request is
            # sent.  It belongs to the prior SUMO instance and must not be
            # evaluated against the requested scenario/model contract.
            if message.get("scenario") != target_scenario:
                result["ignored_non_target_states"] += 1
                continue

            result["states"] += 1
            lights = message.get("traffic_lights") or []
            actions = message.get("actions") or {}
            requested_actions = message.get("requested_actions") or {}
            action_masks = message.get("action_masks") or {}
            model_id = message.get("model_id")
            vehicles = message.get("vehicles") or []
            ids = [item.get("id") for item in lights]
            if len(lights) != 30 or len(set(ids)) != 30:
                result["validation_errors"].append(
                    f"traffic_lights must be 30 unique entries, got {len(lights)}/{len(set(ids))}"
                )
            if len(actions) != 30:
                result["validation_errors"].append(f"actions must contain 30 entries, got {len(actions)}")
            if expected_model_id and model_id != expected_model_id:
                result["validation_errors"].append(
                    f"expected model_id {expected_model_id}, got {model_id}"
                )
            if require_mask:
                if len(requested_actions) != 30 or len(action_masks) != 30:
                    result["validation_errors"].append(
                        "masked verification requires 30 requested_actions and 30 action_masks"
                    )
                for tl_id, action in requested_actions.items():
                    mask = action_masks.get(tl_id)
                    if not isinstance(mask, list) or len(mask) != 4:
                        result["validation_errors"].append(f"{tl_id} has invalid action mask")
                    elif int(action) not in range(4) or int(mask[int(action)]) != 1:
                        result["validation_errors"].append(
                            f"{tl_id} requested masked-out action {action} with mask {mask}"
                        )
            phases = [int(item.get("phase", -1)) for item in lights]
            invalid = [phase for phase in phases if phase not in (0, 1, 2, 3)]
            if invalid:
                result["validation_errors"].append(f"invalid traffic-light phases: {invalid}")
            result["phase_histogram"].update(phases)
            result["vehicle_counts"].append(len(vehicles))
            if model_id:
                result["model_ids"].append(str(model_id))
            if len(result["snapshot_samples"]) < 3:
                result["snapshot_samples"].append(
                    {
                        "scenario": message.get("scenario"),
                        "model_id": model_id,
                        "simulation_time": message.get("simulation_time"),
                        "traffic_lights": len(lights),
                        "actions": len(actions),
                        "requested_actions": len(requested_actions),
                        "action_masks": len(action_masks),
                        "vehicles": len(vehicles),
                        "unique_phases": sorted(set(phases)),
                    }
                )

    result["finished_at_unix"] = time()
    result["phase_histogram"] = dict(sorted(result["phase_histogram"].items()))
    result["model_ids"] = sorted(set(result["model_ids"]))
    result["vehicle_count_min"] = min(result["vehicle_counts"], default=0)
    result["vehicle_count_max"] = max(result["vehicle_counts"], default=0)
    result["passed"] = bool(result["states"] > 0 and not result["validation_errors"])
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="verify Unity/SUMO WebSocket closed loop")
    parser.add_argument("--uri", default="ws://127.0.0.1:8765")
    parser.add_argument("--seconds", type=float, default=15.0)
    parser.add_argument("--switch-to", choices=("real_peak", "real_offpeak", "real_evening"))
    parser.add_argument("--require-mask", action="store_true")
    parser.add_argument("--expect-model-id", help="fail unless every state uses this formal model id")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    report = asyncio.run(
        collect(args.uri, args.seconds, args.switch_to, args.require_mask, args.expect_model_id)
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
