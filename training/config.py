import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SUMO_CFG_PATH = os.path.join(BASE_DIR, 'sumo_files', 'xiongan.sumocfg')
MODEL_DIR = os.path.join(BASE_DIR, 'models')
LOG_DIR = os.path.join(BASE_DIR, 'training', 'logs')
VISUALIZATION_DIR = os.path.join(BASE_DIR, 'visualization', 'output')

os.makedirs(MODEL_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(VISUALIZATION_DIR, exist_ok=True)

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