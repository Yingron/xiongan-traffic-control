"""赛道 C LLM 微调数据集准备：从生成的 JSONL 构建类别平衡的 train/val 切分。

背景：dataset_v1.jsonl（129,600 样本）与 dataset_incident.jsonl（10,440 样本）
类别极不均衡（正常 76% / 拥堵 20% / 溢出 ~3% / 事件 ~0.2%）。
直接训练会让模型"只会输出正常"；本脚本按类别等量抽样，事件类不足时重复补齐。

用法：
    python -m llm_train.prepare_data \
        --data data/llm/dataset_v1.jsonl,data/llm/dataset_incident.jsonl \
        --samples-per-class 2000 \
        --out data/llm/split_balanced.jsonl

输出：单文件 JSONL（每行 {text, target, event, split}），train:val = 9:1（按类别分层）。
"""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from llm_data.schema import EVENT_CLASSES, EVENT_INCIDENT


def load_samples(paths: list[Path]) -> list[dict]:
    """读取 JSONL，抽取微调所需字段，按 id 去重（事件密集文件与主文件窗口有重叠）。"""
    seen: set[str] = set()
    samples = []
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row["id"] in seen:
                continue
            seen.add(row["id"])
            samples.append({
                "id": row["id"],
                "text": row["text"],
                "target": row["target"],
                "event": row["label"]["event"],
            })
    return samples


def build_split(samples: list[dict], per_class: int, val_ratio: float,
                seed: int, repeat_incident: int = 3) -> list[dict]:
    """按类别等量抽样 + 分层切分。事件类样本少，用重复补齐到 per_class。"""
    rng = random.Random(seed)
    by_class: dict[str, list[dict]] = defaultdict(list)
    for s in samples:
        by_class[s["event"]].append(s)

    chosen: list[dict] = []
    for cls in EVENT_CLASSES:
        pool = by_class.get(cls, [])
        if cls == EVENT_INCIDENT and len(pool) < per_class:
            # 事件样本不足：重复多份（数据增强），最多重复 repeat_incident 次
            pool = pool * repeat_incident
        rng.shuffle(pool)
        chosen.extend(pool[:per_class])

    rng.shuffle(chosen)
    # 分层 9:1 切分
    train, val = [], []
    for cls in EVENT_CLASSES:
        cls_items = [s for s in chosen if s["event"] == cls]
        n_val = max(1, int(len(cls_items) * val_ratio))
        val.extend(cls_items[:n_val])
        train.extend(cls_items[n_val:])
    rng.shuffle(train)
    rng.shuffle(val)

    out = []
    for s in train:
        out.append({**s, "split": "train"})
    for s in val:
        out.append({**s, "split": "val"})
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="构建类别平衡的微调数据集")
    parser.add_argument("--data", default="data/llm/dataset_v1.jsonl,data/llm/dataset_incident.jsonl",
                        help="逗号分隔的 JSONL 数据集路径")
    parser.add_argument("--samples-per-class", type=int, default=2000,
                        help="每类别抽样的目标样本数（事件类不足时重复补齐）")
    parser.add_argument("--val-ratio", type=float, default=0.1, help="验证集比例")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default="data/llm/split_balanced.jsonl")
    args = parser.parse_args()

    paths = [Path(p) for p in args.data.split(",") if p.strip()]
    samples = load_samples(paths)
    print(f"原始样本: {len(samples)}  类别分布: {dict(Counter(s['event'] for s in samples))}")

    out = build_split(samples, args.samples_per_class, args.val_ratio, args.seed)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for s in out:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    dist = Counter(s["split"] for s in out)
    by_cls = Counter((s["split"], s["event"]) for s in out)
    print(f"输出: {out_path}  总样本 {len(out)}  train={dist['train']} val={dist['val']}")
    for cls in EVENT_CLASSES:
        print(f"  {cls}: train={by_cls[('train', cls)]} val={by_cls[('val', cls)]}")


if __name__ == "__main__":
    main()
