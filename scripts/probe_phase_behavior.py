"""行为探针：单模型×单路口跑 1 episode，统计相位使用行为（请求 vs 应用、停留时长、违规）

用法:
    python scripts/probe_phase_behavior.py --model models/dqn/dqn_multi_shared_real_evening_perf_1000000steps.zip \
        --scenario real_offpeak --intersections J01,J05,J10,J30 --max-steps 720
注意：offpeak 专用模型已归档（failed_v1/v2），offpeak 场景正式模型为 evening 泛化。
"""
import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from env.single_intersection_env import SingleIntersectionEnv
from evaluation.evaluate_all_strategies import make_dqn_action
from training.config import SCENARIO_CONFIG


def probe(model_path: str, scenario: str, intersection: str, max_steps: int = 720) -> None:
    env = SingleIntersectionEnv(
        intersection_id=intersection,
        sumo_cfg_path=SCENARIO_CONFIG[scenario]["sumo_cfg"],
        max_steps=max_steps,
        delta_time=5,
    )
    obs, info = env.reset(seed=42)
    dqn_action = make_dqn_action(model_path)

    req_counter = Counter()       # 请求动作
    applied_counter = Counter()   # 实际应用相位（MIN_GREEN 抑制后）
    runs = []                     # 连续同相位的停留时长
    cur_phase, cur_start = None, 0
    suppressed = 0                # 请求被 MIN_GREEN 抑制次数
    phase_changes = 0

    done = False
    step = 0
    while not done:
        action = dqn_action(obs, env, step)
        phase_before = int(env._traci.trafficlight.getPhase(intersection))
        obs, reward, terminated, truncated, info = env.step(action)
        phase_after = int(env._traci.trafficlight.getPhase(intersection))
        req_counter[action] += 1
        applied_counter[phase_after] += 1
        if phase_after != phase_before:
            if cur_phase is not None:
                runs.append(step - cur_start)
            cur_phase, cur_start = phase_after, step
            phase_changes += 1
        elif action != phase_after:
            suppressed += 1
        step += 1
        done = terminated or truncated

    if cur_phase is not None:
        runs.append(step - cur_start)
    env.close()

    print(f"===== {intersection} (模板A/C/B) — {scenario} =====")
    print(f"  请求动作分布: {dict(sorted(req_counter.items()))}")
    print(f"  应用相位分布: {dict(sorted(applied_counter.items()))}")
    print(f"  相位切换次数: {phase_changes}  |  平均停留: {np.mean(runs):.1f} 步 (Max {max(runs)})  |  被抑制请求: {suppressed}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, required=True)
    parser.add_argument("--scenario", type=str, required=True, choices=list(SCENARIO_CONFIG.keys()))
    parser.add_argument("--intersections", type=str, default="J01,J05,J10,J30")
    parser.add_argument("--max-steps", type=int, default=720)
    args = parser.parse_args()
    for j in args.intersections.split(","):
        probe(args.model, args.scenario, j.strip(), args.max_steps)


if __name__ == "__main__":
    main()
