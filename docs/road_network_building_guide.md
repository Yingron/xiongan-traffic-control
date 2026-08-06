# 🏗️ 雄安20路口路网构建指南

## 📋 任务概述

将赛题资料中的20个路口数据构建成一个完整的SUMO路网，用于DQN强化学习训练。

## 📁 赛题资料结构

```
赛题资料/
├── 路口数据/                    # 20个路口的详细数据
│   ├── 1/
│   │   ├── 路口数据/            # Excel文件：流量和配时方案
│   │   │   └── demo_1流量和交叉口配时方案.xlsx
│   │   └── 高精地图/            # PNG图片：路口布局图
│   │       └── demo_1.png
│   ├── 2/ ... 20/              # 其他19个路口
│
└── 路口仿真案例/                # 4个路口的SUMO工程示例
    ├── sumo工程_路口1/          # 包含net.xml, rou.xml, sumocfg等
    ├── sumo工程_路口2/
    ├── sumo工程_路口3/
    └── sumo工程_路口4/
```

## 📊 Excel数据格式说明

### 1. 流量数据（Sheet: 流量数据）

| 列 | 内容 |
|----|------|
| 统计开始时间/结束时间 | 15分钟间隔的时间段 |
| 东进口/西进口/北进口/南进口 | 各方向流量 |
| 左转(pcu)/直行(pcu)/右转(pcu) | 各转向的小时流量（pcu/h） |
| 配置参数-总流量 | 该方向总流量 |
| 配置参数-转向比例 | 各转向占比 |

### 2. 信号配时数据（Sheet: 信号配时数据）

| 列 | 内容 |
|----|------|
| 时段分类 | 早高峰/平峰/晚高峰 |
| 相位编号 | 1-4（东西直行、东西左转、南北直行、南北左转） |
| 相位名称 | 相位描述 |
| 绿灯时长(s) | 绿灯时间 |
| 黄灯时长(s) | 黄灯时间 |
| 全红时长(s) | 全红时间 |
| 单相位总时长(s) | 绿灯+黄灯+全红 |
| 周期总时长(s) | 一个周期的总时间 |

---

## 🚀 路网构建步骤

### 步骤1：提取20个路口的流量和配时数据

运行脚本提取所有路口的关键数据：

```bash
python scripts/extract_intersection_data.py
```

生成的文件：
- `data/intersections_data.csv` - 所有路口的汇总数据
- `data/traffic_flows.json` - 流量数据（用于rou.xml）
- `data/timing_plans.json` - 配时方案（用于信号灯配置）

### 步骤2：设计路网拓扑

由于是"窄路密网"（路口间距<200m），我们设计一个4×4网格布局（16个路口）加上周边4个路口。

```
路口编号规则：
J01-J04: 第一排（北）
J05-J08: 第二排
J09-J12: 第三排
J13-J16: 第四排（南）
J17-J20: 周边路口（东/西/北/南各一个）
```

### 步骤3：生成SUMO路网文件

运行脚本自动生成路网：

```bash
python scripts/generate_road_network.py
```

生成的文件：
- `sumo_files/xiongan_20.net.xml` - 20路口路网文件
- `sumo_files/xiongan_20.rou.xml` - 流量配置文件
- `sumo_files/xiongan_20.sumocfg` - 仿真配置文件
- `sumo_files/signals.add.xml` - 信号灯配置文件

### 步骤4：验证路网

```bash
# 非GUI模式验证
sumo -c sumo_files/xiongan_20.sumocfg

# GUI模式验证
sumo-gui -c sumo_files/xiongan_20.sumocfg
```

---

## 📝 数据提取脚本

### extract_intersection_data.py

```python
"""
从Excel文件提取20个路口的流量和配时数据
"""
import os
import json
import pandas as pd

def extract_flow_data(excel_path):
    """提取流量数据"""
    df = pd.read_excel(excel_path, sheet_name='流量数据')
    
    # 提取早高峰流量（第2-9行）
    peak_flows = {}
    directions = ['东进口', '西进口', '北进口', '南进口']
    turns = ['左转', '直行', '右转']
    
    for i, direction in enumerate(directions):
        peak_flows[direction] = {}
        for j, turn in enumerate(turns):
            col_idx = 2 + i * 3 + j
            # 计算平均值
            avg_flow = df.iloc[2:10, col_idx].mean()
            peak_flows[direction][turn] = int(avg_flow)
    
    # 提取转向比例（第11行）
    turn_ratios = {}
    for i, direction in enumerate(directions):
        turn_ratios[direction] = {}
        for j, turn in enumerate(turns):
            col_idx = 2 + i * 3 + j
            ratio = df.iloc[11, col_idx]
            turn_ratios[direction][turn] = float(ratio)
    
    return peak_flows, turn_ratios

def extract_timing_data(excel_path):
    """提取配时数据"""
    df = pd.read_excel(excel_path, sheet_name='信号配时数据')
    
    timing_plans = {}
    phases = ['东西向直行', '东西向左转', '南北向直行', '南北向左转']
    
    # 提取早高峰配时（第1-4行）
    timing_plans['peak'] = {}
    for i, phase in enumerate(phases):
        row_idx = i + 1
        timing_plans['peak'][phase] = {
            'green': int(df.iloc[row_idx, 4]),
            'yellow': int(df.iloc[row_idx, 5]),
            'red': int(df.iloc[row_idx, 6]),
            'total': int(df.iloc[row_idx, 7])
        }
    timing_plans['peak']['cycle'] = int(df.iloc[1, 8])
    
    # 提取平峰配时（第5-8行）
    timing_plans['offpeak'] = {}
    for i, phase in enumerate(phases):
        row_idx = i + 5
        timing_plans['offpeak'][phase] = {
            'green': int(df.iloc[row_idx, 4]),
            'yellow': int(df.iloc[row_idx, 5]),
            'red': int(df.iloc[row_idx, 6]),
            'total': int(df.iloc[row_idx, 7])
        }
    timing_plans['offpeak']['cycle'] = int(df.iloc[5, 8])
    
    return timing_plans

def main():
    base_dir = r'赛题资料\路口数据'
    all_data = {}
    
    for i in range(1, 21):
        excel_path = os.path.join(base_dir, str(i), '路口数据', f'demo_{i}流量和交叉口配时方案.xlsx')
        
        if not os.path.exists(excel_path):
            print(f'⚠️ 未找到文件: {excel_path}')
            continue
        
        print(f'📊 处理路口 {i}...')
        
        try:
            flows, ratios = extract_flow_data(excel_path)
            timing = extract_timing_data(excel_path)
            
            all_data[f'J{i:02d}'] = {
                'flows': flows,
                'turn_ratios': ratios,
                'timing': timing
            }
            
        except Exception as e:
            print(f'❌ 处理路口 {i} 失败: {e}')
    
    # 保存数据
    os.makedirs('data', exist_ok=True)
    
    # CSV格式
    rows = []
    for tl_id, data in all_data.items():
        for direction in ['东进口', '西进口', '北进口', '南进口']:
            for turn in ['左转', '直行', '右转']:
                rows.append({
                    'tl_id': tl_id,
                    'direction': direction,
                    'turn': turn,
                    'flow': data['flows'][direction][turn],
                    'ratio': data['turn_ratios'][direction][turn]
                })
    
    pd.DataFrame(rows).to_csv('data/intersections_data.csv', index=False, encoding='utf-8-sig')
    print('✅ 保存到 data/intersections_data.csv')
    
    # JSON格式
    with open('data/traffic_flows.json', 'w', encoding='utf-8') as f:
        json.dump({k: v['flows'] for k, v in all_data.items()}, f, ensure_ascii=False, indent=2)
    print('✅ 保存到 data/traffic_flows.json')
    
    with open('data/timing_plans.json', 'w', encoding='utf-8') as f:
        json.dump({k: v['timing'] for k, v in all_data.items()}, f, ensure_ascii=False, indent=2)
    print('✅ 保存到 data/timing_plans.json')
    
    print(f'\n📈 共处理 {len(all_data)} 个路口')

if __name__ == '__main__':
    main()
```

---

## 📝 路网生成脚本

### generate_road_network.py

```python
"""
生成20路口SUMO路网文件
"""
import os
import json
import math

def generate_net_xml(num_intersections=20):
    """生成net.xml文件"""
    # 4×4网格布局
    grid_size = 4
    spacing = 200  # 路口间距200m（窄路密网）
    
    edges = []
    junctions = []
    connections = []
    tl_logics = []
    
    # 创建路口节点
    tl_ids = []
    for row in range(grid_size):
        for col in range(grid_size):
            tl_id = f'J{(row*grid_size + col + 1):02d}'
            tl_ids.append(tl_id)
            
            x = col * spacing
            y = (grid_size - 1 - row) * spacing
            
            junctions.append(f'<junction id="{tl_id}" type="traffic_light" x="{x}" y="{y}" incLanes="" intLanes="" shape="{x-20,y-20} {x+20,y-20} {x+20,y+20} {x-20,y+20}"/>')
    
    # 创建道路（双向）
    edge_id = 0
    for row in range(grid_size):
        for col in range(grid_size):
            # 水平道路（东西向）
            if col < grid_size - 1:
                from_junction = tl_ids[row * grid_size + col]
                to_junction = tl_ids[row * grid_size + col + 1]
                
                # 东向（正向）
                edges.append(f'<edge id="E{edge_id}" from="{from_junction}" to="{to_junction}" priority="-1">')
                edges.append(f'  <lane id="E{edge_id}_0" index="0" speed="13.89" length="{spacing}"/>')
                edges.append(f'  <lane id="E{edge_id}_1" index="1" speed="13.89" length="{spacing}"/>')
                edges.append('</edge>')
                
                # 西向（反向）
                edges.append(f'<edge id="-E{edge_id}" from="{to_junction}" to="{from_junction}" priority="-1">')
                edges.append(f'  <lane id="-E{edge_id}_0" index="0" speed="13.89" length="{spacing}"/>')
                edges.append(f'  <lane id="-E{edge_id}_1" index="1" speed="13.89" length="{spacing}"/>')
                edges.append('</edge>')
                
                edge_id += 1
            
            # 垂直道路（南北向）
            if row < grid_size - 1:
                from_junction = tl_ids[row * grid_size + col]
                to_junction = tl_ids[(row + 1) * grid_size + col]
                
                # 南向（正向）
                edges.append(f'<edge id="E{edge_id}" from="{from_junction}" to="{to_junction}" priority="-1">')
                edges.append(f'  <lane id="E{edge_id}_0" index="0" speed="13.89" length="{spacing}"/>')
                edges.append(f'  <lane id="E{edge_id}_1" index="1" speed="13.89" length="{spacing}"/>')
                edges.append('</edge>')
                
                # 北向（反向）
                edges.append(f'<edge id="-E{edge_id}" from="{to_junction}" to="{from_junction}" priority="-1">')
                edges.append(f'  <lane id="-E{edge_id}_0" index="0" speed="13.89" length="{spacing}"/>')
                edges.append(f'  <lane id="-E{edge_id}_1" index="1" speed="13.89" length="{spacing}"/>')
                edges.append('</edge>')
                
                edge_id += 1
    
    # 创建信号灯逻辑（4相位）
    for tl_id in tl_ids:
        tl_logics.append(f'<tlLogic id="{tl_id}" type="static" programID="0" offset="0">')
        tl_logics.append('  <phase duration="30" state="GGgrrr"/>')  # 南北直行
        tl_logics.append('  <phase duration="3" state="yyyrrr"/>')   # 南北黄灯
        tl_logics.append('  <phase duration="20" state="rrrGGg"/>')  # 东西直行
        tl_logics.append('  <phase duration="3" state="rrryyy"/>')   # 东西黄灯
        tl_logics.append('</tlLogic>')
    
    # 生成完整XML
    net_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<net version="1.20" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="http://sumo.dlr.de/xsd/net_file.xsd">
    <location netOffset="0.00,0.00" convBoundary="0,0,{grid_size*spacing},{grid_size*spacing}" projParameter="!"/>

    <!-- 道路 -->
    {"\\n    ".join(edges)}

    <!-- 信号灯逻辑 -->
    {"\\n    ".join(tl_logics)}

    <!-- 路口节点 -->
    {"\\n    ".join(junctions)}

</net>'''
    
    return net_xml

def generate_rou_xml(traffic_flows):
    """生成rou.xml文件"""
    flows = []
    
    # 读取流量数据
    for tl_id, data in traffic_flows.items():
        # 简化处理：每个路口生成4个方向的流量
        for direction, turns in data.items():
            total_flow = sum(turns.values())
            if total_flow > 0:
                # 创建直行流量
                straight_flow = int(turns['直行'] * 0.08)  # 转换为概率
                if straight_flow > 0:
                    flows.append(f'<flow id="{tl_id}_{direction}_straight" route="{tl_id}_{direction}_straight" type="car" begin="0" end="3600" probability="{straight_flow/1000:.4f}"/>')
                
                # 创建左转流量
                left_flow = int(turns['左转'] * 0.04)
                if left_flow > 0:
                    flows.append(f'<flow id="{tl_id}_{direction}_left" route="{tl_id}_{direction}_left" type="car" begin="0" end="3600" probability="{left_flow/1000:.4f}"/>')
    
    # 生成完整XML
    rou_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<routes xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="http://sumo.dlr.de/xsd/routes_file.xsd">
    <vType id="car" accel="2.6" decel="4.5" sigma="0.5" length="5" maxSpeed="13.89"/>

    <!-- 流量定义 -->
    {"\\n    ".join(flows)}

</routes>'''
    
    return rou_xml

def generate_sumocfg():
    """生成sumocfg文件"""
    return '''<?xml version="1.0" encoding="UTF-8"?>

<configuration xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="http://sumo.dlr.de/xsd/sumoConfiguration.xsd">
    <input>
        <net-file value="xiongan_20.net.xml"/>
        <route-files value="xiongan_20.rou.xml"/>
    </input>
    <output>
        <tripinfo-output value="tripinfo.xml"/>
        <summary-output value="summary.xml"/>
        <emission-output value="emissions.xml"/>
    </output>
    <time>
        <begin value="0"/>
        <end value="3600"/>
        <step-length value="1"/>
    </time>
    <processing>
        <lateral-resolution value="0.5"/>
    </processing>
</configuration>'''

def main():
    os.makedirs('sumo_files', exist_ok=True)
    
    # 1. 读取流量数据
    traffic_flows = {}
    if os.path.exists('data/traffic_flows.json'):
        with open('data/traffic_flows.json', 'r', encoding='utf-8') as f:
            traffic_flows = json.load(f)
        print('📥 已加载流量数据')
    else:
        print('⚠️ 未找到流量数据，使用默认值')
        # 创建默认流量
        for i in range(1, 21):
            traffic_flows[f'J{i:02d}'] = {
                '东进口': {'左转': 50, '直行': 80, '右转': 30},
                '西进口': {'左转': 45, '直行': 75, '右转': 28},
                '北进口': {'左转': 48, '直行': 78, '右转': 25},
                '南进口': {'左转': 46, '直行': 76, '右转': 27}
            }
    
    # 2. 生成net.xml
    print('🔧 生成路网文件...')
    net_xml = generate_net_xml()
    with open('sumo_files/xiongan_20.net.xml', 'w', encoding='utf-8') as f:
        f.write(net_xml)
    print('✅ 保存到 sumo_files/xiongan_20.net.xml')
    
    # 3. 生成rou.xml
    print('🔧 生成流量文件...')
    rou_xml = generate_rou_xml(traffic_flows)
    with open('sumo_files/xiongan_20.rou.xml', 'w', encoding='utf-8') as f:
        f.write(rou_xml)
    print('✅ 保存到 sumo_files/xiongan_20.rou.xml')
    
    # 4. 生成sumocfg
    print('🔧 生成仿真配置...')
    sumocfg = generate_sumocfg()
    with open('sumo_files/xiongan_20.sumocfg', 'w', encoding='utf-8') as f:
        f.write(sumocfg)
    print('✅ 保存到 sumo_files/xiongan_20.sumocfg')
    
    print('\n🎉 路网生成完成！')
    print('📁 文件位置: sumo_files/xiongan_20.*')

if __name__ == '__main__':
    main()
```

---

## 🚀 执行命令

```bash
# 1. 创建scripts目录
mkdir scripts

# 2. 提取数据（需要先运行extract_intersection_data.py）
python scripts/extract_intersection_data.py

# 3. 生成路网
python scripts/generate_road_network.py

# 4. 验证路网（非GUI模式）
sumo -c sumo_files/xiongan_20.sumocfg

# 5. 验证路网（GUI模式）
sumo-gui -c sumo_files/xiongan_20.sumocfg
```

---

## 📊 预期结果

### 数据提取输出

```
📊 处理路口 1...
📊 处理路口 2...
...
📊 处理路口 20...
✅ 保存到 data/intersections_data.csv
✅ 保存到 data/traffic_flows.json
✅ 保存到 data/timing_plans.json

📈 共处理 20 个路口
```

### 路网生成输出

```
📥 已加载流量数据
🔧 生成路网文件...
✅ 保存到 sumo_files/xiongan_20.net.xml
🔧 生成流量文件...
✅ 保存到 sumo_files/xiongan_20.rou.xml
🔧 生成仿真配置...
✅ 保存到 sumo_files/xiongan_20.sumocfg

🎉 路网生成完成！
📁 文件位置: sumo_files/xiongan_20.*
```

---

## ⚠️ 注意事项

1. **路口间距**：雄安"窄路密网"要求路口间距<200m，脚本中设置为200m
2. **车道数量**：每个方向设置2条车道（直行+左转/右转）
3. **信号灯**：每个路口4个相位（南北直行→南北左转→东西直行→东西左转）
4. **流量转换**：Excel中的pcu/h需要转换为SUMO的probability
5. **路由定义**：脚本中的路由名称需要与net.xml中的道路ID对应

---

## 🔧 手动调整建议

如果自动生成的路网有问题，可以使用SUMO的netedit工具手动调整：

```bash
netedit sumo_files/xiongan_20.net.xml
```

常用操作：
- 点击道路节点添加路口
- 点击道路添加车道
- 在"Traffic Lights"标签页配置信号灯相位
- 保存后重新运行仿真

---

## 📅 进度安排

| 阶段 | 时间 | 任务 |
|------|------|------|
| 第1天 | 提取数据 | 运行extract_intersection_data.py |
| 第2天 | 生成路网 | 运行generate_road_network.py |
| 第3天 | 验证路网 | 使用sumo-gui检查路网连通性 |
| 第4天 | 手动调整 | 使用netedit修复问题 |
| 第5天 | 流量测试 | 运行仿真验证流量是否合理 |
| 第6天 | 信号灯配置 | 配置各路口的信号灯相位 |
| 第7天 | 综合测试 | 完整3600秒仿真测试 |

---

## 📞 常见问题

### Q1: SUMO_HOME环境变量未设置

```bash
# Windows
set SUMO_HOME=C:\Program Files (x86)\Eclipse\Sumo

# Linux/macOS
export SUMO_HOME=/usr/share/sumo
```

### Q2: 仿真时出现"no route found"错误

检查rou.xml中的路由名称是否与net.xml中的道路ID对应。

### Q3: 车辆排队长度为0

流量密度太低，需要调整probability参数（当前设置为0.08）。

### Q4: 路口死锁

检查信号灯相位配置，确保所有方向都有通行机会。

---

## 📚 参考资料

1. **SUMO官方文档**: https://sumo.dlr.de/docs/
2. **SUMO Tutorial**: https://sumo.dlr.de/docs/Tutorials/
3. **TraCI接口**: https://sumo.dlr.de/docs/TraCI/
4. **路网构建指南**: https://sumo.dlr.de/docs/Networks/Building_Networks.html
