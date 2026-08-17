# 平峰 30 路口 DQN 全链路联调说明

## 已接入链路

```text
SUMO/TraCI → 8000 API（660 维状态、30×4 掩码）
          → 共享 DQN 推理 → 原子提交 J01–J30 动作
          → SUMO 信号相位执行 → Unity Dashboard/信号灯回显
```

Unity 的 8765 端口仍只负责车辆位置等可视化快照；DQN 控制闭环使用独立的
`http://127.0.0.1:8000/api/v1` REST 服务，二者不能混用。

## 本机启动

在仓库根目录执行：

```powershell
& .\.venv\Scripts\python.exe server\api_server.py
```

正式掩码模型训练命令（使用本机 GPU，产物仅留在本地）：

```powershell
& .\.venv\Scripts\python.exe training\train_dqn.py --timesteps 1000000 --scenario real_offpeak --perf --multi --seed 20260817 --save-dir models/dqn_masked_offpeak_1m --save-interval 50000 --run-name masked_1m_20260817
```

随后在 Unity 打开 `frontend/CitySimulation/Assets/Scenes/City.unity` 并点击 Play。
`DqnApiBootstrap` 会在检测到 `XionganRoadBootstrap` 后自动安装：

- `DqnControlClient`：启动 `real_offpeak` 会话、读取 660 维状态、请求 DQN、批量提交动作；
- `DqnDashboardUI`：显示场景、状态长度、最大排队路口、DQN 动作和 30×4 动作掩码；
- `DqnTrafficLightApplier`：根据 API 返回的相位更新 Unity 信号灯。

可在右上角 DQN 面板点击“启动闭环”或“停止闭环”。停止会关闭对应后端 TraCI 会话。
面板还提供“早高峰／平峰／晚高峰”按钮：切换时会关闭旧会话并重新请求对应
`real_peak`、`real_offpeak` 或 `real_evening` 的真实 660 维状态与动作掩码。

## 当前模型与掩码说明

模型 ID：`shared-dqn-real-offpeak-masked-1m-v1`。

本机正式权重为平峰共享掩码 DQN 100 万步检查点。API 为每个路口将 22 维状态与
实时 `4` 维需求门控动作掩码拼接为 26 维推理输入；动作掩码也会同步传给 Unity Dashboard 显示。
模型直接加载验证通过：输入为 26 维，输出为 4 个动作。

## 已通过的后端验收

- `POST /simulation/start`：返回 `J01`–`J30` 和 `state_dimension=660`；
- `GET /simulation/state`：返回 660 项状态和 30 个结构化路口；
- `GET /simulation/action-masks`：返回真实 `30 × 4` 掩码；
- `POST /model/predict`：平峰百万步模型返回 30 个合法动作；
- `POST /simulation/actions`：动作原子执行，`transition_id` 从 0 递增至 1，仿真时间从 0 推进到 5 秒。

2026-08-17 已对三个场景分别运行 `scripts/validate_dqn_control_loop.py`：均验证了
660 维状态、30×4 掩码、30 个动作、掩码合法性和一次原子状态迁移。Unity 画面验收需在
Editor 重新导入本目录的 DQN 脚本后进行。
