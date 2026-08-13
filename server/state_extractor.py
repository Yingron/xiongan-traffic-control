"""状态提取器 - 从TraCI提取660维全局状态（30路口 × 22维）

实现直接复用训练环境的 env/global_state.py（docs/lane_mapping.json 几何映射），
避免 20 路口时代的“车道名前缀推断方向”逻辑在新路网（e_xxx_0 命名）下失效。
保持 StateExtractor 类接口不变，供 scripts/validate_setup.py 等旧入口使用。
"""
from __future__ import annotations

from typing import Any
import numpy as np

from configs.constants import (
    INTERSECTION_ORDER,
    FEATURES_PER_INTERSECTION,
    STATE_DIMENSION,
    DIRECTIONS,
)
from env.global_state import (
    get_global_state as _get_global_state,
    parse_state as _parse_state,
)


class StateExtractor:
    """从TraCI提取660维全局状态向量"""

    def __init__(self, sim_start_hour: float = 7.0):
        self._sim_start_hour = sim_start_hour

    def get_global_state(self, traci: Any) -> np.ndarray:
        """获取完整的660维状态向量（30路口 × 22维）"""
        return _get_global_state(num_intersections=len(INTERSECTION_ORDER))

    def parse_state(self, state: np.ndarray) -> dict:
        """解析状态向量为结构化数据"""
        return _parse_state(state)
