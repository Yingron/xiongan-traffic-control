"""真实定周期（Fixed-Time）控制基线

历史缺陷（审查缺口 ②）：
    evaluation/evaluate_3scenarios.py 与 evaluation/evaluate_all_strategies.py 原来的
    fixed_time_action = (step // 5) % 4 是假基线——20s 周期每相位 5s，比 MIN_GREEN 15s
    还短；真实配时在 data/timing_plans.json（如 J01 早高峰 38/32/32/38，周期 160s）
    却从未被引用。

本模块从 data/timing_plans.json 读取真实配时，结合路网连接关系（linkIndex →
进口/转向）构造真实信号程序，通过 TraCI 安装到被控路口，由 SUMO 按固定周期自主运行：

    1. 解析相位名（如 "东西向直行"、"东西左转直行"、"东、北放行"、"东北、西南放行"）
       为具体放行的 (进口, 转向) 集合（放行 = 直行+左转；对角线进口命名 东北/西南/…
       映射到网格侧 E/W/…，与 scripts/generate_real_demand_scenarios.py 的 DIAGONAL_TO_SIDE 一致）。
    2. 每个真实相位 = 绿灯相位 + 黄灯相位 + 全红相位（时长取自 timing_plans.json）。
       右转车道随本进口的直行相位放行（与 rl4/DQN 基线一致）：若把右转在全部相位中自由
       放行，右转会与对向直行在同一条出口道上抢行，产生额外碰撞（实测 J01 300s 4 次）。
    3. 安装后 env.step 收到 FIXED_TIME_CONTROL（哨兵动作，见 configs/constants.py）
       不再干预信号，只负责指标统计。

用法:
    from baselines.fixed_time import RealFixedTimeController
    controller = RealFixedTimeController("J01", "peak")
    action = controller.get_action(obs, env, step)   # 恒返回 FIXED_TIME_CONTROL

    # 或在评估脚本中直接使用工厂函数
    from baselines.fixed_time import make_real_fixed_time_action
    action_fn = make_real_fixed_time_action("J01", "offpeak")
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import xml.etree.ElementTree as ET

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from configs.constants import DATA_DIR, FIXED_TIME_CONTROL

# ============================================================
# 相位名解析：真实配时相位名 → (进口, 转向) 集合
# ============================================================
# 进口命名 → 网格侧（与需求生成脚本的 DIAGONAL_TO_SIDE 保持一致）：
#   "东北、西南放行"（J18/J19/J20 等对角路口）→ 放行 E/W 两个对侧进口
#   "东南向左转"（J10）/ "西南向左转"（J02）→ S/W 进口左转
SIDE_ALIASES = {
    "东": "E", "西": "W", "南": "S", "北": "N",
    "东北": "E", "西南": "W", "西北": "N", "东南": "S",
}
_DIAGONAL_SIDES = ("东北", "西北", "东南", "西南")
_SIDE_CHARS = "东西南北"
_MOVE_ALIASES = {"直": "T", "左": "L", "右": "R"}


def _expand_sides(token: str) -> List[str]:
    """单个侧向 token → 网格侧列表。"东西"→[E,W]；"东北"→[E]（对角映射）。"""
    if token in SIDE_ALIASES:
        return [SIDE_ALIASES[token]]
    return [SIDE_ALIASES.get(ch) for ch in token if ch in SIDE_ALIASES]


def _parse_moves(token: str) -> Tuple[str, ...]:
    """转向组文字 → 转向集合。'放行'=直行+左转；'直行转向'=直行+左转。"""
    if not token:
        return ()
    if token == "放行":
        return ("T", "L")
    moves: List[str] = []
    if "转向" in token:
        moves.append("L")
    for ch in "直左右":
        if ch in token:
            moves.append(_MOVE_ALIASES[ch])
    return tuple(dict.fromkeys(moves))


def parse_phase_name(name: str) -> List[Tuple[str, str]]:
    """解析真实相位名为 (进口, 转向) 列表。

    覆盖赛题配时中的相位名模式：
      东西向直行 / 南北向左转 / 东西向直左
      东西左转直行 / 南北左转直行 / 东西直左 / 南北直左
      南北直行转向 / 西向直左南向直右 / 东向左右转 / 南向左右转
      东、北放行 / 南放行 / 东北、西南放行 / 西北、东南放行
      东进口直行 / 北进口左转 / 西进口左转 / 东进口左右转
      东北左转右转 / 东北西南左转(直行) / 西北东南左转(直行)
      西南向左转 / 东南向左转
    """
    if not name or name.startswith("相位"):
        return []

    # 形式1: <进口>向<转向>...（每个进口可带独立转向组）
    matched = re.findall(r"([东西南北]{1,2})向([^东西南北]*)", name)
    if matched:
        parts: List[Tuple[str, str]] = []
        for side_tok, move_tok in matched:
            for side in _expand_sides(side_tok):
                for mv in _parse_moves(move_tok):
                    parts.append((side, mv))
        return parts

    # 形式2: <进口>进口<转向>
    if "进口" in name:
        m = re.match(r"^([东西南北]{1,2})进口([^东西南北]+)$", name)
        if m:
            parts = []
            for side in _expand_sides(m.group(1)):
                for mv in _parse_moves(m.group(2)):
                    parts.append((side, mv))
            return parts

    # 形式3: 前缀进口列表（可含 、分隔）+ 后缀转向组
    segments = name.split("、")
    sides: List[str] = []
    move_token = ""
    for seg in segments:
        i = 0
        while i < len(seg):
            if seg[i:i + 2] in _DIAGONAL_SIDES:
                sides.append(seg[i:i + 2])
                i += 2
            elif seg[i] in _SIDE_CHARS:
                sides.append(seg[i])
                i += 1
            else:
                break
        if i < len(seg):
            move_token += seg[i:]

    parts = []
    for side_tok in sides:
        for side in _expand_sides(side_tok):
            for mv in _parse_moves(move_token):
                parts.append((side, mv))
    return parts


# ============================================================
# 路网解码：linkIndex → (进口, 转向)
# ============================================================
_DIR_TO_MOVE = {"s": "T", "l": "L", "r": "R"}


def load_link_map(net_xml_path: str | Path) -> Dict[str, Dict[int, Tuple[str, str, str, int, int]]]:
    """解析路网，返回 {路口: {linkIndex: (进口, 转向, 出口边, 出口车道, 进口车道)}}。

    信号灯相位状态串第 i 个字符对应 linkIndex=i 的车道组（SUMO 约定），
    因此按 linkIndex 建立到 (进口, 转向) 的映射即可把真实相位名转成灯组状态；
    出口边/出口车道/进口车道用于判定合流：同一出口车道同相位至多一个主绿 'G'，
    其余合流链接标记次要绿 'g'（与路网自带 "0" 程序的 G/g 模式一致）。

    进口方位的推断：新 30 路口路网的边名为 e_{from}_{to}，无法从边名前缀
    取方位（旧路网边名以 N/S/E/W 开头，frm.split("_")[0] 在旧网上可用）。
    这里改用节点坐标几何推断：进口边 from 节点相对受控路口的方位。
    """
    tree = ET.parse(str(net_xml_path))
    root = tree.getroot()
    coords = {j.get("id"): (float(j.get("x")), float(j.get("y")))
              for j in root.findall("junction") if j.get("x") is not None}
    edge_from = {e.get("id"): e.get("from")
                 for e in root.findall("edge") if e.get("function") is None}

    def classify(frm_node: str, to_node: str) -> str:
        fx, fy = coords[frm_node]
        tx, ty = coords[to_node]
        dx, dy = fx - tx, fy - ty
        if abs(dx) >= abs(dy):
            return "E" if dx > 0 else "W" if dx < 0 else "?"
        return "N" if dy > 0 else "S" if dy < 0 else "?"

    link_map: Dict[str, Dict[int, Tuple[str, str, str, int, int]]] = {}
    for conn in root.iter("connection"):
        tl = conn.get("tl")
        li = conn.get("linkIndex")
        if tl is None or li is None:
            continue
        frm = conn.get("from", "")
        move = _DIR_TO_MOVE.get(conn.get("dir", ""), "T")
        # 内部边（:J01_0）无坐标/不属于边表，保持旧式前缀兜底（不与 N/S/E/W 匹配）
        if frm.startswith(":") or frm not in edge_from or tl not in coords:
            side = frm.split("_")[0] if frm else "?"
        else:
            side = classify(edge_from[frm], tl)
        link_map.setdefault(tl, {})[int(li)] = (
            side, move,
            conn.get("to", ""),
            int(conn.get("toLane", "-1")),
            int(conn.get("fromLane", "-1")),
        )
    return link_map


def resolve_net_file(sumo_cfg_path: str | Path) -> Path:
    """从 sumocfg 中解析 net-file（相对路径基于 sumocfg 所在目录）。"""
    cfg = Path(sumo_cfg_path)
    text = cfg.read_text(encoding="utf-8")
    m = re.search(r'<net-file value="([^"]+)"', text)
    if not m:
        raise ValueError(f"sumocfg 中未找到 net-file: {cfg}")
    net = Path(m.group(1))
    return net if net.is_absolute() else cfg.parent / net


# ============================================================
# 真实定周期控制器
# ============================================================
class RealFixedTimeController:
    """基于 data/timing_plans.json 的真实定周期信号控制器。

    在 env 上安装真实配时程序后，get_action 恒返回 FIXED_TIME_CONTROL 哨兵，
    让 SUMO 的静态信号逻辑按真实周期（绿/黄/全红）自主运行；env.step 不再干预。
    """

    def __init__(
        self,
        junction_id: str,
        period: str = "offpeak",
        timing_plans_path: str | Path | None = None,
        net_xml_path: str | Path | None = None,
        right_with_through: bool = True,
    ) -> None:
        self.junction_id = junction_id
        self.period = period
        self.timing_plans_path = Path(timing_plans_path or DATA_DIR / "timing_plans.json")
        self.net_xml_path = Path(net_xml_path) if net_xml_path else None
        # 右转随本进口的直行相位放行（与 rl4/DQN 基线的放行方式一致，实测无碰撞）；
        # 若改为全部绿灯相位自由放行，右转会与对向直行在同一条出口道抢行产生碰撞。
        self.right_with_through = right_with_through
        self._installed_for_env: Optional[int] = None
        self._plan_summary: Optional[dict] = None

    # ---- 数据加载 ----
    def _load_plan(self) -> dict:
        data = json.loads(self.timing_plans_path.read_text(encoding="utf-8"))
        plan = data.get(self.junction_id, {}).get(self.period)
        if plan is None:
            raise ValueError(
                f"timing_plans.json 中不存在 {self.junction_id}/{self.period} 的配时方案"
            )
        return plan

    def _load_link_map(self) -> Dict[int, Tuple[str, str, str, int, int]]:
        if self.net_xml_path is None:
            raise ValueError("net_xml_path 未指定，无法解码 linkIndex → (进口, 转向)")
        link_map = load_link_map(self.net_xml_path)
        jm = link_map.get(self.junction_id)
        if not jm:
            raise ValueError(f"路网 {self.net_xml_path} 中未找到 {self.junction_id} 的信号化车道组")
        n_links = max(jm) + 1
        if len(jm) != n_links:
            raise ValueError(f"{self.junction_id} linkIndex 不连续: {len(jm)} != {n_links}")
        return jm

    # ---- 真实信号程序构造 ----
    def build_phases(self) -> List[Dict]:
        """构造真实配时的相位描述列表 [绿, 黄, 全红]×N。

        每个元素为 {"duration", "state", "name"}（纯数据，不依赖 TraCI 连接）；
        install() 用 env 的连接把它们包装成 traci.trafficlight.Phase。
        """
        plan = self._load_plan()
        link_map = self._load_link_map()
        n_links = len(link_map)

        phases: List[Dict] = []
        phase_infos: List[dict] = []
        for phase_name, pdata in plan.items():
            if phase_name == "cycle" or phase_name.startswith("相位"):
                # 相位3/4/7/8 为 xlsx 汇总行的占位填充（不在原始配时表中），丢弃
                continue
            movements = parse_phase_name(phase_name)
            state = ["r"] * n_links
            # (linkIndex, 出口边, 出口车道, 进口车道)：同一出口车道同相位至多一个主绿
            candidates: List[Tuple[int, str, int, int]] = []
            # 右转随本进口直行相位放行：相位名含某进口的直行（或直左/放行等含 T 的组合）
            # 时，该进口的右转车道一并绿灯——与 rl4 动作表一致，避免右转与对向直行
            # 在同一条出口道上抢行。
            if self.right_with_through:
                sides_with_through = {side for side, move in movements if move == "T"}
                for li, (ls, lm, to, to_lane, from_lane) in link_map.items():
                    if lm == "R" and ls in sides_with_through:
                        candidates.append((li, to, to_lane, from_lane))
            for side, move in movements:
                for li, (ls, lm, to, to_lane, from_lane) in link_map.items():
                    if ls == side and lm == move:
                        candidates.append((li, to, to_lane, from_lane))
            if not candidates:
                raise ValueError(
                    f"{self.junction_id} 相位 {phase_name!r} 未映射到任何绿灯车道组 "
                    f"(movements={movements}, net={self.net_xml_path.name})"
                )
            # 合流降级：每条出口道同相位只有主链接为 'G'（直行续行 fromLane==toLane 优先），
            # 其余合流链接标记次要绿 'g'（让行）。否则两条受保护流挤入同一车道，
            # SUMO 报 "unsafe green" 并在饱和需求下互相等待导致堵死（实测全路网 3600s 崩盘）。
            by_lane: Dict[Tuple[str, int], List[Tuple[int, str, int, int]]] = {}
            for cand in candidates:
                by_lane.setdefault((cand[1], cand[2]), []).append(cand)
            for lane_links in by_lane.values():
                lane_links.sort(key=lambda c: (c[3] != c[2], c[0]))
                for i, (li, _to, _to_lane, _from_lane) in enumerate(lane_links):
                    state[li] = "G" if i == 0 else "g"
            green_links = {c[0] for c in candidates}
            green_state = "".join(state)
            yellow_state = "".join("y" if c in ("G", "g") else "r" for c in green_state)
            all_red_state = "r" * n_links

            g = int(pdata.get("green", 0))
            y = int(pdata.get("yellow", 0))
            r = int(pdata.get("red", 0))
            phases.append({"duration": g, "state": green_state, "name": f"{phase_name}_G"})
            if y > 0:
                phases.append({"duration": y, "state": yellow_state, "name": f"{phase_name}_Y"})
            if r > 0:
                phases.append({"duration": r, "state": all_red_state, "name": f"{phase_name}_R"})
            phase_infos.append({"name": phase_name, "green": g, "yellow": y, "red": r,
                                "movements": sorted(movements)})

        if not phases:
            raise ValueError(f"{self.junction_id}/{self.period} 没有可用真实相位")

        self._plan_summary = {
            "junction_id": self.junction_id,
            "period": self.period,
            "n_links": n_links,
            "phases": phase_infos,
            "cycle": sum(p["duration"] for p in phases),
            "right_with_through": self.right_with_through,
            "net": self.net_xml_path.name,
        }
        return phases

    def install(self, env: Any) -> None:
        """把真实配时程序安装到 env 的被控路口（幂等：每个 env 只装一次）。

        必须在 env.reset() 之后、第一次 env.step() 之前调用（评估脚本的 action_fn
        在第一轮循环就满足该时机）。
        """
        if self._installed_for_env == id(env):
            return
        if self.net_xml_path is None:
            self.net_xml_path = resolve_net_file(env.sumo_cfg_path)
        import traci  # Logic/Phase 类（不依赖具体连接）

        phase_specs = self.build_phases()
        sub_id = f"real_{self.period}"
        # 必须走 env 的连接域（env 用 traci.connect(label=...) 连接，模块级
        # traci.trafficlight.* 不会绑定到该连接）
        tl_domain = env._traci.trafficlight
        phases = [traci.trafficlight.Phase(p["duration"], p["state"], name=p["name"]) for p in phase_specs]
        # Logic.type 是 TraCI 整数枚举（TRAFFICLIGHT_TYPE_STATIC=0），不是字符串 "static"
        logic = traci.trafficlight.Logic(sub_id, traci.constants.TRAFFICLIGHT_TYPE_STATIC, 0, phases)
        # setProgramLogic 是 setCompleteRedYellowGreenDefinition 的非弃用别名（无告警）
        tl_domain.setProgramLogic(self.junction_id, logic)
        tl_domain.setProgram(self.junction_id, sub_id)
        self._installed_for_env = id(env)

    def get_action(self, obs: Any, env: Any, step: int) -> int:
        """兼容评估脚本 action_fn(obs, env, step) 接口：安装后恒返回哨兵动作。"""
        self.install(env)
        return FIXED_TIME_CONTROL

    def __call__(self, obs: Any, env: Any, step: int) -> int:
        return self.get_action(obs, env, step)

    @property
    def plan_summary(self) -> Optional[dict]:
        return self._plan_summary


def make_real_fixed_time_action(junction_id: str, period: str = "offpeak", **kwargs):
    """评估脚本用工厂：返回 (obs, env, step) -> FIXED_TIME_CONTROL 的 action_fn。

    内部持有 RealFixedTimeController，在首个 env 上自动安装真实配时程序。
    """
    controller = RealFixedTimeController(junction_id, period, **kwargs)
    return controller.get_action, controller


def real_movements(link_map: Dict[str, Dict[int, Tuple[str, str, str, int, int]]], junction_id: str) -> set:
    """路网中某路口真实存在的 (进口, 转向) 车道组集合（含直行 s/t 归一化）。"""
    return {(s, m) for s, m, *_ in link_map.get(junction_id, {}).values() if s in "NSEW"}


def covered_movements(plan: dict, real: set, right_with_through: bool = True) -> set:
    """配时方案覆盖的 (进口, 转向)：相位显式放行 + 右转随本进口直行相位放行。"""
    covered = set()
    through_sides = set()
    for name in plan:
        if name == "cycle" or name.startswith("相位"):
            continue
        for side, move in parse_phase_name(name):
            if (side, move) in real:
                covered.add((side, move))
            if move == "T":
                through_sides.add(side)
    if right_with_through:
        for side, move in real:
            if move == "R" and side in through_sides:
                covered.add((side, "R"))
    return covered


if __name__ == "__main__":
    # 离线自检：所有 30 个路口的真实配时能否正确映射到路网车道组
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--net", default=str(Path(PROJECT_ROOT) / "sumo_files" / "xiongan_30.net.xml"))
    parser.add_argument("--periods", default="peak,offpeak,evening")
    parser.add_argument("--check-coverage", action="store_true",
                        help="检查每个路口是否存在路网有连接但配时无绿灯放行的流向")
    args = parser.parse_args()

    net_path = Path(args.net)
    link_map = load_link_map(net_path)
    data = json.loads((DATA_DIR / "timing_plans.json").read_text(encoding="utf-8"))
    print(f"net={net_path.name}  路口数={len(link_map)}")
    for jid in sorted(link_map, key=lambda x: int(x[1:])):
        for period in args.periods.split(","):
            if period not in data.get(jid, {}):
                continue
            ctrl = RealFixedTimeController(jid, period, net_xml_path=net_path)
            try:
                phases = ctrl.build_phases()
            except ValueError as e:
                print(f"[FAIL] {jid}/{period}: {e}")
                continue
            summary = ctrl.plan_summary
            names = " + ".join(f"{p['name']}({p['green']}s)" for p in summary["phases"])
            print(f"[OK] {jid}/{period}: cycle={summary['cycle']}s  {names}")

    if args.check_coverage:
        print("\n--- 流向覆盖检查（路网车道组 vs 配时放行，右转随直行） ---")
        for jid in sorted(link_map, key=lambda x: int(x[1:])):
            real = real_movements(link_map, jid)
            period = args.periods.split(",")[0]
            plan = data.get(jid, {}).get(period, {})
            if not plan:
                continue
            uncovered = sorted(real - covered_movements(plan, real))
            if uncovered:
                print(f"[WARN] {jid}/{period}: 路网有连接但配时无绿灯 = {uncovered}")
        print("（无输出 = 全部流向均有绿灯）")
