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
│   └── train_dqn.py              # DQN训练脚本
├── evaluation/                   # 评估
├── server/                       # Unity可视化 WebSocket 服务
├── sumo_files/                   # SUMO路网文件
│   ├── xiongan_30.nod.xml        # 30路口节点定义
│   ├── xiongan_30.edg.xml        # 边定义
│   ├── xiongan_30.net.xml        # 路网文件
│   ├── xiongan_real_peak.rou.xml     # 真实早高峰需求（赛题xlsx生成）
│   ├── xiongan_real_offpeak.rou.xml  # 真实平峰需求
│   └── xiongan_real_evening.rou.xml  # 真实晚高峰需求
├── docs/                         # 文档
│   ├── lane_mapping.json         # 30路口车道方向映射
│   └── state_definition.md       # 状态定义
├── data/                         # 数据
│   └── timing_plans.json         # 真实定周期配时方案
├── scripts/                      # 脚本
│   ├── generate_real_demand_scenarios.py  # 真实需求场景生成
│   └── validate_network.py       # 网络验证
├── configs/                      # 配置（30路口常量）
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
python src/api/api_server.py
# 访问 http://localhost:8000/docs
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
