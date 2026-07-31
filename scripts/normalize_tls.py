#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, math
from pathlib import Path
import xml.etree.ElementTree as ET

ACTIONS = {
    0: "南北直行及右转",
    1: "南北保护左转",
    2: "东西直行及右转",
    3: "东西保护左转",
}

def classify_approach(src_xy, j_xy):
    vx, vy = src_xy[0]-j_xy[0], src_xy[1]-j_xy[1]
    if abs(vx) >= abs(vy): return "E" if vx > 0 else "W"
    return "N" if vy > 0 else "S"

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--net',required=True)
    ap.add_argument('--lane-mapping',required=True)
    ap.add_argument('--tls-mapping',required=True)
    args=ap.parse_args()
    net=Path(args.net)
    ET.register_namespace('xsi','http://www.w3.org/2001/XMLSchema-instance')
    tree=ET.parse(net); root=tree.getroot()
    coords={j.get('id'):(float(j.get('x')),float(j.get('y'))) for j in root.findall('junction')}
    edge_nodes={e.get('id'):(e.get('from'),e.get('to')) for e in root.findall('edge') if e.get('function') is None}
    conns_by_tls={}
    for c in root.findall('connection'):
        tl=c.get('tl')
        if tl and tl.startswith('J'):
            conns_by_tls.setdefault(tl,[]).append(c)
    expected=[f'J{i:02d}' for i in range(1,21)]
    tls_nodes={j.get('id'):j for j in root.findall('junction') if j.get('id') in expected}
    missing=[j for j in expected if j not in conns_by_tls]
    if missing: raise SystemExit(f'缺少受控连接的信号灯: {missing}')
    existing={tl.get('id'):tl for tl in root.findall('tlLogic')}
    lane_mapping={}; tls_mapping={}
    for jid in expected:
        jxy=coords[jid]
        groups={0:[],1:[],2:[],3:[]}
        approaches={'N':set(),'S':set(),'E':set(),'W':set()}
        max_index=-1
        for c in conns_by_tls[jid]:
            idx=int(c.get('linkIndex')); max_index=max(max_index,idx)
            from_edge=c.get('from'); src,_=edge_nodes[from_edge]
            app=classify_approach(coords[src],jxy)
            approaches[app].add(from_edge)
            turn=(c.get('dir') or 's').lower()
            if app in ('N','S'):
                action=1 if turn=='l' else 0
            else:
                action=3 if turn=='l' else 2
            groups[action].append(idx)
        absent=[a for a,v in approaches.items() if not v]
        empty=[a for a,v in groups.items() if not v]
        if absent: raise SystemExit(f'{jid} 缺少进口方向: {absent}')
        if empty: raise SystemExit(f'{jid} 存在空动作相位: {empty}')
        n=max_index+1
        states=[]
        for action in range(4):
            s=['r']*n
            for idx in groups[action]: s[idx]='G'
            states.append(''.join(s))
        tl=existing.get(jid)
        if tl is None:
            tl=ET.Element('tlLogic',{'id':jid,'type':'static','programID':'rl4','offset':'0'})
            insert_at=next((i for i,x in enumerate(list(root)) if x.tag=='edge'),len(root))
            root.insert(insert_at,tl)
        else:
            tl.attrib.update({'type':'static','programID':'rl4','offset':'0'})
            for child in list(tl): tl.remove(child)
        durations=[30,12,30,12]
        for i,state in enumerate(states):
            ET.SubElement(tl,'phase',{'duration':str(durations[i]),'state':state,'name':f'action_{i}'})
        lane_counts={e.get('id'):len(e.findall('lane')) for e in root.findall('edge') if e.get('function') is None}
        lane_mapping[jid]={
            k: sorted(f'{e}_{lane}' for e in v for lane in range(lane_counts[e]))
            for k,v in approaches.items()
        }
        tls_mapping[jid]={
            'tls_id':jid,
            'action_to_phase':{str(i):i for i in range(4)},
            'action_semantics':{str(i):ACTIONS[i] for i in range(4)},
            'state_length':n,
            'phase_states':states,
        }
    tree.write(net,encoding='UTF-8',xml_declaration=True)
    Path(args.lane_mapping).write_text(json.dumps(lane_mapping,ensure_ascii=False,indent=2),encoding='utf-8')
    Path(args.tls_mapping).write_text(json.dumps(tls_mapping,ensure_ascii=False,indent=2),encoding='utf-8')
    print('已规范化 J01-J20：每个路口严格 4 个可控相位。')
if __name__=='__main__': main()
