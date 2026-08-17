"""End-to-end validation for the registered 26-D masked DQN without a web server.

This uses the same TraCI session manager and model service exposed by the REST
API.  It is useful when an older long-running API process is still bound to
port 8000 and cannot reload newly registered model code.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from configs.constants import INTERSECTION_ORDER
from server.api_server import ActionsRequest, StartRequest, manager, model_service

MODEL_ID = "shared-dqn-real-offpeak-masked-1m-v1"


async def main() -> None:
    started = await manager.start(StartRequest(scenario="real_offpeak", use_gui=False))
    session_id = started["session_id"]
    try:
        transition_id, state = await manager.inference_state(session_id)
        masks = await manager.inference_masks(session_id)
        prediction = model_service.predict(
            MODEL_ID,
            state,
            INTERSECTION_ORDER,
            deterministic=True,
            action_masks=masks,
        )
        actions = prediction["actions"]
        assert len(state) == 660
        assert masks.shape == (30, 4)
        assert set(actions) == set(INTERSECTION_ORDER)
        assert all(masks[index, actions[junction_id]] == 1 for index, junction_id in enumerate(INTERSECTION_ORDER))

        applied = await manager.actions(
            ActionsRequest(
                session_id=session_id,
                expected_transition_id=transition_id,
                actions=actions,
                step_seconds=5,
            )
        )
        assert applied["transition_id"] == transition_id + 1
        print(json.dumps({
            "result": "PASS",
            "model_id": MODEL_ID,
            "state_dimension": int(len(state)),
            "mask_shape": list(masks.shape),
            "action_count": len(actions),
            "all_actions_respect_masks": True,
            "inference_latency_ms": prediction["inference_latency_ms"],
            "transition_id": applied["transition_id"],
        }, ensure_ascii=False))
    finally:
        await manager.stop(session_id)


if __name__ == "__main__":
    asyncio.run(main())
