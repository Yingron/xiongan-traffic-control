import torch as th
from torch.distributions import Categorical
from .epsilon_schedules import DecayThenFlatSchedule

REGISTRY = {}


class MultinomialActionSelector():

    def __init__(self, args):
        self.args = args
        self.action_dims = getattr(args, "action_dims", None)
        self.force_noop_action_heads = set(getattr(args, "force_noop_action_heads", []) or [])
        explore_heads = getattr(args, "explore_action_heads", None)
        self.explore_action_heads = None if explore_heads is None else set(explore_heads)

        self.schedule = DecayThenFlatSchedule(args.epsilon_start, args.epsilon_finish, args.epsilon_anneal_time,
                                              decay="linear")
        self.epsilon = self.schedule.eval(0)
        self.test_greedy = getattr(args, "test_greedy", True)

    def select_action(self, agent_inputs, avail_actions, t_env, test_mode=False):
        masked_policies = agent_inputs.clone()
        masked_policies[avail_actions == 0.0] = 0.0

        self.epsilon = self.schedule.eval(t_env)

        if test_mode and self.test_greedy:
            picked_actions = masked_policies.max(dim=2)[1]
        else:
            picked_actions = Categorical(masked_policies).sample().long()

        return picked_actions


REGISTRY["multinomial"] = MultinomialActionSelector


class EpsilonGreedyActionSelector():

    def __init__(self, args):
        self.args = args
        self.action_dims = getattr(args, "action_dims", None)
        self.force_noop_action_heads = set(getattr(args, "force_noop_action_heads", []) or [])
        explore_heads = getattr(args, "explore_action_heads", None)
        self.explore_action_heads = None if explore_heads is None else set(explore_heads)

        self.schedule = DecayThenFlatSchedule(args.epsilon_start, args.epsilon_finish, args.epsilon_anneal_time,
                                              decay="linear")
        self.epsilon = self.schedule.eval(0)

    def select_action(self, agent_inputs, avail_actions, t_env, test_mode=False):

        # Assuming agent_inputs is a batch of Q-Values for each agent bav
        self.epsilon = self.schedule.eval(t_env)

        if test_mode:
            # Greedy action selection only
            self.epsilon = 0.0

        if self.action_dims is not None:
            return self._select_multidiscrete_action(agent_inputs, avail_actions)

        # mask actions that are excluded from selection
        masked_q_values = agent_inputs.clone()
        masked_q_values[avail_actions == 0.0] = -float("inf")  # should never be selected!

        random_numbers = th.rand_like(agent_inputs[:, :, 0])
        pick_random = (random_numbers < self.epsilon).long()
        random_actions = Categorical(avail_actions.float()).sample().long()

        picked_actions = pick_random * random_actions + (1 - pick_random) * masked_q_values.max(dim=2)[1]
        return picked_actions

    def _select_multidiscrete_action(self, agent_inputs, avail_actions):
        picked = []
        offset = 0
        for dim in self.action_dims:
            head_idx = len(picked)
            dim = int(dim)
            head_q = agent_inputs[:, :, offset:offset + dim]
            head_avail = avail_actions[:, :, offset:offset + dim]

            masked_q_values = head_q.clone()
            masked_q_values[head_avail == 0.0] = -float("inf")

            if head_idx in self.force_noop_action_heads:
                picked.append(th.zeros_like(head_q[:, :, 0]).long())
                offset += dim
                continue

            random_numbers = th.rand_like(head_q[:, :, 0])
            head_epsilon = self.epsilon
            if self.explore_action_heads is not None and head_idx not in self.explore_action_heads:
                head_epsilon = 0.0
            pick_random = (random_numbers < head_epsilon).long()
            random_actions = Categorical(head_avail.float()).sample().long()
            greedy_actions = masked_q_values.max(dim=2)[1]
            picked.append(pick_random * random_actions + (1 - pick_random) * greedy_actions)
            offset += dim

        return th.stack(picked, dim=-1)


REGISTRY["epsilon_greedy"] = EpsilonGreedyActionSelector
