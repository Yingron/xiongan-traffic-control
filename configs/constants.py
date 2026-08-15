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

# ========== rl4 相位程序模板（按 sumo_files/xiongan_30.net.xml 的 rl4 program 相位状态分组）==========
# 30 个路口的 4 动作程序并非同构：action_0/action_3 在部分模板上可能是"几乎全红"的转向相位
# （如模板C的 action_0='rrrrggrgrrrr' 仅放右转），而模板A的 action_0 是真·直行主相位。
# 共享参数 DQN 若按路口均匀采样，模板A(20/30=67%)会主导梯度，模型把 action_0/3 学成
# "高价值直行相位"，在模板C上 90% 时间误选全红相位（见 memories/first-model-eval-real-peak）。
# 分组由 scripts/validate_network.py --check-templates 与路网 rl4 状态逐项比对，防路网重生成后漂移。
INTERSECTION_TEMPLATES: dict[str, tuple[str, ...]] = {
    "A": ("J01", "J03", "J04", "J06", "J08", "J09", "J11", "J12", "J15", "J16",
          "J18", "J19", "J20", "J21", "J22", "J23", "J24", "J25", "J28", "J29"),
    "B": ("J13", "J26", "J27", "J30"),
    "C": ("J05", "J07", "J10"),
    "D": ("J14", "J17"),
    "E": ("J02",),
}
# 每模板训练采样权重：保证少数模板合计 ≥ 30%（实际 55%），模板C（已证实的失败模板）2 倍加权。
# 模板内路口等概率采样。None = 按路口均匀采样（旧行为，仅调试用）。
TEMPLATE_WEIGHTS: dict[str, float] = {
    "A": 0.45,
    "B": 0.15,
    "C": 0.20,
    "D": 0.10,
    "E": 0.10,
}

# ========== 需求门控动作掩码 ==========
# 相位所服务链路无排队车辆（halting ≥ 阈值）时该动作无效。掩码由
# env/global_state.compute_action_mask 按 rl4 相位状态的绿灯链路动态计算，
# 以最后 4 维追加进观测（22→26 维，公开全局状态契约 660 维不变）。
# 2026-08-14 首版仅对模板C（J05/J07/J10，T型路口）启用：其 4 相位各服务单一流向
# （action_0 南向右转 / action_1 南向左转 / action_2 东西向主相位 / action_3 东向左转），
# 共享策略会锁定相位子集饿死主相位（见 memories/2m-anticollapse-eval）。
# 1M 训练后发现坍缩迁移到模板A（无掩码保护，最后 25 万步 action_0 锁定 93%→全网死锁），
# 需求门控本身能打断"空相位锁定"的自我强化循环，故推广到全部模板。
# 全部相位都无需求时（路口空闲）兜底全 1，避免死锁。
ACTION_MASK_TEMPLATES: tuple[str, ...] = tuple(INTERSECTION_TEMPLATES.keys())
ACTION_MASK_QUEUE_THRESHOLD: int = 1  # 相位绿灯链路 halting 车辆数达到该值才视为"有需求"

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
