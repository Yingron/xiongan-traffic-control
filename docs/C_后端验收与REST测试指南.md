# C 同学后端验收与 REST 正式模型测试指南

本文用于在 Windows PowerShell 中重复验收 30 路口后端和正式 DQN 模型。所有命令
均从仓库根目录执行。公开状态契约是 660 维（30×22）；正式模型内部输入是
26 维（22 状态+4 动作掩码）。

## 1. 准备环境

确认 Python、SUMO 和正式模型文件：

```powershell
$pythonExe = 'D:\ChallengeCup2026\.venv-xiongan-c\python.exe'
& $pythonExe --version
& $pythonExe -c "import traci, torch, stable_baselines3, fastapi; print('dependencies OK')"
Test-Path '.\sumo_files\xiongan_30.sumocfg'
Test-Path '.\models\dqn\dqn_multi_shared_real_peak_perf_1000000steps.zip'
Test-Path '.\models\dqn\dqn_multi_shared_real_evening_perf_1000000steps.zip'
```

最后三项应分别输出依赖成功信息和两个 `True`。如果 Python 位于其他位置，只修改
`$pythonExe`，不要修改项目代码中的模型路径。

## 2. 第一层：静态契约和正式模型专项测试

```powershell
& $pythonExe -m pytest `
  tests\test_30_intersection_contract.py `
  tests\test_model_service.py -q
```

验收内容包括：

- J01–J30、660 维状态和映射文件一致；
- 三个 `ready` model ID 的注册元数据完整；
- 权重文件存在且 SHA-256 正确；
- 模型空间为 26 输入、4 动作；
- 每次输出 30 个合法动作；
- 确定性推理可复现；
- 需求门控掩码能限制无效动作；
- 正式模型动作可提交至真实 SUMO 会话。

预期结果：全部通过。出现 `MODEL_LOAD_FAILED` 时优先检查 Python/SB3/PyTorch 版本；
出现 checksum 错误时不要修改注册表绕过，应重新取得正确权重。

## 3. 第二层：自动验收全部正式模型

```powershell
& $pythonExe scripts\acceptance_test_models.py --warmup 20 --iterations 200
```

脚本会自动发现注册表中所有 `ready` 模型，完成 SHA-256、加载、形状、确定性、掩码
和动作范围验证，并输出 JSON 格式的模型前向与服务封装 mean/P50/P95/P99 延迟。

注意：offpeak alias 与 evening 使用同一物理权重，但仍要分别验证 model ID 和契约。
该脚本测量的是进程内模型服务，不包含 HTTP、TraCI 推进和网络开销。

## 4. 第三层：启动 REST 服务

打开第一个 PowerShell 窗口：

```powershell
$pythonExe = 'D:\ChallengeCup2026\.venv-xiongan-c\python.exe'
& $pythonExe server\api_server.py
```

看到 Uvicorn 监听 `127.0.0.1:8000` 后不要关闭窗口。浏览器可打开：

```text
http://127.0.0.1:8000/docs
```

Swagger 页面适合逐个试接口；以下 PowerShell 流程更适合完整闭环验收。

## 5. 第四层：手工执行正式 REST 闭环

打开第二个 PowerShell 窗口并进入仓库根目录。

### 5.1 健康检查

```powershell
$baseUrl = 'http://127.0.0.1:8000/api/v1'
$health = Invoke-RestMethod -Method Get -Uri "$baseUrl/health"
$health
```

确认 `sumo_available` 为 `True`。

### 5.2 创建真实晚高峰会话

```powershell
$startBody = @{
  scenario = 'real_evening'
  use_gui = $false
  seed = 20260820
} | ConvertTo-Json

$session = Invoke-RestMethod -Method Post `
  -Uri "$baseUrl/simulation/start" `
  -ContentType 'application/json' `
  -Body $startBody

$sessionId = $session.session_id
$sessionId
$session.state_dimension
$session.intersection_order.Count
```

预期：`state_dimension=660`，路口数量为 30。

### 5.3 查询状态

```powershell
$state = Invoke-RestMethod -Method Get `
  -Uri "$baseUrl/simulation/state?session_id=$sessionId"

$state.state_vector.Count
$state.intersections.Count
$state.transition_id
```

预期依次为 660、30、0。

### 5.4 调用正式模型

```powershell
$predictBody = @{
  session_id = $sessionId
  model_id = 'shared-dqn-real-evening-masked-1m-v1'
  deterministic = $true
} | ConvertTo-Json

$prediction = Invoke-RestMethod -Method Post `
  -Uri "$baseUrl/model/predict" `
  -ContentType 'application/json' `
  -Body $predictBody

$prediction.model_contract_version
$prediction.inference_latency_ms
$prediction.actions.PSObject.Properties.Count
$prediction.actions
```

预期：契约为 `shared-dqn-26x4-v1`、动作数量为 30，所有动作均在 0–3。

### 5.5 提交模型动作

```powershell
$actionBody = @{
  session_id = $sessionId
  expected_transition_id = $prediction.transition_id
  actions = $prediction.actions
  step_seconds = 5
} | ConvertTo-Json -Depth 5

$applied = Invoke-RestMethod -Method Post `
  -Uri "$baseUrl/simulation/actions" `
  -ContentType 'application/json' `
  -Body $actionBody

$applied.transition_id
$applied.applied_actions.PSObject.Properties.Count
```

预期：`transition_id` 从 0 变为 1，并确认提交了 30 个动作。

### 5.6 查询奖励并关闭会话

```powershell
$rewards = Invoke-RestMethod -Method Get `
  -Uri "$baseUrl/simulation/rewards?session_id=$sessionId&transition_id=1"
$rewards.rewards.PSObject.Properties.Count
$rewards.global_reward

$stopBody = @{ session_id = $sessionId } | ConvertTo-Json
Invoke-RestMethod -Method Post `
  -Uri "$baseUrl/simulation/stop" `
  -ContentType 'application/json' `
  -Body $stopBody
```

奖励项数量应为 30。无论中途哪一步失败，排查后都应调用 stop，避免残留 TraCI 会话。

## 6. 测试其他正式场景

重复第 5 节时，保持场景与 model ID 对应：

| scenario | model_id |
|---|---|
| `real_peak` | `shared-dqn-real-peak-masked-1m-v2` |
| `real_offpeak` | `shared-dqn-real-offpeak-via-evening-v1` |
| `real_evening` | `shared-dqn-real-evening-masked-1m-v1` |

平峰 model ID 指向 evening 权重是正式设计，不是路径配置错误。

## 7. 自动 REST 冒烟和完整回归

服务已在第一个窗口启动时，可运行：

```powershell
& $pythonExe scripts\smoke_test_api.py
```

停止独立服务后，再运行测试套件，避免端口或 SUMO 会话互相干扰：

```powershell
& $pythonExe -m pytest `
  tests\test_api_server.py `
  tests\test_model_service.py `
  tests\test_websocket_server.py `
  tests\test_30_intersection_contract.py -q

& $pythonExe -m pytest -q
```

第一条是后端专项验收；第二条是全仓回归。全仓若失败，应区分本次后端问题、缺失的
可选外部环境和历史测试收集问题，不能只报告“部分通过”。

## 8. 常见错误

| 错误 | 常见原因 | 处理 |
|---|---|---|
| `MODEL_NOT_FOUND` | model ID 拼写错误 | 从 `configs/model_registry.json` 复制 `ready` ID |
| `MODEL_NOT_LOADED` | 使用 archived ID 或权重缺失 | 改用正式 ID，检查 artifact 路径 |
| `MODEL_LOAD_FAILED` | 权重损坏或依赖不兼容 | 核对 SHA-256、SB3、PyTorch 版本 |
| `MODEL_CONTRACT_MISMATCH` | 输入/动作空间或掩码形状错误 | 确认公开 22 维、内部 26 维、4 动作 |
| `STALE_TRANSITION` | 使用旧状态的 transition ID | 重新查询状态或重新预测 |
| `SESSION_BUSY` | 同一会话并发推进 | 等当前动作完成后再提交 |
| `TRACI_UNAVAILABLE` | SUMO_HOME/进程/端口问题 | 检查 SUMO 安装并停止残留会话 |

## 9. 当前阶段验收边界

第1–8节验收“正式 SB3 模型 + 后端 REST/TraCI 闭环”；第10节单独验收轻量化模型。
Docker部署已完成SUMO/API/ONNX双服务三场景闭环验收，复验方式见
`docs/容器化部署指南_20260823.md`；Unity直连8000端口仍未完成，不得与Docker闭环混为一项。

## 10. 轻量化模型复验

### 10.1 重新生成全部产物

```powershell
& $pythonExe training\train_distill.py
```

该命令从两个正式SB3权重重新生成 peak/evening 的ONNX、动态INT8、结构化剪枝和
剪枝INT8产物，并更新 `models/edge/manifest.json`。默认约20秒，不启动SUMO。

### 10.2 离线精度、大小和延迟

```powershell
& $pythonExe edge_deploy\benchmark.py --samples 10000 --iterations 500
```

检查 `models/edge/validation_report.json`：顶层应为 `PASS`，两个场景的
`recommended_artifact` 均应为 `model.onnx`。重点字段：

- `action_agreement >= 0.95`；
- `mask_compliance = 1.0`；
- `size_bytes <= 1048576`；
- `single.p95_ms <= 100`；
- `batch30.p95_ms <= 500`。

### 10.3 真实SUMO状态精度

```powershell
& $pythonExe scripts\validate_edge_on_sumo.py --steps 120 --artifact model.onnx
```

该测试覆盖三场景×8代表路口，共2,880条连续真实状态，约需2分钟。预期顶层
`status=PASS`，每个场景 `action_agreement=1.0`。

如需复现实验性INT8未通过的结果，使用独立输出文件，避免覆盖正式报告：

```powershell
& $pythonExe scripts\validate_edge_on_sumo.py `
  --steps 120 `
  --artifact model_int8.onnx `
  --output models\edge\real_state_validation_int8_repeat.json
```

该命令预期可能以退出码1结束，因为真实状态一致率低于95%；这是已记录的模型精度
结论，不是脚本故障。

### 10.4 单个模型推理

```powershell
& $pythonExe edge_deploy\inference.py `
  --model models\edge\peak\model.onnx `
  --benchmark `
  --iterations 1000
```

### 10.5 自动测试

```powershell
& $pythonExe -m pytest tests\test_edge_deploy.py -q
& $pythonExe -m pytest -q
```

轻量化结论和完整数值见 `docs/轻量化验证报告_20260820.md`。Docker和Unity直连仍是
后续工作，不应与本节的模型产物验收混为一项。
