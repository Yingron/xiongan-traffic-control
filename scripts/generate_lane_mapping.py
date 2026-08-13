"""为 30 路口路网生成 docs/lane_mapping.json（按几何方位推断 N/S/E/W）

新路网 xiongan_30.edg.xml 的边名为 e_{from}_{to}，无法从边名前缀推断方位，
因此基于 xiongan_30.nod.xml 的节点坐标：对每个信号路口，遍历所有驶向该路口的
边（to == 路口），按 from 节点相对路口的方位分类为 N/S/E/W，车道 = 边_0 / 边_1。

运行时 env/global_state.py::_extract_intersection_state 会与 TraCI 的
getControlledLanes 取交集，所以这里多列出的边不会污染状态。

用法:
    python scripts/generate_lane_mapping.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUMO_FILES_DIR = PROJECT_ROOT / "sumo_files"
DOCS_DIR = PROJECT_ROOT / "docs"
NOD_FILE = "xiongan_30.nod.xml"
EDG_FILE = "xiongan_30.edg.xml"
OUT_FILE = DOCS_DIR / "lane_mapping.json"

DIRECTIONS = ("N", "S", "E", "W")


def _classify_side(from_xy: tuple[float, float], junction_xy: tuple[float, float]) -> str | None:
    """from 节点相对 junction 的方位（绝对值判主方向）"""
    dx = from_xy[0] - junction_xy[0]
    dy = from_xy[1] - junction_xy[1]
    if abs(dx) >= abs(dy):
        return "E" if dx > 0 else "W" if dx < 0 else None
    return "N" if dy > 0 else "S" if dy < 0 else None


def main() -> None:
    nod = (SUMO_FILES_DIR / NOD_FILE).read_text(encoding="utf-8")
    edg = (SUMO_FILES_DIR / EDG_FILE).read_text(encoding="utf-8")

    nodes = {m.group(1): (float(m.group(2)), float(m.group(3)))
             for m in re.finditer(r'<node id="([^"]+)" x="([^"]+)" y="([^"]+)"', nod)}
    edges = [(m.group(1), m.group(2), m.group(3))
             for m in re.finditer(r'<edge id="([^"]+)" from="([^"]+)" to="([^"]+)"', edg)]

    junctions = sorted(nid for nid in nodes if re.fullmatch(r"J\d{2}", nid))
    mapping: dict[str, dict[str, list[str]]] = {}
    for j in junctions:
        approach: dict[str, list[str]] = {d: [] for d in DIRECTIONS}
        for eid, frm, to in edges:
            if to != j or frm not in nodes:
                continue
            side = _classify_side(nodes[frm], nodes[j])
            if side:
                approach[side].extend([f"{eid}_0", f"{eid}_1"])
        # 去掉不存在的方位键，与旧格式一致（T 型路口缺一侧）
        mapping[j] = {d: lanes for d, lanes in approach.items() if lanes}

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[OK] {OUT_FILE.name}: {len(mapping)} intersections")
    for j in ["J01", "J02", "J05", "J21", "J30"]:
        print(f"   {j}: {mapping[j]}")


if __name__ == "__main__":
    main()
