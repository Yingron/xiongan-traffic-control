"""测试SingleIntersectionEnv - 100步随机动作"""
import sys
import time
import numpy as np
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from env.single_intersection_env import SingleIntersectionEnv

def test_env():
    print("=" * 60)
    print("SingleIntersectionEnv - 100步随机动作测试")
    print("=" * 60)

    env = SingleIntersectionEnv(intersection_id="J01", max_steps=720, delta_time=5)
    print(f"Observation Space: {env.observation_space}")
    print(f"Action Space: {env.action_space}")
    print(f"Intersection: {env.intersection_id}")

    obs, info = env.reset(seed=42)
    print(f"Reset OK - obs shape: {obs.shape}")
    print(f"Info: time={info.get('time', 0):.1f}s, vehicles={info.get('vehicle_count', 0)}")

    rewards = []
    queue_lens = []
    actions_taken = []

    for step in range(100):
        action = env.action_space.sample()
        obs, reward, terminated, truncated, info = env.step(action)
        rewards.append(reward)
        queue_lens.append(info.get("queue_length", 0))
        actions_taken.append(action)

        if step % 20 == 0:
            t = info["time"]
            q = info["queue_length"]
            p = info["phase"]
            print(f"  Step {step:3d}: time={t:6.1f}s, action={action}, reward={reward:+.4f}, queue={q:.1f}, phase={p}")

    env.close()

    print(f"\n统计:")
    print(f"  总步数: {len(rewards)}")
    print(f"  平均奖励: {np.mean(rewards):.4f} +/- {np.std(rewards):.4f}")
    print(f"  奖励范围: [{np.min(rewards):.4f}, {np.max(rewards):.4f}]")
    print(f"  平均排队长度: {np.mean(queue_lens):.2f}")
    
    unique_actions, counts = np.unique(actions_taken, return_counts=True)
    dist = {int(a): int(c) for a, c in zip(unique_actions, counts)}
    print(f"  动作分布: {dist}")
    print(f"\n✅ 环境测试通过！")

if __name__ == "__main__":
    test_env()
