"""LLM 云脑部署效果测试：对验证集样本调用 /api/v1/llm/analyze，统计准确率。

前置条件（见 docs/系统启动手册_20260825.md）：
  1. llama-server 运行中（端口 8081）
  2. api_server 运行中（端口 8000）

用法：
    # 四类各取 20 条 val 样本，经完整 REST 链路测试
    python scripts/test_llm_analyze.py --samples-per-class 20
    # 单条文本测试
    python scripts/test_llm_analyze.py --text "【场景】早高峰…（从数据集中复制一条）"
    # 自定义服务地址
    python scripts/test_llm_analyze.py --base-url http://127.0.0.1:8000/api/v1
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from llm_data.schema import EVENT_CLASSES


def call_analyze(base_url: str, text: str, junction: str | None = None,
                 timeout: float = 120.0) -> tuple[dict, float]:
    payload = {"text": text}
    if junction:
        payload["junction"] = junction
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/llm/analyze",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    return data, (time.time() - t0) * 1000


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM 云脑部署效果测试（经 REST 全链路）")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api/v1",
                        help="api_server 地址")
    parser.add_argument("--data", default="data/llm/split_balanced.jsonl",
                        help="验证集数据（val 切分）")
    parser.add_argument("--samples-per-class", type=int, default=20,
                        help="每类测试条数（默认 20，四类共 80）")
    parser.add_argument("--text", default=None, help="单条测试文本（跳过数据集）")
    parser.add_argument("--junction", default=None, help="单条测试时的路口 ID")
    args = parser.parse_args()

    if args.text:
        resp, ms = call_analyze(args.base_url, args.text, args.junction)
        print(json.dumps(resp, ensure_ascii=False, indent=1))
        print(f"延迟: {ms:.0f} ms")
        return

    rows = []
    for line in Path(args.data).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row["split"] == "val":
            rows.append(row)
    picked = []
    for cls in EVENT_CLASSES:
        picked.extend([r for r in rows if r["event"] == cls][:args.samples_per_class])
    print(f"测试样本: {len(picked)} 条（{', '.join(f'{c} {args.samples_per_class}' for c in EVENT_CLASSES)}）")
    print(f"链路: api_server({args.base_url}) → llama-server → 微调模型\n")

    results, errors, latencies = [], 0, []
    for i, row in enumerate(picked, 1):
        try:
            resp, ms = call_analyze(args.base_url, row["text"], row["id"].split("-")[-1])
        except (urllib.error.URLError, OSError) as error:
            print(f"[{i}/{len(picked)}] {row['id']} 调用失败: {error}")
            errors += 1
            continue
        latencies.append(ms)
        pred = resp.get("event")
        match = pred == row["event"]
        results.append({"id": row["id"], "truth": row["event"], "pred": pred, "match": match})
        status = "✓" if match else "✗"
        if not match or i % 10 == 0:
            print(f"[{i}/{len(picked)}] {status} 真值={row['event']} 预测={pred} ({ms:.0f}ms)")

    n = len(picked) - errors
    correct = sum(1 for r in results if r["match"])
    by_class = {cls: {"total": 0, "correct": 0} for cls in EVENT_CLASSES}
    for r in results:
        by_class[r["truth"]]["total"] += 1
        if r["match"]:
            by_class[r["truth"]]["correct"] += 1

    print("\n=== 测试结果 ===")
    print(f"调用成功: {n}/{len(picked)}  |  事件准确率: {correct / max(n, 1):.1%}")
    for cls in EVENT_CLASSES:
        t, c = by_class[cls]["total"], by_class[cls]["correct"]
        print(f"  {cls}: {c}/{t} ({c / max(t, 1):.1%})")
    if latencies:
        print(f"平均延迟: {sum(latencies) / len(latencies):.0f} ms  (P95 {sorted(latencies)[int(len(latencies) * 0.95) - 1]:.0f} ms)")
    if errors:
        print(f"调用失败 {errors} 条：检查 llama-server(8081) 与 api_server(8000) 是否运行")


if __name__ == "__main__":
    main()
