"""
交通信号控制奖励函数模块（V3版）

设计哲学：
- 面向雄安"窄路密网"场景（路口间距<200m）
- 核心目标：防止排队溢出导致的上游死锁
- 兼顾：通行效率、公平性、稳定性

奖励函数V3公式：
reward = - (w1*avg_queue + w2*max_queue + w3*avg_wait + w4*overflow_penalty + w5*switch_cost + w6*balance_penalty)

权重设计原则：
- 平均排队（1.0）：主要拥堵指标，优先级最高
- 最大排队（0.5）：尖峰惩罚，防止单方向过长导致溢出
- 平均等待（0.3）：公平性，避免车辆饿死
- 溢出惩罚（2.0）：当溢出风险>0.8时线性增罚，防死锁关键
- 切换成本（0.2）：减少不必要切换，避免黄灯损耗
- 均衡惩罚（0.1）：鼓励各方向排队均衡，窄路密网专用

状态维度映射（基于22维全局状态）：
- [0:4] 排队长度（归一化，N/S/E/W）
- [4:8] 平均等待时间（归一化，N/S/E/W）
- [8:12] 车道占有率（N/S/E/W）
- [12:16] 溢出风险（N/S/E/W）—— 与排队长度数值相同，但用于不同目的
- [16:20] 当前相位One-Hot编码
- [20:22] 时间特征（sin/cos）
"""

import numpy as np

# DEBUG模式：设置为True时打印奖励分解
DEBUG = False


def compute_reward_v3(state, action, prev_action, weights=None):
    """
    计算V3版本奖励（窄路密网专用）
    
    Args:
        state: 22维状态向量（来自get_global_state的前22维）
        action: 当前动作（0-3）
        prev_action: 上一步动作（0-3或None）
        weights: 权重字典（可选，用于调参）
        
    Returns:
        tuple: (reward, breakdown)
            - reward: 标量奖励值
            - breakdown: 字典，包含各项分解值
    """
    # 默认权重
    if weights is None:
        weights = {
            'w_avg_queue': 1.0,
            'w_max_queue': 0.5,
            'w_avg_wait': 0.3,
            'w_overflow': 2.0,
            'w_switch': 0.2,
            'w_balance': 0.1
        }
    
    # ==================== 1. 平均排队长度 ====================
    # 物理意义：所有进口道的平均排队，反映整体拥堵程度
    # 归一化范围：[0, 1]，对应0~15辆车
    queues = state[0:4]
    avg_queue = np.mean(queues)
    
    # ==================== 2. 最大排队长度 ====================
    # 物理意义：排队最长方向的长度，反映尖峰拥堵
    # 惩罚单方向过长，避免"一路绿灯，其他路全红"
    max_queue = np.max(queues)
    
    # ==================== 3. 平均等待时间 ====================
    # 物理意义：所有进口道的平均等待时间，反映公平性
    # 归一化范围：[0, 1]，对应0~120秒
    # 防止某方向车辆长时间等待（"饿死"现象）
    wait_times = state[4:8]
    avg_wait = np.mean(wait_times)
    
    # ==================== 4. 溢出惩罚 ====================
    # 物理意义：超过阈值的溢出风险总和，防死锁关键
    # 溢出风险范围：[0, 1]，对应排队长度/15
    # 阈值0.8（即12辆车），超过后线性增罚
    # 窄路密网下，排队超过12辆就有溢出到上游路口的风险
    overflow_threshold = 0.8
    overflow_risks = state[12:16]
    
    # 计算每个方向的溢出惩罚
    overflow_penalty = 0.0
    overflow_contributions = []
    for i, risk in enumerate(overflow_risks):
        excess = max(0, risk - overflow_threshold)
        overflow_contributions.append(excess)
        overflow_penalty += excess
    
    # ==================== 5. 切换成本 ====================
    # 物理意义：相位切换的惩罚，减少不必要切换
    # 每次切换有黄灯时间损耗（约3秒），且增加信号不稳定
    # 仅当动作改变时惩罚
    switch_cost = 1.0 if (prev_action is not None and action != prev_action) else 0.0
    
    # ==================== 6. 均衡惩罚（窄路密网专用） ====================
    # 物理意义：各方向排队的标准差，鼓励排队均衡
    # 窄路密网下（路口间距<200m），不均衡排队易导致局部死锁
    # 标准差越大，说明各方向排队差异越大
    queue_std = np.std(queues)
    balance_penalty = queue_std
    
    # ==================== 总奖励计算 ====================
    # 所有项均为惩罚项，取负值作为奖励
    total_penalty = (
        weights['w_avg_queue'] * avg_queue +
        weights['w_max_queue'] * max_queue +
        weights['w_avg_wait'] * avg_wait +
        weights['w_overflow'] * overflow_penalty +
        weights['w_switch'] * switch_cost +
        weights['w_balance'] * balance_penalty
    )
    
    reward = -total_penalty
    
    # 构建分解字典
    breakdown = {
        'reward': reward,
        'avg_queue': avg_queue,
        'max_queue': max_queue,
        'avg_wait': avg_wait,
        'overflow_penalty': overflow_penalty,
        'overflow_contributions': overflow_contributions,
        'switch_cost': switch_cost,
        'balance_penalty': balance_penalty,
        'total_penalty': total_penalty,
        'weights': weights.copy()
    }
    
    # 调试输出
    if DEBUG:
        print(f"[DEBUG] 奖励分解:")
        print(f"  avg_queue={avg_queue:.4f} × {weights['w_avg_queue']} = {weights['w_avg_queue']*avg_queue:.4f}")
        print(f"  max_queue={max_queue:.4f} × {weights['w_max_queue']} = {weights['w_max_queue']*max_queue:.4f}")
        print(f"  avg_wait={avg_wait:.4f} × {weights['w_avg_wait']} = {weights['w_avg_wait']*avg_wait:.4f}")
        print(f"  overflow_penalty={overflow_penalty:.4f} × {weights['w_overflow']} = {weights['w_overflow']*overflow_penalty:.4f}")
        print(f"  switch_cost={switch_cost:.4f} × {weights['w_switch']} = {weights['w_switch']*switch_cost:.4f}")
        print(f"  balance_penalty={balance_penalty:.4f} × {weights['w_balance']} = {weights['w_balance']*balance_penalty:.4f}")
        print(f"  total_penalty={total_penalty:.4f}, reward={reward:.4f}")
    
    return reward, breakdown


def compute_reward(state, action, prev_action, weights=None):
    """
    计算奖励（统一使用V3版本）
    
    公式：reward = - (w1*avg_queue + w2*max_queue + w3*avg_wait + w4*overflow_penalty + w5*switch_cost + w6*balance_penalty)
    
    Args:
        state: 22维状态向量
        action: 当前动作（0-3）
        prev_action: 上一步动作（0-3或None）
        weights: 权重字典（可选，用于调参）
        
    Returns:
        tuple: (reward, breakdown)
    """
    return compute_reward_v3(state, action, prev_action, weights)


# ==============================================
# 权重调优建议
# ==============================================

def get_tuned_weights(scenario='default'):
    """
    获取不同场景下的调优权重
    
    Args:
        scenario: 场景类型
            - 'default': 默认场景，平衡各目标
            - 'spillback': 高溢出风险场景，加重溢出惩罚
            - 'efficiency': 追求通行效率，降低切换成本
            - 'fairness': 追求公平性，加重等待时间权重
    
    Returns:
        dict: 权重字典
    """
    weights = {
        'w_avg_queue': 1.0,
        'w_max_queue': 0.5,
        'w_avg_wait': 0.3,
        'w_overflow': 2.0,
        'w_switch': 0.2,
        'w_balance': 0.1
    }
    
    if scenario == 'spillback':
        # 高溢出风险场景：加大溢出和最大排队惩罚
        weights['w_overflow'] = 3.0
        weights['w_max_queue'] = 0.8
        weights['w_balance'] = 0.2
    
    elif scenario == 'efficiency':
        # 追求通行效率：降低切换成本，允许更多切换
        weights['w_switch'] = 0.1
        weights['w_avg_queue'] = 1.2
        weights['w_max_queue'] = 0.3
    
    elif scenario == 'fairness':
        # 追求公平性：加重等待时间和均衡惩罚
        weights['w_avg_wait'] = 0.5
        weights['w_balance'] = 0.2
        weights['w_max_queue'] = 0.6
    
    elif scenario == 'conservative':
        # 保守策略：最小化切换，适合初期训练
        weights['w_switch'] = 0.5
        weights['w_overflow'] = 1.5
    
    return weights


# ==============================================
# 单元测试
# ==============================================
if __name__ == "__main__":
    print("=" * 70)
    print("🚀 奖励函数单元测试（V3版）")
    print("=" * 70)
    
    # 测试用例1：无拥堵状态
    print("\n📋 测试用例1：无拥堵状态")
    state_clear = np.array([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0.966, -0.259])
    reward, breakdown = compute_reward(state_clear, 0, None)
    print(f"  奖励: {reward:.4f}")
    
    # 测试用例2：中等拥堵状态
    print("\n📋 测试用例2：中等拥堵状态（排队0.3）")
    state_medium = np.array([0.3, 0.3, 0.3, 0.3, 0.2, 0.2, 0.2, 0.2, 0.5, 0.5, 0.5, 0.5, 0.3, 0.3, 0.3, 0.3, 1, 0, 0, 0, 0.966, -0.259])
    reward, breakdown = compute_reward(state_medium, 0, 0)  # 同动作，无切换惩罚
    print(f"  奖励: {reward:.4f}")
    print(f"  分解: avg_queue={breakdown['avg_queue']:.4f}, max_queue={breakdown['max_queue']:.4f}, "
          f"avg_wait={breakdown['avg_wait']:.4f}, switch={breakdown['switch_cost']:.4f}")
    
    # 测试用例3：严重拥堵+溢出状态
    print("\n📋 测试用例3：严重拥堵+溢出状态（排队0.9）")
    state_congested = np.array([0.9, 0.8, 0.9, 0.8, 0.6, 0.5, 0.6, 0.5, 0.9, 0.8, 0.9, 0.8, 0.9, 0.8, 0.9, 0.8, 1, 0, 0, 0, 0.966, -0.259])
    reward, breakdown = compute_reward(state_congested, 1, 0)  # 动作切换
    print(f"  奖励: {reward:.4f}")
    print(f"  分解: overflow={breakdown['overflow_penalty']:.4f}, switch={breakdown['switch_cost']:.4f}, "
          f"balance={breakdown['balance_penalty']:.4f}")
    
    # 测试用例4：不均衡排队
    print("\n📋 测试用例4：不均衡排队（东向拥堵，其他方向空闲）")
    state_unbalanced = np.array([0.1, 0.1, 0.8, 0.1, 0.1, 0.1, 0.5, 0.1, 0.2, 0.2, 0.7, 0.2, 0.1, 0.1, 0.8, 0.1, 1, 0, 0, 0, 0.966, -0.259])
    reward, breakdown = compute_reward(state_unbalanced, 2, 1)
    print(f"  奖励: {reward:.4f}")
    print(f"  分解: balance_penalty={breakdown['balance_penalty']:.4f}, max_queue={breakdown['max_queue']:.4f}")
    
    # 测试权重调优
    print("\n📋 测试权重调优")
    weights_spillback = get_tuned_weights('spillback')
    weights_efficiency = get_tuned_weights('efficiency')
    weights_fairness = get_tuned_weights('fairness')
    
    reward_default, _ = compute_reward(state_congested, 1, 0)
    reward_spillback, _ = compute_reward(state_congested, 1, 0, weights=weights_spillback)
    reward_efficiency, _ = compute_reward(state_congested, 1, 0, weights=weights_efficiency)
    
    print(f"  默认权重奖励: {reward_default:.4f}")
    print(f"  溢出风险权重奖励: {reward_spillback:.4f}")
    print(f"  效率权重奖励: {reward_efficiency:.4f}")
    
    print("\n" + "=" * 70)
    print("✅ 奖励函数单元测试完成！")
    print("=" * 70)
