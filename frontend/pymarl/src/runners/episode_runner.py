from envs import REGISTRY as env_REGISTRY
from functools import partial
from components.episode_buffer import EpisodeBatch
import numpy as np
import torch as th


def _is_numeric_stat(value):
    try:
        float(value)
        return True
    except Exception:
        return False


class EpisodeRunner:

    def __init__(self, args, logger):
        self.args = args
        self.logger = logger
        self.batch_size = self.args.batch_size_run
        assert self.batch_size == 1

        self.env = env_REGISTRY[self.args.env](**self.args.env_args)
        self.episode_limit = self.env.episode_limit
        self.t = 0

        self.t_env = 0

        self.train_returns = []
        self.test_returns = []
        self.train_stats = {}
        self.test_stats = {}

        # Log the first run
        self.log_train_stats_t = -1000000

    def setup(self, scheme, groups, preprocess, mac):
        self.new_batch = partial(EpisodeBatch, scheme, groups, self.batch_size, self.episode_limit + 1,
                                 preprocess=preprocess, device=self.args.device)
        self.mac = mac

    def get_env_info(self):
        return self.env.get_env_info()

    def save_replay(self):
        self.env.save_replay()

    def close_env(self):
        self.env.close()

    def reset(self):
        self.batch = self.new_batch()
        self.env.reset()
        self.t = 0

    def _get_expert_actions(self):
        if hasattr(self.env, "get_expert_actions"):
            return self.env.get_expert_actions()
        return np.zeros((self.args.n_agents, 1), dtype=np.int64)

    def _get_expert_action_mask(self):
        if hasattr(self.env, "get_expert_action_mask"):
            return self.env.get_expert_action_mask()
        return np.zeros((self.args.n_agents, 1), dtype=np.float32)

    def run(self, test_mode=False):
        if hasattr(self.env, "set_test_mode"):
            self.env.set_test_mode(test_mode)
        self.reset()

        terminated = False
        episode_return = 0
        self.mac.init_hidden(batch_size=self.batch_size)

        while not terminated:

            pre_transition_data = {
                "state": [self.env.get_state()],
                "avail_actions": [self.env.get_avail_actions()],
                "obs": [self.env.get_obs()],
                "expert_actions": [self._get_expert_actions()],
                "expert_action_mask": [self._get_expert_action_mask()],
            }

            self.batch.update(pre_transition_data, ts=self.t)

            # Pass the entire batch of experiences up till now to the agents
            # Receive the actions for each agent at this timestep in a batch of size 1
            actions = self.mac.select_actions(self.batch, t_ep=self.t, t_env=self.t_env, test_mode=test_mode)

            reward, terminated, env_info = self.env.step(actions[0])
            episode_return += reward
            vehicle_reward = float(env_info.get("vehicle_step_reward", reward))
            signal_reward = float(env_info.get("signal_step_reward", 0.0))

            post_transition_data = {
                "actions": actions,
                "reward": [(reward,)],
                "vehicle_reward": [(vehicle_reward,)],
                "signal_reward": [(signal_reward,)],
                "terminated": [(terminated != env_info.get("episode_limit", False),)],
            }

            self.batch.update(post_transition_data, ts=self.t)

            self.t += 1

        if hasattr(self.env, "pop_episode_reward_adjustments"):
            adjustments, entropy_stats = self.env.pop_episode_reward_adjustments(self.t)
            if adjustments:
                add = th.tensor(adjustments, dtype=self.batch["reward"].dtype, device=self.batch["reward"].device)
                self.batch.data.transition_data["reward"][0, : self.t, 0] += add
                self.batch.data.transition_data["vehicle_reward"][0, : self.t, 0] += add
                episode_return += float(np.sum(adjustments))
            if isinstance(entropy_stats, dict):
                env_info.update(entropy_stats)

        last_data = {
            "state": [self.env.get_state()],
            "avail_actions": [self.env.get_avail_actions()],
            "obs": [self.env.get_obs()],
            "expert_actions": [self._get_expert_actions()],
            "expert_action_mask": [self._get_expert_action_mask()],
        }
        self.batch.update(last_data, ts=self.t)

        # Select actions in the last stored state
        actions = self.mac.select_actions(self.batch, t_ep=self.t, t_env=self.t_env, test_mode=test_mode)
        self.batch.update({"actions": actions}, ts=self.t)

        cur_stats = self.test_stats if test_mode else self.train_stats
        cur_returns = self.test_returns if test_mode else self.train_returns
        log_prefix = "test_" if test_mode else ""
        scalar_env_info = {}
        info_t = self.t_env + (0 if test_mode else self.t)
        for key in ("trajectory_embedding_16", "trajectory_road_sequence", "road_visit_counts"):
            value = env_info.get(key)
            if isinstance(value, (list, dict)):
                self.logger.log_info(log_prefix + key, value, info_t)
        for k, v in env_info.items():
            if _is_numeric_stat(v):
                scalar_env_info[k] = float(v)

        cur_stats.update({k: cur_stats.get(k, 0) + scalar_env_info.get(k, 0) for k in set(cur_stats) | set(scalar_env_info)})
        cur_stats["n_episodes"] = 1 + cur_stats.get("n_episodes", 0)
        cur_stats["ep_length"] = self.t + cur_stats.get("ep_length", 0)

        if not test_mode:
            self.t_env += self.t

        cur_returns.append(episode_return)

        if test_mode and (len(self.test_returns) == self.args.test_nepisode):
            self._update_env_after_test(cur_stats)
            self._log(cur_returns, cur_stats, log_prefix)
        elif (not test_mode) and self.t_env - self.log_train_stats_t >= self.args.runner_log_interval:
            self._log(cur_returns, cur_stats, log_prefix)
            if hasattr(self.mac.action_selector, "epsilon"):
                self.logger.log_stat("epsilon", self.mac.action_selector.epsilon, self.t_env)
            self.log_train_stats_t = self.t_env

        return self.batch

    def _update_env_after_test(self, stats):
        if not hasattr(self.env, "update_tee_activation"):
            return

        n_episodes = max(1, stats.get("n_episodes", 1))
        completion_sum = None
        for key in ("vehicle_completion_rate", "vehicle_completed_rate", "vehicle_completed_count"):
            if key in stats:
                completion_sum = stats[key]
                break
        if completion_sum is None:
            return

        completion_rate = float(completion_sum) / float(n_episodes)
        if completion_rate > 1.0:
            n_agents = max(1, int(getattr(self.args, "n_agents", 1)))
            completion_rate = completion_rate / float(n_agents)

        was_active = bool(getattr(self.env, "_tee_reward_active", False))
        is_active = self.env.update_tee_activation(self.t_env, completion_rate)
        if is_active and not was_active:
            self.logger.log_stat("tee_reward_activated_t_env", self.t_env, self.t_env)

    def _log(self, returns, stats, prefix):
        self.logger.log_stat(prefix + "return_mean", np.mean(returns), self.t_env)
        self.logger.log_stat(prefix + "return_std", np.std(returns), self.t_env)
        returns.clear()

        for k, v in stats.items():
            if k != "n_episodes":
                self.logger.log_stat(prefix + k + "_mean" , v/stats["n_episodes"], self.t_env)
        stats.clear()
