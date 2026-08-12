#!/usr/bin/env python3
"""SUMO动态仿真测试 - 运行完整交通流模拟"""
import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)

import traci
import numpy as np
from env.global_state import get_global_state, parse_state
from env.reward_functions import compute_rewards, compute_reward
from configs.constants import STATE_DIMENSION, INTERSECTION_ORDER, ACTION_NAMES

def run_dynamic_test():
    """运行动态仿真测试"""
    print('=' * 60)
    print('雄安新区动态仿真测试')
    print('=' * 60)

    sumo_binary = os.path.join(os.environ['SUMO_HOME'], 'bin', 'sumo.exe')
    cfg_path = str(PROJECT_ROOT / 'sumo_files' / 'xiongan_30.sumocfg')

    try:
        traci.start([
            sumo_binary,
            '-c', cfg_path,
            '--no-step-log',
            '--no-warnings',
            '--time-to-teleport', '-1'
        ])

        print('SUMO已启动，开始动态仿真...')
        print()

        # 运行前60步仿真让交通流稳定
        print('预热阶段 (60步)...')
        for _ in range(60):
            traci.simulationStep()

        # 数据采集
        rewards_history = []
        queue_history = []
        vehicle_history = []
        
        previous_actions = {f'J{i:02d}': None for i in range(1, 21)}
        
        print('数据采集阶段 (120步)...')
        print('-' * 60)
        print(f'{"步数":<8} {"时间(s)":<10} {"车辆数":<10} {"全局奖励":<12} {"平均排队":<12}')
        print('-' * 60)

        for step in range(120):
            # 获取当前状态
            state = get_global_state()
            
            # 构造随机动作（模拟RL智能体）
            current_actions = {}
            for i in range(1, 21):
                tl_id = f'J{i:02d}'
                current_actions[tl_id] = np.random.randint(0, 4)
            
            # 计算奖励
            rewards, breakdowns, global_reward = compute_rewards(
                state, current_actions, previous_actions
            )
            
            # 统计排队长度
            total_queue = 0
            for i in range(20):
                offset = i * 22
                queue = state[offset:offset+4]
                total_queue += np.sum(queue)
            
            rewards_history.append(global_reward)
            queue_history.append(total_queue)
            
            vehicle_count = traci.vehicle.getIDCount()
            vehicle_history.append(vehicle_count)
            
            sim_time = traci.simulation.getTime()
            
            # 每20步打印一次
            if step % 20 == 0 or step == 119:
                print(f'{step:<8} {sim_time:<10.1f} {vehicle_count:<10} {global_reward:<12.4f} {total_queue:<12.2f}')
            
            # 应用动作到仿真（切换相位）
            for tl_id, action in current_actions.items():
                try:
                    traci.trafficlight.setPhase(tl_id, action)
                except:
                    pass
            
            previous_actions = current_actions.copy()
            traci.simulationStep()

        print('-' * 60)
        
        # 统计分析
        print()
        print('统计分析:')
        print(f'  全局奖励均值: {np.mean(rewards_history):.4f}')
        print(f'  全局奖励范围: [{min(rewards_history):.4f}, {max(rewards_history):.4f}]')
        print(f'  平均排队长度: {np.mean(queue_history):.2f}')
        print(f'  排队长度范围: [{min(queue_history):.2f}, {max(queue_history):.2f}]')
        print(f'  平均车辆数: {np.mean(vehicle_history):.1f}')
        
        # 获取当前状态的详细分析
        print()
        print('当前交通状态分析:')
        current_state = get_global_state()
        parsed = parse_state(current_state)
        
        # 找出最拥堵的路口
        congestion = []
        for tl_id in INTERSECTION_ORDER:
            jdata = parsed[tl_id]
            total_queue = sum(jdata['queue_length'].values())
            congestion.append((tl_id, total_queue))
        
        congestion.sort(key=lambda x: x[1], reverse=True)
        
        print('  最拥堵路口 TOP 5:')
        for tl_id, queue in congestion[:5]:
            jdata = parsed[tl_id]
            print(f'    {tl_id}: 总排队={queue:.2f}, 相位={jdata["phase"]}')
        
        print('  最通畅路口 TOP 5:')
        for tl_id, queue in congestion[-5:]:
            jdata = parsed[tl_id]
            print(f'    {tl_id}: 总排队={queue:.2f}, 相位={jdata["phase"]}')

        # 测试随机动作 vs 固定动作对比
        print()
        print('策略对比测试:')
        test_strategies(state, traci)

        traci.close()
        print()
        print('✅ 动态仿真测试完成！')

    except Exception as e:
        import traceback
        print(f'❌ 测试失败: {e}')
        traceback.print_exc()
        try:
            traci.close()
        except:
            pass

def test_strategies(state, traci):
    """测试不同策略的效果"""
    print('  测试固定相位策略...')
    
    # 构造 previous_actions 字典
    prev_actions = {f'J{i:02d}': None for i in range(1, 21)}
    
    # 固定相位0
    fixed_actions = {f'J{i:02d}': 0 for i in range(1, 21)}
    rewards_fixed, _, _ = compute_rewards(state, fixed_actions, prev_actions)
    fixed_reward = sum(rewards_fixed.values()) / len(rewards_fixed)
    
    # 固定相位2
    fixed2_actions = {f'J{i:02d}': 2 for i in range(1, 21)}
    rewards_fixed2, _, _ = compute_rewards(state, fixed2_actions, prev_actions)
    fixed2_reward = sum(rewards_fixed2.values()) / len(rewards_fixed2)
    
    # 随机策略 (测试5次)
    random_rewards = []
    for _ in range(5):
        rand_actions = {f'J{i:02d}': np.random.randint(0, 4) for i in range(1, 21)}
        _, _, r = compute_rewards(state, rand_actions, prev_actions)
        random_rewards.append(r)
    
    avg_random = np.mean(random_rewards)
    
    print(f'    固定相位0 平均奖励: {fixed_reward:.4f}')
    print(f'    固定相位2 平均奖励: {fixed2_reward:.4f}')
    print(f'    随机策略 平均奖励: {avg_random:.4f}')
    print(f'    最优策略: {"固定相位0" if fixed_reward > fixed2_reward else "固定相位2"}')

if __name__ == '__main__':
    run_dynamic_test()