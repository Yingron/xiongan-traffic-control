"""LLM 输出解析工具：从模型输出中提取 JSON 并归一化事件类别。

供 llm_train/evaluate.py（离线评估）与 server/llm_service.py（在线服务）共用。
"""
from __future__ import annotations

import json
import re

from llm_data.schema import EVENT_CLASSES, EVENT_EN


def extract_json(text: str) -> dict | None:
    """从模型输出中提取 JSON。容忍前后杂讯、单引号等常见偏差。"""
    if not text:
        return None
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    candidate = text[start:end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass
    try:
        return json.loads(candidate, strict=False)
    except json.JSONDecodeError:
        pass
    # 至少提取 event 字段
    m = re.search(r'"event"\s*:\s*"([^"]+)"', candidate)
    if m:
        return {"event": m.group(1)}
    return None


def normalize_event(value: str) -> str | None:
    """把模型输出的事件值归一化到四类中文标签（容忍英文输出）。"""
    if value in EVENT_CLASSES:
        return value
    for cn, en in EVENT_EN.items():
        if value.lower() == en:
            return cn
    return None
