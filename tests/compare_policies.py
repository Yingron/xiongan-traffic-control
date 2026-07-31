"""对比测试：随机策略 vs DQN训练后策略"""
import sys
import time
import json
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from env.single_intersection_env import SingleIntersectionEnv


def run_random_policy(episodes=5):
    """随机策略"""
    rewards_all = []
    for ep in range(episodes):
        env = SingleIntersectionEnv(intersection_id="J01", max_steps=720, delta_time=5)
        obs, info = env.reset(seed=42 + ep)
        total_reward = 0.0
        done = False
        while not done:
            action = env.action_space.sample()
            obs, reward, terminated, truncated, info = env.step(action)
            total_reward += reward
            done = terminated or truncated
        rewards_all.append(total_reward)
        env.close()
    return {
        "mean_reward": float(np.mean(rewards_all)),
        "std_reward": float(np.std(rewards_all)),
        "min_reward": float(np.min(rewards_all)),
        "max_reward": float(np.max(rewards_all)),
    }


def run_fixed_time_policy(episodes=5):
    """固定配时策略（周期切换相位）"""
    rewards_all = []
    for ep in range(episodes):
        env = SingleIntersectionEnv(intersection_id="J01", max_steps=720, delta_time=5)
        obs, info = env.reset(seed=42 + ep)
        total_reward = 0.0
        done = False
        step = 0
        while not done:
            action = (step // 5) % 4
            obs, reward, terminated, truncated, info = env.step(action)
            total_reward += reward
            step += 1
            done = terminated or truncated
        rewards_all.append(total_reward)
        env.close()
    return {
        "mean_reward": float(np.mean(rewards_all)),
        "std_reward": float(np.std(rewards_all)),
        "min_reward": float(np.min(rewards_all)),
        "max_reward": float(np.max(rewards_all)),
    }


def main():
    from stable_baselines3 import DQN

    model_path = PROJECT_ROOT / "models" / "dqn" / "dqn_J01_5000steps.zip"
    if not model_path.exists():
        print(f"错误: 模型文件不存在: {model_path}")
        return

    print("=" * 60)
    print("策略对比: 随机 vs 固定配时 vs DQN(训练5000步)")
    print("=" * 60)

    print("\n[1/3] 运行随机策略 (5 episodes)...")
    t0 = time.time()
    random_stats = run_random_policy(episodes=5)
    t_random = time.time() - t0
    print(f"  平均奖励: {random_stats['mean_reward']:.4f} ± {random_stats['std_reward']:.4f}")
    print(f"  耗时: {t_random:.1f}s")

    print("\n[2/3] 运行固定配时策略 (5 episodes)...")
    t0 = time.time()
    fixed_stats = run_fixed_time_policy(episodes=5)
    t_fixed = time.time() - t0
    print(f"  平均奖励: {fixed_stats['mean_reward']:.4f} ± {fixed_stats['std_reward']:.4f}")
    print(f"  耗时: {t_fixed:.1f}s")

    print("\n[3/3] 运行DQN策略 (5 episodes, deterministic)...")
    model = DQN.load(str(model_path))
    dqn_rewards = []
    t0 = time.time()
    for ep in range(5):
        env = SingleIntersectionEnv(intersection_id="J01", max_steps=720, delta_time=5)
        obs, info = env.reset(seed=42 + ep)
        total_reward = 0.0
        done = False
        while not done:
            action, _ = model.predict(obs, deterministic=True)
            obs, reward, terminated, truncated, info = env.step(int(action))
            total_reward += reward
            done = terminated or truncated
        dqn_rewards.append(total_reward)
        env.close()
    t_dqn = time.time() - t0
    dqn_stats = {
        "mean_reward": float(np.mean(dqn_rewards)),
        "std_reward": float(np.std(dqn_rewards)),
        "min_reward": float(np.min(dqn_rewards)),
        "max_reward": float(np.max(dqn_rewards)),
    }
    print(f"  平均奖励: {dqn_stats['mean_reward']:.4f} ± {dqn_stats['std_reward']:.4f}")
    print(f"  耗时: {t_dqn:.1f}s")

    print("\n" + "=" * 60)
    print("对比结果汇总:")
    print("=" * 60)
    print(f"  {'策略':<15} {'平均奖励':>10} {'标准差':>10} {'相对随机提升':>15}")
    print(f"  {'-'*50}")
    print(f"  {'随机':<15} {random_stats['mean_reward']:>10.4f} {random_stats['std_reward']:>10.4f} {'基准':>15}")
    print(f"  {'固定配时':<15} {fixed_stats['mean_reward']:>10.4f} {fixed_stats['std_reward']:>10.4f} {(fixed_stats['mean_reward'] - random_stats['mean_reward']):>+14.4f}")
    print(f"  {'DQN(5k)':<15} {dqn_stats['mean_reward']:>10.4f} {dqn_stats['std_reward']:>10.4f} {(dqn_stats['mean_reward'] - random_stats['mean_reward']):>+14.4f}")

    improvement_vs_random = (dqn_stats['mean_reward'] - random_stats['mean_reward']) / abs(random_stats['mean_reward']) * 100
    improvement_vs_fixed = (dqn_stats['mean_reward'] - fixed_stats['mean_reward']) / abs(fixed_stats['mean_reward']) * 100
    print(f"\n  DQN vs 随机提升: {improvement_vs_random:+.1f}%")
    print(f"  DQN vs 固定配时提升: {improvement_vs_fixed:+.1f}%")

    results = {
        "random": random_stats,
        "fixed_time": fixed_stats,
        "dqn_5000": dqn_stats,
        "improvement_vs_random_percent": improvement_vs_random,
        "improvement_vs_fixed_percent": improvement_vs_fixed,
    }

    results_path = PROJECT_ROOT / "models" / "dqn" / "comparison_results.json"
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n详细结果已保存: {results_path}")

    print("\n✅ 对比测试完成")


if __name__ == "__main__":
    main()
