"""全局状态提取模块 - 从TraCI提取440维全局状态向量"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional
import numpy as np

from configs.constants import (
    INTERSECTION_ORDER,
    FEATURES_PER_INTERSECTION,
    STATE_DIMENSION,
    DIRECTIONS,
    DOCS_DIR,
)

DEBUG = False


@lru_cache(maxsize=1)
def _load_lane_mapping() -> dict[str, dict[str, list[str]]]:
    """Load the validated physical lane mapping generated with the SUMO net.

    The generated 20-intersection network uses internal edge names in some
    places, so inferring N/S/E/W from a lane-ID prefix is not reliable.
    """
    path = Path(DOCS_DIR) / "lane_mapping.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {str(junction): {str(direction): list(lanes) for direction, lanes in directions.items()} for junction, directions in data.items()}
    except (OSError, ValueError, TypeError):
        return {}


def _get_representative_lane(controlled_lanes: list[str], direction: str) -> Optional[str]:
    """从受控车道列表中获取指定方向的代表车道

    Args:
        controlled_lanes: 受控车道ID列表
        direction: 方向 (N/S/E/W)

    Returns:
        代表车道ID，如果找不到返回None
    """
    matching_lanes = []
    for lane in controlled_lanes:
        if len(lane) > 0:
            lane_dir = lane[0].upper()
            if lane_dir == direction:
                matching_lanes.append(lane)

    if not matching_lanes:
        return None

    for lane in matching_lanes:
        if lane.endswith("_0"):
            return lane

    return matching_lanes[0]


def get_global_state(num_intersections: int = 20) -> np.ndarray:
    """获取完整的440维全局状态向量

    Args:
        num_intersections: 路口数量，默认为20

    Returns:
        STATE_DIMENSION维的状态向量
    """
    import traci

    state = np.zeros(STATE_DIMENSION, dtype=np.float32)
    traffic_lights = list(traci.trafficlight.getIDList())

    for idx, tl_id in enumerate(INTERSECTION_ORDER[:num_intersections]):
        if tl_id not in traffic_lights:
            continue
        offset = idx * FEATURES_PER_INTERSECTION
        local_state = _extract_intersection_state(traci, tl_id)
        state[offset:offset + FEATURES_PER_INTERSECTION] = local_state

    return state


def _extract_intersection_state(traci: Any, tl_id: str) -> np.ndarray:
    """提取单个路口的22维状态

    Args:
        traci: TraCI连接对象
        tl_id: 交通信号灯ID

    Returns:
        22维局部状态向量
    """
    state = np.zeros(FEATURES_PER_INTERSECTION, dtype=np.float32)
    controlled_lanes = traci.trafficlight.getControlledLanes(tl_id)

    controlled_set = set(controlled_lanes)
    configured_mapping = _load_lane_mapping().get(tl_id, {})
    if configured_mapping:
        lane_mapping = {
            direction: [lane for lane in configured_mapping.get(direction, []) if lane in controlled_set]
            for direction in DIRECTIONS
        }
    else:
        lane_mapping = {d: [] for d in DIRECTIONS}
        for lane in controlled_lanes:
            if lane:
                direction = lane[0].upper()
                if direction in lane_mapping:
                    lane_mapping[direction].append(lane)

    for dir_idx, direction in enumerate(DIRECTIONS):
        lanes = lane_mapping[direction]
        if not lanes:
            continue

        queue_len = sum(_get_queue_length(traci, lane) for lane in lanes)
        wait_time = float(np.mean([_get_avg_wait_time(traci, lane) for lane in lanes]))
        occupancy = float(np.mean([_get_occupancy(traci, lane) for lane in lanes]))

        state[dir_idx] = _normalize(queue_len, max_val=15.0)
        state[4 + dir_idx] = _normalize(wait_time, max_val=120.0)
        state[8 + dir_idx] = occupancy
        state[12 + dir_idx] = _normalize(queue_len, max_val=15.0)

    phase = _get_phase_onehot(traci, tl_id)
    state[16:20] = phase

    time_sin, time_cos = _get_time_features(traci)
    state[20] = time_sin
    state[21] = time_cos

    if DEBUG:
        print(f"  {tl_id} 状态: 排队={state[0:4]}, 占有率={state[8:12]}")

    return state


def _get_queue_length(traci: Any, lane: str) -> float:
    """获取车道排队长度"""
    try:
        return float(traci.lane.getLastStepHaltingNumber(lane))
    except Exception:
        return 0.0


def _get_avg_wait_time(traci: Any, lane: str) -> float:
    """获取车道平均等待时间"""
    try:
        vehicles = traci.lane.getLastStepVehicleIDs(lane)
        if not vehicles:
            return 0.0
        total_wait = 0.0
        for veh_id in vehicles[:20]:
            try:
                total_wait += traci.vehicle.getWaitingTime(veh_id)
            except Exception:
                pass
        return total_wait / len(vehicles) if vehicles else 0.0
    except Exception:
        return 0.0


def _get_occupancy(traci: Any, lane: str) -> float:
    """获取车道占有率"""
    try:
        return float(traci.lane.getLastStepOccupancy(lane))
    except Exception:
        return 0.0


def _get_phase_onehot(traci: Any, tl_id: str) -> np.ndarray:
    """获取相位的One-Hot编码"""
    phase = int(traci.trafficlight.getPhase(tl_id))
    onehot = np.zeros(4, dtype=np.float32)
    if 0 <= phase <= 3:
        onehot[phase] = 1.0
    return onehot


def _get_time_features(traci: Any, sim_start_hour: float = 7.0) -> tuple[float, float]:
    """获取时间特征（sin/cos编码）"""
    sim_time = float(traci.simulation.getTime())
    current_hour = sim_start_hour + (sim_time / 3600.0)
    sin_val = math.sin(2 * math.pi * current_hour / 24.0)
    cos_val = math.cos(2 * math.pi * current_hour / 24.0)
    return sin_val, cos_val


def _normalize(value: float, max_val: float) -> float:
    """归一化到[0, 1]范围"""
    return min(max(value / max_val, 0.0), 1.0)


def parse_state(state: np.ndarray) -> dict:
    """解析状态向量为结构化数据"""
    from configs.constants import ACTION_NAMES

    result = {}
    for idx, tl_id in enumerate(INTERSECTION_ORDER):
        offset = idx * FEATURES_PER_INTERSECTION
        features = state[offset:offset + FEATURES_PER_INTERSECTION]
        phase = int(np.argmax(features[16:20]))

        result[tl_id] = {
            "queue_length": {d: float(features[i]) for i, d in enumerate(DIRECTIONS)},
            "avg_wait_time": {d: float(features[4 + i]) for i, d in enumerate(DIRECTIONS)},
            "occupancy": {d: float(features[8 + i]) for i, d in enumerate(DIRECTIONS)},
            "overflow_risk": {d: float(features[12 + i]) for i, d in enumerate(DIRECTIONS)},
            "phase": phase,
            "phase_name": ACTION_NAMES[phase] if 0 <= phase < len(ACTION_NAMES) else "unknown",
            "time_sin": float(features[20]),
            "time_cos": float(features[21])
        }
    return result
