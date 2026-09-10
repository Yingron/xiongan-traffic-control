"""自适应控制基线算法 - Max-Pressure（最大压力）感应控制

理论依据：
    Max-Pressure Control of Traffic Networks (Varaiya, 2013)
    核心思想：每个周期选择能释放最大排队压力的相位

实现逻辑：
    1. 获取4个方向(N/S/E/W)的排队长度
    2. 计算各相位的压力值：
       - Phase 0 (NS_Straight): pressure = queue[N] + queue[S]
       - Phase 2 (EW_Straight): pressure = queue[E] + queue[W]
    3. 选择压力最大的相位
    4. 遵守最小绿灯时间约束(MIN_GREEN_SECONDS=15s)

用法:
    from baselines.adaptive import MaxPressureController
    controller = MaxPressureController()
    action = controller.get_action(state, current_phase, elapsed)
"""
from __future__ import annotations

import sys
from pathlib import Path
import numpy as np
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from configs.constants import DIRECTIONS, MIN_GREEN_SECONDS


class MaxPressureController:
    """Max-Pressure 感应式信号控制器

    基于实时排队长度，动态选择压力最大的相位。
    无需训练，纯数据驱动，是交通控制领域经典基线算法。
    """

    def __init__(self, min_green: float = MIN_GREEN_SECONDS):
        self._min_green = min_green
        self._name = "MaxPressure"

    @property
    def name(self) -> str:
        return self._name

    def get_action(
        self,
        state: np.ndarray,
        current_phase: int,
        elapsed: float,
    ) -> int:
        """根据当前状态选择最优相位

        Args:
            state: 22维局部状态 (queue×4, wait×4, occupancy×4, overflow×4, phase×4, time×2)
            current_phase: 当前相位 (0-3)
            elapsed: 当前相位已持续时间(秒)

        Returns:
            选择的相位 (0-3)
        """
        # 最小绿灯时间约束
        if elapsed < self._min_green:
            return current_phase

        # 提取4方向排队长度 (state[0:4] 对应 N/S/E/W)
        queue = state[0:4]  # 归一化后的排队长度

        # 计算各相位压力
        # NS组: Phase 0 (NS_Straight) — 服务南北直行
        # EW组: Phase 2 (EW_Straight) — 服务东西直行
        ns_pressure = float(queue[0] + queue[1])  # N + S
        ew_pressure = float(queue[2] + queue[3])  # E + W

        # 选择压力最大的相位
        if ns_pressure >= ew_pressure:
            return 0  # NS_Straight
        else:
            return 2  # EW_Straight


class FourPhaseMaxPressureController:
    """标准四相位 Max-Pressure 感应控制（逐相位链路排队压力）

    与 MaxPressureController 的区别：后者只比较 NS/EW 直行两组压力、永远不服务
    左转相位，在含独立左转车道与左转相位的高保真路网上会饿死左转车流；
    本控制器对 rl4 程序的全部 4 个相位分别计算"其绿灯链路上的 halting 车辆数"
    作为该相位的压力（与 compute_action_mask 的需求统计同一套 lane/state 对齐），
    选择压力最大的相位，并遵守最小绿灯时间。

    用法:
        from baselines.adaptive import FourPhaseMaxPressureController
        ctrl = FourPhaseMaxPressureController()
        action = ctrl.get_action(env._traci, "J01", current_phase, elapsed)
    """

    def __init__(self, min_green: float = MIN_GREEN_SECONDS):
        self._min_green = min_green
        self._lanes_cache: dict[str, list[str]] = {}
        self._states_cache: dict[str, list[str]] = {}

    def _rl4_states(self, traci, tl_id: str) -> list[str] | None:
        if tl_id not in self._states_cache:
            logic = next(
                (c for c in traci.trafficlight.getAllProgramLogics(tl_id) if c.programID == "rl4"),
                None,
            )
            if logic is None or len(logic.phases) != 4:
                self._states_cache[tl_id] = []
                return None
            self._states_cache[tl_id] = [p.state for p in logic.phases]
        return self._states_cache[tl_id] or None

    def phase_demands(self, traci, tl_id: str) -> list[float] | None:
        """每个相位的压力 = 该相位绿灯链路（G/g）上的 halting 车辆数之和。"""
        states = self._rl4_states(traci, tl_id)
        if states is None:
            return None
        if tl_id not in self._lanes_cache:
            self._lanes_cache[tl_id] = traci.trafficlight.getControlledLanes(tl_id)
        lanes = self._lanes_cache[tl_id]
        halting = [float(traci.lane.getLastStepHaltingNumber(lane)) for lane in lanes]
        demands = []
        for state_str in states:
            green_links = [i for i, ch in enumerate(state_str) if ch in "Gg" and i < len(lanes)]
            demands.append(sum(halting[i] for i in green_links) if green_links else -1.0)
        return demands

    def get_action(self, traci, tl_id: str, current_phase: int, elapsed: float) -> int:
        """选择压力最大的合法相位；遵守最小绿灯；无需求时保持当前相位避免空转切换。"""
        if elapsed < self._min_green:
            return current_phase
        demands = self.phase_demands(traci, tl_id)
        if demands is None:
            return current_phase
        best = int(np.argmax(demands))
        # 全空或并列时保持当前相位，避免空路口两相位间空转
        if demands[best] <= 0 or (0 <= current_phase < 4 and demands[best] == demands[current_phase]):
            return current_phase
        return best


def run_max_pressure_policy(
    intersection_id: str = "J01",
    episodes: int = 5,
    max_steps: int = 720,
    delta_time: int = 5,
) -> dict:
    """运行 Max-Pressure 策略

    Args:
        intersection_id: 路口ID
        episodes: 测试回合数
        max_steps: 最大仿真步数
        delta_time: 每步仿真秒数

    Returns:
        统计信息字典
    """
    from env.single_intersection_env import SingleIntersectionEnv

    controller = MaxPressureController()
    rewards_all = []
    queues_all = []

    for ep in range(episodes):
        env = SingleIntersectionEnv(
            intersection_id=intersection_id,
            max_steps=max_steps,
            delta_time=delta_time,
        )
        obs, info = env.reset(seed=42 + ep)

        total_reward = 0.0
        done = False
        step_count = 0

        while not done:
            sim_time = float(env._traci.simulation.getTime())
            elapsed = sim_time - env._phase_changed_at

            action = controller.get_action(obs, env._current_phase, elapsed)
            obs, reward, terminated, truncated, info = env.step(action)

            total_reward += reward
            queues_all.append(float(obs[0:4].sum()))
            step_count += 1
            done = terminated or truncated

        rewards_all.append(total_reward)
        env.close()

    return {
        "mean_reward": float(np.mean(rewards_all)),
        "std_reward": float(np.std(rewards_all)),
        "min_reward": float(np.min(rewards_all)),
        "max_reward": float(np.max(rewards_all)),
        "mean_queue": float(np.mean(queues_all)),
        "std_queue": float(np.std(queues_all)),
    }


if __name__ == "__main__":
    results = run_max_pressure_policy("J01", episodes=5)
    print(f"\nMax-Pressure 策略结果 (J01, 5 episodes):")
    print(f"  平均奖励: {results['mean_reward']:.4f} ± {results['std_reward']:.4f}")
    print(f"  平均排队: {results['mean_queue']:.4f} ± {results['std_queue']:.4f}")
