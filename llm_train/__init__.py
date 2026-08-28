"""赛道 C LLM 微调工具包（步骤②）。

- prepare_data.py  从生成的 JSONL 构建类别平衡的 train/val 切分
- train.py         Qwen2.5-0.5B-Instruct + LoRA 监督微调
- evaluate.py      识别 F1 / JSON 解析率 / 延迟评估（可与基座模型对比）
"""
from llm_train.prepare_data import build_split, load_samples

__all__ = ["build_split", "load_samples"]
