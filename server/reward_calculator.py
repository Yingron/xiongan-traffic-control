"""奖励计算器 - V5奖励函数实现（吞吐驱动版）"""
from __future__ import annotations

from typing import Optional
import numpy as np


class RewardCalculator:
    """V5奖励函数计算器（吞吐驱动版）

    奖励公式:
    reward = -(queue_pressure + max_queue_weight*max_queue
              + avg_wait_weight*avg_wait + overflow_weight*overflow
              + switch_cost_weight*switch_cost + balance_weight*balance
              + stagnation_penalty*stagnation)
              + throughput_weight*queue_reduction
              + wait_reduction_weight*wait_reduction

    核心改进:
    - 降低惩罚权重，使正向信号(throughput)能主导
    - 队列减少量 = max(0, prev_queue - curr_queue) 作为通过车辆数代理
    - 等待时间减少量作为优化目标
    """

    def __init__(
        self,
        overflow_weight: float = 2.0,
        switch_cost_weight: float = 0.05,
        balance_weight: float = 0.1,
        max_queue_weight: float = 0.6,
        avg_wait_weight: float = 0.4,
        queue_pressure_weight: float = 0.8,
        throughput_weight: float = 0.5,
        wait_reduction_weight: float = 0.3,
        stagnation_penalty: float = 0.02,
    ):
        self.overflow_weight = overflow_weight
        self.switch_cost_weight = switch_cost_weight
        self.balance_weight = balance_weight
        self.max_queue_weight = max_queue_weight
        self.avg_wait_weight = avg_wait_weight
        self.queue_pressure_weight = queue_pressure_weight
        self.throughput_weight = throughput_weight
        self.wait_reduction_weight = wait_reduction_weight
        self.stagnation_penalty = stagnation_penalty

    def compute_reward(
        self,
        local_state: np.ndarray,
        current_action: int,
        previous_action: Optional[int] = None,
        previous_state: Optional[np.ndarray] = None,
        same_action_count: int = 0,
    ) -> tuple[float, dict]:
        """计算单个路口的V5奖励

        Args:
            local_state: 22维局部状态
            current_action: 当前动作
            previous_action: 上一步动作
            previous_state: 上一步22维状态（用于计算队列/等待变化）
            same_action_count: 连续同一动作步数

        Returns:
            (reward, breakdown_dict)
        """
        queue_lengths = local_state[0:4]
        avg_wait_times = local_state[4:8]
        occupancy = local_state[8:12]
        overflow_risks = local_state[12:16]

        avg_queue = float(np.mean(queue_lengths))
        max_queue = float(np.max(queue_lengths))
        avg_wait = float(np.mean(avg_wait_times))
        avg_occupancy = float(np.mean(occupancy))
        overflow_penalty = float(np.max(overflow_risks))

        switch_cost = 1.0 if previous_action is not None and current_action != previous_action else 0.0

        queue_mean = np.mean(queue_lengths)
        balance_penalty = float(np.sqrt(np.mean((queue_lengths - queue_mean) ** 2)))

        queue_pressure = self.queue_pressure_weight * avg_queue

        stagnation = 0.0
        if same_action_count > 2:
            stagnation = float(min((same_action_count - 2) / 3.0, 2.0))

        # 计算队列减少量（代理通过车辆数）
        queue_reduction = 0.0
        wait_reduction = 0.0
        if previous_state is not None:
            prev_queues = previous_state[0:4]
            prev_waits = previous_state[4:8]
            queue_reduction = float(np.sum(np.maximum(prev_queues - queue_lengths, 0.0)))
            wait_reduction = float(np.maximum(np.mean(prev_waits) - avg_wait, 0.0))

        # 惩罚项
        penalty = (
            queue_pressure
            + self.max_queue_weight * max_queue
            + self.avg_wait_weight * avg_wait
            + self.overflow_weight * overflow_penalty
            + self.switch_cost_weight * switch_cost
            + self.balance_weight * balance_penalty
            + self.stagnation_penalty * stagnation
        )

        # 正向奖励
        positive_reward = (
            self.throughput_weight * queue_reduction
            + self.wait_reduction_weight * wait_reduction
        )

        reward = -penalty + positive_reward

        breakdown = {
            "avg_queue": avg_queue,
            "max_queue": max_queue,
            "avg_wait": avg_wait,
            "avg_occupancy": avg_occupancy,
            "overflow_penalty": overflow_penalty,
            "switch_cost": switch_cost,
            "balance_penalty": balance_penalty,
            "queue_pressure": queue_pressure,
            "stagnation": stagnation,
            "same_action_count": same_action_count,
            "queue_reduction": queue_reduction,
            "wait_reduction": wait_reduction,
            "penalty_total": penalty,
            "positive_reward": positive_reward,
            "reward": float(reward),
        }

        return float(reward), breakdown

    def compute_rewards(
        self,
        global_state: np.ndarray,
        current_actions: dict[str, int],
        previous_actions: dict[str, Optional[int]],
        previous_states: dict[str, np.ndarray] | None = None,
        same_action_counts: dict[str, int] | None = None,
    ) -> tuple[dict[str, float], dict[str, dict], float]:
        """计算所有20个路口的奖励

        Args:
            global_state: 440维全局状态
            current_actions: 当前动作字典
            previous_actions: 上一步动作字典
            previous_states: 上一步局部状态字典
            same_action_counts: 连续同一动作计数字典

        Returns:
            (rewards_dict, breakdowns_dict, global_reward)
        """
        from configs.constants import INTERSECTION_ORDER

        rewards = {}
        breakdowns = {}
        state_per_intersection = 22

        if same_action_counts is None:
            same_action_counts = {}
        if previous_states is None:
            previous_states = {}

        for idx, tl_id in enumerate(INTERSECTION_ORDER):
            offset = idx * state_per_intersection
            local_state = global_state[offset:offset + state_per_intersection]

            current_action = current_actions.get(tl_id, 0)
            previous_action = previous_actions.get(tl_id)
            same_count = same_action_counts.get(tl_id, 0)
            prev_state = previous_states.get(tl_id)

            reward, breakdown = self.compute_reward(
                local_state, current_action, previous_action,
                previous_state=prev_state,
                same_action_count=same_count,
            )
            rewards[tl_id] = reward
            breakdowns[tl_id] = breakdown

        global_reward = float(np.mean(list(rewards.values()))) if rewards else 0.0
        return rewards, breakdowns, global_reward
