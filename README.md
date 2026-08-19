# 雄安新区30路口车路云一体化协同管控平台

## 项目结构

`
xiongan_rl_project/
├── env/                          # 环境定义
│   ├── global_state.py           # 660维状态提取 (30路口×22维)
│   ├── reward_functions.py       # V3奖励函数
│   ├── single_intersection_env.py# 单路口/多路口参数共享环境
│   └── xiongan_env.py            # 全局环境
├── baselines/                    # 基线控制器
│   └── fixed_time.py             # 真实定周期基线（读取 data/timing_plans.json）
├── training/                     # 训练
│   ├── config.py                 # 场景配置（真实早/平/晚高峰）
│   ├── masked_policy.py          # 需求门控动作掩码 DQN 策略（正式配方）
│   └── train_dqn.py              # DQN训练脚本
├── evaluation/                   # 评估（sweep / 三场景官方对比）
├── server/                       # API服务 + Unity可视化 WebSocket 服务
├── sumo_files/                   # SUMO路网文件
│   ├── xiongan_30.nod.xml        # 30路口节点定义
│   ├── xiongan_30.edg.xml        # 边定义
│   ├── xiongan_30.net.xml        # 路网文件
│   ├── xiongan_real_peak.rou.xml     # 真实早高峰需求（赛题xlsx生成）
│   ├── xiongan_real_offpeak.rou.xml  # 真实平峰需求
│   └── xiongan_real_evening.rou.xml  # 真实晚高峰需求
├── docs/                         # 文档
│   ├── 模型交付说明_20260819.md  # ★ 正式模型清单/参数/契约/部署（交付入口）
│   ├── 三场景官方对比_20260819.md # ★ 8路口 + 30路口全量评估结论
│   ├── Unity前端部署启动使用说明.md
│   ├── lane_mapping.json         # 30路口车道方向映射
│   └── state_definition.md       # 状态定义
├── data/                         # 数据
│   └── timing_plans.json         # 真实定周期配时方案
├── scripts/                      # 脚本（场景生成/网络验证/冒烟测试/Q监控/行为探针）
├── configs/                      # 配置（30路口常量 + model_registry.json 模型注册表）
└── requirements.txt
`

## 快速开始

### 1. 环境准备
`bash
pip install -r requirements.txt
# 设置SUMO_HOME环境变量
`

### 2. 启动API服务
`bash
python server/api_server.py
# 访问 http://localhost:8000/docs
# 模型注册与推理契约见 docs/模型交付说明_20260819.md
`

### 3. 测试接口
`bash
# 创建会话
curl -X POST http://localhost:8000/api/v1/simulation/start

# 获取状态
curl http://localhost:8000/api/v1/simulation/state?session_id=xxx

# 执行动作
curl -X POST http://localhost:8000/api/v1/simulation/actions
`

## 技术栈
- **后端**: FastAPI + TraCI (SUMO)
- **强化学习**: PyTorch + Stable-Baselines3 + PyMARL
- **仿真**: SUMO + Unity
- **协议**: REST API + WebSocket
