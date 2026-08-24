"""HTTP service for formal 26-dimensional ONNX edge inference.

The service deliberately accepts either a single local state or a batch of
30 states.  The latter is the deployment path used by ``server.api_server``:
the API receives its 660-dimensional snapshot, reconstructs thirty 22-D
local states, supplies the absolute 4-action masks, and forwards them here.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from edge_deploy.inference import DEFAULT_MODEL, EdgeInference


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = PROJECT_ROOT / "configs" / "edge_model_registry.json"


class PredictRequest(BaseModel):
    model_id: str | None = Field(default=None, min_length=1)
    state: list[float] | list[list[float]]
    action_mask: list[float] | list[list[float]] | None = None


def _registry_models() -> dict[str, dict[str, Any]]:
    with REGISTRY_PATH.open("r", encoding="utf-8") as source:
        return json.load(source)["models"]


def _configured_model() -> Path:
    return Path(os.environ.get("EDGE_MODEL_PATH", str(DEFAULT_MODEL))).resolve()


@lru_cache(maxsize=4)
def _inference_for(model_id: str | None) -> EdgeInference:
    if model_id is None:
        return EdgeInference(_configured_model())
    item = _registry_models().get(model_id)
    if item is None:
        raise KeyError(model_id)
    if item.get("status") != "ready":
        raise ValueError(f"model '{model_id}' is not approved for deployment")
    return EdgeInference(PROJECT_ROOT / item["artifact_path"])


app = FastAPI(title="Xiongan ONNX Edge Inference", version="1.0.0")


@app.get("/health")
def health() -> dict[str, Any]:
    try:
        engine = _inference_for(None)
    except (FileNotFoundError, ValueError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return {
        "status": "healthy",
        "backend": engine.backend,
        "model_path": str(engine.model_path),
        "input_dimension": 26,
        "state_dimension": 22,
        "action_count": 4,
    }


@app.post("/predict")
def predict(request: PredictRequest) -> dict[str, Any]:
    try:
        engine = _inference_for(request.model_id)
        observations, was_single = engine.prepare_observations(request.state, request.action_mask)
        q_values, latency_ms = engine.predict_q(observations)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=f"unknown edge model id: {error.args[0]}") from error
    except (FileNotFoundError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    q_rows = np.asarray(q_values, dtype=np.float32)
    actions = np.argmax(q_rows, axis=1).astype(int).tolist()
    return {
        "model_id": request.model_id,
        "backend": engine.backend,
        "actions": actions,
        "q_values": q_rows.tolist(),
        "latency_ms": latency_ms,
        "batch_size": int(len(observations)),
    }
