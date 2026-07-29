"""REST API for the 20-intersection Xiongan traffic-control platform.

The public contract is defined in ``docs/接口文档.md``.  This module deliberately
does not fall back to the legacy one-intersection, 26-dimensional environment:
an invalid or incomplete SUMO network is reported to the caller as a 503.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from env.reward_functions import compute_reward


API_PREFIX = "/api/v1"
STATE_LAYOUT_VERSION = "v1-20x22"
REWARD_VERSION = "v3"
INTERSECTION_ORDER = tuple(f"J{index:02d}" for index in range(1, 21))
ACTION_NAMES = ("NS_Straight", "NS_Left", "EW_Straight", "EW_Left")
FEATURES_PER_INTERSECTION = 22
STATE_DIMENSION = len(INTERSECTION_ORDER) * FEATURES_PER_INTERSECTION
MIN_GREEN_SECONDS = 15
DEFAULT_NETWORK_ROOT = PROJECT_ROOT.parent / "xiongan_rongdong_20" / "sumo_files"
DEFAULT_CONFIG_PATH = Path(
    os.environ.get(
        "XIONGAN_SUMO_CONFIG",
        str(DEFAULT_NETWORK_ROOT / "xiongan.sumocfg" if DEFAULT_NETWORK_ROOT.exists() else PROJECT_ROOT / "sumo_files" / "xiongan.sumocfg"),
    )
).resolve()


class ApiError(Exception):
    """A documented API error that can safely be returned to clients."""

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


class StartRequest(BaseModel):
    scenario: str = Field(default="morning_peak", min_length=1, max_length=64)
    use_gui: bool = False
    seed: int | None = Field(default=None, ge=0)


class SessionRequest(BaseModel):
    session_id: str = Field(min_length=1)


class ResetRequest(SessionRequest):
    seed: int | None = Field(default=None, ge=0)


class ActionsRequest(SessionRequest):
    expected_transition_id: int = Field(ge=0)
    actions: dict[str, int]
    step_seconds: int = Field(default=5, ge=1, le=60)

    @field_validator("actions")
    @classmethod
    def validate_action_values(cls, actions: dict[str, int]) -> dict[str, int]:
        expected_ids = set(INTERSECTION_ORDER)
        received_ids = set(actions)
        if received_ids != expected_ids:
            raise ValueError(
                "actions must contain exactly J01 through J20; "
                f"missing={sorted(expected_ids - received_ids)}, "
                f"unexpected={sorted(received_ids - expected_ids)}"
            )
        invalid = {key: value for key, value in actions.items() if not isinstance(value, int) or value not in range(4)}
        if invalid:
            raise ValueError(f"each action must be an integer in [0, 3]; invalid={invalid}")
        return actions


class ModelPredictRequest(SessionRequest):
    model_id: str = Field(min_length=1)
    deterministic: bool = True


@dataclass
class SimulationSession:
    session_id: str
    scenario: str
    use_gui: bool
    seed: int | None
    config_path: Path
    transition_id: int = 0
    current_actions: dict[str, int] = field(default_factory=dict)
    previous_actions: dict[str, int | None] = field(default_factory=dict)
    phase_changed_at: dict[str, float] = field(default_factory=dict)
    last_state: np.ndarray | None = None
    last_rewards: dict[str, float] = field(default_factory=dict)
    last_breakdowns: dict[str, dict[str, Any]] = field(default_factory=dict)


class TraCISessionManager:
    """Owns the single local TraCI connection exposed by this API process."""

    def __init__(self) -> None:
        self.session: SimulationSession | None = None
        self.lock = asyncio.Lock()

    @staticmethod
    def _traci() -> Any:
        try:
            import traci
        except ImportError as error:  # pragma: no cover - deployment configuration
            raise ApiError(503, "TRACI_UNAVAILABLE", "TraCI is not installed.") from error
        return traci

    @staticmethod
    def _sumo_binary(use_gui: bool) -> str:
        sumo_home = os.environ.get("SUMO_HOME")
        if not sumo_home:
            raise ApiError(
                503,
                "TRACI_UNAVAILABLE",
                "SUMO_HOME is not configured. Run scripts/activate_c_environment.ps1 first.",
            )
        executable = Path(sumo_home) / "bin" / ("sumo-gui.exe" if use_gui else "sumo.exe")
        if not executable.exists():
            raise ApiError(
                503,
                "TRACI_UNAVAILABLE",
                "SUMO executable was not found under SUMO_HOME.",
                {"sumo_home": sumo_home, "expected_executable": str(executable)},
            )
        return str(executable)

    @staticmethod
    def _validate_sumo_assets(sumo_binary: str, config_path: Path) -> None:
        """Fail fast on malformed SUMO files before TraCI starts retrying ports.

        ``--end 0`` forces SUMO to parse all configured network assets and then
        exit before a simulation step is executed.  This turns an otherwise slow
        TraCI connection timeout into a deterministic API error for B/C handoff.
        """
        try:
            result = subprocess.run(
                [
                    sumo_binary,
                    "-c",
                    str(config_path),
                    "--end",
                    "0",
                    "--no-step-log",
                    "--no-warnings",
                    "--duration-log.disable",
                    "true",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise ApiError(
                503,
                "SIMULATION_ASSET_INVALID",
                "SUMO asset validation did not finish within 10 seconds.",
                {"config_path": str(config_path)},
            ) from error
        if result.returncode != 0:
            reason = (result.stderr or result.stdout).strip()
            raise ApiError(
                503,
                "SIMULATION_ASSET_INVALID",
                "SUMO rejected the configured simulation assets.",
                {"config_path": str(config_path), "sumo_error": reason[-2000:]},
            )

    @staticmethod
    def _close_traci_quietly() -> None:
        try:
            TraCISessionManager._traci().close(False)
        except Exception:
            pass

    @staticmethod
    def _validate_intersections(traci: Any) -> list[str]:
        traffic_lights = list(traci.trafficlight.getIDList())
        if len(traffic_lights) != len(INTERSECTION_ORDER) or set(traffic_lights) != set(INTERSECTION_ORDER):
            raise ApiError(
                503,
                "SIMULATION_ASSET_INVALID",
                "SUMO network does not expose exactly the required traffic lights J01 through J20.",
                {
                    "expected_intersections": len(INTERSECTION_ORDER),
                    "actual_intersections": len(traffic_lights),
                    "traffic_light_ids": traffic_lights,
                },
            )
        for traffic_light_id in INTERSECTION_ORDER:
            phase_count = len(traci.trafficlight.getAllProgramLogics(traffic_light_id)[0].phases)
            if phase_count != 4:
                raise ApiError(
                    503,
                    "SIMULATION_ASSET_INVALID",
                    f"Traffic light {traffic_light_id} must expose exactly four signal phases.",
                    {"intersection_id": traffic_light_id, "phase_count": phase_count},
                )
        return traffic_lights

    @staticmethod
    def _ordered_global_state(raw_traffic_light_ids: list[str]) -> np.ndarray:
        """Extract state and explicitly reorder slices to the public J01..J20 contract."""
        from env.global_state import get_global_state

        raw_state = get_global_state(num_intersections=len(INTERSECTION_ORDER))
        if raw_state.shape != (STATE_DIMENSION,):
            raise ApiError(
                503,
                "SIMULATION_STATE_INVALID",
                "Global state extractor did not return a 440-dimensional state vector.",
                {"actual_dimension": int(raw_state.size), "expected_dimension": STATE_DIMENSION},
            )
        raw_slices = {
            traffic_light_id: raw_state[index * FEATURES_PER_INTERSECTION : (index + 1) * FEATURES_PER_INTERSECTION]
            for index, traffic_light_id in enumerate(raw_traffic_light_ids)
        }
        return np.concatenate([raw_slices[traffic_light_id] for traffic_light_id in INTERSECTION_ORDER]).astype(
            np.float32, copy=False
        )

    @staticmethod
    def _intersections_payload(state: np.ndarray) -> list[dict[str, Any]]:
        payload: list[dict[str, Any]] = []
        directions = ("N", "S", "E", "W")
        for index, traffic_light_id in enumerate(INTERSECTION_ORDER):
            offset = index * FEATURES_PER_INTERSECTION
            features = state[offset : offset + FEATURES_PER_INTERSECTION]
            phase = int(np.argmax(features[16:20]))
            payload.append(
                {
                    "id": traffic_light_id,
                    "state_offset": offset,
                    "phase": phase,
                    "phase_name": ACTION_NAMES[phase],
                    "queues": dict(zip(directions, map(float, features[0:4]), strict=True)),
                    "wait_times": dict(zip(directions, map(float, features[4:8]), strict=True)),
                    "occupancy": dict(zip(directions, map(float, features[8:12]), strict=True)),
                    "overflow_risk": dict(zip(directions, map(float, features[12:16]), strict=True)),
                }
            )
        return payload

    @staticmethod
    def _reward_payload(session: SimulationSession, state: np.ndarray) -> tuple[dict[str, float], dict[str, dict[str, Any]]]:
        rewards: dict[str, float] = {}
        breakdowns: dict[str, dict[str, Any]] = {}
        for index, traffic_light_id in enumerate(INTERSECTION_ORDER):
            offset = index * FEATURES_PER_INTERSECTION
            reward, breakdown = compute_reward(
                state[offset : offset + FEATURES_PER_INTERSECTION],
                session.current_actions[traffic_light_id],
                session.previous_actions[traffic_light_id],
            )
            rewards[traffic_light_id] = float(reward)
            breakdowns[traffic_light_id] = {key: _json_value(value) for key, value in breakdown.items()}
        return rewards, breakdowns

    @staticmethod
    def _state_response(session: SimulationSession, traci: Any) -> dict[str, Any]:
        raw_ids = TraCISessionManager._validate_intersections(traci)
        state = TraCISessionManager._ordered_global_state(raw_ids)
        session.last_state = state
        return {
            "session_id": session.session_id,
            "transition_id": session.transition_id,
            "timestamp": int(time.time() * 1000),
            "simulation_time": float(traci.simulation.getTime()),
            "state_layout_version": STATE_LAYOUT_VERSION,
            "intersection_order": list(INTERSECTION_ORDER),
            "state_vector": state.astype(float).tolist(),
            "intersections": TraCISessionManager._intersections_payload(state),
        }

    async def start(self, request: StartRequest) -> dict[str, Any]:
        async with self.lock:
            if self.session is not None:
                raise ApiError(409, "SESSION_BUSY", "A simulation session is already active.")
            if not DEFAULT_CONFIG_PATH.exists():
                raise ApiError(
                    503,
                    "SIMULATION_ASSET_INVALID",
                    "SUMO configuration file was not found.",
                    {"config_path": str(DEFAULT_CONFIG_PATH)},
                )

            traci = self._traci()
            session = SimulationSession(
                session_id=f"sim_{uuid.uuid4().hex}",
                scenario=request.scenario,
                use_gui=request.use_gui,
                seed=request.seed,
                config_path=DEFAULT_CONFIG_PATH,
            )
            command = [
                self._sumo_binary(request.use_gui),
                "-c",
                str(DEFAULT_CONFIG_PATH),
                "--no-step-log",
                "--no-warnings",
                "--time-to-teleport",
                "-1",
            ]
            if request.seed is not None:
                command.extend(["--seed", str(request.seed)])

            try:
                self._validate_sumo_assets(self._sumo_binary(False), DEFAULT_CONFIG_PATH)
                traci.start(command, numRetries=1)
                self._validate_intersections(traci)
                sim_time = float(traci.simulation.getTime())
                session.current_actions = {
                    traffic_light_id: int(traci.trafficlight.getPhase(traffic_light_id))
                    for traffic_light_id in INTERSECTION_ORDER
                }
                session.previous_actions = {traffic_light_id: None for traffic_light_id in INTERSECTION_ORDER}
                session.phase_changed_at = {traffic_light_id: sim_time for traffic_light_id in INTERSECTION_ORDER}
                state = self._ordered_global_state(list(traci.trafficlight.getIDList()))
                session.last_state = state
                session.last_rewards, session.last_breakdowns = self._reward_payload(session, state)
                self.session = session
            except ApiError:
                self._close_traci_quietly()
                raise
            except Exception as error:
                self._close_traci_quietly()
                raise ApiError(
                    503,
                    "SIMULATION_ASSET_INVALID",
                    "SUMO could not start with the configured simulation assets.",
                    {"config_path": str(DEFAULT_CONFIG_PATH), "reason": str(error)},
                ) from error

            return {
                "session_id": session.session_id,
                "status": "running",
                "scenario": session.scenario,
                "intersection_order": list(INTERSECTION_ORDER),
                "state_layout_version": STATE_LAYOUT_VERSION,
                "state_dimension": STATE_DIMENSION,
                "transition_id": session.transition_id,
                "simulation_time": sim_time,
            }

    def _require_session(self, session_id: str) -> SimulationSession:
        if self.session is None or self.session.session_id != session_id:
            raise ApiError(404, "SESSION_NOT_FOUND", "Simulation session was not found or has stopped.")
        return self.session

    async def stop(self, session_id: str) -> dict[str, Any]:
        async with self.lock:
            self._require_session(session_id)
            self._close_traci_quietly()
            self.session = None
            return {"session_id": session_id, "status": "stopped"}

    async def reset(self, request: ResetRequest) -> dict[str, Any]:
        async with self.lock:
            session = self._require_session(request.session_id)
            scenario = session.scenario
            use_gui = session.use_gui
            seed = request.seed if request.seed is not None else session.seed
            self._close_traci_quietly()
            self.session = None
        return await self.start(StartRequest(scenario=scenario, use_gui=use_gui, seed=seed))

    async def state(self, session_id: str) -> dict[str, Any]:
        async with self.lock:
            session = self._require_session(session_id)
            return self._state_response(session, self._traci())

    async def actions(self, request: ActionsRequest) -> dict[str, Any]:
        async with self.lock:
            session = self._require_session(request.session_id)
            if request.expected_transition_id != session.transition_id:
                raise ApiError(
                    409,
                    "STALE_TRANSITION",
                    "Actions were generated from an outdated simulation state.",
                    {"expected_transition_id": request.expected_transition_id, "current_transition_id": session.transition_id},
                )

            traci = self._traci()
            simulation_time = float(traci.simulation.getTime())
            previous_actions = session.current_actions.copy()
            applied_actions: dict[str, int] = {}
            action_result: dict[str, dict[str, Any]] = {}
            for traffic_light_id in INTERSECTION_ORDER:
                requested_action = request.actions[traffic_light_id]
                current_action = int(traci.trafficlight.getPhase(traffic_light_id))
                elapsed_green = simulation_time - session.phase_changed_at[traffic_light_id]
                if requested_action != current_action and elapsed_green < MIN_GREEN_SECONDS:
                    applied_actions[traffic_light_id] = current_action
                    action_result[traffic_light_id] = {
                        "accepted": False,
                        "reason": "min_green_constraint",
                        "remaining_seconds": round(MIN_GREEN_SECONDS - elapsed_green, 3),
                    }
                    continue
                if requested_action != current_action:
                    traci.trafficlight.setPhase(traffic_light_id, requested_action)
                    session.phase_changed_at[traffic_light_id] = simulation_time
                applied_actions[traffic_light_id] = requested_action
                action_result[traffic_light_id] = {"accepted": True, "reason": None}

            for _ in range(request.step_seconds):
                traci.simulationStep()

            session.previous_actions = previous_actions
            session.current_actions = applied_actions
            session.transition_id += 1
            state_response = self._state_response(session, traci)
            session.last_rewards, session.last_breakdowns = self._reward_payload(session, session.last_state)
            return {
                "session_id": session.session_id,
                "transition_id": session.transition_id,
                "simulation_time": state_response["simulation_time"],
                "requested_actions": request.actions,
                "applied_actions": applied_actions,
                "action_result": action_result,
                "rewards_ready": True,
            }

    async def rewards(self, session_id: str, transition_id: int | None, include_breakdown: bool) -> dict[str, Any]:
        async with self.lock:
            session = self._require_session(session_id)
            if transition_id is not None and transition_id != session.transition_id:
                raise ApiError(
                    409,
                    "REWARD_NOT_READY",
                    "Requested rewards are not available for this transition.",
                    {"requested_transition_id": transition_id, "current_transition_id": session.transition_id},
                )
            payload: dict[str, Any] = {
                "session_id": session.session_id,
                "transition_id": session.transition_id,
                "simulation_time": float(self._traci().simulation.getTime()),
                "reward_version": REWARD_VERSION,
                "rewards": session.last_rewards,
                "global_reward": float(np.mean(list(session.last_rewards.values()))),
                "breakdown_available": include_breakdown,
            }
            if include_breakdown:
                payload["breakdown"] = session.last_breakdowns
            return payload

    async def close(self) -> None:
        async with self.lock:
            if self.session is not None:
                self._close_traci_quietly()
                self.session = None


def _json_value(value: Any) -> Any:
    """Convert NumPy values recursively before returning a FastAPI response."""
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    return value


manager = TraCISessionManager()
app = FastAPI(title="Xiongan Traffic Control API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ApiError)
async def api_error_handler(_: Request, error: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={"error": {"code": error.code, "message": error.message, "details": error.details}},
    )


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(request: Request, error: RequestValidationError) -> JSONResponse:
    """Keep malformed payloads as 422, but expose invalid 20-action sets as 400."""
    errors = [
        {"loc": list(validation_error.get("loc", ())), "msg": validation_error.get("msg"), "type": validation_error.get("type")}
        for validation_error in error.errors()
    ]
    invalid_action_set = request.url.path.endswith("/simulation/actions") and any(
        "actions" in validation_error.get("loc", ()) for validation_error in errors
    )
    if invalid_action_set:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "INVALID_ACTION_SET",
                    "message": "Actions must contain exactly J01 through J20 with integer values from 0 to 3.",
                    "details": {"validation_errors": errors},
                }
            },
        )
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "REQUEST_VALIDATION_ERROR",
                "message": "Request body does not match the API schema.",
                "details": {"validation_errors": errors},
            }
        },
    )


@app.on_event("shutdown")
async def shutdown() -> None:
    await manager.close()


@app.get(f"{API_PREFIX}/health")
async def health_check() -> dict[str, Any]:
    sumo_home = os.environ.get("SUMO_HOME")
    sumo_available = bool(sumo_home and (Path(sumo_home) / "bin" / "sumo.exe").exists())
    return {
        "status": "healthy",
        "api_version": "v1",
        "sumo_available": sumo_available,
        "active_session_id": manager.session.session_id if manager.session else None,
    }


@app.post(f"{API_PREFIX}/simulation/start", status_code=201)
async def start_simulation(request: StartRequest) -> dict[str, Any]:
    return await manager.start(request)


@app.post(f"{API_PREFIX}/simulation/stop")
async def stop_simulation(request: SessionRequest) -> dict[str, Any]:
    return await manager.stop(request.session_id)


@app.post(f"{API_PREFIX}/simulation/reset")
async def reset_simulation(request: ResetRequest) -> dict[str, Any]:
    return await manager.reset(request)


@app.get(f"{API_PREFIX}/simulation/state")
async def get_state(session_id: str) -> dict[str, Any]:
    return await manager.state(session_id)


@app.post(f"{API_PREFIX}/simulation/actions")
async def execute_actions(request: ActionsRequest) -> dict[str, Any]:
    return await manager.actions(request)


@app.get(f"{API_PREFIX}/simulation/rewards")
async def get_rewards(
    session_id: str,
    transition_id: int | None = None,
    include_breakdown: bool = False,
) -> dict[str, Any]:
    return await manager.rewards(session_id, transition_id, include_breakdown)


@app.post(f"{API_PREFIX}/model/predict")
async def predict_model_action(request: ModelPredictRequest) -> dict[str, Any]:
    manager._require_session(request.session_id)
    raise ApiError(
        503,
        "MODEL_NOT_LOADED",
        "Model inference will be enabled after A supplies a versioned shared-DQN artifact.",
        {"model_id": request.model_id, "deterministic": request.deterministic},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
