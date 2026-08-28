"""LoRA 合并：把微调适配器合并回基座模型，输出完整 HF 权重（供 GGUF 转换）。

用法：
    python -m llm_train.merge --adapter models/llm/qwen-traffic-v1 \
        --base models/llm/base/qwen2.5-0.5b-instruct \
        --out models/llm/gguf/qwen-traffic-merged
"""
from __future__ import annotations

import argparse
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer


def main() -> None:
    parser = argparse.ArgumentParser(description="合并 LoRA 适配器到基座模型")
    parser.add_argument("--base", default="models/llm/base/qwen2.5-0.5b-instruct")
    parser.add_argument("--adapter", default="models/llm/qwen-traffic-v1")
    parser.add_argument("--out", default="models/llm/gguf/qwen-traffic-merged")
    args = parser.parse_args()

    out_dir = Path(args.out)
    print(f"加载基座: {args.base}")
    model = AutoModelForCausalLM.from_pretrained(
        args.base, torch_dtype=torch.bfloat16, device_map="auto")
    print(f"加载适配器: {args.adapter}")
    model = PeftModel.from_pretrained(model, args.adapter)
    print("合并 LoRA 权重...")
    merged = model.merge_and_unload()
    out_dir.mkdir(parents=True, exist_ok=True)
    merged.save_pretrained(str(out_dir))
    AutoTokenizer.from_pretrained(args.base).save_pretrained(str(out_dir))
    print(f"合并完成 → {out_dir}")


if __name__ == "__main__":
    main()
