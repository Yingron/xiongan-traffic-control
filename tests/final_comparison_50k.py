"""最终策略对比: 随机 vs 固定配时 vs DQN(50k)"""
import sys
import json
import time
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from env.single_intersection_env import SingleIntersectionEnv


def run_random_policy(episodes=5):
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
    }


def run_fixed_time_policy(episodes=5):
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
    }


def main():
    from stable_baselines3 import DQN

    model_path_50k = PROJECT_ROOT / "models" / "dqn" / "dqn_J01_50000steps.zip"
    if not model_path_50k.exists():
        print(f"错误: 50k模型文件不存在: {model_path_50k}")
        return

    print("=" * 70, flush=True)
    print("最终策略对比: 随机 vs 固定配时 vs DQN(50000步)", flush=True)
    print("=" * 70, flush=True)

    print("\n[1/3] 运行随机策略 (5 episodes)...", flush=True)
    t0 = time.time()
    random_stats = run_random_policy(episodes=5)
    print(f"  平均奖励: {random_stats['mean_reward']:.4f} ± {random_stats['std_reward']:.4f}", flush=True)
    print(f"  耗时: {time.time() - t0:.1f}s", flush=True)

    print("\n[2/3] 运行固定配时策略 (5 episodes)...", flush=True)
    t0 = time.time()
    fixed_stats = run_fixed_time_policy(episodes=5)
    print(f"  平均奖励: {fixed_stats['mean_reward']:.4f} ± {fixed_stats['std_reward']:.4f}", flush=True)
    print(f"  耗时: {time.time() - t0:.1f}s", flush=True)

    print("\n[3/3] 运行DQN(50k)策略 (5 episodes, deterministic)...", flush=True)
    model = DQN.load(str(model_path_50k))
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
    dqn_stats = {
        "mean_reward": float(np.mean(dqn_rewards)),
        "std_reward": float(np.std(dqn_rewards)),
    }
    print(f"  平均奖励: {dqn_stats['mean_reward']:.4f} ± {dqn_stats['std_reward']:.4f}", flush=True)
    print(f"  耗时: {time.time() - t0:.1f}s", flush=True)

    print("\n" + "=" * 70, flush=True)
    print("对比结果汇总:", flush=True)
    print("=" * 70, flush=True)
    print(f"\n{'策略':<15} {'平均奖励':>10} {'标准差':>10} {'vs随机提升':>12} {'vs固定提升':>12}", flush=True)
    print(f"{'-'*60}", flush=True)
    print(f"{'随机':<15} {random_stats['mean_reward']:>10.4f} {random_stats['std_reward']:>10.4f} {'基准':>12} {'基准':>12}", flush=True)
    print(f"{'固定配时':<15} {fixed_stats['mean_reward']:>10.4f} {fixed_stats['std_reward']:>10.4f} {(fixed_stats['mean_reward']-random_stats['mean_reward']):>+11.4f} {'基准':>12}", flush=True)
    print(f"{'DQN(50k)':<15} {dqn_stats['mean_reward']:>10.4f} {dqn_stats['std_reward']:>10.4f} {(dqn_stats['mean_reward']-random_stats['mean_reward']):>+11.4f} {(dqn_stats['mean_reward']-fixed_stats['mean_reward']):>+11.4f}", flush=True)

    imp_vs_random = (dqn_stats['mean_reward'] - random_stats['mean_reward']) / abs(random_stats['mean_reward']) * 100
    imp_vs_fixed = (dqn_stats['mean_reward'] - fixed_stats['mean_reward']) / abs(fixed_stats['mean_reward']) * 100
    print(f"\n  DQN vs 随机提升: {imp_vs_random:+.1f}%", flush=True)
    print(f"  DQN vs 固定配时提升: {imp_vs_fixed:+.1f}%", flush=True)

    results = {
        "random": random_stats,
        "fixed_time": fixed_stats,
        "dqn_50000": dqn_stats,
        "improvement_vs_random_percent": imp_vs_random,
        "improvement_vs_fixed_percent": imp_vs_fixed,
    }
    results_path = PROJECT_ROOT / "models" / "dqn" / "final_comparison_50k.json"
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n详细结果: {results_path}", flush=True)

    print("\n✅ Phase 2.4 完成!", flush=True)


if __name__ == "__main__":
    main()
