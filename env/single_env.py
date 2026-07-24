"""
单路口交通信号控制Gym环境（基于SUMO和gymnasium）

目标：基于demo_2路网，快速测试DQN算法和奖励函数

状态空间（22维）：
- [0:4]: 排队长度（归一化，N/S/E/W）
- [4:8]: 平均等待时间（归一化，N/S/E/W）
- [8:12]: 车道占有率（N/S/E/W）
- [12:16]: 溢出风险（N/S/E/W）
- [16:20]: 当前相位One-Hot编码
- [20:22]: 时间特征（sin/cos）

动作空间（4维离散）：
- 0: 南北直行（相位0）
- 1: 南北左转（相位1）
- 2: 东西直行（相位2）
- 3: 东西左转（相位3）

奖励函数（V3，窄路密网专用）：
- reward = - (1.0*avg_queue + 0.5*max_queue + 0.3*avg_wait + 2.0*overflow_penalty + 0.2*switch_cost + 0.1*balance_penalty)
- avg_queue: 平均排队长度（主要拥堵指标）
- max_queue: 最大排队长度（尖峰惩罚）
- avg_wait: 平均等待时间（公平性）
- overflow_penalty: 溢出惩罚（防死锁关键）
- switch_cost: 切换成本（减少不必要切换）
- balance_penalty: 均衡惩罚（鼓励各方向排队均衡）

最小绿灯约束：切换相位后至少维持15秒（3个step，delta_time=5）
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

# 导入全局状态提取模块
from env.global_state import get_global_state, DEBUG
# 导入奖励函数模块
from env.reward_functions import compute_reward


class SingleIntersectionEnv(gym.Env):
    """
    单路口交通信号控制Gym环境
    
    配置：
    - 配置文件：赛题资料/路口仿真案例/sumo工程_路口2/demo_2.sumocfg
    - 仿真步长：delta_time = 5秒
    - 最大步数：max_steps = 720（对应1小时仿真）
    """
    
    # 相位定义
    PHASE_NS_STRAIGHT = 0   # 南北直行
    PHASE_NS_LEFT = 1       # 南北左转
    PHASE_EW_STRAIGHT = 2   # 东西直行
    PHASE_EW_LEFT = 3       # 东西左转
    
    # 最小绿灯时间（秒）和对应的步数（delta_time=5时为3步）
    MIN_GREEN_TIME = 15
    MIN_GREEN_STEPS = 3
    
    # 默认配置文件路径
    DEFAULT_SUMO_CFG = "赛题资料/路口仿真案例/sumo工程_路口2/demo_2.sumocfg"
    
    def __init__(self, sumo_cfg_path=None, use_gui=False, max_steps=720, delta_time=5):
        """
        初始化环境
        
        Args:
            sumo_cfg_path: SUMO配置文件路径（默认为demo_2.sumocfg）
            use_gui: 是否使用GUI模式
            max_steps: 最大仿真步数（默认720，对应1小时）
            delta_time: 每步仿真时间（默认5秒）
        """
        super().__init__()
        
        self.sumo_cfg_path = sumo_cfg_path or self.DEFAULT_SUMO_CFG
        self.use_gui = use_gui
        self.max_steps = max_steps
        self.delta_time = delta_time
        self.current_step = 0
        self.sumo_running = False
        
        # 信号灯信息
        self.tl_id = "J1"
        
        # 动作历史（用于最小绿灯约束）
        self.previous_action = None
        self.green_steps_count = 0  # 当前相位已维持的步数
        
        # 状态空间：22维，范围见注释
        self.observation_space = spaces.Box(
            low=np.array([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, -1, -1]),
            high=np.array([1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]),
            shape=(22,),
            dtype=np.float32
        )
        
        # 动作空间：4个离散动作
        self.action_space = spaces.Discrete(4)
    
    def _get_state(self):
        """
        获取当前状态（J01的22维特征）
        
        Returns:
            np.ndarray: 22维状态向量
        """
        # 获取全局状态（1个路口，22维）
        global_state = get_global_state(num_intersections=1)
        # 取前22维（J01的特征）
        state = global_state[:22].astype(np.float32)
        return state
    
    def _apply_action(self, action):
        """
        应用动作（设置信号灯相位）
        
        Args:
            action: 动作索引（0-3）
        """
        # 直接设置相位
        traci.trafficlight.setPhase(self.tl_id, action)
    
    def _calculate_reward(self, state, action):
        """
        计算奖励（使用V3版本）
        
        Args:
            state: 当前状态（22维）
            action: 当前动作
            
        Returns:
            tuple: (reward, avg_queue, breakdown)
        """
        # 使用V3奖励函数
        reward, breakdown = compute_reward(state, action, self.previous_action)
        
        # 提取平均排队长度（用于info）
        avg_queue = breakdown.get('avg_queue', np.mean(state[0:4]))
        
        return reward, avg_queue, breakdown
    
    def _check_min_green(self, action):
        """
        检查最小绿灯约束
        
        Args:
            action: 欲执行的动作
            
        Returns:
            bool: 是否允许切换相位
        """
        # 如果之前没有动作，允许切换
        if self.previous_action is None:
            return True
        
        # 如果动作相同，允许（继续当前相位）
        if action == self.previous_action:
            return True
        
        # 如果当前相位已维持足够步数，允许切换
        if self.green_steps_count >= self.MIN_GREEN_STEPS:
            return True
        
        # 否则不允许切换，保持原动作
        return False
    
    def reset(self, seed=None, options=None):
        """
        重置环境
        
        Args:
            seed: 随机种子（SUMO本身确定性，可忽略）
            options: 额外选项
            
        Returns:
            tuple: (obs, info)
        """
        super().reset(seed=seed)
        
        # 关闭旧连接（如果存在）
        if self.sumo_running:
            try:
                traci.close()
            except Exception:
                pass
        
        # 启动SUMO
        sumo_cmd = [
            "sumo-gui" if self.use_gui else "sumo",
            "-c", self.sumo_cfg_path,
            "--no-warnings",
            "--time-to-teleport", "-1"
        ]
        
        if self.use_gui:
            sumo_cmd.append("--start")
            sumo_cmd.append("--delay")
            sumo_cmd.append("50")
        
        traci.start(sumo_cmd)
        
        self.sumo_running = True
        self.current_step = 0
        self.previous_action = None
        self.green_steps_count = 0
        
        # 获取初始状态
        obs = self._get_state()
        
        # 获取当前相位
        phase = traci.trafficlight.getPhase(self.tl_id)
        
        info = {
            'queue_length': float(np.mean(obs[0:4])),
            'avg_queue': float(np.mean(obs[0:4])),
            'action': -1,
            'phase': phase
        }
        
        return obs, info
    
    def step(self, action):
        """
        执行一步
        
        Args:
            action: 动作索引（0-3）
            
        Returns:
            tuple: (obs, reward, terminated, truncated, info)
        """
        # 检查最小绿灯约束
        if not self._check_min_green(action):
            # 不允许切换，使用之前的动作
            action = self.previous_action
        
        # 应用动作
        self._apply_action(action)
        
        # 推进仿真delta_time秒（每步5秒）
        for _ in range(self.delta_time):
            traci.simulationStep()
        
        # 更新步数计数器
        self.current_step += 1
        
        # 更新绿灯步数计数
        if action == self.previous_action:
            self.green_steps_count += 1
        else:
            self.green_steps_count = 1
        
        # 保存当前动作作为历史
        self.previous_action = action
        
        # 获取新状态
        obs = self._get_state()
        
        # 计算奖励
        reward, avg_queue, breakdown = self._calculate_reward(obs, action)
        
        # 检查终止条件
        terminated = False  # 通常不使用终止，用截断
        truncated = self.current_step >= self.max_steps
        
        # 获取当前相位
        phase = traci.trafficlight.getPhase(self.tl_id)
        
        # 构建info（包含奖励分解）
        info = {
            'queue_length': float(np.mean(obs[0:4])),
            'avg_queue': float(avg_queue),
            'action': action,
            'phase': phase,
            'step': self.current_step,
            **breakdown  # 添加奖励分解详情
        }
        
        # 调试输出
        if DEBUG and self.current_step % 20 == 0:
            print(f"[DEBUG] Step {self.current_step}: action={action}, phase={phase}, "
                  f"avg_queue={avg_queue:.4f}, reward={reward:.4f}")
        
        return obs, reward, terminated, truncated, info
    
    def close(self):
        """
        关闭环境
        """
        if self.sumo_running:
            try:
                traci.close()
                self.sumo_running = False
            except Exception as e:
                print(f"关闭环境时出错: {e}")
    
    def render(self, mode='human'):
        """
        渲染（仅在GUI模式下有效）
        
        Args:
            mode: 渲染模式（'human'或'rgb_array'）
        """
        if mode == 'rgb_array' and self.use_gui:
            # 尝试获取截图（需要额外配置）
            try:
                screenshot = traci.gui.screenshot('View #0', 'screenshot.png')
                return screenshot
            except Exception:
                pass
        
        # 默认不做任何操作
        pass


# ==============================================
# 测试主函数
# ==============================================
if __name__ == "__main__":
    print("=" * 70)
    print("🚀 测试SingleIntersectionEnv（随机策略）")
    print("=" * 70)
    
    # 创建环境（非GUI模式，快速测试）
    env = SingleIntersectionEnv(use_gui=False)
    
    # 运行随机策略100步
    total_reward = 0.0
    total_queue = 0.0
    obs, info = env.reset()
    
    print(f"初始状态: 排队={info['avg_queue']:.4f}, 相位={info['phase']}")
    
    for step in range(100):
        # 随机选择动作
        action = env.action_space.sample()
        
        # 执行一步
        obs, reward, terminated, truncated, info = env.step(action)
        
        # 累计统计
        total_reward += reward
        total_queue += info['avg_queue']
        
        # 每20步打印一次
        if (step + 1) % 20 == 0:
            print(f"步骤 {step+1:3d}: 动作={action}, 相位={info['phase']}, "
                  f"排队={info['avg_queue']:.4f}, 奖励={reward:.4f}")
        
        if terminated or truncated:
            break
    
    # 统计结果
    avg_reward = total_reward / (step + 1)
    avg_queue = total_queue / (step + 1)
    
    print("\n" + "=" * 70)
    print(f"测试结果（随机策略，{step+1}步）:")
    print(f"平均奖励: {avg_reward:.4f}")
    print(f"平均排队长度: {avg_queue:.4f}")
    print(f"最终步数: {step+1}")
    print("=" * 70)
    
    # 关闭环境
    env.close()
    print("\n✅ 测试完成！")
