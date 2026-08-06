"""DQN训练脚本 - 单路口参数共享模式

使用 stable-baselines3 的 DQN 算法：
- 单路口22维状态 + 4离散动作
- 训练完成后模型可直接部署到20个路口

用法:
    python training/train_dqn.py --timesteps 5000
    python training/train_dqn.py --timesteps 20000 --intersection J05
    python training/train_dqn.py --timesteps 50000 --multi          # 多路口共享训练
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch.nn as nn

PROJECT_ROOT = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(PROJECT_ROOT))

from configs.constants import INTERSECTION_ORDER, SUMO_FILES_DIR
from env.single_intersection_env import SingleIntersectionEnv, MultiIntersectionSharedEnv


def make_env(intersection_id: str = "J01", max_steps: int = 720, delta_time: int = 5):
    """创建单路口环境"""
    return SingleIntersectionEnv(
        intersection_id=intersection_id,
        max_steps=max_steps,
        delta_time=delta_time,
    )


def train_dqn(
    timesteps: int = 5000,
    intersection_id: str = "J01",
    multi: bool = False,
    learning_rate: float = 1e-3,
    buffer_size: int = 10000,
    batch_size: int = 64,
    gamma: float = 0.99,
    exploration_fraction: float = 0.3,
    seed: int = 42,
    save_dir: str = "models/dqn",
    net_arch: list = None,
) -> dict:
    """运行DQN训练

    Args:
        timesteps: 总训练步数
        intersection_id: 路口ID（单路口模式）
        multi: 是否使用多路口参数共享模式
        learning_rate: 学习率
        buffer_size: 经验回放缓冲区大小
        batch_size: 批量大小
        gamma: 折扣因子
        exploration_fraction: 探索率衰减比例
        seed: 随机种子
        save_dir: 模型保存目录
        net_arch: 网络架构列表

    Returns:
        训练统计信息
    """
    from stable_baselines3 import DQN
    from stable_baselines3.common.callbacks import BaseCallback
    from stable_baselines3.common.monitor import Monitor

    if net_arch is None:
        net_arch = [256, 256, 256]

    save_path = PROJECT_ROOT / save_dir
    save_path.mkdir(parents=True, exist_ok=True)

    log_dir = PROJECT_ROOT / "logs" / f"dqn_{intersection_id}"
    log_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("DQN训练 - 雄安新区20路口信号控制")
    print("=" * 60)
    print(f"  模式: {'多路口参数共享' if multi else f'单路口({intersection_id})'}")
    print(f"  总步数: {timesteps}")
    print(f"  学习率: {learning_rate}")
    print(f"  网络架构: {net_arch}")
    print(f"  折扣因子: {gamma}")
    print(f"  探索衰减: {exploration_fraction}")
    print(f"  随机种子: {seed}")
    print()

    if multi:
        env = MultiIntersectionSharedEnv(max_steps=720, delta_time=5)
        env_name = "multi_shared"
    else:
        env = make_env(intersection_id, max_steps=720, delta_time=5)
        env_name = intersection_id

    env = Monitor(env, str(log_dir))

    model = DQN(
        policy="MlpPolicy",
        env=env,
        learning_rate=learning_rate,
        buffer_size=buffer_size,
        batch_size=batch_size,
        gamma=gamma,
        exploration_fraction=exploration_fraction,
        exploration_final_eps=0.05,
        train_freq=4,
        target_update_interval=500,
        device="cuda",
        verbose=1,
        seed=seed,
        tensorboard_log=str(log_dir),
        policy_kwargs=dict(
            net_arch=net_arch,
            activation_fn=nn.Tanh,
        ),
    )

    print("开始训练...")
    t_start = time.time()

    model.learn(total_timesteps=timesteps, tb_log_name="dqn", reset_num_timesteps=True)

    elapsed = time.time() - t_start
    print(f"\n训练完成! 耗时: {elapsed:.1f}s ({timesteps / elapsed:.0f} steps/s)")

    model_path = save_path / f"dqn_{env_name}_{timesteps}steps"
    model.save(str(model_path))
    print(f"模型已保存: {model_path}.zip")

    stats = evaluate_model(model, env, episodes=5)
    stats["model_path"] = str(model_path)
    stats["elapsed_seconds"] = elapsed
    stats["steps_per_second"] = timesteps / elapsed

    stats_path = save_path / f"dqn_{env_name}_{timesteps}steps_stats.json"
    with open(stats_path, "w") as f:
        json.dump(stats, f, indent=2, default=str)
    print(f"统计信息已保存: {stats_path}")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        plot_training_curve(log_dir, save_path, env_name, timesteps)
    except Exception as e:
        print(f"绘图跳过: {e}")

    return stats


def evaluate_model(model, env, episodes: int = 5) -> dict:
    """评估模型"""
    print(f"\n评估模型 ({episodes} episodes)...")

    rewards_list = []
    steps_list = []

    for ep in range(episodes):
        obs, info = env.reset()
        total_reward = 0.0
        done = False
        step_count = 0

        while not done:
            action, _ = model.predict(obs, deterministic=True)
            action = int(action)
            obs, reward, terminated, truncated, info = env.step(action)
            total_reward += reward
            step_count += 1
            done = terminated or truncated

        rewards_list.append(total_reward)
        steps_list.append(step_count)
        print(f"  Episode {ep + 1}: reward={total_reward:.4f}, steps={step_count}")

    return {
        "episodes": episodes,
        "mean_reward": float(np.mean(rewards_list)),
        "std_reward": float(np.std(rewards_list)),
        "min_reward": float(np.min(rewards_list)),
        "max_reward": float(np.max(rewards_list)),
        "mean_steps": float(np.mean(steps_list)),
    }


def plot_training_curve(log_dir: Path, save_path: Path, env_name: str, timesteps: int):
    """绘制训练曲线"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import pandas as pd

    csv_file = log_dir / "monitor.csv"
    if not csv_file.exists():
        print("  无训练数据可绘图")
        return

    try:
        df = pd.read_csv(csv_file, skiprows=1)
        if len(df) == 0 or "r" not in df.columns:
            print("  无奖励数据可绘图")
            return

        df = df[df["r"] < 0]

        fig, axes = plt.subplots(2, 1, figsize=(12, 10), sharex=True)

        axes[0].plot(df.index, df["r"], color="steelblue", linewidth=1.5, alpha=0.8, label="Episode Reward")

        if len(df) >= 10:
            window = max(1, len(df) // 10)
            rolling_mean = df["r"].rolling(window=window, min_periods=1).mean()
            axes[0].plot(df.index, rolling_mean, color="red", linewidth=2,
                         label=f"Rolling Mean (window={window})")
        axes[0].set_ylabel("Episode Reward")
        axes[0].set_title(f"DQN Training - {env_name} ({timesteps} steps)")
        axes[0].legend()
        axes[0].grid(True, alpha=0.3)

        if "l" in df.columns:
            axes[1].plot(df.index, df["l"], color="darkorange", linewidth=1, alpha=0.8)
            axes[1].set_ylabel("Episode Length (steps)")
            axes[1].set_xlabel("Episode Index")
            axes[1].grid(True, alpha=0.3)

        plt.tight_layout()
        chart_path = save_path / f"dqn_{env_name}_{timesteps}steps_curve.png"
        fig.savefig(chart_path, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"训练曲线已保存: {chart_path}")
    except Exception as e:
        print(f"  绘图失败: {e}")
        import traceback
        traceback.print_exc()


def main():
    parser = argparse.ArgumentParser(description="DQN训练 - 雄安新区信号控制")
    parser.add_argument("--timesteps", type=int, default=5000, help="训练步数")
    parser.add_argument("--intersection", type=str, default="J01", help="路口ID")
    parser.add_argument("--multi", action="store_true", help="多路口参数共享模式")
    parser.add_argument("--lr", type=float, default=1e-3, help="学习率")
    parser.add_argument("--net-arch", type=str, default="256,256", help="网络架构，如 '256,256,256'")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    parser.add_argument("--save-dir", type=str, default="models/dqn", help="模型与评估结果保存目录")
    parser.add_argument("--eval-only", action="store_true", help="仅评估已有模型")
    parser.add_argument("--model-path", type=str, default=None, help="已有模型路径")
    args = parser.parse_args()

    net_arch = [int(x) for x in args.net_arch.split(",")]
    print(f"网络架构: {net_arch}")

    if args.eval_only:
        from stable_baselines3 import DQN
        if not args.model_path:
            print("错误: 请指定 --model-path")
            return
        model = DQN.load(args.model_path)
        env = make_env(args.intersection)
        stats = evaluate_model(model, env, episodes=10)
        print(f"\n评估结果: {json.dumps(stats, indent=2)}")
        return

    stats = train_dqn(
        timesteps=args.timesteps,
        intersection_id=args.intersection,
        multi=args.multi,
        learning_rate=args.lr,
        seed=args.seed,
        save_dir=args.save_dir,
        net_arch=net_arch,
    )

    print(f"\n{'='*60}")
    print(f"训练完成统计:")
    print(f"  平均奖励: {stats['mean_reward']:.4f}")
    print(f"  奖励标准差: {stats['std_reward']:.4f}")
    print(f"  平均步数: {stats['mean_steps']:.1f}")
    print(f"  速度: {stats.get('steps_per_second', 0):.0f} steps/s")
    print(f"  模型: {stats['model_path']}")


if __name__ == "__main__":
    main()
