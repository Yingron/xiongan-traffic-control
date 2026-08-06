"""奖励计算器 - V3奖励函数实现"""
from __future__ import annotations

from typing import Optional
import numpy as np


class RewardCalculator:
    """V3奖励函数计算器
    
    奖励公式:
    reward = -(avg_queue + 0.5*max_queue + 0.3*avg_wait
              + 2.0*overflow_penalty + 0.2*switch_cost + 0.1*balance_penalty)
    """

    def __init__(
        self,
        overflow_weight: float = 2.0,
        switch_cost_weight: float = 0.2,
        balance_weight: float = 0.1,
        max_queue_weight: float = 0.5,
        avg_wait_weight: float = 0.3
    ):
        self.overflow_weight = overflow_weight
        self.switch_cost_weight = switch_cost_weight
        self.balance_weight = balance_weight
        self.max_queue_weight = max_queue_weight
        self.avg_wait_weight = avg_wait_weight

    def compute_reward(
        self,
        local_state: np.ndarray,
        current_action: int,
        previous_action: Optional[int] = None
    ) -> tuple[float, dict]:
        """计算单个路口的V3奖励
        
        Args:
            local_state: 22维局部状态
            current_action: 当前动作
            previous_action: 上一步动作
            
        Returns:
            (reward, breakdown_dict)
        """
        queue_lengths = local_state[0:4]
        avg_wait_times = local_state[4:8]
        overflow_risks = local_state[12:16]

        avg_queue = float(np.mean(queue_lengths))
        max_queue = float(np.max(queue_lengths))
        avg_wait = float(np.mean(avg_wait_times))
        overflow_penalty = float(np.max(overflow_risks))

        switch_cost = 1.0 if previous_action is not None and current_action != previous_action else 0.0

        queue_mean = np.mean(queue_lengths)
        balance_penalty = float(np.sqrt(np.mean((queue_lengths - queue_mean) ** 2)))

        reward = -(
            avg_queue
            + self.max_queue_weight * max_queue
            + self.avg_wait_weight * avg_wait
            + self.overflow_weight * overflow_penalty
            + self.switch_cost_weight * switch_cost
            + self.balance_weight * balance_penalty
        )

        breakdown = {
            "avg_queue": avg_queue,
            "max_queue": max_queue,
            "avg_wait": avg_wait,
            "overflow_penalty": overflow_penalty,
            "switch_cost": switch_cost,
            "balance_penalty": balance_penalty,
            "reward": float(reward)
        }

        return float(reward), breakdown

    def compute_rewards(
        self,
        global_state: np.ndarray,
        current_actions: dict[str, int],
        previous_actions: dict[str, Optional[int]]
    ) -> tuple[dict[str, float], dict[str, dict], float]:
        """计算所有20个路口的奖励
        
        Args:
            global_state: 440维全局状态
            current_actions: 当前动作字典
            previous_actions: 上一步动作字典
            
        Returns:
            (rewards_dict, breakdowns_dict, global_reward)
        """
        from configs.constants import INTERSECTION_ORDER

        rewards = {}
        breakdowns = {}
        state_per_intersection = 22

        for idx, tl_id in enumerate(INTERSECTION_ORDER):
            offset = idx * state_per_intersection
            local_state = global_state[offset:offset + state_per_intersection]

            current_action = current_actions.get(tl_id, 0)
            previous_action = previous_actions.get(tl_id)

            reward, breakdown = self.compute_reward(local_state, current_action, previous_action)
            rewards[tl_id] = reward
            breakdowns[tl_id] = breakdown

        global_reward = float(np.mean(list(rewards.values()))) if rewards else 0.0
        return rewards, breakdowns, global_reward
