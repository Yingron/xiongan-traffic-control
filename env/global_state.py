"""全局状态提取模块 - 从TraCI提取660维全局状态向量"""
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
    INTERSECTION_TEMPLATES,
    ACTION_MASK_TEMPLATES,
    ACTION_MASK_QUEUE_THRESHOLD,
)

DEBUG = False


@lru_cache(maxsize=1)
def _load_lane_mapping() -> dict[str, dict[str, list[str]]]:
    """Load the validated physical lane mapping generated with the SUMO net.

    Earlier generated networks used internal edge names in some
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


def get_global_state(num_intersections: int = 30) -> np.ndarray:
    """获取完整的660维全局状态向量

    Args:
        num_intersections: 路口数量，默认为30

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


def _extract_intersection_state(
    traci: Any,
    tl_id: str,
    phase_changed_at: float | None = None,
) -> np.ndarray:
    """提取单个路口的22维状态

    Args:
        traci: TraCI连接对象
        tl_id: 交通信号灯ID
        phase_changed_at: 当前相位开始时刻（单路口训练环境传入），
            用于在 state[20] 编码"相位已持续秒数"，让智能体知道何时可合法切换
            （MIN_GREEN_SECONDS=15）。为None时保持原时间sin特征（全局30路口状态）。

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

    if phase_changed_at is not None:
        # 相位已持续秒数（归一化，60s封顶）：智能体可据此判断是否过了最小绿灯锁定期
        elapsed = max(0.0, float(traci.simulation.getTime()) - phase_changed_at)
        state[20] = _normalize(elapsed, max_val=60.0)
        # 保留cos时间特征（与sin冗余，编码同一时刻角）
        state[21] = _get_time_features(traci)[1]
    else:
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


def _intersection_template(junction: str) -> str | None:
    """返回路口所属 rl4 模板（无分组时返回 None）。"""
    for tpl, junctions in INTERSECTION_TEMPLATES.items():
        if junction in junctions:
            return tpl
    return None


def compute_action_mask(
    traci: Any,
    tl_id: str,
    rl4_states: list[str] | None = None,
) -> np.ndarray:
    """按"相位所服务链路是否有排队车辆"计算 4 维动作掩码（0=无效，1=有效）。

    仅对 ACTION_MASK_TEMPLATES（模板C）启用需求门控：遍历 rl4 程序的每个相位，
    统计其绿灯链路（状态字符为 G/g 的受控链路）上的 halting 车辆数，
    低于 ACTION_MASK_QUEUE_THRESHOLD 的相位视为"无需求"被掩蔽。
    全部相位都无需求时（路口空闲）返回全 1，避免死锁。
    其他模板返回全 1（不掩码）。

    Args:
        traci: TraCI 连接对象
        tl_id: 信号灯 ID
        rl4_states: 预取的 rl4 相位状态字符串（训练 env 在 reset 时缓存，避免每步查询）

    Returns:
        长度 4 的 float32 掩码向量
    """
    if _intersection_template(tl_id) not in ACTION_MASK_TEMPLATES:
        return np.ones(4, dtype=np.float32)

    if rl4_states is None:
        logic = next(
            (candidate for candidate in traci.trafficlight.getAllProgramLogics(tl_id) if candidate.programID == "rl4"),
            None,
        )
        if logic is None or len(logic.phases) != 4:
            return np.ones(4, dtype=np.float32)
        rl4_states = [phase.state for phase in logic.phases]

    lanes = traci.trafficlight.getControlledLanes(tl_id)
    halting = [float(traci.lane.getLastStepHaltingNumber(lane)) for lane in lanes]

    mask = np.zeros(4, dtype=np.float32)
    for action, state_str in enumerate(rl4_states):
        green_links = [i for i, ch in enumerate(state_str) if ch in "Gg" and i < len(lanes)]
        if not green_links:
            continue
        demand = sum(halting[i] for i in green_links)
        if demand >= ACTION_MASK_QUEUE_THRESHOLD:
            mask[action] = 1.0
    if mask.sum() == 0.0:
        # 路口空闲：兜底全部有效，避免策略无动作可选
        mask[:] = 1.0
    return mask


def get_action_masks(
    traci: Any,
    junctions: tuple[str, ...] = INTERSECTION_ORDER,
) -> np.ndarray:
    """获取全部路口动作掩码 (len(junctions), 4)。API 推理与全局控制使用。"""
    return np.stack([compute_action_mask(traci, tl_id) for tl_id in junctions], axis=0)


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
