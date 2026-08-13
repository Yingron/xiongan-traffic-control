"""
训练结果可视化与分析脚本（v2）

功能：
1. 从TensorBoard日志中提取奖励和排队长度数据
2. 绘制奖励曲线（滑动平均）
3. 绘制排队长度曲线
4. 绘制动作分布图
5. 保存图表为 training_analysis.png

运行方式：
python analyze_training.py --logdir=logs_v2
"""

import os
import sys
import argparse
import matplotlib.pyplot as plt
import numpy as np
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator


def load_tensorboard_data(log_dir):
    """
    从TensorBoard日志中加载数据
    
    Args:
        log_dir: TensorBoard日志目录
        
    Returns:
        data: 包含各指标数据的字典
    """
    print(f"📂 正在加载TensorBoard日志: {log_dir}")
    
    # 查找最新的日志目录
    event_dirs = sorted([d for d in os.listdir(log_dir) if os.path.isdir(os.path.join(log_dir, d))], reverse=True)
    
    if not event_dirs:
        print(f"❌ 未找到日志目录: {log_dir}")
        return None
    
    event_dir = os.path.join(log_dir, event_dirs[0])
    print(f"📁 使用日志目录: {event_dir}")
    
    # 加载事件数据
    event_acc = EventAccumulator(event_dir, size_guidance={
        'scalars': 0,  # 加载所有标量数据
        'histograms': 0,
        'images': 0,
        'audio': 0,
        'tensors': 0,
    })
    
    try:
        event_acc.Reload()
    except Exception as e:
        print(f"❌ 加载日志失败: {e}")
        return None
    
    # 获取所有标量标签
    tags = event_acc.Tags()['scalars']
    print(f"📊 可用指标: {tags}")
    
    # 提取关键指标
    data = {}
    
    # 提取 reward 相关数据
    for tag in tags:
        if 'reward' in tag.lower() or 'rew' in tag.lower():
            try:
                events = event_acc.Scalars(tag)
                steps = [e.step for e in events]
                values = [e.value for e in events]
                data[tag] = {'steps': steps, 'values': values}
                print(f"✅ 加载指标: {tag} (共{len(steps)}个数据点)")
            except Exception as e:
                print(f"⚠️ 加载指标失败: {tag} - {e}")
    
    return data


def calculate_moving_average(values, window_size=100):
    """
    计算滑动平均值
    
    Args:
        values: 原始数据
        window_size: 滑动窗口大小
        
    Returns:
        smoothed_values: 平滑后的数据
    """
    if len(values) < window_size:
        return values
    
    cumsum = np.cumsum(np.insert(values, 0, 0))
    smoothed_values = (cumsum[window_size:] - cumsum[:-window_size]) / window_size
    
    return smoothed_values


def plot_reward_curve(data, save_path):
    """
    绘制奖励曲线
    
    Args:
        data: 数据字典
        save_path: 保存路径
    """
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle('DQN交通信号控制训练分析', fontsize=16, fontweight='bold')
    
    # 1. 奖励曲线（原始）
    ax1 = axes[0, 0]
    if 'rollout/ep_rew_mean' in data:
        steps = data['rollout/ep_rew_mean']['steps']
        rewards = data['rollout/ep_rew_mean']['values']
        ax1.plot(steps, rewards, color='#1f77b4', alpha=0.6, label='原始奖励')
        
        # 滑动平均
        if len(rewards) >= 10:
            smoothed_rewards = calculate_moving_average(rewards, window_size=10)
            smoothed_steps = steps[-len(smoothed_rewards):]
            ax1.plot(smoothed_steps, smoothed_rewards, color='#ff7f0e', linewidth=2, label='滑动平均(10)')
        
        ax1.set_title('平均奖励曲线', fontsize=14)
        ax1.set_xlabel('训练步数', fontsize=12)
        ax1.set_ylabel('平均奖励', fontsize=12)
        ax1.legend(fontsize=10)
        ax1.grid(True, alpha=0.3)
    else:
        ax1.text(0.5, 0.5, '无奖励数据', ha='center', va='center', transform=ax1.transAxes)
    
    # 2. 探索率曲线
    ax2 = axes[0, 1]
    if 'rollout/exploration_rate' in data:
        steps = data['rollout/exploration_rate']['steps']
        rates = data['rollout/exploration_rate']['values']
        ax2.plot(steps, rates, color='#2ca02c', linewidth=2)
        ax2.set_title('探索率变化', fontsize=14)
        ax2.set_xlabel('训练步数', fontsize=12)
        ax2.set_ylabel('探索率', fontsize=12)
        ax2.grid(True, alpha=0.3)
    else:
        ax2.text(0.5, 0.5, '无探索率数据', ha='center', va='center', transform=ax2.transAxes)
    
    # 3. 训练损失曲线
    ax3 = axes[1, 0]
    if 'train/loss' in data:
        steps = data['train/loss']['steps']
        losses = data['train/loss']['values']
        ax3.plot(steps, losses, color='#d62728', alpha=0.6, label='原始损失')
        
        # 滑动平均
        if len(losses) >= 50:
            smoothed_losses = calculate_moving_average(losses, window_size=50)
            smoothed_steps = steps[-len(smoothed_losses):]
            ax3.plot(smoothed_steps, smoothed_losses, color='#9467bd', linewidth=2, label='滑动平均(50)')
        
        ax3.set_title('训练损失曲线', fontsize=14)
        ax3.set_xlabel('训练步数', fontsize=12)
        ax3.set_ylabel('损失', fontsize=12)
        ax3.legend(fontsize=10)
        ax3.grid(True, alpha=0.3)
    else:
        ax3.text(0.5, 0.5, '无损失数据', ha='center', va='center', transform=ax3.transAxes)
    
    # 4. episode长度曲线
    ax4 = axes[1, 1]
    if 'rollout/ep_len_mean' in data:
        steps = data['rollout/ep_len_mean']['steps']
        lengths = data['rollout/ep_len_mean']['values']
        ax4.plot(steps, lengths, color='#8c564b', linewidth=2)
        ax4.set_title('平均Episode长度', fontsize=14)
        ax4.set_xlabel('训练步数', fontsize=12)
        ax4.set_ylabel('步数', fontsize=12)
        ax4.grid(True, alpha=0.3)
    else:
        ax4.text(0.5, 0.5, '无Episode长度数据', ha='center', va='center', transform=ax4.transAxes)
    
    # 调整布局
    plt.tight_layout()
    plt.subplots_adjust(top=0.92)
    
    # 保存图表
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    print(f"✅ 图表已保存到: {save_path}")
    
    # 显示图表
    plt.show()


def plot_action_distribution(env, model_path, save_path):
    """
    绘制动作分布图（各相位被选择的频率）
    
    Args:
        env: 环境实例
        model_path: 模型路径
        save_path: 保存路径
    """
    try:
        from stable_baselines3 import DQN
        
        # 加载模型
        model = DQN.load(model_path)
        print(f"✅ 加载模型: {model_path}")
        
        # 运行一个完整的episode，记录动作分布
        obs, _ = env.reset()
        action_counts = {0: 0, 1: 0, 2: 0, 3: 0}
        total_steps = 0
        
        while True:
            action, _ = model.predict(obs, deterministic=True)
            action_counts[action] += 1
            obs, _, terminated, truncated, _ = env.step(action)
            total_steps += 1
            
            if terminated or truncated:
                break
        
        env.close()
        
        # 绘制动作分布图
        fig, ax = plt.subplots(figsize=(8, 6))
        
        phases = ['南北直行', '南北左转', '东西直行', '东西左转']
        counts = [action_counts[0], action_counts[1], action_counts[2], action_counts[3]]
        percentages = [c / total_steps * 100 for c in counts]
        
        colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728']
        bars = ax.bar(phases, counts, color=colors)
        
        # 添加数值标签
        for bar, count, percent in zip(bars, counts, percentages):
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width() / 2, height,
                    f'{count} ({percent:.1f}%)',
                    ha='center', va='bottom', fontsize=10)
        
        ax.set_title('动作分布（各相位选择频率）', fontsize=14, fontweight='bold')
        ax.set_xlabel('相位', fontsize=12)
        ax.set_ylabel('选择次数', fontsize=12)
        ax.grid(axis='y', alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"✅ 动作分布图已保存到: {save_path}")
        
        plt.show()
        
    except Exception as e:
        print(f"❌ 绘制动作分布失败: {e}")
        import traceback
        traceback.print_exc()


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='训练结果可视化与分析')
    parser.add_argument('--logdir', type=str, default='./logs_v2',
                        help='TensorBoard日志目录')
    parser.add_argument('--model', type=str, default='./models_v2/dqn_traffic_final.zip',
                        help='训练好的模型路径')
    parser.add_argument('--output', type=str, default='./training_analysis.png',
                        help='输出图表路径')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("📊 训练结果可视化与分析")
    print("=" * 60)
    
    # 1. 加载并绘制奖励曲线
    data = load_tensorboard_data(args.logdir)
    if data:
        plot_reward_curve(data, args.output)
    else:
        print("⚠️ 无法加载TensorBoard数据，跳过奖励曲线绘制")
    
    # 2. 绘制动作分布图
    if os.path.exists(args.model):
        # 创建环境
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        from env.env import TrafficSignalEnv
        
        env = TrafficSignalEnv(
            sumo_cfg_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sumo_files', 'xiongan_30.sumocfg'),
            use_gui=False,
            max_steps=3600,
            delta_time=5
        )
        
        action_dist_path = args.output.replace('.png', '_action_dist.png')
        plot_action_distribution(env, args.model, action_dist_path)
    else:
        print(f"⚠️ 模型文件不存在: {args.model}，跳过动作分布绘制")
    
    print("\n🎉 分析完成！")


if __name__ == "__main__":
    main()
