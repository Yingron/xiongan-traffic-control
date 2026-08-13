"""
模型评估与基线对比脚本（v2）

功能：
1. 加载训练好的DQN模型
2. 运行DQN策略仿真（无探索）
3. 运行固定配时策略仿真（周期120秒，每相位30秒）
4. 对比两种策略的性能指标

运行方式：
python evaluate_policy.py --model=models_v2/dqn_traffic_final.zip
"""

import os
import sys
import argparse
import numpy as np
from pathlib import Path

# 添加项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 添加SUMO工具路径
if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)
else:
    sys.exit("请设置SUMO_HOME环境变量")

import traci


class FixedTimingPolicy:
    """
    固定配时策略
    
    周期120秒，四个相位各30秒：
    - 相位0（南北直行）：0-30秒
    - 相位1（南北左转）：30-60秒
    - 相位2（东西直行）：60-90秒
    - 相位3（东西左转）：90-120秒
    """
    
    def __init__(self, cycle_length=120, phase_duration=30):
        """
        初始化固定配时策略
        
        Args:
            cycle_length: 信号周期长度（秒）
            phase_duration: 每个相位持续时间（秒）
        """
        self.cycle_length = cycle_length
        self.phase_duration = phase_duration
        self.phase_order = [0, 1, 2, 3]  # 相位执行顺序
    
    def get_action(self, sim_time):
        """
        根据当前仿真时间获取动作
        
        Args:
            sim_time: 当前仿真时间（秒）
            
        Returns:
            action: 相位索引（0-3）
        """
        # 计算当前在周期中的位置
        time_in_cycle = sim_time % self.cycle_length
        
        # 根据时间确定当前相位
        for i, phase in enumerate(self.phase_order):
            if i * self.phase_duration <= time_in_cycle < (i + 1) * self.phase_duration:
                return phase
        
        return self.phase_order[0]


def run_dqn_policy(model_path, sumo_cfg_path, use_gui=False):
    """
    运行DQN策略仿真
    
    Args:
        model_path: DQN模型路径
        sumo_cfg_path: SUMO配置文件路径
        use_gui: 是否使用GUI
        
    Returns:
        metrics: 性能指标字典
    """
    from stable_baselines3 import DQN
    
    print("\n🚀 运行DQN策略仿真...")
    
    # 创建环境
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from env.env import TrafficSignalEnv
    
    env = TrafficSignalEnv(
        sumo_cfg_path=sumo_cfg_path,
        use_gui=use_gui,
        max_steps=3600,
        delta_time=5
    )
    
    # 加载模型
    model = DQN.load(model_path)
    print(f"✅ 加载模型: {model_path}")
    
    # 运行仿真
    obs, _ = env.reset()
    total_reward = 0.0
    total_queue = 0.0
    total_wait_time = 0.0
    action_counts = {0: 0, 1: 0, 2: 0, 3: 0}
    step_count = 0
    
    while True:
        action, _ = model.predict(obs, deterministic=True)
        action = int(action) if isinstance(action, np.ndarray) else action
        action_counts[action] += 1
        
        obs, reward, terminated, truncated, info = env.step(action)
        
        total_reward += reward
        total_queue += info['queue_length']
        step_count += 1
        
        if terminated or truncated:
            break
    
    env.close()
    
    # 计算指标
    metrics = {
        'policy': 'DQN',
        'total_reward': total_reward,
        'avg_reward': total_reward / step_count,
        'avg_queue_length': total_queue / step_count,
        'total_steps': step_count,
        'action_distribution': action_counts,
        'phase_switches': sum(action_counts.values()) - max(action_counts.values()),
    }
    
    return metrics


def run_fixed_policy(sumo_cfg_path, use_gui=False):
    """
    运行固定配时策略仿真
    
    Args:
        sumo_cfg_path: SUMO配置文件路径
        use_gui: 是否使用GUI
        
    Returns:
        metrics: 性能指标字典
    """
    print("\n⚙️ 运行固定配时策略仿真...")
    
    sumo_binary = "sumo-gui" if use_gui else "sumo"
    
    # 启动SUMO
    traci.start([
        sumo_binary,
        "-c", sumo_cfg_path,
        "--no-step-log",
        "--no-warnings",
        "--time-to-teleport", "-1"
    ])
    
    tl_id = "J1"
    
    # 获取受控车道
    controlled_lanes = traci.trafficlight.getControlledLanes(tl_id)
    # 从四个方向各选择一个车道
    lane_groups = {}
    for lane in controlled_lanes:
        direction = lane.split('_')[0]
        if direction not in lane_groups:
            lane_groups[direction] = []
        if lane not in lane_groups[direction]:
            lane_groups[direction].append(lane)
    
    lane_ids = []
    for direction in ['N', 'S', 'E', 'W']:
        if direction in lane_groups:
            for lane in lane_groups[direction]:
                if lane.endswith('_0'):
                    lane_ids.append(lane)
                    break
            else:
                lane_ids.append(lane_groups[direction][0])
    
    # 初始化固定配时策略
    fixed_policy = FixedTimingPolicy(cycle_length=120, phase_duration=30)
    
    # 运行仿真（3600秒）
    total_queue = 0.0
    total_wait_time = 0.0
    step_count = 0
    action_counts = {0: 0, 1: 0, 2: 0, 3: 0}
    last_action = None
    
    while traci.simulation.getTime() < 3600:
        sim_time = traci.simulation.getTime()
        action = fixed_policy.get_action(sim_time)
        
        # 设置相位
        traci.trafficlight.setPhase(tl_id, action)
        action_counts[action] += 1
        
        # 推进仿真5秒
        for _ in range(5):
            traci.simulationStep()
        
        # 计算排队长度
        queue_length = sum(traci.lane.getLastStepHaltingNumber(lane) for lane in lane_ids)
        total_queue += queue_length
        step_count += 1
    
    # 统计通过车辆数
    total_vehicles = traci.simulation.getArrivedNumber()
    
    traci.close()
    
    # 计算指标
    metrics = {
        'policy': '固定配时',
        'cycle_length': 120,
        'phase_duration': 30,
        'avg_queue_length': total_queue / step_count,
        'total_vehicles': total_vehicles,
        'total_steps': step_count,
        'action_distribution': action_counts,
        'phase_switches': sum(action_counts.values()) - max(action_counts.values()),
    }
    
    return metrics


def print_comparison_table(dqn_metrics, fixed_metrics):
    """
    打印对比表格
    
    Args:
        dqn_metrics: DQN策略指标
        fixed_metrics: 固定配时策略指标
    """
    print("\n" + "=" * 70)
    print("📊 策略对比结果")
    print("=" * 70)
    
    # 表格头
    print(f"{'指标':<25} {'DQN策略':<20} {'固定配时':<20}")
    print("-" * 70)
    
    # 排队长度
    dqn_queue = dqn_metrics.get('avg_queue_length', 0)
    fixed_queue = fixed_metrics.get('avg_queue_length', 0)
    improvement = (fixed_queue - dqn_queue) / fixed_queue * 100 if fixed_queue > 0 else 0
    print(f"{'平均排队长度':<25} {dqn_queue:<10.2f}辆       {fixed_queue:<10.2f}辆       {'↑' if improvement > 0 else '↓'}{abs(improvement):.1f}%")
    
    # 奖励
    if 'avg_reward' in dqn_metrics:
        print(f"{'平均奖励':<25} {dqn_metrics['avg_reward']:<10.4f}         -")
    
    # 总车辆数
    if 'total_vehicles' in fixed_metrics:
        print(f"{'总通过车辆数':<25} -                   {fixed_metrics['total_vehicles']:<10d}辆")
    
    # 相位切换次数
    dqn_switches = dqn_metrics.get('phase_switches', 0)
    fixed_switches = fixed_metrics.get('phase_switches', 0)
    print(f"{'相位切换次数':<25} {dqn_switches:<10d}次         {fixed_switches:<10d}次")
    
    # 动作分布
    print("\n📈 动作分布（各相位选择次数）:")
    phases = ['南北直行', '南北左转', '东西直行', '东西左转']
    print(f"{'相位':<10} {'DQN':<10} {'固定配时':<10}")
    print("-" * 30)
    for i, phase in enumerate(phases):
        dqn_count = dqn_metrics.get('action_distribution', {}).get(i, 0)
        fixed_count = fixed_metrics.get('action_distribution', {}).get(i, 0)
        print(f"{phase:<10} {dqn_count:<10d} {fixed_count:<10d}")
    
    print("\n" + "=" * 70)
    
    # 结论
    if dqn_queue < fixed_queue:
        print("🎉 DQN策略表现优于固定配时！")
    else:
        print("⚠️ 固定配时表现更好，需要进一步优化DQN模型")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='模型评估与基线对比')
    parser.add_argument('--model', type=str, default='./models_v2/dqn_traffic_final.zip',
                        help='DQN模型路径')
    parser.add_argument('--sumo-cfg', type=str, 
                        default=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sumo_files', 'xiongan_30.sumocfg'),
                        help='SUMO配置文件路径')
    parser.add_argument('--gui', action='store_true', help='是否使用GUI模式')
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("🧪 模型评估与基线对比")
    print("=" * 70)
    
    # 1. 运行DQN策略
    dqn_metrics = run_dqn_policy(args.model, args.sumo_cfg, use_gui=args.gui)
    
    # 2. 运行固定配时策略
    fixed_metrics = run_fixed_policy(args.sumo_cfg, use_gui=args.gui)
    
    # 3. 打印对比表格
    print_comparison_table(dqn_metrics, fixed_metrics)
    
    print("\n🎉 评估完成！")


if __name__ == "__main__":
    main()
