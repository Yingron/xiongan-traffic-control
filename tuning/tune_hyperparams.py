"""DQN 超参数调优实验

测试不同超参数组合，找出最优配置：
1. 学习率: 1e-4, 5e-4, 1e-3, 5e-3
2. 网络架构: [128], [256], [512], [256, 256]
3. 探索率: 0.1, 0.3, 0.5
4. 折扣因子: 0.95, 0.99, 0.999

用法:
    python tuning/tune_hyperparams.py
"""
import sys
import json
import time
from pathlib import Path

import numpy as np
import torch.nn as nn

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from env.single_intersection_env import SingleIntersectionEnv


def make_env(intersection_id="J01", max_steps=720, delta_time=5):
    return SingleIntersectionEnv(
        intersection_id=intersection_id,
        max_steps=max_steps,
        delta_time=delta_time,
    )


def train_single_config(config, timesteps=10000, seed=42):
    """训练单个超参数配置"""
    from stable_baselines3 import DQN
    from stable_baselines3.common.monitor import Monitor

    env = make_env("J01")
    env = Monitor(env, str(PROJECT_ROOT / "logs" / "tuning" / config["name"]))

    print(f"  创建模型...", flush=True)
    model = DQN(
        policy="MlpPolicy",
        env=env,
        learning_rate=config["learning_rate"],
        buffer_size=config.get("buffer_size", 10000),
        batch_size=config.get("batch_size", 64),
        gamma=config["gamma"],
        exploration_fraction=config["exploration_fraction"],
        exploration_final_eps=0.05,
        train_freq=4,
        target_update_interval=500,
        verbose=0,
        seed=seed,
        policy_kwargs=dict(
            net_arch=config["net_arch"],
            activation_fn=nn.Tanh,
        ),
    )

    print(f"  开始训练 ({timesteps} steps)...", flush=True)
    t0 = time.time()
    model.learn(total_timesteps=timesteps)
    elapsed = time.time() - t0

    print(f"  评估中...", flush=True)
    rewards = []
    for ep in range(3):
        eval_env = make_env("J01")
        obs, info = eval_env.reset(seed=seed + ep + 100)
        total_reward = 0.0
        done = False
        while not done:
            action, _ = model.predict(obs, deterministic=True)
            obs, reward, terminated, truncated, info = eval_env.step(int(action))
            total_reward += reward
            done = terminated or truncated
        rewards.append(total_reward)
        eval_env.close()

    env.close()

    return {
        "config": config,
        "mean_reward": float(np.mean(rewards)),
        "std_reward": float(np.std(rewards)),
        "elapsed": elapsed,
        "timesteps": timesteps,
    }


def main():
    import itertools

    save_dir = PROJECT_ROOT / "models" / "tuning"
    save_dir.mkdir(parents=True, exist_ok=True)

    results = []

    experiments = [
        {
            "name": "baseline",
            "learning_rate": 1e-3,
            "net_arch": [256, 256],
            "gamma": 0.99,
            "exploration_fraction": 0.3,
        },
        {
            "name": "lr_1e-4",
            "learning_rate": 1e-4,
            "net_arch": [256, 256],
            "gamma": 0.99,
            "exploration_fraction": 0.3,
        },
        {
            "name": "lr_5e-4",
            "learning_rate": 5e-4,
            "net_arch": [256, 256],
            "gamma": 0.99,
            "exploration_fraction": 0.3,
        },
        {
            "name": "net_512",
            "learning_rate": 1e-3,
            "net_arch": [512],
            "gamma": 0.99,
            "exploration_fraction": 0.3,
        },
        {
            "name": "gamma_0.95",
            "learning_rate": 1e-3,
            "net_arch": [256, 256],
            "gamma": 0.95,
            "exploration_fraction": 0.3,
        },
        {
            "name": "deep_3x256",
            "learning_rate": 1e-3,
            "net_arch": [256, 256, 256],
            "gamma": 0.99,
            "exploration_fraction": 0.3,
        },
    ]

    print("=" * 60, flush=True)
    print("DQN 超参数调优实验", flush=True)
    print(f"共 {len(experiments)} 个配置，每个训练 10000 步", flush=True)
    print("=" * 60, flush=True)

    for i, config in enumerate(experiments):
        print(f"\n[{i+1}/{len(experiments)}] 测试: {config['name']}", flush=True)
        try:
            result = train_single_config(config, timesteps=10000, seed=42)
            results.append(result)
            print(f"  奖励: {result['mean_reward']:.4f} ± {result['std_reward']:.4f}", flush=True)
            print(f"  耗时: {result['elapsed']:.1f}s", flush=True)
        except Exception as e:
            print(f"  失败: {e}", flush=True)
            results.append({
                "config": config,
                "mean_reward": -999,
                "std_reward": 0,
                "error": str(e),
            })

    print("\n" + "=" * 60)
    print("调优结果汇总:")
    print("=" * 60)

    valid_results = [r for r in results if r["mean_reward"] > -900]
    valid_results.sort(key=lambda x: x["mean_reward"], reverse=True)

    print(f"\n{'排名':<5} {'配置名':<20} {'平均奖励':>10} {'标准差':>10} {'学习率':>10} {'网络':>15} {'Gamma':>8}")
    print("-" * 85)

    for i, r in enumerate(valid_results):
        c = r["config"]
        print(f"{i+1:<5} {c['name']:<20} {r['mean_reward']:>10.4f} {r['std_reward']:>10.4f} "
              f"{c['learning_rate']:>10.0e} {str(c['net_arch']):>15} {c['gamma']:>8.3f}")

    best = valid_results[0] if valid_results else None
    if best:
        print(f"\n最优配置: {best['config']['name']}")
        print(f"  奖励: {best['mean_reward']:.4f}")
        print(f"  学习率: {best['config']['learning_rate']}")
        print(f"  网络: {best['config']['net_arch']}")
        print(f"  Gamma: {best['config']['gamma']}")

    results_path = save_dir / "tuning_results.json"
    with open(results_path, "w") as f:
        json.dump({
            "best_config": best["config"] if best else None,
            "best_reward": best["mean_reward"] if best else None,
            "all_results": results,
        }, f, indent=2, default=str)
    print(f"\n完整结果: {results_path}")


if __name__ == "__main__":
    main()
