"""
生成20路口SUMO路网文件（完整版）

> ⚠️ 已废弃：本脚本生成的是旧版 20 路口（5×4）路网。当前项目以 30 路口
> （6×5，J01–J30）路网为准，路网文件为仓库内已提交的 sumo_files/xiongan_30.*
> 系列（nod/edg/net/rou/sumocfg 均保留）。运行本脚本会重建已删除的
> xiongan_20.* 旧文件，仅保留作历史参考。

使用netconvert工具配合nod.xml和edg.xml文件生成路网，避免手动编写复杂的net.xml

路网布局设计：
- 5×4网格布局，共20个路口（J01-J20）
- 路口间距200m（窄路密网）
- 每条道路2条车道
- 每个路口4相位信号灯

边缘ID分配规则（从net.xml实际观察）：
水平道路（每行6条道路）:
  行0 (J01-J05): E0, E1, E2, E3, E4, E5
  行1 (J06-J10): E6, E7, E8, E9, E10, E11
  行2 (J11-J15): E12, E13, E14, E15, E16, E17
  行3 (J16-J20): E18, E19, E20, E21, E22, E23

垂直道路（每列5条道路）:
  列0 (J01,J06,J11,J16): E24, E25, E26, E27, E28
  列1 (J02,J07,J12,J17): E29, E30, E31, E32, E33
  列2 (J03,J08,J13,J18): E34, E35, E36, E37, E38
  列3 (J04,J09,J14,J19): E39, E40, E41, E42, E43
  列4 (J05,J10,J15,J20): E44, E45, E46, E47, E48
"""
import os
import json

def generate_nod_xml(num_intersections=20):
    """生成nod.xml文件（路口节点定义）"""
    rows = 4  # 4行
    cols = 5  # 5列
    spacing = 200  # 路口间距200m
    
    lines = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append('<nodes xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="http://sumo.dlr.de/xsd/nodes_file.xsd">')
    
    for row in range(rows):
        for col in range(cols):
            node_id = f'J{(row*cols + col + 1):02d}'
            x = col * spacing
            y = (rows - 1 - row) * spacing
            lines.append(f'    <node id="{node_id}" x="{x}" y="{y}" type="traffic_light"/>')
    
    # 添加外围的dead_end节点（用于流量入口/出口）
    for col in range(cols):
        # 北边入口
        node_id = f'J_N{col}'
        x = col * spacing
        y = rows * spacing
        lines.append(f'    <node id="{node_id}" x="{x}" y="{y}" type="dead_end"/>')
        
        # 南边出口
        node_id = f'J_S{col}'
        x = col * spacing
        y = -spacing
        lines.append(f'    <node id="{node_id}" x="{x}" y="{y}" type="dead_end"/>')
    
    for row in range(rows):
        # 西边入口
        node_id = f'J_W{row}'
        x = -spacing
        y = (rows - 1 - row) * spacing
        lines.append(f'    <node id="{node_id}" x="{x}" y="{y}" type="dead_end"/>')
        
        # 东边出口
        node_id = f'J_E{row}'
        x = cols * spacing
        y = (rows - 1 - row) * spacing
        lines.append(f'    <node id="{node_id}" x="{x}" y="{y}" type="dead_end"/>')
    
    lines.append('</nodes>')
    
    return '\n'.join(lines)

def generate_edg_xml(num_intersections=20):
    """生成edg.xml文件（道路定义）"""
    rows = 4
    cols = 5
    spacing = 200
    
    lines = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append('<edges xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="http://sumo.dlr.de/xsd/edges_file.xsd">')
    
    edge_id = 0
    
    # 水平道路（东西向）- 每行6条道路
    for row in range(rows):
        # 内部水平道路（连接路口）- 每行cols-1条
        for col in range(cols - 1):
            from_node = f'J{(row*cols + col + 1):02d}'
            to_node = f'J{(row*cols + col + 2):02d}'
            
            # 东向道路（正向）
            lines.append(f'    <edge id="E{edge_id}" from="{from_node}" to="{to_node}" priority="-1" numLanes="2" speed="13.89" length="{spacing}"/>')
            # 西向道路（反向）
            lines.append(f'    <edge id="-E{edge_id}" from="{to_node}" to="{from_node}" priority="-1" numLanes="2" speed="13.89" length="{spacing}"/>')
            edge_id += 1
        
        # 西边边界道路（连接外围节点到第一个路口）
        from_node = f'J_W{row}'
        to_node = f'J{(row*cols + 1):02d}'
        lines.append(f'    <edge id="E{edge_id}" from="{from_node}" to="{to_node}" priority="-1" numLanes="2" speed="13.89" length="{spacing}"/>')
        lines.append(f'    <edge id="-E{edge_id}" from="{to_node}" to="{from_node}" priority="-1" numLanes="2" speed="13.89" length="{spacing}"/>')
        edge_id += 1
        
        # 东边边界道路（连接最后一个路口到外围节点）
        from_node = f'J{(row*cols + cols):02d}'
        to_node = f'J_E{row}'
        lines.append(f'    <edge id="E{edge_id}" from="{from_node}" to="{to_node}" priority="-1" numLanes="2" speed="13.89" length="{spacing}"/>')
        lines.append(f'    <edge id="-E{edge_id}" from="{to_node}" to="{from_node}" priority="-1" numLanes="2" speed="13.89" length="{spacing}"/>')
        edge_id += 1
    
    # 垂直道路（南北向）- 每列5条道路
    for col in range(cols):
        # 内部垂直道路（连接路口）- 每列rows-1条
        for row in range(rows - 1):
            from_node = f'J{(row*cols + col + 1):02d}'
            to_node = f'J{((row+1)*cols + col + 1):02d}'
            
            # 南向道路（正向）
            lines.append(f'    <edge id="E{edge_id}" from="{from_node}" to="{to_node}" priority="-1" numLanes="2" speed="13.89" length="{spacing}"/>')
            # 北向道路（反向）
            lines.append(f'    <edge id="-E{edge_id}" from="{to_node}" to="{from_node}" priority="-1" numLanes="2" speed="13.89" length="{spacing}"/>')
            edge_id += 1
        
        # 北边边界道路（连接外围节点到第一个路口）
        from_node = f'J_N{col}'
        to_node = f'J{(0*cols + col + 1):02d}'
        lines.append(f'    <edge id="E{edge_id}" from="{from_node}" to="{to_node}" priority="-1" numLanes="2" speed="13.89" length="{spacing}"/>')
        lines.append(f'    <edge id="-E{edge_id}" from="{to_node}" to="{from_node}" priority="-1" numLanes="2" speed="13.89" length="{spacing}"/>')
        edge_id += 1
        
        # 南边边界道路（连接最后一个路口到外围节点）
        from_node = f'J{((rows-1)*cols + col + 1):02d}'
        to_node = f'J_S{col}'
        lines.append(f'    <edge id="E{edge_id}" from="{from_node}" to="{to_node}" priority="-1" numLanes="2" speed="13.89" length="{spacing}"/>')
        lines.append(f'    <edge id="-E{edge_id}" from="{to_node}" to="{from_node}" priority="-1" numLanes="2" speed="13.89" length="{spacing}"/>')
        edge_id += 1
    
    lines.append('</edges>')
    
    return '\n'.join(lines)

def generate_type_xml():
    """生成type.xml文件（车辆类型定义）"""
    return '''<?xml version="1.0" encoding="UTF-8"?>
<types xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="http://sumo.dlr.de/xsd/types_file.xsd">
    <vType id="car" accel="2.6" decel="4.5" sigma="0.5" length="5" maxSpeed="13.89"/>
</types>'''

def generate_rou_xml(traffic_flows):
    """生成rou.xml文件（基于提取的流量数据）"""
    rows = 4
    cols = 5
    
    lines = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append('<routes xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="http://sumo.dlr.de/xsd/routes_file.xsd">')
    lines.append('    <vType id="car" accel="2.6" decel="4.5" sigma="0.5" length="5" maxSpeed="13.89"/>')
    lines.append('')
    lines.append('    <!-- 路由定义 -->')
    
    # 辅助函数：获取水平边缘ID
    def get_horizontal_edge(row, index, eastbound):
        """获取水平边缘ID"""
        edge_id = row * 6 + index
        if eastbound:
            return f'E{edge_id}'
        else:
            return f'-E{edge_id}'
    
    # 辅助函数：获取垂直边缘ID
    def get_vertical_edge(col, index, southbound):
        """获取垂直边缘ID"""
        edge_id = rows * 6 + col * 5 + index
        if southbound:
            return f'E{edge_id}'
        else:
            return f'-E{edge_id}'
    
    # 生成路由和流量
    flow_id = 0
    
    for row in range(rows):
        for col in range(cols):
            tl_id = f'J{(row*cols + col + 1):02d}'
            
            if tl_id not in traffic_flows:
                continue
            
            flows_data = traffic_flows[tl_id]
            
            # 东进口（从西边来）
            direction = '东进口'
            if direction in flows_data:
                # 入边缘：从西边相邻路口或外围入口来
                if col == 0:
                    in_edge = get_horizontal_edge(row, 4, True)
                else:
                    in_edge = get_horizontal_edge(row, col - 1, True)
                
                # 直行向东
                straight_flow = flows_data[direction].get('直行', 0)
                if straight_flow > 0:
                    if col < cols - 1:
                        out_edge = get_horizontal_edge(row, col, True)
                    else:
                        out_edge = get_horizontal_edge(row, 5, True)
                    route_name = f'route_{flow_id}'
                    lines.append(f'    <route id="{route_name}" edges="{in_edge} {out_edge}"/>')
                    lines.append(f'    <flow id="flow_{flow_id}" route="{route_name}" type="car" begin="0" end="3600" number="{straight_flow}"/>')
                    flow_id += 1
                
                # 左转向南
                left_flow = flows_data[direction].get('左转', 0)
                if left_flow > 0:
                    if row < rows - 1:
                        out_edge = get_vertical_edge(col, row, True)
                    else:
                        out_edge = get_vertical_edge(col, 4, True)
                    route_name = f'route_{flow_id}'
                    lines.append(f'    <route id="{route_name}" edges="{in_edge} {out_edge}"/>')
                    lines.append(f'    <flow id="flow_{flow_id}" route="{route_name}" type="car" begin="0" end="3600" number="{left_flow}"/>')
                    flow_id += 1
                
                # 右转向北
                right_flow = flows_data[direction].get('右转', 0)
                if right_flow > 0:
                    if row > 0:
                        out_edge = get_vertical_edge(col, row - 1, False)
                    else:
                        out_edge = get_vertical_edge(col, 3, False)
                    route_name = f'route_{flow_id}'
                    lines.append(f'    <route id="{route_name}" edges="{in_edge} {out_edge}"/>')
                    lines.append(f'    <flow id="flow_{flow_id}" route="{route_name}" type="car" begin="0" end="3600" number="{right_flow}"/>')
                    flow_id += 1
            
            # 西进口（从东边来）
            direction = '西进口'
            if direction in flows_data:
                # 入边缘：从东边相邻路口或外围入口来
                if col == cols - 1:
                    in_edge = get_horizontal_edge(row, 5, False)
                else:
                    in_edge = get_horizontal_edge(row, col, False)
                
                # 直行向西
                straight_flow = flows_data[direction].get('直行', 0)
                if straight_flow > 0:
                    if col > 0:
                        out_edge = get_horizontal_edge(row, col - 1, False)
                    else:
                        out_edge = get_horizontal_edge(row, 4, False)
                    route_name = f'route_{flow_id}'
                    lines.append(f'    <route id="{route_name}" edges="{in_edge} {out_edge}"/>')
                    lines.append(f'    <flow id="flow_{flow_id}" route="{route_name}" type="car" begin="0" end="3600" number="{straight_flow}"/>')
                    flow_id += 1
                
                # 左转向北
                left_flow = flows_data[direction].get('左转', 0)
                if left_flow > 0:
                    if row > 0:
                        out_edge = get_vertical_edge(col, row - 1, False)
                    else:
                        out_edge = get_vertical_edge(col, 3, False)
                    route_name = f'route_{flow_id}'
                    lines.append(f'    <route id="{route_name}" edges="{in_edge} {out_edge}"/>')
                    lines.append(f'    <flow id="flow_{flow_id}" route="{route_name}" type="car" begin="0" end="3600" number="{left_flow}"/>')
                    flow_id += 1
                
                # 右转向南
                right_flow = flows_data[direction].get('右转', 0)
                if right_flow > 0:
                    if row < rows - 1:
                        out_edge = get_vertical_edge(col, row, True)
                    else:
                        out_edge = get_vertical_edge(col, 4, True)
                    route_name = f'route_{flow_id}'
                    lines.append(f'    <route id="{route_name}" edges="{in_edge} {out_edge}"/>')
                    lines.append(f'    <flow id="flow_{flow_id}" route="{route_name}" type="car" begin="0" end="3600" number="{right_flow}"/>')
                    flow_id += 1
            
            # 北进口（从北边来）
            direction = '北进口'
            if direction in flows_data:
                # 入边缘：从北边相邻路口或外围入口来
                if row == 0:
                    in_edge = get_vertical_edge(col, 3, True)
                else:
                    in_edge = get_vertical_edge(col, row - 1, True)
                
                # 直行向南
                straight_flow = flows_data[direction].get('直行', 0)
                if straight_flow > 0:
                    if row < rows - 1:
                        out_edge = get_vertical_edge(col, row, True)
                    else:
                        out_edge = get_vertical_edge(col, 4, True)
                    route_name = f'route_{flow_id}'
                    lines.append(f'    <route id="{route_name}" edges="{in_edge} {out_edge}"/>')
                    lines.append(f'    <flow id="flow_{flow_id}" route="{route_name}" type="car" begin="0" end="3600" number="{straight_flow}"/>')
                    flow_id += 1
                
                # 左转向西
                left_flow = flows_data[direction].get('左转', 0)
                if left_flow > 0:
                    if col > 0:
                        out_edge = get_horizontal_edge(row, col - 1, False)
                    else:
                        out_edge = get_horizontal_edge(row, 4, False)
                    route_name = f'route_{flow_id}'
                    lines.append(f'    <route id="{route_name}" edges="{in_edge} {out_edge}"/>')
                    lines.append(f'    <flow id="flow_{flow_id}" route="{route_name}" type="car" begin="0" end="3600" number="{left_flow}"/>')
                    flow_id += 1
                
                # 右转向东
                right_flow = flows_data[direction].get('右转', 0)
                if right_flow > 0:
                    if col < cols - 1:
                        out_edge = get_horizontal_edge(row, col, True)
                    else:
                        out_edge = get_horizontal_edge(row, 5, True)
                    route_name = f'route_{flow_id}'
                    lines.append(f'    <route id="{route_name}" edges="{in_edge} {out_edge}"/>')
                    lines.append(f'    <flow id="flow_{flow_id}" route="{route_name}" type="car" begin="0" end="3600" number="{right_flow}"/>')
                    flow_id += 1
            
            # 南进口（从南边来）
            direction = '南进口'
            if direction in flows_data:
                # 入边缘：从南边相邻路口或外围入口来
                if row == rows - 1:
                    in_edge = get_vertical_edge(col, 4, False)
                else:
                    in_edge = get_vertical_edge(col, row, False)
                
                # 直行向北
                straight_flow = flows_data[direction].get('直行', 0)
                if straight_flow > 0:
                    if row > 0:
                        out_edge = get_vertical_edge(col, row - 1, False)
                    else:
                        out_edge = get_vertical_edge(col, 3, False)
                    route_name = f'route_{flow_id}'
                    lines.append(f'    <route id="{route_name}" edges="{in_edge} {out_edge}"/>')
                    lines.append(f'    <flow id="flow_{flow_id}" route="{route_name}" type="car" begin="0" end="3600" number="{straight_flow}"/>')
                    flow_id += 1
                
                # 左转向东
                left_flow = flows_data[direction].get('左转', 0)
                if left_flow > 0:
                    if col < cols - 1:
                        out_edge = get_horizontal_edge(row, col, True)
                    else:
                        out_edge = get_horizontal_edge(row, 5, True)
                    route_name = f'route_{flow_id}'
                    lines.append(f'    <route id="{route_name}" edges="{in_edge} {out_edge}"/>')
                    lines.append(f'    <flow id="flow_{flow_id}" route="{route_name}" type="car" begin="0" end="3600" number="{left_flow}"/>')
                    flow_id += 1
                
                # 右转向西
                right_flow = flows_data[direction].get('右转', 0)
                if right_flow > 0:
                    if col > 0:
                        out_edge = get_horizontal_edge(row, col - 1, False)
                    else:
                        out_edge = get_horizontal_edge(row, 4, False)
                    route_name = f'route_{flow_id}'
                    lines.append(f'    <route id="{route_name}" edges="{in_edge} {out_edge}"/>')
                    lines.append(f'    <flow id="flow_{flow_id}" route="{route_name}" type="car" begin="0" end="3600" number="{right_flow}"/>')
                    flow_id += 1
    
    lines.append('</routes>')
    
    return '\n'.join(lines)

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
    sumo_files_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'sumo_files')
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
    
    os.makedirs(sumo_files_dir, exist_ok=True)
    
    print("=" * 60)
    print("🚀 开始生成20路口SUMO路网（5×4网格）")
    print("=" * 60)
    
    # 1. 生成nod.xml
    print('\n🔧 生成节点文件...')
    nod_xml = generate_nod_xml(20)
    nod_path = os.path.join(sumo_files_dir, 'xiongan_20.nod.xml')
    with open(nod_path, 'w', encoding='utf-8') as f:
        f.write(nod_xml)
    print(f'✅ 保存到 {nod_path}')
    
    # 2. 生成edg.xml
    print('\n🔧 生成道路文件...')
    edg_xml = generate_edg_xml(20)
    edg_path = os.path.join(sumo_files_dir, 'xiongan_20.edg.xml')
    with open(edg_path, 'w', encoding='utf-8') as f:
        f.write(edg_xml)
    print(f'✅ 保存到 {edg_path}')
    
    # 3. 使用netconvert生成net.xml
    print('\n🔧 使用netconvert生成路网...')
    net_path = os.path.join(sumo_files_dir, 'xiongan_20.net.xml')
    netconvert_cmd = f'netconvert --node-files {nod_path} --edge-files {edg_path} --output-file {net_path}'
    os.system(netconvert_cmd)
    
    # 检查net.xml是否生成成功
    if os.path.exists(net_path):
        print(f'✅ 保存到 {net_path}')
    else:
        print(f'❌ 路网生成失败！')
        return
    
    # 4. 读取流量数据并生成rou.xml
    print('\n🔧 生成流量文件...')
    traffic_flows = {}
    flows_path = os.path.join(data_dir, 'traffic_flows.json')
    if os.path.exists(flows_path):
        with open(flows_path, 'r', encoding='utf-8') as f:
            traffic_flows = json.load(f)
        print(f'📥 已加载流量数据（{len(traffic_flows)}个路口）')
    else:
        print('⚠️ 未找到流量数据，使用默认值')
    
    rou_xml = generate_rou_xml(traffic_flows)
    rou_path = os.path.join(sumo_files_dir, 'xiongan_20.rou.xml')
    with open(rou_path, 'w', encoding='utf-8') as f:
        f.write(rou_xml)
    print(f'✅ 保存到 {rou_path}')
    
    # 5. 生成type.xml
    print('\n🔧 生成车辆类型文件...')
    type_xml = generate_type_xml()
    type_path = os.path.join(sumo_files_dir, 'xiongan_20.type.xml')
    with open(type_path, 'w', encoding='utf-8') as f:
        f.write(type_xml)
    print(f'✅ 保存到 {type_path}')
    
    # 6. 生成sumocfg
    print('\n🔧 生成仿真配置...')
    sumocfg = generate_sumocfg()
    sumocfg_path = os.path.join(sumo_files_dir, 'xiongan_20.sumocfg')
    with open(sumocfg_path, 'w', encoding='utf-8') as f:
        f.write(sumocfg)
    print(f'✅ 保存到 {sumocfg_path}')
    
    print('\n' + "=" * 60)
    print('🎉 路网生成完成！')
    print('📁 文件位置: sumo_files/xiongan_20.*')
    print('\n📋 验证命令：')
    print(f'   非GUI模式: sumo -c {sumocfg_path}')
    print(f'   GUI模式: sumo-gui -c {sumocfg_path}')
    print("=" * 60)

if __name__ == '__main__':
    main()