# 雄安新区20路口车路云一体化协同管控平台

## 项目结构

`
xiongan_rl_project/
├── src/                          # 源代码
│   ├── api/                      # REST API服务
│   │   └── api_server.py         # FastAPI服务器
│   ├── env/                      # 环境定义
│   │   ├── __init__.py
│   │   ├── global_state.py       # 440维状态提取
│   │   ├── reward_functions.py   # V3奖励函数
│   │   ├── env.py                # 基础环境
│   │   ├── single_env.py         # 单路口环境
│   │   └── xiongan_env.py        # 20路口环境
│   ├── services/                 # 服务层
│   │   └── traci/                # TraCI封装
│   ├── models/                   # 模型定义
│   ├── utils/                    # 工具函数
│   └── config/                   # 配置文件
├── sumo_files/                   # SUMO路网文件
│   ├── xiongan.nod.xml           # 节点定义
│   ├── xiongan.edg.xml           # 边定义
│   ├── xiongan.net.xml           # 路网文件
│   ├── xiongan.rou.xml           # 交通流
│   ├── xiongan.sumocfg           # SUMO配置
│   ├── xiongan_morning.rou.xml   # 早高峰
│   ├── xiongan_flat.rou.xml      # 平峰
│   └── xiongan_evening.rou.xml   # 晚高峰
├── docs/                         # 文档
│   ├── 接口文档.md               # API规范
│   ├── state_definition.md       # 状态定义
│   ├── 路网使用说明.md           # B的README
│   ├── lane_mapping_source.json  # 车道映射
│   └── interface_contract.json   # 接口契约
├── scripts/                      # 脚本
│   ├── validate_source.py        # 源数据验证
│   ├── validate_network.py       # 网络验证
│   ├── normalize_tls.py          # 信号灯规范化
│   └── build_and_validate.ps1    # 构建脚本
├── data/                         # 数据
├── tests/                        # 测试
├── configs/                      # 配置
├── ChallengeCup-main/            # 比赛框架
│   ├── CitySimulation/           # Unity仿真
│   └── pymarl-master/            # PyMARL强化学习
├── requirements.txt
└── README.md
`

## 快速开始

### 1. 环境准备
`ash
pip install -r requirements.txt
# 设置SUMO_HOME环境变量
`

### 2. 启动API服务
`ash
python src/api/api_server.py
# 访问 http://localhost:8000/docs
`

### 3. 测试接口
`ash
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
