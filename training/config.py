import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SUMO_CFG_PATH = os.path.join(BASE_DIR, 'sumo_files', 'xiongan_30.sumocfg')
MODEL_DIR = os.path.join(BASE_DIR, 'models')
LOG_DIR = os.path.join(BASE_DIR, 'training', 'logs')
VISUALIZATION_DIR = os.path.join(BASE_DIR, 'visualization', 'output')

os.makedirs(MODEL_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(VISUALIZATION_DIR, exist_ok=True)

# ========== 标准DQN配置（原默认） ==========
DQN_CONFIG = {
    'policy': 'MlpPolicy',
    'learning_rate': 1e-4,
    'buffer_size': 1000000,
    'learning_starts': 10000,
    'batch_size': 64,
    'gamma': 0.99,
    'train_freq': 4,
    'gradient_steps': 1,
    'target_update_interval': 10000,
    'exploration_fraction': 0.1,
    'exploration_initial_eps': 1.0,
    'exploration_final_eps': 0.05,
    'max_grad_norm': 10,
}

D3QN_CONFIG = {
    'policy': 'MlpPolicy',
    'learning_rate': 1e-4,
    'buffer_size': 1000000,
    'learning_starts': 10000,
    'batch_size': 64,
    'gamma': 0.99,
    'train_freq': 4,
    'gradient_steps': 1,
    'target_update_interval': 10000,
    'exploration_fraction': 0.1,
    'exploration_initial_eps': 1.0,
    'exploration_final_eps': 0.05,
    'max_grad_norm': 10,
    'policy_kwargs': {
        'net_arch': [256, 256]
    }
}

TRAINING_CONFIG = {
    'timesteps': 1000000,
    'eval_freq': 50000,
    'n_eval_episodes': 10,
    'tb_log_name': 'xiongan_dqn',
    'log_interval': 100,
}

DISTILL_CONFIG = {
    'teacher_model_paths': {
        'peak': os.path.join(MODEL_DIR, 'dqn', 'dqn_multi_shared_real_peak_perf_1000000steps.zip'),
        'evening': os.path.join(MODEL_DIR, 'dqn', 'dqn_multi_shared_real_evening_perf_1000000steps.zip'),
    },
    'output_root': os.path.join(MODEL_DIR, 'edge'),
    'input_dimension': 26,
    'state_dimension': 22,
    'action_mask_dimension': 4,
    'distill_epochs': 30,
    'distill_lr': 1e-3,
    'temperature': 2.0,
    'alpha': 0.7,
    'student_hidden_layers': [56, 56],
}

ENV_CONFIG = {
    'sumo_cfg_path': SUMO_CFG_PATH,
    'use_gui': False,
    'max_steps': 3600,
    'delta_time': 5,
}

# ========== 高性能训练配置（200+ steps/s 目标） ==========
# 针对瓶颈分析：仿真41.2% + 网络更新58.8%
# 优化策略：
#   1. 网络极简化：参数量减少约10x (256x256x3 -> 64x64x2)
#   2. train_freq大幅提高：分摊网络更新开销
#   3. batch_size增大：SIMD并行效率提高
#   4. target_update_interval提高：减少同步开销
#   5. learning_starts降低：更快开始更新
#   6. 开启SubprocVecEnv多环境并行：n_envs=4 线性提速
PERF_DQN_CONFIG = {
    'policy': 'MlpPolicy',
    # 学习率适中，配合大batch
    'learning_rate': 3e-4,
    # buffer适度减小以降低内存开销与cache miss
    'buffer_size': 200000,
    # 更快开始学习（500步后开始更新）
    'learning_starts': 500,
    # 大batch：SIMD并行效率更高
    'batch_size': 256,
    'gamma': 0.99,
    # 适当降低train_freq，让模型更频繁学习
    'train_freq': 4,
    'gradient_steps': 1,
    # 目标网络更新频率提高，稳定学习
    'target_update_interval': 8000,
    # 探索策略：更长探索期 + 更高最终探索率
    # 防止模型过早收敛到单一动作
    'exploration_fraction': 0.5,
    'exploration_initial_eps': 1.0,
    'exploration_final_eps': 0.1,
    'max_grad_norm': 10,
    # 稍大的网络：两层64，增加拟合能力避免坍缩
    'policy_kwargs': {
        'net_arch': [64, 64],
        'activation_fn': 'ReLU',
    },
    # 2个并行SubprocVecEnv env
    'n_envs': 2,
}

# ========== 抗策略坍缩 DQN 配置 V5 ==========
# V5: 吞吐驱动奖励 + 更大网络 + 更长探索
# 核心思路: [256,256,128] + Dueling + 更长探索期 + 更高学习率
ANTICOLLAPSE_DQN_CONFIG = {
    'policy': 'MlpPolicy',
    'learning_rate': 5e-4,
    'buffer_size': 500000,
    'learning_starts': 2000,
    'batch_size': 128,
    'gamma': 0.99,
    'train_freq': 4,
    'gradient_steps': 1,
    'target_update_interval': 10000,
    # 探索期延长：前30%步数衰减探索率
    'exploration_fraction': 0.3,
    'exploration_initial_eps': 1.0,
    # 保持10%随机探索防止坍缩
    'exploration_final_eps': 0.1,
    'max_grad_norm': 10,
    # 更大网络：三层 [256,256,128]
    'policy_kwargs': {
        'net_arch': [256, 256, 128],
        'activation_fn': 'ReLU',
        'dueling': True,
        'double_q': True,
    },
    'n_envs': 2,
}

# ========== 场景映射配置 ==========
# 真实数据场景（scripts/generate_real_demand_scenarios.py 生成）：
# 需求直接来自赛题 xlsx（每15min pcu，按真实时段窗口 07:00-09:00 / 14:30-16:30 / 17:30-19:30），
# 路口会真实排队，DQN 才有学习信号。已在 30 路口路网（xiongan_30.net.xml）上重新生成。
# 需求按“真实定周期基线（data/timing_plans.json）全路网可通行能力”等比标定：
# 因子 peak=0.48 / offpeak=0.60 / evening=0.42（约 6.2~7.2 veh/s 总插入率，
# 基线 7200s 全程不堵死、meanSpeed 全程最低 ≥ 2 m/s）。原因：200m 网格路网容量
# 约为真实雄安路网的 45%~55%，若按 xlsx 原始需求（约 12 veh/s）真实基线会在
# 低绿信比左转进口（J12/J14/J10 等）饱和回溢死锁。
# 可复现命令：python scripts/generate_real_demand_scenarios.py --factor 0.48,0.60,0.42
# 注：flat/morning/evening/low/high 旧手工场景及其 sumocfg 已随 20 路口路网一起删除。
SCENARIO_CONFIG = {
    # ========== 真实数据场景 ==========
    'real_peak': {
        'sumo_cfg': os.path.join(BASE_DIR, 'sumo_files', 'xiongan_real_peak.sumocfg'),
        'label': '真实早高峰(07:00-09:00)',
        'target_vehicles': '~51,868',
        'high_traffic': True,
        'n_envs_override': 1,
        'buffer_size_override': 100000,
        'batch_size_override': 256,
        'gradient_steps_override': 4,
    },
    'real_offpeak': {
        'sumo_cfg': os.path.join(BASE_DIR, 'sumo_files', 'xiongan_real_offpeak.sumocfg'),
        'label': '真实平峰(14:30-16:30)',
        'target_vehicles': '~44,947',
        'high_traffic': True,
        'n_envs_override': 1,
        'buffer_size_override': 100000,
        'batch_size_override': 256,
        'gradient_steps_override': 4,
    },
    'real_evening': {
        'sumo_cfg': os.path.join(BASE_DIR, 'sumo_files', 'xiongan_real_evening.sumocfg'),
        'label': '真实晚高峰(17:30-19:30)',
        'target_vehicles': '~50,296',
        'high_traffic': True,
        'n_envs_override': 1,
        'buffer_size_override': 100000,
        'batch_size_override': 256,
        'gradient_steps_override': 4,
    },
}
