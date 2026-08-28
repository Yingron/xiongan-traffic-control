"""规则 oracle：给单路口状态窗口打事件标签并生成管控建议（教师信号）。

优先级：事件（扰动注入真值）> 溢出 > 拥堵 > 正常。
溢出/拥堵要求窗口内满足条件的采样点占比 ≥ persistence，避免瞬时抖动误标。
同级别多方向同时触发时取排队最严重的方向。
"""
from __future__ import annotations

import math
from typing import Any

from configs.constants import DIRECTIONS

from llm_data.schema import (
    DEFAULT_THRESHOLDS,
    DIRECTION_CN,
    EVENT_CLASSES,
    EVENT_CONGESTION,
    EVENT_EN,
    EVENT_INCIDENT,
    EVENT_NORMAL,
    EVENT_SEVERITY,
    EVENT_SPILLOVER,
    PERTURBATION_SPECS,
)

_PHASE_STATE_MAP = {"G": "绿灯", "g": "绿灯", "y": "黄灯", "r": "全红"}


class EventOracle:
    """规则标注器。perturbation=None 表示无扰动注入（纯真实需求场景）。"""

    def __init__(self, perturbation: str | None = None, thresholds: dict | None = None) -> None:
        if perturbation is not None and perturbation not in PERTURBATION_SPECS:
            raise ValueError(f"未知扰动类型: {perturbation!r}，可选 {list(PERTURBATION_SPECS)}")
        self.perturbation = perturbation
        self.thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}

    # ---- 对外接口 ----
    def label_window(self, junction: str, sim_time: float, snapshots: list[dict]) -> dict:
        """给一个窗口打标签。

        Args:
            junction: 路口 ID（J01~J30）
            sim_time: 窗口结束时刻（绝对仿真秒）
            snapshots: 按时间升序的状态快照列表（见 features.extract_intersection_raw）

        Returns:
            {"event": 中文类别, "event_en": 英文类别, "confidence": 1.0,
             "advice": 建议, "evidence": 判定依据}
        """
        spec = PERTURBATION_SPECS.get(self.perturbation)
        # 1) 事件：扰动注入真值窗口内的受影响路口/方向
        if spec is not None:
            t0, t1 = spec["window_s"]
            if junction == spec["affected_junction"] and t0 <= sim_time <= t1:
                return self._result(
                    EVENT_INCIDENT, spec["direction"], sim_time, snapshots,
                    evidence={"trigger": "injection",
                              "affected_junction": spec["affected_junction"],
                              "direction": spec["direction"],
                              "window_s": [t0, t1],
                              "speed_limit_mps": spec["speed_limit_mps"]},
                )

        # 2) 溢出 / 拥堵：按方向聚合窗口判定
        n = len(snapshots)
        persist_min = max(1, math.ceil(n * self.thresholds["persistence"]))
        best: tuple[int, str, float, str, int] | None = None  # (严重度, 方向, 最大排队, trigger, 命中数)

        for direction in DIRECTIONS:
            queues = [snap["dirs"][direction]["queue"] for snap in snapshots]
            occs = [snap["dirs"][direction]["occupancy"] for snap in snapshots]
            spill_hits = sum(
                1 for q in queues if q >= self.thresholds["spillover_queue"]
            )
            cong_hits = sum(
                1 for q, o in zip(queues, occs)
                if q >= self.thresholds["congestion_queue"]
                or o >= self.thresholds["congestion_occupancy"]
            )
            if spill_hits >= persist_min:
                candidate = (EVENT_SEVERITY[EVENT_SPILLOVER], direction, max(queues), "spillover", spill_hits)
            elif cong_hits >= persist_min:
                candidate = (EVENT_SEVERITY[EVENT_CONGESTION], direction, max(queues), "congestion", cong_hits)
            else:
                continue
            if best is None or candidate[0] > best[0] or (
                candidate[0] == best[0] and candidate[2] > best[2]
            ):
                best = candidate

        if best is None:
            return self._result(
                EVENT_NORMAL, None, sim_time, snapshots, evidence={"trigger": "none"}
            )

        severity, direction, value, trigger, hits = best
        event = EVENT_SPILLOVER if severity == EVENT_SEVERITY[EVENT_SPILLOVER] else EVENT_CONGESTION
        evidence = {
            "trigger": trigger,
            "direction": direction,
            "value": value,
            "threshold": (self.thresholds["spillover_queue"]
                          if trigger == "spillover" else self.thresholds["congestion_queue"]),
            "hits": hits,
            "of": n,
        }
        return self._result(event, direction, sim_time, snapshots, evidence=evidence)

    # ---- 内部 ----
    def _result(self, event: str, direction: str | None, sim_time: float,
                snapshots: list[dict], evidence: dict) -> dict:
        # 建议文案口径：排队/占有率取窗口最大值（与 evidence 一致），均速取最新快照
        queue = occ = speed = 0
        if direction is not None:
            queues = [snap["dirs"][direction]["queue"] for snap in snapshots]
            occs = [snap["dirs"][direction]["occupancy"] for snap in snapshots]
            queue = max(queues)
            occ = max(occs)
            speed = snapshots[-1]["dirs"][direction].get("speed_kmh", 0)
        advice = self._advice(event, direction, queue, occ, speed, snapshots[-1])
        return {
            "event": event,
            "event_en": EVENT_EN[event],
            "confidence": 1.0,  # oracle 真值
            "advice": advice,
            "evidence": evidence,
        }

    def _advice(self, event: str, direction: str | None, queue: int,
                occupancy: float, speed: float, current: dict) -> str:
        """按事件类别生成管控建议；拥堵/溢出时相位感知（当前相位是否放行该方向）。"""
        if event == EVENT_NORMAL or direction is None:
            return "路网运行平稳，建议保持当前信号配时方案，无需调整。"

        dir_cn = DIRECTION_CN[direction]
        serving = dir_cn in current.get("phase_name", "")
        if event == EVENT_CONGESTION:
            if serving:
                return (
                    f"{dir_cn}向排队{queue}辆、占有率{occupancy:.0%}，"
                    f"当前相位正在放行该方向，建议适当延长绿灯时长5~10秒。"
                )
            return (
                f"{dir_cn}向排队{queue}辆、占有率{occupancy:.0%}，"
                f"建议优先切换至放行{dir_cn}向的相位。"
            )
        if event == EVENT_SPILLOVER:
            if serving:
                return (
                    f"{dir_cn}向排队{queue}辆接近上游路口，存在溢出回堵风险，"
                    f"建议维持放行并通知上游路口控制汇入车流。"
                )
            return (
                f"{dir_cn}向排队{queue}辆接近上游路口，存在溢出回堵风险，"
                f"建议立即切换至放行{dir_cn}向的相位，并协调上游路口减少汇入。"
            )
        # 事件
        return (
            f"{dir_cn}向检测到施工占道事件，通行速度明显下降"
            f"（当前均速{speed:.0f}km/h），建议发布绕行提示、设置限速警示，"
            f"并优先放行{dir_cn}向疏散积压车辆。"
        )
