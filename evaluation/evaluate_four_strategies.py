"""四策略同口径评估补齐脚本（Random / Max-Pressure → 并入官方 FT/DQN 行）

报告 3.4.6 需要"四策略（Fixed-Time / Max-Pressure / Random / 共享掩码 DQN）在相同
30 路口三场景、同一种子组上的完整对比"。Fixed-Time 与 DQN-Original 的行已由
evaluate_3scenarios.py 于 2026-08-19 产出（models/dqn/3scenario_evaluation_report.json，
3 场景 × 30 路口 × 3 回合，种子 42/43/44），本脚本只补齐缺失的 Random 与
Max-Pressure，评估协议逐项保持一致：

- 同一仿真环境：SingleIntersectionEnv 单路口控制器 + 30 路口路网其余路口走默认信号程序；
- 同一参数：episodes=3、720 步 × 5s、SUMO 种子 42+ep；
- 同一 schema：策略行含 scenario / scenario_label / intersection / episodes，
  指标字段与官方行完全一致，可直接合并生成四策略报告。

产出（不覆盖官方文件）：
- models/dqn/multi_metrics_4strategies.json / .csv：本次新跑的策略行
- 同名 .partial.json：分场景落盘进度，中断后可 --resume 续跑

用法:
    python evaluation/evaluate_four_strategies.py                                   # 默认 30 路口 × 3 回合
    python evaluation/evaluate_four_strategies.py --intersections J01,J05           # 小批量
    python evaluation/evaluate_four_strategies.py --episodes 5 --max-steps 720     # 8路口代表口径 × 5 回合
"""
from __future__ import annotations

import argparse
import csv
import gc
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# SUMO_HOME 缺省候选路径与官方脚本保持一致
if "SUMO_HOME" not in os.environ:
    candidate = PROJECT_ROOT.parent / "tools" / "sumo-1.27.1" / "sumo-1.27.1"
    if candidate.exists():
        os.environ["SUMO_HOME"] = str(candidate)

from training.config import SCENARIO_CONFIG
from evaluation.evaluate_3scenarios import evaluate_single_intersection, SCENARIO_MODELS
from baselines.adaptive import FourPhaseMaxPressureController
from baselines.fixed_time import make_real_fixed_time_action

ALL_INTERSECTIONS = [f"J{i:02d}" for i in range(1, 31)]


def random_action(obs, env, step):
    return int(env.action_space.sample())


def make_max_pressure_action():
    """标准四相位 Max-Pressure 感应控制：压力 = 各相位绿灯链路上的排队（halting）数，
    选压力最大相位，遵守最小绿灯 15 s（控制器内部按当前相位已持续时间判断）。"""
    controller = FourPhaseMaxPressureController()

    def max_pressure_action(obs, env, step):
        sim_time = float(env._traci.simulation.getTime())
        elapsed = sim_time - env._phase_changed_at
        current_phase = int(env._traci.trafficlight.getPhase(env.intersection_id))
        return controller.get_action(env._traci, env.intersection_id, current_phase, elapsed)

    return max_pressure_action


def make_fixed_time_action(junction_id: str, period: str):
    action_fn, _ = make_real_fixed_time_action(junction_id, period)
    return action_fn


def strategy_factory(name: str, junction_id: str, period: str):
    if name == "Random":
        return random_action
    if name == "Max-Pressure":
        return make_max_pressure_action()
    if name == "Fixed-Time":
        return make_fixed_time_action(junction_id, period)
    raise ValueError(f"未知策略: {name}")


def main():
    parser = argparse.ArgumentParser(description="补齐四策略对比中的 Random / Max-Pressure 评估")
    parser.add_argument("--scenarios", type=str,
                        default="real_peak,real_offpeak,real_evening",
                        help="场景列表（SCENARIO_CONFIG 键），逗号分隔")
    parser.add_argument("--intersections", type=str, default=",".join(ALL_INTERSECTIONS),
                        help="路口列表，逗号分隔（默认 J01-J30 全量）")
    parser.add_argument("--strategies", type=str, default="Random,Max-Pressure",
                        help="本次评估的策略（默认补齐 Random 与 Max-Pressure）")
    parser.add_argument("--episodes", type=int, default=3)
    parser.add_argument("--max-steps", type=int, default=720)
    parser.add_argument("--out", type=str, default="multi_metrics_4strategies",
                        help="输出文件前缀（写往 models/dqn/ 下）")
    parser.add_argument("--resume", action="store_true", help="跳过已完成组合（读 .done 记录）")
    args = parser.parse_args()

    scenarios = [s.strip() for s in args.scenarios.split(",")]
    intersections = [x.strip() for x in args.intersections.split(",")]
    strategies = [s.strip() for s in args.strategies.split(",")]
    save_dir = PROJECT_ROOT / "models" / "dqn"
    save_dir.mkdir(parents=True, exist_ok=True)
    out_json = save_dir / f"{args.out}.json"
    out_csv = save_dir / f"{args.out}.csv"
    done_file = save_dir / f"{args.out}.done"

    done_set: set[str] = set()
    if args.resume and done_file.exists():
        done_set = {line.strip() for line in done_file.read_text(encoding="utf-8").splitlines() if line.strip()}
        print(f"[RESUME] 已存在 {len(done_set)} 个完成组合，跳过", flush=True)

    # 合法组合校验（防手误）：Fixed-Time 只能在三场景内使用对应真实配时
    period_map = {"real_peak": "peak", "real_offpeak": "offpeak", "real_evening": "evening"}

    print("=" * 70, flush=True)
    print("四策略补齐评估: Random / Max-Pressure（协议与 3scenario 官方评估一致）", flush=True)
    print(f"  场景: {scenarios}", flush=True)
    print(f"  路口: {len(intersections)} 个: {intersections[0]}..{intersections[-1]}", flush=True)
    print(f"  策略: {strategies}", flush=True)
    print(f"  每回合: {args.max_steps} 步 x {args.episodes} 回合 (种子 42-{41+args.episodes})", flush=True)
    print("=" * 70, flush=True)

    all_results: list[dict] = []
    combos_total = len(scenarios) * len(intersections) * len(strategies)
    combos_done = 0
    t_start = time.time()

    for scenario_key in scenarios:
        info = SCENARIO_MODELS[scenario_key]
        sumo_cfg = info["sumo_cfg"]
        label = info["label"]
        period = period_map[scenario_key]
        for junction_id in intersections:
            for strategy_name in strategies:
                combo = f"{scenario_key}|{junction_id}|{strategy_name}"
                if combo in done_set:
                    combos_done += 1
                    continue
                action_fn = strategy_factory(strategy_name, junction_id, period)
                tag = f"[{combos_done+1}/{combos_total}] {label}/{junction_id}/{strategy_name}"
                print(f"\n  {tag} 运行中...", flush=True)
                t0 = time.time()
                try:
                    result = evaluate_single_intersection(
                        strategy_name=strategy_name,
                        action_fn=action_fn,
                        intersection_id=junction_id,
                        sumo_cfg_path=sumo_cfg,
                        episodes=args.episodes,
                        max_steps=args.max_steps,
                    )
                    result["scenario"] = scenario_key
                    result["scenario_label"] = label
                except Exception as e:
                    print(f"    [ERROR] 评估失败: {e}", flush=True)
                    import traceback
                    traceback.print_exc()
                    sys.exit(1)

                elapsed = time.time() - t0
                eta = elapsed * (combos_total - combos_done - 1) / 60 if combos_total > combos_done else 0
                print(f"    reward={result['reward']['mean']:.1f}±{result['reward']['std']:.1f} "
                      f"wait={result['waiting_time']['mean']:.0f}s "
                      f"collision={result['collisions']['total']:.0f} "
                      f"耗时={elapsed:.0f}s 剩余≈{eta:.0f}min", flush=True)
                all_results.append(result)
                with open(done_file, "a", encoding="utf-8") as f:
                    f.write(combo + "\n")
                combos_done += 1
        # 每完成一个场景即落盘，中断损失 ≤ 1 个场景
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(all_results, f, indent=2, ensure_ascii=False)
        print(f"[SAVE] 阶段性结果: {out_json}（{len(all_results)} 行）", flush=True)
        gc.collect()
        try:
            os.system("taskkill /F /IM sumo.exe 2>nul")
        except Exception:
            pass

    if not all_results:
        print("[SKIP] 无新结果（组合均已跑过），如需重跑请删除 .done 文件。", flush=True)
        return

    # ---- CSV（列布局与官方 3scenario_evaluation_report.csv 一致）----
    metric_names = [
        "reward", "queue_length", "waiting_time", "travel_time",
        "throughput", "fuel_consumption", "co2_emission",
        "stop_count", "time_loss", "collisions", "teleports",
    ]
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["scenario", "intersection", "strategy"] + [f"{m}_mean" for m in metric_names] + [f"{m}_std" for m in metric_names])
        for r in all_results:
            row = [r["scenario"], r["intersection"], r["strategy"]]
            for m in metric_names:
                row.append(f"{r[m]['mean']:.6f}")
            for m in metric_names:
                row.append(f"{r[m]['std']:.6f}")
            writer.writerow(row)
    print(f"[SAVE] CSV: {out_csv}", flush=True)
    print(f"[DONE] 总耗时 {(time.time()-t_start)/60:.1f} min，{len(all_results)} 行结果可并入官方 JSON", flush=True)


if __name__ == "__main__":
    main()
