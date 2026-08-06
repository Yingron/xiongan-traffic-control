"""3场景（早高峰/晚高峰/平峰）DQN参数共享大规模训练脚本

每个场景训练 500,000 steps 参数共享DQN模型。
默认使用 --perf 高性能模式（目标200+ steps/s）和 --multi 参数共享。

用法:
    # 仅基准测试（每个场景5000步，快速验证速度）
    python training/run_3scenario_training.py --benchmark

    # 顺序执行3个场景各50万步
    python training/run_3scenario_training.py --order sequential

    # 单独启动平峰50万步（建议先跑平峰，收敛快作为起点）
    python training/run_3scenario_training.py --scenario flat

    # 单独启动早高峰50万步
    python training/run_3scenario_training.py --scenario morning

    # 后台启动（Windows PowerShell，输出重定向到文件）
    # Start-Process python -ArgumentList "training/run_3scenario_training.py --scenario flat" -RedirectStandardOutput "logs/flat_500k.log" -NoNewWindow
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from training.config import SCENARIO_CONFIG

# 3个核心场景
TARGET_SCENARIOS = ["flat", "morning", "evening"]
DEFAULT_STEPS = 500_000
BENCHMARK_STEPS = 5_000


def run_single_scenario(
    scenario: str,
    timesteps: int,
    perf: bool = True,
    multi: bool = True,
    extra_args: str = "",
) -> dict:
    """运行单个场景的训练

    Returns:
        dict: 训练结果统计
    """
    import subprocess

    if scenario not in SCENARIO_CONFIG:
        raise ValueError(f"未知场景 {scenario}. 可选: {list(SCENARIO_CONFIG.keys())}")

    label = SCENARIO_CONFIG[scenario]["label"]
    vehicles = SCENARIO_CONFIG[scenario].get("target_vehicles", "N/A")

    # 构建命令
    cmd = [
        sys.executable,
        "-u",  # 无缓冲输出
        str(PROJECT_ROOT / "training" / "train_dqn.py"),
        "--scenario", scenario,
        "--timesteps", str(timesteps),
    ]
    if perf:
        cmd.append("--perf")
    if multi:
        cmd.append("--multi")
    if extra_args:
        cmd.extend(extra_args.split())

    log_tag = f"{scenario}_{timesteps//1000}k"
    log_dir = PROJECT_ROOT / "logs" / "scenario_runs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{log_tag}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    print(f"\n{'='*72}")
    print(f" ▶ 启动场景训练: {label} ({scenario})")
    print(f"    目标车辆 : {vehicles}")
    print(f"    训练步数 : {timesteps:,}")
    print(f"    模式     : {'高性能' if perf else '标准'} | {'参数共享' if multi else '单路口'}")
    print(f"    日志文件 : {log_file.name}")
    print(f"    命令     : {' '.join(cmd)}")
    print(f"{'='*72}\n", flush=True)

    t0 = time.time()
    # 实时流式输出
    stats_json_path = None
    last_stats = {}
    try:
        process = subprocess.Popen(
            cmd,
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )

        with open(log_file, "w", encoding="utf-8") as log_fp:
            assert process.stdout is not None
            for line in process.stdout:
                print(line, end="", flush=True)
                log_fp.write(line)
                log_fp.flush()

                # 尝试解析保存的stats文件路径
                if "[SAVE] 统计信息已保存:" in line:
                    parts = line.strip().split(":", 1)
                    if len(parts) == 2:
                        stats_json_path = Path(parts[1].strip())
            process.wait()

        rc = process.returncode
        if rc != 0:
            print(f"\n[ERROR] 场景 {label} 训练异常退出 (exit code={rc})", flush=True)
    except KeyboardInterrupt:
        print(f"\n[WARN] 用户中断 {label} 训练", flush=True)
        try:
            process.terminate()
            process.wait(timeout=10)
        except Exception:
            pass

    elapsed = time.time() - t0

    # 尝试读取stats
    if stats_json_path and stats_json_path.exists():
        try:
            with open(stats_json_path, "r", encoding="utf-8") as f:
                last_stats = json.load(f)
        except Exception as e:
            print(f"[WARN] 读取stats失败: {e}")

    result = {
        "scenario": scenario,
        "label": label,
        "timesteps": timesteps,
        "elapsed_seconds_total": elapsed,
        "steps_per_second_total": timesteps / elapsed if elapsed > 0 else 0.0,
        "log_file": str(log_file),
        "exit_code": locals().get("rc", -1),
        "stats": last_stats,
    }
    return result


def format_hms(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def print_summary(results: list[dict]) -> None:
    """打印3场景汇总报告"""
    print("\n" + "=" * 72)
    print("  3场景大规模训练 - 汇总报告")
    print("=" * 72)
    header = f"| 场景   | 步数       | 耗时        | 速度(steps/s)  | 峰值速度   | 平均奖励   |"
    sep = "-" * len(header)
    print(sep)
    print(header)
    print(sep)

    total_elapsed = 0.0
    total_steps = 0
    for r in results:
        s = r.get("stats", {})
        speed = s.get("steps_per_second") or r.get("steps_per_second_total", 0)
        peak = s.get("peak_steps_per_second", 0)
        reward = s.get("mean_reward", 0)
        elapsed = r.get("elapsed_seconds_total", 0)
        total_elapsed += elapsed
        total_steps += r.get("timesteps", 0)
        t = r.get("timesteps", 0)
        print(
            f"| {r['label']:<5s} | {t:>10,} | {format_hms(elapsed):>10s} | {speed:>14.1f} | {peak:>10.1f} | {reward:>10.2f} |"
        )
    print(sep)
    avg_speed = total_steps / total_elapsed if total_elapsed > 0 else 0
    print(
        f"| 合计   | {total_steps:>10,} | {format_hms(total_elapsed):>10s} | {avg_speed:>14.1f} | -          | -          |"
    )
    print(sep)

    # 保存汇总JSON
    summary_path = PROJECT_ROOT / "models" / "dqn" / f"3scenario_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "generated_at": datetime.now().isoformat(),
                "target_steps_per_scenario": DEFAULT_STEPS,
                "total_steps": total_steps,
                "total_elapsed_seconds": total_elapsed,
                "average_steps_per_second": avg_speed,
                "results": results,
            },
            f,
            indent=2,
            ensure_ascii=False,
            default=str,
        )
    print(f"\n[SAVE] 汇总报告已保存: {summary_path}")
    print("=" * 72)


def main():
    parser = argparse.ArgumentParser(description="3场景 DQN 大规模训练调度器")
    parser.add_argument("--scenario", type=str, default=None,
                        choices=TARGET_SCENARIOS + ["low", "high"],
                        help="只跑单个场景（默认跑全部3个）")
    parser.add_argument("--order", type=str, default="sequential",
                        choices=["sequential"],
                        help="执行顺序（目前仅支持顺序，多开需手动开多个终端）")
    parser.add_argument("--steps", type=int, default=DEFAULT_STEPS,
                        help=f"每个场景的训练步数（默认 {DEFAULT_STEPS:,}）")
    parser.add_argument("--benchmark", action="store_true",
                        help=f"快速基准模式：每场景仅跑 {BENCHMARK_STEPS:,} 步，验证速度")
    parser.add_argument("--no-perf", action="store_true",
                        help="不使用高性能模式（用于对比）")
    parser.add_argument("--no-multi", action="store_true",
                        help="不使用参数共享（用于对比）")
    parser.add_argument("--extra", type=str, default="",
                        help="额外透传给train_dqn.py的参数，如 '--n-envs 2 --seed 123'")
    args = parser.parse_args()

    timesteps = BENCHMARK_STEPS if args.benchmark else args.steps
    perf = not args.no_perf
    multi = not args.no_multi

    scenarios = [args.scenario] if args.scenario else TARGET_SCENARIOS

    print("=" * 72)
    print("  雄安新区信号控制 - 3场景DQN大规模训练")
    print("=" * 72)
    print(f"  模式       : {'快速基准 (BENCHMARK)' if args.benchmark else '正式训练'}")
    print(f"  目标场景   : {', '.join(SCENARIO_CONFIG[s]['label'] for s in scenarios)}")
    print(f"  每场景步数 : {timesteps:,}")
    print(f"  总步数     : {timesteps * len(scenarios):,}")
    print(f"  高性能模式 : {'开启' if perf else '关闭'}")
    print(f"  参数共享   : {'开启' if multi else '关闭'}")
    if args.extra:
        print(f"  额外参数   : {args.extra}")

    # 估算时间
    est_speed_low, est_speed_high = (50, 80) if not perf else (150, 250)
    est_min = (timesteps * len(scenarios)) / est_speed_high
    est_max = (timesteps * len(scenarios)) / est_speed_low
    print(f"  预计时长   : {format_hms(est_min)} ~ {format_hms(est_max)} (基于{'200+' if perf else '60'} steps/s目标)")
    print("=" * 72)
    sys.stdout.flush()

    results: list[dict] = []
    t_start_all = time.time()

    for i, sc in enumerate(scenarios, 1):
        print(f"\n[进度] [{i}/{len(scenarios)}] 准备启动场景: {sc}")
        r = run_single_scenario(sc, timesteps, perf=perf, multi=multi, extra_args=args.extra)
        results.append(r)

        # 场景间暂停以释放SUMO句柄
        if i < len(scenarios):
            print(f"\n[INFO] 等待3秒清理资源后启动下一场景...", flush=True)
            time.sleep(3)

    elapsed_all = time.time() - t_start_all
    print(f"\n[INFO] 全部场景调度完成! 总墙钟耗时: {format_hms(elapsed_all)}")
    print_summary(results)


if __name__ == "__main__":
    main()
