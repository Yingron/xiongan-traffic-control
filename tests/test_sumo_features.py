#!/usr/bin/env python3
"""SUMO功能测试脚本"""
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

def test_state_extraction():
    """测试状态提取"""
    print('=' * 60)
    print('测试状态提取功能')
    print('=' * 60)

    sumo_binary = os.path.join(os.environ['SUMO_HOME'], 'bin', 'sumo.exe')
    cfg_path = str(PROJECT_ROOT / 'sumo_files' / 'xiongan.sumocfg')

    try:
        traci.start([
            sumo_binary,
            '-c', cfg_path,
            '--no-step-log',
            '--no-warnings',
            '--time-to-teleport', '-1'
        ])

        for _ in range(5):
            traci.simulationStep()

        print('提取全局状态...')
        global_state = get_global_state(num_intersections=20)

        print(f'状态维度: {global_state.shape}')
        print(f'状态类型: {global_state.dtype}')
        print(f'状态最小值: {global_state.min():.4f}')
        print(f'状态最大值: {global_state.max():.4f}')
        print(f'状态均值: {global_state.mean():.4f}')

        assert len(global_state) == STATE_DIMENSION, f'维度不匹配: {len(global_state)} != {STATE_DIMENSION}'
        print(f'状态维度验证通过 ({len(global_state)}维)')

        # 解析状态
        parsed = parse_state(global_state)
        print(f'解析路口数量: {len(parsed)}')

        # 显示J01状态
        print()
        print('J01路口状态:')
        j01 = parsed['J01']
        phase_name = ACTION_NAMES[j01['phase']] if 0 <= j01['phase'] < len(ACTION_NAMES) else 'unknown'
        print(f'  相位: {j01["phase"]} ({phase_name})')
        
        ql = j01['queue_length']
        print(f'  排队长度: N={ql["N"]:.2f}, S={ql["S"]:.2f}, E={ql["E"]:.2f}, W={ql["W"]:.2f}')
        
        occ = j01['occupancy']
        print(f'  占有率: N={occ["N"]:.2f}, S={occ["S"]:.2f}, E={occ["E"]:.2f}, W={occ["W"]:.2f}')
        
        print(f'  时间特征: sin={j01["time_sin"]:.4f}, cos={j01["time_cos"]:.4f}')

        # 多步状态采集
        print()
        print('测试多步状态提取 (10步)...')
        states = []
        for step in range(10):
            traci.simulationStep()
            state = get_global_state()
            states.append(state)

        print(f'采集到 {len(states)} 个状态')

        changes = 0
        for i in range(1, len(states)):
            if not np.array_equal(states[i], states[i-1]):
                changes += 1
        print(f'状态变化次数: {changes}/9')

        traci.close()
        print()
        print('✅ 状态提取功能测试通过！')
        return global_state

    except Exception as e:
        import traceback
        print(f'❌ 测试失败: {e}')
        traceback.print_exc()
        try:
            traci.close()
        except:
            pass
        return None

def test_reward_computation(state=None):
    """测试奖励计算"""
    print()
    print('=' * 60)
    print('测试奖励计算功能')
    print('=' * 60)

    if state is None:
        state = np.random.randn(STATE_DIMENSION).astype(np.float32)

    # 构造动作
    current_actions = {}
    previous_actions = {}
    for i in range(1, 21):
        tl_id = f'J{i:02d}'
        current_actions[tl_id] = i % 4
        previous_actions[tl_id] = None

    # 计算批量奖励
    print('计算批量奖励...')
    rewards, breakdowns, global_reward = compute_rewards(state, current_actions, previous_actions)

    print(f'全局奖励: {global_reward:.4f}')
    print(f'路口数量: {len(rewards)}')
    
    reward_values = list(rewards.values())
    print(f'单路口奖励范围: [{min(reward_values):.4f}, {max(reward_values):.4f}]')

    # 显示J01的奖励分解
    print()
    print('J01奖励分解:')
    j01_breakdown = breakdowns['J01']
    for key, value in j01_breakdown.items():
        print(f'  {key}: {value:.4f}')

    # 测试单路口奖励
    print()
    print('测试单路口奖励计算...')
    j01_state = state[0:22]
    reward, breakdown = compute_reward(j01_state, 0, None)
    print(f'单路口奖励: {reward:.4f}')
    print(f'奖励分解: {breakdown}')

    print()
    print('✅ 奖励计算功能测试通过！')

def test_traffic_light_control():
    """测试交通信号灯控制"""
    print()
    print('=' * 60)
    print('测试交通信号灯控制')
    print('=' * 60)

    sumo_binary = os.path.join(os.environ['SUMO_HOME'], 'bin', 'sumo.exe')
    cfg_path = str(PROJECT_ROOT / 'sumo_files' / 'xiongan.sumocfg')

    try:
        traci.start([
            sumo_binary,
            '-c', cfg_path,
            '--no-step-log',
            '--no-warnings',
            '--time-to-teleport', '-1'
        ])

        # 获取所有信号灯
        tl_ids = traci.trafficlight.getIDList()
        print(f'信号灯数量: {len(tl_ids)}')

        # 测试J01的控制
        tl_id = 'J01'
        print(f'\\n测试 {tl_id} 控制...')
        
        # 获取当前状态
        current_phase = traci.trafficlight.getPhase(tl_id)
        current_program = traci.trafficlight.getProgram(tl_id)
        print(f'  当前相位: {current_phase}')
        print(f'  当前程序: {current_program}')

        # 获取相位数量
        logic = traci.trafficlight.getCompleteRedYellowGreenDefinition(tl_id)
        num_phases = len(logic[0].phases) if logic else 0
        print(f'  可用相位数: {num_phases}')

        # 切换相位
        print(f'  切换到相位 1...')
        traci.trafficlight.setPhase(tl_id, 1)
        traci.simulationStep()
        
        new_phase = traci.trafficlight.getPhase(tl_id)
        print(f'  切换后相位: {new_phase}')
        assert new_phase == 1, f'相位切换失败: 期望1, 实际{new_phase}'
        print(f'  ✅ 相位切换成功')

        # 运行30步仿真
        print(f'\\n运行30步仿真...')
        for i in range(30):
            traci.simulationStep()

        # 查看交通状态
        vehicle_count = traci.vehicle.getIDCount()
        sim_time = traci.simulation.getTime()
        print(f'  仿真时间: {sim_time:.1f}秒')
        print(f'  车辆数量: {vehicle_count}')

        traci.close()
        print()
        print('✅ 交通信号灯控制测试通过！')

    except Exception as e:
        import traceback
        print(f'❌ 测试失败: {e}')
        traceback.print_exc()
        try:
            traci.close()
        except:
            pass

def main():
    """运行所有测试"""
    print('\\n' + '=' * 60)
    print('雄安新区SUMO功能测试')
    print('=' * 60)
    print(f'项目根目录: {PROJECT_ROOT}')
    print(f'SUMO_HOME: {os.environ.get("SUMO_HOME", "未设置")}')
    print()

    # 测试1: 状态提取
    state = test_state_extraction()

    # 测试2: 奖励计算
    if state is not None:
        test_reward_computation(state)

    # 测试3: 信号灯控制
    test_traffic_light_control()

    print()
    print('=' * 60)
    print('所有SUMO功能测试完成！')
    print('=' * 60)

if __name__ == '__main__':
    main()