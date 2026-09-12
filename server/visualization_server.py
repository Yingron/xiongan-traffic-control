"""可视化 WebSocket 服务器

连接 SUMO 仿真与 Unity 可视化前端：
  1. 启动 SUMO（支持 真实早高峰/平峰/晚高峰 三种场景）
  2. 加载 DQN 模型进行信号灯控制推理
  3. 通过 WebSocket 向 Unity 推送车辆位置、信号灯相位、指标数据
  4. 接收 Unity 端的场景切换指令

用法:
    python server/visualization_server.py --scenario real_peak --port 8765
    python server/visualization_server.py --scenario real_offpeak --no-model
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
import hashlib
import threading
from pathlib import Path
from typing import Any

import numpy as np

# ── 项目路径 ──
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

SUMO_FILES_DIR = PROJECT_ROOT / "sumo_files"
MODEL_DIR = PROJECT_ROOT / "models" / "dqn"
EDGE_MODEL_REGISTRY_PATH = PROJECT_ROOT / "configs" / "edge_model_registry.json"

# 30 路口顺序/特征维度统一取自 configs.constants（与训练环境一致）
from configs.constants import (
    INTERSECTION_ORDER,
    FEATURES_PER_INTERSECTION,
    ACTION_NAMES,
    INTERSECTION_TEMPLATES,
)
# 状态提取复用训练环境的全局状态实现（docs/lane_mapping.json 几何映射，30路口×22维）
from env.global_state import get_global_state
# LLM 云脑告警：特征文本化与 llama.cpp 调用与训练/评估链路同源
from llm_data.features import extract_intersection_raw
from llm_data.text_format import format_window_text
from server.llm_service import LLMService, LLMServiceError

# ── 场景配置 ──
SCENARIOS = {
    "real_peak": {
        "label": "真实早高峰(07:00-09:00)",
        "sumocfg": SUMO_FILES_DIR / "xiongan_real_peak.sumocfg",
        "edge_model_id": "edge-real-peak-onnx-v1",
    },
    "real_offpeak": {
        "label": "真实平峰(14:30-16:30)",
        "sumocfg": SUMO_FILES_DIR / "xiongan_real_offpeak.sumocfg",
        # offpeak 专用模型两次训练均病态（见 models/dqn/archive/ failed_v1/v2），
        # 正式方案：evening 模型跨场景泛化（30路口全量 reward −1.6%，代表8路口 +5.4%）
        "edge_model_id": "edge-real-offpeak-via-evening-onnx-v1",
    },
    "real_evening": {
        "label": "真实晚高峰(17:30-19:30)",
        "sumocfg": SUMO_FILES_DIR / "xiongan_real_evening.sumocfg",
        "edge_model_id": "edge-real-evening-onnx-v1",
    },
}

MIN_GREEN_SECONDS = 15
STEP_SECONDS = 5  # 每次推进的仿真秒数

# ── LLM 云脑告警配置 ──
# 训练文本的时钟以整点起步（见 llm_data/text_format._clock），此处对齐：
#   real_peak 07:00 / real_offpeak 14:00 / real_evening 17:00 起算仿真时间
SCENARIO_START_HOURS = {"real_peak": 7, "real_offpeak": 14, "real_evening": 17}
# rl4 相位无名（sumo net.xml 的 programID="rl4" 未写 name），LLM 文本需要语义相位名；
# 与 configs.constants.ACTION_NAMES 同序（0/1/2/3 → 南北直行/南北左转/东西直行/东西左转）。
# 训练文本形态为"南北向直行(绿灯)"，实时侧按相位状态字符串补绿灯/全红后缀。
PHASE_SEMANTIC_CN = {
    0: "南北向直行", 1: "南北向左转", 2: "东西向直行", 3: "东西向左转",
}
LLM_ALERT_DEFAULT_INTERVAL = 60.0  # 自动诊断间隔（秒，真实时间）
LLM_ALERT_WINDOW_SEC = 35  # 伪窗口覆盖秒数（保持与训练"最近N秒、每5秒采样"格式一致）
LLM_ALERT_SAMPLE_SEC = 5


def find_sumo_binary(use_gui: bool = False) -> str:
    home = os.environ.get("SUMO_HOME")
    if home:
        exe = Path(home) / "bin" / ("sumo-gui.exe" if use_gui else "sumo.exe")
        if exe.exists():
            return str(exe)
    return "sumo-gui" if use_gui else "sumo"


class VisualizationServer:
    """SUMO + DQN + WebSocket 可视化服务器"""

    def __init__(self, scenario: str = "real_peak", port: int = 8765,
                 use_model: bool = True, use_gui: bool = False,
                 model_override: Path | None = None,
                 llm_enabled: bool = True, llm_interval: float = LLM_ALERT_DEFAULT_INTERVAL) -> None:
        self.scenario = scenario
        self.port = port
        self.use_model = use_model
        self.use_gui = use_gui
        self.model_override = model_override
        self.llm_enabled = llm_enabled
        self.llm_interval = llm_interval
        self._traci: Any = None
        self._model: Any = None
        self._model_backend: str | None = None
        self._model_id: str | None = None
        self._sumo_proc: Any = None
        self._clients: set[Any] = set()
        self._current_actions: dict[str, int] = {}
        self._last_requested_actions: dict[str, int] = {}
        self._last_action_masks: dict[str, list[int]] = {}
        self._last_q_values: dict[str, list[float]] = {}
        self._last_inference_latency_ms: float = 0.0
        self._phase_changed_at: dict[str, float] = {}
        # Remaining minimum-green hold captured at decision time.  The snapshot is
        # emitted after SUMO advances five seconds, so recomputing this value there
        # would obscure why the earlier action was constrained.
        self._last_constraint_remaining: dict[str, float] = {}
        # WebSocket 场景切换在 executor 线程执行；SUMO 步进在服务线程执行。
        # 二者必须串行，避免切换期间对已关闭 TraCI socket 继续读写。
        self._simulation_lock = threading.RLock()
        self._running = False
        self._step_count = 0
        # LLM 云脑告警状态（演示用慢周期决策：60s 级一次，5~9s 一次分析）
        self._llm_service: LLMService | None = None
        self._last_state: np.ndarray | None = None
        self._llm_alert: dict[str, Any] | None = None
        self._llm_alert_clock: str | None = None
        self._llm_alert_at: float = 0.0
        self._llm_busy = False
        self._llm_fail_reason: str | None = None

    # ── SUMO 管理 ──

    @staticmethod
    def _find_free_port() -> int:
        """找到一个可用的本地端口"""
        import socket
        for port in range(8814, 9000):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(("127.0.0.1", port))
                    return port
            except OSError:
                continue
        raise RuntimeError("无法找到可用端口 (8814-8999)")

    def _start_sumo(self) -> None:
        import traci
        self._traci = traci

        cfg = SCENARIOS[self.scenario]["sumocfg"]
        if not cfg.exists():
            raise FileNotFoundError(f"SUMO 配置文件不存在: {cfg}")

        binary = find_sumo_binary(self.use_gui)
        port = self._find_free_port()

        cmd = [binary, "-c", str(cfg), "--no-step-log", "--no-warnings",
               "--time-to-teleport", "-1", "--duration-log.disable", "true"]

        print(f"[Server] 启动 SUMO (端口 {port})...")

        # traci.start() 不支持 cwd，需临时切换目录
        old_cwd = os.getcwd()
        os.chdir(str(cfg.parent))
        try:
            traci.start(cmd, port=port, numRetries=60)
        finally:
            os.chdir(old_cwd)

        # 验证连接
        sim_time = float(traci.simulation.getTime())
        print(f"[Server] TraCI 连接成功 (端口 {port}) — 仿真时间: {sim_time:.1f}s")

        # 推进几步让车辆进入路网
        for _ in range(10):
            traci.simulationStep()

        # 30 路口正式路网只使用 rl4 四相位程序。显式选中它，避免 --no-model
        # 基线演示依赖 SUMO 文件中某个默认程序，或把旧 program 0 的黄灯当作动作相位。
        sim_time = float(traci.simulation.getTime())
        for tl_id in INTERSECTION_ORDER:
            traci.trafficlight.setProgram(tl_id, "rl4")
            self._current_actions[tl_id] = int(traci.trafficlight.getPhase(tl_id))
            self._phase_changed_at[tl_id] = sim_time
            self._last_constraint_remaining[tl_id] = 0.0

        veh_count = len(traci.vehicle.getIDList())
        print(f"[Server] SUMO 已启动 — 场景: {SCENARIOS[self.scenario]['label']} — 车辆数: {veh_count}")

    def _is_traci_connected(self) -> bool:
        """检查 TraCI 是否已连接（兼容不同版本的 traci）"""
        if self._traci is None:
            return False
        try:
            # 方法1: 尝试 getConnection (未连接会抛异常)
            self._traci.getConnection()
            return True
        except Exception:
            pass
        try:
            # 方法2: 尝试执行一个简单命令
            self._traci.simulation.getTime()
            return True
        except Exception:
            return False

    def _close_sumo(self) -> None:
        if self._traci is not None:
            try:
                self._traci.close(False)
            except Exception:
                pass
        self._sumo_proc = None

    # ── DQN 模型 ──

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _load_formal_edge_model(self) -> None:
        """Load the registry-approved ONNX model for the active scenario.

        The edge registry is the deployable source of truth.  It deliberately
        excludes experimental INT8 artefacts whose real-state fidelity failed.
        """
        registry = json.loads(EDGE_MODEL_REGISTRY_PATH.read_text(encoding="utf-8"))
        model_id = SCENARIOS[self.scenario]["edge_model_id"]
        entry = registry.get("models", {}).get(model_id)
        if not isinstance(entry, dict) or entry.get("status") != "ready":
            raise RuntimeError(f"正式边缘模型未就绪: {model_id}")
        artifact = PROJECT_ROOT / str(entry["artifact_path"])
        if not artifact.is_file():
            raise FileNotFoundError(f"正式边缘模型不存在: {artifact}")
        expected_sha = entry.get("sha256")
        actual_sha = self._sha256(artifact)
        if expected_sha and actual_sha != expected_sha:
            raise RuntimeError(f"正式边缘模型校验和不匹配: {artifact.name}")

        from edge_deploy.inference import EdgeInference

        self._model = EdgeInference(artifact)
        self._model_backend = "edge-onnx"
        self._model_id = model_id
        print(f"[Server] 正式边缘模型已加载: {model_id} → {artifact.name}")

    def _load_model(self) -> None:
        # 场景热切换时不能继续保留上一场景的模型。
        self._model = None
        self._model_backend = None
        self._model_id = None
        if not self.use_model:
            print("[Server] 未加载 DQN 模型（--no-model 模式），使用固定配时")
            return

        try:
            if self.model_override is None:
                self._load_formal_edge_model()
                return

            model_path = self.model_override
            if not model_path.exists():
                raise FileNotFoundError(f"本地验证覆盖模型不存在: {model_path}")
            # 保留 .zip 覆盖模式，便于回归比对；正式三场景运行不会走此路径。
            if model_path.suffix.lower() == ".zip":
                from training.masked_policy import MaskableDQN

                self._model = MaskableDQN.load(str(model_path))
                self._model_backend = "sb3-zip-override"
            else:
                from edge_deploy.inference import EdgeInference

                self._model = EdgeInference(model_path)
                self._model_backend = f"edge-{model_path.suffix.lower().lstrip('.')}"
            self._model_id = f"local-override:{model_path.name}"
            print(f"[Server] 本地验证覆盖模型已加载: {model_path.name}")
        except Exception as e:
            print(f"[Server] DQN 模型加载失败: {e}；本次不会执行模型推理")
            self._model = None

    # ── 状态提取 ──

    def _extract_state(self) -> np.ndarray:
        """提取 660 维全局状态向量 (30路口 × 22维)

        复用训练环境 env/global_state.get_global_state：按 docs/lane_mapping.json
        的几何映射聚合每个进口车道的排队/等待/占有率，与 DQN 训练时的状态口径一致。
        """
        return get_global_state(num_intersections=len(INTERSECTION_ORDER))

    def _get_dqn_actions(self, state: np.ndarray) -> dict[str, int]:
        """使用 DQN 模型推理得到 30 个路口的动作

        兼容 26 维掩码模型：按模型观测维度为每个路口追加需求门控掩码
        （22 状态 + 4 掩码，见 env/global_state.get_action_masks）。
        """
        if self._model is None:
            self._last_q_values = {}
            self._last_inference_latency_ms = 0.0
            return dict(self._current_actions)

        masks = None
        if self._traci is not None:
            from env.global_state import get_action_masks

            masks = get_action_masks(self._traci, INTERSECTION_ORDER)

        self._last_action_masks = (
            {tl_id: [int(value) for value in masks[idx]] for idx, tl_id in enumerate(INTERSECTION_ORDER)}
            if masks is not None
            else {}
        )

        local_states = np.asarray(
            [state[index * FEATURES_PER_INTERSECTION:(index + 1) * FEATURES_PER_INTERSECTION]
             for index in range(len(INTERSECTION_ORDER))],
            dtype=np.float32,
        )
        if self._model_backend and self._model_backend.startswith("edge-"):
            if masks is None:
                raise RuntimeError("正式边缘模型推理需要 30×4 动作掩码")
            q_values, latency_ms = self._model.predict_q(local_states, masks)
            q_rows = np.asarray(q_values, dtype=np.float32)
            predictions = np.argmax(q_rows, axis=1).astype(np.int64)
            self._last_inference_latency_ms = float(latency_ms)
            self._last_q_values = {
                tl_id: [float(value) for value in q_rows[index]]
                for index, tl_id in enumerate(INTERSECTION_ORDER)
            }
            return {
                tl_id: int(predictions[index])
                for index, tl_id in enumerate(INTERSECTION_ORDER)
            }

        self._last_q_values = {}
        self._last_inference_latency_ms = 0.0
        obs_dim = int(np.prod(self._model.observation_space.shape))
        actions: dict[str, int] = {}
        for idx, tl_id in enumerate(INTERSECTION_ORDER):
            local_state = local_states[idx]
            if masks is not None:
                local_state = np.concatenate([local_state, masks[idx]])
            if local_state.size != obs_dim:
                raise RuntimeError(
                    f"模型观测维度不匹配: {tl_id} 得到 {local_state.size} 维，模型需要 {obs_dim} 维"
                )
            action, _ = self._model.predict(local_state.astype(np.float32), deterministic=True)
            actions[tl_id] = int(action)
        return actions

    def _apply_actions(self, actions: dict[str, int]) -> None:
        """应用动作到 SUMO 信号灯（含最小绿灯约束）"""
        traci = self._traci
        sim_time = float(traci.simulation.getTime())

        for tl_id in INTERSECTION_ORDER:
            requested = actions[tl_id]
            current = int(traci.trafficlight.getPhase(tl_id))
            elapsed = sim_time - self._phase_changed_at[tl_id]

            if requested != current and elapsed < MIN_GREEN_SECONDS:
                self._current_actions[tl_id] = current
                self._last_constraint_remaining[tl_id] = MIN_GREEN_SECONDS - elapsed
            else:
                self._last_constraint_remaining[tl_id] = 0.0
                if requested != current:
                    traci.trafficlight.setPhase(tl_id, requested)
                    self._phase_changed_at[tl_id] = sim_time
                self._current_actions[tl_id] = requested

    # ── 车辆位置提取 ──

    def _extract_vehicles(self) -> list[dict]:
        """提取所有车辆的实时位置和状态"""
        traci = self._traci
        vehicles: list[dict] = []
        veh_ids = traci.vehicle.getIDList()

        for vid in veh_ids:
            try:
                x, y = traci.vehicle.getPosition(vid)
                angle = float(traci.vehicle.getAngle(vid))
                speed = float(traci.vehicle.getSpeed(vid))
                vtype = traci.vehicle.getTypeID(vid)

                vehicles.append({
                    "id": vid,
                    "x": round(float(x), 2),
                    "y": round(float(y), 2),
                    "angle": round(angle, 1),
                    "speed": round(speed, 2),
                    "type": vtype,
                })
            except traci.exceptions.TraCIException:
                continue

        return vehicles

    # ── 指标计算 ──

    def _compute_metrics(self) -> dict:
        traci = self._traci
        total_queue = 0.0
        total_wait = 0.0
        total_speed = 0.0
        veh_count = 0
        arrived = traci.simulation.getArrivedNumber()
        departed = traci.simulation.getDepartedNumber()

        for vid in traci.vehicle.getIDList():
            try:
                speed = float(traci.vehicle.getSpeed(vid))
                total_speed += speed
                if speed < 0.1:
                    total_queue += 1
                total_wait += float(traci.vehicle.getWaitingTime(vid))
                veh_count += 1
            except Exception:
                continue

        return {
            "vehicle_count": veh_count,
            "avg_queue": round(total_queue / max(1, len(INTERSECTION_ORDER)), 2),  # 平均每路口排队
            "avg_wait": round(total_wait / max(1, veh_count), 2),
            "avg_speed": round(total_speed / max(1, veh_count), 2),
            "total_arrived": arrived,
            "total_departed": departed,
            "simulation_time": round(float(traci.simulation.getTime()), 1),
        }

    def _extract_traffic_lights(self) -> list[dict]:
        traci = self._traci
        tls: list[dict] = []
        for tl_id in INTERSECTION_ORDER:
            phase = int(traci.trafficlight.getPhase(tl_id)) % 4
            tls.append({
                "id": tl_id,
                "phase": phase,
                "phase_name": ["NS_Straight", "NS_Left", "EW_Straight", "EW_Left"][phase],
            })
        return tls

    @staticmethod
    def _template_for_junction(tl_id: str) -> str:
        for template, junctions in INTERSECTION_TEMPLATES.items():
            if tl_id in junctions:
                return template
        return "?"

    def _build_control_states(self, state: np.ndarray) -> list[dict]:
        """Build a JSON-list view of the real DQN decision contract for Unity.

        The existing object-shaped requested_actions/actions/action_masks fields remain for
        protocol compatibility.  Unity's JsonUtility cannot deserialize dictionaries, so this
        list mirrors the same values and adds the four queue inputs and masked Q values used by
        the deployed model.  Queue values are reconstructed from the normalized state contract
        (15 vehicles is the documented cap), rather than invented by the presentation layer.
        """
        sim_time = float(self._traci.simulation.getTime())
        rows: list[dict] = []
        for index, tl_id in enumerate(INTERSECTION_ORDER):
            offset = index * FEATURES_PER_INTERSECTION
            requested = int(self._last_requested_actions.get(tl_id, self._current_actions.get(tl_id, 0)))
            executed = int(self._current_actions.get(tl_id, requested))
            current_phase = int(self._traci.trafficlight.getPhase(tl_id)) % 4
            mask = self._last_action_masks.get(tl_id, [1, 1, 1, 1])
            q_values = self._last_q_values.get(tl_id, [])
            elapsed = max(0.0, sim_time - float(self._phase_changed_at.get(tl_id, sim_time)))
            rows.append({
                "id": tl_id,
                "template": self._template_for_junction(tl_id),
                "requested_action": requested,
                "executed_action": executed,
                "current_phase": current_phase,
                "constrained": requested != executed,
                "phase_elapsed": round(elapsed, 1),
                # Decision-time value.  current_phase and phase_elapsed are sampled
                # after the five-second SUMO advance and may legitimately differ
                # from the action issued at the start of that control interval.
                "min_green_remaining": round(
                    max(0.0, float(self._last_constraint_remaining.get(tl_id, 0.0))), 1
                ),
                "action_mask": [int(value) for value in mask],
                "q_values": [round(float(value), 4) for value in q_values],
                "queue_nsew": [
                    round(float(state[offset + direction]) * 15.0, 1)
                    for direction in range(4)
                ],
            })
        return rows

    # ── 仿真步进 ──

    def _simulation_step(self) -> dict:
        """Run one atomic SUMO/DQN step, never concurrently with a restart."""
        with self._simulation_lock:
            return self._simulation_step_locked()

    def _simulation_step_locked(self) -> dict:
        """执行一步仿真：状态提取 → DQN推理 → 应用动作 → 推进SUMO → 返回快照"""
        # 1. 提取状态
        state = self._extract_state()
        self._last_state = state

        # 2. DQN 推理
        actions = self._get_dqn_actions(state)
        self._last_requested_actions = dict(actions)

        # 3. 应用动作
        self._apply_actions(actions)

        # 4. 推进 SUMO
        traci = self._traci
        for _ in range(STEP_SECONDS):
            traci.simulationStep()

        self._step_count += 1

        # 5. 构建快照
        snapshot = {
            "type": "state",
            "step": self._step_count,
            "scenario": self.scenario,
            "scenario_label": SCENARIOS[self.scenario]["label"],
            "model_id": self._model_id,
            "model_backend": self._model_backend,
            "inference_latency_ms": round(self._last_inference_latency_ms, 4),
            "simulation_time": round(float(traci.simulation.getTime()), 1),
            "traffic_lights": self._extract_traffic_lights(),
            "vehicles": self._extract_vehicles(),
            "metrics": self._compute_metrics(),
            # requested_actions 为掩码 DQN 的原始决策；actions 为经过最小绿灯
            # 约束后实际写入 SUMO 的相位。两者分开可审计动作闭环。
            "requested_actions": dict(self._last_requested_actions),
            "actions": dict(self._current_actions),
            "action_masks": dict(self._last_action_masks),
            "control_states": self._build_control_states(state),
        }
        return snapshot

    # ── LLM 云脑告警（赛道 C：边缘 DQN 快决策 + 云端 LLM 慢周期诊断） ──

    @staticmethod
    def _clock_cn(sim_time: float, start_hour: int) -> str:
        """仿真秒 → "HH:MM:SS" 场景时钟（与 llm_data.text_format 同口径）。"""
        import datetime
        return (datetime.datetime(2026, 1, 1, start_hour)
                + datetime.timedelta(seconds=int(sim_time))).strftime("%H:%M:%S")

    def _rl4_phase_state(self, tl_id: str, phase: int) -> str:
        """rl4 相位状态后缀：按相位 state 字符串判定 绿灯/黄灯/全红。"""
        try:
            logic = next(
                (candidate for candidate in self._traci.trafficlight.getAllProgramLogics(tl_id)
                 if candidate.programID == "rl4"),
                None,
            )
            if logic is not None and phase < len(logic.phases):
                state = logic.phases[phase].state
                if "G" in state or "g" in state:
                    return "绿灯"
                if "Y" in state or "y" in state:
                    return "黄灯"
            return "全红"
        except Exception:
            return "全红"

    def _semantic_phase_name(self, tl_id: str, phase: int) -> str:
        """把无名的 rl4 相位映射为训练文本同形态的语义名，如"南北向直行(绿灯)"。"""
        base = PHASE_SEMANTIC_CN.get(int(phase) % 4, "未知相位")
        return f"{base}({self._rl4_phase_state(tl_id, phase)})"

    def _pick_candidate_junction(self) -> str:
        """按最新 660 维状态打分选"最需诊断"的路口：排队 + 等待 + 占有率加权。

        LLM 一次分析 5~9 秒，无法每步全路口分析；规则预筛把云端注意力
        集中到全网最异常的路口（演示时异常消失则退回正常诊断）。
        """
        state = self._last_state
        if state is None:
            return INTERSECTION_ORDER[0]
        scores: list[tuple[str, float]] = []
        for idx, tl_id in enumerate(INTERSECTION_ORDER):
            offset = idx * FEATURES_PER_INTERSECTION
            queue = float(np.sum(state[offset:offset + 4]))          # 0~4
            wait = float(np.sum(state[offset + 4:offset + 8]))       # 0~4
            occupancy = float(np.sum(state[offset + 8:offset + 12]))  # 0~4
            scores.append((tl_id, queue * 3.0 + wait * 2.0 + occupancy * 8.0))
        scores.sort(key=lambda item: item[1], reverse=True)
        return scores[0][0]

    def _build_llm_window_text(self, junction: str) -> str | None:
        """锁内取数：把当前快照外推为训练同形态的 8 采样伪窗口文本。

        extract_intersection_raw 的实时快照只有"当前时刻"，而微调输入是
        "最近 N 秒、每 5 秒采样"的多行窗口。逐行回填采样时刻构造同分布文本；
        车辆状态行本身是当前值（最近 35 秒内状态持续的代表性样本）。
        """
        if self._traci is None or not self._is_traci_connected():
            return None
        raw = extract_intersection_raw(self._traci, junction)
        sim_time = float(self._traci.simulation.getTime())
        raw["phase_name"] = self._semantic_phase_name(junction, int(raw["phase"]))
        snapshots = []
        for back in range(LLM_ALERT_WINDOW_SEC // LLM_ALERT_SAMPLE_SEC, -1, -1):
            snap = dict(raw)
            snap["t"] = sim_time - back * LLM_ALERT_SAMPLE_SEC
            snapshots.append(snap)
        return format_window_text(
            junction,
            SCENARIOS[self.scenario]["label"],
            SCENARIO_START_HOURS[self.scenario],
            sim_time,
            snapshots,
            LLM_ALERT_WINDOW_SEC,
            LLM_ALERT_SAMPLE_SEC,
            len(self._traci.vehicle.getIDList()),
        )

    def _run_llm_analysis_blocking(self, forced_junction: str | None = None) -> dict[str, Any] | None:
        """后台线程执行一次完整云脑诊断：取数（短占仿真锁）→ LLM HTTP（锁外）。

        Returns:
            llm_service.analyze 结果 + sim_time/sim_clock；失败返回 None。
        """
        if self._llm_service is None:
            try:
                self._llm_service = LLMService()
            except Exception as error:  # 构造失败（如缺依赖）
                self._llm_fail_reason = f"LLMService 初始化失败: {error}"
                return None

        if forced_junction is not None:
            if forced_junction not in INTERSECTION_ORDER:
                self._llm_fail_reason = f"未知路口: {forced_junction}"
                return None
            junction = forced_junction
        else:
            junction = self._pick_candidate_junction()

        with self._simulation_lock:
            text = self._build_llm_window_text(junction)
            if text is None:
                self._llm_fail_reason = "SUMO 未连接"
                return None
            sim_time = float(self._traci.simulation.getTime())
            sim_clock = self._clock_cn(sim_time, SCENARIO_START_HOURS[self.scenario])

        try:
            result = self._llm_service.analyze(text, junction=junction)
        except LLMServiceError as error:
            # llama-server 未启动等场景：记录原因、不推送告警，演示不中断
            self._llm_fail_reason = f"{error.code}: {error.message}"
            print(f"[LLM] 云脑分析失败({junction}): {error.code} {error.message}")
            return None
        except Exception as error:
            self._llm_fail_reason = str(error)
            print(f"[LLM] 云脑分析异常({junction}): {error}")
            return None

        result["sim_time"] = sim_time
        result["sim_clock"] = sim_clock
        print(f"[LLM] 云脑诊断 {junction}: {result['event']} "
              f"(置信度 {result['confidence']}, 耗时 {result['latency_ms']}ms, 仿真 {sim_clock})")
        return result

    def _make_alert_payload(self, result: dict[str, Any]) -> dict[str, Any]:
        """构造推送给 Unity 的 llm_alert 消息（只含展示字段，不带原始文本）。"""
        return {
            "type": "llm_alert",
            "junction": result.get("junction"),
            "event": result.get("event"),
            "event_en": result.get("event_en"),
            "confidence": result.get("confidence"),
            "advice": result.get("advice"),
            "latency_ms": result.get("latency_ms"),
            "sim_time": result.get("sim_time"),
            "sim_clock": result.get("sim_clock"),
            "scenario": self.scenario,
            "llm_backend": result.get("llm_backend"),
        }

    async def _dispatch_llm_alert(self, forced_junction: str | None = None) -> None:
        """触发一次云脑诊断并向全部客户端广播结果（busy 时丢弃本次触发）。

        分析失败（llama-server 未启动等）时广播 llm_alert_error，
        让 Unity 面板能显示"云脑离线"的具体原因而不是干等。
        """
        if not self.llm_enabled or self._llm_busy or not self._clients:
            return
        self._llm_busy = True
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, self._run_llm_analysis_blocking, forced_junction)
            if result is None:
                error_msg = {"type": "llm_alert_error",
                             "message": self._llm_fail_reason or "云脑分析失败"}
                raw = json.dumps(error_msg, ensure_ascii=False)
                for ws in list(self._clients):
                    try:
                        await asyncio.wait_for(ws.send(raw), timeout=2.0)
                    except Exception:
                        pass
                return
            self._llm_alert = result
            self._llm_alert_at = time.time()
            self._llm_alert_clock = result.get("sim_clock")
            self._llm_fail_reason = None
            payload = self._make_alert_payload(result)
            raw = json.dumps(payload, ensure_ascii=False)
            disconnected = set()
            for ws in list(self._clients):
                try:
                    await asyncio.wait_for(ws.send(raw), timeout=2.0)
                except Exception:
                    disconnected.add(ws)
            self._clients -= disconnected
        finally:
            self._llm_busy = False

    async def _llm_alert_loop(self) -> None:
        """慢周期云脑诊断循环：有客户端且距上次超过间隔时自动分析一次。"""
        while self._running:
            try:
                if (self._clients and not self._llm_busy
                        and (self._llm_alert is None
                             or time.time() - self._llm_alert_at >= self.llm_interval)):
                    await self._dispatch_llm_alert(None)
            except Exception as error:
                print(f"[LLM] 云脑循环异常: {error}")
            await asyncio.sleep(2.0)

    def _reset_llm_alert(self) -> None:
        """场景切换后丢弃旧场景的告警缓存。"""
        self._llm_alert = None
        self._llm_alert_clock = None
        self._llm_alert_at = 0.0
        self._llm_fail_reason = None

    # ── 场景切换 ──

    def _switch_scenario(self, new_scenario: str) -> dict:
        if new_scenario not in SCENARIOS:
            return {"type": "error", "message": f"未知场景: {new_scenario}"}

        if new_scenario == self.scenario:
            return {"type": "scenario_switched", "scenario": self.scenario, "message": "已是当前场景"}

        print(f"[Server] 切换场景: {self.scenario} → {new_scenario}")
        with self._simulation_lock:
            self._close_sumo()
            self.scenario = new_scenario
            self._start_sumo()
            self._load_model()
            self._step_count = 0
        self._reset_llm_alert()

        return {
            "type": "scenario_switched",
            "scenario": self.scenario,
            "scenario_label": SCENARIOS[self.scenario]["label"],
            "message": f"已切换到 {SCENARIOS[self.scenario]['label']}",
        }

    # ── WebSocket 服务 ──

    async def _handle_client(self, ws: Any) -> None:
        self._clients.add(ws)
        peer = ws.remote_address
        print(f"[WS] 客户端连接: {peer} (共 {len(self._clients)} 个)")

        # 发送初始确认
        await ws.send(json.dumps({
            "type": "connected",
            "scenario": self.scenario,
            "scenario_label": SCENARIOS[self.scenario]["label"],
            "model_loaded": self._model is not None,
            "model_id": self._model_id,
            "model_backend": self._model_backend,
            "intersection_order": list(INTERSECTION_ORDER),
        }, ensure_ascii=False))

        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                    msg_type = msg.get("type", "")
                    if msg_type == "switch_scenario":
                        result = await asyncio.get_event_loop().run_in_executor(
                            None, self._switch_scenario, msg.get("scenario", "real_peak"))
                        await ws.send(json.dumps(result, ensure_ascii=False))
                    elif msg_type == "ping":
                        await ws.send(json.dumps({"type": "pong", "timestamp": int(time.time() * 1000)}))
                    elif msg_type == "get_state":
                        snapshot = await asyncio.get_event_loop().run_in_executor(
                            None, self._simulation_step)
                        await ws.send(json.dumps(snapshot, ensure_ascii=False))
                    elif msg_type == "request_llm_alert":
                        # 手动请求一次云脑诊断：junction 缺省时由规则预筛自动选路口
                        junction = msg.get("junction") or None
                        asyncio.ensure_future(self._dispatch_llm_alert(junction))
                    elif msg_type == "llm_alert_status":
                        # 查询当前告警缓存/服务状态（面板重连后同步）
                        status: dict[str, Any] = {
                            "type": "llm_alert_status",
                            "enabled": self.llm_enabled,
                            "interval": self.llm_interval,
                            "busy": self._llm_busy,
                            "fail_reason": self._llm_fail_reason,
                            "last_alert": self._make_alert_payload(self._llm_alert)
                            if self._llm_alert is not None else None,
                        }
                        await ws.send(json.dumps(status, ensure_ascii=False))
                except json.JSONDecodeError:
                    await ws.send(json.dumps({"type": "error", "message": "无效的JSON"}))
        except Exception as e:
            print(f"[WS] 客户端断开: {peer} ({e})")
        finally:
            self._clients.discard(ws)
            print(f"[WS] 客户端断开: {peer} (剩余 {len(self._clients)} 个)")

    async def _broadcast_loop(self) -> None:
        """定时向所有客户端推送仿真状态"""
        while self._running:
            if self._clients:
                try:
                    snapshot = await asyncio.get_event_loop().run_in_executor(
                        None, self._simulation_step)
                    raw = json.dumps(snapshot, ensure_ascii=False)
                    # 广播给所有客户端
                    disconnected = set()
                    for ws in list(self._clients):
                        try:
                            await asyncio.wait_for(ws.send(raw), timeout=2.0)
                        except Exception:
                            disconnected.add(ws)
                    self._clients -= disconnected
                except Exception as e:
                    print(f"[Server] 仿真步进异常: {e}")
                    await asyncio.sleep(1.0)
            await asyncio.sleep(0.5)  # 推送间隔（秒）

    async def run(self) -> None:
        self._start_sumo()
        self._load_model()
        self._running = True

        # 启动 WebSocket 服务器
        import websockets
        server = await websockets.serve(self._handle_client, "0.0.0.0", self.port)

        print(f"[Server] WebSocket 服务器已启动 — ws://localhost:{self.port}")
        print(f"[Server] 场景: {SCENARIOS[self.scenario]['label']}")
        print(f"[Server] DQN 模型: {'已加载' if self._model else '未加载（固定配时）'}")
        print(f"[Server] 按 Ctrl+C 停止...")

        # 启动广播循环
        broadcast_task = asyncio.create_task(self._broadcast_loop())
        llm_task = asyncio.create_task(self._llm_alert_loop()) if self.llm_enabled else None

        try:
            await asyncio.Future()  # 永久等待
        except KeyboardInterrupt:
            pass
        finally:
            self._running = False
            broadcast_task.cancel()
            if llm_task is not None:
                llm_task.cancel()
            server.close()
            await server.wait_closed()
            self._close_sumo()
            print("[Server] 已停止")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="雄安交通可视化 WebSocket 服务器")
    parser.add_argument("--scenario", choices=list(SCENARIOS.keys()), default="real_peak",
                        help="初始场景 (默认: real_peak)")
    parser.add_argument("--port", type=int, default=8765, help="WebSocket 端口 (默认: 8765)")
    parser.add_argument("--no-model", action="store_true", help="不加载 DQN 模型（固定配时）")
    parser.add_argument(
        "--model-override", type=Path,
        help="仅用于本地联调的掩码 DQN 模型路径；不替代三场景正式模型交付",
    )
    parser.add_argument("--gui", action="store_true", help="使用 SUMO GUI（调试用）")
    parser.add_argument("--no-llm", action="store_true",
                        help="禁用 LLM 云脑告警（不启动 llama-server 的演示可跳过）")
    parser.add_argument("--llm-interval", type=float, default=LLM_ALERT_DEFAULT_INTERVAL,
                        help=f"自动云脑诊断间隔秒数 (默认: {LLM_ALERT_DEFAULT_INTERVAL:.0f}s)")
    args = parser.parse_args()

    server = VisualizationServer(
        scenario=args.scenario,
        port=args.port,
        use_model=not args.no_model,
        use_gui=args.gui,
        model_override=args.model_override,
        llm_enabled=not args.no_llm,
        llm_interval=args.llm_interval,
    )
    asyncio.run(server.run())


if __name__ == "__main__":
    main()
