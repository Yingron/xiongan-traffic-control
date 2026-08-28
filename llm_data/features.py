"""TraCI 原始交通特征提取：单路口每方向 排队/平均等待/占有率/平均速度。

与 env/global_state.py 的 22 维归一化状态不同，这里输出**未归一化的原始值**
（排队辆数、等待秒数、占有率 0~1、速度 km/h），供 LLM 中文文本化使用。
车道方向映射复用 docs/lane_mapping.json（validate_network 校验过的物理映射）。
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

from configs.constants import DIRECTIONS, DOCS_DIR


@lru_cache(maxsize=1)
def load_lane_mapping() -> dict[str, dict[str, list[str]]]:
    """加载校验过的物理车道映射 {路口: {方向: [车道ID, ...]}}（来源 docs/lane_mapping.json）。"""
    path = Path(DOCS_DIR) / "lane_mapping.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {str(jid): {str(d): list(lanes) for d, lanes in dirs.items()}
                for jid, dirs in data.items()}
    except (OSError, ValueError, TypeError):
        return {}


def _safe_positive(value: float) -> float:
    """getLastStepMeanSpeed 无车时返回 -1，统一归一为 0。"""
    return max(0.0, float(value))


def extract_intersection_raw(traci_mod: Any, tl_id: str) -> dict:
    """提取单个路口的原始交通特征（与状态提取相同的车道口径）。

    Returns:
        {"dirs": {方向: {"queue": 辆, "wait": 秒, "occupancy": 0~1, "speed_kmh": km/h}},
         "phase": 当前相位下标,
         "phase_name": 相位名（真实配时程序内）,
         "phase_state": "绿灯|黄灯|全红",
         "phase_elapsed": 当前相位已持续秒数}
    """
    controlled = set(traci_mod.trafficlight.getControlledLanes(tl_id))
    mapping = load_lane_mapping().get(tl_id, {})
    # lane_mapping 缺失时按车道前缀兜底（旧路网命名约定，新路网不依赖）
    if not mapping:
        mapping = {d: [] for d in DIRECTIONS}
        for lane in controlled:
            if lane:
                d = lane[0].upper()
                if d in mapping:
                    mapping[d].append(lane)

    dirs: dict[str, dict] = {}
    for direction in DIRECTIONS:
        lanes = [lane for lane in mapping.get(direction, []) if lane in controlled]
        if not lanes:
            dirs[direction] = {"queue": 0, "wait": 0.0, "occupancy": 0.0, "speed_kmh": 0.0}
            continue

        queue = int(sum(traci_mod.lane.getLastStepHaltingNumber(l) for l in lanes))

        waits = []
        for lane in lanes:
            veh_ids = traci_mod.lane.getLastStepVehicleIDs(lane)[:20]
            if veh_ids:
                waits.append(float(np.mean(
                    [traci_mod.vehicle.getWaitingTime(v) for v in veh_ids]
                )))
        wait = round(float(np.mean(waits)), 1) if waits else 0.0

        occupancy = round(float(np.mean(
            [_safe_positive(traci_mod.lane.getLastStepOccupancy(l)) for l in lanes]
        )), 3)
        speed_kmh = round(float(np.mean(
            [_safe_positive(traci_mod.lane.getLastStepMeanSpeed(l)) for l in lanes]
        )) * 3.6, 1)

        dirs[direction] = {
            "queue": queue,
            "wait": wait,
            "occupancy": occupancy,
            "speed_kmh": speed_kmh,
        }

    phase = int(traci_mod.trafficlight.getPhase(tl_id))
    duration = _safe_positive(traci_mod.trafficlight.getPhaseDuration(tl_id))
    next_switch = _safe_positive(traci_mod.trafficlight.getNextSwitch(tl_id))
    sim_time = _safe_positive(traci_mod.simulation.getTime())
    # 相位已持续秒数 = 时长 - 剩余；next_switch = 当前时刻 + 剩余
    phase_elapsed = round(max(0.0, sim_time + duration - next_switch), 1)

    return {
        "dirs": dirs,
        "phase": phase,
        "phase_name": _phase_name(traci_mod, tl_id, phase),
        "phase_elapsed": phase_elapsed,
    }


def _phase_name(traci_mod: Any, tl_id: str, phase: int) -> str:
    """从当前运行程序取相位名（如 "东西向直行_G"），失败时退回 "phase{idx}"。"""
    try:
        logic = traci_mod.trafficlight.getAllProgramLogics(tl_id)
        program = traci_mod.trafficlight.getProgram(tl_id)
        for candidate in logic:
            if candidate.programID == program and phase < len(candidate.phases):
                name = candidate.phases[phase].name
                return name or f"phase{phase}"
    except Exception:
        pass
    return f"phase{phase}"
