"""Q 值发散监控：周期性扫描 checkpoints 目录，对全 1 掩码测量原始 Q 量级

用法:
    python scripts/monitor_q_values.py --pattern "dqn_multi_shared_real_evening_perf_*_steps.zip" --interval 600

健康范围：|Q|max 约几百~几千；超过 --threshold（默认 5000）即预警（对应既往发散事故的量级）。
注意：掩码固定为全 1，避免 MASK_FILL(-3e38) 污染测量。
"""
import argparse
import glob
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import torch as th


def measure_q_magnitude(model_path: str, obs_dim: int = 26) -> float:
    from stable_baselines3 import DQN
    m = DQN.load(str(model_path))
    with th.no_grad():
        q = m.policy.q_net(
            th.cat([th.randn(64, obs_dim - 4), th.ones(64, 4)], dim=1)
        ).cpu().numpy()
    return float(np.abs(q).max()), float(np.median(q))


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--ckpt-dir", type=str, default="models/dqn/checkpoints")
    parser.add_argument("--pattern", type=str, required=True)
    parser.add_argument("--interval", type=int, default=600)
    parser.add_argument("--threshold", type=float, default=5000.0)
    args = parser.parse_args()

    ckpt_dir = Path(args.ckpt_dir)
    last_file = None
    while True:
        try:
            fs = sorted(glob.glob(str(ckpt_dir / args.pattern)), key=os.path.getmtime)
            if fs and fs[-1] != last_file:
                last_file = fs[-1]
                qmax, qmed = measure_q_magnitude(last_file)
                flag = "  <<< Q 发散预警" if qmax > args.threshold else ""
                print(f"[{time.strftime('%H:%M:%S')}] {os.path.basename(last_file)}  |Q|max={qmax:.1f}  Qmedian={qmed:.1f}{flag}", flush=True)
        except Exception as e:  # 训练中途 checkpoint 可能正被写入
            print(f"[monitor] 读取失败(跳过): {e}", flush=True)
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
