import argparse
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stable_baselines3 import DQN, D3QN
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.callbacks import CallbackList

from env.xiongan_env import XionganEnv
from training.config import DQN_CONFIG, D3QN_CONFIG, TRAINING_CONFIG, ENV_CONFIG, MODEL_DIR, LOG_DIR


def train_dqn(args):
    env_config = ENV_CONFIG.copy()
    env_config['use_gui'] = args.gui

    env = XionganEnv(**env_config)
    env = Monitor(env, LOG_DIR)

    if args.algorithm == 'dqn':
        model = DQN(env=env, tensorboard_log=LOG_DIR, **DQN_CONFIG)
    elif args.algorithm == 'd3qn':
        model = D3QN(env=env, tensorboard_log=LOG_DIR, **D3QN_CONFIG)
    else:
        raise ValueError(f"Unknown algorithm: {args.algorithm}")

    callbacks = []

    if args.log_reward:
        from training.callbacks import RewardLoggerCallback
        callbacks.append(RewardLoggerCallback())

    if args.save_freq > 0:
        from training.callbacks import ModelSaveCallback
        callbacks.append(ModelSaveCallback(MODEL_DIR, save_freq=args.save_freq))

    callback_list = CallbackList(callbacks)

    print(f"Starting {args.algorithm} training...")
    print(f"Timesteps: {args.timesteps}")
    print(f"GUI: {args.gui}")
    print(f"Algorithm: {args.algorithm}")

    model.learn(
        total_timesteps=args.timesteps,
        callback=callback_list,
        log_interval=TRAINING_CONFIG['log_interval'],
        tb_log_name=TRAINING_CONFIG['tb_log_name']
    )

    model_path = os.path.join(MODEL_DIR, f'{args.algorithm}_pretrained.zip')
    model.save(model_path)
    print(f"Model saved to {model_path}")

    env.close()


def evaluate_model(args):
    env_config = ENV_CONFIG.copy()
    env_config['use_gui'] = args.gui

    env = XionganEnv(**env_config)

    model_path = os.path.join(MODEL_DIR, f'{args.algorithm}_pretrained.zip')
    
    if not os.path.exists(model_path):
        print(f"Model not found: {model_path}")
        return

    if args.algorithm == 'dqn':
        model = DQN.load(model_path, env=env)
    elif args.algorithm == 'd3qn':
        model = D3QN.load(model_path, env=env)
    else:
        raise ValueError(f"Unknown algorithm: {args.algorithm}")

    print(f"Evaluating {args.algorithm} model...")
    
    total_reward = 0
    total_queue = 0
    total_steps = 0

    for episode in range(args.n_episodes):
        obs, _ = env.reset()
        episode_reward = 0
        episode_queue = 0
        done = False

        while not done:
            action, _states = model.predict(obs, deterministic=True)
            obs, reward, done, _, info = env.step(action)
            episode_reward += reward
            episode_queue += info.get('queue_length', 0)
            total_steps += 1

        total_reward += episode_reward
        total_queue += episode_queue

        print(f"Episode {episode+1}: reward={episode_reward:.2f}, queue={episode_queue/total_steps:.2f}")

    avg_reward = total_reward / args.n_episodes
    avg_queue = total_queue / total_steps

    print(f"\nAverage reward: {avg_reward:.2f}")
    print(f"Average queue length: {avg_queue:.2f}")

    env.close()


def main():
    parser = argparse.ArgumentParser(description='Train DQN/D3QN for Xiongan traffic signal control')
    parser.add_argument('--algorithm', type=str, default='d3qn', choices=['dqn', 'd3qn'], help='Algorithm to use')
    parser.add_argument('--timesteps', type=int, default=1000000, help='Total training timesteps')
    parser.add_argument('--gui', action='store_true', help='Use SUMO GUI')
    parser.add_argument('--no_gui', action='store_false', dest='gui', help='Do not use SUMO GUI')
    parser.add_argument('--save_freq', type=int, default=100000, help='Save model frequency')
    parser.add_argument('--log_reward', action='store_true', help='Log episode rewards')
    parser.add_argument('--evaluate', action='store_true', help='Evaluate model instead of training')
    parser.add_argument('--n_episodes', type=int, default=10, help='Number of evaluation episodes')

    args = parser.parse_args()

    if args.evaluate:
        evaluate_model(args)
    else:
        train_dqn(args)


if __name__ == '__main__':
    main()