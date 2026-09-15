# 雄安新区“城市大脑”车路云一体化协同管控与仿真平台

本项目面向赛题 `XH-202613`，提供一套可在普通 CPU 电脑上运行的 30 路口协同管控原型：SUMO 负责真实交通流仿真，边缘侧 ONNX DQN 根据路口状态和动作掩码生成信号控制建议，安全约束层执行最小绿灯约束，Unity 或 WebSocket 客户端展示车辆、信号灯、控制动作和实时指标。

> 复现建议：优先完成下方“典型场景完整复现”。该流程直接使用仓库已交付的正式 ONNX 模型，不需要 GPU、不需要重新训练，也不依赖未交付的大模型文件。完整执行后会得到一份机器可读的闭环验收报告。

## 1. 与赛题要求的对应关系

- 路网规模：`J01` 至 `J30` 共 30 个信号路口，超过赛题“至少 20 个路口”的要求。
- 典型场景：默认复现真实早高峰 `real_peak`，仿真时段为 07:00-09:00；另提供平峰和晚高峰场景。
- 协同闭环：真实 SUMO 状态 → 30 路口局部状态 → 需求门控动作掩码 → ONNX DQN 推理 → 最小绿灯安全约束 → 信号相位写回 SUMO → WebSocket/Unity 实时展示。
- 基线机制：`baselines/fixed_time.py` 从 `data/timing_plans.json` 安装真实定周期方案；可视化服务另提供 `--no-model` 无模型演示对照。
- 工程部署：同时提供本机运行、Unity 可视化和 Docker 云边分离部署。
- 可审计性：正式模型通过模型注册表和 SHA-256 校验；闭环报告会检查路口数、动作数、掩码、模型 ID 和持续状态帧。

## 2. 系统组成

核心目录如下：

```text
xiongan-traffic-control/
├─ sumo_files/                    # 30 路口路网及早/平/晚高峰交通需求
├─ models/edge/                   # 已交付 ONNX/TorchScript 轻量化模型
├─ configs/edge_model_registry.json
│                                  # 正式边缘模型 ID、状态及 SHA-256
├─ env/                           # 660 维全局状态、动作掩码和奖励函数
├─ server/visualization_server.py # 推荐演示入口：SUMO+ONNX+WebSocket 闭环
├─ server/api_server.py           # 标准 REST API
├─ edge_deploy/                   # ONNX 推理服务及 Docker 部署
├─ scripts/                       # 预检、场景生成和闭环验收脚本
├─ frontend/CitySimulation/       # Unity 2022.3 可视化工程
├─ docs/                          # 状态、车道、信号及接口机器可读契约
├─ evaluation/                    # 多策略/多场景评估程序
└─ requirements.txt               # 完整 Python 依赖
```

三个已配置场景：

- `real_peak`：真实早高峰 07:00-09:00，正式模型 `edge-real-peak-onnx-v1`。
- `real_offpeak`：真实平峰 14:30-16:30，正式模型 `edge-real-offpeak-via-evening-onnx-v1`。
- `real_evening`：真实晚高峰 17:30-19:30，正式模型 `edge-real-evening-onnx-v1`。

## 3. 环境要求

### 3.1 推荐配置

- 操作系统：Windows 10/11 x64。Docker 部署也可在 Linux 上运行。
- CPU：4 核及以上。
- 内存：8 GB 及以上；仅无界面闭环通常占用更少。
- 磁盘：至少 5 GB 可用空间，用于项目、Python 虚拟环境和 Unity 缓存。
- GPU：不要求。正式 ONNX 模型默认使用 CPU 推理。

### 3.2 软件版本

- Python：推荐 3.10-3.12。本 README 的命令已在 Python 3.12.14 上验证。
- Eclipse SUMO：推荐 1.27.1。本 README 的命令已在 SUMO 1.27.1 上验证。
- Unity：仅图形化展示需要，版本为 `2022.3.62f2c1`，以 `frontend/CitySimulation/ProjectSettings/ProjectVersion.txt` 为准。
- Docker Desktop：仅容器化部署需要，需支持 `docker compose`。

不建议用 Python 3.14 创建环境；本项目固定了 Stable-Baselines3、Gymnasium 和 NumPy 的兼容范围，3.10-3.12 更稳妥。

## 4. Windows 本机部署

以下命令均在项目根目录的 PowerShell 中执行。若项目位于其他位置，只需修改第一行路径。

### 4.1 安装 Python 依赖

```powershell
Set-Location 'C:\path\to\xiongan-traffic-control'

py -3.12 -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1

python -m pip install --disable-pip-version-check -r requirements.txt
python --version
```

如果 `py -3.12` 不存在，请先安装 Python 3.10、3.11 或 3.12，并用对应解释器创建 `.venv`。不要把依赖安装到系统 Python 中。

### 4.2 安装并配置 SUMO

安装 Eclipse SUMO 后，确认 PowerShell 能找到 `sumo.exe`：

```powershell
$sumoExe = (Get-Command sumo.exe -ErrorAction Stop).Source
$env:SUMO_HOME = Split-Path -Parent (Split-Path -Parent $sumoExe)
$env:Path = "$env:SUMO_HOME\bin;$env:Path"
$env:PYTHONUTF8 = '1'

sumo --version
Test-Path "$env:SUMO_HOME\bin\sumo.exe"
```

最后一条命令必须输出 `True`。若 SUMO 未加入 `PATH`，可直接指定安装目录，例如：

```powershell
$env:SUMO_HOME = 'C:\Program Files (x86)\Eclipse\Sumo'
$env:Path = "$env:SUMO_HOME\bin;$env:Path"
$env:PYTHONUTF8 = '1'
```

环境变量只对当前 PowerShell 窗口生效；每次新开窗口都需要重新设置。

### 4.3 部署前预检

```powershell
python run.py validate

$expected = '4D471C119A4853F6D5A69047729D608CA5CE72AC6AD4C73313BDE7BB1EDA84C3'
$actual = (Get-FileHash '.\models\edge\peak\model.onnx' -Algorithm SHA256).Hash
if ($actual -ne $expected) { throw "正式早高峰模型校验失败：$actual" }

sumo -c '.\sumo_files\xiongan_real_peak.sumocfg' --end 0 --no-step-log true --duration-log.disable true
```

预检应确认：

- 路口数量为 30；
- 全局状态维度为 660，即 `30 × 22`；
- 路网、三类交通需求和正式 ONNX 模型均存在；
- SUMO 能加载 `xiongan_real_peak.sumocfg`，且无致命错误。

## 5. 典型场景完整复现：真实早高峰协同管控

这是评审现场最短、最稳定的复现路径。需要两个 PowerShell 窗口，整个验收约 1 分钟。

### 5.1 窗口 A：启动 30 路口协同管控服务

```powershell
Set-Location 'C:\path\to\xiongan-traffic-control'
.\.venv\Scripts\Activate.ps1

$sumoExe = (Get-Command sumo.exe -ErrorAction Stop).Source
$env:SUMO_HOME = Split-Path -Parent (Split-Path -Parent $sumoExe)
$env:PYTHONUTF8 = '1'

python server\visualization_server.py --scenario real_peak --port 8765 --no-llm
```

`--no-llm` 只关闭可选的慢周期大模型告警，不影响 SUMO、ONNX DQN、动作掩码、安全约束和信号控制闭环。仓库没有把可选 GGUF 大模型作为本次基础复现的前置条件。

看到以下关键信息后，保持窗口 A 运行：

```text
TraCI 连接成功
正式边缘模型已加载: edge-real-peak-onnx-v1
WebSocket 服务器已启动 — ws://localhost:8765
DQN 模型: 已加载
```

### 5.2 窗口 B：生成闭环验收证据

```powershell
Set-Location 'C:\path\to\xiongan-traffic-control'
.\.venv\Scripts\Activate.ps1
$env:PYTHONUTF8 = '1'

New-Item -ItemType Directory -Force '.\artifacts\reproduction' | Out-Null

python scripts\verify_unity_ws_closed_loop.py `
  --uri ws://127.0.0.1:8765 `
  --seconds 30 `
  --require-mask `
  --expect-model-id edge-real-peak-onnx-v1 `
  --report '.\artifacts\reproduction\real_peak_closed_loop.json'
```

验收通过时，命令退出码为 0，屏幕和 JSON 报告中应满足：

- `passed` 为 `true`；
- `validation_errors` 为空；
- `connected.model_loaded` 为 `true`；
- `connected.model_backend` 为 `edge-onnx`；
- `connected.intersection_order` 完整包含 `J01` 至 `J30`；
- `states` 大于 0；
- 每个抽样帧的 `traffic_lights`、`actions`、`requested_actions`、`action_masks` 均为 30；
- `model_ids` 仅包含 `edge-real-peak-onnx-v1`；
- `vehicle_count_max` 大于 0。

这份报告证明的不是静态模型加载，而是下列过程已经连续发生：

```text
SUMO 车辆运行
  → 660 维全局状态（30×22）
  → 30×4 动作掩码
  → ONNX DQN 批量推理
  → 最小绿灯约束
  → 30 路口动作写回 SUMO
  → 新状态和实时指标通过 WebSocket 返回
```

完成后，在窗口 A 按 `Ctrl+C` 停止服务。若需要保留答辩证据，请不要删除 `artifacts/reproduction/real_peak_closed_loop.json`。

### 5.3 本仓库最近一次命令行复验结果

在 Python 3.12.14、SUMO 1.27.1、Windows 环境下，以上闭环命令已实际通过：正式模型成功加载，15 秒内收到 21 个有效状态帧，30 个路口、30 组请求动作、30 组执行动作和 30 组动作掩码均通过校验，`validation_errors=[]`、`passed=true`。

状态帧数量和车辆数量会随机器性能与采样时刻变化；评审时应以结构校验和 `passed=true` 为准，不应要求数值与上述样例逐项相同。

## 6. Unity 图形化演示

命令行闭环通过后，再进行本节；Unity 只是展示层，不应替代上一节的机器验收。

1. 保持第 5.1 节的 `visualization_server.py` 正在运行。
2. 用 Unity Hub 添加项目目录 `frontend/CitySimulation`。
3. 使用 Unity `2022.3.62f2c1` 打开项目，等待首次资源导入和脚本编译完成。
4. 打开场景 `Assets/Scenes/City.unity`。
5. 点击 Unity 顶部的 Play 按钮。
6. 场景已预配置连接 `127.0.0.1:8765`，正常情况下无需修改 Inspector。

画面中应能观察到：

- 30 路口路网、车辆运动和信号灯相位变化；
- 左上角连接状态与当前场景；
- 实时车辆数、速度、排队等指标；
- 右上角早高峰、平峰、晚高峰切换按钮；
- WebSocket 状态帧携带 DQN 建议动作、实际执行动作、动作掩码、Q 值和推理时延，可由闭环验收脚本或演示录制组件审计。

演示镜头快捷键：

- 数字键 `1`：30 路口全景；
- 数字键 `2`：J01 附近路口特写；
- 数字键 `3`：J19 附近中心路口特写；
- `W/A/S/D`：平移；鼠标滚轮或 `Q/E`：调整高度。

推荐答辩演示顺序：先用数字键 `1` 展示全局协同，再用 `2` 或 `3` 展示单路口信号与车辆响应，最后点击场景按钮展示需求变化下的模型热切换。场景切换后，应等待界面显示新的场景名和对应模型 ID，再继续讲解。

## 7. 无模型演示对照与正式定周期基线

### 7.1 无模型可视化对照

先停止 DQN 服务，再使用相同的早高峰配置启动无模型模式。这里改用 `8766`，避免 Windows 在刚结束 WebSocket 客户端连接后短暂占用原端口：

```powershell
python server\visualization_server.py --scenario real_peak --port 8766 --no-model --no-llm
```

服务日志会把该模式标记为“固定配时”：

```text
未加载 DQN 模型（--no-model 模式），使用固定配时
DQN 模型: 未加载（固定配时）
```

可以再次运行闭环采集脚本，但不要添加 `--require-mask` 和 `--expect-model-id`：

```powershell
python scripts\verify_unity_ws_closed_loop.py `
  --uri ws://127.0.0.1:8766 `
  --seconds 30 `
  --report '.\artifacts\reproduction\real_peak_fixed_time.json'
```

该命令适合直观看“有模型/无模型”的控制链路差异，但它不会自动加载 `data/timing_plans.json`，因此不能代替正式定周期基线评估，也不能仅凭两次短时画面计算提升比例。

如需在 Unity 中显示基线，请将场景内 `VisualizationSystem.serverPort` 临时改为 `8766`；返回模型组时改回 `8765`。

### 7.2 正式定周期基线

真实定周期控制器位于 `baselines/fixed_time.py`，会从 `data/timing_plans.json` 读取各路口、各时段的绿灯/黄灯/全红时长，并让 SUMO 按固定周期自主运行。先确认 30 个早高峰方案都能解析：

```powershell
python baselines\fixed_time.py --periods peak
```

如需运行 J01 早高峰的多策略基线评估：

```powershell
python evaluation\evaluate_all_strategies.py `
  --scenario real_peak `
  --period peak `
  --intersection J01 `
  --episodes 5 `
  --max-steps 720
```

此命令默认评估 Random、真实 Fixed-Time 和 Max-Pressure；只有显式提供可用的 Stable-Baselines3 `.zip` 时才会追加 DQN。当前提交包的可部署正式模型是 ONNX，因此完整 ONNX DQN 与真实定周期的量化对比应使用同一指标采集器另行归档，不能把第 7.1 节的短时无模型演示当作正式实验数据。

无论采用何种评估脚本，模型组和基线组都必须使用同一个场景文件、同一仿真时长、同一随机种子和同一指标定义。

完整流向覆盖审计命令如下：

```powershell
python baselines\fixed_time.py --periods peak --check-coverage
```

当前数据在 J02、J05、J07、J10、J13、J17、J26、J27、J30 会报告未覆盖流向警告，J01 无警告。因此本 README 只把 J01 作为可直接复现的真实定周期示例；在修正配时语义或路网映射并重新验证前，不应宣称“30 路口真实定周期基线已完整覆盖”。这些警告不影响第 5 节使用 `rl4` 四动作契约的 30 路口 ONNX 协同闭环。

## 8. Docker 云边分离部署

该方式把边缘 ONNX 推理服务部署在 `8001` 端口，把 SUMO/REST 云端服务部署在 `8000` 端口。首次构建需要联网下载基础镜像、SUMO 和 Python 依赖。

### 8.1 启动服务

```powershell
Set-Location 'C:\path\to\xiongan-traffic-control'

docker compose -f '.\edge_deploy\docker\docker-compose.yml' config --quiet
docker compose -f '.\edge_deploy\docker\docker-compose.yml' up --build -d
docker compose -f '.\edge_deploy\docker\docker-compose.yml' ps

Invoke-RestMethod 'http://127.0.0.1:8001/health'
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/health'
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/edge/health'
```

三个健康检查都成功后，可访问 `http://127.0.0.1:8000/docs` 查看和试调 REST 接口。

### 8.2 执行 12 个“状态-推理-动作-反馈”控制周期

```powershell
$api = 'http://127.0.0.1:8000/api/v1'
$startBody = @{ scenario = 'real_peak'; use_gui = $false; seed = 42 } | ConvertTo-Json
$session = Invoke-RestMethod "$api/simulation/start" -Method Post -ContentType 'application/json' -Body $startBody

try {
    1..12 | ForEach-Object {
        $predictBody = @{
            session_id = $session.session_id
            model_id = 'edge-real-peak-onnx-v1'
        } | ConvertTo-Json

        $decision = Invoke-RestMethod "$api/edge/predict" -Method Post -ContentType 'application/json' -Body $predictBody

        $actionBody = @{
            session_id = $session.session_id
            expected_transition_id = $decision.transition_id
            actions = $decision.actions
            step_seconds = 5
        } | ConvertTo-Json -Depth 6

        $step = Invoke-RestMethod "$api/simulation/actions" -Method Post -ContentType 'application/json' -Body $actionBody

        [pscustomobject]@{
            cycle = $_
            transition = $step.transition_id
            simulation_time = $step.simulation_time
            edge_latency_ms = $decision.latency_ms
            actions = $decision.actions_ordered.Count
        }
    }

    Invoke-RestMethod "$api/simulation/rewards?session_id=$($session.session_id)&include_breakdown=true"
}
finally {
    $stopBody = @{ session_id = $session.session_id } | ConvertTo-Json
    Invoke-RestMethod "$api/simulation/stop" -Method Post -ContentType 'application/json' -Body $stopBody
}
```

每一轮应返回 30 个动作，`transition_id` 应从 0 逐轮递增，仿真时间每轮增加 5 秒。`expected_transition_id` 是并发安全约束，不得写死或跳过。

### 8.3 停止容器

```powershell
docker compose -f '.\edge_deploy\docker\docker-compose.yml' down
```

如需保留日志用于答辩，请先执行：

```powershell
New-Item -ItemType Directory -Force '.\artifacts\docker' | Out-Null
docker compose -f '.\edge_deploy\docker\docker-compose.yml' logs --no-color | Out-File '.\artifacts\docker\compose.log' -Encoding utf8
```

## 9. REST 接口和数据契约

主要接口：

- `GET /api/v1/health`：云端 API 与 SUMO 可用性。
- `POST /api/v1/simulation/start`：按 `real_peak`、`real_offpeak` 或 `real_evening` 创建会话。
- `GET /api/v1/simulation/state`：返回 660 维全局状态和实时交通快照。
- `POST /api/v1/edge/predict`：将 30 组 22 维状态和 30×4 动作掩码发送给 ONNX 边缘服务。
- `POST /api/v1/simulation/actions`：执行 30 路口动作并推进 SUMO。
- `GET /api/v1/simulation/rewards`：返回局部奖励和全局平均奖励。
- `POST /api/v1/simulation/stop`：关闭会话并释放 TraCI。

动作语义：

- `0`：南北直行及右转；
- `1`：南北保护左转；
- `2`：东西直行及右转；
- `3`：东西保护左转。

正式契约文件：

- `docs/interface_contract.json`：路口顺序、状态维度、动作语义和版本。
- `docs/lane_mapping.json`：车道到方向的映射。
- `docs/tls_mapping.json`：路口信号控制映射。
- `configs/edge_model_registry.json`：允许部署的 ONNX 模型、状态和哈希。

注意：`POST /api/v1/model/predict` 面向 Stable-Baselines3 `.zip` 原始训练模型；本仓库当前可直接部署的正式交付物是 `models/edge/` 下的 ONNX 模型。因此评审复现应使用第 5 节的 WebSocket 闭环，或 Docker 模式下的 `/api/v1/edge/predict`，不要把缺少原始 `.zip` 当成 ONNX 演示失败。

## 10. 更换场景

命令行直接启动其他场景：

```powershell
python server\visualization_server.py --scenario real_offpeak --port 8765 --no-llm
python server\visualization_server.py --scenario real_evening --port 8765 --no-llm
```

对应的验收模型 ID：

- 平峰：`edge-real-offpeak-via-evening-onnx-v1`；
- 晚高峰：`edge-real-evening-onnx-v1`。

也可在 Unity 运行时点击场景按钮。后端会关闭当前 SUMO 会话、加载目标场景和正式模型，再从新场景的第一个有效状态帧继续推送。

## 11. 常见问题

### `sumo.exe` 或 `TraCI` 找不到

确认当前窗口已经激活 `.venv`，并重新设置：

```powershell
$sumoExe = (Get-Command sumo.exe -ErrorAction Stop).Source
$env:SUMO_HOME = Split-Path -Parent (Split-Path -Parent $sumoExe)
$env:Path = "$env:SUMO_HOME\bin;$env:Path"
python -c "import traci; print(traci.__file__)"
```

### 端口 `8765`、`8000` 或 `8001` 被占用

```powershell
Get-NetTCPConnection -State Listen | Where-Object LocalPort -In 8765,8000,8001
```

先正常停止占用端口的本项目进程；不要在不确认进程归属的情况下强制结束其他程序。可视化服务也可改用其他端口，但 Unity 的 `VisualizationSystem` 必须同步修改 `serverPort`。

### 服务启动了，但显示“模型加载失败”

检查模型文件和哈希：

```powershell
Test-Path '.\models\edge\peak\model.onnx'
Get-FileHash '.\models\edge\peak\model.onnx' -Algorithm SHA256
Get-Content '.\configs\edge_model_registry.json'
```

正式早高峰 ONNX 模型哈希应为 `4d471c119a4853f6d5a69047729d608ca5ce72ac6ad4c73313bde7bb1eda84c3`。不要通过修改注册表或跳过哈希校验来掩盖模型损坏。

### Unity 一直显示未连接

先在 PowerShell 中完成第 5.2 节。如果命令行验收通过，则后端和端口正常；再检查 Unity 场景是否为 `Assets/Scenes/City.unity`、`VisualizationSystem.serverHost` 是否为 `127.0.0.1`、`serverPort` 是否为 `8765`，以及 Windows 防火墙是否拦截 Unity Editor。

### 没有本地 LLM/GGUF 模型

使用 `--no-llm` 即可完成本赛题要求的基础协同管控复现。LLM 告警属于可选扩展，不影响 ONNX DQN 快速控制链路。

### 是否需要重新训练

不需要。评审复现使用仓库内 `models/edge/peak/model.onnx`。重新训练耗时长、依赖随机性，且不会提高现场复现的确定性。只有在研究训练过程时才运行 `training/` 下的脚本，并将新结果写入独立目录，避免覆盖正式模型。


## 12. 复现边界

本 README 保证的是已交付代码、SUMO 场景和正式 ONNX 边缘模型的部署及闭环运行。短时闭环验收用于证明系统实现与集成稳定性；平均行程时间、排队长度、通行能力、能耗等算法提升比例，应引用相同场景、相同负荷、相同随机种子和足够回合数的实验评估结果，不能由一次 30 秒验收报告外推。

赛题原始数据位于 `赛题资料/`，正式运行资产位于 `sumo_files/`。如重新生成路网或交通流，必须重新执行预检、网络映射校验和模型适配检查，并保留生成参数与版本信息。
