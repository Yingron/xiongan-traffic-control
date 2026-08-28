"""状态窗口 → 中文输入文本（LLM 微调的 user 侧模板）。

文本自包含：场景、时钟、路口、最近一个时间窗的逐采样交通状态，
末尾给出任务指令与输出 JSON 格式约束。训练时按
  输入 = format_window_text(...) 的输出，
  输出 = 标签 JSON 字符串（见 oracle.EventOracle.label_window）
构造 (instruction, response) 对。
"""
from __future__ import annotations

import datetime
from typing import Any

from configs.constants import DIRECTIONS

from llm_data.schema import DIRECTION_CN

_PHASE_SUFFIX_CN = {"_G": "绿灯", "_g": "绿灯", "_Y": "黄灯", "_y": "黄灯", "_R": "全红", "_r": "全红"}

_JSON_SCHEMA_HINT = (
    '只输出 JSON：{"event": "正常|拥堵|溢出|事件", "confidence": 0.0~1.0, "advice": "中文管控建议"}'
)


def _clock(sim_time: float, start_hour: int) -> str:
    return (datetime.datetime(2026, 1, 1, start_hour)
            + datetime.timedelta(seconds=int(sim_time))).strftime("%H:%M:%S")


def _phase_cn(phase_name: str) -> str:
    for suffix, cn in _PHASE_SUFFIX_CN.items():
        if phase_name.endswith(suffix):
            return f"{phase_name[:-2]}({cn})"
    return phase_name


def format_snapshot_line(snap: dict) -> str:
    """单条采样 → "北向:排队6辆 平均等待32秒 占有率0.42 均速21km/h" 形式。"""
    parts = []
    for direction in DIRECTIONS:
        d = snap["dirs"].get(direction, {})
        parts.append(
            f"{DIRECTION_CN[direction]}向:排队{d['queue']}辆 "
            f"平均等待{d['wait']}秒 占有率{d['occupancy']:.2f} 均速{d['speed_kmh']:.0f}km/h"
        )
    return " | ".join(parts)


def format_window_text(
    junction: str,
    scenario_cn: str,
    start_hour: int,
    sim_time: float,
    snapshots: list[dict],
    window_sec: int,
    sample_sec: int,
    vehicle_count: int,
) -> str:
    """渲染一个路口状态窗口的中文文本（不含标签）。"""
    lines = [
        f"【场景】{scenario_cn}（真实需求 · 固定配时基线）",
        f"【时间】{_clock(sim_time, start_hour)}（仿真第 {int(sim_time)} 秒，全网车辆 {vehicle_count} 辆）",
        f"【路口 {junction}】最近 {window_sec} 秒交通状态（每 {sample_sec} 秒采样）：",
    ]
    for snap in snapshots:
        phase = snap.get("phase_name", "")
        lines.append(
            f"  {_clock(snap['t'], start_hour)} | 相位:{_phase_cn(phase)}"
            f"(已持续{snap['phase_elapsed']:.0f}秒) | {format_snapshot_line(snap)}"
        )
    lines.append(f"【问题】请判断该路口当前运行状态属于哪类交通事件（正常/拥堵/溢出/事件），"
                 f"并结合排队、占有率、均速与当前相位给出信号管控建议。{_JSON_SCHEMA_HINT}。")
    return "\n".join(lines)


def format_label_json(label: dict) -> str:
    """oracle 标签 → 训练目标 JSON 字符串（紧凑单行，便于模型复刻）。"""
    return f'{{"event": "{label["event"]}", "confidence": {label["confidence"]}, "advice": "{label["advice"]}"}}'
