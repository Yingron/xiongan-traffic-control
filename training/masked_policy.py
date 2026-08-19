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

# 无效动作的 Q 值填充值：直接用乘法置零网络原始输出（不依赖 q - 大数），
# 即使 Q 网络发散输出 1e10 量级，掩码动作的 Q 也恒为该巨大负值，argmax 不可能选中。
# （2026-08-15 教训：首版用 q - 1e8，全模板门控训练时 Q 发散到 1e10，
#   掩码动作的原始输出超过惩罚量级后反而胜出，造成推理违规。）
MASK_FILL = 3.0e38


class MaskedQNetwork(QNetwork):
    """带动作掩码的 Q 网络：观测尾部 action_dim 维为掩码，其余为状态。

    掩码维度不参与 MLP 前向：头网络输入维度 = features_dim - action_dim，
    forward 时先剥离掩码再走基类前向，最后把无效动作的 Q 值乘法置零为 -MASK_FILL
    （绝对掩码，与 Q 值发散与否无关）。
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
        # 绝对掩码：无效动作 Q = -MASK_FILL（乘法置零原始输出，与发散无关），有效动作原值
        return q_values * mask - (1.0 - mask) * MASK_FILL


class MaskedDQNPolicy(DQNPolicy):
    """DQNPolicy 子类：q_net 与 q_net_target 均使用 MaskedQNetwork。"""

    q_net: MaskedQNetwork
    q_net_target: MaskedQNetwork

    def make_q_net(self) -> MaskedQNetwork:
        # Make sure we always have separate networks for features extractors etc
        net_args = self._update_features_extractor(self.net_args, features_extractor=None)
        return MaskedQNetwork(**net_args).to(self.device)


class MaskableDQN(DQN):
    """DQN 子类：epsilon 探索只在当前掩码允许的动作内随机采样。

    同时把目标计算改为 Double-DQN（在线网络选动作、目标网络估值）：
    全模板门控训练实测 vanilla-DQN 的 max 偏置使 Q 值在 100k 步内发散到 1e8~1e10
    （stratified 非掩码训练不会，掩码冻结部分动作输出加剧了自举放大），
    Double-DQN 的 max 去偏置是抑制发散的常规手段。
    """

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

    def train(self, gradient_steps: int, batch_size: int = 100) -> None:
        import torch.nn.functional as F

        # Switch to train mode (this affects batch norm / dropout)
        self.policy.set_training_mode(True)
        # Update learning rate according to schedule
        self._update_learning_rate(self.policy.optimizer)

        losses = []
        for _ in range(gradient_steps):
            replay_data = self.replay_buffer.sample(batch_size, env=self._vec_normalize_env)
            sample_discounts = getattr(replay_data, "discounts", None)
            discounts = sample_discounts if sample_discounts is not None else self.gamma

            with th.no_grad():
                # Double-DQN：在线（掩码）网络 argmax 选动作，目标网络给该动作估值。
                # 掩码网络保证选中的是有效动作（无效动作 Q=-MASK_FILL 不可能胜出）。
                next_q_online = self.policy.q_net(replay_data.next_observations)
                next_actions = next_q_online.argmax(dim=1, keepdim=True)
                next_q_target = self.policy.q_net_target(replay_data.next_observations)
                next_q_values = next_q_target.gather(dim=1, index=next_actions).reshape(-1, 1)
                # 1-step TD target
                target_q_values = replay_data.rewards + (1 - replay_data.dones) * discounts * next_q_values

            # Get current Q-values estimates
            current_q_values = self.policy.q_net(replay_data.observations)

            # Retrieve the q-values for the actions from the replay buffer
            current_q_values = th.gather(current_q_values, dim=1, index=replay_data.actions.long())

            # Compute Huber loss (less sensitive to outliers)
            loss = F.smooth_l1_loss(current_q_values, target_q_values)
            losses.append(loss.item())

            # Optimize the policy
            self.policy.optimizer.zero_grad()
            loss.backward()
            # Clip gradient norm
            th.nn.utils.clip_grad_norm_(self.policy.parameters(), self.max_grad_norm)
            self.policy.optimizer.step()

        # Increase update counter
        self._n_updates += gradient_steps

        self.logger.record("train/n_updates", self._n_updates, exclude="tensorboard")
        self.logger.record("train/loss", np.mean(losses))

    @staticmethod
    def _sample_valid(mask: np.ndarray, action_dim: int) -> int:
        """从掩码允许的动作中等概率采样；全 0 时兜底退化为全空间。"""
        valid = np.nonzero(mask)[0]
        if len(valid) == 0:
            valid = np.arange(action_dim)
        return int(np.random.choice(valid))
