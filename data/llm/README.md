# 赛道 C LLM 微调数据集（交通事件识别 + 管控建议生成）

> 生成日期：2026-08-24 ｜ 数据来源：SUMO 30 路口真实场景仿真（固定配时基线）
> 生成脚本：`scripts/generate_llm_dataset.py` ｜ 标注器：`llm_data/oracle.py`

## 1. 任务定义

"云脑"决策支持任务：给定**单路口最近一个时间窗**的交通状态序列（文本化），
输出事件类别与管控建议：

```
输入：  【路口 J16】最近 30 秒交通状态（每 5 秒采样）：北向:排队6辆 平均等待32秒 占有率0.42 均速21km/h …
输出：  {"event": "正常|拥堵|溢出|事件", "confidence": 0.0~1.0, "advice": "中文管控建议"}
```

四类事件：**正常 / 拥堵 / 溢出（回堵风险）/ 事件（施工占道）**。
标签由规则 oracle 自动生成（注入真值 + 阈值判定），置信度恒为 1.0（教师信号）。

## 2. 数据 schema（JSONL，每行一个样本）

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | str | `{scenario}-{perturbation}-{seed}-{sim_time}-{junction}` |
| `scenario` / `scenario_cn` | str | real_peak/real_offpeak/real_evening + 中文名 |
| `perturbation` | str | `none` 或 `construction`（施工占道） |
| `seed` / `sim_time` / `clock` | int/float/str | 随机种子 / 仿真秒 / 时钟 |
| `junction` | str | J01~J30 |
| `window_sec` / `sample_sec` | int | 窗口长度 / 采样步长 |
| `snapshots` | list | 窗口内快照序列：每项含 `t`、`phase_name`（含绿/黄/红）、`phase_elapsed`、`vehicle_count`、`dirs{N/S/E/W: {queue, wait, occupancy, speed_kmh}}` |
| `text` | str | 渲染后的中文输入（微调 user 侧） |
| `label` | dict | `{event, event_en, confidence, advice}` |
| `evidence` | dict | 判定依据（trigger/direction/value/threshold/hits，注入真值时为扰动规格） |
| `target` | str | 训练目标 JSON 字符串（response 侧） |

## 3. 生成方法（数据处理环节）

1. 用真实场景路由 + 可选施工占道扰动启动 SUMO（`--seed` 改变车辆到达时刻分布）；
2. 信号控制 = **真实定周期配时**（`data/timing_plans.json`，与官方评估基线一致），
   由 `RealFixedTimeController` 安装到全部 30 路口；
3. 每 5s 提取全部路口原始特征（排队辆数/平均等待秒/占有率/均速 km/h/相位），
   按 30s 窗口（默认不重叠）交给规则 oracle 标注；
4. 渲染中文文本 + 标签 JSON 写入 JSONL。

标注优先级：**事件（注入真值）> 溢出 > 拥堵 > 正常**；
溢出/拥堵要求窗口内 ≥ 50% 采样点满足阈值（`persistence=0.5`，防瞬时抖动）。

## 4. 阈值校准（2026-08-24 实测）

方向最大排队分位数（`<文件名>_stats.json` 的 calibration 段）：

| 运行 | p50 | p90 | p99 | max |
|---|---|---|---|---|
| real_peak-construction 全量 7200s | 8 | 24 | 47 | 52 |
| real_evening 600s | 6 | 14 | 21 | 23 |
| real_offpeak 600s | 5 | 12 | 18 | 19 |

阈值取全量 p90 附近：`spillover_queue=24`（≈最严重 10% 窗口）、
`congestion_queue=10`、`congestion_occupancy=0.35`。
生成更大数据集后应复核 stats 分位数再微调（`--thresholds '{"spillover_queue": 30}'`）。

## 5. 生成命令

```bash
# 冒烟（~1 分钟，2 个 run 各 600s）
python scripts/generate_llm_dataset.py --scenarios real_peak --perturbations none,construction \
    --seeds 42 --end 600 --out data/llm/smoke.jsonl

# 正式数据集（3 场景 × 2 扰动 × 3 种子，全 7200s；实测 ~107s/run，共约 25~30 分钟）
python scripts/generate_llm_dataset.py --seeds 42,43,44 --out data/llm/dataset_v1.jsonl

# 事件密集补充（construction 短窗 + 10s 滑动标注：每 run 25 事件样本 vs 常规 9）
python scripts/generate_llm_dataset.py --scenarios real_peak,real_evening \
    --perturbations construction --seeds 42,43,44 --end 600 --label-stride 10 \
    --out data/llm/dataset_incident.jsonl
```

每个输出配套 `<文件名>_stats.json`：类别分布 + 校准分位数 + 每 run 耗时。

## 6. 冒烟验证结果（2026-08-24）

| 运行 | 样本 | 正常 | 拥堵 | 溢出 | 事件 |
|---|---|---|---|---|---|
| real_peak-none 600s | 600 | 463 | 137 | 0 | 0 |
| real_peak-construction 600s | 600 | 453 | 134 | 4 | 9 |
| real_peak-construction 7200s | 7200 | 4767 | 1658 | 766 | 9 |
| offpeak+evening-none 600s×2 | 1200 | 1046 | 151 | 3 | 0 |
| 事件密集模式 600s (stride 10) | 1740 | 1325 | 388 | 2 | 25 |

事件样本全部落在 J25 北向（扰动注入真值位置），证据字段与建议文案数值一致。

## 7. 已知限制与后续

- **事件类样本少**：单扰动位置（J25 北向）单窗口（60~300s）。后续可扩展多施工点位
  additional 文件（如 `xiongan_30_construction_3sites.add.xml`）提高注入密度；
- **建议模板化**：oracle 建议由模板生成，微调后可配合规则校验保证格式合法；
- **微调（步骤②）**：建议 Qwen2.5-0.5B-Instruct + LoRA，输入 `text`、输出 `target`，
  训练时对四类做类别平衡采样；评估用识别 F1 + 建议 JSON 解析率。

## 8. 相关文件

```
llm_data/schema.py        事件类别/场景表/扰动规格/阈值
llm_data/features.py      TraCI 原始特征提取（复用 docs/lane_mapping.json）
llm_data/oracle.py        规则 oracle（标注 + 建议）
llm_data/text_format.py   状态窗口 → 中文文本
scripts/generate_llm_dataset.py  主流水线
sumo_files/xiongan_30_construction.add.xml  施工占道扰动（e_J20_J25 60~300s 限速 5m/s）
```
