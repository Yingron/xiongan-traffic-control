import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SUMO_CFG_PATH = os.path.join(BASE_DIR, 'sumo_files', 'xiongan.sumocfg')
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
    'teacher_model_path': os.path.join(MODEL_DIR, 'dqn_pretrained.zip'),
    'student_model_path': os.path.join(MODEL_DIR, 'dqn_student.zip'),
    'quantized_model_path': os.path.join(MODEL_DIR, 'dqn_quantized.pt'),
    'distill_epochs': 50,
    'distill_lr': 1e-3,
    'temperature': 2.0,
    'alpha': 0.7,
    'student_hidden_layers': [64, 64],
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
# high_traffic 场景需要降低并行度和缓冲区以避免内存溢出
# 同时优化batch_size和gradient_steps以提高训练速度
SCENARIO_CONFIG = {
    'flat': {
        'sumo_cfg': os.path.join(BASE_DIR, 'sumo_files', 'xiongan_flat.sumocfg'),
        'label': '平峰',
        'target_vehicles': '~2,773',
        'high_traffic': False,
        'n_envs_override': None,
        'buffer_size_override': None,
        'batch_size_override': None,
        'gradient_steps_override': None,
    },
    'morning': {
        'sumo_cfg': os.path.join(BASE_DIR, 'sumo_files', 'xiongan_morning.sumocfg'),
        'label': '早高峰',
        'target_vehicles': '~19,104',
        'high_traffic': True,
        'n_envs_override': 1,
        'buffer_size_override': 100000,
        'batch_size_override': 256,
        'gradient_steps_override': 10,
    },
    'evening': {
        'sumo_cfg': os.path.join(BASE_DIR, 'sumo_files', 'xiongan_evening.sumocfg'),
        'label': '晚高峰',
        'target_vehicles': '~19,104',
        'high_traffic': True,
        'n_envs_override': 1,
        'buffer_size_override': 100000,
        'batch_size_override': 256,
        'gradient_steps_override': 10,
    },
    'low': {
        'sumo_cfg': os.path.join(BASE_DIR, 'sumo_files', 'xiongan_low.sumocfg'),
        'label': '低峰',
        'target_vehicles': '~2,773',
        'high_traffic': False,
        'n_envs_override': None,
        'buffer_size_override': None,
        'batch_size_override': None,
        'gradient_steps_override': None,
    },
    'high': {
        'sumo_cfg': os.path.join(BASE_DIR, 'sumo_files', 'xiongan_high.sumocfg'),
        'label': '高峰(high)',
        'target_vehicles': '~19,104',
        'high_traffic': True,
        'n_envs_override': 1,
        'buffer_size_override': 100000,
        'batch_size_override': 256,
        'gradient_steps_override': 10,
    },
}
