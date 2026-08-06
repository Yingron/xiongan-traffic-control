"""四策略多维度评估脚本

对比 Random / Fixed-Time / Max-Pressure / DQN 在以下维度的表现：
- Mobility: 排队长度、等待时间、行程时间、通行量
- Environment: 燃油消耗、CO2排放
- Safety: 停车次数、时间损失

产出:
- multi_metrics_comparison.json
- multi_metrics_comparison.png
- multi_metrics_comparison.csv

用法:
    python evaluation/evaluate_all_strategies.py
"""
from __future__ import annotations

import sys
import csv
import json
import time
from pathlib import Path
from typing import Dict, List

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from env.single_intersection_env import SingleIntersectionEnv
from evaluation.metrics_collector import MetricsCollector, get_approach_edges
from configs.constants import MIN_GREEN_SECONDS


# ============================================================
# 通用运行框架：每步采集指标
# ============================================================
def run_strategy_with_metrics(
    strategy_name: str,
    action_fn,
    episodes: int = 5,
    intersection_id: str = "J01",
    max_steps: int = 720,
    delta_time: int = 5,
) -> Dict:
    """运行策略并采集多维度指标

    Args:
        strategy_name: 策略名称
        action_fn: 策略函数 (obs, env, step) -> action
        episodes: 测试回合数
        intersection_id: 路口ID
        max_steps: 最大仿真步数
        delta_time: 每步仿真秒数

    Returns:
        汇总指标字典
    """
    all_episode_summaries = []

    for ep in range(episodes):
        env = SingleIntersectionEnv(
            intersection_id=intersection_id,
            max_steps=max_steps,
            delta_time=delta_time,
        )
        obs, info = env.reset(seed=42 + ep)

        # 获取进口道edge IDs
        edge_ids = get_approach_edges(intersection_id, env._traci)
        collector = MetricsCollector(edge_ids, intersection_id)

        total_reward = 0.0
        done = False
        step = 0

        while not done:
            action = action_fn(obs, env, step)
            obs, reward, terminated, truncated, info = env.step(action)
            total_reward += reward

            # 采集指标
            collector.collect(env._traci, incidents=info.get("incidents"))

            step += 1
            done = terminated or truncated

        ep_summary = collector.get_summary()
        ep_summary["episode_reward"] = float(total_reward)
        ep_summary["episode"] = ep + 1
        all_episode_summaries.append(ep_summary)

        env.close()

    # 跨回合聚合
    result = {"strategy": strategy_name, "episodes": episodes}

    metric_fields = [
        "queue_length", "waiting_time", "travel_time", "throughput",
        "fuel_consumption", "co2_emission", "stop_count", "time_loss", "collisions", "teleports",
    ]

    for field_name in metric_fields:
        means = [s[field_name]["mean"] for s in all_episode_summaries]
        totals = [s[field_name]["total"] for s in all_episode_summaries]
        result[field_name] = {
            "mean": float(np.mean(means)),
            "std": float(np.std(means)),
            "total": float(np.mean(totals)),
        }

    # 奖励
    rewards = [s["episode_reward"] for s in all_episode_summaries]
    result["reward"] = {
        "mean": float(np.mean(rewards)),
        "std": float(np.std(rewards)),
    }

    return result


# ============================================================
# 策略函数
# ============================================================
def random_action(obs, env, step):
    return env.action_space.sample()


def fixed_time_action(obs, env, step):
    return (step // 5) % 4


def max_pressure_action(obs, env, step):
    from baselines.adaptive import MaxPressureController
    if not hasattr(env, "_mp_controller"):
        env._mp_controller = MaxPressureController()
    sim_time = float(env._traci.simulation.getTime())
    elapsed = sim_time - env._phase_changed_at
    current_phase = int(env._traci.trafficlight.getPhase(env.intersection_id))
    return env._mp_controller.get_action(obs, current_phase, elapsed)


def make_dqn_action(model_path: str):
    """创建DQN策略函数"""
    from stable_baselines3 import DQN
    model = DQN.load(str(model_path))

    def dqn_action(obs, env, step):
        action, _ = model.predict(obs, deterministic=True)
        return int(action)

    return dqn_action


# ============================================================
# 主函数
# ============================================================
def main():
    import argparse

    parser = argparse.ArgumentParser(description="Evaluate traffic-control strategies on identical SUMO seeds.")
    parser.add_argument("--model-path", type=Path, default=None, help="DQN zip model to evaluate")
    parser.add_argument("--episodes", type=int, default=5)
    parser.add_argument("--intersection", type=str, default="J01")
    parser.add_argument("--max-steps", type=int, default=720)
    args = parser.parse_args()

    save_dir = PROJECT_ROOT / "models" / "dqn"
    save_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70, flush=True)
    print("Multi-Dimension Strategy Evaluation", flush=True)
    print("Random vs Fixed-Time vs Max-Pressure vs DQN", flush=True)
    print("=" * 70, flush=True)

    strategies = [
        ("Random", random_action),
        ("Fixed-Time", fixed_time_action),
        ("Max-Pressure", max_pressure_action),
    ]

    # DQN模型
    model_path = args.model_path or (save_dir / "dqn_multi_shared_5000steps.zip")
    if model_path.exists():
        strategies.append((f"DQN({model_path.stem})", make_dqn_action(str(model_path))))
    else:
        print(f"  Warning: DQN model not found at {model_path}", flush=True)

    all_results = []

    for name, action_fn in strategies:
        print(f"\n[{len(all_results)+1}/{len(strategies)}] Running {name}...", flush=True)
        t0 = time.time()
        result = run_strategy_with_metrics(
            name,
            action_fn,
            episodes=args.episodes,
            intersection_id=args.intersection,
            max_steps=args.max_steps,
        )
        elapsed = time.time() - t0

        print(f"  Reward:      {result['reward']['mean']:.4f} ± {result['reward']['std']:.4f}", flush=True)
        print(f"  Queue:       {result['queue_length']['mean']:.4f}", flush=True)
        print(f"  Wait Time:   {result['waiting_time']['mean']:.4f}s", flush=True)
        print(f"  Travel Time: {result['travel_time']['mean']:.4f}s", flush=True)
        print(f"  Fuel:        {result['fuel_consumption']['mean']:.4f} mL/s", flush=True)
        print(f"  CO2:         {result['co2_emission']['mean']:.4f} mg/s", flush=True)
        print(f"  Stops:       {result['stop_count']['mean']:.1f}", flush=True)
        print(f"  Collisions:  {result['collisions']['total']:.0f}", flush=True)
        print(f"  Teleports:   {result['teleports']['total']:.0f}", flush=True)
        print(f"  Elapsed:     {elapsed:.1f}s", flush=True)

        all_results.append(result)

    # ---- 保存JSON ----
    json_path = save_dir / "multi_metrics_comparison.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"\nJSON saved: {json_path}", flush=True)

    # ---- 保存CSV ----
    csv_path = save_dir / "multi_metrics_comparison.csv"
    metric_names = [
        "reward", "queue_length", "waiting_time", "travel_time",
        "throughput", "fuel_consumption", "co2_emission", "stop_count", "time_loss", "collisions", "teleports",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["strategy"] + [f"{m}_mean" for m in metric_names] + [f"{m}_std" for m in metric_names])
        for r in all_results:
            row = [r["strategy"]]
            for m in metric_names:
                row.append(f"{r[m]['mean']:.6f}")
            for m in metric_names:
                row.append(f"{r[m]['std']:.6f}")
            writer.writerow(row)
    print(f"CSV saved: {csv_path}", flush=True)

    # ---- 生成图表 ----
    plot_comparison_chart(all_results, save_dir)

    # ---- 汇总表格 ----
    print("\n" + "=" * 70, flush=True)
    print("Summary Comparison:", flush=True)
    print("=" * 70, flush=True)

    strategy_names = [r["strategy"] for r in all_results]
    print(f"\n{'Metric':<20}", end="", flush=True)
    for name in strategy_names:
        print(f"  {name:>15}", end="", flush=True)
    print(flush=True)
    print("-" * (20 + 17 * len(strategy_names)), flush=True)

    display_metrics = [
        ("Reward", "reward"),
        ("Queue Length", "queue_length"),
        ("Waiting Time (s)", "waiting_time"),
        ("Travel Time (s)", "travel_time"),
        ("Fuel (mL/s)", "fuel_consumption"),
        ("CO2 (mg/s)", "co2_emission"),
        ("Stop Count", "stop_count"),
    ]

    for display_name, metric_key in display_metrics:
        print(f"{display_name:<20}", end="", flush=True)
        baseline = all_results[0][metric_key]["mean"]
        for r in all_results:
            val = r[metric_key]["mean"]
            print(f"  {val:>15.4f}", end="", flush=True)
        print(flush=True)

    print("\n[OK] Multi-dimension evaluation complete!", flush=True)


def plot_comparison_chart(results: List[Dict], save_dir: Path):
    """生成多维度对比图表（柱状图 + 雷达图）"""

    strategy_names = [r["strategy"] for r in results]
    colors = ["#e74c3c", "#f39c12", "#3498db", "#2ecc71"]

    # 柱状图：6个子图
    fig, axes = plt.subplots(2, 3, figsize=(18, 10))

    metrics_config = [
        ("queue_length", "Avg Queue Length", "vehicles", False),
        ("waiting_time", "Avg Waiting Time", "seconds", False),
        ("travel_time", "Avg Travel Time", "seconds", False),
        ("fuel_consumption", "Fuel Consumption", "mL/s", False),
        ("co2_emission", "CO2 Emission", "mg/s", False),
        ("stop_count", "Stop Count", "vehicles", False),
    ]

    for idx, (metric_key, title, ylabel, _) in enumerate(metrics_config):
        ax = axes[idx // 3][idx % 3]
        values = [r[metric_key]["mean"] for r in results]
        errors = [r[metric_key]["std"] for r in results]

        bars = ax.bar(strategy_names, values, yerr=errors, capsize=4,
                       color=colors[:len(results)], alpha=0.85, edgecolor="black", linewidth=0.5)
        ax.set_ylabel(ylabel, fontsize=11)
        ax.set_title(title, fontsize=12, fontweight="bold")
        ax.grid(axis="y", alpha=0.3)

        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width()/2., bar.get_height() + 0.01 * max(values),
                    f"{val:.2f}", ha="center", va="bottom", fontsize=9)

    plt.suptitle("Multi-Dimension Strategy Comparison (J01 Intersection)",
                 fontsize=15, fontweight="bold", y=1.02)
    plt.tight_layout()
    chart_path = save_dir / "multi_metrics_comparison.png"
    fig.savefig(chart_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Chart saved: {chart_path}", flush=True)

    # 雷达图
    radar_metrics = ["queue_length", "waiting_time", "travel_time",
                     "fuel_consumption", "co2_emission", "stop_count"]
    radar_labels = ["Queue", "Wait Time", "Travel Time", "Fuel", "CO2", "Stops"]

    # 归一化（除以最大值，值越小越好 → 转换为 1 - normalized 表示越好越接近外圈）
    max_values = {m: max(r[m]["mean"] for r in results) for m in radar_metrics}

    angles = np.linspace(0, 2 * np.pi, len(radar_metrics), endpoint=False).tolist()
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True))

    for i, r in enumerate(results):
        values = []
        for m in radar_metrics:
            max_v = max_values[m]
            if max_v > 0:
                # 越小越好 → 反转 (1 - val/max)
                normalized = 1.0 - (r[m]["mean"] / max_v)
            else:
                normalized = 1.0
            values.append(normalized)
        values += values[:1]

        ax.plot(angles, values, "o-", linewidth=2, label=r["strategy"], color=colors[i])
        ax.fill(angles, values, alpha=0.15, color=colors[i])

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(radar_labels, fontsize=11)
    ax.set_ylim(0, 1)
    ax.set_title("Strategy Radar (outer = better)", fontsize=13, fontweight="bold", pad=20)
    ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1), fontsize=10)

    radar_path = save_dir / "multi_metrics_radar.png"
    fig.savefig(radar_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Radar chart saved: {radar_path}", flush=True)


if __name__ == "__main__":
    main()
