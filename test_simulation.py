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

def test_simulation():
    """测试SUMO仿真和状态提取"""
    sumo_binary = "sumo"
    sumo_cfg_path = "sumo_files/xiongan_30.sumocfg"
    
    # 启动SUMO
    traci.start([
        sumo_binary,
        "-c", sumo_cfg_path,
        "--no-warnings",
        "--time-to-teleport", "-1"
    ])
    
    # 获取信号灯控制的车道
    tl_id = "J1"
    controlled_lanes = traci.trafficlight.getControlledLanes(tl_id)
    print(f"信号灯 {tl_id} 控制的车道: {controlled_lanes}")
    
    # 获取所有边
    edges = traci.edge.getIDList()
    print(f"所有边: {edges}")
    
    # 运行100步仿真，检查车辆
    step_count = 0
    max_steps = 100
    
    while step_count < max_steps:
        traci.simulationStep()
        
        # 获取车辆数量
        vehicle_count = traci.vehicle.getIDCount()
        if vehicle_count > 0:
            vehicles = traci.vehicle.getIDList()
            print(f"\n步骤 {step_count}: {vehicle_count} 辆车")
            for v in vehicles[:5]:
                lane = traci.vehicle.getLaneID(v)
                pos = traci.vehicle.getPosition(v)
                speed = traci.vehicle.getSpeed(v)
                print(f"  车辆 {v}: 车道={lane}, 位置={pos}, 速度={speed:.2f}")
        
        step_count += 1
    
    # 检查排队长度
    print("\n排队长度统计:")
    for lane in controlled_lanes:
        queue = traci.lane.getLastStepHaltingNumber(lane)
        vehicles = traci.lane.getLastStepVehicleNumber(lane)
        print(f"  车道 {lane}: 排队车辆={queue}, 总车辆={vehicles}")
    
    # 关闭连接
    traci.close()
    
    return True

if __name__ == "__main__":
    print("=" * 60)
    print("🚀 测试SUMO仿真")
    print("=" * 60)
    
    try:
        test_simulation()
        print("\n✅ 测试完成！")
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        traci.close()
