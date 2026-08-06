import copy
import os
from components.episode_buffer import EpisodeBatch
from modules.mixers.vdn import VDNMixer
from modules.mixers.qmix import QMixer
import torch as th
import torch.nn.functional as F
from torch.optim import RMSprop


class QLearner:
    def __init__(self, mac, scheme, logger, args):
        self.args = args
        self.mac = mac
        self.logger = logger

        self.params = [p for p in mac.parameters() if p.requires_grad]

        self.last_target_update_episode = 0

        self.mixer = None
        self.route_mixer = None
        self.signal_mixer = None
        self.target_route_mixer = None
        self.target_signal_mixer = None
        self.dual_reward_training = (
            getattr(args, "action_dims", None) is not None
            and len(args.action_dims) == 2
        )
        if args.mixer is not None:
            if self.dual_reward_training:
                self.route_mixer = self._build_mixer(args)
                self.signal_mixer = self._build_mixer(args)
                self.params += list(self.route_mixer.parameters())
                self.params += list(self.signal_mixer.parameters())
                self.target_route_mixer = copy.deepcopy(self.route_mixer)
                self.target_signal_mixer = copy.deepcopy(self.signal_mixer)
            else:
                self.mixer = self._build_mixer(args)
                self.params += list(self.mixer.parameters())
                self.target_mixer = copy.deepcopy(self.mixer)

        self.optimiser = RMSprop(params=self.params, lr=args.lr, alpha=args.optim_alpha, eps=args.optim_eps)

        # a little wasteful to deepcopy (e.g. duplicates action selector), but should work for any MAC
        self.target_mac = copy.deepcopy(mac)

        self.log_stats_t = -self.args.learner_log_interval - 1

    @staticmethod
    def _build_mixer(args):
        if args.mixer == "vdn":
            return VDNMixer()
        if args.mixer == "qmix":
            return QMixer(args)
        raise ValueError("Mixer {} not recognised.".format(args.mixer))

    def _head_slice(self, head_idx):
        offset = sum(int(x) for x in self.args.action_dims[:head_idx])
        dim = int(self.args.action_dims[head_idx])
        return offset, dim

    def _gather_head_qvals(self, q_values, actions, head_idx):
        offset, dim = self._head_slice(head_idx)
        head_q = q_values[:, :, :, offset:offset + dim]
        head_actions = actions[:, :, :, head_idx:head_idx + 1]
        return th.gather(head_q, dim=3, index=head_actions).squeeze(3)

    def _max_head_qvals(self, q_values, avail_actions, head_idx, live_q_values=None):
        offset, dim = self._head_slice(head_idx)
        head_q = q_values[:, :, :, offset:offset + dim].clone()
        head_avail = avail_actions[:, :, :, offset:offset + dim]
        head_q[head_avail == 0] = -9999999
        if live_q_values is None:
            return head_q.max(dim=3)[0]

        live = live_q_values[:, :, :, offset:offset + dim].clone()
        live[head_avail == 0] = -9999999
        max_actions = live.max(dim=3, keepdim=True)[1]
        return th.gather(head_q, 3, max_actions).squeeze(3)

    def _gather_chosen_qvals(self, q_values, actions):
        action_dims = getattr(self.args, "action_dims", None)
        if action_dims is None:
            return th.gather(q_values, dim=3, index=actions).squeeze(3)

        parts = []
        offset = 0
        train_heads = self._train_action_heads()
        for head_idx, dim in enumerate(action_dims):
            dim = int(dim)
            if head_idx in train_heads:
                head_q = q_values[:, :, :, offset:offset + dim]
                head_actions = actions[:, :, :, head_idx:head_idx + 1]
                parts.append(th.gather(head_q, dim=3, index=head_actions).squeeze(3))
            offset += dim
        return th.stack(parts, dim=-1).sum(dim=-1)

    def _max_qvals(self, q_values, avail_actions, live_q_values=None):
        action_dims = getattr(self.args, "action_dims", None)
        if action_dims is None:
            masked_q = q_values.clone()
            masked_q[avail_actions == 0] = -9999999
            if live_q_values is not None:
                live = live_q_values.clone()
                live[avail_actions == 0] = -9999999
                cur_max_actions = live.max(dim=3, keepdim=True)[1]
                return th.gather(masked_q, 3, cur_max_actions).squeeze(3)
            return masked_q.max(dim=3)[0]

        parts = []
        offset = 0
        train_heads = self._train_action_heads()
        for head_idx, dim in enumerate(action_dims):
            dim = int(dim)
            if head_idx in train_heads:
                head_q = q_values[:, :, :, offset:offset + dim].clone()
                head_avail = avail_actions[:, :, :, offset:offset + dim]
                head_q[head_avail == 0] = -9999999
                if live_q_values is not None:
                    live = live_q_values[:, :, :, offset:offset + dim].clone()
                    live[head_avail == 0] = -9999999
                    cur_max_actions = live.max(dim=3, keepdim=True)[1]
                    parts.append(th.gather(head_q, 3, cur_max_actions).squeeze(3))
                else:
                    parts.append(head_q.max(dim=3)[0])
            offset += dim
        return th.stack(parts, dim=-1).sum(dim=-1)

    def _train_action_heads(self):
        action_dims = getattr(self.args, "action_dims", None)
        if action_dims is None:
            return {0}
        configured = getattr(self.args, "train_action_heads", None)
        if configured is None:
            return set(range(len(action_dims)))
        return {int(x) for x in configured}

    def train(self, batch: EpisodeBatch, t_env: int, episode_num: int):
        # Get the relevant quantities
        rewards = batch["reward"][:, :-1]
        vehicle_rewards = batch["vehicle_reward"][:, :-1] if self.dual_reward_training else None
        signal_rewards = batch["signal_reward"][:, :-1] if self.dual_reward_training else None
        actions = batch["actions"][:, :-1]
        terminated = batch["terminated"][:, :-1].float()
        mask = batch["filled"][:, :-1].float()
        mask[:, 1:] = mask[:, 1:] * (1 - terminated[:, :-1])
        filled_mask = mask.clone()
        avail_actions = batch["avail_actions"]

        # Calculate estimated Q-Values
        mac_out = []
        self.mac.init_hidden(batch.batch_size)
        for t in range(batch.max_seq_length):
            agent_outs = self.mac.forward(batch, t=t)
            mac_out.append(agent_outs)
        mac_out = th.stack(mac_out, dim=1)  # Concat over time

        # Calculate the Q-Values necessary for the target
        target_mac_out = []
        self.target_mac.init_hidden(batch.batch_size)
        for t in range(batch.max_seq_length):
            target_agent_outs = self.target_mac.forward(batch, t=t)
            target_mac_out.append(target_agent_outs)

        # We don't need the first timesteps Q-Value estimate for calculating targets
        target_mac_out = th.stack(target_mac_out[1:], dim=1)  # Concat across time

        if self.dual_reward_training:
            active_heads = self._train_action_heads()
            head_results = {}
            if 0 in active_heads:
                head_results[0] = self._head_td_loss(
                    0, mac_out, target_mac_out, actions, avail_actions, batch,
                    vehicle_rewards, terminated, mask)
            if 1 in active_heads:
                head_results[1] = self._head_td_loss(
                    1, mac_out, target_mac_out, actions, avail_actions, batch,
                    signal_rewards, terminated, mask)
            if not head_results:
                raise ValueError("train_action_heads must contain route head 0 and/or signal head 1.")

            route_loss, route_stats = head_results.get(0, (None, None))
            signal_loss, signal_stats = head_results.get(1, (None, None))
            td_loss = sum(result[0] for result in head_results.values())
            loss = td_loss
            first_stats = next(iter(head_results.values()))[1]
            chosen_action_qvals = sum(result[1]["chosen"] for result in head_results.values())
            targets = sum(result[1]["targets"] for result in head_results.values())
            masked_td_error = sum(result[1]["masked_td_error"] for result in head_results.values())
            mask = first_stats["mask"]
        else:
            chosen_action_qvals = self._gather_chosen_qvals(mac_out[:, :-1], actions)
            if self.args.double_q:
                target_max_qvals = self._max_qvals(
                    target_mac_out, avail_actions[:, 1:], mac_out[:, 1:].detach())
            else:
                target_max_qvals = self._max_qvals(target_mac_out, avail_actions[:, 1:])

            if self.mixer is not None:
                chosen_action_qvals = self.mixer(chosen_action_qvals, batch["state"][:, :-1])
                target_max_qvals = self.target_mixer(target_max_qvals, batch["state"][:, 1:])

            targets = rewards + self.args.gamma * (1 - terminated) * target_max_qvals
            td_error = chosen_action_qvals - targets.detach()
            mask = mask.expand_as(td_error)
            masked_td_error = td_error * mask
            td_loss = (masked_td_error ** 2).sum() / mask.sum()
            loss = td_loss

        expert_supervised_loss = None
        expert_supervised_count = 0.0
        if getattr(self.args, "expert_action_supervised_enabled", False):
            if getattr(self.args, "action_dims", None) is not None:
                expert_actions = batch["expert_actions"][:, :-1].long()
                expert_mask = batch["expert_action_mask"][:, :-1].float()
            else:
                expert_actions = batch["expert_actions"][:, :-1].long().squeeze(-1)
                expert_mask = batch["expert_action_mask"][:, :-1].float().squeeze(-1)
            if getattr(self.args, "action_dims", None) is not None:
                expert_mask = expert_mask * filled_mask.unsqueeze(-1)
            else:
                expert_mask = expert_mask * filled_mask

            valid = expert_mask > 0
            expert_supervised_count = float(valid.sum().item())
            if expert_supervised_count > 0 and getattr(self.args, "action_dims", None) is None:
                logits = mac_out[:, :-1][valid]
                labels = expert_actions[valid]
                expert_supervised_loss = F.cross_entropy(logits, labels)
                loss = loss + self.args.expert_action_supervised_coef * expert_supervised_loss

        # Optimise
        self.optimiser.zero_grad()
        loss.backward()
        grad_norm = th.nn.utils.clip_grad_norm_(self.params, self.args.grad_norm_clip)
        self.optimiser.step()

        if (episode_num - self.last_target_update_episode) / self.args.target_update_interval >= 1.0:
            self._update_targets()
            self.last_target_update_episode = episode_num

        if t_env - self.log_stats_t >= self.args.learner_log_interval:
            self.logger.log_stat("loss", loss.item(), t_env)
            self.logger.log_stat("td_loss", td_loss.item(), t_env)
            if self.dual_reward_training:
                if route_loss is not None:
                    self.logger.log_stat("route_td_loss", route_loss.item(), t_env)
                    self.logger.log_stat("route_td_error_abs", route_stats["td_error_abs"], t_env)
                if signal_loss is not None:
                    self.logger.log_stat("signal_td_loss", signal_loss.item(), t_env)
                    self.logger.log_stat("signal_td_error_abs", signal_stats["td_error_abs"], t_env)
            if expert_supervised_loss is not None:
                self.logger.log_stat("expert_supervised_loss", expert_supervised_loss.item(), t_env)
                self.logger.log_stat("expert_supervised_count", expert_supervised_count, t_env)
            self.logger.log_stat("grad_norm", grad_norm, t_env)
            mask_elems = mask.sum().item()
            self.logger.log_stat("td_error_abs", (masked_td_error.abs().sum().item()/mask_elems), t_env)
            self.logger.log_stat("q_taken_mean", (chosen_action_qvals * mask).sum().item()/(mask_elems * self.args.n_agents), t_env)
            self.logger.log_stat("target_mean", (targets * mask).sum().item()/(mask_elems * self.args.n_agents), t_env)
            self.log_stats_t = t_env

    def _head_td_loss(
        self,
        head_idx,
        mac_out,
        target_mac_out,
        actions,
        avail_actions,
        batch,
        rewards,
        terminated,
        base_mask,
    ):
        chosen = self._gather_head_qvals(mac_out[:, :-1], actions, head_idx)
        live_next = mac_out[:, 1:].detach() if self.args.double_q else None
        target_max = self._max_head_qvals(
            target_mac_out, avail_actions[:, 1:], head_idx, live_next)

        mixer = self.route_mixer if head_idx == 0 else self.signal_mixer
        target_mixer = self.target_route_mixer if head_idx == 0 else self.target_signal_mixer
        if mixer is not None:
            chosen = mixer(chosen, batch["state"][:, :-1])
            target_max = target_mixer(target_max, batch["state"][:, 1:])

        targets = rewards + self.args.gamma * (1 - terminated) * target_max
        td_error = chosen - targets.detach()
        mask = base_mask.expand_as(td_error)
        masked_td_error = td_error * mask
        loss = (masked_td_error ** 2).sum() / mask.sum()
        stats = {
            "chosen": chosen,
            "targets": targets,
            "mask": mask,
            "masked_td_error": masked_td_error,
            "td_error_abs": masked_td_error.abs().sum().item() / mask.sum().item(),
        }
        return loss, stats

    def _update_targets(self):
        self.target_mac.load_state(self.mac)
        if self.dual_reward_training and self.route_mixer is not None:
            self.target_route_mixer.load_state_dict(self.route_mixer.state_dict())
            self.target_signal_mixer.load_state_dict(self.signal_mixer.state_dict())
        elif self.mixer is not None:
            self.target_mixer.load_state_dict(self.mixer.state_dict())
        self.logger.console_logger.info("Updated target network")

    def cuda(self):
        self.mac.cuda()
        self.target_mac.cuda()
        if self.dual_reward_training and self.route_mixer is not None:
            self.route_mixer.cuda()
            self.signal_mixer.cuda()
            self.target_route_mixer.cuda()
            self.target_signal_mixer.cuda()
        elif self.mixer is not None:
            self.mixer.cuda()
            self.target_mixer.cuda()

    def save_models(self, path):
        self.mac.save_models(path)
        if self.dual_reward_training and self.route_mixer is not None:
            th.save(self.route_mixer.state_dict(), "{}/route_mixer.th".format(path))
            th.save(self.signal_mixer.state_dict(), "{}/signal_mixer.th".format(path))
        elif self.mixer is not None:
            th.save(self.mixer.state_dict(), "{}/mixer.th".format(path))
        th.save(self.optimiser.state_dict(), "{}/opt.th".format(path))

    def load_models(self, path):
        self.mac.load_models(path)
        # Not quite right but I don't want to save target networks
        self.target_mac.load_models(path)
        if self.dual_reward_training and self.route_mixer is not None:
            route_path = "{}/route_mixer.th".format(path)
            signal_path = "{}/signal_mixer.th".format(path)
            legacy_path = "{}/mixer.th".format(path)
            if os.path.exists(route_path) and os.path.exists(signal_path):
                self.route_mixer.load_state_dict(th.load(route_path, map_location=lambda storage, loc: storage))
                self.signal_mixer.load_state_dict(th.load(signal_path, map_location=lambda storage, loc: storage))
            elif os.path.exists(legacy_path):
                legacy_state = th.load(legacy_path, map_location=lambda storage, loc: storage)
                self.route_mixer.load_state_dict(legacy_state)
                self.signal_mixer.load_state_dict(legacy_state)
            self.target_route_mixer.load_state_dict(self.route_mixer.state_dict())
            self.target_signal_mixer.load_state_dict(self.signal_mixer.state_dict())
        elif self.mixer is not None:
            self.mixer.load_state_dict(th.load("{}/mixer.th".format(path), map_location=lambda storage, loc: storage))
        if getattr(self.args, "skip_optimizer_load", False):
            return
        try:
            self.optimiser.load_state_dict(th.load("{}/opt.th".format(path), map_location=lambda storage, loc: storage))
        except ValueError:
            # Stage-wise training may freeze/unfreeze different parameter groups.
            # In that case, model weights are the important transfer; optimizer state can restart.
            pass
