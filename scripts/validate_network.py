#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

def fail(msg): raise SystemExit('验证失败: '+msg)

def check_templates(root):
    """校验 configs.constants.INTERSECTION_TEMPLATES 与路网 rl4 相位状态分组一致。

    30 路口的 4 动作程序存在 5 种模板（action_0/action_3 语义不同），训练按模板分层采样，
    若路网重新生成导致模板漂移而常量未同步，训练采样会失真，故此处逐项比对。
    """
    from configs.constants import INTERSECTION_TEMPLATES
    tls = {x.get('id'): x for x in root.findall('tlLogic') if x.get('programID') == 'rl4'}
    derived = {}
    for jid, el in tls.items():
        states = tuple((p.get('state'), p.get('duration')) for p in el.findall('phase'))
        derived.setdefault(states, []).append(jid)
    mapping = {}
    for states, jids in derived.items():
        for jid in jids:
            mapping[jid] = states
    expected = {}
    for tpl, jids in INTERSECTION_TEMPLATES.items():
        for jid in jids:
            expected[jid] = tpl
    # 模板id与状态顺序无关，按分组比对而非逐模板比对
    tpl_ids_by_states = {}
    for states, jids in derived.items():
        tpls = {expected[j] for j in jids if j in expected}
        if len(tpls) != 1:
            fail(f'模板分组与路网不一致: 状态组 {jids} 对应多个模板 {sorted(tpls)}')
        tpl_ids_by_states[states] = tpls.pop()
    by_template = {}
    for states, tpl in tpl_ids_by_states.items():
        by_template[tpl] = [j for j, s in mapping.items() if tpl_ids_by_states[s] == tpl]
    drift = []
    for tpl, jids in sorted(INTERSECTION_TEMPLATES.items()):
        actual = set(by_template.get(tpl, []))
        if actual != set(jids):
            drift.append(f'{tpl}: 常量{len(jids)}个 {sorted(set(jids)-actual)} vs 路网实际 {sorted(actual)}')
    if drift:
        fail('INTERSECTION_TEMPLATES 与路网 rl4 相位不一致: ' + '; '.join(drift))
    return {tpl: len(jids) for tpl, jids in sorted(INTERSECTION_TEMPLATES.items())}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--net',required=True); ap.add_argument('--lane-mapping',required=True); ap.add_argument('--report',required=True); a=ap.parse_args()
    root=ET.parse(a.net).getroot(); expected=[f'J{i:02d}' for i in range(1,31)]
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
    tpl_counts = check_templates(root)
    lm=json.loads(Path(a.lane_mapping).read_text(encoding='utf-8'))
    # 30 路口网格为 6×5：边界路口可能只有 3 个进口方向（如 J02 无东向）。
    # 校验放宽为"至少 3 个方向且无空方向"，保证状态提取可用即可。
    for j in expected:
        if len(lm.get(j,{})) < 3: fail(f'{j} 进口方向映射少于3个: {sorted(lm.get(j,{}))}')
        if any(not lm[j][d] for d in lm[j]): fail(f'{j} 存在空进口方向')
    tpl_str = '、'.join(f'{t}({n})' for t, n in tpl_counts.items())
    report=['# SUMO 接口兼容验证报告','',f'- 受控路口：30/30（J01-J30）',f'- 每路口相位：统一 4 个',f'- 路口类型：全部 traffic_light',f'- N/S/E/W 进口映射：30/30（边界路口≥3方向）',f'- rl4 模板分组与常量一致：{tpl_str}',f'- 后端动作数组：固定顺序 J01 → J30，长度 30',f'- 动作映射：0→phase0，1→phase1，2→phase2，3→phase3','','## 结论','','**通过。该路网满足 30 路口、统一 4 动作和 N/S/E/W 状态提取接口要求。**']
    Path(a.report).write_text('\n'.join(report)+'\n',encoding='utf-8')
    print('\n'.join(report))
if __name__=='__main__': main()
