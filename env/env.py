"""Gym环境封装 - 将SUMO封装为兼容gymnasium的环境接口"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Optional, Tuple

import numpy as np

from configs.constants import (
    INTERSECTION_ORDER,
    STATE_DIMENSION,
    FEATURES_PER_INTERSECTION,
    ACTION_COUNT_PER_INTERSECTION,
    MIN_GREEN_SECONDS,
    SUMO_FILES_DIR,
)
from env.global_state import get_global_state
from env.reward_functions import compute_rewards


class TrafficSignalEnv:
    """20路口信号控制环境

    将SUMO仿真封装为标准的环境接口，支持DQN等强化学习算法训练。

    Observation Space: 440维连续空间 (20路口 × 22特征)
    Action Space: 20路口 × 4相位 (离散动作)

    用法:
        env = TrafficSignalEnv(sumo_cfg_path="sumo_files/xiongan.sumocfg")
        obs, info = env.reset()
        action = 0  # 选择相位
        obs, reward, terminated, truncated, info = env.step(action)
        env.close()
    """

    def __init__(
        self,
        sumo_cfg_path: Optional[str] = None,
        use_gui: bool = False,
        max_steps: int = 3600,
        delta_time: int = 5,
        seed: Optional[int] = None,
    ):
        """初始化环境

        Args:
            sumo_cfg_path: SUMO配置文件路径，默认为xiongan.sumocfg
            use_gui: 是否使用GUI模式
            max_steps: 每个episode的最大步数（秒）
            delta_time: 每个action之间的仿真步进时间（秒）
            seed: 随机种子
        """
        if sumo_cfg_path is None:
            sumo_cfg_path = str(SUMO_FILES_DIR / "xiongan.sumocfg")

        self._sumo_cfg_path = Path(sumo_cfg_path)
        self._use_gui = use_gui
        self._max_steps = max_steps
        self._delta_time = delta_time
        self._seed = seed

        self._traci = None
        self._sumo_binary = None
        self._connected = False

        self._current_actions: dict[str, int] = {}
        self._previous_actions: dict[str, Optional[int]] = {}
        self._phase_changed_at: dict[str, float] = {}

        self._step_count = 0
        self._episode_reward = 0.0

    @property
    def state_dim(self) -> int:
        """状态维度"""
        return STATE_DIMENSION

    @property
    def action_dim(self) -> int:
        """动作维度（单路口）"""
        return ACTION_COUNT_PER_INTERSECTION

    @property
    def num_intersections(self) -> int:
        """路口数量"""
        return len(INTERSECTION_ORDER)

    def _get_sumo_binary(self) -> str:
        """获取SUMO可执行文件路径"""
        if self._sumo_binary:
            return self._sumo_binary

        sumo_home = os.environ.get("SUMO_HOME")
        if not sumo_home:
            raise RuntimeError("SUMO_HOME 环境变量未设置")

        sumo_exe = Path(sumo_home) / "bin" / ("sumo-gui.exe" if self._use_gui else "sumo.exe")
        if not sumo_exe.exists():
            raise RuntimeError(f"SUMO 可执行文件未找到: {sumo_exe}")

        self._sumo_binary = str(sumo_exe)
        return self._sumo_binary

    def reset(
        self, seed: Optional[int] = None, options: Optional[dict] = None
    ) -> Tuple[np.ndarray, dict]:
        """重置环境

        Args:
            seed: 随机种子
            options: 额外选项

        Returns:
            (observation, info)
        """
        if seed is not None:
            self._seed = seed

        self._close_traci()

        import traci

        command = [self._get_sumo_binary(), "-c", str(self._sumo_cfg_path), "--no-step-log"]
        if self._seed is not None:
            command.extend(["--seed", str(self._seed)])

        traci.start(command, numRetries=1)
        self._traci = traci
        self._connected = True

        self._init_actions()

        self._step_count = 0
        self._episode_reward = 0.0

        obs = get_global_state(num_intersections=self.num_intersections)
        info = self._get_info()

        return obs, info

    def _init_actions(self) -> None:
        """初始化所有路口的动作状态"""
        sim_time = float(self._traci.simulation.getTime())
        for tl_id in INTERSECTION_ORDER:
            self._current_actions[tl_id] = int(self._traci.trafficlight.getPhase(tl_id))
            self._previous_actions[tl_id] = None
            self._phase_changed_at[tl_id] = sim_time

    def step(
        self, action: Any
    ) -> Tuple[np.ndarray, float, bool, bool, dict]:
        """执行一步仿真

        Args:
            action: 动作，可以是:
                - int: 单个相位（适用于单路口）
                - dict: {tl_id: phase} 字典（适用于多路口）
                - np.ndarray: 动作数组

        Returns:
            (observation, reward, terminated, truncated, info)
        """
        traci = self._traci
        sim_time = float(traci.simulation.getTime())

        current_actions = self._parse_action(action)

        applied_actions = {}
        action_results = {}

        for tl_id in INTERSECTION_ORDER:
            requested = current_actions.get(tl_id, 0)
            current = int(traci.trafficlight.getPhase(tl_id))
            elapsed = sim_time - self._phase_changed_at.get(tl_id, 0)

            if requested != current and elapsed < MIN_GREEN_SECONDS:
                applied_actions[tl_id] = current
                action_results[tl_id] = {
                    "accepted": False,
                    "reason": "min_green_constraint",
                }
            else:
                if requested != current:
                    traci.trafficlight.setPhase(tl_id, requested)
                    self._phase_changed_at[tl_id] = sim_time
                applied_actions[tl_id] = requested
                action_results[tl_id] = {"accepted": True}

        self._previous_actions = self._current_actions.copy()
        self._current_actions = applied_actions

        for _ in range(self._delta_time):
            traci.simulationStep()

        self._step_count += 1

        obs = get_global_state(num_intersections=self.num_intersections)

        rewards_dict, breakdowns, global_reward = compute_rewards(
            obs, self._current_actions, self._previous_actions
        )

        self._episode_reward += global_reward

        terminated = False
        truncated = (sim_time + self._delta_time) >= self._max_steps

        info = {
            "time": float(traci.simulation.getTime()),
            "rewards_per_intersection": rewards_dict,
            "breakdowns": breakdowns,
            "vehicle_count": self._get_vehicle_count(),
            "applied_actions": applied_actions,
            "step": self._step_count,
            "queue_length": self._get_total_queue(),
        }

        return obs, global_reward, terminated, truncated, info

    def _parse_action(self, action: Any) -> dict[str, int]:
        """解析动作输入为标准字典格式"""
        if isinstance(action, dict):
            return action
        elif isinstance(action, (int, np.integer)):
            return {tl_id: int(action) for tl_id in INTERSECTION_ORDER}
        elif isinstance(action, np.ndarray):
            if action.ndim == 0:
                return {tl_id: int(action.item()) for tl_id in INTERSECTION_ORDER}
            elif action.ndim == 1:
                if len(action) == self.num_intersections:
                    return {tl_id: int(a) for tl_id, a in zip(INTERSECTION_ORDER, action)}
                else:
                    return {tl_id: int(action[0]) for tl_id in INTERSECTION_ORDER}
            else:
                return {tl_id: int(a) for tl_id, a in zip(INTERSECTION_ORDER, action.flatten()[:self.num_intersections])}
        elif isinstance(action, list):
            if len(action) == self.num_intersections:
                return {tl_id: int(a) for tl_id, a in zip(INTERSECTION_ORDER, action)}
            else:
                return {tl_id: int(action[0]) for tl_id in INTERSECTION_ORDER}
        else:
            return {tl_id: 0 for tl_id in INTERSECTION_ORDER}

    def _get_vehicle_count(self) -> int:
        """获取当前车辆数量"""
        if self._traci:
            return len(self._traci.vehicle.getIDList())
        return 0

    def _get_total_queue(self) -> float:
        """获取总排队长度"""
        if not self._traci:
            return 0.0
        total = 0.0
        for tl_id in INTERSECTION_ORDER:
            try:
                controlled_lanes = self._traci.trafficlight.getControlledLanes(tl_id)
                for lane in controlled_lanes:
                    total += float(self._traci.lane.getLastStepHaltingNumber(lane))
            except Exception:
                pass
        return total

    def _get_info(self) -> dict:
        """获取当前环境信息"""
        return {
            "time": float(self._traci.simulation.getTime()) if self._traci else 0,
            "vehicle_count": self._get_vehicle_count(),
            "queue_length": self._get_total_queue(),
        }

    def _close_traci(self) -> None:
        """关闭TraCI连接"""
        if self._traci and self._connected:
            try:
                self._traci.close(False)
            except Exception:
                pass
            self._connected = False
            self._traci = None

    def close(self) -> None:
        """关闭环境"""
        self._close_traci()

    def get_valid_actions(self) -> dict[str, list[int]]:
        """获取每个路口的合法动作"""
        valid = {}
        if not self._traci:
            return {tl_id: list(range(ACTION_COUNT_PER_INTERSECTION)) for tl_id in INTERSECTION_ORDER}

        sim_time = float(self._traci.simulation.getTime())

        for tl_id in INTERSECTION_ORDER:
            current_phase = self._current_actions.get(tl_id, 0)
            elapsed = sim_time - self._phase_changed_at.get(tl_id, 0)

            if elapsed < MIN_GREEN_SECONDS:
                valid[tl_id] = [current_phase]
            else:
                valid[tl_id] = list(range(ACTION_COUNT_PER_INTERSECTION))

        return valid

    def __enter__(self) -> "TrafficSignalEnv":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
