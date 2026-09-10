"""验证 WebSocket 告警广播（步骤⑥）：REST /llm/analyze → 8765 llm_alert 广播。

从训练集挑一条真实样本 POST 到 api_server(:8000) /api/v1/llm/analyze，
同时以 WS 监听 8765 —— 断言所有前端（Unity 告警面板）能收到该次云脑分析的
广播（source=rest、junction 与事件类别与 REST 应答一致）：

    python scripts/test_llm_rest_broadcast.py                 # 默认拥堵样本 J12
    python scripts/test_llm_rest_broadcast.py --api-port 8000 --ws-port 8765 --timeout 120

前提：llama-server(:8081)、visualization_server(:8765)、api_server(:8000) 均已启动。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import urllib.error
import urllib.request

import websockets

# 默认选"拥堵"类样本做内容级断言；可选 normal/congestion/spillover/incident 的中文标签
EVENT_FILTER = "拥堵"


def _pick_sample(event_filter: str) -> dict:
    """从平衡训练集挑一条指定类别的真实样本（确定性：取第一条）。"""
    path = "data/llm/split_balanced.jsonl"
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            item = json.loads(line)
            if item.get("event") == event_filter:
                junction = re.search(r"路口\s*(J\d{2})", item["text"])
                return {
                    "text": item["text"],
                    "expected_event": item["event"],
                    "junction": junction.group(1) if junction else None,
                }
    raise SystemExit(f"[test] 训练集中未找到 {event_filter} 类样本")


def _post_analyze(host: str, port: int, payload: dict) -> dict:
    url = f"http://{host}:{port}/api/v1/llm/analyze"
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body,
                                     headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


async def main() -> int:
    parser = argparse.ArgumentParser(description="验证 REST 云脑分析 → WebSocket 告警广播")
    parser.add_argument("--api-host", default="127.0.0.1")
    parser.add_argument("--api-port", type=int, default=8000)
    parser.add_argument("--ws-host", default="127.0.0.1")
    parser.add_argument("--ws-port", type=int, default=8765)
    parser.add_argument("--event", default=EVENT_FILTER, help="样本事件类别（正常/拥堵/溢出/事件）")
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()

    sample = _pick_sample(args.event)
    if sample["junction"] is None:
        print("[test] FAIL: 样本文本中未找到路口 ID")
        return 1
    print(f"[test] 样本: 路口 {sample['junction']} | 期望事件 {sample['expected_event']} | "
          f"文本 {len(sample['text'])} 字符")

    # 1) 先挂 WS 监听（8765），等 REST 分析完成后的广播
    uri = f"ws://{args.ws_host}:{args.ws_port}"
    print(f"[test] 连接 {uri} 监听 llm_alert 广播 ...")
    async with websockets.connect(uri, open_timeout=10) as ws:
        connected = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
        print(f"[test] connected: {connected.get('scenario_label')} | "
              f"模型={connected.get('model_id') or 'none'}")

        # 2) REST 触发云脑分析（约 5~9 秒）
        payload = {"text": sample["text"], "junction": sample["junction"]}
        print(f"[test] POST /api/v1/llm/analyze (junction={sample['junction']})，等待分析...")
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None, _post_analyze, args.api_host, args.api_port, payload)
        except urllib.error.HTTPError as error:
            print(f"[test] FAIL: REST 返回 HTTP {error.code} — {error.read().decode('utf-8', 'ignore')[:300]}")
            return 1
        rest_event = result.get("event")
        print(f"[test] REST 应答: 事件={rest_event} (en={result.get('event_en')}) | "
              f"置信度={result.get('confidence')} | 耗时={result.get('latency_ms')}ms")

        # 3) 等待 WS 广播（跳过自动诊断 source=auto 与 state 消息）
        deadline = asyncio.get_event_loop().time() + args.timeout
        state_count = 0
        while True:
            remain = deadline - asyncio.get_event_loop().time()
            if remain <= 0:
                print("[test] FAIL: 超时未收到 REST 广播的 llm_alert")
                return 1
            raw = await asyncio.wait_for(ws.recv(), timeout=remain)
            msg = json.loads(raw)
            msg_type = msg.get("type", "")

            if msg_type == "state":
                state_count += 1
                continue
            if msg_type == "llm_alert" and msg.get("source") != "rest":
                print(f"[test] 收到自动诊断 llm_alert (source={msg.get('source')}, "
                      f"junction={msg.get('junction')})，跳过（等 REST 广播）...")
                continue
            if msg_type == "llm_alert":
                ok = (msg.get("junction") == sample["junction"]
                      and msg.get("event") == rest_event
                      and msg.get("source") == "rest")
                print(f"[test] {'PASS' if ok else 'FAIL'}: REST 广播 llm_alert 收到")
                print(f"  路口    : {msg.get('junction')}（期望 {sample['junction']}）")
                print(f"  事件    : {msg.get('event')} (en={msg.get('event_en')})"
                      + (f"（与 REST 应答一致）" if msg.get("event") == rest_event else f"（REST 应答为 {rest_event}）"))
                print(f"  置信度  : {msg.get('confidence')}")
                print(f"  建议    : {msg.get('advice')}")
                print(f"  仿真    : {msg.get('sim_clock')} (第 {msg.get('sim_time')}s)")
                print(f"  来源    : {msg.get('source')} | 耗时 {msg.get('latency_ms')} ms | "
                      f"后端 {msg.get('llm_backend')}")
                return 0 if ok else 1
            if msg_type == "llm_alert_error":
                print(f"[test] 收到 llm_alert_error — {msg.get('message')}（继续等待 REST 广播）...")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
