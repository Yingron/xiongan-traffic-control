REGISTRY = {}

from .rnn_agent import RNNAgent
REGISTRY["rnn"] = RNNAgent

from .rnn_two_head_agent import RNNTwoHeadAgent
REGISTRY["rnn_two_head"] = RNNTwoHeadAgent

from .rnn_dual_function_agent import RNNDualFunctionAgent
REGISTRY["rnn_dual_function"] = RNNDualFunctionAgent
