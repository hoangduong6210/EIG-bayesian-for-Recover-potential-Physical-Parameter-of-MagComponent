#!/usr/bin/env python3
"""Render the evidence-bound black-and-white MM-3 result figure."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


SCENARIOS = (
    ("matched_control", "Matched"),
    ("permeability_two_pole", "Two-pole"),
    ("core_loss_temperature_curvature", "Loss curve"),
    ("combined_mismatch", "Combined"),
)
POLICIES = (
    ("eig_raw", "EIG"),
    ("predictive_variance_raw", "PV"),
    ("laplace_d_opt_raw", "Laplace"),
    ("eig_per_cost", "EIG/c"),
    ("predictive_variance_per_cost", "PV/c"),
    ("laplace_d_opt_per_cost", "Laplace/c"),
    ("fixed_channel_balanced", "Fixed"),
    ("random_channel_balanced", "Random"),
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render(aggregate_path: Path, output: Path, manifest_path: Path) -> dict:
    aggregate = json.loads(aggregate_path.read_text(encoding="utf-8"))
    if aggregate.get("schema_version") != "magcore-model-mismatch-aggregate/1.0" \
            or aggregate.get("campaign_id") != "MM-3" \
            or aggregate.get("source_result_count") != 120:
        raise ValueError("figure input is not the admitted MM-3 aggregate")
    scenarios = aggregate["scenarios"]

    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": 8,
        "axes.linewidth": 0.8,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
    })
    figure, axes = plt.subplots(1, 3, figsize=(7.5, 2.75), constrained_layout=True)

    combined = scenarios["combined_mismatch"]["policies"]
    false_counts = [combined[name]["false_confidence_count"] for name, _ in POLICIES]
    x = np.arange(len(POLICIES))
    bars = axes[0].bar(x, false_counts, color="0.78", edgecolor="black", linewidth=0.7)
    for index, bar in enumerate(bars):
        bar.set_hatch("///" if index < 6 else "...")
    axes[0].set_xticks(x, [label for _, label in POLICIES], rotation=55, ha="right")
    axes[0].set_ylim(0, 30)
    axes[0].set_ylabel("False-confident seeds (of 30)")
    axes[0].set_title("(a) Combined mismatch")
    axes[0].grid(axis="y", color="0.88", linewidth=0.5)

    scenario_x = np.arange(len(SCENARIOS))
    raw_contrasts = (
        ("eig_raw_vs_predictive_variance_raw", "vs PV", "0.25", "///"),
        ("eig_raw_vs_laplace_d_opt_raw", "vs Laplace", "0.72", "..."),
    )
    width = 0.34
    for offset, (key, label, shade, hatch) in enumerate(raw_contrasts):
        values = [
            scenarios[name]["paired_strong_comparator_contrasts"][key]
            ["paired_difference"]["mean"]
            for name, _ in SCENARIOS
        ]
        axes[1].bar(
            scenario_x + (offset - 0.5) * width,
            values,
            width,
            label=label,
            color=shade,
            edgecolor="black",
            linewidth=0.7,
            hatch=hatch,
        )
    axes[1].axhline(0, color="black", linewidth=0.8)
    axes[1].set_xticks(scenario_x, [label for _, label in SCENARIOS], rotation=40, ha="right")
    axes[1].set_ylabel("Comparator − EIG (measurements)")
    axes[1].set_title("(b) Raw count contrast")
    axes[1].set_ylim(0, 0.215)
    axes[1].legend(frameon=False, fontsize=7, loc="upper center", ncol=2)
    axes[1].grid(axis="y", color="0.88", linewidth=0.5)

    cost_contrasts = (
        ("eig_per_cost_vs_predictive_variance_per_cost", "vs PV", "0.25", "///"),
        ("eig_per_cost_vs_laplace_d_opt_per_cost", "vs Laplace", "0.72", "..."),
    )
    for offset, (key, label, shade, hatch) in enumerate(cost_contrasts):
        values = [
            scenarios[name]["paired_strong_comparator_contrasts"][key]
            ["paired_difference"]["mean"]
            for name, _ in SCENARIOS
        ]
        axes[2].bar(
            scenario_x + (offset - 0.5) * width,
            values,
            width,
            label=label,
            color=shade,
            edgecolor="black",
            linewidth=0.7,
            hatch=hatch,
        )
    axes[2].axhline(0, color="black", linewidth=0.8)
    axes[2].set_xticks(scenario_x, [label for _, label in SCENARIOS], rotation=40, ha="right")
    axes[2].set_ylabel("Comparator − EIG/c (cost units)")
    axes[2].set_title("(c) Modeled-cost contrast")
    axes[2].set_ylim(-16.2, 2.0)
    axes[2].legend(frameon=False, fontsize=7, loc="upper center", ncol=2)
    axes[2].grid(axis="y", color="0.88", linewidth=0.5)

    for axis in axes:
        axis.spines["top"].set_visible(False)
        axis.spines["right"].set_visible(False)
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(
        output,
        dpi=300,
        bbox_inches="tight",
        metadata={"Software": "magcore_calib evidence renderer"},
    )
    plt.close(figure)
    manifest = {
        "schema_version": "magcore-model-mismatch-figure/1.0",
        "campaign_id": "MM-3",
        "source": aggregate_path.as_posix(),
        "source_sha256": sha256_file(aggregate_path),
        "figure": output.name,
        "figure_sha256": sha256_file(output),
        "panels": [
            "combined-mismatch false-confidence count by policy",
            "raw EIG paired measurement-count contrasts",
            "EIG/cost paired modeled-cost contrasts",
        ],
        "difference_definition": "comparator_minus_eig",
        "positive_difference_favors": "eig",
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--aggregate", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(render(args.aggregate, args.output, args.manifest), indent=2))


if __name__ == "__main__":
    main()
