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
from pathlib import Path
from typing import Any

import numpy as np

# ── 项目路径 ──
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

SUMO_FILES_DIR = PROJECT_ROOT / "sumo_files"
MODEL_DIR = PROJECT_ROOT / "models" / "dqn"

# 30 路口顺序/特征维度统一取自 configs.constants（与训练环境一致）
from configs.constants import INTERSECTION_ORDER, FEATURES_PER_INTERSECTION
# 状态提取复用训练环境的全局状态实现（docs/lane_mapping.json 几何映射，30路口×22维）
from env.global_state import get_global_state

# ── 场景配置 ──
SCENARIOS = {
    "real_peak": {
        "label": "真实早高峰(07:00-09:00)",
        "sumocfg": SUMO_FILES_DIR / "xiongan_real_peak.sumocfg",
        "model": "dqn_multi_shared_real_peak_perf_1000000steps.zip",
    },
    "real_offpeak": {
        "label": "真实平峰(14:30-16:30)",
        "sumocfg": SUMO_FILES_DIR / "xiongan_real_offpeak.sumocfg",
        # offpeak 专用模型两次训练均病态（见 models/dqn/archive/ failed_v1/v2），
        # 正式方案：evening 模型跨场景泛化（30路口全量 reward −1.6%，代表8路口 +5.4%）
        "model": "dqn_multi_shared_real_evening_perf_1000000steps.zip",
    },
    "real_evening": {
        "label": "真实晚高峰(17:30-19:30)",
        "sumocfg": SUMO_FILES_DIR / "xiongan_real_evening.sumocfg",
        "model": "dqn_multi_shared_real_evening_perf_1000000steps.zip",
    },
}

MIN_GREEN_SECONDS = 15
STEP_SECONDS = 5  # 每次推进的仿真秒数


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
                 use_model: bool = True, use_gui: bool = False) -> None:
        self.scenario = scenario
        self.port = port
        self.use_model = use_model
        self.use_gui = use_gui
        self._traci: Any = None
        self._model: Any = None
        self._sumo_proc: Any = None
        self._clients: set[Any] = set()
        self._current_actions: dict[str, int] = {}
        self._phase_changed_at: dict[str, float] = {}
        self._running = False
        self._step_count = 0

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

    def _load_model(self) -> None:
        if not self.use_model:
            print("[Server] 未加载 DQN 模型（--no-model 模式），使用固定配时")
            return

        model_file = SCENARIOS[self.scenario]["model"]
        model_path = MODEL_DIR / model_file
        if not model_path.exists():
            # 回退到最优模型
            model_path = MODEL_DIR / "dqn_multi_shared_real_peak_perf_1000000steps.zip"
            if not model_path.exists():
                print(f"[Server] 未找到 DQN 模型，回退到固定配时")
                return

        try:
            from stable_baselines3 import DQN
            self._model = DQN.load(str(model_path))
            print(f"[Server] DQN 模型已加载: {model_path.name}")
        except Exception as e:
            print(f"[Server] DQN 模型加载失败: {e}，回退到固定配时")
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
            return dict(self._current_actions)

        obs_dim = int(np.prod(self._model.observation_space.shape))
        masks = None
        if obs_dim > FEATURES_PER_INTERSECTION and self._traci is not None:
            from env.global_state import get_action_masks

            masks = get_action_masks(self._traci, INTERSECTION_ORDER)

        actions: dict[str, int] = {}
        for idx, tl_id in enumerate(INTERSECTION_ORDER):
            local_state = state[idx * FEATURES_PER_INTERSECTION:(idx + 1) * FEATURES_PER_INTERSECTION]
            if masks is not None:
                local_state = np.concatenate([local_state, masks[idx]])
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
            else:
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

    # ── 仿真步进 ──

    def _simulation_step(self) -> dict:
        """执行一步仿真：状态提取 → DQN推理 → 应用动作 → 推进SUMO → 返回快照"""
        # 1. 提取状态
        state = self._extract_state()

        # 2. DQN 推理
        actions = self._get_dqn_actions(state)

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
            "simulation_time": round(float(traci.simulation.getTime()), 1),
            "traffic_lights": self._extract_traffic_lights(),
            "vehicles": self._extract_vehicles(),
            "metrics": self._compute_metrics(),
            "actions": dict(self._current_actions),
        }
        return snapshot

    # ── 场景切换 ──

    def _switch_scenario(self, new_scenario: str) -> dict:
        if new_scenario not in SCENARIOS:
            return {"type": "error", "message": f"未知场景: {new_scenario}"}

        if new_scenario == self.scenario:
            return {"type": "scenario_switched", "scenario": self.scenario, "message": "已是当前场景"}

        print(f"[Server] 切换场景: {self.scenario} → {new_scenario}")
        self._close_sumo()
        self.scenario = new_scenario
        self._start_sumo()
        self._load_model()
        self._step_count = 0

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

        try:
            await asyncio.Future()  # 永久等待
        except KeyboardInterrupt:
            pass
        finally:
            self._running = False
            broadcast_task.cancel()
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
    parser.add_argument("--gui", action="store_true", help="使用 SUMO GUI（调试用）")
    args = parser.parse_args()

    server = VisualizationServer(
        scenario=args.scenario,
        port=args.port,
        use_model=not args.no_model,
        use_gui=args.gui,
    )
    asyncio.run(server.run())


if __name__ == "__main__":
    main()
