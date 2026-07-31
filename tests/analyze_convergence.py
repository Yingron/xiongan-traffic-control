"""生成50000步DQN训练曲线并进行收敛分析"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

log_dir = PROJECT_ROOT / "logs" / "dqn_J01"
save_dir = PROJECT_ROOT / "models" / "dqn"

csv_file = log_dir / "monitor.csv"
if not csv_file.exists():
    print(f"错误: 找不到训练日志: {csv_file}")
    sys.exit(1)

df = pd.read_csv(csv_file, skiprows=1)
print(f"数据行数: {len(df)}")

fig, axes = plt.subplots(2, 1, figsize=(14, 10), sharex=True)

axes[0].plot(df.index, df["r"], color="steelblue", linewidth=1.2, alpha=0.7, label="Episode Reward")

if len(df) >= 20:
    window = max(1, len(df) // 15)
    rolling_mean = df["r"].rolling(window=window, min_periods=1).mean()
    axes[0].plot(df.index, rolling_mean, color="red", linewidth=2.5,
                 label=f"Rolling Mean (window={window})")

first_5 = df["r"].head(5).mean()
last_5 = df["r"].tail(5).mean()
axes[0].axhline(y=first_5, color="gray", linestyle="--", alpha=0.5, label=f"First 5 mean: {first_5:.2f}")
axes[0].axhline(y=last_5, color="green", linestyle="--", alpha=0.5, label=f"Last 5 mean: {last_5:.2f}")

axes[0].set_ylabel("Episode Reward")
axes[0].set_title(f"DQN Training Convergence - J01 Intersection\n(50000 steps, {len(df)} episodes)")
axes[0].legend(loc="upper right", fontsize=9)
axes[0].grid(True, alpha=0.3)

if "l" in df.columns:
    axes[1].plot(df.index, df["l"], color="darkorange", linewidth=1, alpha=0.8)
    axes[1].set_ylabel("Episode Length (steps)")
    axes[1].set_xlabel("Episode Index")
    axes[1].grid(True, alpha=0.3)

plt.tight_layout()
chart_path = save_dir / "dqn_J01_50000steps_curve.png"
fig.savefig(chart_path, dpi=150, bbox_inches="tight")
plt.close()
print(f"训练曲线已保存: {chart_path}")

print(f"\n{'='*60}")
print("收敛分析:")
print(f"{'='*60}")
print(f"  总回合数: {len(df)}")
print(f"  初始奖励 (前5回合): {first_5:.4f}")
print(f"  最终奖励 (后5回合): {last_5:.4f}")
print(f"  提升幅度: {(last_5 - first_5):.4f} ({(last_5 - first_5)/abs(first_5)*100:.1f}%)")

last_10_std = df["r"].tail(10).std()
print(f"  后10回合标准差: {last_10_std:.4f}")

if last_10_std < 0.5:
    convergence = "✅ 已完全收敛 (std < 0.5)"
elif last_10_std < 2.0:
    convergence = "✅ 基本收敛 (std < 2.0)"
elif last_10_std < 5.0:
    convergence = "⚠️  接近收敛 (std < 5.0)"
else:
    convergence = "❌ 未收敛 (std >= 5.0)"
print(f"  收敛判断: {convergence}")

print(f"\n奖励统计:")
print(f"  最优: {df['r'].max():.4f}")
print(f"  最差: {df['r'].min():.4f}")
print(f"  总体均值: {df['r'].mean():.4f} ± {df['r'].std():.4f}")

improvement = (last_5 - first_5) / abs(first_5) * 100
print(f"\n📈 结论: 模型训练{convergence.split('(')[0].strip()}，奖励提升 {improvement:.1f}%")
