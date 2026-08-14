"""
从20份赛题原始Excel提取流量和配时数据（J21–J30由30路口需求脚本镜像扩展）
"""
import os
import json
import pandas as pd
import numpy as np

def extract_flow_data(excel_path):
    """提取流量数据（兼容不同格式）"""
    df = pd.read_excel(excel_path, sheet_name='流量数据')
    
    # 提取早高峰流量（第2-9行，跳过非数值）
    peak_flows = {}
    directions = ['东进口', '西进口', '北进口', '南进口']
    turns = ['左转', '直行', '右转']
    
    for i, direction in enumerate(directions):
        peak_flows[direction] = {}
        for j, turn in enumerate(turns):
            col_idx = 2 + i * 3 + j
            # 获取数据并处理非数值
            values = []
            for row_idx in range(2, 10):
                val = df.iloc[row_idx, col_idx]
                if pd.notna(val) and isinstance(val, (int, float)):
                    values.append(val)
            
            if values:
                avg_flow = int(np.mean(values))
            else:
                avg_flow = 0
            peak_flows[direction][turn] = avg_flow
    
    # 提取转向比例（第11行）
    turn_ratios = {}
    for i, direction in enumerate(directions):
        turn_ratios[direction] = {}
        total_flow = sum(peak_flows[direction].values())
        
        for j, turn in enumerate(turns):
            col_idx = 2 + i * 3 + j
            val = df.iloc[11, col_idx]
            
            if pd.notna(val) and isinstance(val, (int, float)):
                ratio = float(val)
            else:
                # 如果没有比例数据，计算比例
                if total_flow > 0:
                    ratio = peak_flows[direction][turn] / total_flow
                else:
                    ratio = 0.0
            turn_ratios[direction][turn] = ratio
    
    return peak_flows, turn_ratios

def extract_timing_data(excel_path):
    """提取配时数据（兼容不同Sheet名称和相位数量）"""
    # 尝试多种Sheet名称
    sheet_names = ['信号配时数据', '配信号时数据', '信号配时', '配时数据']
    
    timing_sheet = None
    xls = pd.ExcelFile(excel_path)
    for name in sheet_names:
        if name in xls.sheet_names:
            timing_sheet = name
            break
    
    if timing_sheet is None:
        print(f'  ⚠️ 未找到配时Sheet，使用默认值')
        return {
            'peak': {
                '东西向直行': {'green': 30, 'yellow': 3, 'red': 2, 'total': 35},
                '东西向左转': {'green': 20, 'yellow': 3, 'red': 2, 'total': 25},
                '南北向直行': {'green': 30, 'yellow': 3, 'red': 2, 'total': 35},
                '南北向左转': {'green': 20, 'yellow': 3, 'red': 2, 'total': 25},
                'cycle': 120
            },
            'offpeak': {
                '东西向直行': {'green': 25, 'yellow': 3, 'red': 2, 'total': 30},
                '东西向左转': {'green': 15, 'yellow': 3, 'red': 2, 'total': 20},
                '南北向直行': {'green': 25, 'yellow': 3, 'red': 2, 'total': 30},
                '南北向左转': {'green': 15, 'yellow': 3, 'red': 2, 'total': 20},
                'cycle': 100
            },
            'evening': {
                '东西向直行': {'green': 28, 'yellow': 3, 'red': 2, 'total': 33},
                '东西向左转': {'green': 18, 'yellow': 3, 'red': 2, 'total': 23},
                '南北向直行': {'green': 28, 'yellow': 3, 'red': 2, 'total': 33},
                '南北向左转': {'green': 18, 'yellow': 3, 'red': 2, 'total': 23},
                'cycle': 112
            }
        }
    
    df = pd.read_excel(excel_path, sheet_name=timing_sheet)
    
    timing_plans = {}
    
    # 提取早高峰配时（第1-4行或更多，直到下一个时段）
    peak_phases = {}
    cycle = 0
    row_idx = 1
    while row_idx < len(df):
        val = df.iloc[row_idx, 0]  # 时段分类
        if pd.notna(val) and val != '早高峰':
            break
        
        phase_name = df.iloc[row_idx, 3] if pd.notna(df.iloc[row_idx, 3]) else f'相位{row_idx}'
        green = int(df.iloc[row_idx, 4]) if pd.notna(df.iloc[row_idx, 4]) else 30
        yellow = int(df.iloc[row_idx, 5]) if pd.notna(df.iloc[row_idx, 5]) else 3
        red = int(df.iloc[row_idx, 6]) if pd.notna(df.iloc[row_idx, 6]) else 2
        total = int(df.iloc[row_idx, 7]) if pd.notna(df.iloc[row_idx, 7]) else green + yellow + red
        
        peak_phases[phase_name] = {
            'green': green,
            'yellow': yellow,
            'red': red,
            'total': total
        }
        
        cycle_val = df.iloc[row_idx, 8]
        if pd.notna(cycle_val) and isinstance(cycle_val, (int, float)):
            cycle = int(cycle_val)
        
        row_idx += 1
    
    if cycle == 0:
        cycle = sum(p['total'] for p in peak_phases.values())
    
    timing_plans['peak'] = peak_phases
    timing_plans['peak']['cycle'] = cycle
    
    # 提取平峰配时（继续向后找）
    offpeak_phases = {}
    cycle = 0
    while row_idx < len(df):
        val = df.iloc[row_idx, 0]  # 时段分类
        if pd.notna(val) and val != '平峰':
            break
        
        phase_name = df.iloc[row_idx, 3] if pd.notna(df.iloc[row_idx, 3]) else f'相位{row_idx}'
        green = int(df.iloc[row_idx, 4]) if pd.notna(df.iloc[row_idx, 4]) else 25
        yellow = int(df.iloc[row_idx, 5]) if pd.notna(df.iloc[row_idx, 5]) else 3
        red = int(df.iloc[row_idx, 6]) if pd.notna(df.iloc[row_idx, 6]) else 2
        total = int(df.iloc[row_idx, 7]) if pd.notna(df.iloc[row_idx, 7]) else green + yellow + red
        
        offpeak_phases[phase_name] = {
            'green': green,
            'yellow': yellow,
            'red': red,
            'total': total
        }
        
        cycle_val = df.iloc[row_idx, 8]
        if pd.notna(cycle_val) and isinstance(cycle_val, (int, float)):
            cycle = int(cycle_val)
        
        row_idx += 1
    
    if cycle == 0:
        cycle = sum(p['total'] for p in offpeak_phases.values())
    
    timing_plans['offpeak'] = offpeak_phases
    timing_plans['offpeak']['cycle'] = cycle
    
    # 提取晚高峰配时（继续向后找）
    evening_phases = {}
    cycle = 0
    while row_idx < len(df):
        val = df.iloc[row_idx, 0]  # 时段分类
        if pd.notna(val) and val != '晚高峰':
            break
        
        phase_name = df.iloc[row_idx, 3] if pd.notna(df.iloc[row_idx, 3]) else f'相位{row_idx}'
        green = int(df.iloc[row_idx, 4]) if pd.notna(df.iloc[row_idx, 4]) else 28
        yellow = int(df.iloc[row_idx, 5]) if pd.notna(df.iloc[row_idx, 5]) else 3
        red = int(df.iloc[row_idx, 6]) if pd.notna(df.iloc[row_idx, 6]) else 2
        total = int(df.iloc[row_idx, 7]) if pd.notna(df.iloc[row_idx, 7]) else green + yellow + red
        
        evening_phases[phase_name] = {
            'green': green,
            'yellow': yellow,
            'red': red,
            'total': total
        }
        
        cycle_val = df.iloc[row_idx, 8]
        if pd.notna(cycle_val) and isinstance(cycle_val, (int, float)):
            cycle = int(cycle_val)
        
        row_idx += 1
    
    # 如果晚高峰数据不存在，使用早高峰数据
    if not evening_phases:
        evening_phases = peak_phases.copy()
        cycle = timing_plans['peak']['cycle']
    
    if cycle == 0:
        cycle = sum(p['total'] for p in evening_phases.values())
    
    timing_plans['evening'] = evening_phases
    timing_plans['evening']['cycle'] = cycle
    
    return timing_plans

def main():
    base_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                            '赛题资料', '路口数据')
    all_data = {}
    
    print("=" * 60)
    print("开始提取20份赛题原始路口数据（30路口扩展由 generate_real_demand_scenarios.py 完成）")
    print("=" * 60)
    
    for i in range(1, 21):
        excel_path = os.path.join(base_dir, str(i), '路口数据', f'demo_{i}流量和交叉口配时方案.xlsx')
        
        if not os.path.exists(excel_path):
            print(f'⚠️ 未找到文件: {excel_path}')
            continue
        
        print(f'\n📊 处理路口 {i}...')
        
        try:
            flows, ratios = extract_flow_data(excel_path)
            timing = extract_timing_data(excel_path)
            
            all_data[f'J{i:02d}'] = {
                'flows': flows,
                'turn_ratios': ratios,
                'timing': timing
            }
            
            # 打印摘要
            print(f'   早高峰周期: {timing["peak"]["cycle"]}秒')
            print(f'   相位数量: {len([k for k in timing["peak"].keys() if k != "cycle"])}')
            print(f'   东进口: {flows["东进口"]}')
            print(f'   西进口: {flows["西进口"]}')
            print(f'   北进口: {flows["北进口"]}')
            print(f'   南进口: {flows["南进口"]}')
            
        except Exception as e:
            print(f'❌ 处理路口 {i} 失败: {e}')
            import traceback
            traceback.print_exc()
    
    # 保存数据
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
    os.makedirs(data_dir, exist_ok=True)
    
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
    
    csv_path = os.path.join(data_dir, 'intersections_data.csv')
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding='utf-8-sig')
    print(f'\n✅ 保存到 {csv_path}')
    
    # JSON格式 - 流量数据
    flows_path = os.path.join(data_dir, 'traffic_flows.json')
    with open(flows_path, 'w', encoding='utf-8') as f:
        json.dump({k: v['flows'] for k, v in all_data.items()}, f, ensure_ascii=False, indent=2)
    print(f'✅ 保存到 {flows_path}')
    
    # JSON格式 - 配时方案
    timing_path = os.path.join(data_dir, 'timing_plans.json')
    with open(timing_path, 'w', encoding='utf-8') as f:
        json.dump({k: v['timing'] for k, v in all_data.items()}, f, ensure_ascii=False, indent=2)
    print(f'✅ 保存到 {timing_path}')
    
    print(f'\n' + "=" * 60)
    print(f'📈 共处理 {len(all_data)} 个路口')
    print("=" * 60)

if __name__ == '__main__':
    main()
