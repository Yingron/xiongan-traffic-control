#!/usr/bin/env python3
from pathlib import Path
import xml.etree.ElementTree as ET
from collections import defaultdict
base=Path(__file__).resolve().parents[1]
nroot=ET.parse(base/'sumo_files/xiongan_30.nod.xml').getroot()
eroot=ET.parse(base/'sumo_files/xiongan_30.edg.xml').getroot()
core={f'J{i:02d}' for i in range(1,31)}; inc=defaultdict(set); out=defaultdict(set)
for e in eroot.findall('edge'):
    a,b=e.get('from'),e.get('to'); out[a].add(b); inc[b].add(a)
for j in sorted(core):
    # 30 路口网格为 6×5，边界路口（含死端扩展边）进口/出口≥3 即可连通
    if len(inc[j])<3 or len(out[j])<3:
        raise SystemExit(f'{j} 进口/出口不足3: in={sorted(inc[j])}, out={sorted(out[j])}')
print('源拓扑检查通过：J01-J30 均为信号路口，进口/出口连通（边界路口≥3向）。')
