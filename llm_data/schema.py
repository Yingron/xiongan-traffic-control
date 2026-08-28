"""LLM 微调数据集 schema：事件类别、场景表、扰动规格与规则 oracle 默认阈值。

赛道 C（AI 应用型）的"云脑"任务定义：
  输入 = 单路口最近一个时间窗的交通状态序列（文本化）
  输出 = {"event": "正常|拥堵|溢出|事件", "confidence": 0~1, "advice": "中文管控建议"}
标签由规则 oracle 自动生成（施工占道注入真值 + 排队/占有率阈值），
保证 1.0 置信度的"教师信号"，供 LoRA 微调监督使用。
"""
from __future__ import annotations

# ========== 事件类别（中文标签 = 输出 JSON 的 event 字段） ==========
EVENT_NORMAL = "正常"
EVENT_CONGESTION = "拥堵"
EVENT_SPILLOVER = "溢出"
EVENT_INCIDENT = "事件"
EVENT_CLASSES = (EVENT_NORMAL, EVENT_CONGESTION, EVENT_SPILLOVER, EVENT_INCIDENT)

EVENT_EN = {
    EVENT_NORMAL: "normal",
    EVENT_CONGESTION: "congestion",
    EVENT_SPILLOVER: "spillover",
    EVENT_INCIDENT: "incident",
}

# 严重度（oracle 判定优先级）：事件 > 溢出 > 拥堵 > 正常
EVENT_SEVERITY = {EVENT_NORMAL: 0, EVENT_CONGESTION: 1, EVENT_SPILLOVER: 2, EVENT_INCIDENT: 3}

DIRECTION_CN = {"N": "北", "S": "南", "E": "东", "W": "西"}

# ========== 真实场景表：sumo 路由文件 / 定周期配时 period / 中文场景名 / 起始时刻（小时） ==========
# period 与 data/timing_plans.json 的键一致（RealFixedTimeController 按 period 装真实配时）。
SCENARIOS: dict[str, dict] = {
    "real_peak": {"rou": "xiongan_real_peak.rou.xml", "period": "peak", "cn": "早高峰", "start_hour": 7},
    "real_offpeak": {"rou": "xiongan_real_offpeak.rou.xml", "period": "offpeak", "cn": "平峰", "start_hour": 14},
    "real_evening": {"rou": "xiongan_real_evening.rou.xml", "period": "evening", "cn": "晚高峰", "start_hour": 17},
}

# ========== 扰动规格（事件真值来源） ==========
PERTURBATION_NONE = "none"
PERTURBATION_CONSTRUCTION = "construction"
# 施工占道：sumo_files/xiongan_30_construction.add.xml 对边 e_J20_J25 双车道
# 在 [60,300]s 限速 5 m/s。J25 的北向进口车道即 e_J20_J25_0/1
# （docs/lane_mapping.json 中 J25.N），故受影响路口/方向为 J25 北向。
PERTURBATION_SPECS: dict[str, dict | None] = {
    PERTURBATION_NONE: None,
    PERTURBATION_CONSTRUCTION: {
        "add_file": "xiongan_30_construction.add.xml",
        "affected_junction": "J25",
        "direction": "N",
        "window_s": (60, 300),  # 注入真值窗口（绝对仿真时间）
        "speed_limit_mps": 5.0,
    },
}

# ========== 规则 oracle 默认阈值 ==========
# 实测标定（2026-08-24）：600s 冒烟方向最大排队 p50=7/p90=15/p99≈22；
# 7200s 全量（real_peak-construction）p50=8/p90=24/p99=47/max=52——晚段排队显著更深，
# 阈值按全量 p90 取整：溢出 ≈ 最严重 10% 窗口，拥堵 ≈ 次严重 25%（见 data/llm/smoke_full_stats.json）。
DEFAULT_THRESHOLDS: dict = {
    "spillover_queue": 24,       # 方向排队 ≥ 该值（辆，含该方向全部进口车道）→ 溢出回堵风险
    "congestion_queue": 10,      # 方向排队 ≥ 该值 → 拥堵
    "congestion_occupancy": 0.35,  # 方向平均占有率 ≥ 该值 → 拥堵
    "persistence": 0.5,          # 窗口内满足条件的采样点占比下限（避免瞬时抖动误标）
}

# ========== 数据采样参数 ==========
DEFAULT_SAMPLE_SEC = 5    # 状态采样步长（秒）
DEFAULT_WINDOW_SEC = 30   # 输入窗口长度（秒）
DEFAULT_LABEL_STRIDE = None  # 标注步长，默认 = window_sec（窗口不重叠）
DEFAULT_BEGIN = 0
DEFAULT_END = 7200        # 与真实场景 rou 的注入窗口一致（real_scenario_stats.json）
