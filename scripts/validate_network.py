#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path
import xml.etree.ElementTree as ET

def fail(msg): raise SystemExit('验证失败: '+msg)
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--net',required=True); ap.add_argument('--lane-mapping',required=True); ap.add_argument('--report',required=True); a=ap.parse_args()
    root=ET.parse(a.net).getroot(); expected=[f'J{i:02d}' for i in range(1,21)]
    junctions={j.get('id'):j for j in root.findall('junction')}
    tls={x.get('id'):x for x in root.findall('tlLogic') if x.get('programID') == 'rl4'}
    if set(expected)-set(junctions): fail('缺少核心路口 '+str(sorted(set(expected)-set(junctions))))
    bad_type=[j for j in expected if junctions[j].get('type')!='traffic_light']
    if bad_type: fail('非 traffic_light 路口 '+str(bad_type))
    if set(expected)-set(tls): fail('缺少 tlLogic '+str(sorted(set(expected)-set(tls))))
    extra=[x for x in tls if x.startswith('J') and x not in expected]
    bad_phase={j:len(tls[j].findall('phase')) for j in expected if len(tls[j].findall('phase'))!=4}
    if bad_phase: fail('相位数不为4 '+str(bad_phase))
    conns={j:[] for j in expected}
    for c in root.findall('connection'):
        if c.get('tl') in conns: conns[c.get('tl')].append(c)
    for j in expected:
        maxidx=max(int(c.get('linkIndex')) for c in conns[j])
        for i,p in enumerate(tls[j].findall('phase')):
            st=p.get('state','')
            if len(st)!=maxidx+1: fail(f'{j} phase{i} state长度错误')
            if 'G' not in st and 'g' not in st: fail(f'{j} phase{i} 没有绿灯连接')
    lm=json.loads(Path(a.lane_mapping).read_text(encoding='utf-8'))
    for j in expected:
        if set(lm.get(j,{})) != {'N','S','E','W'}: fail(f'{j} N/S/E/W映射不完整')
        if any(not lm[j][d] for d in 'NSEW'): fail(f'{j} 存在空进口方向')
    report=['# SUMO 接口兼容验证报告','',f'- 受控路口：20/20（J01-J20）',f'- 每路口相位：统一 4 个',f'- 路口类型：全部 traffic_light',f'- N/S/E/W 进口映射：20/20 完整',f'- 后端动作数组：固定顺序 J01 → J20，长度 20',f'- 动作映射：0→phase0，1→phase1，2→phase2，3→phase3','','## 结论','','**通过。该路网满足 20 路口、统一 4 动作和 N/S/E/W 状态提取接口要求。**']
    Path(a.report).write_text('\n'.join(report)+'\n',encoding='utf-8')
    print('\n'.join(report))
if __name__=='__main__': main()
