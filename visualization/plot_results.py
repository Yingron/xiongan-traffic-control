"""
训练结果可视化脚本

功能：
1. 读取TensorBoard日志文件
2. 绘制奖励值（Reward）随训练步数变化的曲线图
3. 绘制平均排队长度（Queue Length）随训练步数变化的曲线图
4. 将生成的图表保存为training_curves.png
"""

import os
import sys
import numpy as np
import matplotlib.pyplot as plt
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

def load_tensorboard_logs(log_dir):
    """
    加载TensorBoard日志
    
    Args:
        log_dir: 日志目录
        
    Returns:
        data: 字典，包含各类指标数据
    """
    event_acc = EventAccumulator(log_dir)
    event_acc.Reload()
    
    data = {}
    
    # 获取所有标签
    tags = event_acc.Tags()['scalars']
    
    for tag in tags:
        events = event_acc.Scalars(tag)
        steps = [event.step for event in events]
        values = [event.value for event in events]
        data[tag] = {'steps': np.array(steps), 'values': np.array(values)}
    
    return data

def plot_training_curves(data, output_path='training_curves.png'):
    """
    绘制训练曲线
    
    Args:
        data: 日志数据字典
        output_path: 输出图片路径
    """
    plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False
    
    fig, axes = plt.subplots(2, 1, figsize=(12, 10))
    
    # 第一张图：奖励曲线
    ax1 = axes[0]
    if 'rollout/ep_rew_mean' in data:
        ax1.plot(
            data['rollout/ep_rew_mean']['steps'],
            data['rollout/ep_rew_mean']['values'],
            label='平均奖励 (ep_rew_mean)',
            color='#1f77b4',
            linewidth=2
        )
    elif 'reward' in data:
        ax1.plot(
            data['reward']['steps'],
            data['reward']['values'],
            label='奖励 (reward)',
            color='#1f77b4',
            linewidth=2
        )
    
    ax1.set_title('训练奖励曲线', fontsize=14, fontweight='bold')
    ax1.set_xlabel('训练步数', fontsize=12)
    ax1.set_ylabel('奖励值', fontsize=12)
    ax1.grid(True, alpha=0.3)
    ax1.legend(fontsize=10)
    ax1.tick_params(axis='both', labelsize=10)
    
    # 第二张图：排队长度曲线
    ax2 = axes[1]
    if 'eval/queue_length' in data:
        ax2.plot(
            data['eval/queue_length']['steps'],
            data['eval/queue_length']['values'],
            label='评估排队长度',
            color='#ff7f0e',
            linewidth=2
        )
    elif 'queue_length' in data:
        ax2.plot(
            data['queue_length']['steps'],
            data['queue_length']['values'],
            label='排队长度',
            color='#ff7f0e',
            linewidth=2
        )
    
    ax2.set_title('排队长度曲线', fontsize=14, fontweight='bold')
    ax2.set_xlabel('训练步数', fontsize=12)
    ax2.set_ylabel('排队长度（车辆数）', fontsize=12)
    ax2.grid(True, alpha=0.3)
    ax2.legend(fontsize=10)
    ax2.tick_params(axis='both', labelsize=10)
    
    # 添加整体标题
    fig.suptitle('DQN交通信号控制训练结果', fontsize=16, fontweight='bold', y=0.98)
    
    # 调整布局
    plt.tight_layout()
    
    # 保存图片
    plt.savefig(output_path, dpi=200, bbox_inches='tight')
    print(f"✅ 图表已保存到: {output_path}")
    
    # 显示图片
    plt.show()

def main():
    """主函数"""
    log_dir = "./logs/"
    
    # 检查日志目录是否存在
    if not os.path.exists(log_dir):
        print(f"❌ 日志目录不存在: {log_dir}")
        print("请先运行训练脚本生成日志")
        sys.exit(1)
    
    # 查找最新的日志子目录
    subdirs = [d for d in os.listdir(log_dir) if os.path.isdir(os.path.join(log_dir, d))]
    if not subdirs:
        print(f"❌ 未找到日志子目录")
        sys.exit(1)
    
    # 按修改时间排序，取最新的
    subdirs.sort(key=lambda x: os.path.getmtime(os.path.join(log_dir, x)), reverse=True)
    latest_log_dir = os.path.join(log_dir, subdirs[0])
    
    print(f"📂 加载日志目录: {latest_log_dir}")
    
    # 加载日志数据
    try:
        data = load_tensorboard_logs(latest_log_dir)
        print(f"✅ 成功加载 {len(data)} 个指标")
        
        # 打印可用指标
        print("\n📋 可用指标:")
        for tag in data.keys():
            print(f"   - {tag}")
    except Exception as e:
        print(f"❌ 加载日志失败: {e}")
        sys.exit(1)
    
    # 绘制图表
    print("\n🎨 绘制训练曲线...")
    plot_training_curves(data)
    
    return data

if __name__ == "__main__":
    main()
