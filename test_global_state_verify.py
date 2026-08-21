"""
本地验证脚本（非GUI版）：使用demo_2路网，测试get_global_state()

功能：
1. 启动SUMO非GUI模式
2. 运行仿真直到有排队产生
3. 调用get_global_state()获取状态
4. 打印前44个值（J01和J02），确认排队/占有率数值不是全0
"""

import sys
import os

# 添加SUMO工具路径
if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)
else:
    sys.exit("请设置SUMO_HOME环境变量")

import traci
import numpy as np
from env.global_state import get_global_state, DEBUG, _get_representative_lane

def main():
    print("=" * 70)
    print("🚀 本地验证：demo_2路网 + get_global_state()")
    print("=" * 70)
    
    # 使用demo_2路网
    sumo_cfg_path = "赛题资料/路口仿真案例/sumo工程_路口2/demo_2.sumocfg"
    
    if not os.path.exists(sumo_cfg_path):
        print(f"错误：未找到配置文件 {sumo_cfg_path}")
        sys.exit(1)
    
    print(f"使用配置文件: {sumo_cfg_path}")
    
    # 启动SUMO非GUI模式
    traci.start([
        "sumo",
        "-c", sumo_cfg_path,
        "--no-warnings",
        "--time-to-teleport", "-1"
    ])
    
    # 运行仿真直到有排队产生
    print("\n运行仿真直到产生排队...")
    step_count = 0
    max_steps = 1000
    queue_detected = False
    
    while step_count < max_steps:
        traci.simulationStep()
        
        # 每50步检查一次排队
        if step_count % 50 == 0:
            # 获取所有受控车道的排队
            tl_ids = traci.trafficlight.getIDList()
            total_queue = 0
            
            for tl_id in tl_ids:
                controlled_lanes = traci.trafficlight.getControlledLanes(tl_id)
                for lane in controlled_lanes:
                    queue = traci.lane.getLastStepHaltingNumber(lane)
                    total_queue += queue
            
            vehicle_count = traci.vehicle.getIDCount()
            print(f"步骤 {step_count}: 车辆数={vehicle_count}, 总排队={total_queue}")
            
            if total_queue > 0:
                print(f"✅ 在步骤 {step_count} 检测到排队")
                queue_detected = True
                break
        
        step_count += 1
    
    if not queue_detected:
        print(f"⚠️ 警告：在 {max_steps} 步内未检测到排队，继续运行...")
        # 再运行500步
        for _ in range(500):
            traci.simulationStep()
        step_count += 500
        print(f"已运行到步骤 {step_count}")
    
    # 获取所有信号灯信息
    tl_ids = traci.trafficlight.getIDList()
    print(f"\n检测到 {len(tl_ids)} 个信号灯: {tl_ids}")
    
    # 打印每个信号灯的受控车道及实时数据
    for tl_id in tl_ids:
        controlled_lanes = traci.trafficlight.getControlledLanes(tl_id)
        print(f"\n信号灯 {tl_id} 受控车道:")
        
        for lane in controlled_lanes:
            queue = traci.lane.getLastStepHaltingNumber(lane)
            occupancy = traci.lane.getLastStepOccupancy(lane)
            vehicles = traci.lane.getLastStepVehicleNumber(lane)
            # 去除负号前缀判断方向
            clean_name = lane.lstrip('-')
            direction = clean_name[0] if clean_name else '?'
            print(f"  {lane:10s} | 方向={direction} | 排队={queue:2d} | 车辆数={vehicles:2d} | 占有率={occupancy:.4f}")
    
    # 测试代表车道选择
    print("\n" + "=" * 70)
    print("🔍 代表车道选择测试:")
    print("=" * 70)
    
    for tl_id in tl_ids:
        controlled_lanes = traci.trafficlight.getControlledLanes(tl_id)
        print(f"\n路口 {tl_id}:")
        
        for direction in ['N', 'S', 'E', 'W']:
            lane = _get_representative_lane(controlled_lanes, direction)
            if lane is not None:
                queue = traci.lane.getLastStepHaltingNumber(lane)
                occupancy = traci.lane.getLastStepOccupancy(lane)
                print(f"  方向 {direction}: {lane} | 排队={queue} | 占有率={occupancy:.4f}")
            else:
                print(f"  方向 {direction}: None (无受控车道)")
    
    # 启用调试模式
    DEBUG = True
    
    # 获取全局状态
    print("\n" + "=" * 70)
    print("📊 获取全局状态 (前44维 = J01 + J02)")
    print("=" * 70)
    
    state = get_global_state(num_intersections=30)
    print(f"\n全局状态维度: {state.shape}")
    print(f"数据类型: {state.dtype}")
    
    # 打印前44个值（J01和J02）
    print("\n" + "=" * 70)
    print("J01 (索引 0-21):")
    print("=" * 70)
    
    # J01特征解析
    j01 = state[0:22]
    print(f"[0:4] 排队长度(N,S,E,W):       {np.round(j01[0:4], 4)}")
    print(f"[4:8] 平均等待时间(N,S,E,W):   {np.round(j01[4:8], 4)}")
    print(f"[8:12] 车道占有率(N,S,E,W):    {np.round(j01[8:12], 4)}")
    print(f"[12:16] 溢出风险(N,S,E,W):     {np.round(j01[12:16], 4)}")
    print(f"[16:20] 当前相位One-Hot:        {j01[16:20]}")
    print(f"[20:22] 时间特征(sin,cos):      {np.round(j01[20:22], 4)}")
    
    print("\n" + "=" * 70)
    print("J02 (索引 22-43):")
    print("=" * 70)
    
    # J02特征解析
    j02 = state[22:44]
    print(f"[22:26] 排队长度(N,S,E,W):     {np.round(j02[0:4], 4)}")
    print(f"[26:30] 平均等待时间(N,S,E,W): {np.round(j02[4:8], 4)}")
    print(f"[30:34] 车道占有率(N,S,E,W):  {np.round(j02[8:12], 4)}")
    print(f"[34:38] 溢出风险(N,S,E,W):   {np.round(j02[12:16], 4)}")
    print(f"[38:42] 当前相位One-Hot:      {j02[16:20]}")
    print(f"[42:44] 时间特征(sin,cos):    {np.round(j02[20:22], 4)}")
    
    # 检查非零值
    print("\n" + "=" * 70)
    print("🔍 非零值检查:")
    print("=" * 70)
    
    j01_nonzero = np.count_nonzero(j01)
    j02_nonzero = np.count_nonzero(j02)
    
    print(f"J01 非零值数量: {j01_nonzero}/22")
    print(f"J02 非零值数量: {j02_nonzero}/22")
    
    # 检查关键特征是否有值
    j01_queues = j01[0:4]
    j01_occupancy = j01[8:12]
    
    print(f"\nJ01 排队长度最大值: {j01_queues.max():.4f}")
    print(f"J01 占有率最大值:   {j01_occupancy.max():.4f}")
    
    if j01_queues.max() > 0 or j01_occupancy.max() > 0:
        print("\n✅ 成功！排队和占有率特征提取正常工作")
        print("   值不为全0，DQN可以看到交通状态")
    else:
        print("\n❌ 警告：排队和占有率全为0")
        print("   请检查：1.路网文件 2.流量配置 3.方向识别逻辑")
    
    # 关闭连接
    traci.close()
    print("\n" + "=" * 70)
    print("✅ 验证完成！")
    print("=" * 70)

if __name__ == "__main__":
    main()
