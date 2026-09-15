#!/usr/bin/env python3
"""Generate grayscale, wiki-native scientific summary figures."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import numpy as np


ASSET_ROOT = Path(__file__).resolve().parent
WIKI_ROOT = ASSET_ROOT.parent
EVIDENCE_PATH = WIKI_ROOT / "evidence" / "results.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_rows():
    evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    endpoints = evidence["results"]["policy_endpoints"]
    contrasts = evidence["results"]["primary_contrasts"]

    count_specs = (
        ("Raw EIG", "eig_raw", "o"),
        ("Predictive variance", "predictive_variance_raw", "x"),
        ("Laplace D-optimal", "laplace_d_opt_raw", "s"),
        ("Random balanced", "random_channel_balanced", "^"),
        ("Fixed traversal", "fixed_channel_balanced", "D"),
    )
    policy_counts = tuple(
        (
            label,
            endpoints[key]["measurement_count"]["mean"],
            endpoints[key]["measurement_count"]["minimum"],
            endpoints[key]["measurement_count"]["maximum"],
            marker,
        )
        for label, key, marker in count_specs
    )

    contrast_specs = (
        ("Raw EIG vs PV", "eig_raw_vs_predictive_variance_raw"),
        ("Raw EIG vs D-opt", "eig_raw_vs_laplace_d_opt_raw"),
        ("EIG/cost vs PV/cost", "eig_per_cost_vs_predictive_variance_per_cost"),
        ("EIG/cost vs D-opt/cost", "eig_per_cost_vs_laplace_d_opt_per_cost"),
    )
    direct_contrasts = tuple(
        (
            label,
            contrasts[key]["wins"],
            contrasts[key]["ties"],
            contrasts[key]["losses"],
        )
        for label, key in contrast_specs
    )

    cost_specs = (
        ("EIG / cost", "eig_per_cost", "o"),
        ("PV / cost", "predictive_variance_per_cost", "x"),
        ("D-opt / cost", "laplace_d_opt_per_cost", "s"),
        ("Fixed traversal", "fixed_channel_balanced", "D"),
    )
    policy_costs = tuple(
        (
            label,
            endpoints[key]["modeled_cost"]["mean"],
            endpoints[key]["modeled_cost"]["minimum"],
            endpoints[key]["modeled_cost"]["maximum"],
            marker,
        )
        for label, key, marker in cost_specs
    )
    return evidence, policy_counts, direct_contrasts, policy_costs


def dot_range(ax, rows, xlabel):
    positions = np.arange(len(rows))[::-1]
    for position, (label, mean, low, high, marker) in zip(positions, rows):
        ax.errorbar(
            mean,
            position,
            xerr=[[mean - low], [high - mean]],
            fmt=marker,
            color="black",
            markerfacecolor="white",
            markersize=6,
            capsize=4,
            linewidth=1.2,
        )
    ax.set_yticks(positions, [row[0] for row in rows])
    ax.set_xlabel(xlabel)
    ax.grid(axis="x", color="0.85", linewidth=0.7)
    ax.spines[["top", "right"]].set_visible(False)


def main():
    evidence, policy_counts, direct_contrasts, policy_costs = load_rows()
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 8,
            "axes.titlesize": 8,
            "figure.dpi": 300,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )
    figure, axes = plt.subplots(1, 3, figsize=(7.25, 3.15), constrained_layout=True)

    dot_range(axes[0], policy_counts, "Measurements to gate")
    axes[0].set_xlim(4.2, 13.8)
    axes[0].set_title("(a) Count endpoint")

    labels = ["EIG vs PV", "EIG vs Laplace", "EIG/c vs PV/c", "EIG/c vs Laplace/c"]
    wins = np.asarray([row[1] for row in direct_contrasts])
    ties = np.asarray([row[2] for row in direct_contrasts])
    losses = np.asarray([row[3] for row in direct_contrasts])
    y = np.arange(len(labels))[::-1]
    axes[1].barh(y, wins, color="white", edgecolor="black", hatch="//", label="EIG win")
    axes[1].barh(
        y, ties, left=wins, color="0.82", edgecolor="black", hatch="..", label="Tie"
    )
    axes[1].barh(
        y,
        losses,
        left=wins + ties,
        color="0.45",
        edgecolor="black",
        hatch="xx",
        label="EIG loss",
    )
    axes[1].set_yticks(y, labels)
    axes[1].set_xlim(0, 30)
    axes[1].set_xlabel("Paired seeds")
    axes[1].set_title("(b) Direct contrasts")
    figure.legend(*axes[1].get_legend_handles_labels(),
        loc="outside lower center",
        ncol=3,
        frameon=False,
        fontsize=8,
        handlelength=1.8,
    )
    axes[1].spines[["top", "right"]].set_visible(False)

    dot_range(axes[2], policy_costs, "Modeled acquisition cost")
    axes[2].set_xlim(160, 305)
    axes[2].set_title("(c) Cost endpoint")
    axes[2].set_xlabel("Modeled cost (not lab time)")

    output = ASSET_ROOT / "acquisition-diagnostics.png"
    figure.savefig(
        output,
        bbox_inches="tight",
        facecolor="white",
        metadata={
            "Title": "Paired acquisition endpoints",
            "Description": f"Evidence projection SHA-256 {sha256(EVIDENCE_PATH)}",
        },
    )
    vector_output = output.with_suffix(".pdf")
    figure.savefig(vector_output, bbox_inches="tight", facecolor="white",
                   metadata={"CreationDate": None, "ModDate": None})
    plt.close(figure)
    manifest = {
        "schema_version": "magnetic-wiki-figure/1.0",
        "figure": output.name,
        "figure_sha256": sha256(output),
        "vector_figure": vector_output.name,
        "vector_figure_sha256": sha256(vector_output),
        "evidence_projection": str(EVIDENCE_PATH.relative_to(WIKI_ROOT)),
        "evidence_projection_sha256": sha256(EVIDENCE_PATH),
        "evidence_sources": ["E4", "E5"],
        "release_id": evidence["release"]["id"],
    }
    (ASSET_ROOT / "acquisition-diagnostics.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    render_workflow()


def render_workflow():
    """Draw the evidence branches separately from the sequential decision loop."""
    figure, axis = plt.subplots(figsize=(7.25, 4.0))
    axis.set(xlim=(0, 10), ylim=(0, 6))
    axis.axis("off")

    def box(x, y, width, height, text, shade="white"):
        axis.add_patch(FancyBboxPatch((x, y), width, height,
                       boxstyle="round,pad=0.025,rounding_size=0.09",
                       facecolor=shade, edgecolor="black", linewidth=0.9))
        axis.text(x + width / 2, y + height / 2, text,
                  ha="center", va="center", fontsize=8)

    def arrow(start, end, dashed=False):
        axis.annotate("", xy=end, xytext=start,
                      arrowprops={"arrowstyle": "-|>", "color": "black",
                                  "linewidth": 0.8,
                                  "linestyle": "--" if dashed else "-"})

    axis.text(0, 5.8, "(a) Separate evidence streams", weight="bold", fontsize=9)
    branches = [("Matched-model\nrecovery", "Six-parameter\nlocal diagnostics"),
                ("Paired policy\ncomparison", "Count and\nmodeled cost"),
                ("Controlled\nmodel mismatch", "False confidence\nand holdout error"),
                ("Measured-data\nadequacy", "In-sample\nresidual error")]
    for index, (name, result) in enumerate(branches):
        x = 0.03 + index * 2.52
        box(x, 4.65, 2.35, .8, name, "0.92")
        arrow((x + 1.175, 4.62), (x + 1.175, 4.23))
        axis.text(x + 1.175, 3.98, result, ha="center", va="center", fontsize=8)
    axis.text(0, 3.35, "(b) Shared-outcome acquisition loop", weight="bold", fontsize=9)
    labels = ["Shared two-point\ninitial data", "Posterior\nsampling", "Score unmeasured\ncandidates", "Reveal shared\nnoisy outcome", "Two-target\nprecision gate"]
    for index, label in enumerate(labels):
        x = .02 + index * 2.02
        box(x, 2.13, 1.82, .85, label)
        if index < 4:
            arrow((x + 1.84, 2.555), (x + 2.0, 2.555))
    axis.plot([9.0, 9.0, 2.95, 2.95], [2.10, 1.70, 1.70, 2.1],
              color="black", linestyle="--", linewidth=.8)
    arrow((2.95, 1.91), (2.95, 2.13), dashed=True)
    axis.text(5.95, 1.43, "If gate fails: append outcome and refit", ha="center", fontsize=8)
    axis.text(0, .99, "(c) Scientific scope", weight="bold", fontsize=9)
    box(.02, .02, 4.8, .72, "Local precision can be reached quickly;\nstrong comparators often match EIG.", "0.94")
    box(5.07, .02, 4.8, .72, "Narrow intervals do not establish accuracy\nunder mismatch or laboratory-time savings.")
    figure.tight_layout(pad=.6)
    output = ASSET_ROOT / "study-workflow.png"
    vector_output = output.with_suffix(".pdf")
    figure.savefig(output, dpi=300, facecolor="white")
    figure.savefig(vector_output, facecolor="white",
                   metadata={"CreationDate": None, "ModDate": None})
    plt.close(figure)


if __name__ == "__main__":
    main()
