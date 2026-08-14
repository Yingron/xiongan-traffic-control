"""基于赛题真实 xlsx 流量数据生成 30 路口训练场景（早/平/晚高峰）

背景（历史问题）:
1. 旧脚本 scripts/generate_road_network.py 的 generate_rou_xml 把 xlsx 中
   "每 15 分钟 pcu" 直接当作 "3600 秒内车辆数" 使用（xiongan_20.rou.xml
   总和 9552，而真实折算应为 ~38208 pcu/h），需求低估约 4 倍；
2. 手工场景 xiongan_flat/morning/evening.rou.xml 的需求只有真实数据的
   1/22 ~ 1/37，导致路网从不拥堵、DQN 无排队/等待学习信号。

本脚本:
- 从 `赛题资料/路口数据/1~20/路口数据/*.xlsx` 逐块提取 早高峰/平峰/晚高峰
  三个时段的 15 分钟分时流量（兼容不同行列布局）；
- 将每个 15 分钟区间的 pcu（× pcu_factor 换算系数）生成独立 flow，
  begin/end 对齐真实时段窗口（早 07:00-09:00 / 平 14:30-16:30 / 晚 17:30-19:30）；
- 依据 xiongan_30.nod.xml / xiongan_30.edg.xml 的路网拓扑，把 (进口方向, 转向)
  映射到真实连接 (入口边, 出口边)（中国右侧通行：东进口直行出西/左转出南/右转出北，等）；
- 新增路口 J21~J30 无真实 xlsx 数据，按 MIRROR_MAP 镜像复用旧路口 J01~J20 的需求，
  使扩展区域同样产生排队/等待学习信号；
- 输出 sumo_files/xiongan_real_{peak,offpeak,evening}.rou.xml + .sumocfg，
  可直接被 training/config.py SCENARIO_CONFIG 引用并用于 DQN 训练。

需求标定（容量匹配法，2026-08 校准）:
- 网格版路网（6×6 路口、200m 街块、每进口 2 车道）的通行能力低于真实雄安路网。
  若直接使用 xlsx 原始 pcu（--factor 1.0，约 12 veh/s 总插入率），真实定周期
  基线会在部分进口左转绿信比过低处（如 J12 南/北左转 9%、J14 北左转 28%、
  J10 东左转 27%）饱和并向全网回溢死锁。
- 因此按“真实定周期基线（baselines/fixed_time.py + data/timing_plans.json）
  全路网可通行能力”等比标定：早/平/晚各取基线尚能持续流通（7200s 全程
  meanSpeed 最低点 ≥ 2 m/s）的最大需求，即 peak=0.48 / offpeak=0.60 /
  evening=0.42（约 6.2~7.2 veh/s 总插入率，仍远超手工场景 22~37 倍，
  路口有真实排队与等待学习信号）。

用法:
    # 三个场景统一系数
    python scripts/generate_real_demand_scenarios.py --factor 0.5
    # 早/平/晚分别标定（推荐，与 data/timing_plans.json 的容量匹配）
    python scripts/generate_real_demand_scenarios.py --factor 0.48,0.60,0.42
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = PROJECT_ROOT / "赛题资料" / "路口数据"
SUMO_FILES_DIR = PROJECT_ROOT / "sumo_files"
NET_FILE = "xiongan_30.net.xml"
NOD_FILE = "xiongan_30.nod.xml"
EDG_FILE = "xiongan_30.edg.xml"

# 中国右侧通行: 进口方向 -> {转向 -> 驶出方向}
# 例如 东进口(车辆向西驶入) 左转 → 南
MOVE_EXIT = {
    "W": {"直行": "E", "左转": "N", "右转": "S"},
    "E": {"直行": "W", "左转": "S", "右转": "N"},
    "N": {"直行": "S", "左转": "E", "右转": "W"},
    "S": {"直行": "N", "左转": "W", "右转": "E"},
}
SIDE_TO_LABEL = {"N": "北进口", "S": "南进口", "E": "东进口", "W": "西进口"}
LABEL_TO_SIDE = {"北进口": "N", "南进口": "S", "东进口": "E", "西进口": "W"}
# J18/J19 是 45° 对角路口，xlsx 用 东北/东南/西北/西南 进口标注。
# 映射到合成网格的 N/S/E/W 进口（保持转向语义与相位结构一致）：
#   东北→E（向东进口直行向西 = 原东北→西南直行）等，见 timing_plans 相位"东北、西南放行"。
DIAGONAL_TO_SIDE = {"东北进口": "E", "东南进口": "S", "西北进口": "N", "西南进口": "W"}
MOVE_CODE = {"直行": "T", "左转": "L", "右转": "R"}

# 30 路口路网（6×5 网格）在旧 20 路口基础上新增 J21~J30，这些路口没有真实
# xlsx 数据。按就近/对称原则镜像复用旧路口需求：每个新路口采用其镜像源路口
# 各时段的 (进口侧, 转向) 分时流量，保证扩展区域同样有排队/等待学习信号。
# （侧向/转向在目标路口按其自身几何重新映射，见 build_topology + MOVE_EXIT。）
MIRROR_MAP = {
    "J21": "J01", "J22": "J03", "J23": "J04", "J24": "J06", "J25": "J08",
    "J26": "J05", "J27": "J07", "J28": "J09", "J29": "J11", "J30": "J02",
}


def _label_to_side(label: str) -> Optional[str]:
    """把 xlsx 进口标签映射为 N/S/E/W（优先标准四向，其次对角映射）"""
    return LABEL_TO_SIDE.get(label) or DIAGONAL_TO_SIDE.get(label)
TIME_RE = re.compile(r"^\d{1,2}:\d{2}:\d{2}$")


# ---------------------------------------------------------------
# 1. 路网拓扑（xiongan.nod.xml / xiongan.edg.xml）
# ---------------------------------------------------------------
def _parse_nodes(nod_path: Path) -> dict[str, tuple[float, float]]:
    """解析节点坐标 {id: (x, y)}"""
    text = nod_path.read_text(encoding="utf-8")
    nodes = {}
    for m in re.finditer(r'<node id="([^"]+)" x="([^"]+)" y="([^"]+)"', text):
        nodes[m.group(1)] = (float(m.group(2)), float(m.group(3)))
    return nodes


def _parse_edges(edg_path: Path) -> list[dict]:
    """解析边 {id, from, to}（忽略内部边，edg.xml 中无内部边）"""
    text = edg_path.read_text(encoding="utf-8")
    edges = []
    for m in re.finditer(r'<edge id="([^"]+)" from="([^"]+)" to="([^"]+)"', text):
        edges.append({"id": m.group(1), "from": m.group(2), "to": m.group(3)})
    return edges


def _classify_side(from_xy: tuple[float, float], junction_xy: tuple[float, float]) -> Optional[str]:
    """返回 from 节点相对 junction 的方位 (N/S/E/W)，即该边在 junction 的哪一侧"""
    dx = from_xy[0] - junction_xy[0]
    dy = from_xy[1] - junction_xy[1]
    if abs(dx) >= abs(dy):
        return "E" if dx > 0 else "W" if dx < 0 else None
    return "N" if dy > 0 else "S" if dy < 0 else None


def build_topology(sumo_files_dir: Path) -> dict:
    """构建 30 路口的 进口边/出口边 映射（按方位）"""
    nodes = _parse_nodes(sumo_files_dir / NOD_FILE)
    edges = _parse_edges(sumo_files_dir / EDG_FILE)
    junctions = sorted(nid for nid in nodes if re.fullmatch(r"J\d{2}", nid))

    approach_edges: dict[str, dict[str, list[str]]] = {j: {} for j in junctions}
    exit_edges: dict[str, dict[str, list[str]]] = {j: {} for j in junctions}
    junction_set = set(junctions)
    for e in edges:
        if e["from"] not in nodes or e["to"] not in nodes:
            continue
        if e["to"] in junction_set:  # 驶向该路口的边 → 进口边
            side = _classify_side(nodes[e["from"]], nodes[e["to"]])
            if side:
                approach_edges[e["to"]].setdefault(side, []).append(e["id"])
        if e["from"] in junction_set:  # 从该路口驶出的边 → 出口边
            side = _classify_side(nodes[e["to"]], nodes[e["from"]])
            if side:
                exit_edges[e["from"]].setdefault(side, []).append(e["id"])
    return {"junctions": junctions, "approach_edges": approach_edges, "exit_edges": exit_edges}


# ---------------------------------------------------------------
# 2. xlsx 流量解析（按 早高峰/平峰/晚高峰 分块，兼容多种布局）
# ---------------------------------------------------------------
def _norm(s) -> str:
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ""
    return str(s).strip()


def _clean_label(s) -> str:
    """去掉表头里的 '(pcu)' 等括号后缀，得到 东进口/左转 这类纯标签"""
    s = _norm(s)
    if "(" in s:
        s = s[: s.index("(")]
    return s.strip()


def _block_period(name: str) -> Optional[str]:
    if "早高峰" in name:
        return "peak"
    if "平峰" in name and "晚" not in name:
        return "offpeak"
    if "晚高峰" in name:
        return "evening"
    return None


def _parse_flow_xlsx(xlsx_path: Path, factor: float) -> dict:
    """返回 {period: {"window": (s, e), "intervals": [...], "flows": {(side, move): [num,...]}}}"""
    df = pd.read_excel(xlsx_path, sheet_name="流量数据", header=None)
    result = {}
    n_rows, n_cols = df.shape
    title_row = None
    for r in range(n_rows):
        if "流量数据" in _norm(df.iloc[r, 0]):
            title_row = r
            break
    if title_row is None:
        raise ValueError(f"{xlsx_path.name} 未找到 '流量数据' 分块标题行")

    r = title_row
    while r < n_rows:
        period = _block_period(_norm(df.iloc[r, 0]))
        if period is None:
            r += 1
            continue
        # 找数据起始行: 标题后两行内出现时间列
        header_row = r + 1
        data_row = header_row + 2
        # 读取 方向->列 与 (方向,转向)->列 映射
        dir_col: dict[int, str] = {}
        data_cols: dict[tuple[str, str], int] = {}
        current_dir = ""
        for c in range(2, min(n_cols, 14)):
            cell = _clean_label(df.iloc[header_row, c])
            if cell:
                current_dir = cell
            if current_dir:
                dir_col[c] = current_dir
            turn = _clean_label(df.iloc[data_row - 1, c])
            if turn:
                key = (current_dir, turn)
                if current_dir and turn:
                    data_cols[key] = c
        # 收集 15 分钟数据行
        intervals = []
        flow_values: dict[tuple[str, str], list[float]] = {}
        rr = data_row
        period_start = None
        while rr < n_rows:
            t0 = _norm(df.iloc[rr, 0])
            t1 = _norm(df.iloc[rr, 1])
            if not TIME_RE.match(t0) or not TIME_RE.match(t1):
                break
            h0, m0, s0 = (int(x) for x in t0.split(":"))
            h1, m1, s1 = (int(x) for x in t1.split(":"))
            start = h0 * 3600 + m0 * 60 + s0
            end = h1 * 3600 + m1 * 60 + s1
            if period_start is None:
                period_start = start
            intervals.append((start, end))
            for (d, t), col in data_cols.items():
                val = df.iloc[rr, col]
                if pd.notna(val) and isinstance(val, (int, float)):
                    flow_values.setdefault((d, t), []).append(float(val) * factor)
                else:
                    flow_values.setdefault((d, t), []).append(0.0)
            rr += 1
        if not intervals:
            r += 1
            continue
        window = (0, intervals[-1][1] - (period_start or 0))
        # 区间相对周期起点偏移
        rel_intervals = [(a - (period_start or 0), b - (period_start or 0)) for a, b in intervals]
        result[period] = {
            "window": window,
            "intervals": rel_intervals,
            "flows": flow_values,
        }
        r = rr
    return result


# ---------------------------------------------------------------
# 3. 生成 rou.xml / sumocfg
# ---------------------------------------------------------------
def generate_scenario(
    period: str,
    parsed: dict,
    topology: dict,
    sumo_files_dir: Path,
    factor: float,
) -> tuple[Path, int]:
    """生成单个场景的 rou.xml 与 sumocfg，返回 (rou_path, 总车辆数)"""
    window = parsed["window"]
    intervals = parsed["intervals"]
    approach_edges = topology["approach_edges"]
    exit_edges = topology["exit_edges"]

    lines: list[str] = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append('<routes>')
    lines.append(
        '    <vType id="passenger" vClass="passenger" accel="2.6" decel="4.5" sigma="0.5" '
        'length="5.0" minGap="2.5" maxSpeed="13.89" color="0.2,0.5,1.0"/>'
    )

    route_cache: dict[tuple[str, str, str], str] = {}
    flow_lines: list[tuple[int, str]] = []  # (begin, xml_line) — 最后按 begin 排序写出
    flow_count = 0
    total_vehicles = 0
    missing = []

    # (路口, 进口侧, 转向) -> 各 15 分钟区间车辆数，已由 parse_all_flow_xlsx 按路口聚合
    flows_by_junction: dict[str, dict] = parsed["_flows_by_junction"]

    for j, jdata in flows_by_junction.items():
        for (side, move), values in jdata.items():
            in_edges = approach_edges.get(j, {}).get(side, [])
            out_edges = exit_edges.get(j, {}).get(MOVE_EXIT[side][move], [])
            if not in_edges or not out_edges:
                missing.append((j, side, move))
                continue
            rkey = (j, side, move)
            if rkey not in route_cache:
                route_cache[rkey] = f"r_{j}_{side}_{MOVE_CODE[move]}"
                lines.append(
                    f'    <route id="{route_cache[rkey]}" edges="{in_edges[0]} {out_edges[0]}"/>'
                )
            for idx, (t0, t1) in enumerate(intervals):
                n = int(round(values[idx] * factor)) if idx < len(values) else 0
                if n <= 0:
                    continue
                fid = f"f_{j}_{side}_{MOVE_CODE[move]}_{idx}"
                flow_lines.append((
                    t0,
                    f'    <flow id="{fid}" route="{route_cache[rkey]}" type="passenger" '
                    f'begin="{t0}" end="{t1}" number="{n}"/>',
                ))
                flow_count += 1
                total_vehicles += n

    # SUMO 缺陷/限制：若某条 flow 的 begin 晚于其后声明的 flow，后面的 flow 会被静默跳过
    # （整文件只有第一个 flow 产车）。必须按 begin 升序输出所有 flow。
    lines.extend(line for _, line in sorted(flow_lines, key=lambda x: x[0]))

    lines.append('</routes>')
    rou_path = sumo_files_dir / f"xiongan_real_{period}.rou.xml"
    rou_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    cfg = f"""<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <input>
        <net-file value="{NET_FILE}"/>
        <route-files value="{rou_path.name}"/>
    </input>
    <time><begin value="0"/><end value="{window[1] + 1200}"/><step-length value="1"/></time>
    <processing><time-to-teleport value="-1"/><collision.action value="warn"/></processing>
    <report><verbose value="false"/><no-step-log value="true"/></report>
</configuration>
"""
    cfg_path = sumo_files_dir / f"xiongan_real_{period}.sumocfg"
    cfg_path.write_text(cfg, encoding="utf-8")

    if missing:
        print(f"  ⚠️  无连接可映射 {len(missing)} 组: {missing[:5]}...")
    return rou_path, total_vehicles


def parse_all_flow_xlsx(data_dir: Path) -> dict[str, dict]:
    """读取全部 20 个路口 xlsx，按 (路口, 进口, 转向) 聚合到各时段（pcu 原始值，factor=1.0）

    返回 {period: {"window": (s,e), "intervals": [...], "_flows_by_junction":
        {J01: {(side, move): [每15min车辆数]}}}}
    """
    per_junction: dict[str, dict] = {}
    dirs = sorted(
        [d for d in data_dir.iterdir() if d.is_dir() and d.name.isdigit()],
        key=lambda d: int(d.name),
    )
    if len(dirs) != 20:
        print(f"  ⚠️  路口数据目录数量 = {len(dirs)}（期望 20）", file=sys.stderr)
    for d in dirs:
        xlsx = list(d.glob("**/*.xlsx"))
        if not xlsx:
            print(f"  ⚠️  {d.name} 下无 xlsx", file=sys.stderr)
            continue
        jid = f"J{int(d.name):02d}"
        per_junction[jid] = _parse_flow_xlsx(xlsx[0], 1.0)

    # 新增路口 J21~J30 无真实 xlsx 数据：镜像复用旧路口需求（共享解析结果，只读）。
    for target, source in MIRROR_MAP.items():
        if source not in per_junction:
            print(f"  ⚠️  镜像源 {source} 缺失，跳过 {target}", file=sys.stderr)
            continue
        per_junction[target] = per_junction[source]

    periods = ["peak", "offpeak", "evening"]
    merged: dict[str, dict] = {}
    for p in periods:
        window = None
        intervals = None
        flows_by_junction: dict[str, dict] = {}
        for jid, parsed in per_junction.items():
            if p not in parsed:
                print(f"  ⚠️  {jid} 缺少时段 {p}", file=sys.stderr)
                continue
            jflows: dict[tuple[str, str], list[float]] = {}
            for (dir_label, move), values in parsed[p]["flows"].items():
                side = _label_to_side(dir_label)
                if side:
                    jflows[(side, move)] = values
                else:
                    print(f"  ⚠️  {jid} 未知进口标签 {dir_label!r}，已跳过", file=sys.stderr)
            flows_by_junction[jid] = jflows
            if window is None:
                window = parsed[p]["window"]
                intervals = parsed[p]["intervals"]
        merged[p] = {"window": window, "intervals": intervals, "_flows_by_junction": flows_by_junction}
    return merged


def _parse_factors(text: str) -> dict[str, float]:
    """解析 --factor：单个浮点数（三场景统一）或 'peak,offpeak,evening' 三个值"""
    parts = [p.strip() for p in text.split(",")]
    try:
        if len(parts) == 1:
            f = float(parts[0])
            return {"peak": f, "offpeak": f, "evening": f}
        if len(parts) == 3:
            return dict(zip(["peak", "offpeak", "evening"], map(float, parts)))
    except ValueError:
        pass
    raise SystemExit(f"--factor 解析失败: {text!r}（应为单个浮点数或 '早,平,晚' 三个值）")


def main() -> None:
    ap = argparse.ArgumentParser(description="基于真实 xlsx 数据生成 30 路口训练场景（早/平/晚）")
    ap.add_argument("--factor", default="1.0",
                    help="pcu→veh 换算系数。单个浮点数（三场景统一）或 '早,平,晚' 三个值。"
                         "容量匹配标定值见本文件头注释：0.48,0.65,0.42")
    ap.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR, help="赛题路口数据目录")
    ap.add_argument("--out-dir", type=Path, default=SUMO_FILES_DIR, help="输出目录（sumo_files）")
    args = ap.parse_args()
    factors = _parse_factors(args.factor)

    print("🔧 读取路网拓扑...")
    topology = build_topology(args.out_dir)
    print(f"   30 路口拓扑: 进口/出口边按 N/S/E/W 建立完成")
    for j in ["J01", "J05", "J16", "J21", "J30"]:
        print(f"   {j} 进口: { {s: e[0] for s, e in topology['approach_edges'][j].items()} }")

    print("📥 解析 20 个真实路口 xlsx 流量 + 10 个镜像路口（早/平/晚）...")
    all_flows = parse_all_flow_xlsx(args.data_dir)

    labels = {"peak": "早高峰(07:00-09:00)", "offpeak": "平峰(14:30-16:30)", "evening": "晚高峰(17:30-19:30)"}
    stats = {}
    for p in ["peak", "offpeak", "evening"]:
        f = factors[p]
        print(f"\n🚦 生成场景 [{labels[p]}] factor={f}")
        rou_path, total = generate_scenario(p, all_flows[p], topology, args.out_dir, f)
        stats[p] = {"rou": str(rou_path.name), "total_vehicles": total, "window_s": all_flows[p]["window"][1],
                    "factor": f}
        print(f"   ✅ {rou_path.name}: {total} 辆车 / {all_flows[p]['window'][1]}s")

    # 汇总各路口小时需求（取早高峰），便于核对
    print("\n📊 早高峰各路口总需求（pcu/h，2 小时总量 ÷ 2）：")
    for j in ["J01", "J05", "J10", "J15", "J20", "J21", "J25", "J30"]:
        jf = all_flows["peak"]["_flows_by_junction"].get(j, {})
        total_2h = sum(sum(v) for v in jf.values())
        print(f"   {j}: {total_2h / 2:.0f} pcu/h")

    stats_path = args.out_dir / "real_scenario_stats.json"
    stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n📄 统计已写入 {stats_path}")


if __name__ == "__main__":
    main()
