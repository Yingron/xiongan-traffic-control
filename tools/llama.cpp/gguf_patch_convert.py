"""运行 b10612 的 convert_hf_to_gguf.py，但先给本机 gguf 包补缺失的架构枚举。

背景：llama.cpp b10612 的 conversion 包引用了 gguf 0.20+ 才有的架构枚举
（DFLASH/CLIP_VISION 等），本机 pip 最新 gguf 0.19 没有。本项目只转 QWEN2，
缺的架构不会被用到，补成占位值即可。

用法：
    python tools/llama.cpp/gguf_patch_convert.py <convert_hf_to_gguf.py 的参数...>
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

import gguf

_MISSING = [
    "BAILINGMOE3", "COHERE2MOE", "DEEPSEEK32", "DEEPSEEK4", "DFLASH",
    "DOTS3NOTE", "EAGLE3", "GEMMA4_ASSISTANT", "GRANITE_SWA", "GRANITE_SWITCH",
    "HY_V3", "KIMI_K3", "LAGUNA", "MELLUM", "MINIMAX01", "MINIMAXM3",
    "MUSE_GLIMMER", "NANBEIGE", "POCKETTTS", "QWEN3TTS", "TALKIE",
    "CLIP_VISION", "CLIP_TEXT", "CLIP_TEXT_PROJ",
]

for name in _MISSING:
    if not hasattr(gguf.MODEL_ARCH, name):
        setattr(gguf.MODEL_ARCH, name, 0)

script = Path(__file__).parent / "convert_hf_to_gguf.py"
sys.argv = [str(script), *sys.argv[1:]]
runpy.run_path(str(script), run_name="__main__")
