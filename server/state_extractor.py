"""状态提取器 - 从TraCI提取440维全局状态"""
from __future__ import annotations

import math
from typing import Any, Optional
import numpy as np

INTERSECTION_ORDER = tuple(f"J{i:02d}" for i in range(1, 21))
FEATURES_PER_INTERSECTION = 22
STATE_DIMENSION = 440
DIRECTIONS = ("N", "S", "E", "W")


class StateExtractor:
    """从TraCI提取440维全局状态向量"""

    def __init__(self, sim_start_hour: float = 7.0):
        self._sim_start_hour = sim_start_hour

    def get_global_state(self, traci: Any) -> np.ndarray:
        """获取完整的440维状态向量"""
        state = np.zeros(STATE_DIMENSION, dtype=np.float32)
        traffic_lights = list(traci.trafficlight.getIDList())

        for idx, tl_id in enumerate(INTERSECTION_ORDER):
            if tl_id not in traffic_lights:
                continue
            offset = idx * FEATURES_PER_INTERSECTION
            local_state = self._extract_intersection_state(traci, tl_id)
            state[offset:offset + FEATURES_PER_INTERSECTION] = local_state

        return state

    def _extract_intersection_state(self, traci: Any, tl_id: str) -> np.ndarray:
        """提取单个路口的22维状态"""
        state = np.zeros(FEATURES_PER_INTERSECTION, dtype=np.float32)
        controlled_lanes = traci.trafficlight.getControlledLanes(tl_id)

        lane_mapping = {d: [] for d in DIRECTIONS}
        for lane in controlled_lanes:
            if len(lane) > 0:
                direction = lane[0].upper()
                if direction in lane_mapping:
                    lane_mapping[direction].append(lane)

        for dir_idx, direction in enumerate(DIRECTIONS):
            lanes = lane_mapping[direction]
            if not lanes:
                continue

            representative = self._get_representative_lane(lanes)
            queue_len = self._get_queue_length(traci, representative)
            wait_time = self._get_avg_wait_time(traci, representative)
            occupancy = self._get_occupancy(traci, representative)

            state[dir_idx] = self._normalize(queue_len, max_val=15.0)
            state[4 + dir_idx] = self._normalize(wait_time, max_val=120.0)
            state[8 + dir_idx] = occupancy
            state[12 + dir_idx] = self._normalize(queue_len, max_val=15.0)

        phase = self._get_phase_onehot(traci, tl_id)
        state[16:20] = phase

        time_sin, time_cos = self._get_time_features(traci)
        state[20] = time_sin
        state[21] = time_cos

        return state

    def _get_representative_lane(self, lanes: list[str]) -> str:
        if not lanes:
            return ""
        for lane in lanes:
            if lane.endswith("_0"):
                return lane
        return lanes[0]

    def _get_queue_length(self, traci: Any, lane: str) -> float:
        try:
            return float(traci.lane.getLastStepHaltingNumber(lane))
        except Exception:
            return 0.0

    def _get_avg_wait_time(self, traci: Any, lane: str) -> float:
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

    def _get_occupancy(self, traci: Any, lane: str) -> float:
        try:
            return float(traci.lane.getLastStepOccupancy(lane))
        except Exception:
            return 0.0

    def _get_phase_onehot(self, traci: Any, tl_id: str) -> np.ndarray:
        phase = int(traci.trafficlight.getPhase(tl_id))
        onehot = np.zeros(4, dtype=np.float32)
        if 0 <= phase <= 3:
            onehot[phase] = 1.0
        return onehot

    def _get_time_features(self, traci: Any) -> tuple[float, float]:
        sim_time = float(traci.simulation.getTime())
        current_hour = self._sim_start_hour + (sim_time / 3600.0)
        sin_val = math.sin(2 * math.pi * current_hour / 24.0)
        cos_val = math.cos(2 * math.pi * current_hour / 24.0)
        return sin_val, cos_val

    @staticmethod
    def _normalize(value: float, max_val: float) -> float:
        return min(max(value / max_val, 0.0), 1.0)

    def parse_state(self, state: np.ndarray) -> dict:
        """解析状态向量为结构化数据"""
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
                "phase_name": ["NS_Straight", "NS_Left", "EW_Straight", "EW_Left"][phase],
                "time_sin": float(features[20]),
                "time_cos": float(features[21])
            }
        return result
