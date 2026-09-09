"""REST API for the 30-intersection Xiongan traffic-control platform.

The public contract is defined in ``docs/接口文档.md``.  This module deliberately
does not fall back to the legacy one-intersection, 26-dimensional environment:
an invalid or incomplete SUMO network is reported to the caller as a 503.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
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
from server.model_service import ModelServiceError, SB3ModelService
from server.llm_service import LLMService, LLMServiceError
from configs.constants import (
    INTERSECTION_ORDER,
    ACTION_NAMES,
    FEATURES_PER_INTERSECTION,
    STATE_DIMENSION,
    STATE_LAYOUT_VERSION,
    MIN_GREEN_SECONDS,
    API_VERSION,
)

API_PREFIX = "/api/v1"
STATE_LAYOUT_VERSION = "v1-30x22"
REWARD_VERSION = "v3"
SCENARIO_CONFIG_PATHS: dict[str, Path] = {
    "real_peak": PROJECT_ROOT / "sumo_files" / "xiongan_real_peak.sumocfg",
    "real_offpeak": PROJECT_ROOT / "sumo_files" / "xiongan_real_offpeak.sumocfg",
    "real_evening": PROJECT_ROOT / "sumo_files" / "xiongan_real_evening.sumocfg",
}
SCENARIO_ALIASES = {
    "morning_peak": "real_peak",
    "peak": "real_peak",
    "offpeak": "real_offpeak",
    "evening_peak": "real_evening",
    "evening": "real_evening",
}


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
    scenario: str = Field(default="real_peak", min_length=1, max_length=64)
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
                "actions must contain exactly J01 through J30; "
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


class EdgePredictRequest(SessionRequest):
    """Request a batched 30-junction decision from the ONNX edge service."""

    model_id: str = Field(min_length=1)


class LLMAnalyzeRequest(BaseModel):
    """Request a cloud-brain analysis of one intersection's state window.

    ``text`` is the rendered Chinese state window (see llm_data.text_format);
    callers build it from the 660-D state or from SUMO snapshots.
    """

    text: str = Field(min_length=20, max_length=8192)
    junction: str | None = Field(default=None, min_length=2, max_length=8)


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
    total_arrived: int = 0
    total_departed: int = 0


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
    def _scenario_config_path(scenario: str) -> Path:
        """Resolve only the three public real-demand scenarios.

        Previously the API stored ``scenario`` as metadata while always
        launching ``xiongan_30.sumocfg``.  That made an 8000-port Unity scene
        switch visually plausible but traffic-demand incorrect.  The resolver
        keeps the scenario and loaded SUMO configuration inseparable.
        """

        scenario = SCENARIO_ALIASES.get(scenario, scenario)
        config_path = SCENARIO_CONFIG_PATHS.get(scenario)
        if config_path is None:
            raise ApiError(
                422,
                "INVALID_SCENARIO",
                "scenario must be one of real_peak, real_offpeak, or real_evening.",
                {"scenario": scenario, "supported_scenarios": sorted(SCENARIO_CONFIG_PATHS)},
            )
        return config_path

    @staticmethod
    def _sumo_binary(use_gui: bool) -> str:
        sumo_home = os.environ.get("SUMO_HOME")
        binary_name = "sumo-gui" if use_gui else "sumo"
        candidates: list[Path] = []
        if sumo_home:
            bin_dir = Path(sumo_home) / "bin"
            # Windows packages use .exe while Debian SUMO packages use bare names.
            candidates.extend((bin_dir / f"{binary_name}.exe", bin_dir / binary_name))
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)
        executable = shutil.which(binary_name) or shutil.which(f"{binary_name}.exe")
        if executable:
            return executable
        raise ApiError(
            503,
            "TRACI_UNAVAILABLE",
            "SUMO executable was not found. Configure SUMO_HOME or put SUMO on PATH.",
            {
                "sumo_home": sumo_home,
                "searched": [str(candidate) for candidate in candidates],
                "binary_name": binary_name,
            },
        )

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
                "SUMO network does not expose exactly the required traffic lights J01 through J30.",
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
        """Extract state and explicitly reorder slices to the public J01..J30 contract."""
        from env.global_state import get_global_state

        raw_state = get_global_state(num_intersections=len(INTERSECTION_ORDER))
        if raw_state.shape != (STATE_DIMENSION,):
            raise ApiError(
                503,
                "SIMULATION_STATE_INVALID",
                "Global state extractor did not return a 660-dimensional state vector.",
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
    def _visualization_payload(
        traci: Any,
        state: np.ndarray,
        *,
        total_arrived: int,
        total_departed: int,
    ) -> dict[str, Any]:
        """Build a Unity-oriented view from the same authoritative TraCI tick.

        The public 660-D state remains the control contract.  This additional
        payload only removes the former need for Unity to open a separate 8765
        visualization session when it is connected directly to the formal API.
        Individual vehicle reads are best-effort: a vehicle may leave SUMO in
        the interval between ``getIDList`` and a property lookup.
        """

        traffic_lights = []
        for traffic_light_id in INTERSECTION_ORDER:
            phase = int(traci.trafficlight.getPhase(traffic_light_id))
            traffic_lights.append(
                {
                    "id": traffic_light_id,
                    "phase": phase,
                    "phase_name": ACTION_NAMES[phase],
                }
            )

        vehicles = []
        for vehicle_id in traci.vehicle.getIDList():
            try:
                x, y = traci.vehicle.getPosition(vehicle_id)
                vehicles.append(
                    {
                        "id": vehicle_id,
                        "x": float(x),
                        "y": float(y),
                        "angle": float(traci.vehicle.getAngle(vehicle_id)),
                        "speed": float(traci.vehicle.getSpeed(vehicle_id)),
                        "type": str(traci.vehicle.getTypeID(vehicle_id)),
                    }
                )
            except Exception:
                # TraCI can remove a vehicle during this short read window.
                continue

        observations = state.reshape(len(INTERSECTION_ORDER), FEATURES_PER_INTERSECTION)
        return {
            "traffic_lights": traffic_lights,
            "vehicles": vehicles,
            "metrics": {
                "vehicle_count": len(vehicles),
                "avg_queue": float(np.mean(np.sum(observations[:, 0:4], axis=1))),
                "avg_wait": float(np.mean(np.sum(observations[:, 4:8], axis=1))),
                "avg_speed": 0.0,
                "total_arrived": total_arrived,
                "total_departed": total_departed,
                "simulation_time": float(traci.simulation.getTime()),
            },
        }

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
            "visualization": TraCISessionManager._visualization_payload(
                traci,
                state,
                total_arrived=session.total_arrived,
                total_departed=session.total_departed,
            ),
        }

    async def start(self, request: StartRequest) -> dict[str, Any]:
        async with self.lock:
            if self.session is not None:
                raise ApiError(409, "SESSION_BUSY", "A simulation session is already active.")
            scenario = SCENARIO_ALIASES.get(request.scenario, request.scenario)
            config_path = self._scenario_config_path(scenario)
            if not config_path.exists():
                raise ApiError(
                    503,
                    "SIMULATION_ASSET_INVALID",
                    "SUMO configuration file was not found.",
                    {"config_path": str(config_path), "scenario": scenario},
                )

            traci = self._traci()
            session = SimulationSession(
                session_id=f"sim_{uuid.uuid4().hex}",
                scenario=scenario,
                use_gui=request.use_gui,
                seed=request.seed,
                config_path=config_path,
            )
            command = [
                self._sumo_binary(request.use_gui),
                "-c",
                str(config_path),
                "--no-step-log",
                "--no-warnings",
                "--time-to-teleport",
                "-1",
            ]
            if request.seed is not None:
                command.extend(["--seed", str(request.seed)])

            try:
                self._validate_sumo_assets(self._sumo_binary(False), config_path)
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
                    {"config_path": str(config_path), "scenario": scenario, "reason": str(error)},
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
                session.total_arrived += int(traci.simulation.getArrivedNumber())
                session.total_departed += int(traci.simulation.getDepartedNumber())

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

    async def stream_snapshot(self, session_id: str, channels: set[str] | frozenset[str]) -> dict[str, Any]:
        """Return one lock-consistent WebSocket snapshot for the selected channels."""
        from server.websocket_server import snapshot_payload

        async with self.lock:
            session = self._require_session(session_id)
            state = self._state_response(session, self._traci())
            rewards: dict[str, Any] | None = None
            if "reward" in channels:
                rewards = {
                    "reward_version": REWARD_VERSION,
                    "rewards": session.last_rewards,
                    "global_reward": float(np.mean(list(session.last_rewards.values()))),
                }
            return snapshot_payload(state, rewards, channels)

    async def inference_state(self, session_id: str) -> tuple[int, np.ndarray]:
        """Return the transition id and a copy of the real 660-dimensional state."""
        async with self.lock:
            session = self._require_session(session_id)
            raw_ids = self._validate_intersections(self._traci())
            state = self._ordered_global_state(raw_ids)
            session.last_state = state
            return session.transition_id, state.copy()

    async def inference_masks(self, session_id: str) -> np.ndarray:
        """返回 30×4 需求门控动作掩码（与 state 同一仿真时刻，供掩码模型推理）。"""
        from env.global_state import get_action_masks

        async with self.lock:
            self._require_session(session_id)
            raw_ids = self._validate_intersections(self._traci())
            return get_action_masks(self._traci(), tuple(raw_ids))

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
model_service = SB3ModelService(
    registry_path=PROJECT_ROOT / "configs" / "model_registry.json",
    project_root=PROJECT_ROOT,
)
llm_service = LLMService()  # llama.cpp 云脑服务（LLM_BASE_URL/LLM_MODEL 可经环境变量覆盖）
app = FastAPI(title="Xiongan Traffic Control API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from server.websocket_server import WebSocketHub

websocket_hub = WebSocketHub(manager, ActionsRequest, ApiError)
websocket_hub.register(app, f"{API_PREFIX}/ws")


@app.exception_handler(ApiError)
async def api_error_handler(_: Request, error: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={"error": {"code": error.code, "message": error.message, "details": error.details}},
    )


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(request: Request, error: RequestValidationError) -> JSONResponse:
    """Keep malformed payloads as 422, but expose invalid 30-action sets as 400."""
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
                    "message": "Actions must contain exactly J01 through J30 with integer values from 0 to 3.",
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
    try:
        sumo_executable = manager._sumo_binary(use_gui=False)
    except ApiError:
        sumo_executable = None
    return {
        "status": "healthy",
        "api_version": "v1",
        "sumo_available": bool(sumo_executable),
        "sumo_executable": sumo_executable,
        "active_session_id": manager.session.session_id if manager.session else None,
    }


@app.get(f"{API_PREFIX}/edge/health")
async def edge_health_check() -> dict[str, Any]:
    """Check the optional ONNX edge service configured for deployment."""

    edge_url = os.environ.get("EDGE_INFERENCE_URL")
    if not edge_url:
        raise ApiError(503, "EDGE_SERVICE_UNAVAILABLE", "EDGE_INFERENCE_URL is not configured.")
    endpoint = f"{edge_url.rstrip('/')}/health"
    try:
        with urllib.request.urlopen(endpoint, timeout=3) as response:
            payload = response.read().decode("utf-8")
    except (OSError, urllib.error.URLError) as error:
        raise ApiError(
            503,
            "EDGE_SERVICE_UNAVAILABLE",
            "The ONNX edge service could not be reached.",
            {"endpoint": endpoint, "reason": str(error)},
        ) from error
    try:
        status = json.loads(payload)
    except ValueError as error:
        raise ApiError(503, "EDGE_SERVICE_UNAVAILABLE", "The edge service returned invalid JSON.") from error
    return {"status": "healthy", "edge_url": edge_url, "edge": status}


@app.post(f"{API_PREFIX}/simulation/start", status_code=201)
async def start_simulation(request: StartRequest) -> dict[str, Any]:
    result = await manager.start(request)
    await websocket_hub.broadcast_snapshot(result["session_id"])
    return result


@app.post(f"{API_PREFIX}/simulation/stop")
async def stop_simulation(request: SessionRequest) -> dict[str, Any]:
    result = await manager.stop(request.session_id)
    await websocket_hub.broadcast_event(
        request.session_id,
        {"type": "simulation.stopped", **result},
        unsubscribe=True,
    )
    return result


@app.post(f"{API_PREFIX}/simulation/reset")
async def reset_simulation(request: ResetRequest) -> dict[str, Any]:
    result = await manager.reset(request)
    await websocket_hub.broadcast_event(
        request.session_id,
        {
            "type": "simulation.reset",
            "previous_session_id": request.session_id,
            "session_id": result["session_id"],
            "transition_id": result["transition_id"],
        },
        unsubscribe=True,
    )
    return result


@app.get(f"{API_PREFIX}/simulation/state")
async def get_state(session_id: str) -> dict[str, Any]:
    return await manager.state(session_id)


@app.post(f"{API_PREFIX}/simulation/actions")
async def execute_actions(request: ActionsRequest) -> dict[str, Any]:
    result = await manager.actions(request)
    await websocket_hub.broadcast_snapshot(request.session_id)
    return result


@app.get(f"{API_PREFIX}/simulation/rewards")
async def get_rewards(
    session_id: str,
    transition_id: int | None = None,
    include_breakdown: bool = False,
) -> dict[str, Any]:
    return await manager.rewards(session_id, transition_id, include_breakdown)


@app.post(f"{API_PREFIX}/model/predict")
async def predict_model_action(request: ModelPredictRequest) -> dict[str, Any]:
    transition_id, state = await manager.inference_state(request.session_id)
    masks = await manager.inference_masks(request.session_id)
    try:
        prediction = model_service.predict(
            request.model_id,
            state,
            INTERSECTION_ORDER,
            deterministic=request.deterministic,
            action_masks=masks,
        )
    except ModelServiceError as error:
        raise ApiError(error.status_code, error.code, error.message, error.details) from error
    return {
        "session_id": request.session_id,
        "model_id": request.model_id,
        "transition_id": transition_id,
        "state_layout_version": STATE_LAYOUT_VERSION,
        "deterministic": request.deterministic,
        "action_masks": np.asarray(masks, dtype=np.float32).tolist(),
        "action_masks_flat": np.asarray(masks, dtype=np.float32).reshape(-1).tolist(),
        "action_mask_shape": [len(INTERSECTION_ORDER), 4],
        "actions_ordered": [prediction["actions"][junction_id] for junction_id in INTERSECTION_ORDER],
        **prediction,
    }


@app.post(f"{API_PREFIX}/edge/predict")
async def predict_edge_action(request: EdgePredictRequest) -> dict[str, Any]:
    """Forward the current 660-D state and 30 action masks to the ONNX edge service.

    This endpoint keeps the 30-junction API contract intact while exercising the
    real container-to-container inference path used in deployment.
    """

    edge_url = os.environ.get("EDGE_INFERENCE_URL")
    if not edge_url:
        raise ApiError(503, "EDGE_SERVICE_UNAVAILABLE", "EDGE_INFERENCE_URL is not configured.")
    transition_id, state = await manager.inference_state(request.session_id)
    masks = await manager.inference_masks(request.session_id)
    observations = np.asarray(state, dtype=np.float32).reshape(len(INTERSECTION_ORDER), FEATURES_PER_INTERSECTION)
    payload = {
        "model_id": request.model_id,
        "state": observations.tolist(),
        "action_mask": np.asarray(masks, dtype=np.float32).tolist(),
    }
    endpoint = f"{edge_url.rstrip('/')}/predict"
    body = json.dumps(payload).encode("utf-8")
    edge_request = urllib.request.Request(endpoint, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(edge_request, timeout=5) as response:
            edge_response = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, urllib.error.URLError) as error:
        raise ApiError(
            503,
            "EDGE_SERVICE_UNAVAILABLE",
            "The ONNX edge prediction request failed.",
            {"endpoint": endpoint, "reason": str(error)},
        ) from error
    actions = edge_response.get("actions")
    if not isinstance(actions, list) or len(actions) != len(INTERSECTION_ORDER):
        raise ApiError(503, "EDGE_SERVICE_INVALID_RESPONSE", "The edge service did not return 30 actions.")
    ordered_actions = [int(action) for action in actions]
    return {
        "session_id": request.session_id,
        "model_id": request.model_id,
        "transition_id": transition_id,
        "state_layout_version": STATE_LAYOUT_VERSION,
        "action_masks": np.asarray(masks, dtype=np.float32).tolist(),
        "action_masks_flat": np.asarray(masks, dtype=np.float32).reshape(-1).tolist(),
        "action_mask_shape": [len(INTERSECTION_ORDER), 4],
        "actions_ordered": ordered_actions,
        "actions": {junction_id: action for junction_id, action in zip(INTERSECTION_ORDER, ordered_actions)},
        "latency_ms": edge_response.get("latency_ms"),
        "edge_backend": edge_response.get("backend"),
    }


@app.post(f"{API_PREFIX}/llm/analyze")
async def analyze_with_llm(request: LLMAnalyzeRequest) -> dict[str, Any]:
    """云端 LLM 事件识别与管控建议（赛道 C 云脑）。

    调用 llama.cpp 服务（OpenAI 兼容接口）分析一个路口的交通状态窗口文本，
    返回结构化事件判定；建议 JSON 经合法性校验后由上层决定是否干预信号。
    """
    try:
        result = llm_service.analyze(request.text, junction=request.junction)
    except LLMServiceError as error:
        raise ApiError(error.status_code, error.code, error.message, error.details) from error
    return {
        "api_version": API_VERSION,
        "state_layout_version": STATE_LAYOUT_VERSION,
        **result,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
