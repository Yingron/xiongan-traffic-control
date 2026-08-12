"""项目常量和配置"""
from __future__ import annotations

from pathlib import Path

INTERSECTION_ORDER = tuple(f"J{i:02d}" for i in range(1, 31))
STATE_DIMENSION = 660
FEATURES_PER_INTERSECTION = 22
ACTION_COUNT_PER_INTERSECTION = 4
ACTION_NAMES = ("NS_Straight", "NS_Left", "EW_Straight", "EW_Left")
DIRECTIONS = ("N", "S", "E", "W")
MIN_GREEN_SECONDS = 15
YELLOW_TRANSITION_SECONDS = 3

# 真实定周期基线专用哨兵动作：
# 值为 -1，表示"不干预信号"——由 baselines/fixed_time.py 在 env 上安装的真实配时
# 程序（data/timing_plans.json）按固定周期自主运行，env.step 不做任何相位覆盖。
# 见 baselines/fixed_time.py 与 env/single_intersection_env.py::step。
FIXED_TIME_CONTROL = -1

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUMO_FILES_DIR = PROJECT_ROOT / "sumo_files"
DOCS_DIR = PROJECT_ROOT / "docs"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
DATA_DIR = PROJECT_ROOT / "data"

DEFAULT_SUMO_CONFIG = SUMO_FILES_DIR / "xiongan_30.sumocfg"
DEFAULT_NET_FILE = SUMO_FILES_DIR / "xiongan_30.net.xml"
DEFAULT_ROU_FILE = SUMO_FILES_DIR / "xiongan_30.rou.xml"

STATE_LAYOUT_VERSION = "1.0"
REWARD_VERSION = "v3"
API_VERSION = "v1"
