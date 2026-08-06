# C 同学 REST 模型接口预留记录

## 1. 当前结论

`POST /api/v1/model/predict` 的 Stable-Baselines3 接入框架已经完成。接口使用真实
TraCI 会话的 440 维状态，按 J01–J20 切成 `float32[20,22]`，并预留使用同一个
参数共享 DQN 批量输出 20 个动作的实现。

当前没有 A 的真实权重，因此未进行模型加载成功、真实动作、确定性及延迟验收，
也没有使用假模型或其他策略替代。

## 2. 已确认契约

| 项目 | 当前值 |
|---|---|
| 模型框架 | Stable-Baselines3 DQN |
| 单路口输入 | 22 维 `float32` |
| 单路口输出 | 离散动作 `0`–`3` |
| 全局状态 | 440 维，按 J01–J20 切分 |
| 模型 ID | `shared-dqn-generalization-100k-v1` |
| 模型契约 | `shared-dqn-22x4-v1` |

## 3. 已完成实现

- JSON 模型注册表；
- SB3 DQN CPU 懒加载及进程内缓存；
- 模型文件 SHA-256 校验；
- 模型 observation/action space 校验；
- 440 维有限值检查及 20×22 有序切分；
- `model.predict(observations, deterministic=...)` 批量入口；
- 20 个整数动作及 `0`–`3` 范围校验；
- 推理耗时字段；
- `MODEL_NOT_FOUND`、`MODEL_NOT_LOADED`、`MODEL_LOAD_FAILED`、
  `MODEL_CONTRACT_MISMATCH`、`MODEL_REGISTRY_INVALID`、`INFERENCE_FAILED`、
  `INVALID_MODEL_OUTPUT` 错误。

## 4. 等待 A 交付/确认

需要 A 提供：

1. `dqn_multi_shared_100000steps.zip` 真实模型权重；
2. 模型文件 SHA-256；
3. 确认训练时未使用额外归一化；若使用 `VecNormalize`，需交付对应 `.pkl`；
4. stable-baselines3、PyTorch、Gymnasium 和 Python 版本；
5. 确认模型为 J01–J20 参数共享泛化模型；
6. 训练代码 Git commit、训练场景和已知限制。

交付后修改 `configs/model_registry.json`：

```json
{
  "status": "ready",
  "normalization": "none",
  "sha256": "A提供的真实SHA-256"
}
```

如果使用了 `VecNormalize`，不能直接将 `normalization` 改成 `none`；需要先扩展
加载器以恢复 A 提供的归一化统计，再进行真实推理。

## 5. 当前验证结果

不依赖模型权重的测试覆盖：

- 440→20×22 顺序和 `float32` 类型；
- 非法状态形状；
- 未注册模型；
- 已注册但等待 A 的模型；
- 真实 SUMO 会话调用 `/model/predict` 时正确返回待交付状态。

模型交付后仍须补充：

- 真实 SB3 加载测试；
- 20 个真实动作输出测试；
- 相同输入的确定性测试；
- CPU 推理 mean/P95/P99 延迟；
- 输出动作可直接提交到 `/simulation/actions` 的闭环测试。

当前模型接口专项测试 5 项通过；REST、WebSocket、模型接口联合回归 13 项通过。
全仓库回归为 17 项通过、1 项既有收集错误：
`tests/test_dynamic_simulation.py::test_strategies` 被 pytest 当作独立测试，但仓库
没有定义它声明的 `state` 和 `traci` fixture。该问题与本次模型接口改动无关。
