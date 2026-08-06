"""生成DQN训练曲线"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

log_dir = PROJECT_ROOT / "logs" / "dqn_J01"
save_dir = PROJECT_ROOT / "models" / "dqn"

csv_file = log_dir / "monitor.csv"

if not csv_file.exists():
    print(f"错误: 找不到训练日志文件: {csv_file}")
    sys.exit(1)

df = pd.read_csv(csv_file, skiprows=1)
print(f"日志列: {list(df.columns)}")
print(f"数据行数: {len(df)}")

fig, axes = plt.subplots(2, 1, figsize=(12, 10), sharex=True)

axes[0].plot(df.index, df["r"], color="steelblue", linewidth=1.5, alpha=0.8)
axes[0].set_ylabel("Episode Reward")
axes[0].set_title("DQN Training - J01 Intersection (5000 steps)")
axes[0].grid(True, alpha=0.3)

window = max(1, len(df) // 10)
if len(df) >= window:
    rolling_mean = df["r"].rolling(window=window, min_periods=1).mean()
    axes[0].plot(df.index, rolling_mean, color="red", linewidth=2, 
                 label=f"Rolling Mean (window={window})")
    axes[0].legend()

if "l" in df.columns:
    axes[1].plot(df.index, df["l"], color="darkorange", linewidth=1, alpha=0.8)
    axes[1].set_ylabel("Episode Length (steps)")
    axes[1].set_xlabel("Episode Index")
    axes[1].grid(True, alpha=0.3)

plt.tight_layout()
chart_path = save_dir / "dqn_J01_5000steps_curve.png"
fig.savefig(chart_path, dpi=150, bbox_inches="tight")
plt.close()
print(f"训练曲线已保存: {chart_path}")

print(f"\n训练统计:")
print(f"  总回合数: {len(df)}")
print(f"  初始奖励 (前5回合平均): {df['r'].head(5).mean():.2f}")
print(f"  最终奖励 (后5回合平均): {df['r'].tail(5).mean():.2f}")
print(f"  最佳回合奖励: {df['r'].max():.2f}")
print(f"  最差回合奖励: {df['r'].min():.2f}")
print(f"  总体平均值: {df['r'].mean():.2f}")
