import torch as th
import torch.nn as nn
import torch.nn.functional as F


class RNNDualFunctionAgent(nn.Module):
    """Two independent recurrent Q networks for intersection control.

    route_net:  selects the vehicle next-hop action.
    signal_net: selects the binary signal switch action.

    Agent parameters are still shared across intersections by BasicMAC; the split
    is by function, not by individual intersection.
    """

    def __init__(self, input_shape, args):
        super(RNNDualFunctionAgent, self).__init__()
        self.args = args
        self.action_dims = [int(x) for x in getattr(args, "action_dims", [5, 2])]
        if len(self.action_dims) != 2:
            raise ValueError("RNNDualFunctionAgent expects action_dims=[route_dim, signal_dim].")

        h = args.rnn_hidden_dim
        self.route_fc1 = nn.Linear(input_shape, h)
        self.route_rnn = nn.GRUCell(h, h)
        self.route_head = nn.Linear(h, self.action_dims[0])

        self.signal_fc1 = nn.Linear(input_shape, h)
        self.signal_rnn = nn.GRUCell(h, h)
        self.signal_head = nn.Linear(h, self.action_dims[1])

        if getattr(args, "freeze_route_net", False):
            self._set_route_requires_grad(False)
        if getattr(args, "freeze_signal_net", False):
            self._set_signal_requires_grad(False)

    def _set_route_requires_grad(self, requires_grad):
        for module in (self.route_fc1, self.route_rnn, self.route_head):
            for p in module.parameters():
                p.requires_grad = requires_grad

    def _set_signal_requires_grad(self, requires_grad):
        for module in (self.signal_fc1, self.signal_rnn, self.signal_head):
            for p in module.parameters():
                p.requires_grad = requires_grad

    def init_hidden(self):
        h = self.args.rnn_hidden_dim
        return self.route_fc1.weight.new(1, h * 2).zero_()

    def forward(self, inputs, hidden_state):
        h = self.args.rnn_hidden_dim
        h_in = hidden_state.reshape(-1, h * 2)
        route_h_in = h_in[:, :h]
        signal_h_in = h_in[:, h:]

        route_x = F.relu(self.route_fc1(inputs))
        route_h = self.route_rnn(route_x, route_h_in)
        route_q = self.route_head(route_h)

        signal_x = F.relu(self.signal_fc1(inputs))
        signal_h = self.signal_rnn(signal_x, signal_h_in)
        signal_q = self.signal_head(signal_h)

        q = th.cat([route_q, signal_q], dim=-1)
        next_h = th.cat([route_h, signal_h], dim=-1)
        return q, next_h
