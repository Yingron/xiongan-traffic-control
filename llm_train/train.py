"""赛道 C LLM 微调（步骤②）：Qwen2.5-0.5B-Instruct + LoRA 监督微调。

任务：单路口交通状态窗口文本 → {"event": "正常|拥堵|溢出|事件", "confidence", "advice"}。
训练数据：llm_train.prepare_data 产出的 split_balanced.jsonl（text=输入, target=目标 JSON）。
只训练 LoRA 适配器（< 1% 参数），基座模型冻结，8GB 显存可跑。

用法：
    python -m llm_train.train \
        --data data/llm/split_balanced.jsonl \
        --out models/llm/qwen-traffic-v1

推荐先用 --epochs 1 --max-train-samples 200 冒烟，再正式训练。
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

# Windows WDDM 下 PyTorch CUDA 缓存分配器预留池会膨胀（reserved 可达 10~15GB，
# 实际分配仅 ~1.1GB），训练结束的最终 eval 会因碎片化触发驱动级 OOM。
# 对策：训练内不做 eval（评估由 llm_train.evaluate 独立完成）+ 周期性 empty_cache 释放缓存。
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "garbage_collection_threshold:0.6")

import torch  # noqa: E402
from datasets import Dataset  # noqa: E402
from peft import LoraConfig, get_peft_model
from transformers import (  # noqa: E402
    AutoModelForCausalLM,
    AutoTokenizer,
    DataCollatorForSeq2Seq,
    Trainer,
    TrainerCallback,
    TrainingArguments,
)


class _MemoryMaintainCallback(TrainerCallback):
    """Windows WDDM 修复：周期性把 CUDA 缓存池空闲块归还驱动。

    缓存池碎片化会让 reserved 膨胀到 10GB+（实际只用 ~1GB），新段申请触发
    驱动级 OOM。每 25 个优化步 empty_cache 一次，把池子压回实际占用。
    """

    def on_step_end(self, args, state, control, **kwargs):
        if state.global_step > 0 and state.global_step % 25 == 0:
            torch.cuda.empty_cache()


def load_split(path: Path, split: str, max_samples: int | None = None) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row["split"] != split:
            continue
        rows.append(row)
        if max_samples is not None and len(rows) >= max_samples:
            break
    return rows


def tokenize_function(examples: dict, tokenizer, max_seq_len: int) -> dict:
    """把 (user 文本, target JSON) 编码为 input_ids + labels。

    labels 中 user 部分为 -100（不计算损失），只监督 assistant 输出。
    超长输入从左侧截断 user 部分（丢弃最旧的状态快照），保证 target 完整。
    """
    input_ids_list, labels_list, attention_list = [], [], []
    for text, target in zip(examples["text"], examples["target"]):
        user_text = tokenizer.apply_chat_template(
            [{"role": "user", "content": text}],
            tokenize=False,
            add_generation_prompt=True,
        )
        user_ids = tokenizer(user_text, add_special_tokens=False).input_ids
        target_ids = tokenizer(target + tokenizer.eos_token, add_special_tokens=False).input_ids

        ids = user_ids + target_ids
        labels = [-100] * len(user_ids) + target_ids
        if len(ids) > max_seq_len:
            overflow = len(ids) - max_seq_len
            cut = min(overflow, len(user_ids) - 1)
            ids = ids[cut:]
            labels = labels[cut:]

        input_ids_list.append(ids)
        labels_list.append(labels)
        attention_list.append([1] * len(ids))
    return {"input_ids": input_ids_list, "labels": labels_list, "attention_mask": attention_list}


def main() -> None:
    parser = argparse.ArgumentParser(description="Qwen2.5 LoRA 微调（交通事件识别+建议生成）")
    parser.add_argument("--model", default="models/llm/base/qwen2.5-0.5b-instruct",
                        help="基座模型（本地目录或 HF id；国内网络建议本地目录）")
    parser.add_argument("--data", default="data/llm/split_balanced.jsonl", help="准备脚本输出的 JSONL")
    parser.add_argument("--out", default="models/llm/qwen-traffic-v1", help="输出目录（LoRA 适配器）")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--lr", type=float, default=2e-4, help="LoRA 学习率（经验值 1e-4~3e-4）")
    parser.add_argument("--batch-size", type=int, default=2,
                        help="单卡 batch。Windows WDDM 下 CUDA 缓存池会过度预留，8GB 显存建议 2")
    parser.add_argument("--grad-accum", type=int, default=4, help="梯度累积，有效 batch = batch-size × grad-accum")
    parser.add_argument("--max-seq-len", type=int, default=1280,
                        help="序列截断长度（实测输入+目标 p95≈1200 token，1280 全量覆盖）")
    parser.add_argument("--gradient-checkpointing", action="store_true", default=True,
                        help="梯度检查点：以少量计算换显存（激活不缓存）")
    parser.add_argument("--lora-r", type=int, default=16, help="LoRA 秩（越大表达力越强，越容易过拟合）")
    parser.add_argument("--lora-alpha", type=int, default=32, help="LoRA alpha，一般取 2×r")
    parser.add_argument("--warmup-ratio", type=float, default=0.03)
    parser.add_argument("--eval-steps", type=int, default=50)
    parser.add_argument("--max-train-samples", type=int, default=None, help="冒烟用：只取前 N 条训练样本")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    torch.manual_seed(args.seed)
    data_path = Path(args.data)
    out_dir = Path(args.out)

    print(f"[1/5] 加载数据: {data_path}")
    train_rows = load_split(data_path, "train", args.max_train_samples)
    val_rows = load_split(data_path, "val")
    print(f"  train={len(train_rows)} val={len(val_rows)}")

    print(f"[2/5] 加载基座模型: {args.model}")
    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        args.model,
        torch_dtype=torch.bfloat16 if torch.cuda.is_available() and torch.cuda.is_bf16_supported() else torch.float16,
        device_map="auto",
        trust_remote_code=True,
    )

    print(f"[3/5] 挂 LoRA 适配器 (r={args.lora_r}, alpha={args.lora_alpha})")
    lora_config = LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora_config)
    if args.gradient_checkpointing:
        model.gradient_checkpointing_enable()
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    print(f"  可训练参数: {trainable/1e6:.2f}M / 总参数 {total/1e6:.0f}M ({trainable/total:.2%})")

    print("[4/5] 构建数据集")
    row_keys = list(train_rows[0].keys())
    train_ds = Dataset.from_list(train_rows).map(
        lambda ex: tokenize_function(ex, tokenizer, args.max_seq_len),
        batched=True, remove_columns=row_keys)
    val_ds = Dataset.from_list(val_rows).map(
        lambda ex: tokenize_function(ex, tokenizer, args.max_seq_len),
        batched=True, remove_columns=row_keys)

    steps_per_epoch = max(1, len(train_ds) // (args.batch_size * args.grad_accum))
    warmup_steps = int(steps_per_epoch * args.epochs * args.warmup_ratio)
    print(f"  每轮 {steps_per_epoch} 步 × {args.epochs} 轮 = {steps_per_epoch * args.epochs} 步, warmup {warmup_steps} 步")

    training_args = TrainingArguments(
        output_dir=str(out_dir),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        warmup_steps=warmup_steps,
        lr_scheduler_type="cosine",
        logging_steps=10,
        # Windows WDDM 下训练结束的最终 eval 会触发驱动级 OOM（缓存池碎片化），
        # 训练内不做评估；模型效果由 llm_train/evaluate.py 独立评估。
        eval_strategy="no",
        save_strategy="no",
        bf16=torch.cuda.is_available() and torch.cuda.is_bf16_supported(),
        fp16=torch.cuda.is_available() and not torch.cuda.is_bf16_supported(),
        remove_unused_columns=False,
        report_to=[],
        seed=args.seed,
    )
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        data_collator=DataCollatorForSeq2Seq(tokenizer=tokenizer, padding=True),
        callbacks=[_MemoryMaintainCallback()],
    )

    print(f"[5/5] 开始训练（{len(train_ds)} 样本 × {args.epochs} epochs）")
    trainer.train()

    print(f"保存 LoRA 适配器 → {out_dir}")
    trainer.save_model(str(out_dir))
    tokenizer.save_pretrained(str(out_dir))
    # 训练/验证损失存档（评估脚本会引用）
    (out_dir / "train_stats.json").write_text(
        json.dumps({"train_samples": len(train_rows), "val_samples": len(val_rows),
                    "args": vars(args)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("完成 ✅")


if __name__ == "__main__":
    main()
