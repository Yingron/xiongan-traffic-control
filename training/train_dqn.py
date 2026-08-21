"""DQN训练脚本 - 支持多场景 + 高性能模式（200+ steps/s）

使用 stable-baselines3 的 DQN 算法：
- 单路口22维状态 + 4离散动作
- 训练完成后模型可直接部署到30个路口
- 支持多场景（real_peak/real_offpeak/real_evening）
- 高性能模式：极简网络 + 大train_freq + 多SubprocVecEnv并行

路口ID支持两种格式:
  - 规范格式: J01 ~ J30
  - 友好格式: intersection_1 ~ intersection_30 (自动映射)

用法:
    # 快速基准测试（5000步）
    python training/train_dqn.py --timesteps 5000 --perf

    # 真实早高峰场景50万步训练
    python training/train_dqn.py --timesteps 500000 --scenario real_peak --perf --multi

    # 真实晚高峰场景50万步训练
    python training/train_dqn.py --timesteps 500000 --scenario real_evening --perf --multi
"""
from __future__ import annotations

import argparse
import gc
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
from training.config import PERF_DQN_CONFIG, ANTICOLLAPSE_DQN_CONFIG, SCENARIO_CONFIG


def resolve_intersection_id(raw_id: str) -> str:
    """将友好名称映射为规范路口ID

    支持格式:
      - J01, J02, ... J30 (直接通过)
      - intersection_1, intersection_2, ... intersection_30
      - intersection1, intersection2, ... (无下划线)
      - 数字: 1, 2, ... 30
    """
    if raw_id in INTERSECTION_ORDER:
        return raw_id
    stripped = raw_id.strip().lower()
    for prefix in ("intersection_", "intersection", "int_", "int"):
        if stripped.startswith(prefix):
            num_part = stripped[len(prefix):]
            try:
                idx = int(num_part)
                if 1 <= idx <= 30:
                    return f"J{idx:02d}"
            except ValueError:
                pass
    try:
        idx = int(stripped)
        if 1 <= idx <= 30:
            return f"J{idx:02d}"
    except ValueError:
        pass
    return raw_id


def make_env_factory(
    intersection_id: str = "J01",
    multi: bool = False,
    sumo_cfg_path: str | Path | None = None,
    max_steps: int = 720,
    delta_time: int = 5,
    rank: int = 0,
    restart_every: int = 50,
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
                rank=rank,
                restart_every=restart_every,
            )
        else:
            env = SingleIntersectionEnv(
                intersection_id=intersection_id,
                sumo_cfg_path=sumo_cfg_path,
                max_steps=max_steps,
                delta_time=delta_time,
                seed=rank,
                rank=rank,
                restart_every=restart_every,
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


class PolicyCollapseMonitorCallback:
    """策略坍缩监控回调 - 检测并警告策略坍缩

    监控指标:
    1. 动作分布（预测动作中各相位的频率）
    2. 最近N步的平均奖励趋势
    3. 探索率变化
    """

    def __init__(self, check_interval: int = 500, window_size: int = 100):
        self.check_interval = check_interval
        self.window_size = window_size
        self.last_check_steps = 0
        self.action_counts = [0, 0, 0, 0]
        self.recent_rewards = []
        self.collapse_warnings = 0
        self.action_distribution_log = []

    def on_step(self, model, total_steps: int, env=None) -> None:
        if total_steps - self.last_check_steps < self.check_interval:
            return

        self.last_check_steps = total_steps

        if hasattr(model, 'policy') and hasattr(model.policy, 'action_noise'):
            eps = getattr(model.policy, 'exploration_rate', None)
        else:
            eps = None

        action_probs = self._estimate_action_distribution(model)

        dominant_action = np.argmax(action_probs)
        dominant_pct = action_probs[dominant_action]

        if dominant_pct > 0.9:
            self.collapse_warnings += 1
            print(
                f"[COLLAPSE-WARN #{self.collapse_warnings}] Step {total_steps}: "
                f"动作分布极度倾斜! Action {dominant_action}占 {dominant_pct:.1%} "
                f"(分布: {[f'{p:.1%}' for p in action_probs]}, eps={eps})",
                flush=True,
            )
        elif dominant_pct > 0.75:
            print(
                f"[COLLAPSE-WATCH] Step {total_steps}: "
                f"动作分布有偏斜倾向: Action {dominant_action}占 {dominant_pct:.1%} "
                f"(分布: {[f'{p:.1%}' for p in action_probs]}, eps={eps})",
                flush=True,
            )

        if len(self.recent_rewards) >= self.window_size:
            recent_avg = np.mean(self.recent_rewards[-self.window_size:])
            if abs(recent_avg) < 0.01:
                print(
                    f"[REWARD-WARN] Step {total_steps}: "
                    f"最近{self.window_size}步平均奖励={recent_avg:.4f}，"
                    f"奖励接近0可能意味着策略无实质学习",
                    flush=True,
                )

    def _estimate_action_distribution(self, model, n_samples: int = 50) -> np.ndarray:
        """通过采样估计动作分布"""
        try:
            action_counts = np.zeros(4)
            for _ in range(n_samples):
                dummy_obs = np.random.randn(1, *model.observation_space.shape).astype(np.float32)
                action, _ = model.predict(dummy_obs, deterministic=False)
                action_counts[int(np.asarray(action).item())] += 1
            return action_counts / n_samples
        except Exception:
            return np.array([0.25, 0.25, 0.25, 0.25])


def train_dqn(
    timesteps: int = 5000,
    intersection_id: str = "J01",
    multi: bool = False,
    scenario: str | None = None,
    perf: bool = False,
    anti_collapse: bool = False,
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
    save_interval: int = 50000,
    resume_path: str | None = None,
) -> dict:
    """运行DQN训练

    Args:
        timesteps: 本次运行的训练步数（继续训练时为增量步数）
        intersection_id: 路口ID（单路口模式）
        multi: 是否使用多路口参数共享模式
        scenario: 场景 real_peak/real_offpeak/real_evening（30路口真实需求，见 SCENARIO_CONFIG）
        perf: 是否启用高性能模式（200+ steps/s 目标）
        anti_collapse: 是否启用抗策略坍缩模式
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
        save_interval: 周期性checkpoint保存间隔（步），异常中断后可从最近存档续训
        resume_path: 已有模型路径，非None时从该模型继续训练
            （沿用已保存的网络架构/超参数，本次steps为增量）

    Returns:
        训练统计信息
    """
    import torch
    import torch.nn as nn
    from stable_baselines3 import DQN
    from stable_baselines3.common.monitor import Monitor
    import traci

    from training.masked_policy import MaskableDQN, MaskedDQNPolicy

    # ========== 解析场景配置 ==========
    sumo_cfg_path = None
    scenario_label = "default"
    scenario_info = {}
    if scenario is not None:
        if scenario not in SCENARIO_CONFIG:
            raise ValueError(f"未知场景: {scenario}. 可选: {list(SCENARIO_CONFIG.keys())}")
        sumo_cfg_path = SCENARIO_CONFIG[scenario]["sumo_cfg"]
        scenario_label = scenario
        scenario_info = SCENARIO_CONFIG[scenario]

    # ========== 应用配置 ==========
    active_config = None
    if anti_collapse:
        active_config = ANTICOLLAPSE_DQN_CONFIG
        config_tag = "抗策略坍缩"
    elif perf:
        active_config = PERF_DQN_CONFIG
        config_tag = "高性能"
    else:
        config_tag = "标准"

    if active_config:
        lr = learning_rate or active_config["learning_rate"]
        bs = batch_size or active_config["batch_size"]
        bf = buffer_size or active_config["buffer_size"]
        ls = active_config["learning_starts"]
        tf = active_config["train_freq"]
        gs = active_config["gradient_steps"]
        tui = active_config["target_update_interval"]
        ef = exploration_fraction or active_config["exploration_fraction"]
        efe = active_config["exploration_final_eps"]
        arch = net_arch or active_config["policy_kwargs"]["net_arch"]
        act_fn_name = active_config["policy_kwargs"]["activation_fn"]
        ne = n_envs or active_config["n_envs"]
        activation_fn = nn.ReLU if act_fn_name == "ReLU" else nn.Tanh
        dueling = active_config["policy_kwargs"].get("dueling", False)
        double_q = active_config["policy_kwargs"].get("double_q", False)
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
        dueling = False
        double_q = False

    # ========== 应用场景特定覆盖（高流量场景降低并行度和缓冲区） ==========
    if scenario_info.get("high_traffic", False):
        override_ne = scenario_info.get("n_envs_override")
        override_bf = scenario_info.get("buffer_size_override")
        override_bs = scenario_info.get("batch_size_override")
        override_gs = scenario_info.get("gradient_steps_override")
        if override_ne is not None and ne > override_ne:
            print(f"[ADAPT] 高流量场景({scenario})：n_envs {ne} → {override_ne}，降低内存压力", flush=True)
            ne = override_ne
        if override_bf is not None and bf > override_bf:
            print(f"[ADAPT] 高流量场景({scenario})：buffer_size {bf:,} → {override_bf:,}", flush=True)
            bf = override_bf
        if override_bs is not None and bs > override_bs:
            print(f"[ADAPT] 高流量场景({scenario})：batch_size {bs} → {override_bs}", flush=True)
            bs = override_bs
        if override_gs is not None and gs != override_gs:
            print(f"[ADAPT] 高流量场景({scenario})：gradient_steps {gs} → {override_gs}", flush=True)
            gs = override_gs

    # ========== 系统内存检查与自适应调整 ==========
    try:
        import psutil
        mem = psutil.virtual_memory()
        mem_pct = mem.percent
        print(f"[MEMORY] 系统内存使用: {mem_pct:.1f}% (可用: {mem.available / 1024**3:.1f}GB)", flush=True)
        if mem_pct > 85:
            print(f"[WARN] 内存使用率过高({mem_pct:.1f}%)，强制降为单环境模式", flush=True)
            ne = 1
            if bf > 50000:
                bf = 50000
    except ImportError:
        pass

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
    print(" DQN训练 - 雄安新区30路口信号控制")
    print("=" * 68)
    print(f"  模式      : {'多路口参数共享' if multi else f'单路口({intersection_id})'}")
    print(f"  场景      : {SCENARIO_CONFIG.get(scenario, {}).get('label', scenario_label) if scenario else '默认'}")
    print(f"  配置      : {config_tag}模式")
    print(f"  设备      : {device.upper()}")
    print(f"  并行环境  : {ne}")
    print(f"  总步数    : {timesteps:,}")
    if resume_path is not None:
        print(f"  继续训练  : 是（恢复自 {resume_path}，本次为增量步数）")
    print(f"  学习率    : {lr}")
    print(f"  网络架构  : {arch} ({activation_fn.__name__})")
    print(f"  Dueling   : {'启用' if dueling else '关闭'}  | Double-Q: {'启用' if double_q else '关闭'}")
    print(f"  批量大小  : {bs}  | train_freq={tf}  | gradient_steps={gs}")
    print(f"  缓冲区    : {bf:,}  | learning_starts={ls}")
    print(f"  探索策略  : initial=1.0 → final={efe} (fraction={ef})")
    print(f"  折扣因子  : {gamma}")
    print(f"  随机种子  : {seed}")
    print("=" * 68)
    sys.stdout.flush()

    # ========== 创建环境（支持SubprocVecEnv并行） ==========
    from stable_baselines3.common.env_util import make_vec_env

    # 高流量场景更频繁重启SUMO进程（每20集），普通场景每50集
    restart_every = 20 if scenario_info.get("high_traffic", False) else 50

    if ne > 1 and perf:
        # 多进程并行环境（SubprocVecEnv）- 线性提速
        vec_env_cls = None
        try:
            from stable_baselines3.common.vec_env import SubprocVecEnv
            vec_env_cls = SubprocVecEnv
        except ImportError:
            vec_env_cls = None

        from stable_baselines3.common.vec_env import VecMonitor
        def _make_env_with_monitor(rank):
            _env = make_env_factory(
                intersection_id=intersection_id,
                multi=multi,
                sumo_cfg_path=sumo_cfg_path,
                max_steps=720,
                delta_time=5,
                rank=rank,
                restart_every=restart_every,
            )()
            return _env

        if vec_env_cls is not None:
            print(f"[INFO] 使用 SubprocVecEnv 启动 {ne} 个并行环境 (restart_every={restart_every})...", flush=True)
            env_fns = [lambda r=i: _make_env_with_monitor(r) for i in range(ne)]
            env = vec_env_cls(env_fns)
            env = VecMonitor(env, filename=str(log_dir / "monitor"), info_keywords=("cleared_count",))
            ne_used = ne
        else:
            print(f"[WARN] SubprocVecEnv不可用，回退单环境", flush=True)
            env = make_env_factory(intersection_id, multi, sumo_cfg_path, 720, 5, 0, restart_every)()
            env = Monitor(env, str(log_dir))
            ne_used = 1
    else:
        print(f"[INFO] 单环境训练模式 (restart_every={restart_every})", flush=True)
        from env.single_intersection_env import SingleIntersectionEnv, MultiIntersectionSharedEnv

        if multi:
            env = MultiIntersectionSharedEnv(
                sumo_cfg_path=sumo_cfg_path, max_steps=720, delta_time=5,
                seed=seed, rank=0, restart_every=restart_every,
            )
        else:
            env = SingleIntersectionEnv(
                intersection_id=intersection_id,
                sumo_cfg_path=sumo_cfg_path,
                max_steps=720,
                delta_time=5,
                seed=seed,
                rank=0,
                restart_every=restart_every,
            )
        env = Monitor(env, str(log_dir), info_keywords=("cleared_count",))
        ne_used = 1

    # ========== 构建DQN模型 ==========
    t_init_start = time.time()

    if resume_path is not None:
        # 继续训练：加载已有模型，沿用其网络架构/超参数，仅更换环境
        if not Path(resume_path).exists():
            raise FileNotFoundError(f"恢复模型不存在: {resume_path}")
        print(f"[INFO] 继续训练模式: 加载模型 {resume_path}", flush=True)
        model = MaskableDQN.load(resume_path, env=env, device=device)
        print(
            f"[INFO] 已恢复: num_timesteps={model.num_timesteps:,}, "
            f"lr={model.learning_rate}, batch_size={model.batch_size}, "
            f"net_arch={list(model.policy.net_arch)}, "
            f"exploration_rate={getattr(model, 'exploration_rate', None):.3f}",
            flush=True,
        )
    else:
        policy_kw = dict(
            net_arch=arch,
            activation_fn=activation_fn,
        )
        if dueling:
            policy_kw["dueling"] = True
        if double_q:
            policy_kw["double_q"] = True

        try:
            model = MaskableDQN(
                policy=MaskedDQNPolicy,
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
                verbose=0,
                seed=seed,
                tensorboard_log=str(log_dir),
                policy_kwargs=policy_kw,
            )
        except TypeError:
            # 某些 SB3 版本不支持 dueling/double_q，自动降级
            print("[WARN] 当前 SB3 版本不支持 Dueling/Double-Q，降级为标准 DQN", flush=True)
            policy_kw = dict(
                net_arch=arch,
                activation_fn=activation_fn,
            )
            dueling = False
            double_q = False
            model = MaskableDQN(
                policy=MaskedDQNPolicy,
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
                verbose=0,
                seed=seed,
                tensorboard_log=str(log_dir),
                policy_kwargs=policy_kw,
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
    from stable_baselines3.common.callbacks import BaseCallback, CheckpointCallback

    class _SB3CombinedCallback(BaseCallback):
        def __init__(self, speed_monitor: SpeedMonitorCallback, collapse_monitor: PolicyCollapseMonitorCallback):
            super().__init__(verbose=0)
            self.speed_monitor = speed_monitor
            self.collapse_monitor = collapse_monitor

        def _on_step(self) -> bool:
            self.speed_monitor.on_step(self.model, self.num_timesteps)
            self.collapse_monitor.on_step(self.model, self.num_timesteps, self.training_env)
            return True

    collapse_cb = PolicyCollapseMonitorCallback(check_interval=500, window_size=100)

    # 周期性checkpoint：异常中断后可从最近存档 --resume 续训，最多丢失 save_interval 步
    if save_interval <= 0:
        raise ValueError(f"--save-interval 必须为正数, got {save_interval}")
    ckpt_dir = save_path / "checkpoints"
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    ckpt_cb = CheckpointCallback(
        save_freq=save_interval,
        save_path=str(ckpt_dir),
        name_prefix=f"dqn_{env_name}{scenario_tag}{perf_tag}",
        save_vecnormalize=False,
    )
    callbacks = [_SB3CombinedCallback(speed_cb, collapse_cb), ckpt_cb]

    try:
        model.learn(
            total_timesteps=timesteps,
            tb_log_name=f"dqn{perf_tag}",
            reset_num_timesteps=not resume_path,
            callback=callbacks,
            log_interval=None,
            progress_bar=False,
        )
    except KeyboardInterrupt:
        print("\n[WARN] 用户中断训练，保存当前模型...", flush=True)
    except traci.exceptions.FatalTraCIError as _e:
        # SUMO连接中断：保存recovery模型后以非零码退出，避免静默丢失进度
        recovery_path = save_path / f"dqn_{env_name}{scenario_tag}{perf_tag}_recovery_{int(model.num_timesteps)}steps"
        model.save(str(recovery_path))
        print(f"\n[FATAL] SUMO连接中断: {_e}", flush=True)
        print(f"[SAVE] 已保存恢复模型: {recovery_path}.zip (累计 {int(model.num_timesteps):,} steps)", flush=True)
        resume_cmd = (
            f"python training/train_dqn.py --scenario {scenario_label} --perf --multi "
            f"--resume \"{recovery_path}.zip\" --timesteps {timesteps}"
        )
        print(f"[RESUME] 建议续训命令: {resume_cmd}", flush=True)
        sys.exit(1)

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
    # 继续训练时以累计总步数命名（如 1M+1M -> 2000000steps）
    final_total_steps = int(model.num_timesteps)
    model_filename = f"dqn_{env_name}{scenario_tag}{perf_tag}_{final_total_steps}steps"
    if anti_collapse:
        model_filename = f"dqn_{env_name}{scenario_tag}_anticollapse_{final_total_steps}steps"
    model_path = save_path / model_filename
    model.save(str(model_path))
    print(f"[SAVE] 模型已保存: {model_path}.zip (累计 {final_total_steps:,} steps)")

    # ========== 评估模型 ==========
    try:
        stats = evaluate_model(model, env, episodes=5, sumo_cfg_path=sumo_cfg_path)
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
    stats["resumed_from"] = resume_path
    stats["total_timesteps"] = final_total_steps
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
        plot_training_curve(log_dir, save_path, f"{env_name}{scenario_tag}{perf_tag}", final_total_steps)
    except Exception as e:
        print(f"[WARN] 绘图跳过: {e}")

    # 关闭vec env
    try:
        env.close()
    except Exception:
        pass

    return stats


def evaluate_model(model, env, episodes: int = 5, sumo_cfg_path=None) -> dict:
    """评估模型 - 对VecEnv自动使用单env评估以兼容5-tuple接口

    Args:
        sumo_cfg_path: 评估所用的场景配置路径。必须与训练时一致，
            否则模型会在错误的场景下评估（默认场景 vs 训练场景流量差异巨大）。
    """
    print(f"\n评估模型 ({episodes} episodes)...")

    is_vec = hasattr(env, "num_envs")

    # VecEnv下创建一个单独的普通env进行评估（避免4-tuple vs 5-tuple差异）
    eval_env = env
    if is_vec:
        try:
            from env.single_intersection_env import SingleIntersectionEnv, MultiIntersectionSharedEnv
            from stable_baselines3.common.monitor import Monitor
            # 使用训练时的第一个子env的相同配置（关键：必须传入训练场景的sumo_cfg_path）
            eval_env = MultiIntersectionSharedEnv(max_steps=720, delta_time=5, sumo_cfg_path=sumo_cfg_path)
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

        has_throughput = "cleared_count" in df.columns
        n_rows = 3 if has_throughput else 2
        fig, axes = plt.subplots(n_rows, 1, figsize=(12, 11 if has_throughput else 10), sharex=True)
        axes = np.atleast_1d(axes)

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

        next_ax = 1
        if "l" in df_valid.columns:
            axes[1].plot(df_valid.index, df_valid["l"], color="darkorange", linewidth=1, alpha=0.8)
            axes[1].set_ylabel("Episode Length (steps)")
            axes[1].grid(True, alpha=0.3)
            next_ax = 2

        if has_throughput:
            # 吞吐量与奖励正负无关，用完整df绘图
            axes[next_ax].plot(df.index, df["cleared_count"], color="seagreen", linewidth=1, alpha=0.8)
            if len(df) >= 10:
                window = max(1, len(df) // 10)
                rolling_throughput = df["cleared_count"].rolling(window=window, min_periods=1).mean()
                axes[next_ax].plot(df.index, rolling_throughput, color="red", linewidth=2,
                                   label=f"Rolling Mean (window={window})")
            axes[next_ax].set_ylabel("Cleared Vehicles / Episode")
            axes[next_ax].legend()
            axes[next_ax].grid(True, alpha=0.3)

        axes[-1].set_xlabel("Episode Index")

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
                        choices=list(SCENARIO_CONFIG.keys()),
                        help="训练场景: 真实场景(real_peak/real_offpeak/real_evening, 需求来自赛题xlsx)")
    parser.add_argument("--perf", action="store_true",
                        help="高性能模式: 极简网络+大train_freq+4x并行 (目标200+ steps/s)")
    parser.add_argument("--anti-collapse", action="store_true",
                        help="抗策略坍缩模式: 更大网络+更长探索+策略坍缩监控")
    parser.add_argument("--lr", type=float, default=None, help="覆盖学习率")
    parser.add_argument("--batch-size", type=int, default=None, help="覆盖batch_size")
    parser.add_argument("--n-envs", type=int, default=None, help="覆盖并行环境数")
    parser.add_argument("--net-arch", type=str, default=None, help="网络架构，如 '64,64'")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    parser.add_argument("--save-dir", type=str, default="models/dqn", help="模型与评估结果保存目录")
    parser.add_argument("--log-interval", type=int, default=1000, help="速度日志间隔(步)")
    parser.add_argument("--save-interval", type=int, default=50000, help="周期性checkpoint保存间隔(步)，异常中断后可从最近存档续训")
    parser.add_argument("--eval-only", action="store_true", help="仅评估已有模型")
    parser.add_argument("--model-path", type=str, default=None, help="已有模型路径")
    parser.add_argument("--resume", type=str, default=None,
                        help="从已有模型继续训练（模型路径，--timesteps为本次增量步数，"
                             "沿用已保存的网络架构/超参数）")
    args = parser.parse_args()

    net_arch = None
    if args.net_arch:
        net_arch = [int(x) for x in args.net_arch.split(",")]

    resolved_id = resolve_intersection_id(args.intersection)
    if resolved_id != args.intersection:
        print(f"[INFO] 路口ID映射: {args.intersection} → {resolved_id}")

    if args.eval_only:
        from stable_baselines3 import DQN
        if not args.model_path:
            print("错误: 请指定 --model-path")
            return
        model = DQN.load(args.model_path)
        from env.single_intersection_env import SingleIntersectionEnv, MultiIntersectionSharedEnv
        sumo_cfg_path = None
        if args.scenario:
            sumo_cfg_path = SCENARIO_CONFIG[args.scenario]["sumo_cfg"]
        if args.multi:
            # 与训练一致的MultiIntersectionSharedEnv评估（每episode随机采样一个路口）
            env = MultiIntersectionSharedEnv(
                sumo_cfg_path=sumo_cfg_path,
                max_steps=720,
                delta_time=5,
                seed=args.seed,
            )
        else:
            env = SingleIntersectionEnv(
                intersection_id=resolved_id,
                sumo_cfg_path=sumo_cfg_path,
            )
        stats = evaluate_model(model, env, episodes=10, sumo_cfg_path=sumo_cfg_path)
        print(f"\n评估结果:\n{json.dumps(stats, indent=2)}")
        return

    stats = train_dqn(
        timesteps=args.timesteps,
        intersection_id=resolved_id,
        multi=args.multi,
        scenario=args.scenario,
        perf=args.perf,
        anti_collapse=args.anti_collapse,
        learning_rate=args.lr,
        batch_size=args.batch_size,
        seed=args.seed,
        save_dir=args.save_dir,
        net_arch=net_arch,
        n_envs=args.n_envs,
        log_interval=args.log_interval,
        save_interval=args.save_interval,
        resume_path=args.resume,
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
