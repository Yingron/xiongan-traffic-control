"""LLM 云脑分析服务：调用 llama.cpp（OpenAI 兼容 /chat/completions）做交通事件识别。

部署形态（赛道 C 步骤④）：
    llama-server 独立进程（Windows 本地或 Docker 容器）加载 INT4 GGUF 模型，
    本模块经 HTTP 调用；xiongan-api 通过 /api/v1/llm/analyze 暴露给前端。

环境变量：
    LLM_BASE_URL   llama-server 地址，默认 http://127.0.0.1:8081/v1
    LLM_MODEL      GGUF 模型名（llama-server 端配置的 alias），默认 qwen-traffic
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

from llm_data.parsing import extract_json, normalize_event
from llm_data.schema import EVENT_CLASSES

SYSTEM_PROMPT = (
    "你是雄安新区'城市大脑'的交通管控分析助手。根据路口交通状态文本，"
    "判断当前属于哪类交通事件（正常/拥堵/溢出/事件），并给出信号管控建议。"
    "只输出 JSON：{\"event\": \"正常|拥堵|溢出|事件\", \"confidence\": 0.0~1.0, \"advice\": \"中文管控建议\"}"
)


class LLMServiceError(Exception):
    """LLM 服务错误，可安全返回给调用方。"""

    def __init__(self, status_code: int, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


class LLMService:
    """封装对 llama-server 的调用与结果校验。"""

    def __init__(self, base_url: str | None = None, model: str | None = None,
                 timeout: float = 30.0, max_new_tokens: int = 160) -> None:
        self.base_url = (base_url or os.environ.get("LLM_BASE_URL", "http://127.0.0.1:8081/v1")).rstrip("/")
        self.model = model or os.environ.get("LLM_MODEL", "qwen-traffic")
        self.timeout = timeout
        self.max_new_tokens = max_new_tokens

    def analyze(self, text: str, junction: str | None = None) -> dict[str, Any]:
        """分析一个路口的交通状态文本，返回结构化事件判定。

        Returns:
            {"junction", "event", "event_en", "confidence", "advice",
             "raw", "latency_ms", "llm_backend", "llm_model"}
        """
        # 注意：不加 system 消息——微调数据只有 user+assistant 两段，
        # 加 system 会让 0.5B 模型行为偏移（实测事件识别从 100% 掉到 ~0%）。
        payload = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": text},
            ],
            "temperature": 0.0,
            "max_tokens": self.max_new_tokens,
        }
        endpoint = f"{self.base_url}/chat/completions"
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(endpoint, data=body,
                                         headers={"Content-Type": "application/json"}, method="POST")
        t0 = time.time()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as error:
            raise LLMServiceError(503, "LLM_SERVICE_UNAVAILABLE",
                                  "The LLM service is unreachable. Start llama-server first.",
                                  {"endpoint": endpoint, "reason": str(error)}) from error
        except (OSError, ValueError) as error:
            raise LLMServiceError(503, "LLM_SERVICE_INVALID_RESPONSE",
                                  "The LLM service returned invalid data.", {"reason": str(error)}) from error
        latency_ms = round((time.time() - t0) * 1000, 1)

        try:
            raw = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise LLMServiceError(502, "LLM_BAD_RESPONSE",
                                  "The LLM response is missing the content field.",
                                  {"response_keys": sorted(data)}) from error

        parsed = extract_json(raw)
        if parsed is None:
            raise LLMServiceError(502, "LLM_PARSE_FAILED",
                                  "The LLM output could not be parsed as JSON.", {"raw": raw})
        event = normalize_event(parsed.get("event"))
        if event not in EVENT_CLASSES:
            raise LLMServiceError(422, "LLM_INVALID_EVENT",
                                  f"Unknown event value: {parsed.get('event')!r}", {"raw": raw})

        confidence = parsed.get("confidence")
        if not isinstance(confidence, (int, float)) or not (0.0 <= float(confidence) <= 1.0):
            confidence = None

        return {
            "junction": junction,
            "event": event,
            "event_en": {"正常": "normal", "拥堵": "congestion", "溢出": "spillover", "事件": "incident"}[event],
            "confidence": float(confidence) if confidence is not None else None,
            "advice": parsed.get("advice"),
            "raw": raw,
            "latency_ms": latency_ms,
            "llm_backend": "llama.cpp",
            "llm_model": self.model,
        }
