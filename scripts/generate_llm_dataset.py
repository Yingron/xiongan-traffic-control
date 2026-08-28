"""生成赛道 C LLM 微调数据集：SUMO 仿真 → 状态窗口 → 规则 oracle 标注 → JSONL。

数据流水线（对应"数据处理"环节）：
  1. 用真实场景路由（早/平/晚高峰）+ 可选施工占道扰动启动 SUMO，
     信号控制使用真实定周期配时（data/timing_plans.json，与评估基线一致）；
  2. 每 sample-sec 秒提取全部 30 路口的原始交通特征（排队/等待/占有率/均速/相位）；
  3. 每 label-stride 秒对每个路口取最近 window-sec 的窗口，
     由规则 oracle（llm_data/oracle.py）打标签：
       事件（扰动注入真值）> 溢出 > 拥堵 > 正常，并生成管控建议；
  4. 渲染中文输入文本（llm_data/text_format.py），与标签 JSON 一起写入 JSONL。

典型用法：
  # 冒烟（~5分钟）
  python scripts/generate_llm_dataset.py --scenarios real_peak --perturbations none,construction \
      --seeds 42 --end 600 --out data/llm/smoke.jsonl
  # 完整数据集（3 场景 × 2 扰动 × 3 种子，全 7200s，约 2~3 小时）
  python scripts/generate_llm_dataset.py --seeds 42,43,44 --out data/llm/dataset_v1.jsonl
  # 事件密集补充（construction 短窗 + 小步长滑动，事件类样本更多）
  python scripts/generate_llm_dataset.py --scenarios real_peak,real_evening \
      --perturbations construction --seeds 42,43,44 --end 600 --label-stride 10 \
      --out data/llm/dataset_incident.jsonl

输出：
  --out 指向的 JSONL（每行一个样本）+ 同目录 <文件名>_stats.json（类别分布与阈值校准分位数）。
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from baselines.fixed_time import RealFixedTimeController  # noqa: E402
from configs.constants import INTERSECTION_ORDER, SUMO_FILES_DIR  # noqa: E402
from llm_data.features import extract_intersection_raw  # noqa: E402
from llm_data.oracle import EventOracle  # noqa: E402
from llm_data.schema import (  # noqa: E402
    DEFAULT_BEGIN,
    DEFAULT_END,
    DEFAULT_LABEL_STRIDE,
    DEFAULT_SAMPLE_SEC,
    DEFAULT_WINDOW_SEC,
    EVENT_CLASSES,
    EVENT_EN,
    PERTURBATION_CONSTRUCTION,
    PERTURBATION_NONE,
    PERTURBATION_SPECS,
    SCENARIOS,
)
from llm_data.text_format import format_label_json, format_window_text  # noqa: E402

BASE_PORT = 8813


class _ShimEnv:
    """让 RealFixedTimeController.install 能脱离 Gym env 直接安装真实配时。"""

    def __init__(self, cfg_path: Path, traci_mod: Any) -> None:
        self.sumo_cfg_path = str(cfg_path)
        self._traci = traci_mod


def _sumo_binary() -> str:
    sumo_home = os.environ.get("SUMO_HOME")
    if not sumo_home:
        raise RuntimeError("SUMO_HOME 环境变量未设置（参考 scripts/activate_c_environment.*）")
    exe = Path(sumo_home) / "bin" / "sumo.exe"
    if not exe.exists():
        raise RuntimeError(f"SUMO 可执行文件未找到: {exe}")
    return str(exe)


def build_sumo_command(net: Path, rou: Path, add: Path | None,
                       begin: int, end: int, seed: int) -> list[str]:
    cmd = [
        _sumo_binary(),
        "--net-file", str(net),
        "--route-files", str(rou),
        "--begin", str(begin),
        "--end", str(end),
        "--step-length", "1",
        "--time-to-teleport", "-1",   # 与真实场景 sumocfg 一致：不瞬移
        "--collision.action", "warn",
        "--no-step-log",
        "--seed", str(seed),
    ]
    if add is not None:
        cmd += ["--additional-files", str(add)]
    return cmd


def install_fixed_time(traci_mod: Any, period: str, net: Path, cfg_path: Path) -> None:
    """为全部 30 路口安装真实定周期配时程序（sub_id = real_{period}）。"""
    shim = _ShimEnv(cfg_path, traci_mod)
    for jid in INTERSECTION_ORDER:
        controller = RealFixedTimeController(jid, period, net_xml_path=net)
        controller.install(shim)


def run_scenario(
    traci_mod: Any,
    scenario: str,
    perturbation: str,
    seed: int,
    begin: int,
    end: int,
    sample_sec: int,
    window_sec: int,
    label_stride: int,
    oracle: EventOracle,
    writer: Any,
) -> dict:
    """跑一次仿真并输出样本。返回该 run 的统计信息（含校准原始数据）。"""
    sc = SCENARIOS[scenario]
    spec = PERTURBATION_SPECS.get(perturbation)
    net = SUMO_FILES_DIR / "xiongan_30.net.xml"
    rou = SUMO_FILES_DIR / sc["rou"]
    add = (SUMO_FILES_DIR / spec["add_file"]) if spec else None
    cfg_path = SUMO_FILES_DIR / f"xiongan_{scenario}.sumocfg"

    port = BASE_PORT + (os.getpid() % 1000)
    cmd = build_sumo_command(net, rou, add, begin, end, seed)
    t0 = time.time()
    traci_mod.start(cmd, port=port, numRetries=1)

    try:
        install_fixed_time(traci_mod, sc["period"], net, cfg_path)

        window_steps = window_sec // sample_sec
        windows: dict[str, list[dict]] = {jid: [] for jid in INTERSECTION_ORDER}
        class_counts: dict[str, int] = {e: 0 for e in EVENT_CLASSES}
        run_samples = 0
        max_vehicle_count = 0
        calib: dict[str, list[float]] = {"dir_max_queue": [], "dir_max_occupancy": [], "dir_speed": []}
        last_log = -1

        while True:
            traci_mod.simulationStep()
            sim_time = float(traci_mod.simulation.getTime())

            if int(sim_time) % sample_sec == 0:
                vehicle_count = len(traci_mod.vehicle.getIDList())
                max_vehicle_count = max(max_vehicle_count, vehicle_count)
                for jid in INTERSECTION_ORDER:
                    snap = extract_intersection_raw(traci_mod, jid)
                    snap["t"] = sim_time
                    snap["vehicle_count"] = vehicle_count
                    windows[jid].append(snap)

            if sim_time >= window_sec and (int(sim_time) - window_sec) % label_stride == 0:
                for jid in INTERSECTION_ORDER:
                    snaps = windows[jid][-window_steps:]
                    windows[jid] = snaps  # 截断，防止无界增长
                    if len(snaps) < window_steps:
                        continue
                    label = oracle.label_window(jid, sim_time, snaps)
                    text = format_window_text(
                        jid, sc["cn"], sc["start_hour"], sim_time, snaps,
                        window_sec, sample_sec, snaps[-1]["vehicle_count"],
                    )
                    sample = {
                        "id": f"{scenario}-{perturbation}-{seed}-{int(sim_time)}-{jid}",
                        "scenario": scenario,
                        "scenario_cn": sc["cn"],
                        "perturbation": perturbation,
                        "seed": seed,
                        "sim_time": sim_time,
                        "clock": text.splitlines()[1].split("（")[0].replace("【时间】", ""),
                        "junction": jid,
                        "window_sec": window_sec,
                        "sample_sec": sample_sec,
                        "snapshots": snaps,
                        "text": text,
                        "label": {k: label[k] for k in ("event", "event_en", "confidence", "advice")},
                        "evidence": label["evidence"],
                        "target": format_label_json(label),
                    }
                    writer.write(json.dumps(sample, ensure_ascii=False) + "\n")
                    class_counts[label["event"]] += 1
                    run_samples += 1

                    # 阈值校准统计：取该路口窗口内每方向的最大排队/占有率与有车方向均速
                    dir_max_q = max(max(s["dirs"][d]["queue"] for d in s["dirs"]) for s in snaps)
                    dir_max_o = max(max(s["dirs"][d]["occupancy"] for d in s["dirs"]) for s in snaps)
                    calib["dir_max_queue"].append(dir_max_q)
                    calib["dir_max_occupancy"].append(dir_max_o)
                    speeds = []
                    for s in snaps:
                        for d in s["dirs"]:
                            if s["dirs"][d]["queue"] >= 1:
                                speeds.append(s["dirs"][d]["speed_kmh"])
                    if speeds:
                        calib["dir_speed"].append(statistics.mean(speeds))

            if sim_time >= end:
                break
            if int(sim_time) - last_log >= 600:
                last_log = int(sim_time)
                print(f"    [{sim_time:>6.0f}s/{end}s] 样本 {run_samples} 辆 {max_vehicle_count}")

        return {
            "scenario": scenario,
            "perturbation": perturbation,
            "seed": seed,
            "samples": run_samples,
            "classes": class_counts,
            "max_vehicle_count": max_vehicle_count,
            "wall_seconds": round(time.time() - t0, 1),
            "calib": calib,
        }
    finally:
        traci_mod.close()


def _percentiles(values: list[float]) -> dict:
    if not values:
        return {}
    values = sorted(values)
    n = len(values)
    out = {}
    for p in (50, 90, 95, 99):
        out[f"p{p}"] = round(values[min(n - 1, int(n * p / 100))], 3)
    out["max"] = round(values[-1], 3)
    out["n"] = n
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="生成赛道 C LLM 微调数据集（SUMO→规则 oracle 标注→JSONL）")
    parser.add_argument("--scenarios", default="real_peak,real_evening,real_offpeak",
                        help="真实场景，逗号分隔，可选: real_peak/real_offpeak/real_evening")
    parser.add_argument("--perturbations", default=f"{PERTURBATION_NONE},{PERTURBATION_CONSTRUCTION}",
                        help="扰动类型，逗号分隔，可选: none/construction")
    parser.add_argument("--seeds", default="42,43", help="随机种子（决定车辆到达时刻分布）")
    parser.add_argument("--begin", type=int, default=DEFAULT_BEGIN, help="仿真开始秒")
    parser.add_argument("--end", type=int, default=DEFAULT_END, help="仿真结束秒（场景默认 7200）")
    parser.add_argument("--sample-sec", type=int, default=DEFAULT_SAMPLE_SEC, help="状态采样步长（秒）")
    parser.add_argument("--window-sec", type=int, default=DEFAULT_WINDOW_SEC, help="输入窗口长度（秒）")
    parser.add_argument("--label-stride", type=int, default=DEFAULT_LABEL_STRIDE,
                        help="标注步长（秒），默认=window-sec（窗口不重叠）；小于窗口长则滑动重叠")
    parser.add_argument("--thresholds", default=None,
                        help='oracle 阈值覆盖 JSON，如 \'{"spillover_queue": 30}\'')
    parser.add_argument("--out", default="data/llm/dataset_v1.jsonl", help="输出 JSONL 路径")
    args = parser.parse_args()

    scenarios = [s.strip() for s in args.scenarios.split(",") if s.strip()]
    perturbations = [p.strip() for p in args.perturbations.split(",") if p.strip()]
    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    for s in scenarios:
        if s not in SCENARIOS:
            raise SystemExit(f"未知场景 {s!r}，可选 {list(SCENARIOS)}")
    for p in perturbations:
        if p not in PERTURBATION_SPECS:
            raise SystemExit(f"未知扰动 {p!r}，可选 {list(PERTURBATION_SPECS)}")
    label_stride = args.label_stride or args.window_sec
    if args.window_sec % args.sample_sec != 0:
        raise SystemExit("--window-sec 必须是 --sample-sec 的整数倍")
    if label_stride > args.window_sec:
        raise SystemExit("--label-stride 不应大于 --window-sec")

    thresholds = json.loads(args.thresholds) if args.thresholds else None
    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    oracle = EventOracle(perturbation=None, thresholds=thresholds)  # 按 run 更换 perturbation

    print(f"场景={scenarios} 扰动={perturbations} 种子={seeds} "
          f"窗口={args.window_sec}s 步长={label_stride}s 输出={out_path.name}")
    total_samples = 0
    total_classes: dict[str, int] = {e: 0 for e in EVENT_CLASSES}
    runs: list[dict] = []
    calib_all: dict[str, dict[str, list[float]]] = {}
    t_start = time.time()

    with out_path.open("w", encoding="utf-8") as writer:
        for scenario in scenarios:
            for perturbation in perturbations:
                oracle.perturbation = perturbation  # EventOracle 允许运行中切换扰动
                for seed in seeds:
                    print(f"[run] {scenario}-{perturbation}-{seed} ...")
                    import traci

                    run = run_scenario(
                        traci, scenario, perturbation, seed,
                        args.begin, args.end, args.sample_sec, args.window_sec,
                        label_stride, oracle, writer,
                    )
                    for cls, n in run["classes"].items():
                        total_classes[cls] += n
                    total_samples += run["samples"]
                    key = f"{scenario}-{perturbation}"
                    calib_all.setdefault(key, {})
                    for name, values in run["calib"].items():
                        calib_all[key].setdefault(name, []).extend(values)
                    runs.append(run)
                    print(f"  done: 样本 {run['samples']} "
                          f"耗时 {run['wall_seconds']}s 分类 {run['classes']}")

    # 聚合校准分位数（按场景-扰动合并）
    calibration = {}
    for key in sorted(calib_all):
        calibration[key] = {name: _percentiles(vals) for name, vals in calib_all[key].items()}

    stats = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "args": vars(args),
        "total_samples": total_samples,
        "class_distribution": total_classes,
        "class_distribution_en": {EVENT_EN[k]: v for k, v in total_classes.items()},
        "runs": runs,
        "calibration": calibration,
        "thresholds_used": oracle.thresholds,
    }
    stats_path = out_path.with_name(out_path.stem + "_stats.json")
    stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n=== 完成：{total_samples} 样本，总耗时 {time.time() - t_start:.0f}s ===")
    for cls in EVENT_CLASSES:
        print(f"  {cls}: {total_classes[cls]} ({total_classes[cls] / max(total_samples, 1):.1%})")
    print(f"统计与校准分位数 → {stats_path}")
    for key in sorted(calibration):
        q = calibration[key].get("dir_max_queue", {})
        print(f"  {key}: 方向最大排队 p50={q.get('p50')} p90={q.get('p90')} p99={q.get('p99')} max={q.get('max')}")


if __name__ == "__main__":
    main()
