"""
多路口全局状态提取模块

状态空间定义（440维，20个路口 × 22维/路口）：

每个路口22维特征（顺序固定）：
┌─────────────────────────────────────────────────────────────────────┐
│ 索引范围  │ 特征名称               │ 维度 │ 取值范围   │ 归一化方式       │
├─────────────────────────────────────────────────────────────────────┤
│ [0:4]    │ 排队长度（veh）         │ 4    │ 0~15      │ /15（截断至1.0）│
│ [4:8]    │ 平均等待时间（s）       │ 4    │ 0~120     │ /120（截断至1.0）│
│ [8:12]   │ 车道占有率（0~1）       │ 4    │ 0~1       │ 原始值          │
│ [12:16]  │ 溢出风险（0~1）         │ 4    │ 0~1       │ min(queue/15,1)│
│ [16:20]  │ 当前相位One-Hot编码    │ 4    │ {0,1}     │ 原始值           │
│ [20:22]  │ 时间特征（sin/cos）     │ 2    │ [-1,1]    │ 原始值          │
└─────────────────────────────────────────────────────────────────────┘

方向顺序：[北(N), 南(S), 东(E), 西(W)]

数据来源：
- 排队长度: traci.lane.getLastStepHaltingNumber(lane)
- 平均等待时间: 遍历车道车辆, 取traci.vehicle.getWaitingTime()平均值
- 车道占有率: traci.lane.getLastStepOccupancy(lane)
- 溢出风险: min(排队长度/15, 1.0)
- 当前相位: traci.trafficlight.getPhase(tl_id) → One-Hot编码
- 时间特征: [sin(2π·hour/24), cos(2π·hour/24)]

车道映射规则：
1. 使用traci.trafficlight.getControlledLanes(tl_id)获取受控车道
2. 方向判断：取车道ID第一个字符（N/S/E/W）
3. 代表车道选择：优先选择直行车道（通常以_0结尾），若不存在则取该方向第一个车道
4. 容错处理：若某方向无受控车道，对应维度填充0

使用示例：
    >>> import traci
    >>> from env.global_state import get_global_state
    >>> traci.start(["sumo", "-c", "xiongan.sumocfg"])
    >>> state = get_global_state()  # 返回440维np.ndarray
    >>> traci.close()
"""

import os
import sys
import numpy as np
import math

# 添加SUMO工具路径并导入traci
if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)
    import traci
else:
    raise EnvironmentError("请设置SUMO_HOME环境变量")

# DEBUG模式：设置为True时打印每个路口的特征提取日志
DEBUG = False


def get_global_state(num_intersections=20, sim_start_hour=7.0):
    """
    主入口函数：采集所有路口的实时交通数据，拼接成一维归一化状态向量
    
    Args:
        num_intersections: 路口数量（默认20）
        sim_start_hour: 仿真起始小时（默认7.0，即早上7点），用于时间特征计算
    
    Returns:
        np.ndarray: 440维归一化状态向量（20×22），dtype=np.float32
    """
    # 获取所有信号灯ID
    tl_ids = traci.trafficlight.getIDList()
    
    # 如果实际信号灯数量少于指定数量，使用实际数量
    num_tls = min(len(tl_ids), num_intersections)
    
    if DEBUG:
        print(f"[DEBUG] 检测到 {len(tl_ids)} 个信号灯，使用前 {num_tls} 个")
        print(f"[DEBUG] 信号灯列表: {tl_ids[:num_tls]}")
    
    # 初始化全局状态向量（440维）
    global_state = np.zeros(num_intersections * 22, dtype=np.float32)
    
    # 遍历每个路口提取特征
    for i in range(num_tls):
        tl_id = tl_ids[i]
        features = _extract_intersection_features(tl_id, sim_start_hour)
        global_state[i * 22:(i + 1) * 22] = features
    
    # 如果实际信号灯数量少于指定数量，剩余位置保持0（容错处理）
    if num_tls < num_intersections and DEBUG:
        print(f"[DEBUG] 警告：实际信号灯数量({num_tls})少于指定数量({num_intersections})")
    
    return global_state


def _extract_intersection_features(tl_id, sim_start_hour=7.0):
    """
    提取单个路口的22维特征
    
    Args:
        tl_id: 信号灯ID
        sim_start_hour: 仿真起始小时，用于计算当前时间
    
    Returns:
        np.ndarray: 22维特征向量
    """
    features = np.zeros(22, dtype=np.float32)
    
    # 获取该路口控制的所有车道
    controlled_lanes = traci.trafficlight.getControlledLanes(tl_id)
    
    if DEBUG:
        print(f"[DEBUG] 路口 {tl_id} 受控车道: {controlled_lanes}")
    
    # 四个方向的代表车道
    directions = ['N', 'S', 'E', 'W']
    rep_lanes = []
    
    for dir_char in directions:
        lane = _get_representative_lane(controlled_lanes, dir_char)
        rep_lanes.append(lane)
        if DEBUG:
            print(f"[DEBUG] 方向 {dir_char} 代表车道: {lane}")
    
    # ========== [0:4] 排队长度（veh） ==========
    # 读取每个方向代表车道的停止车辆数
    for i, lane in enumerate(rep_lanes):
        if lane is not None:
            queue_length = traci.lane.getLastStepHaltingNumber(lane)
            # 归一化：除以最大容量15，截断至1.0
            features[i] = min(queue_length / 15.0, 1.0)
        else:
            features[i] = 0.0  # 无车道时填充0
    
    if DEBUG:
        print(f"[DEBUG] 排队长度(归一化): {features[0:4]}")
    
    # ========== [4:8] 平均等待时间（s） ==========
    # 读取每个方向代表车道上车辆的平均等待时间
    for i, lane in enumerate(rep_lanes):
        if lane is not None:
            vehicle_ids = traci.lane.getLastStepVehicleIDs(lane)
            if len(vehicle_ids) > 0:
                total_wait_time = 0.0
                for veh_id in vehicle_ids:
                    total_wait_time += traci.vehicle.getWaitingTime(veh_id)
                avg_wait_time = total_wait_time / len(vehicle_ids)
                # 归一化：除以最大红灯等待时间120秒，截断至1.0
                features[4 + i] = min(avg_wait_time / 120.0, 1.0)
            else:
                features[4 + i] = 0.0  # 无车辆时填充0
        else:
            features[4 + i] = 0.0  # 无车道时填充0
    
    if DEBUG:
        print(f"[DEBUG] 平均等待时间(归一化): {features[4:8]}")
    
    # ========== [8:12] 车道占有率（0~1） ==========
    # 读取每个方向代表车道的占有率
    for i, lane in enumerate(rep_lanes):
        if lane is not None:
            occupancy = traci.lane.getLastStepOccupancy(lane)
            # 占有率本身已经是0~1范围，直接使用
            features[8 + i] = occupancy
        else:
            features[8 + i] = 0.0  # 无车道时填充0
    
    if DEBUG:
        print(f"[DEBUG] 车道占有率: {features[8:12]}")
    
    # ========== [12:16] 溢出风险（0~1连续值） ==========
    # 计算方式：当前排队长度 / 车道最大存储容量(15辆车)，截断至1.0
    # 注：此特征与[0:4]排队长度归一化后数值相同，但保留作为独立特征
    for i, lane in enumerate(rep_lanes):
        if lane is not None:
            queue_length = traci.lane.getLastStepHaltingNumber(lane)
            overflow_risk = min(queue_length / 15.0, 1.0)
            features[12 + i] = overflow_risk
        else:
            features[12 + i] = 0.0  # 无车道时填充0
    
    if DEBUG:
        print(f"[DEBUG] 溢出风险: {features[12:16]}")
    
    # ========== [16:20] 当前相位One-Hot编码 ==========
    # 获取当前相位索引，将对应位置置1
    current_phase = traci.trafficlight.getPhase(tl_id)
    # 确保相位索引在0~3范围内（4相位系统）
    if 0 <= current_phase < 4:
        features[16 + current_phase] = 1.0
    else:
        if DEBUG:
            print(f"[DEBUG] 警告：路口 {tl_id} 相位 {current_phase} 超出范围[0,3]")
        features[16] = 1.0  # 默认设为相位0
    
    if DEBUG:
        print(f"[DEBUG] 当前相位: {current_phase}, One-Hot: {features[16:20]}")
    
    # ========== [20:22] 时间特征 ==========
    # 获取当前仿真时间（秒），转换为小时
    current_sim_time = traci.simulation.getTime()
    current_hour = sim_start_hour + (current_sim_time / 3600.0)
    current_hour = current_hour % 24  # 确保在0~24范围内
    
    # 计算sin/cos编码
    features[20] = math.sin(2 * math.pi * current_hour / 24.0)
    features[21] = math.cos(2 * math.pi * current_hour / 24.0)
    
    if DEBUG:
        print(f"[DEBUG] 仿真时间: {current_sim_time:.1f}s, 当前小时: {current_hour:.2f}")
        print(f"[DEBUG] 时间特征(sin/cos): [{features[20]:.4f}, {features[21]:.4f}]")
        print(f"[DEBUG] 路口 {tl_id} 完整特征: {features}")
    
    return features


def _get_representative_lane(controlled_lanes, direction):
    """
    获取指定方向的代表车道ID（修正版：兼容带负号的SUMO车道命名）
    
    SUMO标准路网中，边缘ID经常以负号开头表示反向，例如：
    - E0_0: 东向边缘的反向车道（西进口）
    - -E0_0: 东向边缘的正向车道（东进口）
    
    选择规则：
    1. 跳过负号前缀，提取实际方向字符
    2. 优先选择**排队最长**的车道（最能反映拥堵状态）
    3. 若排队相同，优先选择直行车道（以_0结尾）
    4. 若该方向没有任何受控车道，返回None
    
    Args:
        controlled_lanes: 该路口所有受控车道列表
        direction: 方向字符（'N', 'S', 'E', 'W'）
    
    Returns:
        str or None: 代表车道ID，若不存在则返回None
    """
    dir_lanes = []
    for lane in controlled_lanes:
        # 去除可能的负号前缀（例如 -E0_0 -> E0_0）
        clean_name = lane.lstrip('-')
        if clean_name and clean_name[0] == direction:
            dir_lanes.append(lane)
    
    if not dir_lanes:
        return None
    
    # 优先选择排队最长的车道（最能反映拥堵状态）
    max_queue = -1
    best_lane = None
    
    for lane in dir_lanes:
        queue = traci.lane.getLastStepHaltingNumber(lane)
        if queue > max_queue:
            max_queue = queue
            best_lane = lane
        elif queue == max_queue:
            # 排队相同时，优先选择直行车道（以_0结尾）
            if lane.endswith('_0') and not best_lane.endswith('_0'):
                best_lane = lane
    
    return best_lane


# ==============================================
# 辅助函数：状态向量解析（用于调试和分析）
# ==============================================

def parse_global_state(state, num_intersections=20):
    """
    解析全局状态向量，返回结构化数据
    
    Args:
        state: 440维状态向量
        num_intersections: 路口数量
    
    Returns:
        dict: 结构化的状态数据
    """
    result = {}
    
    for i in range(num_intersections):
        start = i * 22
        features = state[start:start + 22]
        
        result[f"J{i+1:02d}"] = {
            'queue_length': features[0:4],      # [N, S, E, W]
            'avg_wait_time': features[4:8],     # [N, S, E, W]
            'occupancy': features[8:12],        # [N, S, E, W]
            'overflow_risk': features[12:16],   # [N, S, E, W]
            'current_phase': int(np.argmax(features[16:20])),
            'phase_onehot': features[16:20],
            'time_feature': features[20:22]
        }
    
    return result


def get_state_dimension_info():
    """
    返回状态维度详细信息（用于文档和调试）
    
    Returns:
        list: 每个维度的详细信息
    """
    info = []
    dim_idx = 0
    
    for tl_idx in range(20):
        tl_name = f"J{tl_idx+1:02d}"
        
        # [0:4] 排队长度
        for dir_name in ['N', 'S', 'E', 'W']:
            info.append({
                'index': dim_idx,
                'intersection': tl_name,
                'feature': 'queue_length',
                'direction': dir_name,
                'range': '[0, 1]',
                'description': f"{tl_name} {dir_name}方向排队长度（归一化）",
                'source': 'traci.lane.getLastStepHaltingNumber(lane) / 15'
            })
            dim_idx += 1
        
        # [4:8] 平均等待时间
        for dir_name in ['N', 'S', 'E', 'W']:
            info.append({
                'index': dim_idx,
                'intersection': tl_name,
                'feature': 'avg_wait_time',
                'direction': dir_name,
                'range': '[0, 1]',
                'description': f"{tl_name} {dir_name}方向平均等待时间（归一化）",
                'source': 'mean(traci.vehicle.getWaitingTime(veh)) / 120'
            })
            dim_idx += 1
        
        # [8:12] 车道占有率
        for dir_name in ['N', 'S', 'E', 'W']:
            info.append({
                'index': dim_idx,
                'intersection': tl_name,
                'feature': 'occupancy',
                'direction': dir_name,
                'range': '[0, 1]',
                'description': f"{tl_name} {dir_name}方向车道占有率",
                'source': 'traci.lane.getLastStepOccupancy(lane)'
            })
            dim_idx += 1
        
        # [12:16] 溢出风险
        for dir_name in ['N', 'S', 'E', 'W']:
            info.append({
                'index': dim_idx,
                'intersection': tl_name,
                'feature': 'overflow_risk',
                'direction': dir_name,
                'range': '[0, 1]',
                'description': f"{tl_name} {dir_name}方向溢出风险",
                'source': 'min(queue_length / 15, 1.0)'
            })
            dim_idx += 1
        
        # [16:20] 当前相位One-Hot
        for phase_idx in range(4):
            phase_names = ['NS_Straight', 'NS_Left', 'EW_Straight', 'EW_Left']
            info.append({
                'index': dim_idx,
                'intersection': tl_name,
                'feature': 'phase_onehot',
                'direction': phase_names[phase_idx],
                'range': '{0, 1}',
                'description': f"{tl_name} 相位{phase_idx}({phase_names[phase_idx]})指示",
                'source': 'traci.trafficlight.getPhase(tl_id) → One-Hot'
            })
            dim_idx += 1
        
        # [20:22] 时间特征
        info.append({
            'index': dim_idx,
            'intersection': tl_name,
            'feature': 'time_sin',
            'direction': '-',
            'range': '[-1, 1]',
            'description': f"{tl_name} 时间特征(sin)",
            'source': 'sin(2π·hour/24)'
        })
        dim_idx += 1
        
        info.append({
            'index': dim_idx,
            'intersection': tl_name,
            'feature': 'time_cos',
            'direction': '-',
            'range': '[-1, 1]',
            'description': f"{tl_name} 时间特征(cos)",
            'source': 'cos(2π·hour/24)'
        })
        dim_idx += 1
    
    return info


# ==============================================
# 单元测试（可单独运行）
# ==============================================
if __name__ == "__main__":
    import sys
    import os
    
    # 测试状态提取功能
    print("=" * 60)
    print("全局状态提取模块单元测试")
    print("=" * 60)
    
    # 启动SUMO仿真（使用默认配置）
    sumo_cfg_path = os.path.join(os.path.dirname(__file__), '../sumo_files/xiongan.sumocfg')
    if not os.path.exists(sumo_cfg_path):
        print(f"错误：未找到SUMO配置文件 {sumo_cfg_path}")
        sys.exit(1)
    
    print(f"使用配置文件: {sumo_cfg_path}")
    
    traci.start([
        "sumo",
        "-c", sumo_cfg_path,
        "--no-step-log",
        "--no-warnings",
        "--time-to-teleport", "-1"
    ])
    
    # 执行几步仿真让车辆进入路网
    for _ in range(10):
        traci.simulationStep()
    
    # 测试状态提取
    DEBUG = True  # 启用调试日志
    state = get_global_state(num_intersections=20)
    
    print("\n" + "=" * 60)
    print(f"全局状态向量维度: {state.shape}")
    print(f"数据类型: {state.dtype}")
    print(f"状态向量前30个值: {state[:30]}")
    print(f"状态向量统计: 最小值={state.min():.4f}, 最大值={state.max():.4f}, 均值={state.mean():.4f}")
    print("=" * 60)
    
    # 解析状态
    parsed = parse_global_state(state, num_intersections=1)
    print(f"\n解析后的状态: {parsed}")
    
    # 获取维度信息
    dim_info = get_state_dimension_info()
    print(f"\n总维度数: {len(dim_info)}")
    
    traci.close()
    print("\n测试完成！")
