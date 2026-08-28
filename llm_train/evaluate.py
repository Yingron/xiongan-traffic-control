"""赛道 C LLM 微调评估（步骤②收尾）：识别 F1 + JSON 解析率 + 延迟 + 示例输出。

用法：
    python -m llm_train.evaluate --adapter models/llm/qwen-traffic-v1 \
        --data data/llm/split_balanced.jsonl --max-samples 200

对比基座模型（未微调）：
    python -m llm_train.evaluate --data data/llm/split_balanced.jsonl --max-samples 200

输出：--out 指向的 JSON（指标 + 预测明细），控制台打印示例。
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

from llm_data.parsing import extract_json, normalize_event
from llm_data.schema import EVENT_CLASSES


def build_prompt(tokenizer, text: str) -> str:
    return tokenizer.apply_chat_template(
        [{"role": "user", "content": text}], tokenize=False, add_generation_prompt=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="评估微调后的交通事件识别模型")
    parser.add_argument("--adapter", default=None, help="LoRA 适配器目录；不传则评估基座模型（微调前对比）")
    parser.add_argument("--model", default="models/llm/base/qwen2.5-0.5b-instruct",
                        help="基座模型（本地目录或 HF id）")
    parser.add_argument("--data", default="data/llm/split_balanced.jsonl")
    parser.add_argument("--max-samples", type=int, default=200)
    parser.add_argument("--max-new-tokens", type=int, default=160)
    parser.add_argument("--out", default=None, help="评估结果 JSON 输出路径（默认写到适配器目录）")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    torch.manual_seed(args.seed)
    rows = []
    for line in Path(args.data).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row["split"] == "val":
            rows.append(row)
    # 按类别等量取验证样本，保证评估覆盖四类
    per_class = max(1, args.max_samples // 4)
    picked = []
    for cls in EVENT_CLASSES:
        picked.extend([r for r in rows if r["event"] == cls][:per_class])
    rows = picked
    dist = ", ".join(f"{cls} {sum(1 for r in rows if r['event'] == cls)}" for cls in EVENT_CLASSES)
    print(f"评估样本: {len(rows)}  [{dist}]")

    print(f"加载模型: {args.model}" + (f" + 适配器 {args.adapter}" if args.adapter else "（基座，未微调）"))
    tokenizer = AutoTokenizer.from_pretrained(args.adapter or args.model, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        args.model,
        torch_dtype=torch.bfloat16 if torch.cuda.is_available() and torch.cuda.is_bf16_supported() else torch.float16,
        device_map="auto",
        trust_remote_code=True,
    )
    if args.adapter:
        model = PeftModel.from_pretrained(model, args.adapter)
    model.eval()

    results = []
    parse_fail, event_mismatch = 0, 0
    conf_errors = []
    latencies = []
    t_start = time.time()

    for i, row in enumerate(rows):
        prompt = build_prompt(tokenizer, row["text"])
        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
        t0 = time.time()
        with torch.no_grad():
            outputs = model.generate(
                **inputs, max_new_tokens=args.max_new_tokens,
                do_sample=False, temperature=None, pad_token_id=tokenizer.pad_token_id,
            )
        latencies.append(time.time() - t0)
        raw = tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)

        parsed = extract_json(raw)
        pred_event = normalize_event(parsed.get("event")) if parsed else None
        ok = parsed is not None and pred_event is not None
        match = ok and pred_event == row["event"]
        if not ok:
            parse_fail += 1
        elif not match:
            event_mismatch += 1
        if parsed and isinstance(parsed.get("confidence"), (int, float)):
            conf_errors.append(abs(float(parsed["confidence"]) - 1.0))  # oracle 真值置信度恒为 1.0
        results.append({
            "id": row["id"], "event": row["event"], "raw": raw,
            "parsed": parsed, "match": match,
        })
        if (i + 1) % 50 == 0:
            print(f"  {i + 1}/{len(rows)}  累计延迟 {(time.time()-t_start)/max(i+1,1)*1000:.0f} ms/条")

    n = len(rows)
    json_rate = (n - parse_fail) / n
    acc = (n - parse_fail - event_mismatch) / n
    # 分类混淆 → 各类别召回
    by_class = {cls: {"total": 0, "correct": 0} for cls in EVENT_CLASSES}
    for r in results:
        pred = normalize_event(r["parsed"].get("event")) if r["parsed"] else None
        by_class[r["event"]]["total"] += 1
        if pred == r["event"]:
            by_class[r["event"]]["correct"] += 1
    recall = {cls: (v["correct"] / v["total"] if v["total"] else 0) for cls, v in by_class.items()}
    macro_f1 = sum(recall.values()) / len(EVENT_CLASSES)  # 均衡采样下召回≈F1（各类精度受分布影响，报告用召回）

    report = {
        "adapter": args.adapter,
        "model": args.model,
        "samples": n,
        "json_parse_rate": round(json_rate, 4),
        "event_accuracy": round(acc, 4),
        "class_recall": {k: round(v, 4) for k, v in recall.items()},
        "macro_recall": round(macro_f1, 4),
        "mean_conf_abs_error": round(sum(conf_errors) / len(conf_errors), 4) if conf_errors else None,
        "latency_ms": {"mean": round(sum(latencies) / len(latencies) * 1000, 1),
                       "p95": round(sorted(latencies)[int(n * 0.95) - 1] * 1000, 1)},
        "examples": results[:20],
    }
    out = Path(args.out) if args.out else (Path(args.adapter) / "eval_report.json" if args.adapter else Path("models/llm/eval_base.json"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n=== 评估结果（{n} 条，耗时 {time.time()-t_start:.0f}s）===")
    print(f"JSON 解析率 : {json_rate:.1%}")
    print(f"事件准确率 : {acc:.1%}")
    for cls in EVENT_CLASSES:
        print(f"  {cls} 召回: {recall[cls]:.1%} ({by_class[cls]['correct']}/{by_class[cls]['total']})")
    print(f"平均单条生成延迟: {report['latency_ms']['mean']} ms (P95 {report['latency_ms']['p95']} ms)")
    print(f"结果 → {out}")

    print("\n=== 示例（预测 vs 真值）===")
    for r in results[:8]:
        pred = normalize_event(r["parsed"].get("event")) if r["parsed"] else "解析失败"
        print(f"  [{r['id']}] 真值={r['event']} 预测={pred} {'✓' if r['match'] else '✗'}")
        if r["parsed"]:
            print(f"    建议: {r['parsed'].get('advice', '')[:60]}")


if __name__ == "__main__":
    main()
