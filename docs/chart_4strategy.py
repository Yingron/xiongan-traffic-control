#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""图3-14 四策略 × 30路口 × 三场景 全量对比图（读 merge_4strategy_report 的 totals JSON）

用法:
    python docs/chart_4strategy.py
产出:
    docs/charts/fig3_14_four_strategies.png
"""
import json
import os
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['figure.dpi'] = 150

ROOT = Path(__file__).resolve().parent.parent
TOTALS_JSON = ROOT / "models" / "dqn" / "3scenario_4strategy_totals.json"
OUT_PNG = Path(__file__).resolve().parent / "charts" / "fig3_14_four_strategies.png"

SCEN = ["real_peak", "real_offpeak", "real_evening"]
SCEN_LABEL = {"real_peak": "早高峰", "real_offpeak": "平峰", "real_evening": "晚高峰"}
STRATS = ["Fixed-Time", "DQN-Original", "Max-Pressure", "Random"]
STRAT_LABEL = {"Fixed-Time": "Fixed-Time", "DQN-Original": "共享掩码DQN",
               "Max-Pressure": "Max-Pressure", "Random": "Random"}
COLORS = {"Fixed-Time": "#F59E0B", "DQN-Original": "#3B82F6",
          "Max-Pressure": "#EF4444", "Random": "#8B5CF6"}


def main():
    totals = json.loads(TOTALS_JSON.read_text(encoding="utf-8"))
    x = np.arange(len(SCEN))
    width = 0.2

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10.5, 8),
                                   gridspec_kw={'height_ratios': [1.35, 1]})
    fig.suptitle('四策略 × 30路口 × 三场景 全量对比（3回合×720步×5s，种子42–44）',
                 fontsize=13, fontweight='bold')

    # ---- 上：reward 总量（Σ路口 mean）----
    for i, s in enumerate(STRATS):
        vals = [totals[sc][s]["reward"] for sc in SCEN]
        bars = ax1.bar(x + (i - 1.5) * width, vals, width,
                       label=STRAT_LABEL[s], color=COLORS[s], edgecolor='white', lw=0.3)
        for b, v in zip(bars, vals):
            ax1.text(b.get_x() + b.get_width() / 2, b.get_height() + 800,
                     f"{v:,.0f}", ha='center', va='bottom', fontsize=7)
    ax1.set_xticks(x)
    ax1.set_xticklabels([SCEN_LABEL[s] for s in SCEN])
    ax1.set_ylabel('reward 总量（Σ路口 mean）')
    ax1.set_title('reward 总量对比', fontsize=11)
    ax1.legend(loc='lower right', fontsize=9, ncol=2)
    ax1.grid(axis='y', alpha=0.3)

    # ---- 下：waiting 总量（Σ路口 mean，对数轴）----
    for i, s in enumerate(STRATS):
        vals = [totals[sc][s]["waiting_time"] for sc in SCEN]
        bars = ax2.bar(x + (i - 1.5) * width, vals, width,
                       label=STRAT_LABEL[s], color=COLORS[s], edgecolor='white', lw=0.3)
        for b, v in zip(bars, vals):
            ax2.text(b.get_x() + b.get_width() / 2, b.get_height() * 1.06,
                     f"{v:,.0f}", ha='center', va='bottom', fontsize=7)
    ax2.set_xticks(x)
    ax2.set_xticklabels([SCEN_LABEL[s] for s in SCEN])
    ax2.set_yscale('log')
    ax2.set_ylabel('waiting 总量（s，对数轴）')
    ax2.set_title('waiting 总量对比（Max-Pressure 数量级过大，采用对数轴）', fontsize=11)
    ax2.grid(axis='y', alpha=0.3, which='both')

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(OUT_PNG, bbox_inches='tight')
    plt.close()
    print(f"[SAVE] {OUT_PNG}")


if __name__ == "__main__":
    main()
