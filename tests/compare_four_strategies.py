"""四策略对比：随机 vs 固定配时 vs Max-Pressure(自适应) vs DQN

生成对比图表和详细数据，补全赛题要求的基线对比实验

用法:
    python tests/compare_four_strategies.py
"""
import sys
import json
import time
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from env.single_intersection_env import SingleIntersectionEnv
from configs.constants import MIN_GREEN_SECONDS


# ============================================================
# 策略1：随机
# ============================================================
def run_random_policy(episodes=5):
    rewards_all = []
    queues_all = []
    for ep in range(episodes):
        env = SingleIntersectionEnv(intersection_id="J01", max_steps=720, delta_time=5)
        obs, info = env.reset(seed=42 + ep)
        total_reward = 0.0
        done = False
        while not done:
            action = env.action_space.sample()
            obs, reward, terminated, truncated, info = env.step(action)
            total_reward += reward
            queues_all.append(float(obs[0:4].sum()))
            done = terminated or truncated
        rewards_all.append(total_reward)
        env.close()
    return {
        "mean_reward": float(np.mean(rewards_all)),
        "std_reward": float(np.std(rewards_all)),
        "mean_queue": float(np.mean(queues_all)),
        "std_queue": float(np.std(queues_all)),
        "rewards": rewards_all,
    }


# ============================================================
# 策略2：固定配时（周期切换，每5步切换一次）
# ============================================================
def run_fixed_time_policy(episodes=5):
    rewards_all = []
    queues_all = []
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
            queues_all.append(float(obs[0:4].sum()))
            step += 1
            done = terminated or truncated
        rewards_all.append(total_reward)
        env.close()
    return {
        "mean_reward": float(np.mean(rewards_all)),
        "std_reward": float(np.std(rewards_all)),
        "mean_queue": float(np.mean(queues_all)),
        "std_queue": float(np.std(queues_all)),
        "rewards": rewards_all,
    }


# ============================================================
# 策略3：Max-Pressure 自适应控制
# ============================================================
def run_max_pressure_policy(episodes=5):
    from baselines.adaptive import MaxPressureController

    controller = MaxPressureController()
    rewards_all = []
    queues_all = []

    for ep in range(episodes):
        env = SingleIntersectionEnv(intersection_id="J01", max_steps=720, delta_time=5)
        obs, info = env.reset(seed=42 + ep)
        total_reward = 0.0
        done = False
        while not done:
            sim_time = float(env._traci.simulation.getTime())
            elapsed = sim_time - env._phase_changed_at
            action = controller.get_action(obs, env._current_phase, elapsed)
            obs, reward, terminated, truncated, info = env.step(action)
            total_reward += reward
            queues_all.append(float(obs[0:4].sum()))
            done = terminated or truncated
        rewards_all.append(total_reward)
        env.close()

    return {
        "mean_reward": float(np.mean(rewards_all)),
        "std_reward": float(np.std(rewards_all)),
        "mean_queue": float(np.mean(queues_all)),
        "std_queue": float(np.std(queues_all)),
        "rewards": rewards_all,
    }


# ============================================================
# 策略4：DQN (50k 单路口模型)
# ============================================================
def run_dqn_policy(model_path, episodes=5):
    from stable_baselines3 import DQN

    model = DQN.load(str(model_path))
    rewards_all = []
    queues_all = []

    for ep in range(episodes):
        env = SingleIntersectionEnv(intersection_id="J01", max_steps=720, delta_time=5)
        obs, info = env.reset(seed=42 + ep)
        total_reward = 0.0
        done = False
        while not done:
            action, _ = model.predict(obs, deterministic=True)
            obs, reward, terminated, truncated, info = env.step(int(action))
            total_reward += reward
            queues_all.append(float(obs[0:4].sum()))
            done = terminated or truncated
        rewards_all.append(total_reward)
        env.close()

    return {
        "mean_reward": float(np.mean(rewards_all)),
        "std_reward": float(np.std(rewards_all)),
        "mean_queue": float(np.mean(queues_all)),
        "std_queue": float(np.std(queues_all)),
        "rewards": rewards_all,
    }


# ============================================================
# 主函数：运行对比并生成图表
# ============================================================
def main():
    save_dir = PROJECT_ROOT / "models" / "dqn"

    print("=" * 70, flush=True)
    print("四策略对比: 随机 vs 固定配时 vs Max-Pressure vs DQN", flush=True)
    print("=" * 70, flush=True)

    # 策略1：随机
    print("\n[1/4] 迚机策略 (5 episodes)...", flush=True)
    t0 = time.time()
    random_stats = run_random_policy(episodes=5)
    print(f"  奖励: {random_stats['mean_reward']:.4f} ± {random_stats['std_reward']:.4f}", flush=True)
    print(f"  排队: {random_stats['mean_queue']:.4f} ± {random_stats['std_queue']:.4f}", flush=True)
    print(f"  耗时: {time.time()-t0:.1f}s", flush=True)

    # 策略2：固定配时
    print("\n[2/4] 固定配时策略 (5 episodes)...", flush=True)
    t0 = time.time()
    fixed_stats = run_fixed_time_policy(episodes=5)
    print(f"  奖励: {fixed_stats['mean_reward']:.4f} ± {fixed_stats['std_reward']:.4f}", flush=True)
    print(f"  排队: {fixed_stats['mean_queue']:.4f} ± {fixed_stats['std_queue']:.4f}", flush=True)
    print(f"  耗时: {time.time()-t0:.1f}s", flush=True)

    # 策略3：Max-Pressure
    print("\n[3/4] Max-Pressure 自适应策略 (5 episodes)...", flush=True)
    t0 = time.time()
    mp_stats = run_max_pressure_policy(episodes=5)
    print(f"  奖励: {mp_stats['mean_reward']:.4f} ± {mp_stats['std_reward']:.4f}", flush=True)
    print(f"  排队: {mp_stats['mean_queue']:.4f} ± {mp_stats['std_queue']:.4f}", flush=True)
    print(f"  耗时: {time.time()-t0:.1f}s", flush=True)

    # 策略4：DQN
    model_path = save_dir / "dqn_J01_50000steps.zip"
    if not model_path.exists():
        print(f"\n[4/4] DQN模型不存在: {model_path}，跳过", flush=True)
        dqn_stats = None
    else:
        print(f"\n[4/4] DQN策略 (5 episodes, model: {model_path.name})...", flush=True)
        t0 = time.time()
        dqn_stats = run_dqn_policy(model_path, episodes=5)
        print(f"  奖励: {dqn_stats['mean_reward']:.4f} ± {dqn_stats['std_reward']:.4f}", flush=True)
        print(f"  排队: {dqn_stats['mean_queue']:.4f} ± {dqn_stats['std_queue']:.4f}", flush=True)
        print(f"  耗时: {time.time()-t0:.1f}s", flush=True)

    # 汇总表格
    print("\n" + "=" * 70, flush=True)
    print("对比结果汇总:", flush=True)
    print("=" * 70, flush=True)

    strategies = [
        ("随机", random_stats),
        ("固定配时", fixed_stats),
        ("Max-Pressure", mp_stats),
    ]
    if dqn_stats:
        strategies.append(("DQN(50k)", dqn_stats))

    baseline = random_stats["mean_reward"]
    print(f"\n{'策略':<16} {'平均奖励':>10} {'标准差':>8} {'平均排队':>10} {'vs随机':>10}", flush=True)
    print(f"{'-'*58}", flush=True)
    for name, s in strategies:
        imp = (s["mean_reward"] - baseline) / abs(baseline) * 100 if baseline != 0 else 0
        print(f"{name:<16} {s['mean_reward']:>10.4f} {s['std_reward']:>8.4f} "
              f"{s['mean_queue']:>10.4f} {imp:>+9.1f}%", flush=True)

    # 生成图表
    fig, axes = plt.subplots(1, 2, figsize=(16, 7))

    names = ["Random", "Fixed-Time", "Max-Pressure", "DQN(50k)"]
    # 截取实际策略数
    names = names[:len(strategies)]
    rewards = [s[1]["mean_reward"] for s in strategies]
    reward_errs = [s[1]["std_reward"] for s in strategies]
    queues = [s[1]["mean_queue"] for s in strategies]
    queue_errs = [s[1]["std_queue"] for s in strategies]

    colors = ["#e74c3c", "#f39c12", "#3498db", "#2ecc71"]

    bars1 = axes[0].bar(names, rewards, yerr=reward_errs, capsize=5,
                         color=colors[:len(names)], alpha=0.85, edgecolor="black", linewidth=0.5)
    axes[0].set_ylabel("Average Reward", fontsize=13)
    axes[0].set_title("Strategy Comparison - Reward (J01)", fontsize=14, fontweight="bold")
    axes[0].grid(axis="y", alpha=0.3)
    for bar, val in zip(bars1, rewards):
        axes[0].text(bar.get_x() + bar.get_width()/2., bar.get_height() + 0.3,
                     f"{val:.2f}", ha="center", va="bottom", fontsize=11, fontweight="bold")

    bars2 = axes[1].bar(names, queues, yerr=queue_errs, capsize=5,
                         color=colors[:len(names)], alpha=0.85, edgecolor="black", linewidth=0.5)
    axes[1].set_ylabel("Average Queue Length", fontsize=13)
    axes[1].set_title("Strategy Comparison - Queue (J01)", fontsize=14, fontweight="bold")
    axes[1].grid(axis="y", alpha=0.3)
    for bar, val in zip(bars2, queues):
        axes[1].text(bar.get_x() + bar.get_width()/2., bar.get_height() + 0.01,
                     f"{val:.3f}", ha="center", va="bottom", fontsize=11, fontweight="bold")

    plt.tight_layout()
    chart_path = save_dir / "four_strategy_comparison.png"
    fig.savefig(chart_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"\n图表已保存: {chart_path}", flush=True)

    # 保存JSON
    results = {
        "random": random_stats,
        "fixed_time": fixed_stats,
        "max_pressure": mp_stats,
    }
    if dqn_stats:
        results["dqn_50k"] = dqn_stats

    json_path = save_dir / "four_strategy_comparison.json"
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"数据已保存: {json_path}", flush=True)

    print("\n✅ 四策略对比完成!", flush=True)


if __name__ == "__main__":
    main()
