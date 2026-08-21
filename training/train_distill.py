"""Build deployable 26-dimensional edge models from the formal SB3 DQNs.

Outputs per physical teacher:
  model_fp32.pt             exact TorchScript export
  model.onnx                exact portable ONNX export
  model_int8.pt             dynamically quantized TorchScript export
  model_int8.onnx           dynamically quantized ONNX export
  model_pruned_fp32.pt      structured-pruned + distilled TorchScript model
  model_pruned_int8.pt      quantized structured-pruned model
  metadata.json             provenance and offline fidelity results
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch
from torch import nn


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from edge_deploy.modeling import (
    ACTION_DIM,
    MODEL_INPUT_DIM,
    STATE_DIM,
    MaskedEdgeQNetwork,
    copy_formal_teacher,
    make_calibration_observations,
    sha256_file,
    structured_prune,
)


MODEL_SPECS = {
    "peak": PROJECT_ROOT / "models" / "dqn" / "dqn_multi_shared_real_peak_perf_1000000steps.zip",
    "evening": PROJECT_ROOT / "models" / "dqn" / "dqn_multi_shared_real_evening_perf_1000000steps.zip",
}


def quantize_dynamic(model: nn.Module) -> nn.Module:
    model = model.cpu().eval()
    try:
        from torch.ao.quantization import per_channel_dynamic_qconfig
        from torch.ao.quantization import quantize_dynamic as quantize
    except ImportError:
        from torch.quantization import per_channel_dynamic_qconfig
        from torch.quantization import quantize_dynamic as quantize
    # Per-channel weight scales materially improve action fidelity for this small
    # Q-network. Keep the four-output decision head in FP32 because its narrow
    # action margins make full INT8 quantization unnecessarily lossy.
    linear_names = [name for name, module in model.named_modules() if isinstance(module, nn.Linear)]
    qconfig_spec = {linear_names[0]: per_channel_dynamic_qconfig}
    return quantize(model, qconfig_spec).eval()


def save_torchscript(model: nn.Module, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    scripted = torch.jit.script(model.cpu().eval())
    torch.jit.save(scripted, str(path))


def export_onnx(model: nn.Module, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    dummy = torch.zeros(1, MODEL_INPUT_DIM, dtype=torch.float32)
    dummy[:, STATE_DIM:] = 1.0
    torch.onnx.export(
        model.cpu().eval(),
        dummy,
        str(path),
        input_names=["observations"],
        output_names=["q_values"],
        dynamic_axes={"observations": {0: "batch"}, "q_values": {0: "batch"}},
        opset_version=17,
        dynamo=False,
    )


def quantize_onnx(source: Path, destination: Path) -> None:
    from onnxruntime.quantization import QuantType, quantize_dynamic

    quantize_dynamic(
        str(source),
        str(destination),
        weight_type=QuantType.QInt8,
        per_channel=True,
        # ORT rewrites Gemm nodes to these MatMul names before quantization.
        # Quantize only the first hidden layer; keeping later layers in FP32
        # preserves the narrow action margins of the formal policy.
        nodes_to_exclude=["/core/core.2/Gemm_MatMul", "/core/core.4/Gemm_MatMul"],
    )


def distill_pruned(
    teacher: MaskedEdgeQNetwork,
    student: MaskedEdgeQNetwork,
    observations: np.ndarray,
    *,
    epochs: int,
    batch_size: int,
    learning_rate: float,
    seed: int,
) -> list[float]:
    torch.manual_seed(seed)
    state = torch.from_numpy(observations[:, :STATE_DIM])
    with torch.no_grad():
        targets = teacher.forward_core(state).detach()

    student.train()
    optimizer = torch.optim.Adam(student.parameters(), lr=learning_rate)
    losses: list[float] = []
    generator = torch.Generator().manual_seed(seed)
    for _ in range(epochs):
        permutation = torch.randperm(len(state), generator=generator)
        total_loss = 0.0
        batches = 0
        for start in range(0, len(state), batch_size):
            indices = permutation[start:start + batch_size]
            predicted = student.forward_core(state[indices])
            loss = nn.functional.smooth_l1_loss(predicted, targets[indices])
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            total_loss += float(loss.detach())
            batches += 1
        losses.append(total_loss / max(batches, 1))
    student.eval()
    return losses


def actions(model: nn.Module, observations: np.ndarray, batch_size: int = 2048) -> np.ndarray:
    output: list[np.ndarray] = []
    model.eval()
    with torch.no_grad():
        for start in range(0, len(observations), batch_size):
            q_values = model(torch.from_numpy(observations[start:start + batch_size]))
            output.append(q_values.argmax(dim=1).cpu().numpy())
    return np.concatenate(output)


def agreement(reference: np.ndarray, candidate: np.ndarray) -> float:
    return float(np.mean(reference == candidate))


def artifact_record(path: Path) -> dict[str, object]:
    return {
        "path": str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def build_one(args: argparse.Namespace, name: str, teacher_path: Path) -> dict[str, object]:
    if not teacher_path.is_file():
        raise FileNotFoundError(f"Formal teacher not found: {teacher_path}")
    from stable_baselines3 import DQN
    import training.masked_policy  # noqa: F401 - required to unpickle the custom policy

    print(f"[{name}] loading {teacher_path}", flush=True)
    sb3_model = DQN.load(str(teacher_path), device="cpu")
    teacher = copy_formal_teacher(sb3_model)
    output_dir = args.output_root / name
    output_dir.mkdir(parents=True, exist_ok=True)

    calibration = make_calibration_observations(args.calibration_samples, args.seed)
    validation = make_calibration_observations(args.validation_samples, args.seed + 1000)
    teacher_actions = actions(teacher, validation)

    pruned = structured_prune(teacher, args.prune_width)
    losses = distill_pruned(
        teacher,
        pruned,
        calibration,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        seed=args.seed,
    )

    fp32_path = output_dir / "model_fp32.pt"
    onnx_path = output_dir / "model.onnx"
    int8_path = output_dir / "model_int8.pt"
    int8_onnx_path = output_dir / "model_int8.onnx"
    pruned_path = output_dir / "model_pruned_fp32.pt"
    pruned_int8_path = output_dir / "model_pruned_int8.pt"

    save_torchscript(teacher, fp32_path)
    export_onnx(teacher, onnx_path)
    save_torchscript(quantize_dynamic(teacher), int8_path)
    quantize_onnx(onnx_path, int8_onnx_path)
    save_torchscript(pruned, pruned_path)
    save_torchscript(quantize_dynamic(pruned), pruned_int8_path)

    candidates = {
        "fp32": torch.jit.load(str(fp32_path), map_location="cpu"),
        "int8": torch.jit.load(str(int8_path), map_location="cpu"),
        "pruned_fp32": torch.jit.load(str(pruned_path), map_location="cpu"),
        "pruned_int8": torch.jit.load(str(pruned_int8_path), map_location="cpu"),
    }
    agreements = {
        key: agreement(teacher_actions, actions(candidate, validation))
        for key, candidate in candidates.items()
    }
    if agreements["int8"] < args.min_agreement:
        raise RuntimeError(f"{name}: INT8 action agreement {agreements['int8']:.3%} below target")
    if agreements["pruned_int8"] < args.min_agreement:
        raise RuntimeError(
            f"{name}: pruned INT8 action agreement {agreements['pruned_int8']:.3%} below target; "
            "increase --prune-width or --epochs"
        )

    artifacts = {
        "torchscript_fp32": artifact_record(fp32_path),
        "onnx_fp32": artifact_record(onnx_path),
        "torchscript_int8": artifact_record(int8_path),
        "onnx_int8": artifact_record(int8_onnx_path),
        "torchscript_pruned_fp32": artifact_record(pruned_path),
        "torchscript_pruned_int8": artifact_record(pruned_int8_path),
    }
    metadata: dict[str, object] = {
        "schema_version": "edge-model-v1",
        "source": {
            "path": str(teacher_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "sha256": sha256_file(teacher_path),
            "format": "stable-baselines3-dqn",
        },
        "contract": {
            "input_dimension": MODEL_INPUT_DIM,
            "state_dimension": STATE_DIM,
            "action_mask_dimension": ACTION_DIM,
            "action_count": ACTION_DIM,
            "model_contract_version": "shared-dqn-26x4-v1",
            "normalization": "none",
        },
        "structured_pruning": {
            "teacher_hidden_dims": [64, 64],
            "pruned_hidden_dims": [args.prune_width, args.prune_width],
            "calibration_samples": args.calibration_samples,
            "validation_samples": args.validation_samples,
            "epochs": args.epochs,
            "final_distillation_loss": losses[-1],
        },
        "offline_action_agreement": agreements,
        "artifacts": artifacts,
    }
    metadata_path = output_dir / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"[{name}] complete: int8={agreements['int8']:.2%}, "
        f"pruned_int8={agreements['pruned_int8']:.2%}",
        flush=True,
    )
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description="Export, quantize, prune and distill formal DQN models")
    parser.add_argument("--models", nargs="+", choices=sorted(MODEL_SPECS), default=sorted(MODEL_SPECS))
    parser.add_argument("--output-root", type=Path, default=PROJECT_ROOT / "models" / "edge")
    parser.add_argument("--calibration-samples", type=int, default=20000)
    parser.add_argument("--validation-samples", type=int, default=5000)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=512)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--prune-width", type=int, default=56)
    parser.add_argument("--min-agreement", type=float, default=0.95)
    parser.add_argument("--seed", type=int, default=20260820)
    args = parser.parse_args()
    args.output_root = args.output_root.resolve()
    if not 0.0 < args.min_agreement <= 1.0:
        parser.error("--min-agreement must be in (0, 1]")

    summaries = [build_one(args, name, MODEL_SPECS[name]) for name in args.models]
    manifest = {
        "schema_version": "edge-manifest-v1",
        "models": {name: summary for name, summary in zip(args.models, summaries, strict=True)},
    }
    args.output_root.mkdir(parents=True, exist_ok=True)
    (args.output_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Manifest: {args.output_root / 'manifest.json'}")


if __name__ == "__main__":
    main()
