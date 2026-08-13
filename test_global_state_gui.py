"""
本地验证脚本：使用SUMO GUI运行demo_2路网，测试get_global_state()

功能：
1. 启动SUMO GUI模式（自动运行）
2. 运行仿真直到有排队产生
3. 获取并打印全局状态前44维（J01+J02）
4. 保持GUI打开供观察
"""

import sys
import os
import time

# 添加SUMO工具路径
if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)
else:
    sys.exit("请设置SUMO_HOME环境变量")

import traci
import numpy as np
from env.global_state import get_global_state, DEBUG

def main():
    print("=" * 70)
    print("🚀 本地验证：demo_2路网 + SUMO GUI + get_global_state()")
    print("=" * 70)
    
    # 使用demo_2路网
    sumo_cfg_path = "赛题资料/路口仿真案例/sumo工程_路口2/demo_2.sumocfg"
    
    if not os.path.exists(sumo_cfg_path):
        print(f"错误：未找到配置文件 {sumo_cfg_path}")
        sys.exit(1)
    
    print(f"使用配置文件: {sumo_cfg_path}")
    
    # 启动SUMO GUI模式
    # 添加 --start 自动开始，--delay 50 设置延迟便于观察
    traci.start([
        "sumo-gui",
        "-c", sumo_cfg_path,
        "--no-warnings",
        "--time-to-teleport", "-1",
        "--start",
        "--delay", "50"
    ])
    
    # 运行仿真直到有排队产生
    print("\n运行仿真中... (可以在SUMO GUI中观察车辆运动)")
    step_count = 0
    queue_detected = False
    
    while step_count < 500:
        traci.simulationStep()
        
        if step_count % 50 == 0:
            vehicle_count = traci.vehicle.getIDCount()
            tl_ids = traci.trafficlight.getIDList()
            total_queue = 0
            
            for tl_id in tl_ids:
                controlled_lanes = traci.trafficlight.getControlledLanes(tl_id)
                for lane in controlled_lanes:
                    total_queue += traci.lane.getLastStepHaltingNumber(lane)
            
            print(f"步骤 {step_count}: 车辆数={vehicle_count}, 总排队={total_queue}")
            
            if total_queue > 0:
                print(f"✅ 在步骤 {step_count} 检测到排队！")
                queue_detected = True
                break
        
        step_count += 1
    
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
            clean_name = lane.lstrip('-')
            direction = clean_name[0] if clean_name else '?'
            print(f"  {lane:10s} | 方向={direction} | 排队={queue:2d} | 占有率={occupancy:.4f}")
    
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
    
    if j01_nonzero > 0 or j02_nonzero > 0:
        print("\n✅ 成功！状态值不是全0，特征提取正常工作")
        print("   DQN可以看到交通状态（排队、占有率等）")
    else:
        print("\n❌ 警告：状态值全为0，请检查车道映射逻辑")
    
    # 保持GUI打开供用户继续观察
    print("\n" + "=" * 70)
    print("观察完成！")
    print("按 Ctrl+C 或关闭SUMO GUI窗口退出...")
    print("=" * 70)
    
    # 持续运行直到用户关闭GUI
    try:
        while True:
            traci.simulationStep()
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("\n用户中断，关闭仿真...")
    except Exception as e:
        print(f"\n仿真结束: {e}")
    
    # 关闭连接
    try:
        traci.close()
    except Exception as e:
        pass
    
    print("\n✅ 验证完成！")

if __name__ == "__main__":
    main()
