"""Benchmark and tune static phase durations for the 20-intersection network.

The script keeps the four RL action phases intact and compares phase-duration
plans under identical traffic demand.  It is intentionally independent of a
trained DQN so that SUMO engineers can establish a reproducible baseline
before model training begins.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path


PLANS: dict[str, tuple[int, int, int, int]] = {
    "balanced": (30, 12, 30, 12),
    "throughput_favored": (36, 8, 36, 8),
    "turn_protection": (30, 16, 30, 16),
}


def set_phase_durations(net_path: Path, durations: tuple[int, int, int, int]) -> None:
    tree = ET.parse(net_path)
    for logic in tree.getroot().findall("tlLogic"):
        if logic.get("id", "").startswith("J"):
            phases = logic.findall("phase")
            if len(phases) != 4:
                raise ValueError(f"{logic.get('id')} does not have exactly four phases")
            for phase, duration in zip(phases, durations):
                phase.set("duration", str(duration))
    tree.write(net_path, encoding="UTF-8", xml_declaration=True)


def parse_last_summary(summary_path: Path) -> dict[str, float | int]:
    root = ET.parse(summary_path).getroot()
    steps = root.findall("step")
    if not steps:
        raise RuntimeError("SUMO did not write any summary steps")
    last = steps[-1]
    keys = ("ended", "collisions", "teleports", "halting")
    metrics: dict[str, float | int] = {key: int(last.get(key, "0")) for key in keys}
    metrics["mean_waiting_time"] = float(last.get("meanWaitingTime", "0"))
    metrics["mean_travel_time"] = float(last.get("meanTravelTime", "0"))
    return metrics


def benchmark_plan(sumo_cfg: Path, source_net: Path, plan: str, durations: tuple[int, int, int, int], end: int) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="xiongan_phase_tuning_") as temp_dir:
        temp = Path(temp_dir)
        tuned_net = temp / "tuned.net.xml"
        summary = temp / "summary.xml"
        shutil.copy2(source_net, tuned_net)
        set_phase_durations(tuned_net, durations)
        command = [
            "sumo", "-c", str(sumo_cfg), "--net-file", str(tuned_net), "--end", str(end),
            "--summary-output", str(summary), "--no-step-log", "true", "--duration-log.statistics", "true",
        ]
        completed = subprocess.run(command, text=True, capture_output=True, check=False)
        if completed.returncode:
            raise RuntimeError(f"{plan} failed:\n{completed.stderr[-2000:]}")
        metrics = parse_last_summary(summary)
    score = float(metrics["mean_waiting_time"]) + 0.1 * float(metrics["mean_travel_time"]) + 50 * int(metrics["collisions"]) + 50 * int(metrics["teleports"])
    return {"plan": plan, "durations": list(durations), **metrics, "score": round(score, 4)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sumo-cfg", type=Path, default=Path("sumo_files/xiongan_30.sumocfg"))
    parser.add_argument("--net", type=Path, default=Path("sumo_files/xiongan_30.net.xml"))
    parser.add_argument("--end", type=int, default=600, help="Simulation seconds per plan")
    parser.add_argument("--output", type=Path, default=Path("logs/phase_tuning_results.json"))
    parser.add_argument("--apply-best", action="store_true", help="Write the selected phase durations to --net")
    args = parser.parse_args()
    results = [benchmark_plan(args.sumo_cfg, args.net, name, durations, args.end) for name, durations in PLANS.items()]
    results.sort(key=lambda row: float(row["score"]))
    payload = {"window_seconds": args.end, "objective": "mean_waiting_time + 0.1 * mean_travel_time; collisions/teleports penalized", "results": results, "best": results[0]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for row in results:
        print(f"{row['plan']:18s} durations={row['durations']} wait={row['mean_waiting_time']:.2f}s travel={row['mean_travel_time']:.2f}s ended={row['ended']} score={row['score']:.3f}")
    if args.apply_best:
        set_phase_durations(args.net, tuple(payload["best"]["durations"]))  # type: ignore[arg-type]
        print(f"Applied {payload['best']['plan']} to {args.net}")
    print(f"Saved results to {args.output}")


if __name__ == "__main__":
    main()
