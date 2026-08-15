# DQN 100 万步训练结果（real_offpeak）

## 运行配置

- 命令：`python training/train_dqn.py --timesteps 1000000 --scenario real_offpeak --perf --multi`
- 路网：30 路口
- 算法：共享参数、动作掩码 DQN
- 设备：本机 NVIDIA GPU（CUDA）
- 训练步数：1,000,000

## 训练与评估结果

| 指标 | 数值 |
| --- | ---: |
| 训练总耗时 | 23,537.79 s（6.54 h） |
| 平均训练速度 | 42.48 steps/s |
| 峰值训练速度 | 55.25 steps/s |
| 5 回合评估平均奖励 | 1811.38 ± 641.35 |
| 最低 / 最高回合奖励 | 1142.83 / 2866.15 |
| 每回合平均步数 | 720 |
| 网络参数量 | 11,784 |

## 已提交产物

- `models/dqn/dqn_multi_shared_real_offpeak_perf_1000000steps.zip`：最终模型。
- `models/dqn/dqn_multi_shared_real_offpeak_perf_1000000steps_stats.json`：结构化统计结果。
- `models/dqn/dqn_multi_shared_real_offpeak_perf_1000000steps_curve.png`：训练曲线。

SHA-256：

```text
model  B3169CCE5200FA72516B190FB07B33C43BB887138B5C42EAF6CC5F1F24EAA4AF
stats  1DD7EBB893CDE9D928A90FF5FEFC6ABF96622E96EE4832035A207E554CECC585
curve  05FB77E1B830F22839CF92DCAA472E4AD1F0A917AC0ABB718524E85B8FEBD91F
```

## 说明

本分支同时包含本次训练所需的兼容性修复：30 路口状态维度定义、模型注册表中的 30 路口契约字段，以及 Stable-Baselines3 2.4 回放样本的折扣因子兼容处理。过程日志和中间检查点未提交，以避免仓库冗余。
