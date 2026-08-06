# 第 3–5 项本地执行报告


## 3. Demo 路网测试（J01–J04）

已对 1–4 路口的早高峰配置完成完整 7,200 秒 SUMO 仿真。四个场景均为 0 碰撞、0 传送。

| 路口 | 到达车辆 | 平均等待时间（s） | 平均行程时间（s） |
|---|---:|---:|---:|
| J01 | 3,962 | 1.04 | 71.05 |
| J02 | 2,751 | 1.00 | 31.51 |
| J03 | 3,124 | 0.88 | 33.38 |
| J04 | 3,379 | 1.01 | 74.10 |

补齐了缺失的 `env/single_intersection_env.py`，提供 22 维局部状态、4 动作空间，以及按回合轮换路口的参数共享环境包装。单路口和多路口环境均已完成 TraCI 冒烟测试。

随后完成了 J01 的 100 步随机动作测试：平均奖励 -0.5600、平均排队 4.38 辆；相位切换、最小绿灯约束和 3 秒黄灯过渡均可正常执行。

## 4. 扩展并验证完整 20 路口路网

完整 20 路口网络完成了 600 秒集成仿真：1,540 辆到达、0 碰撞、0 传送、平均等待 12.83 秒、平均行程 50.83 秒。

原始 `xiongan_20.net.xml` 的相位 1 和相位 3 是黄灯，不能作为有效 RL 动作。已使用 `scripts/normalize_tls.py` 规范为每路口 4 个可控相位，并重新生成：

- `docs/lane_mapping.json`
- `docs/tls_mapping.json`

`scripts/validate_network.py` 已通过：J01–J20 全部为 `traffic_light`，每个路口均有 4 个有效动作，N/S/E/W 映射完整。

保留的本地备份：

- `sumo_files/xiongan_20.pre_rl4.net.xml`
- `sumo_files/xiongan_20.pre_phase_tuning.net.xml`
- `docs/lane_mapping.pre_rl4.json`
- `docs/tls_mapping.pre_rl4.json`

状态提取现已改为读取验证后的 `docs/lane_mapping.json`，并聚合每个方向的全部进口车道；J01 的实测 22 维状态已包含非零排队、等待和占有率特征。环境层还加入了 3 秒黄灯过渡，同时保持 DQN 的 4 动作接口不变。20 路口同步切换测试已通过。

## 5. 评估与优化

新增 `evaluation/optimize_phase_plan.py`，在相同车流与 600 秒窗口下比较三组静态相位时长，目标函数为：

`平均等待时间 + 0.1 × 平均行程时间`，碰撞和传送将被重罚。

| 配时方案 | 相位时长（秒） | 到达车辆 | 平均等待（s） | 平均行程（s） | 得分 |
|---|---|---:|---:|---:|---:|
| balanced | 30 / 12 / 30 / 12 | 1,527 | 0.93 | 58.46 | **6.776** |
| throughput_favored | 36 / 8 / 36 / 8 | 1,549 | 0.93 | 59.31 | 6.861 |
| turn_protection | 30 / 16 / 30 / 16 | 1,512 | 0.93 | 62.66 | 7.196 |

已将得分最佳的 `balanced` 配时应用到 `sumo_files/xiongan_20.net.xml`。原始结果保存在 `logs/phase_tuning_results.json`。

## GPU 训练验证

本机 RTX 2050（4 GB 显存）已完成 CUDA 验证：PyTorch 2.5.1+cu121 可正常执行 GPU 矩阵运算，且依赖检查通过。已执行 300 步多路口共享 DQN 烟雾训练，训练速度约为 18 steps/s，并完成 5 回合评估：平均奖励为 -167.2383（标准差 55.5254）。模型、统计数据和训练曲线分别保存于 `models/dqn/dqn_multi_shared_300steps.zip`、`models/dqn/dqn_multi_shared_300steps_stats.json` 和 `models/dqn/dqn_multi_shared_300steps_curve.png`。

该短训仅用于验证 GPU、SUMO 环境和共享 DQN 链路，并不构成最终性能结论。正式比较仍应增加训练步数，并与固定配时/自适应基线使用相同随机种子进行评估。

随后已完成 5,000 步多路口共享 DQN 训练（约 277.1 秒，18 steps/s）。5 回合评估平均奖励为 -114.9903，模型、统计和曲线位于 `models/dqn/dqn_multi_shared_5000steps.zip`、`models/dqn/dqn_multi_shared_5000steps_stats.json` 与 `models/dqn/dqn_multi_shared_5000steps_curve.png`。相较 300 步验证的 -167.2383，该次抽样评估更高；由于回合路口为随机抽样，尚不能作为严格性能对比结论。

## 路网安全与控制优化

已将每个动作相位中的右转和掉头连接改为让行绿灯 `g`，消除 SUMO 的 `Unsafe green` 冲突提示；静态 20 路口 600 秒复验结果为：1,527 辆到达、平均等待 0.94 秒、平均行程 58.60 秒、0 碰撞、0 传送。RL 环境的最小绿灯计时也修正为从黄灯结束、目标绿灯实际生效时开始计算。

在上述优化路网中，以相同 3 组种子在 J01 进行 Random、Fixed-Time、Max-Pressure 和 10,000 步共享 DQN 对比。DQN 平均奖励为 -43.09，平均排队为 1.400 辆，平均等待为 40.79 秒，平均进口道通行时间为 30.95 秒，0 碰撞、0 传送。相对 Fixed-Time，平均等待降低 21.3%，平均排队降低 4.1%，通行时间降低 4.2%。原始对比数据、CSV 和图表保存在 `models/dqn/multi_metrics_comparison.json`、`models/dqn/multi_metrics_comparison.csv` 与 `models/dqn/multi_metrics_comparison.png`；优化模型位于 `models/dqn/optimized_safety/dqn_multi_shared_10000steps.zip`。
