"""四策略 × 30 路口 × 三场景 官方口径合并出表

数据源（全部同协议：SingleIntersectionEnv 单路口控制器、30 路口路网、
episodes=3、720 步×5s、SUMO 种子 42-44）：
1. models/dqn/3scenario_evaluation_report.json  官方 FT / DQN-Original（2026-08-19）
2. models/dqn/multi_metrics_4strategies.json    Random（本次补齐，MP 行按旧版弃用）
3. models/dqn/multi_metrics_mp4.json            Max-Pressure 四相位版（本次补齐）

官方口径（与 3scenario 官方表逐项复现一致）：
- 场景×策略 总量 = Σ_{30 路口} metric.mean
- 胜路口 = 该策略 reward.mean > Fixed-Time reward.mean 的路口数
- 碰撞 = Σ_{30 路口} collisions.total

产出：
- models/dqn/3scenario_4strategy_report.json / .csv  四策略逐路口全量（360 行）
- docs/四策略对比_20260909.md  汇总表（三场景 × 四策略）

用法:
    python evaluation/merge_4strategy_report.py
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

SAVE_DIR = PROJECT_ROOT / "models" / "dqn"
DOCS_DIR = PROJECT_ROOT / "docs"

OFFICIAL_JSON = SAVE_DIR / "3scenario_evaluation_report.json"
RANDOM_JSON = SAVE_DIR / "multi_metrics_4strategies.json"
MP4_JSON = SAVE_DIR / "multi_metrics_mp4.json"
OUT_JSON = SAVE_DIR / "3scenario_4strategy_report.json"
OUT_CSV = SAVE_DIR / "3scenario_4strategy_report.csv"
OUT_MD = DOCS_DIR / "四策略对比_20260909.md"
OUT_TOTALS = SAVE_DIR / "3scenario_4strategy_totals.json"

SCENARIO_ORDER = ["real_peak", "real_offpeak", "real_evening"]
SCENARIO_LABEL = {"real_peak": "真实早高峰", "real_offpeak": "真实平峰", "real_evening": "真实晚高峰"}
STRATEGY_ORDER = ["Fixed-Time", "DQN-Original", "Max-Pressure", "Random"]
STRATEGY_LABEL = {
    "Fixed-Time": "Fixed-Time",
    "DQN-Original": "共享掩码DQN",
    "Max-Pressure": "Max-Pressure(四相位)",
    "Random": "Random",
}
METRIC_NAMES = [
    "queue_length", "waiting_time", "travel_time", "throughput",
    "fuel_consumption", "co2_emission", "stop_count", "time_loss",
    "collisions", "teleports",
]


def load_rows(path: Path, keep_strategies: set[str] | None = None) -> list[dict]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    if keep_strategies:
        rows = [r for r in rows if r["strategy"] in keep_strategies]
    return rows


def build_report() -> dict:
    """构造 {scenario: {strategy: {junction: row}}} 索引并返回四策略全量行"""
    official = load_rows(OFFICIAL_JSON)
    random_rows = load_rows(RANDOM_JSON, keep_strategies={"Random"})
    mp4_rows = load_rows(MP4_JSON, keep_strategies={"Max-Pressure"})

    merged: dict[tuple[str, str], dict] = {}  # (scenario, strategy) -> {junction: row}
    for row in official + random_rows + mp4_rows:
        key = (row["scenario"], row["strategy"])
        merged.setdefault(key, {})[row["intersection"]] = row

    # 逐路口全量行（四策略 × 三场景 × 30 路口）
    all_rows = []
    missing = []
    for scen in SCENARIO_ORDER:
        for strat in STRATEGY_ORDER:
            by_junction = merged.get((scen, strat), {})
            for j in range(1, 31):
                jid = f"J{j:02d}"
                row = by_junction.get(jid)
                if row is None:
                    missing.append(f"{scen}|{strat}|{jid}")
                else:
                    all_rows.append(row)
    if missing:
        raise SystemExit(f"[FATAL] 缺失 {len(missing)} 组合（先跑 evaluate_four_strategies.py）:\n  " + "\n  ".join(missing[:20]))

    # 场景×策略汇总（官方口径：Σ mean）
    totals = {}
    for scen in SCENARIO_ORDER:
        totals[scen] = {}
        ft_rows = {r["intersection"]: r for r in all_rows
                   if r["scenario"] == scen and r["strategy"] == "Fixed-Time"}
        for strat in STRATEGY_ORDER:
            srows = [r for r in all_rows if r["scenario"] == scen and r["strategy"] == strat]
            agg = {"reward": sum(r["reward"]["mean"] for r in srows),
                   "wins": sum(1 for r in srows
                               if r["reward"]["mean"] > ft_rows[r["intersection"]]["reward"]["mean"])}
            # 注意顺序：collisions 必须用 Σ total（事件计数），不能用 mean 覆盖
            for m in METRIC_NAMES:
                agg[m] = sum(r[m]["total"] if m == "collisions" else r[m]["mean"] for r in srows)
            totals[scen][strat] = agg

    return {"all_rows": all_rows, "totals": totals}


def fmt_delta(v: float, base: float) -> str:
    if base == 0:
        return "-"
    return f"{100.0 * (v - base) / base:+.1f}%"


def fmt_thousands(x: float) -> str:
    return f"{x:,.0f}"


def write_outputs(rep: dict) -> None:
    all_rows, totals = rep["all_rows"], rep["totals"]

    # ---- JSON：全量 360 行 ----
    OUT_JSON.write_text(
        json.dumps(all_rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[SAVE] {OUT_JSON}（{len(all_rows)} 行）")

    # ---- CSV ----
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["scenario", "scenario_label", "intersection", "strategy"]
                   + [f"{m}_mean" for m in ["reward"] + METRIC_NAMES]
                   + [f"{m}_std" for m in ["reward"] + METRIC_NAMES])
        for r in all_rows:
            w.writerow([r["scenario"], r["scenario_label"], r["intersection"], r["strategy"]]
                       + [f"{r[m]['mean']:.6f}" for m in ["reward"] + METRIC_NAMES]
                       + [f"{r[m]['std']:.6f}" for m in ["reward"] + METRIC_NAMES])
    print(f"[SAVE] {OUT_CSV}")

    # ---- md 汇总 ----
    md = ["# 四策略 × 30 路口 × 三场景 汇总（2026-09-09 终版）", "",
          "> 协议：SingleIntersectionEnv 单路口控制器 + 30 路口路网（其余路口走默认信号程序），"
          "3 回合 × 720 步（种子 42–44），与官方 3scenario_evaluation_report.json 同构同口径。", ""]
    md.append("> 数据源：Fixed-Time / DQN-Original 复用 2026-08-19 官方行；"
              "Max-Pressure（四相位排队压力，含左转）与 Random 为 2026-09-09 同协议补齐。"
              "reward/waiting 聚合 = Σ 路口 mean（与官方一致）；胜路口 = reward.mean 高于 Fixed-Time 的路口数；碰撞 = Σ collisions.total。")
    md.append("> 复现：`python evaluation/evaluate_four_strategies.py`（MP/Random 补跑）+ `python evaluation/merge_4strategy_report.py`（出表）")
    md.append("")
    for scen in SCENARIO_ORDER:
        ft = totals[scen]["Fixed-Time"]
        md.append(f"## {SCENARIO_LABEL[scen]}（Fixed-Time 基线 reward={fmt_thousands(ft['reward'])}"
                  f" wait={fmt_thousands(ft['waiting_time'])}）")
        md.append("")
        md.append("| 策略 | reward 总量 | Δ% vs FT | waiting 总量 | Δ% vs FT | 通行量Δ% | 碰撞 | 胜路口/30 |")
        md.append("|---|---|---|---|---|---|---|---|")
        for strat in STRATEGY_ORDER:
            a = totals[scen][strat]
            tp_delta = fmt_delta(a["throughput"], ft["throughput"])
            md.append(f"| {STRATEGY_LABEL[strat]} | {fmt_thousands(a['reward'])} | "
                      f"{fmt_delta(a['reward'], ft['reward'])} | "
                      f"{fmt_thousands(a['waiting_time'])} | {fmt_delta(a['waiting_time'], ft['waiting_time'])} | "
                      f"{tp_delta} | {a['collisions']:.0f} | {a['wins']}/30 |")
        md.append("")
    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"[SAVE] {OUT_MD}")

    # ---- totals JSON（供 docx 回填 / 绘图脚本消费）----
    OUT_TOTALS.write_text(
        json.dumps(totals, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[SAVE] {OUT_TOTALS}")


def print_console(rep: dict) -> None:
    totals = rep["totals"]
    print("\n" + "=" * 78)
    print("四策略汇总（官方口径 Σmean）")
    print("=" * 78)
    for scen in SCENARIO_ORDER:
        ft = totals[scen]["Fixed-Time"]
        print(f"\n{SCENARIO_LABEL[scen]}  FT baseline reward={ft['reward']:.0f} wait={ft['waiting_time']:.0f}")
        for strat in STRATEGY_ORDER:
            a = totals[scen][strat]
            print(f"  {STRATEGY_LABEL[strat]:<18} reward={a['reward']:>9,.0f} "
                  f"({fmt_delta(a['reward'], ft['reward']):>7})  wait={a['waiting_time']:>11,.0f} "
                  f"({fmt_delta(a['waiting_time'], ft['waiting_time']):>7})  碰撞={a['collisions']:.0f}  胜={a['wins']}/30")


if __name__ == "__main__":
    rep = build_report()
    print_console(rep)
    write_outputs(rep)
    print("[DONE] 四策略报告已生成")
