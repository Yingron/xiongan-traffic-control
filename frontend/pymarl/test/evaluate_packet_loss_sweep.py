#!/usr/bin/env python3
"""Evaluate trained Sacred runs under packet-loss-induced stale observations.

The script:
1. selects each training run's best validation step using the task-quality score;
2. resolves the nearest saved checkpoint;
3. evaluates every run sequentially against one Unity instance;
4. stores all scalar test metrics in wide/long CSV files and preserves raw Sacred data.

It is safe to stop and restart: completed (run, packet-loss level) pairs are skipped.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


ROOT = Path(__file__).resolve().parents[1]
SACRED_DIR = ROOT / "results" / "sacred"
MODELS_DIR = ROOT / "results" / "models"

SELECTION_METRICS = {
    "completion_rate": "test_vehicle_completion_rate_mean",
    "avg_seconds": "test_vehicle_all_avg_seconds_mean",
    "unfinished_distance": "test_vehicle_unfinished_avg_distance_mean",
    "uturn_ratio": "test_trajectory_entropy_uturn_ratio_mean",
}

# The columns most likely to be used directly in paper plots/tables.
PAPER_METRICS = [
    "test_vehicle_completion_rate_mean",
    "test_vehicle_completed_count_mean",
    "test_vehicle_all_avg_seconds_mean",
    "test_completed_vehicle_arrival_time_mean_mean",
    "test_completed_vehicle_arrival_time_p95_mean",
    "test_vehicle_timeout_rate_mean",
    "test_vehicle_unfinished_avg_distance_mean",
    "test_vehicle_unfinished_max_distance_mean",
    "test_return_mean",
    "test_trajectory_heatmap_coverage_mean",
    "test_road_visit_entropy_mean",
    "test_trajectory_entropy_uturn_ratio_mean",
    "test_trajectory_entropy_repeat_cell_ratio_mean",
    "test_trajectory_road_repeat_ratio_mean",
    "test_emergency_red_wait_seconds_mean_per_vehicle_mean",
    "test_emergency_green_time_ratio_mean",
    "test_stale_observation_ratio_mean",
    "test_packet_loss_probability_mean_mean",
    "test_packet_loss_probability_p95_mean",
    "test_observation_age_steps_mean_mean",
    "test_observation_age_steps_p95_mean",
    "test_observation_age_seconds_mean_mean",
    "test_observation_age_seconds_p95_mean",
]

REQUIRED_WIRELESS_METRICS = [
    "test_stale_observation_ratio_mean",
    "test_packet_loss_probability_mean_mean",
    "test_observation_age_seconds_mean_mean",
]

IDENTITY_FIELDS = [
    "source_run",
    "method",
    "seed",
    "wireless_model",
    "configured_packet_loss",
    "configured_packet_loss_percent",
    "best_validation_step",
    "selected_checkpoint_step",
    "selection_score",
    "model_dir",
    "evaluation_sacred_run",
    "test_nepisode",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate runs under packet-loss levels using one Unity server."
    )
    parser.add_argument("--runs", nargs="+", type=int, default=list(range(160, 166)))
    parser.add_argument(
        "--loss-levels",
        nargs="+",
        type=float,
        default=[0, 5, 10, 15, 20, 25, 30],
        help="Configured maximum packet-loss scaling levels in percent.",
    )
    parser.add_argument("--port", type=int, default=5001)
    parser.add_argument("--episodes", type=int, default=100)
    parser.add_argument("--test-seed-base", type=int, default=900000)
    parser.add_argument(
        "--python",
        type=Path,
        default=None,
        help="Python executable containing torch and sacred; auto-detects citysim when omitted.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "results" / "packet_loss_sweep_160_165",
    )
    parser.add_argument(
        "--model-map",
        nargs="*",
        default=[],
        metavar="RUN=PATH",
        help="Explicit model directory override, e.g. 160=results/models/run_dir.",
    )
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="Evaluate available runs and skip runs whose checkpoints are missing.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-run combinations already present in evaluations.csv.",
    )
    parser.add_argument(
        "--allow-missing-wireless-metrics",
        action="store_true",
        help="Do not stop when Unity omits stale-observation/packet-loss metrics.",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def numeric(value: Any) -> Optional[float]:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def last_numeric(value: Any) -> Optional[float]:
    if isinstance(value, list):
        for item in reversed(value):
            result = numeric(item)
            if result is not None:
                return result
        return None
    return numeric(value)


def aligned_series(info: Mapping[str, Any], key: str) -> Tuple[List[float], List[float]]:
    values = info.get(key, [])
    steps = info.get(f"{key}_T", [])
    if not isinstance(values, list) or not isinstance(steps, list):
        return [], []
    count = min(len(values), len(steps))
    out_steps: List[float] = []
    out_values: List[float] = []
    for step, value in zip(steps[:count], values[:count]):
        step_num = numeric(step)
        value_num = numeric(value)
        if step_num is not None and value_num is not None:
            out_steps.append(step_num)
            out_values.append(value_num)
    return out_steps, out_values


def choose_best_validation(info: Mapping[str, Any]) -> Tuple[int, float, Dict[str, float]]:
    series: Dict[str, Dict[int, float]] = {}
    for label, key in SELECTION_METRICS.items():
        steps, values = aligned_series(info, key)
        series[label] = {int(round(step)): value for step, value in zip(steps, values)}

    common_steps = set.intersection(*(set(values) for values in series.values()))
    if not common_steps:
        raise ValueError("Required validation metrics have no aligned steps.")

    candidates: List[Tuple[float, int, Dict[str, float]]] = []
    for step in sorted(common_steps):
        metrics = {label: values[step] for label, values in series.items()}
        score = (
            100.0 * metrics["completion_rate"]
            - 0.2 * metrics["avg_seconds"]
            - 0.01 * metrics["unfinished_distance"]
            - 20.0 * metrics["uturn_ratio"]
        )
        candidates.append((score, step, metrics))

    # A later step wins only when the task-quality score is exactly tied.
    score, step, metrics = max(candidates, key=lambda item: (item[0], item[1]))
    return step, score, metrics


def parse_model_map(entries: Sequence[str]) -> Dict[int, Path]:
    result: Dict[int, Path] = {}
    for entry in entries:
        if "=" not in entry:
            raise ValueError(f"Invalid --model-map value: {entry!r}")
        run_text, path_text = entry.split("=", 1)
        path = Path(path_text)
        if not path.is_absolute():
            path = ROOT / path
        result[int(run_text)] = path.resolve()
    return result


def timestamp_from_model_dir(path: Path) -> Optional[datetime]:
    marker = "__"
    if marker not in path.name:
        return None
    try:
        return datetime.strptime(path.name.rsplit(marker, 1)[1], "%Y-%m-%d_%H-%M-%S")
    except ValueError:
        return None


def discover_model_dir(run_id: int, override: Optional[Path]) -> Optional[Path]:
    if override is not None:
        return override if override.is_dir() else None

    run_data = load_json(SACRED_DIR / str(run_id) / "run.json")
    start_text = run_data.get("start_time")
    if not isinstance(start_text, str):
        return None

    # Sacred stores UTC-like timestamps while model directory names use local UTC+8.
    start_local = datetime.fromisoformat(start_text) + timedelta(hours=8)
    candidates: List[Tuple[float, Path]] = []
    for path in MODELS_DIR.iterdir():
        if not path.is_dir():
            continue
        timestamp = timestamp_from_model_dir(path)
        if timestamp is None:
            continue
        delta = abs((timestamp - start_local).total_seconds())
        if delta <= 10 * 60:
            candidates.append((delta, path.resolve()))
    return min(candidates, default=(0.0, None), key=lambda item: item[0])[1]


def checkpoint_steps(model_dir: Path) -> List[int]:
    return sorted(
        int(path.name)
        for path in model_dir.iterdir()
        if path.is_dir() and path.name.isdigit() and (path / "agent.th").is_file()
    )


def nearest_checkpoint(model_dir: Path, target_step: int) -> int:
    steps = checkpoint_steps(model_dir)
    if not steps:
        raise ValueError(f"No valid checkpoint containing agent.th: {model_dir}")
    return min(steps, key=lambda step: (abs(step - target_step), -step))


def method_name(config: Mapping[str, Any]) -> str:
    env_args = config.get("env_args", {})
    tee = isinstance(env_args, dict) and bool(env_args.get("trajectory_entropy_enabled", False))
    return "QMIX+TEE" if tee else "QMIX"


def existing_pairs(csv_path: Path) -> set[Tuple[int, float]]:
    if not csv_path.is_file():
        return set()
    pairs: set[Tuple[int, float]] = set()
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                pairs.add((int(row["source_run"]), round(float(row["configured_packet_loss"]), 8)))
            except (KeyError, TypeError, ValueError):
                continue
    return pairs


def numeric_sacred_dirs() -> set[int]:
    return {
        int(path.name)
        for path in SACRED_DIR.iterdir()
        if path.is_dir() and path.name.isdigit()
    }


def build_command(
    run_id: int,
    config: Mapping[str, Any],
    model_dir: Path,
    checkpoint_step: int,
    loss_probability: float,
    args: argparse.Namespace,
) -> List[str]:
    seed = int(config["seed"])
    python_executable = resolve_python_executable(args.python)
    try:
        checkpoint_arg = model_dir.relative_to(ROOT).as_posix()
    except ValueError:
        checkpoint_arg = model_dir.as_posix()
    return [
        str(python_executable),
        str(ROOT / "src" / "main.py"),
        "--config=qmix_dual",
        "with",
        f"checkpoint_path={checkpoint_arg}",
        f"load_step={checkpoint_step}",
        "evaluate=True",
        f"test_nepisode={args.episodes}",
        "save_model=False",
        "save_replay=False",
        "test_greedy=True",
        f"seed={seed}",
        f"env_args.port={args.port}",
        "env_args.simulate_packet_loss=True",
        f"env_args.max_packet_loss_probability={loss_probability:.8f}",
        "env_args.trajectory_entropy_enabled=False",
        f"env_args.test_seed_base={args.test_seed_base}",
        f"env_args.test_seed_count={args.episodes}",
        f"label=packet_loss_sweep_source_{run_id}",
    ]


def resolve_python_executable(override: Optional[Path]) -> Path:
    if override is not None:
        path = override.expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Python executable does not exist: {path}")
        return path

    citysim = Path.home() / "anaconda3" / "envs" / "citysim" / "python.exe"
    if citysim.is_file():
        return citysim
    return Path(sys.executable).resolve()


def run_evaluation(command: Sequence[str], log_path: Path) -> int:
    with log_path.open("w", encoding="utf-8", newline="") as log:
        process = subprocess.run(
            list(command),
            cwd=ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=False,
        )
    return int(process.returncode)


def find_new_sacred_run(before: set[int]) -> int:
    created = sorted(numeric_sacred_dirs() - before)
    if not created:
        raise RuntimeError("Evaluation did not create a new Sacred result directory.")
    return created[-1]


def extract_scalar_test_metrics(info: Mapping[str, Any]) -> Dict[str, float]:
    metrics: Dict[str, float] = {}
    for key, value in info.items():
        if not key.startswith("test_") or key.endswith("_T"):
            continue
        result = last_numeric(value)
        if result is not None:
            metrics[key] = result
    return metrics


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]], preferred: Sequence[str]) -> None:
    if not rows:
        return
    all_fields = {key for row in rows for key in row}
    fields = [key for key in preferred if key in all_fields]
    fields.extend(sorted(all_fields - set(fields)))
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temp_path.replace(path)


def read_rows(path: Path) -> List[Dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def rebuild_long_csv(wide_rows: Sequence[Mapping[str, Any]], path: Path) -> None:
    long_rows: List[Dict[str, Any]] = []
    identity = set(IDENTITY_FIELDS)
    for row in wide_rows:
        base = {key: row.get(key, "") for key in IDENTITY_FIELDS}
        for key, value in row.items():
            if key in identity or not key.startswith("test_") or value in ("", None):
                continue
            long_rows.append({**base, "metric": key, "value": value})
    write_csv(path, long_rows, [*IDENTITY_FIELDS, "metric", "value"])


def copy_raw_sacred(run_id: int, target: Path) -> None:
    source = SACRED_DIR / str(run_id)
    target.mkdir(parents=True, exist_ok=True)
    for name in ("config.json", "info.json", "run.json", "cout.txt"):
        source_path = source / name
        if source_path.is_file():
            shutil.copy2(source_path, target / name)


def main() -> int:
    args = parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "logs").mkdir(exist_ok=True)
    (args.output / "raw_sacred").mkdir(exist_ok=True)

    overrides = parse_model_map(args.model_map)
    selections: List[Dict[str, Any]] = []
    missing: List[int] = []

    for run_id in args.runs:
        run_dir = SACRED_DIR / str(run_id)
        config = load_json(run_dir / "config.json")
        info = load_json(run_dir / "info.json")
        best_step, score, validation = choose_best_validation(info)
        model_dir = discover_model_dir(run_id, overrides.get(run_id))
        if model_dir is None:
            missing.append(run_id)
            selections.append(
                {
                    "source_run": run_id,
                    "method": method_name(config),
                    "seed": config.get("seed"),
                    "best_validation_step": best_step,
                    "selection_score": score,
                    "model_dir": "",
                    "selected_checkpoint_step": "",
                    "status": "missing_model",
                    **{f"selection_{key}": value for key, value in validation.items()},
                }
            )
            continue

        checkpoint_step = nearest_checkpoint(model_dir, best_step)
        selections.append(
            {
                "source_run": run_id,
                "method": method_name(config),
                "seed": config.get("seed"),
                "best_validation_step": best_step,
                "selection_score": score,
                "model_dir": str(model_dir),
                "selected_checkpoint_step": checkpoint_step,
                "status": "ready",
                **{f"selection_{key}": value for key, value in validation.items()},
            }
        )

    write_csv(
        args.output / "selected_checkpoints.csv",
        selections,
        [
            "source_run",
            "method",
            "seed",
            "best_validation_step",
            "selected_checkpoint_step",
            "selection_score",
            "model_dir",
            "status",
        ],
    )

    if missing and not args.allow_missing:
        joined = ", ".join(str(run_id) for run_id in missing)
        print(f"Missing model directories for runs: {joined}", file=sys.stderr)
        print(
            "Restore them or pass --model-map RUN=PATH. "
            "Use --allow-missing to evaluate only available runs.",
            file=sys.stderr,
        )
        return 2

    wide_path = args.output / "evaluations.csv"
    wide_rows: List[Dict[str, Any]] = read_rows(wide_path)
    done = set() if args.force else existing_pairs(wide_path)

    ready = [row for row in selections if row["status"] == "ready"]
    for selection in ready:
        run_id = int(selection["source_run"])
        config = load_json(SACRED_DIR / str(run_id) / "config.json")
        model_dir = Path(str(selection["model_dir"]))
        checkpoint_step = int(selection["selected_checkpoint_step"])

        for loss_percent in args.loss_levels:
            loss_probability = float(loss_percent) / 100.0
            pair = (run_id, round(loss_probability, 8))
            if pair in done:
                print(f"[skip] run={run_id} loss={loss_percent:g}%")
                continue

            command = build_command(
                run_id,
                config,
                model_dir,
                checkpoint_step,
                loss_probability,
                args,
            )
            print(f"[run] source={run_id} loss={loss_percent:g}% checkpoint={checkpoint_step}")
            if args.dry_run:
                print(subprocess.list2cmdline(command))
                continue

            before = numeric_sacred_dirs()
            log_path = args.output / "logs" / f"run_{run_id}_loss_{loss_percent:g}.log"
            return_code = run_evaluation(command, log_path)
            if return_code != 0:
                raise RuntimeError(
                    f"Evaluation failed for source run {run_id}, loss={loss_percent:g}%. "
                    f"Exit code={return_code}; log={log_path}"
                )
            evaluation_run = find_new_sacred_run(before)

            eval_dir = SACRED_DIR / str(evaluation_run)
            eval_info = load_json(eval_dir / "info.json")
            metrics = extract_scalar_test_metrics(eval_info)
            missing_wireless = [
                key for key in REQUIRED_WIRELESS_METRICS if key not in metrics
            ]
            if missing_wireless and not args.allow_missing_wireless_metrics:
                names = ", ".join(missing_wireless)
                raise RuntimeError(
                    "Unity did not return required wireless metrics: "
                    f"{names}. The running Unity instance is likely an old build "
                    "or has not recompiled the current NetworkInterface/"
                    "VehicleObservationDelayBuffer code. "
                    f"Sacred run={evaluation_run}; log={log_path}"
                )
            if loss_probability > 0.0 and not args.allow_missing_wireless_metrics:
                measured_probability = metrics.get(
                    "test_packet_loss_probability_mean_mean", 0.0
                )
                stale_ratio = metrics.get("test_stale_observation_ratio_mean", 0.0)
                if measured_probability < 0.1 * loss_probability or stale_ratio <= 0.0:
                    raise RuntimeError(
                        "Wireless stress is present in the configuration but is not "
                        "materially affecting observations. Expected measured packet-loss "
                        f"probability >= {0.1 * loss_probability:.6f} and a non-zero stale "
                        f"ratio; got probability={measured_probability:.6f}, "
                        f"stale_ratio={stale_ratio:.6f}. Sacred run={evaluation_run}"
                    )
            row: Dict[str, Any] = {
                "source_run": run_id,
                "method": selection["method"],
                "seed": selection["seed"],
                "wireless_model": "urban_distance_hold_last_v2",
                "configured_packet_loss": loss_probability,
                "configured_packet_loss_percent": loss_percent,
                "best_validation_step": selection["best_validation_step"],
                "selected_checkpoint_step": checkpoint_step,
                "selection_score": selection["selection_score"],
                "model_dir": str(model_dir),
                "evaluation_sacred_run": evaluation_run,
                "test_nepisode": args.episodes,
                **metrics,
            }
            wide_rows = [
                old
                for old in wide_rows
                if not (
                    int(old["source_run"]) == run_id
                    and round(float(old["configured_packet_loss"]), 8)
                    == round(loss_probability, 8)
                )
            ]
            wide_rows.append(row)
            wide_rows.sort(
                key=lambda item: (
                    int(item["source_run"]),
                    float(item["configured_packet_loss"]),
                )
            )
            write_csv(wide_path, wide_rows, [*IDENTITY_FIELDS, *PAPER_METRICS])
            rebuild_long_csv(wide_rows, args.output / "evaluations_long.csv")
            copy_raw_sacred(
                evaluation_run,
                args.output
                / "raw_sacred"
                / f"source_{run_id}"
                / f"loss_{loss_percent:g}",
            )
            done.add(pair)

    if args.dry_run:
        print("Dry run completed; no evaluations were launched.")
    else:
        print(f"Completed. Data: {wide_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
