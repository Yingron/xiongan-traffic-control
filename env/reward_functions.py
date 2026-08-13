"""奖励函数模块 - V5奖励函数（吞吐驱动版）

核心改进 (vs V4):
1. 大幅降低stagnation惩罚 (0.15 -> 0.02)，防止压制探索
2. 引入正向奖励：队列减少量 = 通过车辆数的代理指标
3. 引入总等待时间减少的正向奖励
4. 让智能体明白"放行更多车辆"比"不扣分"更重要
5. 所有惩罚仍为负值，奖励可正可负
"""
from __future__ import annotations

from typing import Optional
import numpy as np

from configs.constants import INTERSECTION_ORDER, FEATURES_PER_INTERSECTION


def compute_reward(
    local_state: np.ndarray,
    current_action: int,
    previous_action: Optional[int] = None,
    previous_state: Optional[np.ndarray] = None,
    overflow_weight: float = 2.0,
    switch_cost_weight: float = 0.01,
    balance_weight: float = 0.1,
    max_queue_weight: float = 0.6,
    avg_wait_weight: float = 0.4,
    queue_pressure_weight: float = 0.8,
    throughput_weight: float = 0.5,
    wait_reduction_weight: float = 0.3,
    stagnation_penalty: float = 0.08,
    crossed_throughput_weight: float = 2.0,
    crossed_vehicles: int = 0,
    same_action_count: int = 0,
) -> tuple[float, dict]:
    """计算单个路口的V5奖励（吞吐驱动版 + 真实通过量）

    奖励公式:
    reward = -(queue_pressure + max_queue_weight*max_queue
              + avg_wait_weight*avg_wait + overflow_weight*overflow
              + switch_cost_weight*switch_cost + balance_weight*balance
              + stagnation_penalty*stagnation)
              + throughput_weight*queue_reduction
              + crossed_throughput_weight*crossed_vehicles
              + wait_reduction_weight*wait_reduction

    核心改进 (V5.1):
    - 新增真实通过量奖励 crossed_throughput_weight*crossed_vehicles：
      由环境层统计"本步越过停车线的车辆数"，直接驱动单位时间放行车辆数，
      不受同一步"进一辆出一辆"抵消影响（比 queue_reduction 代理更准）。
    - 降低切换成本 (0.05 -> 0.01)：切换代价已由损失的有效绿灯时间承担，
      过高的切换惩罚会把模型压制为"死守相位"。
    - 提高停滞惩罚 (0.02 -> 0.08)：死守相位不服务车辆时惩罚更明显。

    Args:
        local_state: 22维局部状态
        current_action: 当前动作 (0-3)
        previous_action: 上一步动作
        previous_state: 上一步的22维状态（用于计算队列/等待变化）
        overflow_weight: 溢出惩罚权重
        switch_cost_weight: 切换成本权重
        balance_weight: 均衡惩罚权重
        max_queue_weight: 最大排队权重
        avg_wait_weight: 平均等待权重
        queue_pressure_weight: 排队压力权重
        throughput_weight: 队列减少量（通过车辆代理）正向奖励权重
        wait_reduction_weight: 等待时间减少正向奖励权重
        stagnation_penalty: 停滞惩罚权重
        crossed_throughput_weight: 真实通过车辆数正向奖励权重（每辆）
        crossed_vehicles: 本步越过停车线的车辆数（由环境层统计传入；0表示不启用）
        same_action_count: 连续选择同一动作的步数

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

    queue_pressure = queue_pressure_weight * avg_queue

    stagnation = 0.0
    if same_action_count > 2:
        stagnation = float(min((same_action_count - 2) / 3.0, 2.0))

    # 计算队列减少量（代理通过车辆数）
    queue_reduction = 0.0
    wait_reduction = 0.0
    if previous_state is not None:
        prev_queues = previous_state[0:4]
        prev_waits = previous_state[4:8]
        # 队列减少：越大越好（车辆通过了路口）
        queue_reduction = float(np.sum(np.maximum(prev_queues - queue_lengths, 0.0)))
        # 等待时间减少：越大越好
        wait_reduction = float(np.maximum(np.mean(prev_waits) - avg_wait, 0.0))

    # 惩罚项（全部为负）
    penalty = (
        queue_pressure
        + max_queue_weight * max_queue
        + avg_wait_weight * avg_wait
        + overflow_weight * overflow_penalty
        + switch_cost_weight * switch_cost
        + balance_weight * balance_penalty
        + stagnation_penalty * stagnation
    )

    # 正向奖励项：队列减少代理 + 真实通过车辆数（环境层统计）+ 等待时间减少
    positive_reward = (
        throughput_weight * queue_reduction
        + crossed_throughput_weight * float(crossed_vehicles)
        + wait_reduction_weight * wait_reduction
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
        "crossed_vehicles": int(crossed_vehicles),
        "wait_reduction": wait_reduction,
        "penalty_total": penalty,
        "positive_reward": positive_reward,
        "reward": float(reward),
    }

    return float(reward), breakdown


def compute_rewards(
    global_state: np.ndarray,
    current_actions: dict[str, int],
    previous_actions: dict[str, Optional[int]],
    previous_states: dict[str, np.ndarray] | None = None,
    same_action_counts: dict[str, int] | None = None,
    **kwargs,
) -> tuple[dict[str, float], dict[str, dict], float]:
    """计算所有30个路口的奖励

    Args:
        global_state: 660维全局状态
        current_actions: 当前动作字典 {tl_id: action}
        previous_actions: 上一步动作字典 {tl_id: action_or_None}
        previous_states: 上一步的局部状态字典 {tl_id: local_state}
        same_action_counts: 连续同一动作计数字典 {tl_id: count}
        **kwargs: 传递给compute_reward的额外参数

    Returns:
        (rewards_dict, breakdowns_dict, global_reward)
    """
    rewards = {}
    breakdowns = {}
    state_per_intersection = FEATURES_PER_INTERSECTION

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

        reward, breakdown = compute_reward(
            local_state, current_action, previous_action,
            previous_state=prev_state,
            same_action_count=same_count, **kwargs
        )
        rewards[tl_id] = reward
        breakdowns[tl_id] = breakdown

    global_reward = float(np.mean(list(rewards.values()))) if rewards else 0.0
    return rewards, breakdowns, global_reward


# 别名兼容 - 一些文件使用 compute_reward_v3
compute_reward_v3 = compute_reward
