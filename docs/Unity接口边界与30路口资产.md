# Unity接口边界与30路口资产

## 当前30路口契约

- 路口顺序：J01–J30；
- 单路口状态：22维；
- SUMO全局状态：660维；
- 单路口动作：0–3；
- 状态布局版本：`v1-30x22`。

地图由以下命令从 `sumo_files/xiongan_30.nod.xml` 生成：

```powershell
python scripts/convert_to_unity_map.py
```

生成器写入仓库唯一的Unity地图资产：

- `frontend/CitySimulation/Assets/Scripts/Maps/xiongan_30.json`。

该文件必须包含30个且仅包含J01–J30的信号灯。`tests/test_30_intersection_contract.py` 会对此做回归检查。

## 接口边界

### Unity工程

`frontend/CitySimulation` 由 `NetworkInterface.cs` 在 `127.0.0.1:5000` 启动TCP服务，使用长度前缀UTF-8 JSON的 `init/reset/step/close` 协议。客户端是 `frontend/pymarl` 中的 `UnityTCPEnv`。

`reset` 请求显式携带 `map_id: "xiongan_30"`；Unity 无参数回退也固定加载该地图。PyMARL 的 `n_agents`、`obs_size` 和 `state_size` 由 Unity 初始化响应动态回填，它们属于车辆/信号联合智能体协议，不等同于SUMO后端固定的30路口/660维DQN契约。

### C后端正式API

`server/api_server.py` 提供：

- REST：`http://localhost:8000/api/v1`；
- WebSocket：`ws://localhost:8000/api/v1/ws`。

该接口管理 SUMO/TraCI 的 30 路口会话。peak、evening 和 offpeak 泛化别名三个
正式 model ID 已注册为 `ready`；`/model/predict` 正常返回 30 个真实模型动作及
`shared-dqn-26x4-v1` 契约。只有调用历史归档、未注册或缺失权重的模型时才返回错误。

Unity 可通过 `Runtime/Visualization/FormalApiClosedLoopClient.cs` 直接接入该协议：

1. `POST /simulation/start` 创建唯一的 TraCI 会话；
2. 连接 `ws://localhost:8000/api/v1/ws` 并订阅 `state`、`reward`；
3. 对每个 `simulation.state` 调用 `/model/predict`（或容器模式的 `/edge/predict`）；
4. `POST /simulation/actions` 回传严格有序的 J01–J30 动作；
5. 接收动作后的下一条状态快照，并用同一 TraCI 时刻附带的 `visualization` 字段刷新车辆和 30 盏信号灯。

`visualization` 是对 660 维控制状态的只读渲染补充，包含车辆坐标、车型、朝向和四相位灯色；它不替代 `state_vector`，也不参与模型输入。推理响应额外提供 `action_masks_flat`（120 项）和 `actions_ordered`（30 项），供 Unity Dashboard 显示和协议校验，保留原有字典字段以兼容旧调用方。

### SUMO可视化接口

同一 Unity 工程中的 SUMO 可视化脚本仍可配合 `server/visualization_server.py` 的8765端口使用，作为旧演示通道和故障回退。它面向车辆和信号灯可视化；正式模式下应在 `VisualizationBootstrap` 勾选 `useFormalApi`，此时旧组件被禁用，避免两个后端会话并发占用 TraCI。

## 正式模式启用与验收

1. 在 `VisualizationBootstrap` 勾选 `useFormalApi`，填写 API Host 和 `formalApiPort=8000`；
2. 本机 FastAPI 模式保持 `useEdgeInference=false`，容器已启动 `xiongan-edge` 时再勾选它；
3. 运行 Unity 后核验日志依次出现 `已连接`、`订阅确认`，并检查 Dashboard 中场景名称、660 维状态摘要和 30×4 掩码；
4. 三个场景分别检查模型映射、30 个动作回传、30/30 信号灯相位变化和车辆快照刷新。

`8765`、`8000` 和 `5000` 仍是三条独立协议：8765 为旧可视化回退，5000 为 PyMARL TCP 训练接口，8000 为本节所述的 Unity 正式 REST/WebSocket 闭环。

## Unity实机验收（2026-08-13）

使用Unity 2022.3.62f2打开 `frontend/CitySimulation` 并进入Play Mode，实测结果：

- `xiongan_30`成功构建120条道路和30/30个信号路口；
- Game主相机自动适配完整地图范围；
- Unity TCP服务成功监听 `127.0.0.1:5000`；
- PyMARL smoke test完成 `init/reset(xiongan_30)/step×3/close`；
- Unity协议动态回填30个联合智能体、510维全局状态；
- 三步奖励依次为3.3492、3.0370、2.6028，均未终止且无shape mismatch。

这里的510维属于Unity车辆与信号联合智能体协议；C后端SUMO接口仍严格使用
J01–J30、30×22=660维状态，两套协议不得混作同一模型输入契约。
