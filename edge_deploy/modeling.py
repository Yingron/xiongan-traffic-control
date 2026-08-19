"""Shared 26-dimensional edge-deployment model definitions.

The formal SB3 model advertises a 26-value observation, but its MLP consumes
the first 22 state features and applies the final four action-mask values to
the four Q outputs.  Every exported backend must preserve that exact contract.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable

import numpy as np
import torch
from torch import nn


STATE_DIM = 22
ACTION_DIM = 4
MODEL_INPUT_DIM = STATE_DIM + ACTION_DIM
MASK_FILL = 3.0e38


class MaskedEdgeQNetwork(nn.Module):
    """Portable Q-network with the formal 22-state + 4-mask contract."""

    def __init__(self, hidden_dims: Iterable[int] = (64, 64)) -> None:
        super().__init__()
        dims = [STATE_DIM, *[int(value) for value in hidden_dims], ACTION_DIM]
        layers: list[nn.Module] = []
        for index, (input_dim, output_dim) in enumerate(zip(dims, dims[1:])):
            layers.append(nn.Linear(input_dim, output_dim))
            if index < len(dims) - 2:
                layers.append(nn.ReLU())
        self.core = nn.Sequential(*layers)

    def forward(self, observations: torch.Tensor) -> torch.Tensor:
        # Literal slice bounds keep this module portable across TorchScript and ONNX.
        state = observations[..., :22]
        mask = observations[..., 22:26]
        q_values = self.core(state)
        return q_values * mask - (1.0 - mask) * 3.0e38

    def forward_core(self, state: torch.Tensor) -> torch.Tensor:
        return self.core(state)


def linear_layers(module: nn.Module) -> list[nn.Linear]:
    return [layer for layer in module.modules() if isinstance(layer, nn.Linear)]


def copy_formal_teacher(sb3_model) -> MaskedEdgeQNetwork:
    """Copy the formal SB3 online Q-network into a portable edge module."""
    source_layers = linear_layers(sb3_model.policy.q_net.q_net)
    hidden_dims = [layer.out_features for layer in source_layers[:-1]]
    target = MaskedEdgeQNetwork(hidden_dims)
    target_layers = linear_layers(target.core)
    if len(source_layers) != len(target_layers):
        raise ValueError("Unsupported formal Q-network structure")
    with torch.no_grad():
        for source, destination in zip(source_layers, target_layers, strict=True):
            destination.weight.copy_(source.weight.detach().cpu())
            destination.bias.copy_(source.bias.detach().cpu())
    return target.eval()


def structured_prune(source: MaskedEdgeQNetwork, width: int) -> MaskedEdgeQNetwork:
    """Physically remove low-importance neurons from both hidden layers."""
    source_layers = linear_layers(source.core)
    if len(source_layers) != 3:
        raise ValueError("Structured pruning currently supports two hidden layers")
    first, second, output = source_layers
    if not 0 < width <= min(first.out_features, second.out_features):
        raise ValueError("prune width must be between 1 and the teacher hidden width")

    first_importance = (
        first.weight.detach().abs().sum(dim=1)
        + first.bias.detach().abs()
        + second.weight.detach().abs().sum(dim=0)
    )
    keep_first = torch.topk(first_importance, width, sorted=True).indices.sort().values
    second_importance = (
        second.weight.detach()[:, keep_first].abs().sum(dim=1)
        + second.bias.detach().abs()
        + output.weight.detach().abs().sum(dim=0)
    )
    keep_second = torch.topk(second_importance, width, sorted=True).indices.sort().values

    pruned = MaskedEdgeQNetwork((width, width))
    pruned_first, pruned_second, pruned_output = linear_layers(pruned.core)
    with torch.no_grad():
        pruned_first.weight.copy_(first.weight.detach()[keep_first])
        pruned_first.bias.copy_(first.bias.detach()[keep_first])
        pruned_second.weight.copy_(second.weight.detach()[keep_second][:, keep_first])
        pruned_second.bias.copy_(second.bias.detach()[keep_second])
        pruned_output.weight.copy_(output.weight.detach()[:, keep_second])
        pruned_output.bias.copy_(output.bias.detach())
    return pruned.eval()


def make_calibration_observations(samples: int, seed: int) -> np.ndarray:
    """Generate normalized, contract-shaped observations for distillation QA."""
    if samples < 1:
        raise ValueError("samples must be positive")
    rng = np.random.default_rng(seed)
    observations = np.zeros((samples, MODEL_INPUT_DIM), dtype=np.float32)
    observations[:, :16] = rng.random((samples, 16), dtype=np.float32)
    phases = rng.integers(0, ACTION_DIM, size=samples)
    observations[np.arange(samples), 16 + phases] = 1.0
    angles = rng.uniform(0.0, 2.0 * np.pi, size=samples)
    observations[:, 20] = np.sin(angles)
    observations[:, 21] = np.cos(angles)

    observations[:, STATE_DIM:] = 1.0
    gated_rows = rng.random(samples) < 0.15
    if np.any(gated_rows):
        gated = (rng.random((int(gated_rows.sum()), ACTION_DIM)) > 0.45).astype(np.float32)
        empty = np.flatnonzero(gated.sum(axis=1) == 0)
        gated[empty, rng.integers(0, ACTION_DIM, size=len(empty))] = 1.0
        observations[gated_rows, STATE_DIM:] = gated
    return observations


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
