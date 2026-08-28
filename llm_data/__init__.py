"""赛道 C LLM 数据集工具包：特征提取 / 规则标注 / 文本格式化。

- features.py     TraCI 原始交通特征提取（未归一化，供文本化）
- oracle.py       规则 oracle（事件标注 + 管控建议生成）
- text_format.py  状态窗口 → 中文输入文本
- schema.py       事件类别、场景表、扰动规格与阈值
"""
from llm_data.features import extract_intersection_raw, load_lane_mapping
from llm_data.oracle import EventOracle
from llm_data.text_format import format_label_json, format_window_text

__all__ = [
    "EventOracle",
    "extract_intersection_raw",
    "format_label_json",
    "format_window_text",
    "load_lane_mapping",
]
