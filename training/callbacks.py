import os
import numpy as np
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.logger import TensorBoardOutputFormat


class RewardLoggerCallback(BaseCallback):
    def __init__(self, log_interval=100, verbose=0):
        super().__init__(verbose)
        self.log_interval = log_interval
        self.episode_rewards = []
        self.episode_queue_lengths = []
        self.current_episode_reward = 0
        self.current_queue_length = 0

    def _on_step(self) -> bool:
        reward = self.locals.get('reward', 0)
        info = self.locals.get('info', {})
        
        self.current_episode_reward += reward
        self.current_queue_length += info.get('queue_length', 0)

        if self.locals.get('done', False):
            self.episode_rewards.append(self.current_episode_reward)
            self.episode_queue_lengths.append(self.current_queue_length / info.get('step', 1))
            self.current_episode_reward = 0
            self.current_queue_length = 0

            if len(self.episode_rewards) % self.log_interval == 0:
                avg_reward = np.mean(self.episode_rewards[-self.log_interval:])
                avg_queue = np.mean(self.episode_queue_lengths[-self.log_interval:])
                
                self.logger.record('episode/avg_reward', avg_reward)
                self.logger.record('episode/avg_queue_length', avg_queue)
                self.logger.dump(self.num_timesteps)

        return True


class ModelSaveCallback(BaseCallback):
    def __init__(self, save_path, save_freq=100000, verbose=0):
        super().__init__(verbose)
        self.save_path = save_path
        self.save_freq = save_freq

    def _on_step(self) -> bool:
        if self.num_timesteps % self.save_freq == 0:
            model_path = os.path.join(self.save_path, f'dqn_{self.num_timesteps}')
            self.model.save(model_path)
            
            if self.verbose > 0:
                print(f"Model saved at {model_path}")

        return True


class EvaluationCallback(BaseCallback):
    def __init__(self, eval_env, eval_freq=50000, n_eval_episodes=10, verbose=0):
        super().__init__(verbose)
        self.eval_env = eval_env
        self.eval_freq = eval_freq
        self.n_eval_episodes = n_eval_episodes

    def _on_step(self) -> bool:
        if self.num_timesteps % self.eval_freq == 0:
            total_reward = 0
            total_queue = 0
            
            for _ in range(self.n_eval_episodes):
                obs, _ = self.eval_env.reset()
                episode_reward = 0
                episode_queue = 0
                done = False
                
                while not done:
                    action, _states = self.model.predict(obs, deterministic=True)
                    obs, reward, done, _, info = self.eval_env.step(action)
                    episode_reward += reward
                    episode_queue += info.get('queue_length', 0)
                
                total_reward += episode_reward
                total_queue += episode_queue

            avg_reward = total_reward / self.n_eval_episodes
            avg_queue = total_queue / self.n_eval_episodes
            
            self.logger.record('eval/avg_reward', avg_reward)
            self.logger.record('eval/avg_queue_length', avg_queue)
            self.logger.dump(self.num_timesteps)

            if self.verbose > 0:
                print(f"Evaluation at {self.num_timesteps}: avg_reward={avg_reward:.2f}, avg_queue={avg_queue:.2f}")

        return True