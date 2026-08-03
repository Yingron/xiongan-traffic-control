"""多维度指标采集器

支持：排队长度、等待时间、行程时间、燃油消耗、CO2排放、通行量
维度：Mobility（机动性）、Environment（环境）、Safety（安全）

用法:
    from evaluation.metrics_collector import MetricsCollector
    collector = MetricsCollector(edge_ids)
    collector.collect()  # 每步调用
    summary = collector.get_summary()
"""
from __future__ import annotations

import sys
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional
import json

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class TrafficMetrics:
    """单步交通指标"""
    # Mobility
    queue_length: float = 0.0       # 平均排队长度（辆）
    waiting_time: float = 0.0       # 总等待时间（秒）
    travel_time: float = 0.0        # 平均行程时间（秒）
    throughput: int = 0             # 当前步通行量（辆）

    # Environment
    fuel_consumption: float = 0.0   # 燃油消耗（mL/步）
    co2_emission: float = 0.0       # CO2排放（mg/步）

    # Safety
    stop_count: int = 0             # 停车次数（速度<0.1m/s的车辆数）
    time_loss: float = 0.0          # 时间损失（秒）


class MetricsCollector:
    """多维度交通指标采集器"""

    def __init__(self, edge_ids: List[str], intersection_id: str = "J01"):
        """
        Args:
            edge_ids: 需要监控的边缘ID列表（进口道）
            intersection_id: 路口ID
        """
        self.edge_ids = edge_ids
        self.intersection_id = intersection_id
        self.history: List[TrafficMetrics] = []
        self._total_throughput: int = 0
        self._total_fuel: float = 0.0
        self._total_co2: float = 0.0
        self._vehicle_departure: Dict[str, float] = {}

    def collect(self, traci_conn=None) -> TrafficMetrics:
        """采集当前步的所有指标

        Args:
            traci_conn: TraCI连接对象，None则使用默认连接
        """
        if traci_conn is None:
            import traci
            traci_conn = traci

        metrics = TrafficMetrics()

        # ---- Mobility指标 ----
        # 排队长度：所有进口道的车辆数之和
        queue_counts = []
        for e in self.edge_ids:
            try:
                queue_counts.append(traci_conn.edge.getLastStepVehicleNumber(e))
            except Exception:
                queue_counts.append(0)
        metrics.queue_length = float(np.mean(queue_counts)) if queue_counts else 0.0

        # 等待时间：所有进口道的等待时间之和
        wait_times = []
        for e in self.edge_ids:
            try:
                wait_times.append(traci_conn.edge.getWaitingTime(e))
            except Exception:
                wait_times.append(0.0)
        metrics.waiting_time = float(np.sum(wait_times)) if wait_times else 0.0

        # 行程时间：所有进口道的平均行程时间
        travel_times = []
        for e in self.edge_ids:
            try:
                travel_times.append(traci_conn.edge.getTravelTime(e))
            except Exception:
                travel_times.append(0.0)
        metrics.travel_time = float(np.mean(travel_times)) if travel_times else 0.0

        # 通行量：当前步所有进口道的车辆数之和
        metrics.throughput = int(np.sum(queue_counts)) if queue_counts else 0
        self._total_throughput += metrics.throughput

        # ---- Environment指标 ----
        all_vehicles = traci_conn.vehicle.getIDList()

        # 燃油消耗：所有车辆的瞬时燃油消耗之和（mL/s）
        fuel = 0.0
        for v in all_vehicles:
            try:
                fuel += traci_conn.vehicle.getFuelConsumption(v)
            except Exception:
                pass
        metrics.fuel_consumption = float(fuel)
        self._total_fuel += fuel

        # CO2排放：所有进口道的CO2排放之和（mg/s）
        co2 = 0.0
        for e in self.edge_ids:
            try:
                co2 += traci_conn.edge.getCO2Emission(e)
            except Exception:
                pass
        metrics.co2_emission = float(co2)
        self._total_co2 += co2

        # ---- Safety指标 ----
        # 停车次数：速度<0.1 m/s的车辆数
        stop_count = 0
        for v in all_vehicles:
            try:
                if traci_conn.vehicle.getSpeed(v) < 0.1:
                    stop_count += 1
            except Exception:
                pass
        metrics.stop_count = stop_count

        # 时间损失：使用 tripinfo 的 timeLoss（近似为等待时间-最小行程时间）
        # 简化：用等待时间作为近似
        metrics.time_loss = metrics.waiting_time

        self.history.append(metrics)
        return metrics

    def get_summary(self) -> Dict:
        """返回所有指标的汇总统计"""
        if not self.history:
            return {}

        summary = {}
        for field_name in TrafficMetrics.__dataclass_fields__.keys():
            values = [getattr(m, field_name) for m in self.history]
            summary[field_name] = {
                'mean': float(np.mean(values)),
                'std': float(np.std(values)),
                'min': float(np.min(values)),
                'max': float(np.max(values)),
                'total': float(np.sum(values)),
            }

        # 累计指标
        summary['total_throughput'] = self._total_throughput
        summary['total_fuel'] = float(self._total_fuel)
        summary['total_co2'] = float(self._total_co2)
        summary['steps'] = len(self.history)

        return summary

    def export(self, filepath: str):
        """导出历史数据到JSON"""
        data = {
            'intersection_id': self.intersection_id,
            'edge_ids': self.edge_ids,
            'steps': len(self.history),
            'metrics': [asdict(m) for m in self.history],
            'summary': self.get_summary(),
        }
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def reset(self):
        """重置采集器"""
        self.history.clear()
        self._total_throughput = 0
        self._total_fuel = 0.0
        self._total_co2 = 0.0
        self._vehicle_departure.clear()


def get_approach_edges(tl_id: str, traci_conn=None) -> List[str]:
    """获取路口的进口道edge ID列表

    Args:
        tl_id: 交通信号灯ID
        traci_conn: TraCI连接对象

    Returns:
        进口道edge ID列表
    """
    if traci_conn is None:
        import traci
        traci_conn = traci

    controlled_lanes = traci_conn.trafficlight.getControlledLanes(tl_id)
    edges = set()
    for lane in controlled_lanes:
        try:
            edge_id = traci_conn.lane.getEdgeID(lane)
            edges.add(edge_id)
        except Exception:
            # fallback: 从lane ID截取edge ID（去掉最后的_lane_index）
            if '_' in lane:
                edge_id = lane.rsplit('_', 1)[0]
                edges.add(edge_id)
    return sorted(edges)
