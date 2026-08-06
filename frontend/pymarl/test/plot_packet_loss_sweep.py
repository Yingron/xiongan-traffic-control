#!/usr/bin/env python3
"""Plot paper-style packet-loss robustness results from evaluations.csv."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = ROOT / "results" / "packet_loss_sweep_160_165"

METHOD_STYLE = {
    "QMIX": {"color": "#D62728", "marker": "o"},
    "QMIX+TEE": {"color": "#1F4AFF", "marker": "^"},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_DIR / "evaluations.csv")
    parser.add_argument("--output", type=Path, default=DEFAULT_DIR)
    return parser.parse_args()


def configure_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "serif",
            "font.serif": ["Times New Roman", "DejaVu Serif"],
            "font.size": 11,
            "axes.labelsize": 11,
            "axes.titlesize": 12,
            "legend.fontsize": 10,
            "axes.linewidth": 1.0,
            "lines.linewidth": 2.0,
            "figure.dpi": 140,
            "savefig.dpi": 400,
            "savefig.bbox": "tight",
        }
    )


def load_data(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    numeric_columns = [
        column
        for column in frame.columns
        if column not in {"method", "model_dir"}
    ]
    frame[numeric_columns] = frame[numeric_columns].apply(pd.to_numeric, errors="coerce")
    return frame


def plot_metric(
    axis: plt.Axes,
    frame: pd.DataFrame,
    metric: str,
    title: str,
    ylabel: str,
    scale: float = 1.0,
    zero_origin: bool = False,
) -> None:
    for method in ("QMIX", "QMIX+TEE"):
        subset = frame[frame["method"] == method]
        if subset.empty or metric not in subset:
            continue
        grouped = subset.groupby("configured_packet_loss_percent")[metric]
        mean = grouped.mean().sort_index() * scale
        std = grouped.std(ddof=1).reindex(mean.index).fillna(0.0) * scale
        x = mean.index.to_numpy(dtype=float)
        y = mean.to_numpy(dtype=float)
        spread = std.to_numpy(dtype=float)
        style = METHOD_STYLE[method]
        axis.plot(
            x,
            y,
            label=method,
            color=style["color"],
            marker=style["marker"],
            markersize=5,
        )
        axis.fill_between(
            x,
            y - spread,
            y + spread,
            color=style["color"],
            alpha=0.16,
            linewidth=0,
        )

    axis.set_title(title)
    axis.set_xlabel("Configured Maximum Packet-Loss Scaling Factor (%)")
    axis.set_ylabel(ylabel)
    axis.set_xticks(sorted(frame["configured_packet_loss_percent"].dropna().unique()))
    if zero_origin:
        _, upper = axis.get_ylim()
        axis.set_ylim(0.0, upper)
    axis.grid(True, linestyle="--", linewidth=0.7, alpha=0.55)
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)


def save_figure(fig: plt.Figure, output: Path, stem: str) -> None:
    fig.tight_layout()
    fig.savefig(output / f"{stem}.png")
    fig.savefig(output / f"{stem}.pdf")
    plt.close(fig)


def performance_figure(frame: pd.DataFrame, output: Path) -> None:
    specs = [
        (
            "test_vehicle_completion_rate_mean",
            "Emergency-Vehicle Completion Rate",
            "Completion Rate (%)",
            100.0,
        ),
        (
            "test_completed_vehicle_arrival_time_mean_mean",
            "Completed-Vehicle Arrival Time",
            "Arrival Time (s)",
            1.0,
        ),
        (
            "test_vehicle_unfinished_avg_distance_mean",
            "Unfinished-Vehicle Remaining Distance",
            "Remaining Distance (m)",
            1.0,
        ),
        ("test_return_mean", "Evaluation Return", "Return", 1.0),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(11.2, 7.2))
    for axis, spec in zip(axes.flat, specs):
        plot_metric(axis, frame, *spec, zero_origin=True)
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=2, frameon=True)
    fig.subplots_adjust(top=0.89)
    save_figure(fig, output, "packet_loss_rescue_performance")


def wireless_figure(frame: pd.DataFrame, output: Path) -> None:
    specs = [
        (
            "test_packet_loss_probability_mean_mean",
            "Measured Mean Packet-Loss Probability",
            "Probability (%)",
            100.0,
        ),
        (
            "test_stale_observation_ratio_mean",
            "Stale Observation Ratio",
            "Stale Observations (%)",
            100.0,
        ),
        (
            "test_observation_age_seconds_mean_mean",
            "Mean Stale-Observation Age",
            "Observation Age (s)",
            1.0,
        ),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(15.2, 4.3))
    for axis, spec in zip(axes, specs):
        plot_metric(axis, frame, *spec)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=2, frameon=True)
    fig.subplots_adjust(top=0.82)
    save_figure(fig, output, "packet_loss_wireless_effect")


def behavior_figure(frame: pd.DataFrame, output: Path) -> None:
    specs = [
        (
            "test_trajectory_entropy_uturn_ratio_mean",
            "UTurn Ratio",
            "UTurn Ratio (%)",
            100.0,
        ),
        (
            "test_trajectory_entropy_repeat_cell_ratio_mean",
            "Local Repeat Ratio",
            "Repeat Ratio (%)",
            100.0,
        ),
        (
            "test_emergency_red_wait_seconds_mean_per_vehicle_mean",
            "Emergency-Vehicle Red-Light Waiting",
            "Seconds per Vehicle",
            1.0,
        ),
        (
            "test_emergency_green_time_ratio_mean",
            "Emergency Green-Time Ratio",
            "Green Exposure (%)",
            100.0,
        ),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(11.2, 7.2))
    for axis, spec in zip(axes.flat, specs):
        plot_metric(axis, frame, *spec)
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=2, frameon=True)
    fig.subplots_adjust(top=0.89)
    save_figure(fig, output, "packet_loss_behavior_metrics")


def individual_figures(frame: pd.DataFrame, output: Path) -> None:
    specs = [
        ("test_vehicle_completion_rate_mean", "Completion Rate", "Completion Rate (%)", 100.0),
        (
            "test_completed_vehicle_arrival_time_mean_mean",
            "Arrival Time",
            "Arrival Time (s)",
            1.0,
        ),
        (
            "test_vehicle_unfinished_avg_distance_mean",
            "Remaining Distance",
            "Remaining Distance (m)",
            1.0,
        ),
        (
            "test_stale_observation_ratio_mean",
            "Stale Observation Ratio",
            "Stale Observations (%)",
            100.0,
        ),
        (
            "test_packet_loss_probability_mean_mean",
            "Measured Packet-Loss Probability",
            "Probability (%)",
            100.0,
        ),
        (
            "test_observation_age_seconds_mean_mean",
            "Mean Observation Age",
            "Observation Age (s)",
            1.0,
        ),
    ]
    for metric, title, ylabel, scale in specs:
        fig, axis = plt.subplots(figsize=(6.2, 4.4))
        plot_metric(axis, frame, metric, title, ylabel, scale)
        axis.legend(loc="best", frameon=True)
        save_figure(fig, output, metric.removeprefix("test_").removesuffix("_mean"))


def main() -> int:
    args = parse_args()
    args.input = args.input.resolve()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    configure_style()
    frame = load_data(args.input)
    performance_figure(frame, args.output)
    wireless_figure(frame, args.output)
    behavior_figure(frame, args.output)
    individual_figures(frame, args.output)
    print(f"Generated figures in {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
