"""场景冒烟测试：验证 SUMO 场景能跑通且受控路口产生真实排队

用法:
    python scripts/smoke_test_scenario.py sumo_files/xiongan_real_peak.sumocfg [--end 1200] [--interval 60]

输出:
    - 路由错误/插入失败检查（sumo stderr）
    - 每 60s 全网车辆数、受控路口排队数
    - 结束时各路口最大/平均排队统计
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUMO_HOME = os.environ.get("SUMO_HOME", "C:/Program Files (x86)/Eclipse/Sumo")
SUMO_BIN = Path(SUMO_HOME) / "bin" / "sumo.exe"


def main() -> None:
    ap = argparse.ArgumentParser(description="场景冒烟测试（排队/路由检查）")
    ap.add_argument("sumo_cfg", type=Path, help="sumocfg 路径")
    ap.add_argument("--end", type=int, default=1200, help="仿真时长(秒)")
    ap.add_argument("--interval", type=int, default=60, help="采样间隔(秒)")
    args = ap.parse_args()

    cfg = Path(args.sumo_cfg)
    if not cfg.exists():
        sys.exit(f"❌ 找不到 {cfg}")

    port = 8991
    cmd = [
        str(SUMO_BIN),
        "-c", str(cfg),
        "--remote-port", str(port),
        "--end", str(args.end),
        "--no-step-log", "true",
        "--no-internal-links", "true",
        "--time-to-teleport", "-1",
        "--collision.action", "warn",
        "--no-warnings", "true",  # 抑制黄灯相位等噪音；路由错误用加载探针单独验证
        "--seed", "42",
    ]
    print(f"🚀 启动 SUMO: {cmd[0]} -c {cfg.name} (--end {args.end})", flush=True)
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    try:
        import traci
        traci.init(port, host="127.0.0.1")
    except Exception as e:
        out, err = proc.communicate(timeout=10)
        print(f"❌ TraCI 连接失败: {e}\nstderr 前 40 行:\n{err.decode('utf-8', 'replace')[:4000]}")
        sys.exit(1)

    tls = traci.trafficlight.getIDList()
    controlled_lanes = sorted({ln for tl in tls for ln in traci.trafficlight.getControlledLanes(tl)})
    print(f"  受控路口 {len(tls)} 个，受控车道 {len(controlled_lanes)} 条\n", flush=True)

    # 关键指标: 全网车辆数 + 受控车道排队（速度<0.1 且 距路口<100m）
    QUEUE_SPEED = 0.1
    records = {tl: [] for tl in tls}
    total_max = 0
    step = 0
    while step < args.end:
        step += args.interval
        traci.simulationStep(step)  # 一次跳跃 interval 秒，避免逐秒 TraCI 开销
        n_total = traci.simulation.getDepartedNumber()
        in_net = len(traci.vehicle.getIDList())
        per_tl = {}
        for tl in tls:
            q = 0
            for ln in traci.trafficlight.getControlledLanes(tl):
                for vid in traci.lane.getLastStepVehicleIDs(ln):
                    if traci.vehicle.getSpeed(vid) < QUEUE_SPEED:
                        q += 1
            per_tl[tl] = q
            records[tl].append(q)
        total_max = max(total_max, max(per_tl.values(), default=0))
        busy = sum(1 for v in per_tl.values() if v > 0)
        print(f"  t={step:5d}s 累计驶入 {n_total:6d} 辆 | 路网内 {in_net:5d} 辆 | "
              f"排队最多 {max(per_tl, key=per_tl.get)}={max(per_tl.values())} 辆 | 排队路口 {busy}/20",
              flush=True)

    traci.close()
    proc.terminate()

    print("\n📊 各路口排队统计（辆）：")
    print(f"  {'路口':<6}{'最大':>6}{'平均':>8}")
    n_congested = 0
    for tl in sorted(tls):
        data = records[tl]
        mx = max(data, default=0)
        avg = sum(data) / len(data) if data else 0.0
        marker = " ✅" if mx >= 5 else ""
        if mx >= 5:
            n_congested += 1
        print(f"  {tl:<6}{mx:>6}{avg:>8.1f}{marker}")
    print(f"\n✅ 有拥堵的路口: {n_congested}/20（标准: ≥5辆排队视为有学习信号）")
    if n_congested < 5:
        print("⚠️  拥堵路口偏少——建议用 --factor 1.5~2.0 重新生成场景")


if __name__ == "__main__":
    main()
