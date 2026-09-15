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
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })
    figure, axes = plt.subplots(1, 3, figsize=(7.25, 3.15), constrained_layout=True)

    combined = scenarios["combined_mismatch"]["policies"]
    false_counts = [combined[name]["false_confidence_count"] for name, _ in POLICIES]
    x = np.arange(len(POLICIES))
    bars = axes[0].bar(x, false_counts, color="0.78", edgecolor="black", linewidth=0.7)
    for index, bar in enumerate(bars):
        bar.set_hatch("///" if index < 6 else "...")
    axes[0].bar_label(bars, padding=2, fontsize=7)
    axes[0].set_xticks(x, [label for _, label in POLICIES], rotation=55, ha="right")
    axes[0].set_ylim(0, 32)
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
        bounds = [scenarios[name]["paired_strong_comparator_contrasts"][key]
                  ["paired_difference"] for name, _ in SCENARIOS]
        errors = [[value - row["bootstrap_mean_ci95_low"] for value, row in zip(values, bounds)],
                  [row["bootstrap_mean_ci95_high"] - value for value, row in zip(values, bounds)]]
        axes[1].bar(
            scenario_x + (offset - 0.5) * width,
            values,
            width,
            label=label,
            color=shade,
            edgecolor="black",
            linewidth=0.7,
            hatch=hatch,
            yerr=errors,
            capsize=2,
            error_kw={"elinewidth": 0.8, "capthick": 0.8},
        )
    axes[1].axhline(0, color="black", linewidth=0.8)
    axes[1].set_xticks(scenario_x, [label for _, label in SCENARIOS], rotation=40, ha="right")
    axes[1].set_ylabel("Comparator − EIG (measurements)")
    axes[1].set_title("(b) Raw count contrast")
    axes[1].set_ylim(-0.025, 0.35)
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
        bounds = [scenarios[name]["paired_strong_comparator_contrasts"][key]
                  ["paired_difference"] for name, _ in SCENARIOS]
        errors = [[value - row["bootstrap_mean_ci95_low"] for value, row in zip(values, bounds)],
                  [row["bootstrap_mean_ci95_high"] - value for value, row in zip(values, bounds)]]
        axes[2].bar(
            scenario_x + (offset - 0.5) * width,
            values,
            width,
            label=label,
            color=shade,
            edgecolor="black",
            linewidth=0.7,
            hatch=hatch,
            yerr=errors,
            capsize=2,
            error_kw={"elinewidth": 0.8, "capthick": 0.8},
        )
    axes[2].axhline(0, color="black", linewidth=0.8)
    axes[2].set_xticks(scenario_x, [label for _, label in SCENARIOS], rotation=40, ha="right")
    axes[2].set_ylabel("Comparator − EIG/c (cost units)")
    axes[2].set_title("(c) Modeled-cost contrast")
    axes[2].set_ylim(-18, 4)
    figure.legend(*axes[1].get_legend_handles_labels(), frameon=False,
                  fontsize=8, loc="outside lower center", ncol=2,
                  title="Paired mean difference with 95% bootstrap interval (b, c)",
                  title_fontsize=8)
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
    vector_output = output.with_suffix(".pdf")
    figure.savefig(vector_output, bbox_inches="tight",
                   metadata={"Creator": "magcore_calib evidence renderer",
                             "CreationDate": None, "ModDate": None})
    plt.close(figure)
    manifest = {
        "schema_version": "magcore-model-mismatch-figure/1.0",
        "campaign_id": "MM-3",
        "source": aggregate_path.as_posix(),
        "source_sha256": sha256_file(aggregate_path),
        "figure": output.name,
        "figure_sha256": sha256_file(output),
        "vector_figure": vector_output.name,
        "vector_figure_sha256": sha256_file(vector_output),
        "panels": [
            "combined-mismatch false-confidence count by policy",
            "raw EIG paired measurement-count contrasts",
            "EIG/cost paired modeled-cost contrasts",
        ],
        "difference_definition": "comparator_minus_eig",
        "positive_difference_favors": "eig",
        "interval": "95% paired-bootstrap mean interval; descriptive, not multiplicity-adjusted",
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
