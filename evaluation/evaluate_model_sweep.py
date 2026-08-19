"""单模型多路口扫评：DQN vs Fixed-Time(真实配时) vs Random vs Max-Pressure

用法:
    python evaluation/evaluate_model_sweep.py --model models/dqn/dqn_multi_shared_real_peak_perf_1000000steps.zip \
        --scenario real_peak --intersections J01,J05,J10,J21,J30 --episodes 5

产出:
    models/dqn/model_sweep_{model_stem}.json   (含逐路口×策略的多维指标)
    models/dqn/model_sweep_{model_stem}.csv
"""
from __future__ import annotations

import sys
import csv
import json
import time
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.evaluate_all_strategies import (
    run_strategy_with_metrics,
    random_action,
    max_pressure_action,
    make_dqn_action,
)
from baselines.fixed_time import make_real_fixed_time_action
from training.config import SCENARIO_CONFIG


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Single-model multi-intersection sweep vs real Fixed-Time baseline")
    parser.add_argument("--model", type=str, required=True, help="DQN 模型 zip 路径")
    parser.add_argument("--scenario", type=str, default="real_peak", choices=list(SCENARIO_CONFIG.keys()))
    parser.add_argument("--intersections", type=str, default="J01,J05,J10,J15,J20,J21,J25,J30")
    parser.add_argument("--episodes", type=int, default=5)
    parser.add_argument("--max-steps", type=int, default=720)
    parser.add_argument("--period", type=str, default=None,
                        choices=["peak", "offpeak", "evening"],
                        help="Fixed-Time 基线时段，默认按 --scenario 对齐")
    args = parser.parse_args()

    scenario_cfg = SCENARIO_CONFIG[args.scenario]["sumo_cfg"]
    default_period = {"real_peak": "peak", "real_offpeak": "offpeak", "real_evening": "evening"}.get(args.scenario, "offpeak")
    period = args.period or default_period

    intersections = [x.strip() for x in args.intersections.split(",") if x.strip()]
    model_stem = Path(args.model).stem
    save_dir = PROJECT_ROOT / "models" / "dqn"
    save_dir.mkdir(parents=True, exist_ok=True)

    dqn_action = make_dqn_action(args.model)
    strategies = [
        ("Random", random_action),
        (f"Fixed-Time({period})", None),
        ("Max-Pressure", max_pressure_action),
        (f"DQN({model_stem[:30]})", dqn_action),
    ]

    print(f"Scenario: {args.scenario}  period: {period}  episodes: {args.episodes}  max_steps: {args.max_steps}")
    print(f"Intersections: {intersections}")

    # junction 字典: {junction: {strategy: result}}
    all_results = {}
    for jid in intersections:
        print(f"\n===== {jid} =====", flush=True)
        ft_action, _ = make_real_fixed_time_action(jid, period)
        # 把真实定周期动作注入 strategies（按路口生成）
        local_strategies = [(name, act if act is not None else (ft_action if "Fixed" in name else act))
                            for name, act in strategies]
        all_results[jid] = {}
        for name, action_fn in local_strategies:
            t0 = time.time()
            result = run_strategy_with_metrics(
                name, action_fn,
                episodes=args.episodes,
                intersection_id=jid,
                max_steps=args.max_steps,
                delta_time=5,
                sumo_cfg_path=scenario_cfg,
            )
            dt = time.time() - t0
            print(f"  [{name}] reward={result['reward']['mean']:8.1f} | "
                  f"queue={result['queue_length']['mean']:6.1f} | wait={result['waiting_time']['mean']:7.1f}s | "
                  f"throughput={result['throughput']['mean']:6.1f} | stops={result['stop_count']['mean']:6.1f} | "
                  f"coll={result['collisions']['total']:.0f} | tel={result['teleports']['total']:.0f} | {dt:.0f}s", flush=True)
            all_results[jid][name] = result

    # ---- 保存（文件名含场景，避免同一模型换场景时互相覆盖）----
    json_path = save_dir / f"model_sweep_{model_stem}_{args.scenario}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n[SAVE] {json_path}")

    csv_path = save_dir / f"model_sweep_{model_stem}_{args.scenario}.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["junction", "strategy", "reward_mean", "reward_std",
                    "queue_mean", "waiting_time_mean", "travel_time_mean",
                    "throughput_mean", "fuel_mean", "co2_mean",
                    "stop_count_mean", "time_loss_mean", "collisions_total", "teleports_total"])
        for jid, sdict in all_results.items():
            for name, r in sdict.items():
                w.writerow([jid, name,
                            f"{r['reward']['mean']:.1f}", f"{r['reward']['std']:.1f}",
                            f"{r['queue_length']['mean']:.2f}", f"{r['waiting_time']['mean']:.2f}",
                            f"{r['travel_time']['mean']:.2f}", f"{r['throughput']['mean']:.2f}",
                            f"{r['fuel_consumption']['mean']:.2f}", f"{r['co2_emission']['mean']:.2f}",
                            f"{r['stop_count']['mean']:.2f}", f"{r['time_loss']['mean']:.2f}",
                            f"{r['collisions']['total']:.0f}", f"{r['teleports']['total']:.0f}"])
    print(f"[SAVE] {csv_path}")

    # ---- 汇总表 ----
    print("\n===== 汇总 (DQN vs Fixed-Time) =====")
    print(f"{'junction':<8} {'metric':<14} {'Fixed-Time':>12} {'DQN':>12} {'Δ%':>8}")
    for jid in intersections:
        ft = all_results[jid][f"Fixed-Time({period})"]
        dqn = all_results[jid][f"DQN({model_stem[:30]})"]
        for mkey, label in [("reward", "reward"), ("queue_length", "queue"),
                            ("waiting_time", "wait"), ("throughput", "throughput"),
                            ("stop_count", "stops"), ("time_loss", "time_loss"),
                            ("collisions", "collisions")]:
            fv = ft[mkey]["mean"] if isinstance(ft[mkey], dict) else ft[mkey]
            dv = dqn[mkey]["mean"] if isinstance(dqn[mkey], dict) else dqn[mkey]
            if isinstance(ft[mkey], dict) and "total" in ft[mkey]:
                fv, dv = ft[mkey]["total"], dqn[mkey]["total"]
            delta = (dv - fv) / abs(fv) * 100 if fv != 0 else float("nan")
            print(f"{jid:<8} {label:<14} {fv:>12.1f} {dv:>12.1f} {delta:>+7.1f}%")
        print()


if __name__ == "__main__":
    main()
