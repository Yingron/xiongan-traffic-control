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

该接口管理SUMO/TraCI的30路口会话。当前模型注册状态为 `waiting_for_A`，没有权重时 `/model/predict` 正确返回 `503 MODEL_NOT_LOADED`。

### SUMO可视化接口

同一 Unity 工程中的 SUMO 可视化脚本可配合 `server/visualization_server.py` 的8765端口使用。该协议面向SUMO车辆和信号灯可视化，不等同于8000端口REST/WebSocket会话协议。

## 当前未完成事项

- Unity工程尚未实现对C后端8000端口协议的直接适配；
- 正式DQN权重、SHA-256和归一化配置尚未交付；
- 因此不得宣称Unity—C后端—DQN闭环已经完成。

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
