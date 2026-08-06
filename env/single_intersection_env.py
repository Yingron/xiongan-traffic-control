"""Single-intersection and parameter-sharing SUMO environments.

Each episode runs the validated 20-intersection SUMO network, while the agent
observes and controls one selected junction.  This lets a single 22-input,
4-action DQN share parameters across all junctions without changing the
traffic-signal interface used by the full-network environment.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import numpy as np

from configs.constants import ACTION_COUNT_PER_INTERSECTION, FEATURES_PER_INTERSECTION, INTERSECTION_ORDER, MIN_GREEN_SECONDS, SUMO_FILES_DIR, YELLOW_TRANSITION_SECONDS
from env.global_state import _extract_intersection_state
from env.reward_functions import compute_reward

try:
    import gymnasium as gym
    from gymnasium import spaces
    _EnvBase = gym.Env
except ImportError:  # Allows SUMO smoke tests before the ML packages are installed.
    class _Discrete:
        def __init__(self, n: int) -> None:
            self.n = n

        def sample(self) -> int:
            return int(np.random.randint(self.n))

        def contains(self, value: object) -> bool:
            return isinstance(value, (int, np.integer)) and 0 <= int(value) < self.n

    class _Box:
        def __init__(self, low: float, high: float, shape: tuple[int, ...], dtype: type[np.floating[Any]]) -> None:
            self.low, self.high, self.shape, self.dtype = low, high, shape, dtype

    class _Spaces:
        Discrete = _Discrete
        Box = _Box

    spaces = _Spaces()
    _EnvBase = object


class SingleIntersectionEnv(_EnvBase):
    """Control one junction in the full 20-intersection SUMO scenario."""

    metadata = {"render_modes": [None, "human"]}

    def __init__(
        self,
        intersection_id: str = "J01",
        sumo_cfg_path: str | Path | None = None,
        use_gui: bool = False,
        max_steps: int = 720,
        delta_time: int = 5,
        seed: int | None = None,
    ) -> None:
        if intersection_id not in INTERSECTION_ORDER:
            raise ValueError(f"Unknown intersection: {intersection_id}")
        self.intersection_id = intersection_id
        self.sumo_cfg_path = Path(sumo_cfg_path or SUMO_FILES_DIR / "xiongan_20.sumocfg")
        self.use_gui = use_gui
        self.max_steps = max_steps
        self.delta_time = delta_time
        self.seed_value = seed
        self.action_space = spaces.Discrete(ACTION_COUNT_PER_INTERSECTION)
        self.observation_space = spaces.Box(low=-1.0, high=1.0, shape=(FEATURES_PER_INTERSECTION,), dtype=np.float32)
        self._traci: Any | None = None
        self._previous_action: int | None = None
        self._phase_changed_at = 0.0
        self._step_count = 0

    def _sumo_binary(self) -> str:
        home = os.environ.get("SUMO_HOME")
        if home:
            candidate = Path(home) / "bin" / ("sumo-gui.exe" if self.use_gui else "sumo.exe")
            if candidate.exists():
                return str(candidate)
        return "sumo-gui" if self.use_gui else "sumo"

    def reset(self, *, seed: Optional[int] = None, options: Optional[dict] = None) -> tuple[np.ndarray, dict]:
        if seed is not None:
            self.seed_value = seed
            np.random.seed(seed)
        self.close()
        if not self.sumo_cfg_path.exists():
            raise FileNotFoundError(f"SUMO configuration not found: {self.sumo_cfg_path}")
        import traci

        command = [self._sumo_binary(), "-c", str(self.sumo_cfg_path), "--no-step-log", "true"]
        if self.seed_value is not None:
            command.extend(["--seed", str(self.seed_value)])
        traci.start(command, numRetries=1)
        self._traci = traci
        traci.trafficlight.setProgram(self.intersection_id, "rl4")
        self._previous_action = int(traci.trafficlight.getPhase(self.intersection_id))
        self._phase_changed_at = float(traci.simulation.getTime())
        self._step_count = 0
        return self._state(), self._info()

    def _state(self) -> np.ndarray:
        assert self._traci is not None
        return _extract_intersection_state(self._traci, self.intersection_id)

    def _queue_length(self) -> float:
        assert self._traci is not None
        lanes = set(self._traci.trafficlight.getControlledLanes(self.intersection_id))
        return float(sum(self._traci.lane.getLastStepHaltingNumber(lane) for lane in lanes))

    def _info(self, breakdown: dict | None = None, applied_action: int | None = None) -> dict:
        assert self._traci is not None
        return {
            "intersection_id": self.intersection_id,
            "time": float(self._traci.simulation.getTime()),
            "vehicle_count": int(self._traci.vehicle.getIDCount()),
            "queue_length": self._queue_length(),
            "phase": int(self._traci.trafficlight.getPhase(self.intersection_id)),
            "applied_action": applied_action,
            "breakdown": breakdown or {},
            "step": self._step_count,
        }

    def _record_incidents(self, incidents: dict[str, int]) -> None:
        """Accumulate safety events across every simulated second."""
        assert self._traci is not None
        incidents["collisions"] += len(self._traci.simulation.getCollidingVehiclesIDList())
        incidents["teleports"] += len(self._traci.simulation.getStartingTeleportIDList())

    def _set_yellow_transition(self, target_phase: int) -> None:
        assert self._traci is not None
        current_state = self._traci.trafficlight.getRedYellowGreenState(self.intersection_id)
        logic = next(
            (candidate for candidate in self._traci.trafficlight.getAllProgramLogics(self.intersection_id) if candidate.programID == "rl4"),
            None,
        )
        if logic is None or len(logic.phases) != ACTION_COUNT_PER_INTERSECTION:
            raise RuntimeError(f"{self.intersection_id} has no valid four-action rl4 program")
        target_state = logic.phases[target_phase].state
        yellow_state = "".join("y" if old in "Gg" and new == "r" else "r" for old, new in zip(current_state, target_state))
        self._traci.trafficlight.setRedYellowGreenState(self.intersection_id, yellow_state)

    def step(self, action: int) -> tuple[np.ndarray, float, bool, bool, dict]:
        if self._traci is None:
            raise RuntimeError("Call reset() before step().")
        if not self.action_space.contains(action):
            raise ValueError(f"Action must be in [0, 3], got {action!r}")
        traci = self._traci
        now = float(traci.simulation.getTime())
        current = int(traci.trafficlight.getPhase(self.intersection_id))
        applied = current if int(action) != current and now - self._phase_changed_at < MIN_GREEN_SECONDS else int(action)
        yellow_steps = min(YELLOW_TRANSITION_SECONDS, self.delta_time) if applied != current else 0
        incidents = {"collisions": 0, "teleports": 0}
        if yellow_steps:
            self._set_yellow_transition(applied)
        for _ in range(yellow_steps):
            traci.simulationStep()
            self._record_incidents(incidents)
        if yellow_steps:
            traci.trafficlight.setProgram(self.intersection_id, "rl4")
            traci.trafficlight.setPhase(self.intersection_id, applied)
            # Minimum green starts when the target green actually becomes active,
            # rather than when its preceding yellow transition begins.
            self._phase_changed_at = now + yellow_steps
        for _ in range(self.delta_time - yellow_steps):
            traci.simulationStep()
            self._record_incidents(incidents)
        self._step_count += 1
        state = self._state()
        reward, breakdown = compute_reward(state, applied, self._previous_action)
        self._previous_action = applied
        terminated = traci.simulation.getMinExpectedNumber() <= 0
        truncated = float(traci.simulation.getTime()) >= self.max_steps
        info = self._info(breakdown, applied)
        info["incidents"] = incidents
        return state, reward, terminated, truncated, info

    def close(self) -> None:
        if self._traci is not None:
            try:
                self._traci.close()
            finally:
                self._traci = None


class MultiIntersectionSharedEnv(SingleIntersectionEnv):
    """Sample a junction per episode for parameter-shared DQN training."""

    def __init__(self, intersections: tuple[str, ...] = INTERSECTION_ORDER, **kwargs: Any) -> None:
        if not intersections:
            raise ValueError("intersections cannot be empty")
        self.intersections = tuple(intersections)
        self._episode_index = 0
        super().__init__(intersection_id=self.intersections[0], **kwargs)

    def reset(self, *, seed: Optional[int] = None, options: Optional[dict] = None) -> tuple[np.ndarray, dict]:
        if seed is not None:
            self._episode_index = seed % len(self.intersections)
        self.intersection_id = self.intersections[self._episode_index % len(self.intersections)]
        self._episode_index += 1
        state, info = super().reset(seed=seed, options=options)
        info["sampled_intersection"] = self.intersection_id
        return state, info
