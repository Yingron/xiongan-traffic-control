"""多步数模型对比: 5k vs 20k vs 50k vs 100k

评估不同训练步数下模型性能的收敛情况

用法:
    python training/compare_checkpoints.py
"""
import sys
import json
import time
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from env.single_intersection_env import SingleIntersectionEnv


def evaluate_checkpoint(model_path, checkpoint_name, episodes=5):
    """评估单个检查点"""
    from stable_baselines3 import DQN

    if not Path(model_path).exists():
        print(f"  ⚠️  跳过: {model_path} 不存在")
        return None

    print(f"\n评估 {checkpoint_name}...")
    model = DQN.load(str(model_path))

    rewards = []
    for ep in range(episodes):
        env = SingleIntersectionEnv(intersection_id="J01", max_steps=720, delta_time=5)
        obs, info = env.reset(seed=42 + ep)
        total_reward = 0.0
        done = False
        while not done:
            action, _ = model.predict(obs, deterministic=True)
            obs, reward, terminated, truncated, info = env.step(int(action))
            total_reward += reward
            done = terminated or truncated
        rewards.append(total_reward)
        env.close()
        print(f"    Episode {ep+1}: reward={total_reward:.4f}")

    return {
        "name": checkpoint_name,
        "mean_reward": float(np.mean(rewards)),
        "std_reward": float(np.std(rewards)),
        "min_reward": float(np.min(rewards)),
        "max_reward": float(np.max(rewards)),
    }


def main():
    models_dir = PROJECT_ROOT / "models" / "dqn"

    checkpoints = [
        ("5000", "dqn_J01_5000steps.zip"),
        ("20000", "dqn_J01_20000steps.zip"),
        ("50000", "dqn_J01_50000steps.zip"),
        ("100000", "dqn_J01_100000steps.zip"),
    ]

    print("=" * 60)
    print("DQN 多步数检查点对比")
    print("=" * 60)

    results = []
    for steps, filename in checkpoints:
        model_path = models_dir / filename
        result = evaluate_checkpoint(str(model_path), f"{steps} steps", episodes=5)
        if result:
            results.append(result)

    if not results:
        print("\n❌ 没有可评估的模型，请先运行训练")
        return

    print("\n" + "=" * 60)
    print("对比结果:")
    print("=" * 60)

    print(f"\n{'步数':<12} {'平均奖励':>12} {'标准差':>10} {'vs 5k提升':>12} {'收敛指示':>12}")
    print("-" * 70)

    baseline = results[0]["mean_reward"] if results else 0
    prev_reward = None

    for i, r in enumerate(results):
        improvement = (r["mean_reward"] - baseline) / abs(baseline) * 100 if baseline != 0 else 0

        if prev_reward is not None:
            delta = r["mean_reward"] - prev_reward
            pct = delta / abs(prev_reward) * 100 if prev_reward != 0 else 0
            if abs(pct) < 2:
                converged = "✅ 已收敛"
            elif pct > 0:
                converged = "📈 仍在提升"
            else:
                converged = "📉 开始下降"
        else:
            converged = "📊 基准"

        print(f"{r['name']:<12} {r['mean_reward']:>12.4f} {r['std_reward']:>10.4f} "
              f"{improvement:>+11.1f}% {converged:>12}")

        prev_reward = r["mean_reward"]

    print(f"\n💡 收敛判断: 当相邻检查点奖励提升 < 2% 时视为已收敛")

    results_path = models_dir / "checkpoint_comparison.json"
    with open(results_path, "w") as f:
        json.dump({"results": results}, f, indent=2)
    print(f"\n结果已保存: {results_path}")


if __name__ == "__main__":
    main()
