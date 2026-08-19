# C 同学 30 路口 WebSocket 联调记录

## 1. 交付范围

当前 WebSocket 服务已迁移为 30 路口契约。WebSocket 集成在现有
FastAPI 服务中，与 REST API 共用同一个 `TraCISessionManager`、TraCI 连接、
会话锁和 `transition_id`。

服务地址：

```text
ws://<host>:8000/api/v1/ws
```

WebSocket 本身不承载模型预测请求；正式 DQN 预测由同一 FastAPI 服务的
`POST /api/v1/model/predict` 完成。调用方取得 J01–J30 共 30 个真实预测动作后，
可通过 WebSocket 或 REST 动作端点提交。服务不生成随机动作或模拟 DQN 结果。

## 2. 已实现功能

- 按 `session_id` 订阅 `state`、`reward` 通道；
- 首次订阅立即返回当前真实 SUMO 快照；
- 状态严格按 J01–J30 排列，总长度 660，每路口 22 维；
- 奖励包含 J01–J30 共 30 项及 `global_reward`；
- WebSocket 可提交一次完整的 30 路口动作；
- REST 执行动作后向相同会话的 WebSocket 订阅者广播新快照；
- REST 停止或重置会话时推送相应事件并取消旧会话订阅；
- 支持 `ping`/`pong` 和服务端心跳；
- 非法订阅、非法动作、旧 `transition_id` 和无效会话使用结构化错误响应。

## 3. 与 D 同学的对接步骤

1. 使用 REST `POST /api/v1/simulation/start` 创建会话；
2. 连接 `/api/v1/ws`；
3. 发送订阅消息：

```json
{"type":"subscribe","session_id":"<REST返回值>","channels":["state","reward"]}
```

4. 等待 `subscription.confirmed` 和第一条 `simulation.state`；
5. Unity 使用快照中的 `transition_id` 提交完整动作：

```json
{
  "type": "simulation.actions",
  "request_id": "unity-001",
  "session_id": "<session_id>",
  "expected_transition_id": 0,
  "actions": {"J01": 0, "J02": 0, "...": 0, "J30": 0},
  "step_seconds": 5
}
```

实际报文中必须列出 J01–J30，不能使用上例的 `"..."` 占位字段。

## 4. 验证结果

执行环境：本地 SUMO 1.27.1、FastAPI TestClient、真实 30 路口路网。

```powershell
& D:\ChallengeCup2026\.venv-xiongan-c\python.exe -m pytest tests/test_websocket_server.py -q
```

验证内容：

- 660 维状态和 30 个有序路口；
- 30 项奖励；
- WebSocket 动作结果和后续状态推送；
- 非法订阅及不完整动作错误；
- REST 动作完成后 WebSocket 收到相同 `transition_id` 的真实 SUMO 状态。

本次专项结果：WebSocket 测试 5 项通过；REST 与 WebSocket 联合回归共 8 项通过。

全仓库回归结果为 12 项通过、1 项既有收集错误。错误位于
`tests/test_dynamic_simulation.py::test_strategies`：该辅助函数被 pytest 当作测试，
但项目没有定义它声明的 `state`、`traci` fixture。该问题不在本次 WebSocket
变更范围内，也没有影响上述专项和真实 SUMO 联调结果。

## 5. 正式模型接入后的边界

正式模型、model ID、SHA-256、26 维模型输入契约和推理链路均已交付并验收。
WebSocket 协议仍保持职责单一：订阅真实状态/奖励并提交动作，不在 WebSocket
消息内请求模型推理。标准链路为：REST `/model/predict` 获取动作，再将动作提交至
WebSocket `simulation.actions` 或 REST `/simulation/actions`。

当前尚未完成的是 Unity 对 8000 端口协议的直接适配，而不是模型权重交付。
