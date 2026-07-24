"""
交通信号控制强化学习环境（基于SUMO和gymnasium）

MDP设计说明：
1. 状态空间：每个进口道的排队长度 + 每个进口道的等待时间（一维向量）
2. 动作空间：4个离散动作（选择4个相位之一）
3. 奖励函数：所有车道的平均排队长度的负值

相位定义（4相位）：
- 动作0：南北直行（Phase 0）
- 动作1：南北左转（Phase 1）
- 动作2：东西直行（Phase 2）
- 动作3：东西左转（Phase 3）
"""

import os
import sys
import numpy as np
import gymnasium as gym
from gymnasium import spaces

# 添加SUMO工具路径
if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)
else:
    sys.exit("请设置SUMO_HOME环境变量")

import traci


class TrafficSignalEnv(gym.Env):
    """
    单交叉口交通信号控制环境
    
    状态空间（8维）：
    - [0:4]: 四个进口道的排队长度（停止车辆数）
    - [4:8]: 四个进口道的平均等待时间
    
    动作空间（4维离散）：
    - 0: 南北直行
    - 1: 南北左转
    - 2: 东西直行
    - 3: 东西左转
    
    奖励函数：
    - 基于所有车道的平均排队长度的负值
    - 排队越长，奖励越低
    """
    
    # 相位定义
    PHASE_NS_STRAIGHT = 0   # 南北直行
    PHASE_NS_LEFT = 1       # 南北左转
    PHASE_EW_STRAIGHT = 2   # 东西直行
    PHASE_EW_LEFT = 3       # 东西左转
    
    # 最小绿灯时间（秒）
    MIN_GREEN = 15
    
    def __init__(self, sumo_cfg_path, use_gui=False, max_steps=3600, delta_time=5):
        """
        初始化环境
        
        Args:
            sumo_cfg_path: SUMO配置文件路径
            use_gui: 是否使用GUI模式
            max_steps: 最大仿真步数
            delta_time: 每步仿真时间（秒）
        """
        self.sumo_cfg_path = sumo_cfg_path
        self.use_gui = use_gui
        self.max_steps = max_steps
        self.delta_time = delta_time
        self.current_step = 0
        self.sumo_running = False
        
        # 信号灯和车道信息
        self.tl_id = "J1"  # 默认信号灯ID
        self.lane_ids = []  # 四个进口道的车道ID
        
        # 状态空间：8维向量 [排队长度×4, 等待时间×4]
        self.observation_space = spaces.Box(
            low=0, high=np.inf, shape=(8,), dtype=np.float32
        )
        
        # 动作空间：4个离散动作
        self.action_space = spaces.Discrete(4)
        
        # 记录前一个动作（用于惩罚不必要的切换）
        self.prev_action = None
        
    def _start_sumo(self):
        """启动SUMO仿真"""
        if self.sumo_running:
            return
            
        sumo_binary = "sumo-gui" if self.use_gui else "sumo"
        traci.start([
            sumo_binary,
            "-c", self.sumo_cfg_path,
            "--no-step-log",
            "--no-warnings",
            "--time-to-teleport", "-1"
        ])
        self.sumo_running = True
        
        # 获取信号灯控制的车道
        self._init_lanes()
        
    def _init_lanes(self):
        """初始化车道信息"""
        # 获取信号灯控制的所有车道
        controlled_lanes = traci.trafficlight.getControlledLanes(self.tl_id)
        
        # 从四个方向各选择一个代表性车道
        # 车道格式: N_0, N_1, N_2, S_0, S_1, S_2, E_0, E_1, E_2, W_0, W_1, W_2
        lane_groups = {}
        for lane in controlled_lanes:
            # 提取方向前缀（N, S, E, W）
            direction = lane.split('_')[0]
            if direction not in lane_groups:
                lane_groups[direction] = []
            if lane not in lane_groups[direction]:
                lane_groups[direction].append(lane)
        
        # 从每个方向选择主车道（直行道，通常是_0）
        self.lane_ids = []
        for direction in ['N', 'S', 'E', 'W']:
            if direction in lane_groups:
                # 优先选择直行道（通常以_0结尾）
                for lane in lane_groups[direction]:
                    if lane.endswith('_0'):
                        self.lane_ids.append(lane)
                        break
                else:
                    # 如果没有_0车道，取第一个
                    self.lane_ids.append(lane_groups[direction][0])
        
        print(f"选择的车道: {self.lane_ids}")
        
    def _get_state(self):
        """
        获取当前状态
        
        返回8维向量：
        - [0:4]: 四个进口道的排队长度（停止车辆数）
        - [4:8]: 四个进口道的平均等待时间（秒）
        """
        state = np.zeros(8, dtype=np.float32)
        
        for i, lane in enumerate(self.lane_ids):
            # 排队长度：停止的车辆数
            queue_length = traci.lane.getLastStepHaltingNumber(lane)
            state[i] = queue_length
            
            # 等待时间：该车道上车辆的平均等待时间
            wait_time = traci.lane.getLastStepVehicleNumber(lane) * 5  # 简化估计
            state[4 + i] = wait_time
        
        return state
    
    def _calculate_reward(self, state, old_action, action):
        """
        计算奖励（v2优化版）
        
        奖励函数设计：
        r(s, a) = -avg_queue - switch_penalty - congestion_penalty
        
        组成部分：
        1. -avg_queue: 负平均排队长度（主要驱动）
        2. switch_penalty: 相位切换惩罚（0.1，仅当相位改变时）
        3. congestion_penalty: 拥堵惩罚（当排队超过阈值时额外惩罚）
        
        Args:
            state: 当前状态向量
            old_action: 上一步动作
            action: 当前执行的动作
            
        Returns:
            reward: 奖励值
        """
        # 获取排队长度（前4维）
        queues = state[:4]
        
        # 计算平均排队长度
        avg_queue = np.mean(queues)
        
        # 1. 主奖励：负平均排队长度
        reward = -avg_queue
        
        # 2. 切换惩罚：仅当相位改变时（0.1）
        if old_action is not None and action != old_action:
            reward -= 0.1  # 降低切换惩罚，从0.5改为0.1
        
        # 3. 拥堵惩罚：当排队超过阈值时给予额外负奖励
        # 排队超过5辆时开始惩罚，超过越多惩罚越重
        congestion_threshold = 5
        max_queue = np.max(queues)
        if max_queue > congestion_threshold:
            congestion_penalty = (max_queue - congestion_threshold) * 0.5
            reward -= congestion_penalty
        
        return reward
    
    def _apply_action(self, action):
        """
        应用动作（切换信号灯相位）
        
        Args:
            action: 0-3的整数，表示选择的相位
        """
        # 设置信号灯相位
        traci.trafficlight.setPhase(self.tl_id, action)
        self.prev_action = action
        
    def step(self, action):
        """
        执行一步仿真
        
        Args:
            action: 动作（0-3）
            
        Returns:
            state: 新状态
            reward: 奖励
            terminated: 是否终止
            truncated: 是否截断
            info: 额外信息
        """
        self.current_step += 1
        terminated = self.current_step >= self.max_steps
        
        # 保存当前动作（用于计算奖励中的切换惩罚）
        old_action = self.prev_action
        
        # 应用动作
        self._apply_action(action)
        
        # 推进仿真
        for _ in range(self.delta_time):
            traci.simulationStep()
        
        # 获取新状态和奖励
        state = self._get_state()
        reward = self._calculate_reward(state, old_action, action)
        
        # 额外信息
        info = {
            'step': self.current_step,
            'sim_time': traci.simulation.getTime(),
            'queue_length': np.sum(state[:4]),
            'avg_queue': np.mean(state[:4]),
            'reward': reward
        }
        
        if terminated:
            self.close()
            
        return state, reward, terminated, False, info
    
    def reset(self, seed=None, options=None):
        """
        重置环境
        
        Args:
            seed: 随机种子
            options: 其他选项
            
        Returns:
            state: 初始状态
            info: 额外信息
        """
        super().reset(seed=seed)
        
        # 关闭之前的连接
        if self.sumo_running:
            traci.close()
            self.sumo_running = False
            
        self.current_step = 0
        self.prev_action = None
        
        # 启动新的仿真
        self._start_sumo()
        state = self._get_state()
        
        return state, {}
    
    def close(self):
        """关闭环境"""
        if self.sumo_running:
            traci.close()
            self.sumo_running = False
    
    def render(self, mode='human'):
        """渲染环境"""
        if self.use_gui:
            traci.gui.screenshot("View #0", "screenshot.png")


# ==============================================
# MDP设计说明文档
# ==============================================
"""
MDP设计说明：

一、状态空间设计（8维）
---------------------
状态向量 s ∈ R^8，包含：
- s[0]: 北进口道排队长度（停止车辆数）
- s[1]: 南进口道排队长度（停止车辆数）
- s[2]: 东进口道排队长度（停止车辆数）
- s[3]: 西进口道排队长度（停止车辆数）
- s[4]: 北进口道平均等待时间（秒）
- s[5]: 南进口道平均等待时间（秒）
- s[6]: 东进口道平均等待时间（秒）
- s[7]: 西进口道平均等待时间（秒）

设计合理性：
1. 排队长度直接反映交通拥堵程度
2. 等待时间反映了车辆延误情况
3. 8维空间简洁有效，便于DQN学习

二、动作空间设计（4维离散）
-------------------------
动作 a ∈ {0, 1, 2, 3}，对应：
- a=0: 南北直行（Phase 0）
- a=1: 南北左转（Phase 1）
- a=2: 东西直行（Phase 2）
- a=3: 东西左转（Phase 3）

设计合理性：
1. 4相位覆盖了典型交叉口的所有转向需求
2. 离散动作空间适合DQN算法
3. 动作空间小，训练效率高

三、奖励函数设计
---------------
奖励函数 r(s, a) = -avg_queue - switch_penalty

其中：
- avg_queue: 所有车道的平均排队长度
- switch_penalty: 相位切换惩罚（0.5）

设计合理性：
1. 负平均排队长度直接优化目标——减少拥堵
2. 排队越长，奖励越低，激励智能体寻找最优配时
3. 切换惩罚避免频繁切换相位，提高安全性
4. 简单直观，训练收敛快
"""
