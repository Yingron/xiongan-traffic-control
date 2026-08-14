"""需求门控动作掩码的 DQN 策略与算法封装。

观测尾部 4 维为动作掩码（0=无效、1=有效，见 env/global_state.compute_action_mask），
掩码由模板C 的"相位所服务链路是否有排队车辆"动态决定。
无效动作的 Q 值被强制减去 MASK_PENALTY，因此 argmax 与 TD 目标的 max 只会落在
有效动作上；epsilon 探索也只在有效动作内随机采样。训练/加载均与 SB3 DQN 兼容：
模型 zip 直接以本模块中的类名 pickle，加载方只要能从项目根目录 import 本模块即可。
"""
from __future__ import annotations

from typing import Any

import numpy as np
import torch as th

from stable_baselines3.dqn import DQN
from stable_baselines3.dqn.policies import DQNPolicy, QNetwork

# 远大于该任务 Q 值量级（~±50）的掩码惩罚：保证无效动作永远不被 argmax 选中
MASK_PENALTY = 1e8


class MaskedQNetwork(QNetwork):
    """带动作掩码的 Q 网络：观测尾部 action_dim 维为掩码，其余为状态。

    掩码维度不参与 MLP 前向：头网络输入维度 = features_dim - action_dim，
    forward 时先剥离掩码再走基类前向，最后对无效动作 Q 值施加 MASK_PENALTY。
    """

    def __init__(
        self,
        observation_space: Any,
        action_space: Any,
        features_extractor: Any,
        features_dim: int,
        net_arch: list[int] | None = None,
        activation_fn: Any = th.nn.ReLU,
        normalize_images: bool = True,
    ) -> None:
        action_dim = int(action_space.n)
        super().__init__(
            observation_space,
            action_space,
            features_extractor,
            features_dim - action_dim,
            net_arch,
            activation_fn,
            normalize_images,
        )

    def forward(self, obs: th.Tensor) -> th.Tensor:
        action_dim = int(self.action_space.n)
        state = obs[:, :-action_dim]
        mask = obs[:, -action_dim:]
        q_values = super().forward(state)
        return q_values - (1.0 - mask) * MASK_PENALTY


class MaskedDQNPolicy(DQNPolicy):
    """DQNPolicy 子类：q_net 与 q_net_target 均使用 MaskedQNetwork。"""

    q_net: MaskedQNetwork
    q_net_target: MaskedQNetwork

    def make_q_net(self) -> MaskedQNetwork:
        # Make sure we always have separate networks for features extractors etc
        net_args = self._update_features_extractor(self.net_args, features_extractor=None)
        return MaskedQNetwork(**net_args).to(self.device)


class MaskableDQN(DQN):
    """DQN 子类：epsilon 探索只在当前掩码允许的动作内随机采样。"""

    def predict(
        self,
        observation: np.ndarray | dict[str, np.ndarray],
        state: tuple[np.ndarray, ...] | None = None,
        episode_start: np.ndarray | None = None,
        deterministic: bool = False,
    ) -> tuple[np.ndarray, tuple[np.ndarray, ...] | None]:
        if not deterministic and np.random.rand() < self.exploration_rate:
            action_dim = int(self.action_space.n)
            if self.policy.is_vectorized_observation(observation):
                obs_arr = (
                    observation
                    if isinstance(observation, np.ndarray)
                    else observation[next(iter(observation.keys()))]
                )
                n_batch = obs_arr.shape[0]
                masks = np.asarray(obs_arr)[:, -action_dim:]
                action = np.array(
                    [self._sample_valid(masks[i], action_dim) for i in range(n_batch)]
                )
            else:
                mask = np.asarray(observation, dtype=np.float32)[-action_dim:]
                action = np.array(self._sample_valid(mask, action_dim))
            return action, state
        return super().predict(observation, state, episode_start, deterministic)

    @staticmethod
    def _sample_valid(mask: np.ndarray, action_dim: int) -> int:
        """从掩码允许的动作中等概率采样；全 0 时兜底退化为全空间。"""
        valid = np.nonzero(mask)[0]
        if len(valid) == 0:
            valid = np.arange(action_dim)
        return int(np.random.choice(valid))
