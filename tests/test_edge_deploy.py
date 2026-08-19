"""Acceptance checks for generated lightweight edge artifacts."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from edge_deploy.inference import EdgeInference
from edge_deploy.modeling import ACTION_DIM, MODEL_INPUT_DIM, STATE_DIM, sha256_file


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EDGE_ROOT = PROJECT_ROOT / "models" / "edge"


@pytest.mark.parametrize("name", ["peak", "evening"])
def test_recommended_onnx_model_preserves_contract_and_masks(name: str) -> None:
    model_path = EDGE_ROOT / name / "model.onnx"
    inference = EdgeInference(model_path, warmup=1)

    observations = np.zeros((8, MODEL_INPUT_DIM), dtype=np.float32)
    expected = np.arange(8, dtype=np.int64) % ACTION_DIM
    observations[np.arange(8), STATE_DIM + expected] = 1.0
    actions, latency = inference.predict(observations)

    assert np.asarray(actions).tolist() == expected.tolist()
    assert latency >= 0.0


def test_22_state_requires_explicit_action_mask() -> None:
    inference = EdgeInference(EDGE_ROOT / "peak" / "model_int8.onnx", warmup=0)
    with pytest.raises(ValueError, match="requires a four-value action_mask"):
        inference.predict(np.zeros(STATE_DIM, dtype=np.float32))


def test_edge_manifest_checksums_and_validation_report() -> None:
    manifest = json.loads((EDGE_ROOT / "manifest.json").read_text(encoding="utf-8"))
    report = json.loads((EDGE_ROOT / "validation_report.json").read_text(encoding="utf-8"))
    assert report["status"] == "PASS"

    for name in ("peak", "evening"):
        assert report["models"][name]["recommended_artifact"] == "model.onnx"
        metadata = manifest["models"][name]
        assert metadata["contract"]["input_dimension"] == MODEL_INPUT_DIM
        for artifact in metadata["artifacts"].values():
            path = PROJECT_ROOT / artifact["path"]
            assert path.is_file()
            assert path.stat().st_size == artifact["size_bytes"]
            assert sha256_file(path) == artifact["sha256"]


def test_ready_edge_registry_entries_match_artifacts() -> None:
    registry = json.loads(
        (PROJECT_ROOT / "configs" / "edge_model_registry.json").read_text(encoding="utf-8")
    )
    for entry in registry["models"].values():
        path = PROJECT_ROOT / entry["artifact_path"]
        assert path.is_file()
        assert path.stat().st_size == entry["size_bytes"]
        assert sha256_file(path) == entry["sha256"]
        if entry["status"] == "ready":
            assert entry["real_state_action_agreement"] >= 0.95
