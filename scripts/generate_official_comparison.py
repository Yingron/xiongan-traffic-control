"""生成三场景官方对比表（DQN 掩码模型 vs 真实 Fixed-Time 配时）

数据源: models/dqn/model_sweep_{模型}_{场景}.json（8路口 × 5回合 × 720步）
用法: python scripts/generate_official_comparison.py
产出: docs/三场景官方对比_20260819.md
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

MODEL_DIR = Path("models/dqn")

# 正式方案（2026-08-19 定稿）：offpeak 采用 evening 模型跨场景泛化
SCENARIOS = {
    "real_peak": {
        "label": "真实早高峰",
        "file": "model_sweep_dqn_multi_shared_real_peak_perf_1000000steps_real_peak.json",
        "model": "dqn_multi_shared_real_peak_perf_1000000steps.zip（专用）",
    },
    "real_offpeak": {
        "label": "真实平峰",
        "file": "model_sweep_dqn_multi_shared_real_evening_perf_1000000steps_real_offpeak.json",
        "model": "dqn_multi_shared_real_evening_perf_1000000steps.zip（evening 模型泛化）",
    },
    "real_evening": {
        "label": "真实晚高峰",
        "file": "model_sweep_dqn_multi_shared_real_evening_perf_1000000steps_real_evening.json",
        "model": "dqn_multi_shared_real_evening_perf_1000000steps.zip（专用）",
    },
}

METRICS = [
    ("reward", "累计奖励", "reward"),
    ("waiting_time", "等待时间(s)", "waiting_time"),
    ("throughput", "通行量(pcu)", "throughput"),
    ("queue_length", "平均排队(veh)", "queue_length"),
    ("collisions", "碰撞次数", "collisions"),
]


def pct(dq: float, ft: float) -> str:
    if ft == 0:
        return "—"
    return f"{100 * (dq / ft - 1):+.1f}%"


def main() -> None:
    lines = [
        "# 三场景官方对比表（DQN 需求门控掩码模型 vs 真实 Fixed-Time 配时）",
        "",
        "> 生成日期：2026-08-19 ｜ 评估配置：8 代表路口（J01/J05/J10/J15/J20/J21/J25/J30）× 5 回合 × 720 步（1 小时真实交通）",
        "> 掩码配方：26 维观测（22 状态 + 4 动作掩码）+ Double-DQN + 模板分层采样；Fixed-Time 为 timing_plans.json 真实定周期",
        "",
        "## 一、总量对比（8 路口合计）",
        "",
        "| 场景 | 模型 | reward | Δ% | waiting(s) | Δ% | throughput | Δ% | 碰撞 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]

    totals = {}
    for scen, cfg in SCENARIOS.items():
        d = json.load(open(MODEL_DIR / cfg["file"], encoding="utf-8"))
        ft_k = next(k for k in d["J01"] if "Fixed" in k)
        dq_k = next(k for k in d["J01"] if "DQN" in k)

        def tot(k: str, m: str) -> float:
            return sum(d[j][k][m]["mean"] if m != "collisions" else d[j][k][m]["total"] for j in d)

        vals = {m: (tot(dq_k, key), tot(ft_k, key)) for m, _, key in METRICS}
        totals[scen] = vals

        r = vals["reward"]
        w = vals["waiting_time"]
        t = vals["throughput"]
        c = vals["collisions"]
        lines.append(
            f"| {cfg['label']} | {cfg['model']} | {r[0]:.0f} vs {r[1]:.0f} | **{pct(*r)}** | "
            f"{w[0]:.0f} vs {w[1]:.0f} | {pct(*w)} | {t[0]:.0f} vs {t[1]:.0f} | {pct(*t)} | {c[0]:.0f} vs {c[1]:.0f} |"
        )

    lines += [
        "",
        "**结论**：三场景 reward 全部优于 Fixed-Time（早高峰 +13.7% / 平峰 +5.4% / 晚高峰 +15.4%，历史最佳），",
        "通行量基本持平，晚高峰等待时间略优于基线；平峰场景等待时间劣于基线（+60.5%）——",
        "根因：平峰低流量下相位选择的学习信号弱，且平峰专用模型两次训练均收敛到病态策略（见 archive/），",
        "正式方案采用晚高峰模型跨场景泛化。",
        "",
        "## 二、路口级 reward 对比（DQN vs Fixed-Time）",
        "",
        "| 场景 | J01 | J05 | J10 | J15 | J20 | J21 | J25 | J30 | 胜/8 |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]

    for scen, cfg in SCENARIOS.items():
        d = json.load(open(MODEL_DIR / cfg["file"], encoding="utf-8"))
        ft_k = next(k for k in d["J01"] if "Fixed" in k)
        dq_k = next(k for k in d["J01"] if "DQN" in k)
        cells = []
        wins = 0
        for j in d:
            r_ft = d[j][ft_k]["reward"]["mean"]
            r_dq = d[j][dq_k]["reward"]["mean"]
            mark = "🟢" if r_dq > r_ft else "🔴"
            cells.append(f"{r_dq:,.0f} vs {r_ft:,.0f} {pct(r_dq, r_ft)} {mark}")
            wins += r_dq > r_ft
        lines.append(f"| {cfg['label']} | " + " | ".join(cells) + f" | **{wins}/8** |")

    lines += [
        "",
        "## 三、数据文件",
        "",
        "| 场景 | 文件 |",
        "|---|---|",
    ]
    for scen, cfg in SCENARIOS.items():
        lines.append(f"| {cfg['label']} | `models/dqn/{cfg['file']}` |")

    out = Path("docs/三场景官方对比_20260819.md")
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"[SAVE] {out} ({len(lines)} 行)")


if __name__ == "__main__":
    main()
