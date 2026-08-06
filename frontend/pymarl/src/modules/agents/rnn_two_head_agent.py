import torch as th
import torch.nn as nn
import torch.nn.functional as F


class RNNTwoHeadAgent(nn.Module):
    """Type-specific recurrent Q network for vehicles and traffic lights.

    The Unity observation reserves one field for object type:
      0 = emergency vehicle
      1 = traffic light

    Vehicles and traffic lights use separate encoders, recurrent transitions, and
    output heads. The returned hidden state keeps the same shape as the standard
    PyMARL RNN agent, so existing MACs and learners can use this agent unchanged.
    """

    def __init__(self, input_shape, args):
        super(RNNTwoHeadAgent, self).__init__()
        self.args = args
        self.object_type_index = int(getattr(args, "object_type_index", 8))

        self.vehicle_fc1 = nn.Linear(input_shape, args.rnn_hidden_dim)
        self.vehicle_rnn = nn.GRUCell(args.rnn_hidden_dim, args.rnn_hidden_dim)
        self.vehicle_head = nn.Linear(args.rnn_hidden_dim, args.n_actions)

        self.traffic_fc1 = nn.Linear(input_shape, args.rnn_hidden_dim)
        self.traffic_rnn = nn.GRUCell(args.rnn_hidden_dim, args.rnn_hidden_dim)
        self.traffic_head = nn.Linear(args.rnn_hidden_dim, args.n_actions)

    def init_hidden(self):
        return self.vehicle_fc1.weight.new(1, self.args.rnn_hidden_dim).zero_()

    def forward(self, inputs, hidden_state):
        if self.object_type_index < 0 or self.object_type_index >= inputs.shape[1]:
            raise ValueError(
                f"object_type_index={self.object_type_index} is outside input width {inputs.shape[1]}"
            )

        h_in = hidden_state.reshape(-1, self.args.rnn_hidden_dim)

        vehicle_x = F.relu(self.vehicle_fc1(inputs))
        vehicle_h = self.vehicle_rnn(vehicle_x, h_in)
        vehicle_q = self.vehicle_head(vehicle_h)

        traffic_x = F.relu(self.traffic_fc1(inputs))
        traffic_h = self.traffic_rnn(traffic_x, h_in)
        traffic_q = self.traffic_head(traffic_h)

        object_type = inputs[:, self.object_type_index]
        is_traffic = object_type > 0.5
        q = th.where(is_traffic.unsqueeze(1), traffic_q, vehicle_q)
        h = th.where(is_traffic.unsqueeze(1), traffic_h, vehicle_h)
        return q, h
