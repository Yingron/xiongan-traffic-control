# C 同学 REST 正式模型接入与验收记录

> 状态：已完成正式模型接入。本文替代早期“等待 A 交付”的预留记录；操作步骤见
> [C_后端验收与REST测试指南.md](C_后端验收与REST测试指南.md)。

## 1. 当前结论

`POST /api/v1/model/predict` 已接入真实 Stable-Baselines3 DQN 权重。服务从真实
TraCI 会话读取 660 维公开状态，按 J01–J30 切成 `float32[30,22]`，再为每个路口
追加 4 维需求门控动作掩码，形成 `float32[30,26]` 模型输入并批量输出 30 个动作。

当前没有使用随机策略、固定配时或伪造权重替代模型预测。

## 2. 正式模型

| 场景 | model_id | 权重 | 状态 |
|---|---|---|---|
| 真实早高峰 | `shared-dqn-real-peak-masked-1m-v2` | `models/dqn/dqn_multi_shared_real_peak_perf_1000000steps.zip` | `ready` |
| 真实平峰 | `shared-dqn-real-offpeak-via-evening-v1` | evening 权重的跨场景别名 | `ready` |
| 真实晚高峰 | `shared-dqn-real-evening-masked-1m-v1` | `models/dqn/dqn_multi_shared_real_evening_perf_1000000steps.zip` | `ready` |

历史 `shared-dqn-generalization-100k-v1` 已标记为 `archived`，不得用于正式推理。

## 3. 已确认契约

| 项目 | 当前值 |
|---|---|
| 模型框架 | Stable-Baselines3 DQN + `MaskedDQNPolicy` |
| 对外单路口状态 | 22 维 `float32` |
| 模型单路口输入 | 26 维：22 状态 + 4 动作掩码 |
| 单路口输出 | 离散动作 `0`–`3` |
| 全局公开状态 | 660 维，按 J01–J30 切分 |
| 模型契约 | `shared-dqn-26x4-v1` |
| 状态布局 | `v1-30x22` |
| 归一化 | `none` |

## 4. 已完成实现

- JSON 模型注册表及三场景 model ID；
- 模型文件 SHA-256 校验；
- SB3 DQN CPU 懒加载及进程内缓存；
- observation/action space 校验；
- 660 维有限值检查及 30×22 有序切分；
- TraCI 同刻动作掩码提取及 22→26 维拼接；
- 30 个整数动作及 `0`–`3` 范围校验；
- 确定性推理和逐次推理耗时字段；
- 预测动作提交到 `/simulation/actions` 的真实 SUMO 闭环。

## 5. 验收结果

2026-08-20 完成以下验收：

- 两个物理权重文件存在且 SHA-256 与注册表一致；
- peak、evening、offpeak alias 均可加载并输出 J01–J30 共 30 个动作；
- 相同状态、相同掩码、`deterministic=true` 时动作一致；
- 单一合法动作掩码能约束模型只能选择该动作；
- 真实 REST 闭环通过：创建会话 → 正式模型预测 → 提交动作 → 读取 660 维状态 → 停止会话；
- 正式模型契约测试与 30 路口静态契约测试共 12 项通过。

延迟字段已能正常返回；正式性能报告仍应另行采集 warm-up 后的 mean/P50/P95/P99，
并区分单路口网络前向时间与 REST+TraCI 整体链路时间。

## 6. 已知限制

- 平峰使用 evening 模型泛化。30 路口全量评估 reward 比真实 Fixed-Time 低 1.6%，
  且 J16/J18 等低流量路口等待时间拖尾，演示与报告不得描述为全量全面领先；
- ONNX、动态量化和结构化剪枝已经完成；正式推荐FP32 ONNX，详见
  `docs/轻量化验证报告_20260820.md`。包含SUMO、API和ONNX推理的Docker Compose
  双服务已完成三场景闭环验收，见`docs/容器化部署验收记录_20260823.md`；
- Unity 工程尚未直接接入 8000 端口的 REST/WebSocket 会话协议。
