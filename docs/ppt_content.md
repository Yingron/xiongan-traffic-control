<!-- Slide number: 1 -->

![](图片10.jpg)
云路协同·城市大脑
面向雄安新区“城市大脑”的车路云一体化协同管控算法与仿真平台研究

答辩人：
日期：

### Notes:

<!-- Slide number: 2 -->

01
项目背景与意义

02
研究特色与思路
目录

CONTENT
03
实验设计与结果

04
应用价值与展望

### Notes:

<!-- Slide number: 3 -->

![](图片10.jpg)

01
项目背景与意义

### Notes:

<!-- Slide number: 4 -->

01

产品介绍

### Notes:

<!-- Slide number: 5 -->
1.1 研究背景：为什么需要车路云协同

![](图片46.jpg)

![](图片53.jpg)

窄路密网
路口之间“牵一发而动全身”
车路云协同：四层分工，形成闭环
车端 + 路侧：实时采集车辆排队、道路占用等数据。
边缘侧：5秒一个决策周期，毫秒级输出信号方案。
云端侧：训练 AI 模型、做分钟级全局分析。
仿真平台：复现实验、校验安全约束、可视化展示。
路口间距短、高峰车流集中，相邻路口几十秒内就会互相影响。
一个路口的放行会在数十秒内改变上下游排队。

传统方法难以兼顾全局
固定配时：车流早高峰、晚高峰、平峰差异大，一套时刻表 不适配全天。
单点优化：每个路口独立不可行，必须考虑全局效率。

![](图片5.jpg)

核心诉求：让 30 个路口在统一状态、动作与奖励规范下协同运行，从各自为战变成协同疏堵。

### Notes:

<!-- Slide number: 6 -->
1.2 核心挑战：从“算法有效”走向“系统可用”

多路口协同与实时约束
评价口径与工程衔接
场景真实性与可复现性
评价算法的前提是实验可复现
路网拓扑、信号模板、交通需求与扰动参数均可记录、可调整、可重复。
训练、仿真与部署必须统一口径
单一指标不足以刻画路网运行，离线效果也不等于在线可用
区域协同
必须在 5 秒控制周期内完成实时决策，同时保证下发到每个路口的动作满足安全约束。

多维指标联合评估：通行效率、排队长度、吞吐量与动作稳定性并重，避免单一指标掩盖局部运行风险。
统一状态 - 动作契约：训练、仿真与服务调用采用一致的数据定义，防止“离线有效、在线失效”。
部署保真验证：模型压缩后须在真实 SUMO 状态上复核动作一致性。
参数共享，控制开销可控：30 个路口共享一套网络参数与经验回放，避免逐路口独立训练，支撑批量实时控制

安全执行，动作合法下发：通过动作掩码、最小绿灯与黄灯过渡多重约束，确保相位动作合法、可审计
30 路口“窄路密网”拓扑：贴近雄安近距路口、排队易回溢的实际特征。
早/平/晚高峰多时段交通流：覆盖典型运行状态，避免单场景结论。
施工占道等扰动注入：逼近真实运行场景，检验算法鲁棒性。
同一输入下结果稳定可比：为算法优劣判断提供统一、可信的依据。

本项目的核心目标，不是追求单次实验的更高得分，而是构建稳定、可审计、可复现的车路云协同管控闭环。

### Notes:

<!-- Slide number: 7 -->
1.3 研究现状：算法演进与工程落地并行

从自适应配时到多路口强化学习
车端 / 路侧
快速感知车辆与道路状态

SCATS / SCOOT
依据检测器数据滚动调整周期、绿信比与相位差

车路云协同与轻量化部署

信号控制方法沿“规则配时 → 单路口学习 → 多路口协同”逐步演进。

自适应配时（SCATS / SCOOT）：
基于检测器数据滚动调整周期、绿信比与相位差，构成工程应用基础
DQN / Double-DQN：
将信号控制建模为 "状态 — 动作 — 反馈" 循环，为相位选择提供可训练框架
CoLight / FRAP / PressLight：
通过刻画路口关联、相位竞争与排队压力，走向多路口协同

车路云分层架构按“响应时延”分工：
局部快响应、全局慢决策

![](图形52.jpg)
分层协同
车端 + 路侧：
实时感知，承担局部快速响应
边缘侧：
低时延推理与安全执行，满足秒级控制周期
云端 / 仿真：
模型训练、全局分析与可复现验证，支撑慢周期决策
ONNX + 容器化：
统一模型格式与运行环境，打通算法原型到跨平台部署

共识：区域协同、安全约束、可复现实验与部署保真缺一不可，共同构成系统可用的前提。

### Notes:

<!-- Slide number: 8 -->
1.4 项目目标：形成可验证的技术原型

以 30 个受控路口为对象，
构建“训练 — 控制 — 评估 — 展示”一体化的可验证原型。

![](图形81.jpg)

统一控制契约
安全实时决策
全链路联调验证

覆盖多场景，贯通仿真、推理与可视化，验证模型保真与系统稳定性。
从安全相位集合中实时选动作，经合法性校验后批量下发。
状态、动作、奖励与接口规范同源，控制周期 5 秒。

目标是：建立可复现、可部署、可扩展的验证基础。

### Notes:

<!-- Slide number: 9 -->
2.1 技术路线：云—边—端协同闭环

以仿真真值、边缘控制和云端分析为职责边界，将 30 路口场景、DQN 决策、可视化和部署接入同一条可审计链路。

云端与展示
SUMO 仿真真值
边缘实时决策

30 路口 × 三场景
660维 → 30×26维
服务化与可观测

6×5“窄路密网”
真实早/平/晚高峰
TraCI 真值、推进与执行
30 路口共享参数
4 相位掩码约束
批量动作回传
ONNX + Docker
Unity + WebSocket
可视化与指标
SUMO 负责真值，DQN 负责秒级相位选择，LLM 仅作慢周期建议。

### Notes:

<!-- Slide number: 10 -->
2.2 控制周期：660维状态驱动30路口批量决策

动作执行与安全
状态组织
J01–J30 固定顺序拼接

每路口 22 维：排队、等待、占有率、溢出风险、当前相位与时间特征

全局状态：30×22 = 660 维

追加 4 维绝对动作掩码，形成 26 维局部观测
ONNX 一次批量推理 30 行×26 维

输出每路口 4 个 Q 值，选择合法相位

API 校验路口完整性、掩码、最小绿灯 15 s 与黄灯过渡 3 s

TraCI 同帧回写并广播新快照

26维
→30动作

同一仿真时刻读取、批量决策、批量执行，避免逐路口推进产生时间不一致。

### Notes:

<!-- Slide number: 11 -->
2.3 Unity展示层：30路口的实时表达与演示交互

Unity 只表达 SUMO 快照，不自行生成交通状态；道路、信号灯、车辆与指标均随同一仿真时刻刷新。

车辆与镜头
路网构建
相位可视化

唯一地图
直行与左转
性能与演示

加载 xiongan_30
30 路口 / 30 灯
清理静态车辆
网格建筑填充
四相位独立显示
直行与保护左转
箭头灯随相位更新
车辆池 120–900
单帧预算 850
全景和两组近景
Dashboard 刷新状态

支持三场景切换，统一展示模型状态、信号执行和交通指标。

### Notes:

<!-- Slide number: 12 -->
2.4 闭环验收：三场景切换与连续运行

可核验结果
场景切换与控制链路
real_peak、real_offpeak、real_evening 由 Unity 侧发起切换。

每一控制周期：
Unity → WebSocket → SUMO 状态 → ONNX DQN 掩码推理 → 30 个动作回传 → TraCI 信号执行 → Unity 刷新。

每帧校验 660 维状态、30×4 掩码、30 个动作及 30 盏信号灯。
模型保真
2,880 条真实 SUMO 状态动作一致率 100%。

稳定性
30 分钟连续运行，记录 1,279 个状态快照，协议错误与超时均为 0。

恢复能力
断线后可自动重连，并继续接收状态、车辆和信号灯刷新。

验收重点：三场景完成模型映射与指标重置，30 路口车辆和灯色持续随相位变化。

### Notes:

<!-- Slide number: 13 -->
3.4 实验结果 1 ：

国产大模型领跑双重平衡

Qwen2.5、DeepSeek、GLM4 等国产前沿模型位于“合规-可用”的最佳象限
国产头部模型表现卓越，在深刻理解本土法律法规的同时，并未牺牲服务可用性

海外模型过度防御

Llama 3、GPT-4o-mini 等国外模型虽然合规率极高，但拒答率同时也极高
海外模型普遍存在过度防御现象，倾向于对敏感问题一刀切式拒绝，服务效能折损

部分模型存在合规盲区
高亮的框框
Mistral 及部分早期模型位于合规阈值线左侧
少数模型尚未对齐中国法律价值观，存在显著风险

### Notes:

<!-- Slide number: 14 -->
3.5 实验结果 2

国产前沿模型在合宪性维度达到 100% 合规 ，而海外模型由于缺乏本土法规对齐，在此维度存在显著的合规风险。其它评估维度上各模型表现出平衡的性能。
合规性评测

llama 系列、mistral 系列等海外模型，对歧视性内容和违宪内容未能有效拦截，更易对其他四个评测维度的问题拒绝回答
拒答评测

### Notes:

<!-- Slide number: 15 -->

![](图片10.jpg)

04
应用价值与展望

### Notes:

<!-- Slide number: 16 -->
4.1 项目成果：完成全链条原型闭环

部署与云脑

FP32 ONNX 边缘模型，动作一致性保真。
Docker 容器化，运行环境一键复现。
LLM 云脑：慢周期事件识别与中文建议。
算法与平台

共享掩码 DQN，适配异构路口结构。
统一状态 — 动作契约，支撑 30 路口批量决策。
SUMO 仿真 + Unity 展示，覆盖三时段场景。

![](图片2.jpg)

![](图片11.jpg)

项目已贯通“场景构建—策略决策—安全执行—部署验证—三维展示”全流程

### Notes:

<!-- Slide number: 17 -->
4.1 关键结果：效果、保真与时延同时验收

结果均来自报告中的同口径对照；平峰负值与压缩失败也如实保留。

云脑支持
控制效果
边缘部署

30 路口平均收益：
早高峰 +11.0%
晚高峰 +9.9%。
平峰 −1.6%（低流量路口存在最小绿灯切换开销）
模型仅 25 KB，真实路况下动作一致率 100%
单路口推理约 0.02 ms，满足秒级控制周期
事件识别准确率 99.5%
云端慢周期分析，实时控制仍由边缘 DQN 承担
核心发现：INT8 / 剪枝候选未达到正式部署门槛——轻量化必须逐任务实测

### Notes:

<!-- Slide number: 18 -->

4.2 局限性：从原型可用走向真实可信

在保持现有架构稳定的基础上，逐步扩大实验覆盖面，补充多维评价证据，并增强与真实数据和边缘设备的兼容性
现阶段边界
现实接入仍需扩展
仿真结论尚不能替代道路实测；需引入 V2X 通信时延、路侧设备差异与真实交通流样本复验。

![](图形12.jpg)

评价证据待补齐

需补充多随机种子、策略横向对照、置信区间及安全指标（冲突、碰撞、急减速），增强结论稳健性。
低流量切换开销
平峰收益 −1.6%，源于低流量路口最小绿灯的固定空转，需调整环境机制后重训。

![](图形10.jpg)

![](图形7.jpg)

### Notes:

<!-- Slide number: 19 -->

4.3 未来展望：扩大验证，增强落地能力

评价与算法深化

工程与应用扩展

补充显著性检验、置信区间与安全指标（冲突、急减速）。
针对低流量路口优化最小绿灯与切换惩罚。
探索 LLM 建议经动作掩码参与策略校验。
基于真实交通流样本开展迁移学习与部署复验。
统一奖励版本、接口说明与复现记录。
保持云端慢分析、边缘快控制的职责边界。

![](图片61.jpg)

下一阶段：在保持架构稳定基础上，扩大实验覆盖面、补齐多维证据、增强真实数据与边缘设备兼容性。

### Notes:

<!-- Slide number: 20 -->

参考文献

| [1] | B. Cottier, R. Rahman, L. Fattorini, et al., “The rising costs of training frontier AI models,” arXiv preprint arXiv:2405.21015, 2024. |
| --- | --- |
| [2] | P. Villalobos, A. Ho, J. Sevilla, et al., “Position: will we run out of data? limits of LLM scaling based on human-generated data,” Proceedings of the 41st International Conference on Machine Learning (ICML), 2024, pp. 1–22. |
| [3] | A. Ho, T. Besiroglu, E. Erdil, et al., “Algorithmic progress in language models,” Advances in Neural Information Processing Systems, vol. 37, pp. 58245–58283, 2024. |
| [4] | P. Röttger, F. Pernisi, B. Vidgen, et al., “Safetyprompts: a systematic review of open datasets for evaluating and improving large language model safety,” Proceedings of the AAAI Conference on Artificial Intelligence, vol. 39, no. 26, pp. 27617–27627, 2025. |
| [5] | N. Nangia, C. Vania, R. Bhalerao, et al., “CrowS-Pairs: A Challenge Dataset for Measuring Social Biases in Masked Language Models,” Proceedings of the 2020 Conference on Empirical Methods in Natural Language Processing (EMNLP), 2020, pp. 1953–1967. |
| [6] | J. Li, X. Cheng, W. X. Zhao, et al., “HaluEval: A Large-Scale Hallucination Evaluation Benchmark for Large Language Models,” Proceedings of the 2023 Conference on Empirical Methods in Natural Language Processing, 2023, pp. 6449–6464. |
| [7] | H. Ullrich, J. Drchal, M. Rýpar, et al., “CsFEVER and CTKFacts: acquiring Czech data for fact verification,” Language Resources and Evaluation, vol. 57, no. 4, pp. 1571–1605, 2023. |
| [8] | W. Su, Y. Hu, A. Xie, et al., “STARD: A Chinese Statute Retrieval Dataset with Real Queries Issued by Non-professionals,” arXiv preprint arXiv:2406.15313, 2024. |
| [9] | Y. Xiao, Y. Hu, K.-K. R. Choo, et al., “ToxiCloakCN: Evaluating Robustness of Offensive Language Detection in Chinese with Cloaking Perturbations,” arXiv preprint arXiv:2406.12223, 2024. |
| [10] | T. Brown, B. Mann, N. Ryder, et al., “Language models are few-shot learners,” Advances in neural information processing systems, vol. 33, pp. 1877–1901, 2020. |
| [11] | J. Wei, X. Wang, D. Schuurmans, et al., “Chain-of-thought prompting elicits reasoning in large language models,” Advances in neural information processing systems, vol. 35, pp. 24824–24837, 2022. |
| [12] | H. W. Chung, L. Hou, S. Longpre, et al., “Scaling instruction-finetuned language models,” Journal of Machine Learning Research, vol. 25, no. 70, pp. 1–53, 2024. |
| [13] | N. Ho, L. Schmid, and S.-Y. Yun, “Large language models are reasoning teachers,” arXiv preprint arXiv:2212.10071, 2022. |
| [14] | J. Devlin, M.-W. Chang, K. Lee, and K. Toutanova, “Bert: Pre-training of deep bidirectional transformers for language understanding,” Proceedings of the 2019 conference of the North American chapter of the association for computational linguistics: human language technologies, volume 1 (long and short papers), 2019, pp. 4171–4186. |
| [15] | I. Beltagy, M. E. Peters, and A. Cohan, “Longformer: The long-document transformer,” arXiv preprint arXiv:2004.05150, 2020. |
| [16] | M. Ding, C. Zhou, H. Yang, et al., “Cogltx: Applying bert to long texts,” Advances in Neural Information Processing Systems, vol. 33, pp. 12792–12804, 2020. |
| [17] | A. Vaswani, N. Shazeer, N. Parmar, et al., “Attention is all you need,” Proceedings of the 31st International Conference on Neural Information Processing Systems, 2017, pp. 6000–6010. |
| [18] | Y. Liu, M. Ott, N. Goyal, et al., “Roberta: A robustly optimized bert pretraining approach,” arXiv preprint arXiv:1907.11692, 2019. |
| [19] | 全国网络安全标准化技术委员会, “生成式人工智能服务安全基本要求：TC260-003,” 全国网络安全标准化技术委员会, 2024. |

### Notes:
