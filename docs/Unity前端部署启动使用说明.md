# Unity 前端部署、启动和使用说明（旧 WebSocket 可视化副本）

> 适用范围：仓库仅保留 `frontend/CitySimulation` Unity工程。它既包含配合 `server/visualization_server.py:8765` 的SUMO可视化脚本，也包含监听 `127.0.0.1:5000`、供 `frontend/pymarl` 调用的长度前缀JSON/TCP协议；目前没有直接调用C后端REST `/api/v1/model/predict` 或WebSocket `/api/v1/ws`。三种接口不可混用。
>
> 当前仓库尚无正式DQN模型权重，注册表保持 `waiting_for_A`。下文提及的百万步模型文件是预期部署名，不代表文件当前存在。30路口地图请使用 `frontend/CitySimulation/Assets/Scripts/Maps/xiongan_30.json`，由 `python scripts/convert_to_unity_map.py` 生成。

本指南面向首次接触本项目的用户，从零开始一步步完成 Unity 前端的部署与启动，最终在 Unity 编辑器中看到交通仿真动画正常运行。

本指南使用的 DQN 模型文件为：`models/dqn/dqn_multi_shared_real_peak_perf_1000000steps.zip`（真实早高峰场景，100万训练步）。

---

## 目录

1. [环境准备总览](#1-环境准备总览)
2. [第一步：安装 Unity Hub 与 Unity 编辑器](#2-第一步安装-unity-hub-与-unity-编辑器)
3. [第二步：安装 SUMO 仿真平台](#3-第二步安装-sumo-仿真平台)
4. [第三步：安装 Python 与依赖](#4-第三步安装-python-与依赖)
5. [第四步：配置 DQN 模型](#5-第四步配置-dqn-模型)
6. [第五步：启动后端可视化服务](#6-第五步启动后端可视化服务)
7. [第六步：配置 Unity 场景并运行](#7-第六步配置-unity-场景并运行)
8. [第七步：验证动画运行正常](#8-第七步验证动画运行正常)
9. [使用说明：交互操作与场景切换](#9-使用说明交互操作与场景切换)
10. [常见问题排查](#10-常见问题排查)

---

## 1. 环境准备总览

### 1.1 所需软件清单

| 软件 | 版本要求 | 用途 |
|------|---------|------|
| Unity Hub | 最新版 | 管理 Unity 编辑器与项目 |
| Unity 编辑器 | **2022.3.62f2c1**（LTS） | 运行 Unity 前端项目 |
| SUMO | 1.27.1 或更高 | 交通流仿真引擎 |
| Python | 3.8 - 3.11 | 后端可视化服务 |
| Git | 任意版本 | 获取项目代码（如需要） |

### 1.2 硬件建议

| 项目 | 最低配置 | 推荐配置 |
|------|---------|---------|
| CPU | 4 核 | 8 核及以上 |
| 内存 | 8 GB | 16 GB 及以上 |
| 显卡 | 集成显卡 | 独立显卡（支持 DirectX 11） |
| 硬盘 | 10 GB 可用空间 | 20 GB 可用空间（含 SUMO、Unity） |
| 操作系统 | Windows 10 64 位 | Windows 11 64 位 |

### 1.3 项目目录结构概览

```
xiongan-traffic-control/
├── frontend/CitySimulation/        ← Unity 项目（本指南重点）
│   ├── Assets/
│   │   ├── Scenes/                 ← 场景文件
│   │   │   ├── xiong_30.unity      ← 推荐打开的场景（30 路口）
│   │   │   ├── City.unity
│   │   │   └── SampleScene.unity
│   │   └── Scripts/
│   │       ├── Maps/xiongan_30.json ← 30路口路网数据
│   │       ├── Bootstrap/           ← 路网构建
│   │       ├── Runtime/Visualization/ ← WebSocket 可视化
│   │       └── Camera/              ← 相机控制
├── server/visualization_server.py  ← 后端可视化服务
├── models/dqn/                     ← DQN 模型文件
│   └── dqn_multi_shared_real_peak_perf_1000000steps.zip
├── sumo_files/                     ← SUMO 路网与场景配置
└── requirements.txt                ← Python 依赖
```

> 本指南采用**纯命令行方式**启动，不依赖任何 .bat 脚本，避免中文路径/编码导致的脚本闪退问题。

---

## 2. 第一步：安装 Unity Hub 与 Unity 编辑器

### 2.1 下载 Unity Hub

1. 打开浏览器，访问 Unity 官方下载页面：
   ```
   https://unity.com/download
   ```
2. 点击"Download for Windows"下载 Unity Hub 安装包。
3. 双击运行 `UnityHubSetup.exe`，按提示完成安装。
4. 安装完成后打开 Unity Hub，使用 Unity ID 登录（如无账号，免费注册一个）。

### 2.2 安装 Unity 编辑器（2022.3.62f2c1）

> 本项目使用的 Unity 版本为 **2022.3.62f2c1**，必须安装此版本以保证兼容性。

1. 在 Unity Hub 左侧导航点击 **Installs（安装）**。
2. 点击右上角 **Install Editor（安装编辑器）** 按钮。
3. 在弹出的版本列表中，找到 **2022.3.x LTS** 系列。
4. 如果列表中没有 2022.3.62f2c1，点击下方的 **Archive（归档）** 链接，或直接访问：
   ```
   https://unity.com/releases/editor/archive
   ```
   找到 2022.3.62f2c1 版本并下载安装。
5. 安装时，**必须勾选以下模块**：
   - **Windows Build Support (IL2CPP)**（可选，用于打包）
   - **Documentation**（文档）
   - 平台模块保持默认即可

### 2.3 验证 Unity 安装

1. 安装完成后，在 Unity Hub → Installs 页面应能看到 2022.3.62f2c1。
2. 确认状态为"已安装"且无感叹号。

---

## 3. 第二步：安装 SUMO 仿真平台

### 3.1 下载 SUMO

1. 访问 SUMO 官方下载页面：
   ```
   https://sumo.dlr.de/docs/Downloads.php
   ```
2. 下载 Windows 版本安装包（建议 1.27.1 或更高），例如：
   ```
   sumo-win64-1.27.1.msi
   ```
3. 双击运行安装包，按提示完成安装。默认安装路径通常为：
   ```
   C:\Program Files (x86)\Eclipse\Sumo
   ```

### 3.2 配置 SUMO_HOME 环境变量

> **关键步骤**：后端服务必须读取 `SUMO_HOME` 环境变量才能找到 SUMO 可执行文件。

1. 右键"此电脑" → "属性" → "高级系统设置" → "环境变量"。
2. 在"系统变量"区域，点击"新建"：
   - 变量名：`SUMO_HOME`
   - 变量值：`C:\Program Files (x86)\Eclipse\Sumo`（根据实际安装路径调整）
3. 在"系统变量"中找到 `Path`，点击"编辑"，添加一行：
   - `%SUMO_HOME%\bin`
4. 点击"确定"保存所有对话框。

### 3.3 验证 SUMO 安装

1. 打开新的命令行窗口（按 `Win+R`，输入 `cmd`，回车）。
2. 执行以下命令：
   ```cmd
   echo %SUMO_HOME%
   sumo --version
   ```
3. 应看到 SUMO_HOME 路径输出，以及 SUMO 版本信息（如 `Eclipse SUMO sumo Version 1.27.1`）。

---

## 4. 第三步：安装 Python 与依赖

### 4.1 安装 Python

1. 访问 Python 官网下载页面：
   ```
   https://www.python.org/downloads/
   ```
2. 下载 Python 3.10 或 3.11（推荐 3.10.x）。
3. 安装时**务必勾选**"Add Python to PATH"。
4. 安装完成后，打开新的命令行窗口验证：
   ```cmd
   python --version
   ```
   应输出类似 `Python 3.10.11`。

### 4.2 安装 Python 依赖

1. 打开命令行，切换到项目根目录：
   ```cmd
   cd /d "\xiongan-traffic-control"
   ```
   > 请将路径替换为您的实际项目路径。

2. （推荐）创建虚拟环境：
   ```cmd
   python -m venv .venv
   .venv\Scripts\activate
   ```

3. 安装依赖：
   ```cmd
   pip install -r requirements.txt
   ```
   等待安装完成。主要依赖包括：
   - `fastapi` / `uvicorn` — Web 服务
   - `traci` — SUMO 交互接口
   - `stable-baselines3` — DQN 模型加载
   - `websockets` — WebSocket 服务器
   - `numpy` / `pandas` / `matplotlib` — 数据处理

4. 验证依赖：
   ```cmd
   python -c "import traci; import stable_baselines3; import websockets; print('依赖验证成功')"
   ```
   应输出 `依赖验证成功`。

---

## 5. 第四步：配置 DQN 模型

### 5.1 确认模型文件

确认以下模型文件存在：
```
models/dqn/dqn_multi_shared_real_peak_perf_1000000steps.zip
```

> 该模型为真实早高峰场景下训练 100 万步的参数共享 DQN，文件大小约 118 KB（11,784 参数）。

### 5.2 修改可视化服务配置

> **说明**：后端可视化服务 `visualization_server.py` 的场景配置已随 30 路口路网迁移，
> 现为三个真实数据场景（`real_peak` / `real_offpeak` / `real_evening`），
> 对应 `sumo_files/xiongan_real_{peak,offpeak,evening}.sumocfg`（需求来自赛题 xlsx）。

1. 使用文本编辑器（如 VS Code、Notepad++）打开：
   ```
   server/visualization_server.py
   ```

2. 找到 `SCENARIOS` 配置（文件头部）：
   ```python
   SCENARIOS = {
       "real_peak": {
           "label": "真实早高峰(07:00-09:00)",
           "sumocfg": SUMO_FILES_DIR / "xiongan_real_peak.sumocfg",
           "model": "dqn_multi_shared_real_peak_perf_1000000steps.zip",
       },
       "real_offpeak": {
           "label": "真实平峰(14:30-16:30)",
           "sumocfg": SUMO_FILES_DIR / "xiongan_real_offpeak.sumocfg",
           # 正式方案：offpeak 专用模型两次训练均病态（archive/ failed_v1/v2），
           # 采用 evening 模型跨场景泛化（代表8路口 +5.4% vs FT）
           "model": "dqn_multi_shared_real_evening_perf_1000000steps.zip",
       },
       "real_evening": {
           "label": "真实晚高峰(17:30-19:30)",
           "sumocfg": SUMO_FILES_DIR / "xiongan_real_evening.sumocfg",
           "model": "dqn_multi_shared_real_evening_perf_1000000steps.zip",
       },
   }
   ```

3. `model` 字段指向训练产出的模型文件（`training/train_dqn.py` 按
   `dqn_multi_shared_{scenario}_perf_{steps}steps.zip` 命名）。
   模型文件不存在时服务会自动回退到固定配时，不影响启动。

4. 保存文件。

---

## 6. 第五步：启动后端可视化服务

后端可视化服务负责：
- 启动 SUMO 仿真
- 加载 DQN 模型进行信号灯控制推理
- 通过 WebSocket 向 Unity 推送车辆位置、信号灯状态、指标数据

> **本指南采用纯命令行方式启动**，不使用任何 .bat 脚本，避免中文路径或编码问题导致闪退。

### 6.1 启动前环境自检（强烈推荐）

打开命令行（按 `Win+R`，输入 `cmd`，回车），按顺序执行以下命令逐一确认环境就绪。任一步骤失败时，请先解决再继续。

**1. 切换到项目根目录：**
```cmd
cd /d "C:\Users\挑战杯\xiongan-traffic-control"
```
> 请将路径替换为您实际的项目位置。`/d` 参数用于跨盘符切换。

**2. 确认 SUMO_HOME 环境变量：**
```cmd
echo %SUMO_HOME%
```
- 应输出 SUMO 安装路径，例如：`C:\Program Files (x86)\Eclipse\Sumo`
- 若输出 `%SUMO_HOME%` 或为空，说明环境变量未设置，请回到第 3.2 节完成配置后**重新打开**一个新的 cmd 窗口再试。

**3. 确认 SUMO 可执行文件可用：**
```cmd
"%SUMO_HOME%\bin\sumo.exe" --version
```
- 应输出 `Eclipse SUMO sumo Version 1.27.1` 之类的版本信息。

**4. 确认 Python 可用：**
```cmd
python --version
```
- 应输出 `Python 3.10.x` 或更高版本。

**5. 确认关键 Python 依赖已安装：**
```cmd
python -c "import traci,stable_baselines3,websockets,numpy; print('OK')"
```
- 应输出 `OK`。
- 若报 `ModuleNotFoundError`，请回到第 4.2 节执行 `pip install -r requirements.txt`。

**6. 确认关键项目文件存在：**
```cmd
if exist "server\visualization_server.py" (echo [OK] server) else (echo [MISSING] server)
if exist "sumo_files\xiongan_real_peak.sumocfg" (echo [OK] scenario) else (echo [MISSING] scenario)
if exist "sumo_files\xiongan_30.net.xml" (echo [OK] net) else (echo [MISSING] net)
```
- 三行都应输出 `[OK]`。

### 6.2 启动可视化服务

在**项目根目录**下执行以下命令（推荐使用真实早高峰场景 real_peak，模型缺失时自动回退固定配时）：

```cmd
python server/visualization_server.py --scenario real_peak --port 8765
```

启动后，命令行会依次输出以下日志。看到 **"WebSocket 服务器已启动"** 即表示服务就绪：

```
[Server] 启动 SUMO (端口 xxxx)...
[Server] TraCI 连接成功 (端口 xxxx) — 仿真时间: 0.0s
[Server] SUMO 已启动 — 场景: 真实早高峰(07:00-09:00) — 车辆数: xx
[Server] DQN 模型已加载: dqn_multi_shared_real_peak_perf_1000000steps.zip
[Server] WebSocket 服务器已启动 — ws://localhost:8765
[Server] 场景: 真实早高峰(07:00-09:00)
[Server] DQN 模型: 已加载
[Server] 按 Ctrl+C 停止...
```

### 6.3 启动参数说明

| 参数 | 说明 | 示例 |
|------|------|------|
| `--scenario` | 场景选择：`real_peak` / `real_offpeak` / `real_evening` | `--scenario real_peak` |
| `--port` | WebSocket 端口（默认 8765） | `--port 8765` |
| `--no-model` | 不加载 DQN 模型，使用固定配时 | `--no-model` |
| `--gui` | 启用 SUMO GUI 界面（调试用） | `--gui` |

**常用启动组合：**

| 场景 | 命令 |
|------|------|
| 真实早高峰（推荐） | `python server/visualization_server.py --scenario real_peak` |
| 真实平峰 | `python server/visualization_server.py --scenario real_offpeak` |
| 真实晚高峰 | `python server/visualization_server.py --scenario real_evening` |
| 无模型（固定配时） | `python server/visualization_server.py --scenario real_peak --no-model` |
| 带 SUMO GUI 调试 | `python server/visualization_server.py --scenario real_peak --gui` |

### 6.4 验证后端服务运行

- **保持命令行窗口不关闭**，后端服务需持续运行以向 Unity 推送数据。
- 服务运行期间会持续输出仿真步进日志和 WebSocket 客户端连接日志。
- 当 Unity 连接成功时，命令行会输出：
  ```
  [WS] 客户端连接: ('127.0.0.1', xxxxx) (共 1 个)
  ```

### 6.5 停止后端服务

在命令行窗口中按 `Ctrl+C` 即可优雅停止服务。SUMO 进程会自动关闭。

---

## 7. 第六步：配置 Unity 场景并运行

### 7.1 将项目添加到 Unity Hub

1. 打开 Unity Hub。
2. 左侧导航点击 **Projects（项目）**。
3. 点击右上角 **Add（添加）** → **Add project from disk**。
4. 选择项目中的 Unity 工程目录：
   ```
   frontend/CitySimulation
   ```
   > 完整路径示例：`C:\Users\挑战杯\xiongan-traffic-control\frontend\CitySimulation`
5. 确保项目旁显示的 Unity 版本为 **2022.3.62f2c1**。

### 7.2 打开项目

1. 在 Unity Hub 的 Projects 列表中，点击 `CitySimulation` 项目。
2. Unity 编辑器开始加载项目（首次加载可能需要数分钟，会编译脚本、导入资源）。
3. 加载完成后，Unity 编辑器主界面出现。

### 7.3 步骤 1：打开 Unity 项目 frontend/CitySimulation

> 如已按 7.1 / 7.2 完成项目添加并打开，可跳过本节。

- 在 Unity Hub 中点击 `CitySimulation` 项目，等待 Unity 编辑器加载完成。
- 加载完成后，可在编辑器顶部标题栏看到项目名称 `CitySimulation - Unity 2022.3.62f2c1`。

### 7.4 步骤 2：打开场景 Scenes/xiong_30.unity（或 City.unity）

1. 在 Unity 编辑器顶部的 **Project 窗口**中，导航到：
   ```
   Assets/Scenes/
   ```
2. 双击以下任一场景文件打开：
   - **`xiong_30.unity`**（推荐，30 路口专用场景）
   - 或 **`City.unity`**（主城市场景，`XionganRoadBootstrap` 的 Map Id 已配置为 `xiongan_30`）

   > 也可通过菜单 **File → Open Scene** 打开。
3. 打开后，**Hierarchy 窗口**（左上）会显示当前场景的 GameObject 层级结构。

### 7.5 步骤 3：确保场景中已有路网构建器和仿真驱动器

在 Hierarchy 窗口中，确认以下 GameObject 已存在：

| GameObject 名称 | 挂载的关键组件 | 作用 |
|----------------|---------------|------|
| `XionganRoadBootstrap` | `XionganRoadBootstrap` | 自动构建 30 路口路网 |
| `SimulationRuntimeDriver` | `SimulationRuntimeDriver` | 运行时车辆生成与仿真驱动 |

**检查方法：**
- 在 Hierarchy 中点击 `XionganRoadBootstrap`，右侧 Inspector 应显示 `XionganRoadBootstrap (Script)` 组件。
- 同样检查 `SimulationRuntimeDriver`。

**如果缺少这些 GameObject，请手动创建：**

1. Hierarchy 窗口右键 → **Create Empty**，分别命名为 `XionganRoadBootstrap` 和 `SimulationRuntimeDriver`。
2. 选中 `XionganRoadBootstrap`，在 Inspector 中点击 **Add Component**，搜索 `XionganRoadBootstrap` 脚本并添加。
   - 确认 `Map Id` 字段为 `xiongan_30`
   - 确认 `Build On Awake` 勾选
3. 选中 `SimulationRuntimeDriver`，在 Inspector 中点击 **Add Component**，搜索 `SimulationRuntimeDriver` 脚本并添加。
   - 确认 `Spawn Vehicles On Start` 勾选（如需本地车辆生成）
   - `Target Vehicle Count` 建议设为 25

### 7.6 步骤 4：生成路网和信号灯（通过菜单 雄安路网 / 构建 xiongan_30 30路口）

> 路网和信号灯是 Unity 中可视化交通的基础。`XionganRoadBootstrap` 在场景启动（Play）时会自动构建，但也可在编辑模式下手动构建以便预览。

**方法 A：通过 Unity 顶部菜单构建（编辑模式预览）**

1. 在 Unity 编辑器顶部菜单栏，点击 **雄安路网** 菜单（如果看不到，可能是因为脚本未编译完成，请等待编译完成或检查 Console 是否有编译错误）。
2. 选择 **构建 xiongan_30 30路口**（菜单项名称类似 `雄安路网 / 构建 xiongan_30 30路口`）。
3. 等待构建完成，Console 窗口会输出：
   ```
   [XionganRoadBootstrap] [OK][standalone] map=xiongan_30 roads=98 tls=30/30
   ```
4. 切换到 **Scene 视图**（点击 Scene 标签页），应能看到 30 路口的网格路网和信号灯。

**方法 B：通过 Inspector 上下文菜单构建**

1. 在 Hierarchy 中选中 `XionganRoadBootstrap` 对象。
2. 在 Inspector 中 `XionganRoadBootstrap (Script)` 组件右上角，点击三个小点（齿轮）图标。
3. 在弹出菜单中选择：
   - **Build Xiongan 30 (standalone / edit mode)** — 编辑模式下构建（推荐用于预览）
   - 或 **Build Xiongan 30 (use GameServices)** — 运行模式下构建
4. Console 窗口会输出构建成功日志。

**方法 C：运行时自动构建（Play 模式）**

- 如果 `Build On Awake` 已勾选，点击 Play 运行时会自动构建路网。
- 但建议先用方法 A 或 B 在编辑模式下构建一次，确认路网结构正确。

**验证路网生成成功：**

- Scene 视图中应出现 30 个十字路口和连接道路。
- Hierarchy 中可能新增 `Roads`、`TrafficLights` 等对象组。
- Console 无红色错误日志。

### 7.7 步骤 5：确认 VisualizationSystem（已预置）

> `VisualizationSystem` 已预置在 `xiong_30.unity` 与 `City.unity` 中，**无需手动创建**。
> 它是连接 Unity 与后端 Python 服务的桥梁，Awake 时自动配置 WebSocket 客户端、可视化桥接器和演示 HUD。

**场景中应已存在以下组件：**

- `VisualizationBootstrap` — 启动器（Server Host = `127.0.0.1`，Server Port = `8765`，Auto Connect ✅，Disable Local Simulation ✅）
- `SumoWebSocketClient` — WebSocket 客户端（8765 端口）
- `SumoVisualizationBridge` — 可视化桥接器（SUMO 数据驱动车辆渲染与信号灯相位）
- `TrafficVisualizationUI` — 演示 HUD（自动创建 Canvas）

**演示 HUD 布局：**

| 位置 | 内容 |
|------|------|
| 顶部中央 | 平台标题「雄安新区车路云一体化协同管控平台」 |
| 左上 | 连接状态 ● 已连接 / ○ 未连接 + 当前场景名 |
| 右上 | 场景切换按钮：**早高峰**（real_peak）/ **晚高峰**（real_evening）/ **平峰**（real_offpeak） |
| 左下 | 实时指标面板（仿真时间、车辆总数、平均排队、平均等待、平均车速、已到达、已发车） |
| 右下 | 渲染车辆数 |

> 中文由 `Assets/Resources/Fonts/simhei.ttf`（黑体）渲染，保证中文正常显示。

**编辑器侧边栏（已默认禁用）：**

- 场景中的 `UIDocument`（英文编辑器侧边栏，含 edit map / running / training 等开发工具按钮）默认**禁用**，避免遮挡演示画面。
- 开发需要时可选中 Hierarchy 中的 `UIDocument` 对象，在 Inspector 顶部勾选重新启用。
- 若在新建场景中没有 `VisualizationSystem`，可通过菜单 **雄安路网 / 创建可视化系统** 一键创建。

**5.3 确认 VisualizationBootstrap 参数：**

选中 `VisualizationSystem` 对象，确认 `VisualizationBootstrap (Script)` 参数：

| 参数 | 推荐值 | 说明 |
|------|--------|------|
| **Server Host** | `127.0.0.1` | 后端 Python 服务地址（本机） |
| **Server Port** | `8765` | WebSocket 端口，需与后端启动参数一致 |
| **Auto Connect** | ✅ 勾选 | 启动时自动连接后端服务 |
| **Disable Local Simulation** | ✅ 勾选 | 禁用本地车辆仿真，使用 SUMO 数据驱动 |

> 其余三个组件（`SumoWebSocketClient` / `SumoVisualizationBridge` / `TrafficVisualizationUI`）由 `VisualizationBootstrap` 在 Awake 时自动配置，一般无需手动调整。

**5.4 保存场景：**

按 `Ctrl+S` 保存场景，使配置持久化。

### 7.8 场景配置完成检查清单

运行前，请逐项确认以下配置已完成：

- [ ] 1. 已打开 `xiong_30.unity` 或 `City.unity` 场景（均内置 30 路口配置）
- [ ] 2. Hierarchy 中存在 `XionganRoadBootstrap`，且 `Map Id` = `xiongan_30`
- [ ] 3. Hierarchy 中存在 `SimulationRuntimeDriver`
- [ ] 4. 已通过菜单 **雄安路网 / 构建 xiongan_30 30路口** 生成路网和信号灯
- [ ] 5. Hierarchy 中存在 `VisualizationSystem`（已预置 4 组件：VisualizationBootstrap / SumoWebSocketClient / SumoVisualizationBridge / TrafficVisualizationUI）
- [ ] 6. `VisualizationBootstrap` 的 Server Host = `127.0.0.1`，Server Port = `8765`
- [ ] 7. `UIDocument` 编辑器侧边栏处于禁用状态（默认已禁用，可勾选恢复）
- [ ] 8. 已保存场景（Ctrl+S）

### 7.9 点击 Play 运行

1. 确认后端可视化服务（第 6 步）仍在运行（命令行窗口显示 `WebSocket 服务器已启动`）。
2. 在 Unity 编辑器顶部，点击 **▶ Play 按钮**（或按快捷键 `Ctrl+P`）。
3. 等待场景加载，Console 窗口会依次输出：

**路网构建日志：**
```
[XionganRoadBootstrap] [OK] map=xiongan_30 roads=98 tls=30/30
```

**WebSocket 连接成功日志：**
```
[SumoWS] 已连接 → ws://127.0.0.1:8765
[SumoWS] 服务器确认 — 场景: 真实早高峰(07:00-09:00)
```

**可视化桥接启动日志：**
```
[VisualizationBootstrap] 已禁用本地车辆仿真，使用 SUMO 数据驱动
```

4. 切换到 Game 视图（点击 Game 标签页），即可看到交通仿真动画。

---

## 8. 第七步：验证动画运行正常

### 8.1 视觉检查清单

运行后，Game 视图应出现以下画面，逐项确认：

| 检查项 | 预期表现 | 异常表现 |
|--------|---------|---------|
| **路网** | 30 路口网格路网出现，道路清晰可见 | 路网空白 / 部分缺失 |
| **车辆** | 道路上有多辆车辆移动 | 无车辆 / 车辆静止不动 |
| **信号灯** | 路口信号灯有红/绿/黄颜色变化 | 信号灯全红 / 无颜色 |
| **车辆行为** | 车辆遇红灯减速停车，绿灯通行 | 车辆穿墙 / 穿越红灯 |

### 8.2 Console 日志检查

在 Console 窗口（菜单 Window → General → Console）中，确认以下日志出现：

**路网构建成功日志：**
```
[XionganRoadBootstrap] [OK] map=xiongan_30 roads=98 tls=30/30
```

**WebSocket 连接成功日志：**
```
[SumoWS] 已连接 → ws://127.0.0.1:8765
[SumoWS] 服务器确认 — 场景: 真实早高峰(07:00-09:00)
```

**车辆生成日志（如启用本地仿真）：**
```
[SimulationRuntimeDriver] 已生成 25/25 辆车辆
```

**后端服务持续输出（在命令行窗口）：**
```
[Server] 仿真步进中... step=xxx, 车辆数=xx
```

### 8.3 后端服务状态确认

切换到后端服务命令行窗口，应看到：
- 持续的仿真步进日志
- WebSocket 客户端连接确认：
  ```
  [WS] 客户端连接: ('127.0.0.1', xxxxx) (共 1 个)
  ```

### 8.4 可视化数据面板（如有）

如果场景中包含 `TrafficVisualizationUI` 组件，Game 视图右上角会显示数据面板，包含：
- 当前场景：真实早高峰
- 仿真时间
- 车辆总数
- 平均排队长度
- 平均等待时间
- 平均车速
- DQN 模型状态：已加载

### 8.5 动画正常运行的综合判断

当以下条件全部满足时，即可判定动画运行正常：
1. ✅ Unity Game 视图中显示完整的 30 路口路网
2. ✅ 路网上有车辆在行驶，且数量动态变化
3. ✅ 路口信号灯按相位切换颜色
4. ✅ Console 无红色错误日志（黄色警告可忽略）
5. ✅ 后端服务命令行持续输出仿真步进日志
6. ✅ 车辆遇红灯停车、绿灯通行，行为符合交通规则

---

## 9. 使用说明：交互操作与场景切换

### 9.1 相机控制

运行时，可通过键盘控制相机视角：

| 按键 | 功能 |
|------|------|
| `W` | 向前移动 |
| `S` | 向后移动 |
| `A` | 向左移动 |
| `D` | 向右移动 |
| `Q` | 向下移动 |
| `E` | 向上移动 |
| `鼠标滚轮` | 垂直升降 |
| `Shift`（按住） | 移动速度加倍 |

> 移动速度默认为 200，可在 `CameraMoveController` 组件的 Inspector 中调整 `Move Speed`。

### 9.2 场景切换

如果场景中包含可视化 UI，可通过按钮切换交通场景：

| 场景 | 说明 | 流量特征 |
|------|------|---------|
| 真实早高峰（real_peak） | 07:00-09:00 | 需求来自赛题 xlsx |
| 真实平峰（real_offpeak） | 14:30-16:30 | 需求来自赛题 xlsx |
| 真实晚高峰（real_evening） | 17:30-19:30 | 需求来自赛题 xlsx |

> 切换场景时，后端服务会自动重启 SUMO 并加载对应场景的 DQN 模型。
> 切换过程约需 3-5 秒，Console 会输出 `[SumoWS] 场景已切换: xxx`。

### 9.3 后端模式切换（BridgeStatusPanel）

如果场景中包含 `BridgeStatusPanel` 组件，右上角会显示状态面板：

- **TEST MOCK**（青色）：使用 Unity 本地模拟决策
- **CONNECTED**（绿色）：已连接到后端 Bridge 服务
- **CONNECTING...**（黄色）：正在连接中

点击"Switch to Bridge TCP"按钮可在两种模式间切换。

### 9.4 停止运行

1. 在 Unity 编辑器点击 **▶ Play 按钮**（或按 `Ctrl+P`）停止场景运行。
2. 在后端服务命令行窗口按 `Ctrl+C` 停止后端服务。
3. 关闭命令行窗口。

---

## 10. 常见问题排查

### 10.1 Unity 报错：项目版本不匹配

**现象**：打开项目时提示 Unity 版本不一致。

**解决**：
- 必须使用 2022.3.62f2c1 版本。
- 如已安装其他 2022.3.x 版本，可通过 Unity Hub → Installs → 选择 2022.3.62f2c1 设为默认。

### 10.2 后端启动报错：SUMO_HOME 未设置

**现象**：运行 `visualization_server.py` 时报错：
```
[ERROR] SUMO_HOME is not set.
```

**解决**：
- 按 3.2 节设置 `SUMO_HOME` 环境变量。
- 设置后**重新打开**命令行窗口使环境变量生效。

### 10.3 后端启动报错：ModuleNotFoundError

**现象**：提示 `No module named 'traci'` 或 `No module named 'stable_baselines3'`。

**解决**：
- 确认已激活虚拟环境（如使用）。
- 重新安装依赖：`pip install -r requirements.txt`。
- 验证：`python -c "import traci; import stable_baselines3; print('OK')"`

### 10.4 后端启动报错：模型文件未找到

**现象**：
```
[Server] 未找到 DQN 模型，回退到固定配时
```

**解决**：
- 确认 `models/dqn/dqn_multi_shared_real_peak_perf_1000000steps.zip` 文件存在。
- 确认已按 5.2 节修改 `visualization_server.py` 中的模型文件名。

### 10.5 Unity Console 报错：WebSocket 连接失败

**现象**：
```
[SumoWS] 连接失败: Unable to connect to the remote server
```

**解决**：
- 确认后端服务已启动且正在运行。
- 确认端口未被占用（默认 8765）。
- 检查防火墙是否阻止了本地连接。
- 在 `VisualizationBootstrap` 或 `SumoWebSocketClient` 组件中确认 Server Host = `127.0.0.1`，Server Port = `8765`。

### 10.6 Unity 中看不到车辆

**现象**：路网显示正常，但道路上无车辆。

**解决**：
- 检查 Console 是否有 `[SumoWS] 已连接` 日志。
- 检查 `SimulationRuntimeDriver` 的 `Spawn Vehicles On Start` 是否勾选。
- 如 `VisualizationBootstrap` 的 `Disable Local Simulation` 为 true，则车辆由 SUMO 数据驱动，确认后端 SUMO 已有车辆（查看后端日志中的"车辆数"）。
- 在 `SimulationRuntimeDriver` 组件中将 `Target Vehicle Count` 调大（如 25）。

### 10.7 Unity 中信号灯不变色

**现象**：所有信号灯颜色固定不变。

**解决**：
- 确认后端 DQN 模型已加载（后端日志显示 `DQN 模型已加载`）。
- 检查 `TrafficService` 是否已初始化。
- 查看后端日志是否有 `仿真步进异常` 错误。

### 10.8 SUMO 端口被占用

**现象**：后端启动报错提示端口被占用。

**解决**：
- 关闭可能残留的 SUMO 进程：
  ```cmd
  taskkill /f /im sumo.exe
  taskkill /f /im sumo-gui.exe
  ```
- 重新启动后端服务。
- 后端服务会自动在 8814-9000 范围内寻找可用端口，通常无需手动指定。

### 10.9 性能问题：帧率低

**现象**：Unity 运行时帧率低，画面卡顿。

**解决**：
- 在 Unity 编辑器顶部将 Game 视图分辨率调低。
- 关闭 Editor Stats（右上角 Stats 按钮）。
- 在 `SimulationRuntimeDriver` 中降低 `Target Vehicle Count`。
- 在 `SimulationConfig` 中降低 `RuntimeStepRepeat`。
- 确认未启用 SUMO GUI（`--gui` 参数）。

### 10.10 后端服务异常退出

**现象**：后端服务运行一段时间后自动退出。

**解决**：
- 查看命令行窗口的错误信息。
- 常见原因：SUMO 仿真结束（场景时间到）、内存不足、TraCI 连接断开。
- 重新启动后端服务即可。
- 如频繁崩溃，尝试使用 `--no-model` 参数排除模型问题。

### 10.11 命令行窗口闪退 / 中文路径乱码

**现象**：在 cmd 中执行 `python server/visualization_server.py` 后窗口立即关闭，或路径中的中文显示为乱码（如 `荣光` → `鑽ｅ厜`）。

**原因**：Windows cmd 默认使用 GBK（CP936）编码，而某些环境下 Python 输出 / 文件路径采用 UTF-8 编码，两者不匹配时会导致路径解析失败或脚本异常退出。

**解决**：
1. **使用纯 cmd 而非 PowerShell**：按 `Win+R` → 输入 `cmd` → 回车，使用传统命令提示符。
2. **手动切换代码页**：在执行 python 命令前先执行：
   ```cmd
   chcp 936
   ```
   将当前 cmd 的代码页设为 GBK，使其与 Windows 中文系统默认编码一致。
3. **使用引号包裹中文路径**：
   ```cmd
   cd /d "C:\Users\挑战杯\xiongan-traffic-control"
   ```
   双引号可避免路径中的空格和特殊字符被错误解析。
4. **避免在路径中使用特殊符号**：如项目路径含括号（如 `C:\Program Files (x86)\...`），务必用双引号包裹整个路径。
5. **检查 Python 文件编码**：`visualization_server.py` 应保存为 UTF-8（无 BOM）。如怀疑编码问题，可用 VS Code 打开，右下角点击编码 → "Save with Encoding" → UTF-8。
6. **如仍闪退**：在 cmd 中先执行 `python -u server/visualization_server.py --scenario real_peak`，`-u` 参数禁用输出缓冲，可立即看到错误堆栈。

### 10.12 Python 版本兼容性问题

**现象**：启动时报 `AttributeError`、`ImportError` 或 `SyntaxError`。

**解决**：
- 本项目推荐 Python 3.10 - 3.11。
- Python 3.12+ 部分依赖包可能不兼容（如 `gymnasium` 旧版本）。
- 如使用 Python 3.12+，确保 `stable-baselines3 >= 2.4.0`。
- 验证命令：
  ```cmd
  python -c "import sys; print(sys.version)"
  python -c "import stable_baselines3; print(stable_baselines3.__version__)"
  ```

---

## 附录：快速启动检查清单

部署完成后，可按以下清单快速启动：

**后端环境：**
- [ ] 1. SUMO_HOME 环境变量已设置
- [ ] 2. Python 依赖已安装（`pip install -r requirements.txt`）
- [ ] 3. `visualization_server.py` 中真实场景模型已配置为 `dqn_multi_shared_real_peak_perf_1000000steps.zip`
- [ ] 4. 后端服务已启动（`python server/visualization_server.py --scenario real_peak`）
- [ ] 5. 后端日志显示"DQN 模型已加载"
- [ ] 6. 后端日志显示"WebSocket 服务器已启动 — ws://localhost:8765"

**Unity 项目：**
- [ ] 7. Unity Hub 中已添加 CitySimulation 项目
- [ ] 8. Unity 编辑器使用 2022.3.62f2c1 版本
- [ ] 9. 已打开 `xiong_30.unity` 场景

**Unity 场景配置：**
- [ ] 10. Hierarchy 中存在 `XionganRoadBootstrap`，且 `Map Id` = `xiongan_30`
- [ ] 11. Hierarchy 中存在 `SimulationRuntimeDriver`
- [ ] 12. 已通过菜单 **雄安路网 / 构建 xiongan_30 30路口** 生成路网和信号灯
- [ ] 13. Hierarchy 中存在 `VisualizationSystem`（已预置 4 组件）
- [ ] 14. `VisualizationBootstrap` 的 Server Host = `127.0.0.1`，Server Port = `8765`
- [ ] 15. `UIDocument` 编辑器侧边栏处于禁用状态（默认已禁用）
- [ ] 16. 已保存场景（Ctrl+S）

**运行验证：**
- [ ] 17. 点击 Play 运行后，Console 显示 WebSocket 连接成功
- [ ] 18. Game 视图中显示路网、车辆、信号灯
- [ ] 19. 车辆正常行驶，信号灯按相位切换

全部勾选后，Unity 前端即部署成功，可正常观看交通仿真动画。
