# 多路口交通信号控制扩展设计文档

## 一、设计目标

将当前单路口强化学习交通信号控制环境扩展到多路口场景（例如4×4网格，共20个路口），为最终赛题提交做准备。

## 二、路网设计方案

### 2.1 4×4网格路网结构

```
    N4      N3      N2      N1
    ↓       ↓       ↓       ↓
W4──J13──J14──J15──J16──E4
    ↓       ↓       ↓       ↓
W3──J09──J10──J11──J12──E3
    ↓       ↓       ↓       ↓
W2──J05──J06──J07──J08──E2
    ↓       ↓       ↓       ↓
W1──J01──J02──J03──J04──E1
    ↑       ↑       ↑       ↑
    S1      S2      S3      S4
```

### 2.2 路网文件扩展

#### 节点定义（nod.xml）

```xml
<?xml version="1.0" encoding="UTF-8"?>
<nodes>
    <!-- 边界节点 -->
    <node id="N1" x="0" y="0" type="priority"/>
    <node id="N2" x="500" y="0" type="priority"/>
    <node id="N3" x="1000" y="0" type="priority"/>
    <node id="N4" x="1500" y="0" type="priority"/>
    
    <node id="S1" x="0" y="1500" type="priority"/>
    <node id="S2" x="500" y="1500" type="priority"/>
    <node id="S3" x="1000" y="1500" type="priority"/>
    <node id="S4" x="1500" y="1500" type="priority"/>
    
    <node id="E1" x="1500" y="0" type="priority"/>
    <node id="E2" x="1500" y="500" type="priority"/>
    <node id="E3" x="1500" y="1000" type="priority"/>
    <node id="E4" x="1500" y="1500" type="priority"/>
    
    <node id="W1" x="0" y="0" type="priority"/>
    <node id="W2" x="0" y="500" type="priority"/>
    <node id="W3" x="0" y="1000" type="priority"/>
    <node id="W4" x="0" y="1500" type="priority"/>
    
    <!-- 内部路口节点（信号控制） -->
    <node id="J01" x="0" y="375" type="traffic_light"/>
    <node id="J02" x="500" y="375" type="traffic_light"/>
    <node id="J03" x="1000" y="375" type="traffic_light"/>
    <node id="J04" x="1500" y="375" type="traffic_light"/>
    
    <node id="J05" x="0" y="875" type="traffic_light"/>
    <node id="J06" x="500" y="875" type="traffic_light"/>
    <node id="J07" x="1000" y="875" type="traffic_light"/>
    <node id="J08" x="1500" y="875" type="traffic_light"/>
    
    <node id="J09" x="0" y="1250" type="traffic_light"/>
    <node id="J10" x="500" y="1250" type="traffic_light"/>
    <node id="J11" x="1000" y="1250" type="traffic_light"/>
    <node id="J12" x="1500" y="1250" type="traffic_light"/>
    
    <node id="J13" x="0" y="625" type="traffic_light"/>
    <node id="J14" x="500" y="625" type="traffic_light"/>
    <node id="J15" x="1000" y="625" type="traffic_light"/>
    <node id="J16" x="1500" y="625" type="traffic_light"/>
</nodes>
```

#### 边定义（edg.xml）

```xml
<?xml version="1.0" encoding="UTF-8"?>
<edges>
    <!-- 南北方向道路 -->
    <edge id="N1" from="N1" to="J01" priority="1" numLanes="3" speed="12"/>
    <edge id="-N1" from="J01" to="N1" priority="1" numLanes="3" speed="12"/>
    
    <edge id="N2" from="N2" to="J02" priority="1" numLanes="3" speed="12"/>
    <edge id="-N2" from="J02" to="N2" priority="1" numLanes="3" speed="12"/>
    
    <!-- 东西方向道路 -->
    <edge id="W1" from="W1" to="J01" priority="1" numLanes="3" speed="12"/>
    <edge id="-W1" from="J01" to="W1" priority="1" numLanes="3" speed="12"/>
    
    <!-- 内部连接道路 -->
    <edge id="J01-J05" from="J01" to="J05" priority="1" numLanes="3" speed="12"/>
    <edge id="J05-J01" from="J05" to="J01" priority="1" numLanes="3" speed="12"/>
    
    <edge id="J01-J02" from="J01" to="J02" priority="1" numLanes="3" speed="12"/>
    <edge id="J02-J01" from="J02" to="J01" priority="1" numLanes="3" speed="12"/>
    
    <!-- ... 其他内部连接道路 ... -->
</edges>
```

## 三、状态空间设计

### 3.1 方案一：独立状态（Multi-Agent）

每个路口维护独立的状态向量，每个智能体只观察自己路口的状态。

```python
# 每个路口的状态（8维）
state_per_intersection = [
    N_queue,  # 北进口道排队长度
    S_queue,  # 南进口道排队长度
    E_queue,  # 东进口道排队长度
    W_queue,  # 西进口道排队长度
    N_wait,   # 北进口道等待时间
    S_wait,   # 南进口道等待时间
    E_wait,   # 东进口道等待时间
    W_wait    # 西进口道等待时间
]

# 16个路口的总状态维度：16 × 8 = 128维
```

### 3.2 方案二：全局状态（Centralized Agent）

单个智能体观察所有路口的状态。

```python
# 全局状态：所有路口的状态串联
global_state = np.concatenate([
    intersection_1_state,
    intersection_2_state,
    ...,
    intersection_16_state
])

# 总状态维度：16 × 8 = 128维
```

### 3.3 方案三：邻域状态（Partial Observation）

每个智能体观察自己和相邻路口的状态。

```python
# 中心路口（J06）观察自己 + 上下左右4个邻居
state_with_neighbors = np.concatenate([
    J06_state,      # 自己
    J02_state,      # 上方
    J10_state,      # 下方
    J05_state,      # 左方
    J07_state       # 右方
])

# 每个智能体状态维度：5 × 8 = 40维
```

**推荐方案：方案三（邻域状态）**
- 平衡了信息完整性和状态空间复杂度
- 符合实际交通信号控制场景（相邻路口影响最大）
- 便于扩展到更多路口

## 四、动作空间设计

### 4.1 方案一：独立动作（Decentralized）

每个路口独立决策，选择自己的相位。

```python
# 每个路口4个动作（4相位）
action_space_per_intersection = spaces.Discrete(4)

# 16个路口的总动作空间：16 × 4 = 64维离散空间
# 或使用MultiDiscrete：MultiDiscrete([4, 4, ..., 4])
```

### 4.2 方案二：联合动作（Centralized）

单个智能体为所有路口选择相位。

```python
# 联合动作：每个路口选一个相位
action_space = spaces.MultiDiscrete([4] * 16)

# 动作空间大小：4^16 ≈ 43亿（太大，不可行）
```

### 4.3 方案三：分层动作（Hierarchical）

上层策略决定协调模式，下层策略执行具体相位切换。

```python
# 上层动作：协调模式（绿波方向等）
high_level_action = spaces.Discrete(4)  # N-S绿波, E-W绿波, 平衡, 自适应

# 下层动作：每个路口独立决策
low_level_action = spaces.MultiDiscrete([4] * 16)
```

**推荐方案：方案一（独立动作）**
- 实现简单，训练效率高
- 每个智能体只需关注自己的路口
- 可以通过奖励函数间接实现协调

## 五、奖励函数设计

### 5.1 局部奖励（独立优化）

每个路口的奖励仅基于自身排队长度。

```python
def calculate_local_reward(self, state):
    queues = state[:4]
    avg_queue = np.mean(queues)
    reward = -avg_queue
    
    # 切换惩罚
    if self.prev_action is not None and action != self.prev_action:
        reward -= 0.1
    
    return reward
```

### 5.2 全局奖励（联合优化）

所有路口共享一个全局奖励，鼓励整体最优。

```python
def calculate_global_reward(all_states):
    total_queue = 0
    for state in all_states:
        queues = state[:4]
        total_queue += np.sum(queues)
    
    avg_queue = total_queue / (len(all_states) * 4)
    reward = -avg_queue
    
    return reward
```

### 5.3 混合奖励（局部+全局）

```python
def calculate_hybrid_reward(local_state, global_states, alpha=0.7):
    # 局部奖励
    local_queues = local_state[:4]
    local_avg_queue = np.mean(local_queues)
    local_reward = -local_avg_queue
    
    # 全局奖励
    total_queue = sum(np.sum(state[:4]) for state in global_states)
    global_avg_queue = total_queue / (len(global_states) * 4)
    global_reward = -global_avg_queue
    
    # 混合
    reward = alpha * local_reward + (1 - alpha) * global_reward
    
    return reward
```

**推荐方案：混合奖励**
- alpha=0.7：70%局部 + 30%全局
- 既保证单个路口性能，又鼓励全局协调

## 六、算法选择

### 6.1 Multi-Agent DQN（MADQN）

每个路口一个DQN智能体，独立训练。

```python
# 伪代码
agents = []
for i in range(num_intersections):
    agent = DQN(
        "MlpPolicy",
        env[i],
        learning_rate=1e-4,
        ...
    )
    agents.append(agent)

# 训练
for timestep in range(total_timesteps):
    for i, agent in enumerate(agents):
        obs = get_observation(i)
        action, _ = agent.predict(obs)
        new_obs, reward, done, info = env.step(i, action)
        agent.learn(...)
```

### 6.2 Independent Q-Learning（IQL）

完全独立的Q学习，不考虑其他智能体的影响。

### 6.3 Centralized Training with Decentralized Execution（CTDE）

集中训练、分散执行框架。

```python
# 训练时：中心化评估器观察全局状态
critic = Critic(global_state_dim, num_actions)

# 执行时：每个智能体独立决策
for agent in agents:
    action = agent.predict(local_observation)
```

**推荐方案：MADQN + CTDE混合**
- 训练效率高
- 可以学习到协调策略

## 七、环境修改方案

### 7.1 多路口环境类

```python
class MultiIntersectionEnv(gym.Env):
    """
    多路口交通信号控制环境
    
    Attributes:
        num_intersections: 路口数量
        tl_ids: 信号灯ID列表
        lane_ids_per_tl: 每个信号灯控制的车道列表
    """
    
    def __init__(self, sumo_cfg_path, num_intersections=16, **kwargs):
        self.num_intersections = num_intersections
        self.tl_ids = [f"J{i:02d}" for i in range(1, num_intersections + 1)]
        
        # 状态空间：每个路口8维，共 num_intersections × 8 维
        self.observation_space = spaces.Box(
            low=0, high=np.inf, 
            shape=(num_intersections * 8,), 
            dtype=np.float32
        )
        
        # 动作空间：每个路口4个动作，使用MultiDiscrete
        self.action_space = spaces.MultiDiscrete([4] * num_intersections)
        
        # 其他初始化...
    
    def _get_state(self):
        """获取所有路口的状态"""
        state = np.zeros(self.num_intersections * 8, dtype=np.float32)
        
        for i, tl_id in enumerate(self.tl_ids):
            # 获取该路口的状态
            controlled_lanes = traci.trafficlight.getControlledLanes(tl_id)
            # ...提取排队长度和等待时间...
            
            state[i * 8:(i + 1) * 8] = local_state
        
        return state
    
    def step(self, actions):
        """
        执行一步仿真
        
        Args:
            actions: 所有路口的动作列表/数组
        """
        # 应用所有动作
        for i, tl_id in enumerate(self.tl_ids):
            traci.trafficlight.setPhase(tl_id, actions[i])
        
        # 推进仿真
        for _ in range(self.delta_time):
            traci.simulationStep()
        
        # 获取新状态和奖励
        state = self._get_state()
        reward = self._calculate_reward(state, actions)
        
        return state, reward, terminated, False, info
```

### 7.2 独立路口环境列表

```python
class IntersectionEnv(gym.Env):
    """单个路口环境"""
    
    def __init__(self, sumo_cfg_path, tl_id, **kwargs):
        self.tl_id = tl_id
        # ... 初始化 ...

# 创建多个独立环境
envs = []
for tl_id in tl_ids:
    env = IntersectionEnv(sumo_cfg_path, tl_id)
    envs.append(env)
```

## 八、扩展步骤

### 步骤1：生成多路口路网

```bash
# 创建nod.xml和edg.xml
# 使用netconvert生成net.xml
netconvert \
    --node-files=xiongan_multi.nod.xml \
    --edge-files=xiongan_multi.edg.xml \
    --output-file=xiongan_multi.net.xml
```

### 步骤2：配置流量

```xml
<!-- 在rou.xml中添加更多路线和流量 -->
<route id="N1-J01-J05" edges="N1 J01-J05"/>
<flow id="N1_flow" route="N1-J01-J05" type="car" begin="0" end="3600" probability="0.05"/>
```

### 步骤3：修改环境代码

创建 `MultiIntersectionEnv` 类，支持多路口状态和动作。

### 步骤4：修改训练脚本

```python
# 修改train_dqn.py支持多智能体
from env.multi_env import MultiIntersectionEnv

env = MultiIntersectionEnv(
    sumo_cfg_path=sumo_cfg_path,
    num_intersections=16
)

# 使用MultiDiscrete动作空间的策略
model = DQN(
    "MlpPolicy",
    env,
    ...
)
```

## 九、预期挑战

1. **状态空间爆炸**：16个路口 × 8维 = 128维状态空间
2. **训练效率**：需要更多训练步数（100万+）
3. **协调问题**：如何让多个智能体协调工作
4. **计算资源**：多路口仿真速度较慢

## 十、优化方向

1. **状态压缩**：使用CNN或图神经网络提取空间特征
2. **课程学习**：先训练单路口，再扩展到多路口
3. **注意力机制**：让智能体关注关键路口
4. **并行训练**：使用多个GPU并行训练不同路口的智能体

## 十一、代码骨架

### 多路口环境模板

```python
# env/multi_env.py
import numpy as np
import gymnasium as gym
from gymnasium import spaces

class MultiIntersectionEnv(gym.Env):
    def __init__(self, sumo_cfg_path, num_intersections=16):
        self.num_intersections = num_intersections
        self.tl_ids = [f"J{i:02d}" for i in range(1, num_intersections + 1)]
        
        self.observation_space = spaces.Box(
            low=0, high=np.inf,
            shape=(num_intersections * 8,),
            dtype=np.float32
        )
        
        self.action_space = spaces.MultiDiscrete([4] * num_intersections)
        
        # ... 其他初始化 ...
    
    def step(self, actions):
        # ... 实现多路口step ...
        pass
    
    def reset(self):
        # ... 实现reset ...
        pass
    
    def close(self):
        # ... 实现close ...
        pass
```

### 多智能体训练模板

```python
# training/train_multi_dqn.py
from stable_baselines3 import DQN
from env.multi_env import MultiIntersectionEnv

env = MultiIntersectionEnv(
    sumo_cfg_path="sumo_files/xiongan_multi.sumocfg",
    num_intersections=16
)

model = DQN(
    "MlpPolicy",
    env,
    learning_rate=1e-4,
    buffer_size=500000,
    learning_starts=5000,
    batch_size=128,
    gamma=0.99,
    target_update_interval=5000,
    exploration_fraction=0.2,
    verbose=1,
    tensorboard_log="./logs_multi/"
)

model.learn(
    total_timesteps=1000000,
    progress_bar=True
)

model.save("./models_multi/dqn_multi_final.zip")
```
