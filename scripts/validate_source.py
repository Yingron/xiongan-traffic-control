#!/usr/bin/env python3
from pathlib import Path
import xml.etree.ElementTree as ET
from collections import defaultdict
base=Path(__file__).resolve().parents[1]
nroot=ET.parse(base/'sumo_files/xiongan.nod.xml').getroot()
eroot=ET.parse(base/'sumo_files/xiongan.edg.xml').getroot()
core={f'J{i:02d}' for i in range(1,21)}; inc=defaultdict(set); out=defaultdict(set)
for e in eroot.findall('edge'):
    a,b=e.get('from'),e.get('to'); out[a].add(b); inc[b].add(a)
for j in sorted(core):
    if len(inc[j])!=4 or len(out[j])!=4:
        raise SystemExit(f'{j} 不是四进口四出口: in={len(inc[j])}, out={len(out[j])}')
print('源拓扑检查通过：J01-J20 均为四进口、四出口。')
