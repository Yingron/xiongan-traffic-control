"""多场景流量泛化压力测试

保持DQN模型权重不变，在低/中/高三档需求场景下进行推理测试。
验证模型在不同交通拥堵程度下的泛化能力。

流量场景（以真实早高峰需求为基准缩放，xiongan_real_peak.rou.xml）:
  - 低峰 (low):    基准需求 × 0.5
  - 平峰 (medium): 基准需求 × 1.0（即真实早高峰）
  - 高峰 (high):   基准需求 × 1.25（真实早高峰已是容量匹配上限，1.25x 用于压力测试）

产出:
  - sumo_files/xiongan_gen_low.rou.xml / xiongan_gen_high.rou.xml (缩放后的路由文件)
  - sumo_files/xiongan_gen_low.sumocfg / xiongan_gen_high.sumocfg (场景配置)
  - generalization_test_results.json (详细数据)
  - generalization_performance.png (对比图)

用法:
    python tests/test_generalization.py
"""
from __future__ import annotations

import sys
import re
import json
import time
import csv
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
from configs.constants import MIN_GREEN_SECONDS, SUMO_FILES_DIR


# ============================================================
# Step 1: 生成不同流量场景的路由文件
# ============================================================
def generate_scaled_route_file(
    original_rou_path: Path,
    output_path: Path,
    scale: float,
):
    """从原始路由文件生成缩放版本

    Args:
        original_rou_path: 原始路由文件路径
        output_path: 输出路径
        scale: 流量缩放因子 (0.5=低峰, 1.25=高峰)
    """
    with open(original_rou_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 缩放每个flow的number属性
    def scale_number(match):
        original_num = int(match.group(1))
        scaled_num = max(1, int(original_num * scale))
        return f'number="{scaled_num}"'

    scaled_content = re.sub(r'number="(\d+)"', scale_number, content)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(scaled_content)

    # 统计车辆数
    original_total = sum(int(m) for m in re.findall(r'number="(\d+)"', content))
    scaled_total = sum(int(m) for m in re.findall(r'number="(\d+)"', scaled_content))
    print(f"  Route file: {output_path.name} (scale={scale})", flush=True)
    print(f"    Vehicles: {original_total} -> {scaled_total}", flush=True)


def generate_scenario_configs():
    """生成低峰/高峰场景的sumocfg和rou.xml文件（基于真实早高峰需求缩放）"""
    original_rou = SUMO_FILES_DIR / "xiongan_real_peak.rou.xml"
    net_file = "xiongan_30.net.xml"

    scenarios = {
        "low": 0.5,
        "medium": 1.0,  # 使用原始文件
        "high": 1.25,
    }

    config_paths = {}

    for name, scale in scenarios.items():
        if name == "medium":
            config_paths[name] = SUMO_FILES_DIR / "xiongan_real_peak.sumocfg"
            continue

        rou_path = SUMO_FILES_DIR / f"xiongan_gen_{name}.rou.xml"
        generate_scaled_route_file(original_rou, rou_path, scale)

        cfg_content = f"""<?xml version="1.0" encoding="UTF-8"?>

<configuration xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="http://sumo.dlr.de/xsd/sumoConfiguration.xsd">
    <input>
        <net-file value="{net_file}"/>
        <route-files value="{rou_path.name}"/>
    </input>
    <output>
        <tripinfo-output value="tripinfo_gen_{name}.xml"/>
        <summary-output value="summary_gen_{name}.xml"/>
        <emission-output value="emissions_gen_{name}.xml"/>
    </output>
    <time>
        <begin value="0"/>
        <end value="3600"/>
        <step-length value="1"/>
    </time>
    <processing>
        <lateral-resolution value="0.5"/>
    </processing>
</configuration>
"""
        cfg_path = SUMO_FILES_DIR / f"xiongan_gen_{name}.sumocfg"
        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write(cfg_content)

        config_paths[name] = cfg_path
        print(f"  Config: {cfg_path.name}", flush=True)

    return config_paths


# ============================================================
# Step 2: 策略函数
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
    return env._mp_controller.get_action(obs, env._current_phase, elapsed)


def make_dqn_action(model_path: str):
    """创建DQN策略函数"""
    from stable_baselines3 import DQN
    model = DQN.load(str(model_path))

    def dqn_action(obs, env, step):
        action, _ = model.predict(obs, deterministic=True)
        return int(action)

    return dqn_action


# ============================================================
# Step 3: 运行评估
# ============================================================
def run_strategy_on_scenario(
    strategy_name: str,
    action_fn,
    sumocfg_path: str,
    episodes: int = 5,
    intersection_id: str = "J01",
    max_steps: int = 720,
    delta_time: int = 5,
) -> Dict:
    """在特定流量场景下运行策略并采集指标"""

    all_episode_summaries = []

    for ep in range(episodes):
        env = SingleIntersectionEnv(
            intersection_id=intersection_id,
            sumo_cfg_path=sumocfg_path,
            max_steps=max_steps,
            delta_time=delta_time,
        )
        obs, info = env.reset(seed=42 + ep)

        edge_ids = get_approach_edges(intersection_id, env._traci)
        collector = MetricsCollector(edge_ids, intersection_id)

        total_reward = 0.0
        done = False
        step = 0

        while not done:
            action = action_fn(obs, env, step)
            obs, reward, terminated, truncated, info = env.step(action)
            total_reward += reward
            collector.collect(env._traci)
            step += 1
            done = terminated or truncated

        ep_summary = collector.get_summary()
        ep_summary["episode_reward"] = float(total_reward)
        all_episode_summaries.append(ep_summary)
        env.close()

    # 聚合
    result = {"strategy": strategy_name, "episodes": episodes}
    metric_fields = [
        "queue_length", "waiting_time", "travel_time", "throughput",
        "fuel_consumption", "co2_emission", "stop_count", "time_loss",
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
# Step 4: 主函数
# ============================================================
def main():
    save_dir = PROJECT_ROOT / "models" / "dqn"
    save_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70, flush=True)
    print("Multi-Scenario Generalization Stress Test", flush=True)
    print("Low / Medium / High Traffic Flow", flush=True)
    print("=" * 70, flush=True)

    # Step 1: 生成场景配置
    print("\n[1/4] Generating scenario configs...", flush=True)
    config_paths = generate_scenario_configs()
    for name, path in config_paths.items():
        print(f"  {name}: {path.name}", flush=True)

    # Step 2: 准备策略
    print("\n[2/4] Preparing strategies...", flush=True)
    model_path = save_dir / "dqn_J01_50000steps.zip"

    strategies = [
        ("Random", random_action),
        ("Fixed-Time", fixed_time_action),
        ("Max-Pressure", max_pressure_action),
    ]
    if model_path.exists():
        strategies.append(("DQN(50k)", make_dqn_action(str(model_path))))
        print(f"  DQN model: {model_path.name}", flush=True)
    else:
        print(f"  Warning: DQN model not found at {model_path}", flush=True)

    # Step 3: 运行测试
    print("\n[3/4] Running generalization tests...", flush=True)
    scenario_names = ["low", "medium", "high"]
    scenario_labels = {"low": "Low (0.5x)", "medium": "Medium (1.0x)", "high": "High (1.25x)"}

    all_results = {}  # {scenario: [strategy_results]}

    for scenario in scenario_names:
        print(f"\n  --- Scenario: {scenario_labels[scenario]} ---", flush=True)
        cfg_path = str(config_paths[scenario])
        scenario_results = []

        for s_name, s_fn in strategies:
            print(f"    [{s_name}] running...", end="", flush=True)
            t0 = time.time()
            result = run_strategy_on_scenario(
                s_name, s_fn, cfg_path, episodes=5
            )
            elapsed = time.time() - t0
            result["scenario"] = scenario
            print(f" reward={result['reward']['mean']:.2f}, "
                  f"queue={result['queue_length']['mean']:.3f}, "
                  f"wait={result['waiting_time']['mean']:.1f}s, "
                  f"fuel={result['fuel_consumption']['mean']:.0f}, "
                  f"({elapsed:.1f}s)", flush=True)
            scenario_results.append(result)

        all_results[scenario] = scenario_results

    # Step 4: 保存结果
    print("\n[4/4] Saving results...", flush=True)

    # JSON
    json_path = save_dir / "generalization_test_results.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"  JSON: {json_path}", flush=True)

    # CSV
    csv_path = save_dir / "generalization_test_results.csv"
    metric_names = [
        "reward", "queue_length", "waiting_time", "travel_time",
        "throughput", "fuel_consumption", "co2_emission", "stop_count", "time_loss",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["scenario", "strategy"] + [f"{m}_mean" for m in metric_names] + [f"{m}_std" for m in metric_names])
        for scenario in scenario_names:
            for r in all_results[scenario]:
                row = [scenario, r["strategy"]]
                for m in metric_names:
                    row.append(f"{r[m]['mean']:.6f}")
                for m in metric_names:
                    row.append(f"{r[m]['std']:.6f}")
                writer.writerow(row)
    print(f"  CSV: {csv_path}", flush=True)

    # 图表
    plot_generalization(all_results, scenario_names, scenario_labels, save_dir)

    # 汇总表格
    print("\n" + "=" * 70, flush=True)
    print("Generalization Test Summary", flush=True)
    print("=" * 70, flush=True)

    for scenario in scenario_names:
        print(f"\n  [{scenario_labels[scenario]}]", flush=True)
        print(f"  {'Strategy':<16} {'Reward':>10} {'Queue':>10} {'Wait(s)':>10} "
              f"{'Fuel':>10} {'CO2':>10} {'Stops':>8}", flush=True)
        print(f"  {'-'*76}", flush=True)
        for r in all_results[scenario]:
            print(f"  {r['strategy']:<16} {r['reward']['mean']:>10.2f} "
                  f"{r['queue_length']['mean']:>10.3f} {r['waiting_time']['mean']:>10.1f} "
                  f"{r['fuel_consumption']['mean']:>10.0f} {r['co2_emission']['mean']:>10.0f} "
                  f"{r['stop_count']['mean']:>8.1f}", flush=True)

    # DQN跨场景对比
    print(f"\n  [DQN Cross-Scenario Comparison]", flush=True)
    print(f"  {'Scenario':<16} {'Reward':>10} {'Queue':>10} {'Wait(s)':>10} "
          f"{'Fuel':>10} {'CO2':>10} {'Stops':>8}", flush=True)
    print(f"  {'-'*76}", flush=True)
    for scenario in scenario_names:
        for r in all_results[scenario]:
            if r["strategy"].startswith("DQN"):
                print(f"  {scenario_labels[scenario]:<16} {r['reward']['mean']:>10.2f} "
                      f"{r['queue_length']['mean']:>10.3f} {r['waiting_time']['mean']:>10.1f} "
                      f"{r['fuel_consumption']['mean']:>10.0f} {r['co2_emission']['mean']:>10.0f} "
                      f"{r['stop_count']['mean']:>8.1f}", flush=True)

    print(f"\n✅ Generalization test complete!", flush=True)


def plot_generalization(all_results, scenario_names, scenario_labels, save_dir):
    """生成泛化性能对比图"""

    strategy_names = [r["strategy"] for r in all_results[scenario_names[0]]]
    colors = ["#e74c3c", "#f39c12", "#3498db", "#2ecc71"]
    n_strategies = len(strategy_names)
    n_scenarios = len(scenario_names)

    # 6个子图: reward, queue, waiting, fuel, co2, stops
    metrics_config = [
        ("reward", "Reward", False),
        ("queue_length", "Queue Length", False),
        ("waiting_time", "Waiting Time (s)", False),
        ("fuel_consumption", "Fuel (mL/s)", False),
        ("co2_emission", "CO2 (mg/s)", False),
        ("stop_count", "Stop Count", False),
    ]

    fig, axes = plt.subplots(2, 3, figsize=(18, 10))

    x = np.arange(n_scenarios)
    width = 0.8 / n_strategies

    for idx, (metric_key, title, _) in enumerate(metrics_config):
        ax = axes[idx // 3][idx % 3]

        for i, s_name in enumerate(strategy_names):
            values = []
            errors = []
            for scenario in scenario_names:
                for r in all_results[scenario]:
                    if r["strategy"] == s_name:
                        values.append(r[metric_key]["mean"])
                        errors.append(r[metric_key]["std"])
                        break

            offset = (i - n_strategies / 2 + 0.5) * width
            bars = ax.bar(x + offset, values, width, yerr=errors, capsize=3,
                          label=s_name, color=colors[i], alpha=0.85,
                          edgecolor="black", linewidth=0.5)

        ax.set_xticks(x)
        ax.set_xticklabels([scenario_labels[s] for s in scenario_names], fontsize=10)
        ax.set_title(title, fontsize=12, fontweight="bold")
        ax.grid(axis="y", alpha=0.3)
        if idx == 0:
            ax.legend(fontsize=9)

    plt.suptitle("Multi-Scenario Generalization Test (J01 Intersection)",
                 fontsize=15, fontweight="bold", y=1.02)
    plt.tight_layout()
    chart_path = save_dir / "generalization_performance.png"
    fig.savefig(chart_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Chart: {chart_path}", flush=True)


if __name__ == "__main__":
    main()
