"""
DQN交通信号控制训练脚本

功能：
1. 创建交通信号控制环境（基于SUMO和gymnasium）
2. 使用Stable-Baselines3的DQN算法进行训练
3. 训练100,000步，每1000步保存一次模型
4. 启用TensorBoard记录训练日志
5. 训练结束后进行评估测试
"""

import os
import sys
import numpy as np
from datetime import datetime

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stable_baselines3 import DQN
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.callbacks import (
    CheckpointCallback,
    EvalCallback
)
from stable_baselines3.common.logger import configure

from env.env import TrafficSignalEnv


def main():
    """主训练函数"""
    # ====================
    # 1. 配置参数
    # ====================
    # SUMO配置文件路径（使用赛题资料中的路口1）
    sumo_cfg_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "sumo_files",
        "xiongan.sumocfg"
    )
    
    # 训练参数（v2优化版）
    total_timesteps = 500000   # 总训练步数，从100000增加到500000
    save_freq = 5000           # 保存频率（步），从1000增加到5000
    eval_freq = 25000          # 评估频率（步）
    log_dir = "./logs_v2/"     # 日志目录（v2版本）
    model_dir = "./models_v2/" # 模型保存目录（v2版本）
    device = "auto"            # 设备（auto表示自动选择GPU/CPU）
    
    # 创建目录
    os.makedirs(log_dir, exist_ok=True)
    os.makedirs(model_dir, exist_ok=True)
    
    # ====================
    # 2. 创建环境
    # ====================
    print("=" * 60)
    print("...创建交通信号控制环境...")
    print(f"SUMO配置文件: {sumo_cfg_path}")
    print("=" * 60)
    
    try:
        env = TrafficSignalEnv(
            sumo_cfg_path=sumo_cfg_path,
            use_gui=False,      # 训练时关闭GUI以提高速度
            max_steps=3600,     # 最大仿真步数（1小时）
            delta_time=5        # 每步仿真5秒
        )
        print("---------环境创建成功！")
    except Exception as e:
        print(f"---------环境创建失败: {e}")
        sys.exit(1)
    
    # ====================
    # 3. 配置回调函数
    # ====================
    print("\n...配置回调函数...")
    
    # 检查点回调：每save_freq步保存一次模型
    checkpoint_callback = CheckpointCallback(
        save_freq=save_freq,
        save_path=model_dir,
        name_prefix="dqn_traffic",
        save_replay_buffer=True,
        save_vecnormalize=True,
    )
    
    # TensorBoard日志已通过model的tensorboard_log参数自动启用
    # 注意：EvalCallback会创建新环境导致TraCI连接冲突，因此只使用CheckpointCallback
    callbacks = [checkpoint_callback]
    
    # ====================
    # 4. 创建DQN模型
    # ====================
    print("\n...创建DQN模型...")
    
    model = DQN(
        "MlpPolicy",           # 多层感知器策略网络
        env,
        learning_rate=1e-4,     # 学习率
        buffer_size=200000,     # 经验回放缓冲区大小，从100000增加到200000
        learning_starts=2000,   # 开始学习前的预热步数，从1000增加到2000
        batch_size=64,          # 批次大小
        gamma=0.99,             # 折扣因子
        train_freq=4,           # 训练频率（每4步训练一次）
        gradient_steps=1,       # 梯度更新步数
        target_update_interval=2000,  # 目标网络更新间隔，从1000增加到2000
        exploration_fraction=0.3,     # 探索率衰减比例，从0.1增加到0.3（前30%步数探索）
        exploration_initial_eps=1.0,  # 初始探索率
        exploration_final_eps=0.01,   # 最终探索率
        verbose=1,              # 详细输出
        tensorboard_log=log_dir, # TensorBoard日志目录
        device=device,          # 设备
    )
    
    print("---------DQN模型创建成功！")
    print(f"模型参数: {model.policy}")
    
    # ====================
    # 5. 开始训练
    # ====================
    print("\n" + "=" * 60)
    print(f"---------开始训练（总步数: {total_timesteps}）")
    print(f"---------开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    try:
        model.learn(
            total_timesteps=total_timesteps,
            callback=callbacks,
            progress_bar=True,
        )
        print("\n---------训练完成！")
    except KeyboardInterrupt:
        print("\n---------训练被用户中断")
    except Exception as e:
        print(f"\n---------训练过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
    
    # ====================
    # 6. 保存最终模型
    # ====================
    print("\n...保存最终模型...")
    final_model_path = os.path.join(model_dir, "dqn_traffic_final.zip")
    model.save(final_model_path)
    print(f"---------模型已保存到: {final_model_path}")
    
    # ====================
    # 7. 评估模型
    # ====================
    print("\n" + "=" * 60)
    print("---------评估训练后的模型...")
    print("=" * 60)
    
    # 加载最佳模型
    best_model_path = os.path.join(model_dir, "best_model.zip")
    if os.path.exists(best_model_path):
        print(f"---------加载最佳模型: {best_model_path}")
        model = DQN.load(best_model_path, env=env)
    else:
        print(f"---------未找到最佳模型，使用最终模型")
        model = DQN.load(final_model_path, env=env)
    
    # 进行一次完整的episode测试
    obs, info = env.reset()
    total_reward = 0.0
    total_queue = 0.0
    step_count = 0
    
    while True:
        action, _states = model.predict(obs, deterministic=True)
        obs, reward, terminated, truncated, info = env.step(action)
        
        total_reward += reward
        total_queue += info['queue_length']
        step_count += 1
        
        if terminated or truncated:
            break
    
    # 计算平均指标
    avg_reward = total_reward / step_count
    avg_queue = total_queue / step_count
    
    print(f"\n---------评估结果:")
    print(f"   - 总步数: {step_count}")
    print(f"   - 总奖励: {total_reward:.2f}")
    print(f"   - 平均奖励: {avg_reward:.4f}")
    print(f"   - 平均排队长度: {avg_queue:.2f}")
    
    # ====================
    # 8. 关闭环境
    # ====================
    env.close()
    print("\n---------评估完成！")
    
    return {
        'total_reward': total_reward,
        'avg_reward': avg_reward,
        'avg_queue': avg_queue,
        'step_count': step_count
    }


if __name__ == "__main__":
    # 设置种子以保证可重复性
    np.random.seed(42)
    
    # 执行主函数
    results = main()
    
    # 打印最终结果
    print("\n" + "=" * 60)
    print("---------训练脚本执行完成！")
    print("=" * 60)
    print(f"---------评估结果:")
    print(f"  - 总奖励: {results['total_reward']:.2f}")
    print(f"  - 平均奖励: {results['avg_reward']:.4f}")
    print(f"  - 平均排队长度: {results['avg_queue']:.2f}")
    print(f"  - 步数: {results['step_count']}")
