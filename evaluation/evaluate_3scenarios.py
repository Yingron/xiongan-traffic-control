"""三场景全模型评估脚本

在三个真实需求场景（真实早高峰/平峰/晚高峰，需求来自赛题 xlsx）下运行
DQN 策略与真实定周期 Fixed-Time 基线策略（配时来自 data/timing_plans.json），
采集多维度指标（排队、等待、行程时间、燃油、CO2、停车、碰撞等），
生成对比报告（JSON + CSV + 图表）。

Fixed-Time 基线说明：
    旧的 fixed_time_action = (step//5)%4（20s 周期每相位 5s，比 MIN_GREEN 15s 还短）
    是假基线；现在改为 baselines/fixed_time.py 的 RealFixedTimeController——
    读取 data/timing_plans.json 的 {路口}/{时段} 真实配时（如 J01 早高峰
    38/32/32/38、周期 160s），安装真实信号程序后由 SUMO 自主按周期运行，
    与 DQN 在完全相同的仿真种子下对比。

用法:
    python evaluation/evaluate_3scenarios.py
    python evaluation/evaluate_3scenarios.py --episodes 3 --max-steps 720
"""
from __future__ import annotations

import csv
import gc
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 设置 SUMO_HOME
if "SUMO_HOME" not in os.environ:
    candidate = PROJECT_ROOT.parent / "tools" / "sumo-1.27.1" / "sumo-1.27.1"
    if candidate.exists():
        os.environ["SUMO_HOME"] = str(candidate)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
# 图表含中文标签（真实早高峰等），配置中文字体避免方框乱码
plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

from env.single_intersection_env import SingleIntersectionEnv
from evaluation.metrics_collector import MetricsCollector, get_approach_edges
from training.config import SCENARIO_CONFIG
from baselines.fixed_time import make_real_fixed_time_action

# ============================================================
# 配置：场景 → 模型文件
# ============================================================
MODEL_DIR = PROJECT_ROOT / "models" / "dqn"

# 三场景固定使用真实需求场景（scripts/generate_real_demand_scenarios.py 生成，
# 需求来自赛题 xlsx）。period 指定 Fixed-Time 基线读取 timing_plans.json 的时段。
SCENARIO_MODELS = {
    "real_peak": {
        "model": MODEL_DIR / "dqn_multi_shared_real_peak_perf_1000000steps.zip",
        "anticollapse_model": MODEL_DIR / "dqn_multi_shared_real_peak_anticollapse_2000000steps.zip",
        "label": "真实早高峰",
        "period": "peak",
        "sumo_cfg": SCENARIO_CONFIG["real_peak"]["sumo_cfg"],
    },
    "real_offpeak": {
        "model": MODEL_DIR / "dqn_multi_shared_real_offpeak_perf_1000000steps.zip",
        "anticollapse_model": MODEL_DIR / "dqn_multi_shared_real_offpeak_anticollapse_2000000steps.zip",
        "label": "真实平峰",
        "period": "offpeak",
        "sumo_cfg": SCENARIO_CONFIG["real_offpeak"]["sumo_cfg"],
    },
    "real_evening": {
        "model": MODEL_DIR / "dqn_multi_shared_real_evening_perf_1000000steps.zip",
        "anticollapse_model": MODEL_DIR / "dqn_multi_shared_real_evening_anticollapse_2000000steps.zip",
        "label": "真实晚高峰",
        "period": "evening",
        "sumo_cfg": SCENARIO_CONFIG["real_evening"]["sumo_cfg"],
    },
}

# 测试路口列表（从30个路口中选取代表性路口：含网格边界与新增 J21-J30 区域）
TEST_INTERSECTIONS = ["J01", "J05", "J10", "J15", "J20", "J21", "J25", "J30"]


# ============================================================
# 策略函数
# ============================================================
def make_fixed_time_action(intersection_id: str, period: str):
    """真实定周期基线（见 baselines/fixed_time.py）。

    每个 (路口, 时段) 一个控制器；在首个 env 上安装 timing_plans.json 的真实
    配时程序，之后恒返回 FIXED_TIME_CONTROL 哨兵动作。
    """
    action_fn, controller = make_real_fixed_time_action(intersection_id, period)
    return action_fn, controller


def make_dqn_action(model_path: str):
    """创建 DQN 策略函数"""
    from stable_baselines3 import DQN
    model = DQN.load(str(model_path))

    def dqn_action(obs, env, step):
        action, _ = model.predict(obs, deterministic=True)
        return int(action)

    return dqn_action


# ============================================================
# 单路口评估
# ============================================================
def evaluate_single_intersection(
    strategy_name: str,
    action_fn,
    intersection_id: str,
    sumo_cfg_path: str,
    episodes: int = 3,
    max_steps: int = 720,
    delta_time: int = 5,
    seed: int = 42,
) -> Dict:
    """在指定路口和场景下评估一个策略

    Returns:
        汇总指标字典
    """
    all_episode_summaries = []

    for ep in range(episodes):
        env = SingleIntersectionEnv(
            intersection_id=intersection_id,
            sumo_cfg_path=sumo_cfg_path,
            max_steps=max_steps,
            delta_time=delta_time,
            seed=seed + ep,
        )
        obs, info = env.reset()

        edge_ids = get_approach_edges(intersection_id, env._traci)
        collector = MetricsCollector(edge_ids, intersection_id)

        total_reward = 0.0
        done = False
        step = 0

        while not done:
            action = action_fn(obs, env, step)
            obs, reward, terminated, truncated, info = env.step(action)
            total_reward += reward
            collector.collect(env._traci, incidents=info.get("incidents"))
            step += 1
            done = terminated or truncated

        ep_summary = collector.get_summary()
        ep_summary["episode_reward"] = float(total_reward)
        ep_summary["episode"] = ep + 1
        all_episode_summaries.append(ep_summary)

        env.close()
        gc.collect()

    # 跨回合聚合
    result = {"strategy": strategy_name, "intersection": intersection_id, "episodes": episodes}

    metric_fields = [
        "queue_length", "waiting_time", "travel_time", "throughput",
        "fuel_consumption", "co2_emission", "stop_count", "time_loss",
        "collisions", "teleports",
    ]

    for field_name in metric_fields:
        means = [s[field_name]["mean"] for s in all_episode_summaries]
        totals = [s[field_name]["total"] for s in all_episode_summaries]
        result[field_name] = {
            "mean": float(np.mean(means)),
            "std": float(np.std(means)),
            "total": float(np.mean(totals)),
        }

    rewards = [s["episode_reward"] for s in all_episode_summaries]
    result["reward"] = {
        "mean": float(np.mean(rewards)),
        "std": float(np.std(rewards)),
    }

    return result


# ============================================================
# 场景评估
# ============================================================
def evaluate_scenario(
    scenario_key: str,
    scenario_info: Dict,
    episodes: int = 3,
    max_steps: int = 720,
) -> List[Dict]:
    """评估一个场景下的 DQN vs Fixed-Time (可选对比抗坍缩DQN)

    Returns:
        所有路口×策略的评估结果列表
    """
    model_path = scenario_info["model"]
    anticollapse_path = scenario_info.get("anticollapse_model")
    scenario_label = scenario_info["label"]
    period = scenario_info["period"]
    sumo_cfg = scenario_info["sumo_cfg"]

    print(f"\n{'=' * 70}", flush=True)
    print(f"  场景评估: {scenario_label} ({scenario_key})", flush=True)
    print(f"  Fixed-Time 配时时段: {period} (timing_plans.json)", flush=True)
    print(f"  原模型: {model_path.name} {'[存在]' if model_path.exists() else '[不存在]'}", flush=True)
    if anticollapse_path:
        print(f"  抗坍缩模型: {anticollapse_path.name} {'[存在]' if anticollapse_path.exists() else '[不存在]'}", flush=True)
    print(f"  SUMO: {Path(sumo_cfg).name}", flush=True)
    print(f"  测试路口: {', '.join(TEST_INTERSECTIONS)}", flush=True)
    print(f"  每路口回合数: {episodes}", flush=True)
    print(f"{'=' * 70}", flush=True)

    all_results = []

    for intersection_id in TEST_INTERSECTIONS:
        # Fixed-Time 基线按 (路口, 时段) 取真实配时，需在每个路口内构造 action_fn
        fixed_time_action, ft_controller = make_fixed_time_action(intersection_id, period)
        strategies = [("Fixed-Time", fixed_time_action)]

        if model_path.exists():
            dqn_action = make_dqn_action(str(model_path))
            strategies.append(("DQN-Original", dqn_action))
        else:
            print(f"  [WARN] 原DQN模型不存在，跳过", flush=True)

        if anticollapse_path and anticollapse_path.exists():
            ac_action = make_dqn_action(str(anticollapse_path))
            strategies.append(("DQN-AntiCollapse", ac_action))
        elif anticollapse_path:
            print(f"  [INFO] 抗坍缩模型不存在，跳过 (训练后自动出现)", flush=True)

        # 打印真实配时摘要
        ft_summary = ft_controller.plan_summary
        if ft_summary:
            plan_phases = " + ".join(
                f"{p['name']}(绿{p['green']}s)" for p in ft_summary["phases"]
            )
            print(f"\n  [Fixed-Time] {intersection_id} 周期={ft_summary['cycle']}s: {plan_phases}", flush=True)

        for strategy_name, action_fn in strategies:
            tag = f"{scenario_label}/{intersection_id}/{strategy_name}"
            print(f"\n  [{tag}] 运行中...", flush=True)
            t0 = time.time()

            try:
                result = evaluate_single_intersection(
                    strategy_name=f"{strategy_name}",
                    action_fn=action_fn,
                    intersection_id=intersection_id,
                    sumo_cfg_path=sumo_cfg,
                    episodes=episodes,
                    max_steps=max_steps,
                )
                result["scenario"] = scenario_key
                result["scenario_label"] = scenario_label
                elapsed = time.time() - t0

                print(f"    奖励:     {result['reward']['mean']:.4f} ± {result['reward']['std']:.4f}", flush=True)
                print(f"    排队:     {result['queue_length']['mean']:.2f}", flush=True)
                print(f"    等待:     {result['waiting_time']['mean']:.2f}s", flush=True)
                print(f"    行程时间: {result['travel_time']['mean']:.2f}s", flush=True)
                print(f"    通行量:   {result['throughput']['total']:.0f}", flush=True)
                print(f"    燃油:     {result['fuel_consumption']['mean']:.4f} mL/s", flush=True)
                print(f"    CO2:      {result['co2_emission']['mean']:.4f} mg/s", flush=True)
                print(f"    停车:     {result['stop_count']['mean']:.1f}", flush=True)
                print(f"    碰撞:     {result['collisions']['total']:.0f}", flush=True)
                print(f"    传送:     {result['teleports']['total']:.0f}", flush=True)
                print(f"    耗时:     {elapsed:.1f}s", flush=True)

                all_results.append(result)
            except Exception as e:
                print(f"    [ERROR] 评估失败: {e}", flush=True)
                import traceback
                traceback.print_exc()

    return all_results


# ============================================================
# 汇总与报告生成
# ============================================================
def generate_report(all_results: List[Dict], save_dir: Path):
    """生成 JSON、CSV 和图表报告"""

    save_dir.mkdir(parents=True, exist_ok=True)

    # ---- JSON ----
    json_path = save_dir / "3scenario_evaluation_report.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"\n[SAVE] JSON: {json_path}", flush=True)

    # ---- CSV ----
    csv_path = save_dir / "3scenario_evaluation_report.csv"
    metric_names = [
        "reward", "queue_length", "waiting_time", "travel_time",
        "throughput", "fuel_consumption", "co2_emission",
        "stop_count", "time_loss", "collisions", "teleports",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        header = ["scenario", "intersection", "strategy"] + [f"{m}_mean" for m in metric_names] + [f"{m}_std" for m in metric_names]
        writer.writerow(header)
        for r in all_results:
            row = [r["scenario"], r["intersection"], r["strategy"]]
            for m in metric_names:
                row.append(f"{r[m]['mean']:.6f}")
            for m in metric_names:
                row.append(f"{r[m]['std']:.6f}")
            writer.writerow(row)
    print(f"[SAVE] CSV: {csv_path}", flush=True)

    # ---- 图表 ----
    plot_scenario_comparison(all_results, save_dir)


def plot_scenario_comparison(all_results: List[Dict], save_dir: Path):
    """生成三场景对比图表"""

    scenarios = list(SCENARIO_MODELS.keys())  # real_peak / real_offpeak / real_evening
    scenario_labels = [SCENARIO_MODELS[s]["label"] for s in scenarios]
    # 策略取评估结果中实际出现的（Fixed-Time 恒存在；DQN-Original/AntiCollapse 视模型而定）
    strategies = [s for s in ["Fixed-Time", "DQN-Original", "DQN-AntiCollapse"]
                  if any(r["strategy"] == s for r in all_results)]
    palette = ["#e74c3c", "#2ecc71", "#3498db"]
    colors = {s: palette[i] for i, s in enumerate(strategies)}

    metrics_config = [
        ("queue_length", "Avg Queue Length", "vehicles"),
        ("waiting_time", "Avg Waiting Time", "seconds"),
        ("travel_time", "Avg Travel Time", "seconds"),
        ("throughput", "Total Throughput", "vehicles"),
        ("fuel_consumption", "Fuel Consumption", "mL/s"),
        ("co2_emission", "CO2 Emission", "mg/s"),
        ("stop_count", "Stop Count", "vehicles"),
        ("reward", "Avg Reward", ""),
    ]

    # 图1: 每个场景下各路口的 DQN vs Fixed-Time 对比（4个子图，每个2指标）
    fig, axes = plt.subplots(4, 2, figsize=(16, 20))

    for idx, (metric_key, title, ylabel) in enumerate(metrics_config):
        ax = axes[idx // 2][idx % 2]
        x = np.arange(len(TEST_INTERSECTIONS))
        width = 0.35

        for si, scenario in enumerate(scenarios):
            offset = (si - 1) * width * 0.5
            for sti, strategy in enumerate(strategies):
                vals = []
                for intersection in TEST_INTERSECTIONS:
                    match = [r for r in all_results
                             if r["scenario"] == scenario
                             and r["intersection"] == intersection
                             and r["strategy"] == strategy]
                    if match:
                        vals.append(match[0][metric_key]["mean"])
                    else:
                        vals.append(0.0)
                # 只画一个场景的柱状图太拥挤，改为按策略分组
                if si == 0 and sti == 0:
                    pass  # placeholder

        # 简化：按策略分组，取所有场景所有路口的平均值
        for sti, strategy in enumerate(strategies):
            means_per_scenario = []
            stds_per_scenario = []
            for scenario in scenarios:
                vals = [r[metric_key]["mean"] for r in all_results
                        if r["scenario"] == scenario and r["strategy"] == strategy]
                means_per_scenario.append(np.mean(vals) if vals else 0)
                stds_per_scenario.append(np.std(vals) if vals else 0)

            bars = ax.bar(
                np.arange(len(scenarios)) + sti * width,
                means_per_scenario,
                width,
                yerr=stds_per_scenario,
                capsize=4,
                label=strategy,
                color=colors[strategy],
                alpha=0.85,
                edgecolor="black",
                linewidth=0.5,
            )
            for bar, val in zip(bars, means_per_scenario):
                ax.text(bar.get_x() + bar.get_width() / 2., bar.get_height() + 0.01 * max(means_per_scenario + [1]),
                        f"{val:.2f}", ha="center", va="bottom", fontsize=8)

        ax.set_xticks(np.arange(len(scenarios)) + width / 2)
        ax.set_xticklabels(scenario_labels, fontsize=11)
        ax.set_ylabel(ylabel, fontsize=10)
        ax.set_title(title, fontsize=12, fontweight="bold")
        ax.legend(fontsize=9)
        ax.grid(axis="y", alpha=0.3)

    plt.suptitle("3-Scenario Evaluation: DQN vs Fixed-Time", fontsize=16, fontweight="bold", y=1.01)
    plt.tight_layout()
    chart_path = save_dir / "3scenario_comparison.png"
    fig.savefig(chart_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[SAVE] 对比图: {chart_path}", flush=True)

    # 图2: DQN 相对 Fixed-Time 的改善率（按场景×指标热力图）
    improvement_data = []
    display_metrics = [
        ("queue_length", "Queue"),
        ("waiting_time", "Wait Time"),
        ("travel_time", "Travel Time"),
        ("fuel_consumption", "Fuel"),
        ("co2_emission", "CO2"),
        ("stop_count", "Stops"),
    ]

    for scenario in scenarios:
        row = []
        # 优先用原DQN模型做对比，缺失时退化为抗坍缩模型
        dqn_strategy = next((s for s in ["DQN-Original", "DQN-AntiCollapse"]
                             if any(r["scenario"] == scenario and r["strategy"] == s for r in all_results)), None)
        for metric_key, _ in display_metrics:
            ft_vals = [r[metric_key]["mean"] for r in all_results
                       if r["scenario"] == scenario and r["strategy"] == "Fixed-Time"]
            dqn_vals = [r[metric_key]["mean"] for r in all_results
                        if dqn_strategy and r["scenario"] == scenario and r["strategy"] == dqn_strategy]
            if ft_vals and dqn_vals:
                ft_mean = np.mean(ft_vals)
                dqn_mean = np.mean(dqn_vals)
                if ft_mean != 0:
                    improvement = (ft_mean - dqn_mean) / ft_mean * 100
                else:
                    improvement = 0
            else:
                improvement = 0
            row.append(improvement)
        improvement_data.append(row)

    fig, ax = plt.subplots(figsize=(10, 4))
    data = np.array(improvement_data)
    im = ax.imshow(data, cmap="RdYlGn", aspect="auto", vmin=-50, vmax=50)

    ax.set_xticks(np.arange(len(display_metrics)))
    ax.set_xticklabels([m[1] for m in display_metrics], fontsize=11)
    ax.set_yticks(np.arange(len(scenarios)))
    ax.set_yticklabels(scenario_labels, fontsize=11)

    for i in range(len(scenarios)):
        for j in range(len(display_metrics)):
            val = data[i, j]
            color = "white" if abs(val) > 30 else "black"
            ax.text(j, i, f"{val:.1f}%", ha="center", va="center", color=color, fontsize=11, fontweight="bold")

    ax.set_title("DQN vs Fixed-Time Improvement (%)  [positive=DQN better]", fontsize=13, fontweight="bold")
    plt.colorbar(im, ax=ax, shrink=0.8, label="Improvement (%)")
    heatmap_path = save_dir / "3scenario_improvement_heatmap.png"
    fig.savefig(heatmap_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[SAVE] 热力图: {heatmap_path}", flush=True)


# ============================================================
# 汇总打印
# ============================================================
def print_summary(all_results: List[Dict]):
    """打印汇总对比表"""
    print(f"\n{'=' * 70}", flush=True)
    print("  三场景评估汇总报告", flush=True)
    print(f"{'=' * 70}", flush=True)

    scenarios = list(SCENARIO_MODELS.keys())  # real_peak / real_offpeak / real_evening
    scenario_labels = [SCENARIO_MODELS[s]["label"] for s in scenarios]

    available_strategies = list(dict.fromkeys(r["strategy"] for r in all_results))
    strategy_labels = {
        "Fixed-Time": "固定配时",
        "DQN": "DQN(原)",
        "DQN-Original": "DQN(原)",
        "DQN-AntiCollapse": "DQN(抗坍缩)",
    }

    for si, scenario in enumerate(scenarios):
        print(f"\n  ── {scenario_labels[si]} ({scenario}) ──", flush=True)
        header_str = f"  {'路口':<8}"
        for s in available_strategies:
            header_str += f" {strategy_labels.get(s, s):<14}"
        print(header_str + f" {'碰撞':>6} {'传送':>6}", flush=True)

        for intersection in TEST_INTERSECTIONS:
            line = f"  {intersection:<8}"
            for strategy in available_strategies:
                match = [r for r in all_results
                         if r["scenario"] == scenario
                         and r["intersection"] == intersection
                         and r["strategy"] == strategy]
                if match:
                    r = match[0]
                    line += f" {r['reward']['mean']:>7.4f} Q={r['queue_length']['mean']:>5.1f} W={r['waiting_time']['mean']:>5.0f}"
                else:
                    line += f" {'N/A':<14}"
            collisions = sum(r['collisions']['total'] for r in all_results
                            if r["scenario"] == scenario and r["intersection"] == intersection)
            teleports = sum(r['teleports']['total'] for r in all_results
                           if r["scenario"] == scenario and r["intersection"] == intersection)
            line += f" {collisions:>6.0f} {teleports:>6.0f}"
            print(line, flush=True)

    # 改善率汇总
    print(f"\n  ── DQN 相对 Fixed-Time 改善率 ──", flush=True)
    metric_labels = [
        ("queue_length", "排队长度"),
        ("waiting_time", "等待时间"),
        ("travel_time", "行程时间"),
        ("fuel_consumption", "燃油消耗"),
        ("co2_emission", "CO2排放"),
        ("stop_count", "停车数"),
    ]

    print(f"  {'指标':<12}", end="", flush=True)
    for label in scenario_labels:
        print(f"  {label:>10}", end="", flush=True)
    print(flush=True)
    print(f"  {'-' * 12}" + f"  {'-' * 10}" * len(scenario_labels), flush=True)

    dqn_strategies_to_compare = [s for s in available_strategies if s != "Fixed-Time"]

    for dqn_strat in dqn_strategies_to_compare:
        print(f"\n  --- {strategy_labels.get(dqn_strat, dqn_strat)} vs Fixed-Time ---", flush=True)
        for metric_key, metric_label in metric_labels:
            print(f"  {metric_label:<12}", end="", flush=True)
            for scenario in scenarios:
                ft_vals = [r[metric_key]["mean"] for r in all_results
                           if r["scenario"] == scenario and r["strategy"] == "Fixed-Time"]
                dqn_vals = [r[metric_key]["mean"] for r in all_results
                            if r["scenario"] == scenario and r["strategy"] == dqn_strat]
                if ft_vals and dqn_vals:
                    ft_mean = np.mean(ft_vals)
                    dqn_mean = np.mean(dqn_vals)
                    if ft_mean != 0:
                        imp = (ft_mean - dqn_mean) / ft_mean * 100
                        print(f"  {imp:>9.1f}%", end="", flush=True)
                    else:
                        print(f"  {'N/A':>10}", end="", flush=True)
                else:
                    print(f"  {'N/A':>10}", end="", flush=True)
            print(flush=True)

    # 抗坍缩DQN vs 原DQN对比
    if "DQN-Original" in available_strategies and "DQN-AntiCollapse" in available_strategies:
        print(f"\n  --- 抗坍缩DQN vs 原DQN 改善率 ---", flush=True)
        for metric_key, metric_label in metric_labels:
            print(f"  {metric_label:<12}", end="", flush=True)
            for scenario in scenarios:
                orig_vals = [r[metric_key]["mean"] for r in all_results
                            if r["scenario"] == scenario and r["strategy"] == "DQN-Original"]
                ac_vals = [r[metric_key]["mean"] for r in all_results
                           if r["scenario"] == scenario and r["strategy"] == "DQN-AntiCollapse"]
                if orig_vals and ac_vals:
                    orig_mean = np.mean(orig_vals)
                    ac_mean = np.mean(ac_vals)
                    if orig_mean != 0:
                        imp = (orig_mean - ac_mean) / abs(orig_mean) * 100
                        print(f"  {imp:>9.1f}%", end="", flush=True)
                    else:
                        print(f"  {'N/A':>10}", end="", flush=True)
                else:
                    print(f"  {'N/A':>10}", end="", flush=True)
            print(flush=True)

    print(f"\n{'=' * 70}", flush=True)
    print("  评估完成!", flush=True)
    print(f"{'=' * 70}", flush=True)


# ============================================================
# 主函数
# ============================================================
def main():
    import argparse

    parser = argparse.ArgumentParser(description="三场景全模型评估: DQN vs Fixed-Time")
    parser.add_argument("--episodes", type=int, default=3, help="每路口测试回合数 (默认3)")
    parser.add_argument("--max-steps", type=int, default=720, help="每回合最大步数 (默认720, 即3600秒)")
    parser.add_argument("--intersections", type=str, default=None,
                        help="测试路口列表，逗号分隔 (默认 J01,J05,J10,J15,J20)")
    args = parser.parse_args()

    global TEST_INTERSECTIONS
    if args.intersections:
        TEST_INTERSECTIONS = [x.strip() for x in args.intersections.split(",")]

    save_dir = MODEL_DIR

    print(f"{'=' * 70}", flush=True)
    print(f"  三场景全模型评估", flush=True)
    print(f"  测试路口: {', '.join(TEST_INTERSECTIONS)}", flush=True)
    print(f"  每路口回合数: {args.episodes}", flush=True)
    print(f"  每回合步数: {args.max_steps} ({args.max_steps * 5}秒仿真)", flush=True)
    print(f"{'=' * 70}", flush=True)

    all_results = []

    for scenario_key, scenario_info in SCENARIO_MODELS.items():
        results = evaluate_scenario(
            scenario_key,
            scenario_info,
            episodes=args.episodes,
            max_steps=args.max_steps,
        )
        all_results.extend(results)

        # 场景间清理
        gc.collect()
        try:
            os.system("taskkill /F /IM sumo.exe 2>nul")
        except Exception:
            pass

    if not all_results:
        print("\n[ERROR] 没有有效的评估结果，请检查模型文件和SUMO配置。", flush=True)
        return

    # 生成报告
    generate_report(all_results, save_dir)
    print_summary(all_results)


if __name__ == "__main__":
    main()
