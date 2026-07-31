"""雄安环境封装 - 兼容旧版XionganEnv接口"""
from __future__ import annotations

from typing import Any, Optional, Tuple
import numpy as np

from env.env import TrafficSignalEnv
from configs.constants import SUMO_FILES_DIR


class XionganEnv(TrafficSignalEnv):
    """兼容旧版XionganEnv接口的环境类

    继承自TrafficSignalEnv，提供向后兼容的API。
    """

    def __init__(
        self,
        sumo_cfg_path: Optional[str] = None,
        use_gui: bool = False,
        max_steps: int = 3600,
        delta_time: int = 5,
        seed: Optional[int] = None,
    ):
        if sumo_cfg_path is None:
            sumo_cfg_path = str(SUMO_FILES_DIR / "xiongan.sumocfg")

        super().__init__(
            sumo_cfg_path=sumo_cfg_path,
            use_gui=use_gui,
            max_steps=max_steps,
            delta_time=delta_time,
            seed=seed,
        )

    def reset(self, seed: Optional[int] = None, options: Optional[dict] = None):
        """重置环境 - 兼容旧版接口"""
        obs, info = super().reset(seed=seed, options=options)
        return obs, info

    def step(self, action: Any):
        """执行一步 - 兼容旧版接口，支持4元组返回"""
        obs, reward, terminated, truncated, info = super().step(action)
        done = terminated or truncated
        return obs, reward, done, info
