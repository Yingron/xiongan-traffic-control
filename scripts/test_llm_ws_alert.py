"""验证 LLM 云脑告警 WebSocket 链路（Unity 告警面板后端链路）。

请求 visualization_server 触发一次云脑诊断，等待 llm_alert 推送并打印：
    python scripts/test_llm_ws_alert.py                          # 自动选最异常路口
    python scripts/test_llm_ws_alert.py --junction J25           # 指定路口
    python scripts/test_llm_ws_alert.py --port 8765 --timeout 90

前提：llama-server(:8081) 与 visualization_server(:8765) 已启动。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

import websockets

EXPECTED_KEYS = ("junction", "event", "event_en", "confidence", "advice",
                 "latency_ms", "sim_time", "sim_clock", "scenario")


async def main() -> int:
    parser = argparse.ArgumentParser(description="验证 LLM 云脑告警 WebSocket 链路")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--junction", default=None,
                        help="指定诊断路口（缺省由后端规则自动选最异常路口）")
    parser.add_argument("--timeout", type=float, default=90.0, help="总超时秒数")
    args = parser.parse_args()

    uri = f"ws://{args.host}:{args.port}"
    print(f"[test] 连接 {uri} ...")

    async with websockets.connect(uri, open_timeout=10) as ws:
        connected = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
        print(f"[test] connected: {connected.get('type')} | "
              f"场景={connected.get('scenario_label')} | "
              f"模型={connected.get('model_id') or 'none'}")

        request = {"type": "request_llm_alert"}
        if args.junction:
            request["junction"] = args.junction
        await ws.send(json.dumps(request, ensure_ascii=False))
        print(f"[test] 已发送 request_llm_alert "
              f"(junction={args.junction or 'auto'})，等待云脑诊断（约 5~9 秒）...")

        deadline = asyncio.get_event_loop().time() + args.timeout
        state_count = 0
        while True:
            remain = deadline - asyncio.get_event_loop().time()
            if remain <= 0:
                print("[test] FAIL: 超时未收到 llm_alert")
                return 1
            raw = await asyncio.wait_for(ws.recv(), timeout=remain)
            msg = json.loads(raw)
            msg_type = msg.get("type", "")

            if msg_type == "state":
                state_count += 1
                if state_count % 20 == 1:
                    print(f"[test] 收到 state ×{state_count}（跳过，等待告警）...")
                continue
            if msg_type == "llm_alert":
                missing = [k for k in EXPECTED_KEYS if k not in msg]
                print(f"[test] PASS: llm_alert 收到")
                print(f"  路口    : {msg.get('junction')}")
                print(f"  事件    : {msg.get('event')} (en={msg.get('event_en')})")
                print(f"  置信度  : {msg.get('confidence')}")
                print(f"  建议    : {msg.get('advice')}")
                print(f"  仿真    : {msg.get('sim_clock')} (第 {msg.get('sim_time')}s)")
                print(f"  耗时    : {msg.get('latency_ms')} ms | 后端 {msg.get('llm_backend')}")
                print(f"  缺失字段: {missing if missing else '无'}")
                return 0 if not missing else 1
            if msg_type == "llm_alert_error":
                print(f"[test] FAIL: llm_alert_error — {msg.get('message')}")
                return 1
            # 其他消息忽略


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
