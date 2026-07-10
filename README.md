# 面向雄安新区“城市大脑”的车路云一体化协同管控算法与仿真平台

## 项目概述

本项目基于三层协同架构（SUMO仿真核心 + Python算法层 + Unity可视化层），实现面向雄安"窄路密网"的自适应交通信号控制算法。

- **赛题编号**: XH-202613
- **赛道**: C（AI应用型）—— 自适应交通信号控制
- **核心算法**: DQN/D3QN深度强化学习

## 目录结构

```
xiongan_rl_project/
├── env/                # Gym环境封装
├── sumo_files/         # SUMO仿真文件
├── training/           # 训练脚本
├── models/             # 模型存储
├── server/             # WebSocket服务器
├── edge_deploy/        # 边缘部署
├── visualization/      # 可视化脚本
└── docs/               # 文档
```

## 环境搭建

### 1. 创建Conda环境

```bash
conda create -n xiongan_rl python=3.10 -y
conda activate xiongan_rl
```

### 2. 安装SUMO

```bash
# Ubuntu/Debian
sudo add-apt-repository ppa:sumo/stable -y
sudo apt-get update
sudo apt-get install sumo sumo-tools sumo-doc -y

# 设置环境变量
echo 'export SUMO_HOME="/usr/share/sumo"' >> ~/.bashrc
echo 'export PATH="$SUMO_HOME/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

### 3. 安装Python依赖

```bash
pip install -r requirements.txt
```

### 4. 验证环境

```bash
sumo --version
python -c "import traci; import gymnasium as gym; import sumo_rl; print('环境验证成功')"
```

## 运行指南

### 启动SUMO仿真

```bash
sumo-gui -c sumo_files/xiongan.sumocfg
```

### 运行DQN训练

```bash
python training/train_dqn.py --no_gui
```

### 启动WebSocket服务器

```bash
python server/websocket_server.py
```

### 运行对比实验

```bash
python visualization/plot_comparison.py --runs 3
```

### 边缘推理测试

```bash
python edge_deploy/inference.py --benchmark --n 1000
```

## 架构说明

### 三层协同架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Unity 可视化层                                   │
│  • 3D场景渲染                                                       │
│  • 实时数据仪表盘                                                   │
│  • 用户交互控制                                                     │
│  ↕ WebSocket                                                        │
├─────────────────────────────────────────────────────────────────────┤
│                    Python 算法层                                    │
│  • DQN/D3QN训练                                                     │
│  • 模型轻量化（剪枝+蒸馏+量化）                                      │
│  • 边缘端推理                                                       │
│  ↕ TraCI协议                                                        │
├─────────────────────────────────────────────────────────────────────┤
│                    SUMO 仿真层                                      │
│  • 20路口路网仿真                                                   │
│  • 交通流生成                                                       │
│  • 信号控制执行                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## 关键指标

| 指标 | 目标 |
|------|------|
| 模型体积 | < 1MB |
| 推理延迟 | < 5ms |
| 平均行程时间降低 | ≥ 15% |
| 平均排队长度降低 | ≥ 20% |

## 团队分工

### 角色定义

| 角色 | 职责 |
|------|------|
| A | 算法负责人 + 项目经理 |
| B | SUMO仿真工程师 |
| C | Python后端/接口工程师 |
| D | Unity可视化 + 测试工程师 |

### 文件夹-角色责任矩阵

| 文件夹 | 主负责人 | 协作者 | 核心职责 |
|--------|:---:|:---:|---------|
| `env/` | A | B | Gym环境封装、状态/动作空间定义、奖励函数设计；B负责TraCI数据采集逻辑 |
| `sumo_files/` | B | A | 路网构建、流量配置、信号配时、检测器配置；A提供算法所需数据格式说明 |
| `training/` | A | - | DQN/D3QN训练、知识蒸馏、模型量化、训练参数调优 |
| `server/` | C | A, D | WebSocket实时通信、RESTful API接口、状态推送协议定义 |
| `edge_deploy/` | C | A | Docker容器化部署、推理引擎集成、基准测试；A提供量化模型格式说明 |
| `visualization/` | D | A, B | 实验数据图表生成、对比实验报告、数据可视化；A/B提供实验数据 |
| `docs/` | A | B, C, D | 技术报告、接口文档、演示脚本；各角色撰写各自模块部分 |
| `models/` | A | C | 模型存储目录；C负责部署时模型加载路径配置 |

### 跨角色协作点

| 协作点 | 涉及角色 | 说明 |
|--------|:---:|------|
| TraCI数据采集 | A + B | A定义算法所需数据格式，B实现SUMO端数据采集 |
| 状态空间定义 | A + B | A定义26维状态空间结构，B提供各维度数据来源 |
| 模型部署接口 | A + C | A提供量化模型格式，C实现边缘推理引擎 |
| 实时数据推送 | C + D | C定义WebSocket协议，D实现Unity端数据接收 |
| 实验数据验证 | D + A + B | D生成可视化图表，A/B验证数据准确性 |