"""GGUF 模型评估（步骤③对比）：通过 llama-server OpenAI 兼容接口批量评测。

与 llm_train/evaluate.py 同口径（同一批 val 样本、同一解析逻辑），
用于量化 INT4 前后的精度/延迟对比：
    python -m llm_train.evaluate_gguf --base-url http://127.0.0.1:8081/v1 \
        --max-samples 100 --out models/llm/gguf/eval_report_q4.json
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from llm_data.parsing import extract_json, normalize_event
from llm_data.schema import EVENT_CLASSES


def call_llm(base_url: str, model: str, text: str, timeout: float = 60.0) -> tuple[str, float]:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": text}],
        "temperature": 0.0,
        "max_tokens": 160,
    }
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    latency_ms = (time.time() - t0) * 1000
    return data["choices"][0]["message"]["content"], latency_ms


def main() -> None:
    parser = argparse.ArgumentParser(description="通过 llama-server 评估 GGUF 模型")
    parser.add_argument("--base-url", default="http://127.0.0.1:8081/v1")
    parser.add_argument("--model", default="qwen-traffic")
    parser.add_argument("--data", default="data/llm/split_balanced.jsonl")
    parser.add_argument("--max-samples", type=int, default=100)
    parser.add_argument("--out", default="models/llm/gguf/eval_report_q4.json")
    parser.add_argument("--workers", type=int, default=4, help="并发请求数")
    args = parser.parse_args()

    rows = []
    for line in Path(args.data).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row["split"] == "val":
            rows.append(row)
    per_class = max(1, args.max_samples // 4)
    picked = []
    for cls in EVENT_CLASSES:
        picked.extend([r for r in rows if r["event"] == cls][:per_class])
    rows = picked
    print(f"评估样本: {len(rows)}")

    def evaluate(row: dict) -> dict:
        raw, latency = call_llm(args.base_url, args.model, row["text"])
        parsed = extract_json(raw)
        pred = normalize_event(parsed.get("event")) if parsed else None
        return {"id": row["id"], "event": row["event"], "raw": raw,
                "parsed": parsed, "pred": pred, "latency_ms": latency}

    t_start = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(evaluate, rows))

    parse_fail = sum(1 for r in results if r["parsed"] is None)
    mismatch = sum(1 for r in results if r["parsed"] and r["pred"] != r["event"])
    n = len(results)
    by_class = {cls: {"total": 0, "correct": 0} for cls in EVENT_CLASSES}
    for r in results:
        by_class[r["event"]]["total"] += 1
        if r["pred"] == r["event"]:
            by_class[r["event"]]["correct"] += 1
    recall = {cls: (v["correct"] / v["total"] if v["total"] else 0) for cls, v in by_class.items()}
    latencies = sorted(r["latency_ms"] for r in results)

    report = {
        "backend": "llama.cpp (GGUF Q4_K_M)",
        "base_url": args.base_url,
        "samples": n,
        "json_parse_rate": round((n - parse_fail) / n, 4),
        "event_accuracy": round((n - parse_fail - mismatch) / n, 4),
        "class_recall": {k: round(v, 4) for k, v in recall.items()},
        "latency_ms": {"mean": round(sum(latencies) / n, 1),
                       "p95": round(latencies[int(n * 0.95) - 1], 1)},
        "wall_seconds": round(time.time() - t_start, 1),
        "examples": results[:10],
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"JSON 解析率: {report['json_parse_rate']:.1%}")
    print(f"事件准确率: {report['event_accuracy']:.1%}")
    for cls in EVENT_CLASSES:
        print(f"  {cls} 召回: {recall[cls]:.1%} ({by_class[cls]['correct']}/{by_class[cls]['total']})")
    print(f"平均延迟: {report['latency_ms']['mean']} ms (P95 {report['latency_ms']['p95']} ms)")
    print(f"结果 → {out}")


if __name__ == "__main__":
    main()
