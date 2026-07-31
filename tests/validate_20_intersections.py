"""20路口泛化验证

验证多路口训练后的模型在所有20个路口上的性能

用法:
    python tests/validate_20_intersections.py
"""
import sys
import json
import time
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from configs.constants import INTERSECTION_ORDER
from env.single_intersection_env import SingleIntersectionEnv


def validate_on_all_intersections(model_path: str, episodes_per_intersection: int = 3):
    """在所有20个路口上验证模型"""
    from stable_baselines3 import DQN

    if not Path(model_path).exists():
        print(f"错误: 模型不存在: {model_path}")
        return None

    print(f"加载模型: {model_path}")
    model = DQN.load(model_path)

    results = {}
    all_rewards = []

    print(f"\n在 {len(INTERSECTION_ORDER)} 个路口上验证...")
    print("=" * 60)

    for i, intersection_id in enumerate(INTERSECTION_ORDER):
        print(f"\n[{i+1}/{len(INTERSECTION_ORDER)}] 验证 {intersection_id}...", flush=True)
        rewards = []

        for ep in range(episodes_per_intersection):
            env = SingleIntersectionEnv(
                intersection_id=intersection_id,
                max_steps=720,
                delta_time=5,
            )
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

        mean_reward = float(np.mean(rewards))
        std_reward = float(np.std(rewards))
        results[intersection_id] = {
            "mean_reward": mean_reward,
            "std_reward": std_reward,
            "rewards": rewards,
        }
        all_rewards.extend(rewards)
        print(f"  {intersection_id}: {mean_reward:.4f} ± {std_reward:.4f}")

    overall_mean = float(np.mean(all_rewards))
    overall_std = float(np.std(all_rewards))

    print("\n" + "=" * 60)
    print("泛化验证结果汇总:")
    print("=" * 60)
    print(f"  总路口数: {len(INTERSECTION_ORDER)}")
    print(f"  每路口测试回合: {episodes_per_intersection}")
    print(f"  总测试回合: {len(all_rewards)}")
    print(f"  全局平均奖励: {overall_mean:.4f} ± {overall_std:.4f}")
    print(f"  最优路口: {max(results.keys(), key=lambda x: results[x]['mean_reward'])} "
          f"({max(results.values(), key=lambda x: x['mean_reward'])['mean_reward']:.4f})")
    print(f"  最差路口: {min(results.keys(), key=lambda x: results[x]['mean_reward'])} "
          f"({min(results.values(), key=lambda x: x['mean_reward'])['mean_reward']:.4f})")

    good_count = sum(1 for r in results.values() if r["mean_reward"] > overall_mean)
    print(f"  表现优于平均水平路口数: {good_count}/{len(INTERSECTION_ORDER)}")

    return {
        "model_path": model_path,
        "episodes_per_intersection": episodes_per_intersection,
        "overall_mean": overall_mean,
        "overall_std": overall_std,
        "per_intersection_results": results,
    }


def main():
    model_path = PROJECT_ROOT / "models" / "dqn" / "dqn_multi_shared_100000steps.zip"

    if not model_path.exists():
        print(f"等待模型训练完成: {model_path}")
        print("请先完成 Phase 3.1 训练")
        return

    results = validate_on_all_intersections(str(model_path), episodes_per_intersection=3)

    if results:
        save_path = PROJECT_ROOT / "models" / "dqn" / "generalization_results.json"
        with open(save_path, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n结果已保存: {save_path}")


if __name__ == "__main__":
    main()