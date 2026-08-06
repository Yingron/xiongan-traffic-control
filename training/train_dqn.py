"""DQN训练脚本 - 支持多场景 + 高性能模式（200+ steps/s）

使用 stable-baselines3 的 DQN 算法：
- 单路口22维状态 + 4离散动作
- 训练完成后模型可直接部署到20个路口
- 支持多场景（flat/morning/evening）
- 高性能模式：极简网络 + 大train_freq + 多SubprocVecEnv并行

用法:
    # 快速基准测试（5000步）
    python training/train_dqn.py --timesteps 5000 --perf

    # 平峰场景50万步训练
    python training/train_dqn.py --timesteps 500000 --scenario flat --perf --multi

    # 早高峰场景50万步训练
    python training/train_dqn.py --timesteps 500000 --scenario morning --perf --multi
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# Windows GBK encoding fix - reconfigure stdout to UTF-8
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from configs.constants import INTERSECTION_ORDER, SUMO_FILES_DIR
from training.config import PERF_DQN_CONFIG, SCENARIO_CONFIG


def make_env_factory(
    intersection_id: str = "J01",
    multi: bool = False,
    sumo_cfg_path: str | Path | None = None,
    max_steps: int = 720,
    delta_time: int = 5,
    rank: int = 0,
):
    """返回用于SubprocVecEnv的工厂函数"""
    def _init():
        from env.single_intersection_env import SingleIntersectionEnv, MultiIntersectionSharedEnv
        from stable_baselines3.common.monitor import Monitor

        if multi:
            env = MultiIntersectionSharedEnv(
                sumo_cfg_path=sumo_cfg_path,
                max_steps=max_steps,
                delta_time=delta_time,
                seed=rank,
            )
        else:
            env = SingleIntersectionEnv(
                intersection_id=intersection_id,
                sumo_cfg_path=sumo_cfg_path,
                max_steps=max_steps,
                delta_time=delta_time,
                seed=rank,
            )
        return env
    return _init


class SpeedMonitorCallback:
    """训练速度实时监控回调 - 每N步打印速度并flush"""

    def __init__(self, log_interval: int = 1000):
        self.log_interval = log_interval
        self.last_steps = 0
        self.last_time = time.time()
        self.start_time = time.time()
        self.speeds = []

    def on_step(self, model, total_steps: int) -> None:
        if total_steps - self.last_steps >= self.log_interval:
            now = time.time()
            dt = now - self.last_time
            ds = total_steps - self.last_steps
            inst_speed = ds / dt if dt > 0 else 0
            total_dt = now - self.start_time
            avg_speed = total_steps / total_dt if total_dt > 0 else 0
            self.speeds.append(inst_speed)
            msg = (
                f"[Step {total_steps:>8d}] "
                f"瞬时速度: {inst_speed:>7.1f} steps/s | "
                f"平均速度: {avg_speed:>7.1f} steps/s | "
                f"已耗时: {total_dt:>6.0f}s"
            )
            print(msg, flush=True)
            self.last_steps = total_steps
            self.last_time = now


def train_dqn(
    timesteps: int = 5000,
    intersection_id: str = "J01",
    multi: bool = False,
    scenario: str | None = None,
    perf: bool = False,
    learning_rate: float | None = None,
    buffer_size: int | None = None,
    batch_size: int | None = None,
    gamma: float = 0.99,
    exploration_fraction: float | None = None,
    seed: int = 42,
    save_dir: str = "models/dqn",
    net_arch: list | None = None,
    n_envs: int | None = None,
    log_interval: int = 1000,
) -> dict:
    """运行DQN训练

    Args:
        timesteps: 总训练步数
        intersection_id: 路口ID（单路口模式）
        multi: 是否使用多路口参数共享模式
        scenario: 场景 flat/morning/evening/low/high
        perf: 是否启用高性能模式（200+ steps/s 目标）
        learning_rate: 学习率（None则使用默认或高性能配置）
        buffer_size: 缓冲区大小
        batch_size: 批量大小
        gamma: 折扣因子
        exploration_fraction: 探索率衰减比例
        seed: 随机种子
        save_dir: 模型保存目录
        net_arch: 网络架构列表
        n_envs: 并行环境数（高性能模式默认=4）
        log_interval: 速度日志打印间隔（步）

    Returns:
        训练统计信息
    """
    import torch
    import torch.nn as nn
    from stable_baselines3 import DQN
    from stable_baselines3.common.monitor import Monitor

    # ========== 解析场景配置 ==========
    sumo_cfg_path = None
    scenario_label = "default"
    if scenario is not None:
        if scenario not in SCENARIO_CONFIG:
            raise ValueError(f"未知场景: {scenario}. 可选: {list(SCENARIO_CONFIG.keys())}")
        sumo_cfg_path = SCENARIO_CONFIG[scenario]["sumo_cfg"]
        scenario_label = scenario

    # ========== 应用高性能配置 ==========
    if perf:
        lr = learning_rate or PERF_DQN_CONFIG["learning_rate"]
        bs = batch_size or PERF_DQN_CONFIG["batch_size"]
        bf = buffer_size or PERF_DQN_CONFIG["buffer_size"]
        ls = PERF_DQN_CONFIG["learning_starts"]
        tf = PERF_DQN_CONFIG["train_freq"]
        gs = PERF_DQN_CONFIG["gradient_steps"]
        tui = PERF_DQN_CONFIG["target_update_interval"]
        ef = exploration_fraction or PERF_DQN_CONFIG["exploration_fraction"]
        efe = PERF_DQN_CONFIG["exploration_final_eps"]
        arch = net_arch or PERF_DQN_CONFIG["policy_kwargs"]["net_arch"]
        act_fn_name = PERF_DQN_CONFIG["policy_kwargs"]["activation_fn"]
        ne = n_envs or PERF_DQN_CONFIG["n_envs"]
        activation_fn = nn.ReLU if act_fn_name == "ReLU" else nn.Tanh
    else:
        lr = learning_rate or 1e-3
        bs = batch_size or 64
        bf = buffer_size or 10000
        ls = 100
        tf = 4
        gs = 1
        tui = 500
        ef = exploration_fraction or 0.3
        efe = 0.05
        arch = net_arch or [256, 256, 256]
        activation_fn = nn.Tanh
        ne = n_envs or 1

    # 设备优先CUDA，自动回退CPU
    device = "cuda" if torch.cuda.is_available() else "cpu"

    save_path = PROJECT_ROOT / save_dir
    save_path.mkdir(parents=True, exist_ok=True)

    env_name = "multi_shared" if multi else intersection_id
    perf_tag = "_perf" if perf else ""
    scenario_tag = f"_{scenario_label}" if scenario else ""

    log_dir = PROJECT_ROOT / "logs" / f"dqn_{env_name}{scenario_tag}{perf_tag}"
    log_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 68)
    print(" DQN训练 - 雄安新区20路口信号控制")
    print("=" * 68)
    print(f"  模式      : {'多路口参数共享' if multi else f'单路口({intersection_id})'}")
    print(f"  场景      : {SCENARIO_CONFIG.get(scenario, {}).get('label', scenario_label) if scenario else '默认'}")
    print(f"  高性能    : {'开启 (目标200+ steps/s)' if perf else '标准模式'}")
    print(f"  设备      : {device.upper()}")
    print(f"  并行环境  : {ne}")
    print(f"  总步数    : {timesteps:,}")
    print(f"  学习率    : {lr}")
    print(f"  网络架构  : {arch} ({activation_fn.__name__})")
    print(f"  批量大小  : {bs}  | train_freq={tf}  | gradient_steps={gs}")
    print(f"  缓冲区    : {bf:,}  | learning_starts={ls}")
    print(f"  探索策略  : initial=1.0 → final={efe} (fraction={ef})")
    print(f"  折扣因子  : {gamma}")
    print(f"  随机种子  : {seed}")
    print("=" * 68)
    sys.stdout.flush()

    # ========== 创建环境（支持SubprocVecEnv并行） ==========
    from stable_baselines3.common.env_util import make_vec_env

    if ne > 1 and perf:
        # 多进程并行环境（SubprocVecEnv）- 线性提速
        vec_env_cls = None
        try:
            from stable_baselines3.common.vec_env import SubprocVecEnv
            vec_env_cls = SubprocVecEnv
        except ImportError:
            vec_env_cls = None

        # Monitor包装工厂 - 确保每个worker都写monitor.csv
        # 注意：SubprocVecEnv下会自动创建worker_0, worker_1等子目录
        from stable_baselines3.common.vec_env import VecMonitor
        def _make_env_with_monitor(rank):
            _env = make_env_factory(
                intersection_id=intersection_id,
                multi=multi,
                sumo_cfg_path=sumo_cfg_path,
                max_steps=720,
                delta_time=5,
                rank=rank,
            )()
            return _env

        if vec_env_cls is not None:
            print(f"[INFO] 使用 SubprocVecEnv 启动 {ne} 个并行环境...", flush=True)
            env_fns = [lambda r=i: _make_env_with_monitor(r) for i in range(ne)]
            env = vec_env_cls(env_fns)
            # VecMonitor会汇总所有worker的episode，写入monitor.csv（带worker_前缀）
            env = VecMonitor(env, filename=str(log_dir / "monitor"))
            ne_used = ne
        else:
            print(f"[WARN] SubprocVecEnv不可用，回退单环境", flush=True)
            env = make_env_factory(intersection_id, multi, sumo_cfg_path, 720, 5, 0)()
            env = Monitor(env, str(log_dir))
            ne_used = 1
    else:
        print(f"[INFO] 单环境训练模式", flush=True)
        from env.single_intersection_env import SingleIntersectionEnv, MultiIntersectionSharedEnv

        if multi:
            env = MultiIntersectionSharedEnv(
                sumo_cfg_path=sumo_cfg_path, max_steps=720, delta_time=5, seed=seed
            )
        else:
            env = SingleIntersectionEnv(
                intersection_id=intersection_id,
                sumo_cfg_path=sumo_cfg_path,
                max_steps=720,
                delta_time=5,
                seed=seed,
            )
        env = Monitor(env, str(log_dir))
        ne_used = 1

    # ========== 构建DQN模型 ==========
    t_init_start = time.time()

    model = DQN(
        policy="MlpPolicy",
        env=env,
        learning_rate=lr,
        buffer_size=bf,
        learning_starts=ls,
        batch_size=bs,
        gamma=gamma,
        train_freq=tf,
        gradient_steps=gs,
        target_update_interval=tui,
        exploration_fraction=ef,
        exploration_final_eps=efe,
        exploration_initial_eps=1.0,
        max_grad_norm=10,
        device=device,
        verbose=0,  # 用我们自己的SpeedMonitorCallback替代
        seed=seed,
        tensorboard_log=str(log_dir),
        policy_kwargs=dict(
            net_arch=arch,
            activation_fn=activation_fn,
        ),
    )

    t_init = time.time() - t_init_start
    total_params = sum(p.numel() for p in model.policy.parameters())
    print(f"[INFO] 模型初始化完成: 参数量={total_params:,}, 耗时={t_init:.1f}s", flush=True)

    # ========== 开始训练 ==========
    print(f"\n{'='*68}")
    print(f" 开始训练: {timesteps:,} steps  (预计速度: {'200+' if perf else '~25'} steps/s)")
    print(f"{'='*68}\n", flush=True)

    speed_cb = SpeedMonitorCallback(log_interval=log_interval)
    t_start = time.time()

    # SB3 learn callback钩子
    from stable_baselines3.common.callbacks import BaseCallback

    class _SB3SpeedCallback(BaseCallback):
        def __init__(self, monitor: SpeedMonitorCallback):
            super().__init__(verbose=0)
            self.monitor = monitor

        def _on_step(self) -> bool:
            self.monitor.on_step(self.model, self.num_timesteps)
            return True

    try:
        model.learn(
            total_timesteps=timesteps,
            tb_log_name=f"dqn{perf_tag}",
            reset_num_timesteps=True,
            callback=_SB3SpeedCallback(speed_cb),
            log_interval=None,  # 禁用SB3自带日志
            progress_bar=False,
        )
    except KeyboardInterrupt:
        print("\n[WARN] 用户中断训练，保存当前模型...", flush=True)

    elapsed = time.time() - t_start
    speed = timesteps / elapsed if elapsed > 0 else 0

    print(f"\n{'='*68}")
    print(f" 训练完成!")
    print(f"  总耗时     : {elapsed:,.1f}s ({elapsed/3600:.2f}h)")
    print(f"  平均速度   : {speed:,.1f} steps/s")
    if speed_cb.speeds:
        print(f"  峰值速度   : {max(speed_cb.speeds):,.1f} steps/s")
        print(f"  后50%均速  : {np.mean(speed_cb.speeds[len(speed_cb.speeds)//2:]):,.1f} steps/s")
    print(f"{'='*68}")

    # ========== 保存模型 ==========
    model_filename = f"dqn_{env_name}{scenario_tag}{perf_tag}_{timesteps}steps"
    model_path = save_path / model_filename
    model.save(str(model_path))
    print(f"[SAVE] 模型已保存: {model_path}.zip")

    # ========== 评估模型 ==========
    try:
        stats = evaluate_model(model, env, episodes=5)
    except Exception as e:
        print(f"[WARN] 评估失败: {e}", flush=True)
        stats = {
            "episodes": 0,
            "mean_reward": 0.0,
            "std_reward": 0.0,
            "min_reward": 0.0,
            "max_reward": 0.0,
            "mean_steps": 0.0,
        }

    stats["model_path"] = str(model_path) + ".zip"
    stats["scenario"] = scenario_label
    stats["perf_mode"] = perf
    stats["elapsed_seconds"] = elapsed
    stats["steps_per_second"] = speed
    stats["peak_steps_per_second"] = max(speed_cb.speeds) if speed_cb.speeds else 0.0
    stats["params_count"] = total_params
    stats["n_envs"] = ne
    stats["timesteps"] = timesteps
    stats["net_arch"] = arch
    stats["batch_size"] = bs
    stats["train_freq"] = tf
    stats["learning_rate"] = lr
    stats["device"] = device

    stats_path = save_path / f"{model_filename}_stats.json"
    with open(stats_path, "w") as f:
        json.dump(stats, f, indent=2, default=str)
    print(f"[SAVE] 统计信息已保存: {stats_path}")

    # ========== 绘图 ==========
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        plot_training_curve(log_dir, save_path, f"{env_name}{scenario_tag}{perf_tag}", timesteps)
    except Exception as e:
        print(f"[WARN] 绘图跳过: {e}")

    # 关闭vec env
    try:
        env.close()
    except Exception:
        pass

    return stats


def evaluate_model(model, env, episodes: int = 5) -> dict:
    """评估模型 - 对VecEnv自动使用单env评估以兼容5-tuple接口"""
    print(f"\n评估模型 ({episodes} episodes)...")

    is_vec = hasattr(env, "num_envs")

    # VecEnv下创建一个单独的普通env进行评估（避免4-tuple vs 5-tuple差异）
    eval_env = env
    if is_vec:
        try:
            from env.single_intersection_env import SingleIntersectionEnv, MultiIntersectionSharedEnv
            from stable_baselines3.common.monitor import Monitor
            # 使用训练时的第一个子env的相同配置
            eval_env = MultiIntersectionSharedEnv(max_steps=720, delta_time=5)
            eval_env = Monitor(eval_env)
            _use_eval_env = True
        except Exception:
            _use_eval_env = False
    else:
        _use_eval_env = False

    rewards_list = []
    steps_list = []

    for ep in range(episodes):
        if _use_eval_env:
            obs, info = eval_env.reset()
            total_reward = 0.0
            done = False
            step_count = 0
            while not done:
                action, _ = model.predict(obs, deterministic=True)
                action = int(action)
                step_out = eval_env.step(action)
                if len(step_out) == 5:
                    obs, reward, terminated, truncated, info = step_out
                else:
                    obs, reward, terminated, info = step_out
                    truncated = False
                total_reward += float(reward)
                step_count += 1
                done = terminated or truncated
        elif is_vec:
            # VecEnv fallback: SB3 VecEnv step返回(obs, rew, done, info) 4-tuple
            obs = env.reset()
            total_reward = 0.0
            done = False
            step_count = 0
            while not done:
                action, _ = model.predict(obs, deterministic=True)
                step_out = env.step(action)
                if len(step_out) == 5:
                    obs, reward, terminated, truncated, info = step_out
                    done = bool(np.any(terminated) or np.any(truncated))
                else:
                    obs, reward, terminated, info = step_out
                    done = bool(np.any(terminated))
                total_reward += float(np.mean(reward)) if hasattr(reward, '__len__') else float(reward)
                step_count += 1
        else:
            obs, info = env.reset()
            total_reward = 0.0
            done = False
            step_count = 0
            while not done:
                action, _ = model.predict(obs, deterministic=True)
                action = int(action)
                step_out = env.step(action)
                if len(step_out) == 5:
                    obs, reward, terminated, truncated, info = step_out
                else:
                    obs, reward, terminated, info = step_out
                    truncated = False
                total_reward += reward
                step_count += 1
                done = terminated or truncated

        rewards_list.append(total_reward)
        steps_list.append(step_count)
        print(f"  Episode {ep + 1:>2d}: reward={total_reward:>10.4f}, steps={step_count}")

    if _use_eval_env:
        try:
            eval_env.close()
        except Exception:
            pass

    return {
        "episodes": episodes,
        "mean_reward": float(np.mean(rewards_list)),
        "std_reward": float(np.std(rewards_list)),
        "min_reward": float(np.min(rewards_list)),
        "max_reward": float(np.max(rewards_list)),
        "mean_steps": float(np.mean(steps_list)),
    }


def plot_training_curve(log_dir: Path, save_path: Path, env_name: str, timesteps: int):
    """绘制训练曲线"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import pandas as pd

    csv_file = log_dir / "monitor.csv"
    csv_candidates = []
    if csv_file.exists():
        csv_candidates.append(csv_file)
    # 递归搜索所有子目录（VecMonitor/Subproc会在worker_x、dqn_perf_x等嵌套目录下）
    # VecMonitor(filename="...") 会生成 ...monitor.csv，搜索 pattern *monitor.csv
    for pattern in ["monitor.csv", "*monitor.csv"]:
        for f in log_dir.rglob(pattern):
            if f.is_file() and f not in csv_candidates:
                csv_candidates.append(f)
    # 选择行数最多（数据最全）的monitor.csv
    best_csv = None
    best_rows = -1
    for candidate in csv_candidates:
        try:
            with open(candidate, "r", encoding="utf-8") as fh:
                rows = sum(1 for _ in fh)
            if rows > best_rows:
                best_rows = rows
                best_csv = candidate
        except Exception:
            pass
    if best_csv is None:
        print("  无训练数据可绘图")
        return
    csv_file = best_csv
    print(f"  读取训练日志: {csv_file} (rows≈{best_rows})")

    try:
        df = pd.read_csv(csv_file, skiprows=1)
        if len(df) == 0 or "r" not in df.columns:
            print("  无奖励数据可绘图")
            return

        df_valid = df[df["r"] < 0] if (df["r"] < 0).any() else df

        fig, axes = plt.subplots(2, 1, figsize=(12, 10), sharex=True)

        axes[0].plot(df_valid.index, df_valid["r"], color="steelblue", linewidth=1.0, alpha=0.6, label="Episode Reward")

        if len(df_valid) >= 10:
            window = max(1, len(df_valid) // 10)
            rolling_mean = df_valid["r"].rolling(window=window, min_periods=1).mean()
            axes[0].plot(df_valid.index, rolling_mean, color="red", linewidth=2,
                         label=f"Rolling Mean (window={window})")
        axes[0].set_ylabel("Episode Reward")
        axes[0].set_title(f"DQN Training - {env_name} ({timesteps:,} steps)")
        axes[0].legend()
        axes[0].grid(True, alpha=0.3)

        if "l" in df_valid.columns:
            axes[1].plot(df_valid.index, df_valid["l"], color="darkorange", linewidth=1, alpha=0.8)
            axes[1].set_ylabel("Episode Length (steps)")
            axes[1].set_xlabel("Episode Index")
            axes[1].grid(True, alpha=0.3)

        plt.tight_layout()
        chart_path = save_path / f"dqn_{env_name}_{timesteps}steps_curve.png"
        fig.savefig(chart_path, dpi=120, bbox_inches="tight")
        plt.close()
        print(f"训练曲线已保存: {chart_path}")
    except Exception as e:
        print(f"  绘图失败: {e}")
        import traceback
        traceback.print_exc()


def main():
    parser = argparse.ArgumentParser(description="DQN训练 - 雄安新区信号控制")
    parser.add_argument("--timesteps", type=int, default=5000, help="训练步数")
    parser.add_argument("--intersection", type=str, default="J01", help="路口ID (单路口模式)")
    parser.add_argument("--multi", action="store_true", help="多路口参数共享模式（推荐）")
    parser.add_argument("--scenario", type=str, default=None,
                        choices=["flat", "morning", "evening", "low", "high"],
                        help="训练场景: 平峰/早高峰/晚高峰/低峰/高峰")
    parser.add_argument("--perf", action="store_true",
                        help="高性能模式: 极简网络+大train_freq+4x并行 (目标200+ steps/s)")
    parser.add_argument("--lr", type=float, default=None, help="覆盖学习率")
    parser.add_argument("--batch-size", type=int, default=None, help="覆盖batch_size")
    parser.add_argument("--n-envs", type=int, default=None, help="覆盖并行环境数")
    parser.add_argument("--net-arch", type=str, default=None, help="网络架构，如 '64,64'")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    parser.add_argument("--save-dir", type=str, default="models/dqn", help="模型与评估结果保存目录")
    parser.add_argument("--log-interval", type=int, default=1000, help="速度日志间隔(步)")
    parser.add_argument("--eval-only", action="store_true", help="仅评估已有模型")
    parser.add_argument("--model-path", type=str, default=None, help="已有模型路径")
    args = parser.parse_args()

    net_arch = None
    if args.net_arch:
        net_arch = [int(x) for x in args.net_arch.split(",")]

    if args.eval_only:
        from stable_baselines3 import DQN
        if not args.model_path:
            print("错误: 请指定 --model-path")
            return
        model = DQN.load(args.model_path)
        from env.single_intersection_env import SingleIntersectionEnv
        sumo_cfg_path = None
        if args.scenario:
            sumo_cfg_path = SCENARIO_CONFIG[args.scenario]["sumo_cfg"]
        env = SingleIntersectionEnv(
            intersection_id=args.intersection,
            sumo_cfg_path=sumo_cfg_path,
        )
        stats = evaluate_model(model, env, episodes=10)
        print(f"\n评估结果:\n{json.dumps(stats, indent=2)}")
        return

    stats = train_dqn(
        timesteps=args.timesteps,
        intersection_id=args.intersection,
        multi=args.multi,
        scenario=args.scenario,
        perf=args.perf,
        learning_rate=args.lr,
        batch_size=args.batch_size,
        seed=args.seed,
        save_dir=args.save_dir,
        net_arch=net_arch,
        n_envs=args.n_envs,
        log_interval=args.log_interval,
    )

    print(f"\n{'='*68}")
    print(f" >>> 训练完成报告")
    print(f"{'='*68}")
    print(f"  场景       : {stats.get('scenario', '-')}")
    print(f"  模式       : {'高性能' if stats.get('perf_mode') else '标准'}")
    print(f"  设备       : {stats.get('device', '-')}")
    print(f"  平均奖励   : {stats['mean_reward']:.4f} ± {stats['std_reward']:.4f}")
    print(f"  奖励范围   : [{stats['min_reward']:.2f}, {stats['max_reward']:.2f}]")
    print(f"  平均步数   : {stats['mean_steps']:.1f}")
    print(f"  平均速度   : {stats.get('steps_per_second', 0):.1f} steps/s")
    print(f"  峰值速度   : {stats.get('peak_steps_per_second', 0):.1f} steps/s")
    print(f"  参数量     : {stats.get('params_count', 0):,}")
    print(f"  模型文件   : {stats['model_path']}")
    print(f"{'='*68}")


if __name__ == "__main__":
    main()
