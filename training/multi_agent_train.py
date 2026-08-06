"""
多路口交通信号控制训练框架（独立DQN + 参数共享 + 共享经验回放）

核心设计：
- 所有20个路口使用同一个DQN网络（参数共享）
- 每个路口独立决策（22维输入，4维输出）
- 经验存储在共享的回放缓冲区中
- 训练时采样不同路口经验混合更新网络

适用场景：雄安新区20路口窄路密网

训练流程：
1. 启动SUMO仿真，获取所有信号灯ID
2. 重置环境，获取全局状态并按路口切片
3. 每个路口独立ε-贪婪选择动作
4. 批量设置所有路口相位，推进仿真
5. 获取新状态，计算每个路口奖励，存入buffer
6. 每隔一定步数，从buffer采样批量更新网络
7. 探索率从1.0线性衰减至0.01
"""

import os
import sys
import numpy as np
import random
import json
from datetime import datetime

# 添加SUMO工具路径
if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)
else:
    sys.exit("请设置SUMO_HOME环境变量")

import traci

# 导入项目模块
from env.global_state import get_global_state, DEBUG
from env.reward_functions import compute_reward_v3

try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    USE_TORCH = True
except ImportError:
    print("⚠️ 未安装PyTorch，使用numpy实现简单网络")
    USE_TORCH = False


class ReplayBuffer:
    """
    共享经验回放缓冲区
    
    存储格式：(state, action, reward, next_state, done, agent_id)
    支持批量采样和随机混合不同agent的经验
    """
    
    def __init__(self, capacity=500000):
        """
        初始化缓冲区
        
        Args:
            capacity: 缓冲区容量
        """
        self.capacity = capacity
        self.buffer = []
        self.position = 0
    
    def add(self, state, action, reward, next_state, done, agent_id):
        """
        添加一条经验
        
        Args:
            state: 22维状态向量
            action: 动作索引（0-3）
            reward: 奖励值
            next_state: 22维下一状态向量
            done: 是否终止
            agent_id: 智能体ID（路口ID）
        """
        if len(self.buffer) < self.capacity:
            self.buffer.append(None)
        
        self.buffer[self.position] = (
            state.copy(), action, reward, next_state.copy(), done, agent_id
        )
        self.position = (self.position + 1) % self.capacity
    
    def sample(self, batch_size):
        """
        采样一批经验
        
        Args:
            batch_size: 批大小
            
        Returns:
            tuple: (states, actions, rewards, next_states, dones, agent_ids)
        """
        batch = random.sample(self.buffer, min(batch_size, len(self.buffer)))
        
        states = np.array([exp[0] for exp in batch], dtype=np.float32)
        actions = np.array([exp[1] for exp in batch], dtype=np.int64)
        rewards = np.array([exp[2] for exp in batch], dtype=np.float32)
        next_states = np.array([exp[3] for exp in batch], dtype=np.float32)
        dones = np.array([exp[4] for exp in batch], dtype=np.float32)
        agent_ids = [exp[5] for exp in batch]
        
        return states, actions, rewards, next_states, dones, agent_ids
    
    def __len__(self):
        return len(self.buffer)


class SharedDQN:
    """
    共享DQN网络（参数共享，所有路口使用同一网络）
    
    输入：22维单路口状态
    输出：4维Q值（4个相位）
    """
    
    def __init__(self, state_dim=22, action_dim=4, hidden_dim=256, lr=1e-4):
        """
        初始化共享DQN网络
        
        Args:
            state_dim: 状态维度（默认22）
            action_dim: 动作维度（默认4）
            hidden_dim: 隐藏层维度（默认256）
            lr: 学习率（默认1e-4）
        """
        self.state_dim = state_dim
        self.action_dim = action_dim
        
        if USE_TORCH:
            # PyTorch实现
            self.q_net = nn.Sequential(
                nn.Linear(state_dim, hidden_dim),
                nn.ReLU(),
                nn.Linear(hidden_dim, hidden_dim // 2),
                nn.ReLU(),
                nn.Linear(hidden_dim // 2, action_dim)
            )
            
            self.target_q_net = nn.Sequential(
                nn.Linear(state_dim, hidden_dim),
                nn.ReLU(),
                nn.Linear(hidden_dim, hidden_dim // 2),
                nn.ReLU(),
                nn.Linear(hidden_dim // 2, action_dim)
            )
            
            self.target_q_net.load_state_dict(self.q_net.state_dict())
            self.optimizer = optim.Adam(self.q_net.parameters(), lr=lr)
            self.criterion = nn.MSELoss()
        else:
            # numpy实现（简单网络）
            self.weights = {
                'w1': np.random.randn(state_dim, hidden_dim) * 0.01,
                'b1': np.zeros(hidden_dim),
                'w2': np.random.randn(hidden_dim, action_dim) * 0.01,
                'b2': np.zeros(action_dim)
            }
            self.lr = lr
    
    def forward(self, state):
        """
        前向传播
        
        Args:
            state: 状态向量（22维）
            
        Returns:
            np.ndarray or torch.Tensor: 4维Q值
        """
        if USE_TORCH:
            if not isinstance(state, torch.Tensor):
                state = torch.tensor(state, dtype=torch.float32)
            return self.q_net(state)
        else:
            h = np.maximum(0, np.dot(state, self.weights['w1']) + self.weights['b1'])
            q = np.dot(h, self.weights['w2']) + self.weights['b2']
            return q
    
    def act(self, state, epsilon=0.0):
        """
        ε-贪婪动作选择
        
        Args:
            state: 22维状态向量
            epsilon: 探索率
            
        Returns:
            int: 动作索引（0-3）
        """
        if random.random() < epsilon:
            return random.randint(0, self.action_dim - 1)
        
        q_values = self.forward(state)
        if USE_TORCH:
            return q_values.argmax().item()
        else:
            return np.argmax(q_values)
    
    def update(self, buffer, batch_size=64, gamma=0.99):
        """
        更新网络参数
        
        Args:
            buffer: 经验回放缓冲区
            batch_size: 批大小
            gamma: 折扣因子
            
        Returns:
            float: 损失值
        """
        if len(buffer) < batch_size:
            return 0.0
        
        states, actions, rewards, next_states, dones, _ = buffer.sample(batch_size)
        
        if USE_TORCH:
            states = torch.tensor(states, dtype=torch.float32)
            actions = torch.tensor(actions, dtype=torch.long)
            rewards = torch.tensor(rewards, dtype=torch.float32)
            next_states = torch.tensor(next_states, dtype=torch.float32)
            dones = torch.tensor(dones, dtype=torch.float32)
            
            # 当前Q值
            current_q = self.q_net(states).gather(1, actions.unsqueeze(1)).squeeze(1)
            
            # 目标Q值
            next_q = self.target_q_net(next_states).max(1)[0].detach()
            target_q = rewards + gamma * next_q * (1 - dones)
            
            # 计算损失
            loss = self.criterion(current_q, target_q)
            
            # 反向传播
            self.optimizer.zero_grad()
            loss.backward()
            self.optimizer.step()
            
            return loss.item()
        else:
            # numpy实现（简单梯度下降）
            loss = 0.0
            for i in range(batch_size):
                state = states[i]
                action = actions[i]
                reward = rewards[i]
                next_state = next_states[i]
                done = dones[i]
                
                # 当前Q值
                q = self.forward(state)
                current_q = q[action]
                
                # 目标Q值
                next_q = self.forward(next_state)
                target_q = reward + gamma * np.max(next_q) * (1 - done)
                
                # 更新权重（简单实现）
                error = target_q - current_q
                h = np.maximum(0, np.dot(state, self.weights['w1']) + self.weights['b1'])
                
                # 更新第二层
                self.weights['w2'][:, action] += self.lr * error * h
                self.weights['b2'][action] += self.lr * error
                
                # 更新第一层（链式法则简化版）
                grad_h = np.zeros_like(h)
                grad_h[:] = error * self.weights['w2'][:, action]
                grad_h *= (h > 0)
                self.weights['w1'][:, :] += self.lr * np.outer(state, grad_h)
                self.weights['b1'][:] += self.lr * grad_h
                
                loss += error ** 2
            
            return loss / batch_size
    
    def update_target_network(self):
        """
        更新目标网络
        """
        if USE_TORCH:
            self.target_q_net.load_state_dict(self.q_net.state_dict())
        else:
            # numpy实现：复制权重
            self.target_weights = {k: v.copy() for k, v in self.weights.items()}
    
    def save(self, path):
        """
        保存模型
        
        Args:
            path: 保存路径
        """
        if USE_TORCH:
            torch.save(self.q_net.state_dict(), path)
        else:
            np.savez(path, **self.weights)
        print(f"模型已保存到: {path}")
    
    def load(self, path):
        """
        加载模型
        
        Args:
            path: 模型路径
        """
        if USE_TORCH:
            self.q_net.load_state_dict(torch.load(path))
            self.target_q_net.load_state_dict(self.q_net.state_dict())
        else:
            data = np.load(path, allow_pickle=True)
            self.weights = {k: data[k] for k in data.keys()}
        print(f"模型已从: {path} 加载")


class MultiIntersectionEnv:
    """
    多路口SUMO环境包装（提供多智能体接口）
    
    功能：
    - 启动/关闭SUMO仿真
    - 获取所有信号灯ID
    - 重置环境，返回各路口状态
    - 执行动作，推进仿真，收集奖励
    """
    
    def __init__(self, sumo_cfg, num_intersections=20, use_gui=False, delta_time=5, max_steps=720):
        """
        初始化多路口环境
        
        Args:
            sumo_cfg: SUMO配置文件路径
            num_intersections: 路口数量（默认20）
            use_gui: 是否使用GUI模式
            delta_time: 每步仿真时间（默认5秒）
            max_steps: 最大仿真步数（默认720）
        """
        self.sumo_cfg = sumo_cfg
        self.num_intersections = num_intersections
        self.use_gui = use_gui
        self.delta_time = delta_time
        self.max_steps = max_steps
        
        self.current_step = 0
        self.sumo_running = False
        self.tl_ids = []  # 信号灯ID列表
        self.previous_actions = {}  # 各路口上一步动作
        
        # 最小绿灯约束（15秒 = 3个step）
        self.min_green_steps = 3
        self.green_steps_count = {}  # 各路口当前相位已维持的步数
    
    def _start_sumo(self):
        """
        启动SUMO仿真
        """
        sumo_cmd = [
            "sumo-gui" if self.use_gui else "sumo",
            "-c", self.sumo_cfg,
            "--no-warnings",
            "--time-to-teleport", "-1"
        ]
        
        if self.use_gui:
            sumo_cmd.append("--start")
            sumo_cmd.append("--delay")
            sumo_cmd.append("50")
        
        traci.start(sumo_cmd)
        self.sumo_running = True
        
        # 获取所有信号灯ID
        self.tl_ids = traci.trafficlight.getIDList()
        
        # 如果实际信号灯数量少于指定数量，使用实际数量
        if len(self.tl_ids) < self.num_intersections:
            print(f"警告：实际信号灯数量({len(self.tl_ids)})少于指定数量({self.num_intersections})")
            self.num_intersections = len(self.tl_ids)
    
    def reset(self):
        """
        重置环境
        
        Returns:
            dict: {tl_id: obs} 各路口状态字典
        """
        # 关闭旧连接
        if self.sumo_running:
            try:
                traci.close()
            except Exception:
                pass
        
        # 启动新仿真
        self._start_sumo()
        
        self.current_step = 0
        self.previous_actions = {tl_id: None for tl_id in self.tl_ids}
        self.green_steps_count = {tl_id: 0 for tl_id in self.tl_ids}
        
        # 获取全局状态并按路口切片
        global_state = get_global_state(num_intersections=self.num_intersections)
        obs_dict = {}
        
        for i, tl_id in enumerate(self.tl_ids):
            start = i * 22
            end = (i + 1) * 22
            obs_dict[tl_id] = global_state[start:end]
        
        return obs_dict
    
    def _check_min_green(self, tl_id, action):
        """
        检查最小绿灯约束
        
        Args:
            tl_id: 信号灯ID
            action: 欲执行的动作
            
        Returns:
            bool: 是否允许切换相位
        """
        prev_action = self.previous_actions[tl_id]
        
        if prev_action is None:
            return True
        
        if action == prev_action:
            return True
        
        if self.green_steps_count[tl_id] >= self.min_green_steps:
            return True
        
        return False
    
    def step(self, actions_dict):
        """
        执行一步
        
        Args:
            actions_dict: {tl_id: action} 各路口动作字典
            
        Returns:
            tuple: (obs_dict, reward_dict, done_dict, info_dict)
        """
        # 检查最小绿灯约束，修正动作
        corrected_actions = {}
        for tl_id, action in actions_dict.items():
            if tl_id not in self.tl_ids:
                continue
            
            if not self._check_min_green(tl_id, action):
                # 不允许切换，保持原动作
                corrected_actions[tl_id] = self.previous_actions[tl_id]
            else:
                corrected_actions[tl_id] = action
        
        # 批量设置所有路口相位（关键：必须在step前设置所有相位）
        for tl_id, action in corrected_actions.items():
            if action is not None:
                traci.trafficlight.setPhase(tl_id, action)
        
        # 推进仿真delta_time秒
        for _ in range(self.delta_time):
            traci.simulationStep()
        
        # 更新步数计数器
        self.current_step += 1
        
        # 更新绿灯步数计数和历史动作
        for tl_id, action in corrected_actions.items():
            if action == self.previous_actions[tl_id]:
                self.green_steps_count[tl_id] += 1
            else:
                self.green_steps_count[tl_id] = 1
            self.previous_actions[tl_id] = action
        
        # 获取新状态
        global_state = get_global_state(num_intersections=self.num_intersections)
        obs_dict = {}
        reward_dict = {}
        info_dict = {}
        
        for i, tl_id in enumerate(self.tl_ids):
            start = i * 22
            end = (i + 1) * 22
            state = global_state[start:end]
            obs_dict[tl_id] = state
            
            # 计算奖励（使用V3奖励函数）
            action = corrected_actions.get(tl_id, 0)
            prev_action = self.previous_actions.get(tl_id, None)
            reward, breakdown = compute_reward_v3(state, action, prev_action)
            reward_dict[tl_id] = reward
            
            # 构建info
            info_dict[tl_id] = {
                'queue_length': float(np.mean(state[0:4])),
                'avg_queue': breakdown.get('avg_queue', np.mean(state[0:4])),
                'action': action,
                'phase': traci.trafficlight.getPhase(tl_id),
                **breakdown
            }
        
        # 检查终止条件
        done_dict = {tl_id: False for tl_id in self.tl_ids}
        truncated = self.current_step >= self.max_steps
        
        if truncated:
            done_dict = {tl_id: True for tl_id in self.tl_ids}
        
        return obs_dict, reward_dict, done_dict, info_dict, truncated
    
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


def train_multi_agent(env, dqn, buffer, total_timesteps=500000, batch_size=64, gamma=0.99,
                      epsilon_start=1.0, epsilon_end=0.01, epsilon_fraction=0.3,
                      target_update_interval=2000, log_interval=1000, save_interval=50000):
    """
    多智能体训练主循环
    
    Args:
        env: 多路口环境
        dqn: 共享DQN网络
        buffer: 经验回放缓冲区
        total_timesteps: 总训练步数
        batch_size: 批大小
        gamma: 折扣因子
        epsilon_start: 初始探索率
        epsilon_end: 最终探索率
        epsilon_fraction: 探索率衰减比例
        target_update_interval: 目标网络更新间隔
        log_interval: 日志打印间隔
        save_interval: 模型保存间隔
        
    Returns:
        dict: 训练统计信息
    """
    # 计算探索率衰减参数
    epsilon_decay_steps = int(total_timesteps * epsilon_fraction)
    epsilon_decay = (epsilon_start - epsilon_end) / epsilon_decay_steps
    
    # 初始化统计信息
    stats = {
        'timesteps': [],
        'epsilon': [],
        'avg_reward': [],
        'avg_queue': [],
        'loss': []
    }
    
    # 训练循环
    obs_dict = env.reset()
    episode_rewards = []
    episode_queues = []
    
    for timestep in range(1, total_timesteps + 1):
        # 计算当前探索率
        if timestep <= epsilon_decay_steps:
            epsilon = epsilon_start - epsilon_decay * (timestep - 1)
        else:
            epsilon = epsilon_end
        
        # 每个路口独立选择动作（ε-贪婪）
        actions_dict = {}
        for tl_id in env.tl_ids:
            obs = obs_dict[tl_id]
            action = dqn.act(obs, epsilon)
            actions_dict[tl_id] = action
        
        # 执行动作，推进仿真
        obs_dict_new, reward_dict, done_dict, info_dict, truncated = env.step(actions_dict)
        
        # 收集经验，存入共享缓冲区
        for tl_id in env.tl_ids:
            obs = obs_dict[tl_id]
            action = actions_dict[tl_id]
            reward = reward_dict[tl_id]
            obs_new = obs_dict_new[tl_id]
            done = done_dict[tl_id]
            
            buffer.add(obs, action, reward, obs_new, done, tl_id)
            
            episode_rewards.append(reward)
            episode_queues.append(info_dict[tl_id]['avg_queue'])
        
        # 更新状态
        obs_dict = obs_dict_new
        
        # 更新网络
        loss = dqn.update(buffer, batch_size, gamma)
        
        # 更新目标网络
        if timestep % target_update_interval == 0:
            dqn.update_target_network()
            print(f"[TIMESTEP {timestep}] 目标网络已更新")
        
        # 打印日志
        if timestep % log_interval == 0:
            avg_reward = np.mean(episode_rewards[-log_interval:])
            avg_queue = np.mean(episode_queues[-log_interval:])
            
            stats['timesteps'].append(timestep)
            stats['epsilon'].append(epsilon)
            stats['avg_reward'].append(avg_reward)
            stats['loss'].append(loss)
            stats['avg_queue'].append(avg_queue)
            
            print(f"[TIMESTEP {timestep}] "
                  f"epsilon={epsilon:.4f}, "
                  f"avg_reward={avg_reward:.4f}, "
                  f"avg_queue={avg_queue:.4f}, "
                  f"loss={loss:.6f}, "
                  f"buffer_size={len(buffer)}")
        
        # 保存模型
        if timestep % save_interval == 0:
            model_path = f"models/shared_dqn_step_{timestep}.pth"
            dqn.save(model_path)
            
            # 保存统计信息
            stats_path = f"models/training_stats_step_{timestep}.json"
            with open(stats_path, 'w') as f:
                json.dump(stats, f, indent=2)
        
        # 如果仿真结束，重置环境
        if truncated:
            obs_dict = env.reset()
    
    # 保存最终模型
    dqn.save("models/shared_dqn_final.pth")
    
    # 保存最终统计信息
    with open("models/training_stats_final.json", 'w') as f:
        json.dump(stats, f, indent=2)
    
    return stats


# ==============================================
# 主函数：启动训练
# ==============================================
if __name__ == "__main__":
    print("=" * 70)
    print("🚀 多路口交通信号控制训练框架")
    print("=" * 70)
    
    # 配置参数
    SUMO_CFG = "赛题资料/路口仿真案例/sumo工程_路口2/demo_2.sumocfg"
    NUM_INTERSECTIONS = 1  # demo_2只有1个路口，完整路网时改为20
    USE_GUI = False
    
    # 训练参数
    TOTAL_TIMESTEPS = 100000  # 测试时用100K，完整训练时改为500K
    BATCH_SIZE = 64
    GAMMA = 0.99
    EPSILON_START = 1.0
    EPSILON_END = 0.01
    EPSILON_FRACTION = 0.3
    TARGET_UPDATE_INTERVAL = 2000
    LOG_INTERVAL = 1000
    SAVE_INTERVAL = 20000
    
    # 创建环境
    print(f"\n创建多路口环境（{NUM_INTERSECTIONS}个路口）...")
    env = MultiIntersectionEnv(
        sumo_cfg=SUMO_CFG,
        num_intersections=NUM_INTERSECTIONS,
        use_gui=USE_GUI,
        delta_time=5,
        max_steps=720
    )
    
    # 创建共享DQN网络
    print("创建共享DQN网络...")
    dqn = SharedDQN(state_dim=22, action_dim=4, hidden_dim=256, lr=1e-4)
    
    # 创建经验回放缓冲区
    print("创建经验回放缓冲区...")
    buffer = ReplayBuffer(capacity=500000)
    
    # 开始训练
    print("\n开始训练...")
    print(f"总步数: {TOTAL_TIMESTEPS}")
    print(f"探索率: {EPSILON_START} -> {EPSILON_END}（前{EPSILON_FRACTION*100}%步数衰减）")
    print(f"目标网络更新间隔: {TARGET_UPDATE_INTERVAL}")
    print("=" * 70)
    
    try:
        stats = train_multi_agent(
            env=env,
            dqn=dqn,
            buffer=buffer,
            total_timesteps=TOTAL_TIMESTEPS,
            batch_size=BATCH_SIZE,
            gamma=GAMMA,
            epsilon_start=EPSILON_START,
            epsilon_end=EPSILON_END,
            epsilon_fraction=EPSILON_FRACTION,
            target_update_interval=TARGET_UPDATE_INTERVAL,
            log_interval=LOG_INTERVAL,
            save_interval=SAVE_INTERVAL
        )
        
        print("\n" + "=" * 70)
        print("✅ 训练完成！")
        print("=" * 70)
        print(f"最终平均奖励: {np.mean(stats['avg_reward'][-10:]):.4f}")
        print(f"最终平均排队长度: {np.mean(stats['avg_queue'][-10:]):.4f}")
        
    except KeyboardInterrupt:
        print("\n训练被用户中断")
        dqn.save("models/shared_dqn_interrupted.pth")
        print("模型已保存")
    
    finally:
        env.close()
        print("\n环境已关闭")
