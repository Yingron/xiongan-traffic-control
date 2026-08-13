"""全路网部署性能测试

同时控制30个交叉口，评估路网级性能指标

用法:
    python tests/full_network_deployment.py
"""
import sys
import json
import time
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from configs.constants import INTERSECTION_ORDER, SUMO_FILES_DIR


def run_full_network_with_dqn(model_path: str, episodes: int = 3):
    """全路网部署测试：同时控制30个路口"""
    from stable_baselines3 import DQN
    import traci

    if not Path(model_path).exists():
        print(f"错误: 模型不存在: {model_path}")
        return None

    print(f"加载模型: {model_path}")
    model = DQN.load(model_path)

    results = []
    total_start = time.time()

    for ep in range(episodes):
        print(f"\n{'='*60}")
        print(f"Episode {ep + 1}/{episodes}")
        print(f"{'='*60}")

        sumo_cfg = str(SUMO_FILES_DIR / "xiongan.sumocfg")
        cmd = ["sumo", "-c", sumo_cfg, "--no-step-log", "--seed", str(42 + ep)]

        traci.start(cmd, numRetries=1)

        sim_time = 0.0
        max_time = 720.0
        delta_time = 5.0
        step_count = 0

        intersection_rewards = {tl_id: 0.0 for tl_id in INTERSECTION_ORDER}
        intersection_phases = {tl_id: 0 for tl_id in INTERSECTION_ORDER}

        print("开始仿真...")

        while sim_time < max_time:
            for tl_id in INTERSECTION_ORDER:
                state = extract_state_for_intersection(traci, tl_id)

                action, _ = model.predict(state, deterministic=True)
                action = int(action)

                current_phase = traci.trafficlight.getPhase(tl_id)
                if action != current_phase:
                    traci.trafficlight.setPhase(tl_id, action)
                intersection_phases[tl_id] = action

            for _ in range(int(delta_time)):
                traci.simulationStep()

            for tl_id in INTERSECTION_ORDER:
                reward = compute_intersection_reward(traci, tl_id, intersection_phases[tl_id])
                intersection_rewards[tl_id] += reward

            sim_time += delta_time
            step_count += 1

            if step_count % 20 == 0:
                total_queue = sum(get_queue_length(traci, tl_id) for tl_id in INTERSECTION_ORDER)
                print(f"  Time: {sim_time:.0f}s, Total Queue: {total_queue}", flush=True)

        total_vehicles = len(traci.vehicle.getIDList())
        total_queue_end = sum(get_queue_length(traci, tl_id) for tl_id in INTERSECTION_ORDER)

        ep_result = {
            "episode": ep + 1,
            "total_vehicles": total_vehicles,
            "total_queue_end": total_queue_end,
            "intersection_rewards": intersection_rewards,
            "total_reward": sum(intersection_rewards.values()),
            "mean_reward_per_intersection": np.mean(list(intersection_rewards.values())),
        }
        results.append(ep_result)

        print(f"\n  总车辆: {total_vehicles}")
        print(f"  最终总排队: {total_queue_end}")
        print(f"  总奖励: {ep_result['total_reward']:.4f}")
        print(f"  平均路口奖励: {ep_result['mean_reward_per_intersection']:.4f}")

        traci.close()

    total_elapsed = time.time() - total_start

    summary = {
        "episodes": episodes,
        "elapsed_seconds": total_elapsed,
        "mean_total_reward": float(np.mean([r["total_reward"] for r in results])),
        "std_total_reward": float(np.std([r["total_reward"] for r in results])),
        "mean_reward_per_intersection": float(np.mean([r["mean_reward_per_intersection"] for r in results])),
        "mean_queue_end": float(np.mean([r["total_queue_end"] for r in results])),
        "per_episode_results": results,
    }

    print(f"\n{'='*60}")
    print("全路网部署测试汇总:")
    print(f"{'='*60}")
    print(f"  总回合数: {episodes}")
    print(f"  总耗时: {total_elapsed:.1f}s")
    print(f"  平均总奖励: {summary['mean_total_reward']:.4f} ± {summary['std_total_reward']:.4f}")
    print(f"  平均路口奖励: {summary['mean_reward_per_intersection']:.4f}")
    print(f"  平均最终排队: {summary['mean_queue_end']:.1f}")

    return summary


def extract_state_for_intersection(traci, tl_id: str) -> np.ndarray:
    """提取单个路口的状态"""
    from env.global_state import _extract_intersection_state
    return _extract_intersection_state(traci, tl_id)


def compute_intersection_reward(traci, tl_id: str, phase: int) -> float:
    """计算单个路口的奖励"""
    state = extract_state_for_intersection(traci, tl_id)
    queue_length = state[0:4].sum()
    waiting_time = state[4:8].sum()
    throughput = state[16:20].sum()

    reward = -0.1 * queue_length - 0.01 * waiting_time + 0.5 * throughput
    return float(reward)


def get_queue_length(traci, tl_id: str) -> int:
    """获取路口排队长度"""
    try:
        lanes = traci.trafficlight.getControlledLanes(tl_id)
        queue = 0
        for lane in set(lanes):
            queue += traci.lane.getLastStepHaltingNumber(lane)
        return queue
    except Exception:
        return 0


def main():
    model_path = PROJECT_ROOT / "models" / "dqn" / "dqn_multi_shared_100000steps.zip"

    if not model_path.exists():
        print(f"错误: 模型不存在: {model_path}")
        print("请先完成 Phase 3.1 训练")
        return

    results = run_full_network_with_dqn(str(model_path), episodes=3)

    if results:
        save_path = PROJECT_ROOT / "models" / "dqn" / "full_network_deployment.json"
        with open(save_path, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n结果已保存: {save_path}")


if __name__ == "__main__":
    main()
