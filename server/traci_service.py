"""TraCI服务封装 - 管理SUMO连接和仿真控制"""
from __future__ import annotations

import os
import time
import subprocess
from pathlib import Path
from typing import Any, Optional
import numpy as np

INTERSECTION_ORDER = tuple(f"J{i:02d}" for i in range(1, 31))
STATE_DIMENSION = 660
FEATURES_PER_INTERSECTION = 22
ACTION_NAMES = ("NS_Straight", "NS_Left", "EW_Straight", "EW_Left")
MIN_GREEN_SECONDS = 15


class TraCIService:
    """封装SUMO的TraCI接口，提供30路口信号控制功能"""

    def __init__(self, sumo_config_path: Optional[str] = None):
        self._traci: Any = None
        self._sumo_binary: Optional[str] = None
        self._config_path = Path(sumo_config_path) if sumo_config_path else None
        self._connected = False
        self._current_actions: dict[str, int] = {}
        self._previous_actions: dict[str, Optional[int]] = {}
        self._phase_changed_at: dict[str, float] = {}

    @property
    def connected(self) -> bool:
        return self._connected

    def _get_traci(self) -> Any:
        if self._traci is None:
            import traci
            self._traci = traci
        return self._traci

    def _get_sumo_binary(self) -> str:
        if self._sumo_binary:
            return self._sumo_binary
        sumo_home = os.environ.get("SUMO_HOME")
        if not sumo_home:
            raise RuntimeError("SUMO_HOME is not configured")
        sumo_exe = Path(sumo_home) / "bin" / "sumo.exe"
        if not sumo_exe.exists():
            raise RuntimeError(f"SUMO executable not found: {sumo_exe}")
        self._sumo_binary = str(sumo_exe)
        return self._sumo_binary

    def validate_network(self, config_path: Optional[Path] = None) -> bool:
        """预验证SUMO网络文件是否有效"""
        config = config_path or self._config_path
        if config is None:
            raise ValueError("No SUMO config path provided")

        sumo_binary = self._get_sumo_binary()
        try:
            result = subprocess.run(
                [sumo_binary, "-c", str(config), "--end", "0", "--no-step-log"],
                capture_output=True, text=True, timeout=30
            )
            return result.returncode == 0
        except Exception as e:
            print(f"Network validation failed: {e}")
            return False

    def start(self, config_path: Optional[str] = None, seed: Optional[int] = None) -> None:
        """启动SUMO仿真"""
        import traci

        config = Path(config_path) if config_path else self._config_path
        if config is None or not config.exists():
            raise FileNotFoundError(f"SUMO config not found: {config}")

        command = [self._get_sumo_binary(), "-c", str(config), "--no-step-log"]
        if seed is not None:
            command.extend(["--seed", str(seed)])

        traci.start(command, numRetries=1)
        self._traci = traci
        self._connected = True

        self._init_actions()

    def _init_actions(self) -> None:
        """初始化所有路口的动作状态"""
        traci = self._get_traci()
        sim_time = float(traci.simulation.getTime())
        for tl_id in INTERSECTION_ORDER:
            self._current_actions[tl_id] = int(traci.trafficlight.getPhase(tl_id))
            self._previous_actions[tl_id] = None
            self._phase_changed_at[tl_id] = sim_time

    def get_current_actions(self) -> dict[str, int]:
        """获取当前所有路口的动作"""
        return self._current_actions.copy()

    def get_phase(self, tl_id: str) -> int:
        """获取指定路口的当前相位"""
        traci = self._get_traci()
        return int(traci.trafficlight.getPhase(tl_id))

    def step(self, actions: dict[str, int], step_seconds: int = 5) -> tuple[float, dict]:
        """执行一步仿真"""
        traci = self._get_traci()
        sim_time = float(traci.simulation.getTime())
        applied_actions: dict[str, int] = {}
        action_results: dict[str, dict] = {}

        for tl_id in INTERSECTION_ORDER:
            requested = actions[tl_id]
            current = int(traci.trafficlight.getPhase(tl_id))
            elapsed = sim_time - self._phase_changed_at[tl_id]

            if requested != current and elapsed < MIN_GREEN_SECONDS:
                applied_actions[tl_id] = current
                action_results[tl_id] = {
                    "accepted": False,
                    "reason": "min_green_constraint",
                    "remaining": round(MIN_GREEN_SECONDS - elapsed, 3)
                }
            else:
                if requested != current:
                    traci.trafficlight.setPhase(tl_id, requested)
                    self._phase_changed_at[tl_id] = sim_time
                applied_actions[tl_id] = requested
                action_results[tl_id] = {"accepted": True, "reason": None}

        self._previous_actions = self._current_actions.copy()
        self._current_actions = applied_actions

        for _ in range(step_seconds):
            traci.simulationStep()

        new_time = float(traci.simulation.getTime())
        return new_time, {"applied": applied_actions, "results": action_results}

    def get_simulation_time(self) -> float:
        """获取当前仿真时间"""
        traci = self._get_traci()
        return float(traci.simulation.getTime())

    def get_vehicle_count(self) -> int:
        """获取当前车辆数量"""
        traci = self._get_traci()
        return len(traci.vehicle.getIDList())

    def close(self) -> None:
        """关闭TraCI连接"""
        if self._traci and self._connected:
            try:
                self._traci.close(False)
            except Exception:
                pass
            self._connected = False
            self._traci = None
