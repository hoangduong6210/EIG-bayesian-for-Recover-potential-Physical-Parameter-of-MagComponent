#!/usr/bin/env python3
"""Generate grayscale, wiki-native scientific summary figures."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np


POLICY_COUNTS = (
    ("Raw EIG", 5.0, 5.0, 5.0, "o"),
    ("Predictive variance", 5.0, 5.0, 5.0, "x"),
    ("Laplace D-optimal", 5.0, 5.0, 5.0, "s"),
    ("Random balanced", 7.8, 5.0, 13.0, "^"),
    ("Fixed traversal", 9.0, 9.0, 9.0, "D"),
)

DIRECT_CONTRASTS = (
    ("Raw EIG vs PV", 0, 30, 0),
    ("Raw EIG vs D-opt", 0, 30, 0),
    ("EIG/cost vs PV/cost", 0, 0, 30),
    ("EIG/cost vs D-opt/cost", 0, 30, 0),
)

POLICY_COSTS = (
    ("EIG / cost", 190.17, 190.0, 195.0, "o"),
    ("PV / cost", 175.0, 175.0, 175.0, "x"),
    ("D-opt / cost", 190.17, 190.0, 195.0, "s"),
    ("Fixed traversal", 290.0, 290.0, 290.0, "D"),
)


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
    plt.rcParams.update(
        {
            "font.family": "serif",
            "font.size": 9,
            "axes.titlesize": 10,
            "figure.dpi": 180,
        }
    )
    figure, axes = plt.subplots(1, 3, figsize=(12.0, 3.6), constrained_layout=True)

    dot_range(axes[0], POLICY_COUNTS, "Measurements to gate")
    axes[0].set_xlim(4.2, 13.8)
    axes[0].set_title("(a) Count endpoint")

    labels = [row[0] for row in DIRECT_CONTRASTS]
    wins = np.asarray([row[1] for row in DIRECT_CONTRASTS])
    ties = np.asarray([row[2] for row in DIRECT_CONTRASTS])
    losses = np.asarray([row[3] for row in DIRECT_CONTRASTS])
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
    axes[1].set_title("(b) Direct contrasts", pad=38)
    axes[1].legend(
        loc="lower center",
        bbox_to_anchor=(0.5, 1.01),
        ncol=3,
        frameon=False,
        fontsize=8,
        handlelength=1.8,
    )
    axes[1].spines[["top", "right"]].set_visible(False)

    dot_range(axes[2], POLICY_COSTS, "Modeled acquisition cost")
    axes[2].set_xlim(160, 305)
    axes[2].set_title("(c) Cost endpoint")
    axes[2].text(
        0.98,
        0.97,
        "Prespecified model; not lab time",
        transform=axes[2].transAxes,
        ha="right",
        va="top",
        fontsize=7.5,
    )

    output = __file__.replace("generate_figures.py", "acquisition-diagnostics.png")
    figure.savefig(output, bbox_inches="tight", facecolor="white")
    plt.close(figure)


if __name__ == "__main__":
    main()
