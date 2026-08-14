#!/usr/bin/env python3
"""Generate and verify full-paper monochrome figures from frozen evidence.

Generation is a scientific pipeline operation and therefore requires a SLURM
allocation. Verification is read-only and intentionally login/CI safe.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Patch

from magcore_calib.runtime import require_slurm


SCHEMA_VERSION = "current-paper-figures/1.0"
PARAMETERS = ("k", "alpha", "beta", "mu_s", "f_rel_hz", "alpha_cc")
PARAMETER_LABELS = {
    "k": r"$k$", "alpha": r"$\alpha$", "beta": r"$\beta$",
    "mu_s": r"$\mu_s$", "f_rel_hz": r"$f_{\mathrm{rel}}$",
    "alpha_cc": r"$a_{\mathrm{cc}}$",
}
FIGURE_NAMES = (
    "study_workflow_full.pdf",
    "synthetic_diagnostics_full.pdf",
    "acquisition_diagnostics_full.pdf",
    "measured_adequacy_full.pdf",
)
FIXED_CREATION_TIME = datetime(2026, 8, 12, tzinfo=timezone.utc)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_name(path.name + ".partial")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _save(fig: plt.Figure, destination: Path, title: str, release_id: str) -> None:
    temporary = destination.with_name(destination.name + ".partial")
    fig.savefig(
        temporary,
        format="pdf",
        bbox_inches="tight",
        metadata={
            "Title": title,
            "Subject": f"Derived from frozen release {release_id}",
            "Creator": "generate_current_paper_figures.py",
            "CreationDate": FIXED_CREATION_TIME,
            "ModDate": FIXED_CREATION_TIME,
        },
    )
    plt.close(fig)
    os.replace(temporary, destination)


def _box(ax: plt.Axes, xy: tuple[float, float], width: float, height: float,
         text: str, *, facecolor: str = "white", hatch: str = "",
         linestyle: str = "-", fontsize: float = 7.4) -> None:
    box = FancyBboxPatch(
        xy, width, height, boxstyle="round,pad=0.015",
        facecolor=facecolor, edgecolor="black", linewidth=0.9,
        linestyle=linestyle, hatch=hatch,
    )
    ax.add_patch(box)
    ax.text(xy[0] + width / 2, xy[1] + height / 2, text,
            ha="center", va="center", fontsize=fontsize)


def _arrow(ax: plt.Axes, start: tuple[float, float], end: tuple[float, float],
           *, style: str = "-") -> None:
    ax.add_patch(FancyArrowPatch(
        start, end, arrowstyle="-|>", mutation_scale=9,
        linewidth=0.8, linestyle=style, color="black",
    ))


def render_workflow(summary: dict[str, Any], output_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(7.2, 4.55))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.text(0.01, 0.96, "(a) Evidence branches", weight="bold", fontsize=9)
    _box(ax, (0.02, 0.69), 0.18, 0.15, "Declared model, prior,\nnoise, and geometry")
    _box(ax, (0.29, 0.72), 0.18, 0.12, "Matched-model\nrecovery", facecolor="0.96")
    _box(ax, (0.52, 0.72), 0.18, 0.12, "Paired sequential\nacquisition", facecolor="0.90")
    _box(ax, (0.77, 0.72), 0.20, 0.12, "Measured-data\nmodel adequacy", facecolor="0.82")
    ax.plot((0.20, 0.245), (0.765, 0.765), color="black", linewidth=0.8)
    ax.plot((0.245, 0.245), (0.765, 0.89), color="black", linewidth=0.8)
    ax.plot((0.245, 0.87), (0.89, 0.89), color="black", linewidth=0.8)
    for center in (0.38, 0.61, 0.87):
        _arrow(ax, (center, 0.89), (center, 0.84))
    ax.text(0.01, 0.59, "(b) One-step acquisition loop", weight="bold", fontsize=9)
    labels = (
        "Shared two-point\ninitial state", "Posterior\nsamples",
        "Score every\nunrevealed design", "Reveal shared\ncandidate outcome",
        "Two-target\nprecision gate",
    )
    starts = (0.02, 0.215, 0.405, 0.61, 0.81)
    widths = (0.15, 0.14, 0.16, 0.16, 0.16)
    for x, width, label in zip(starts, widths, labels):
        _box(ax, (x, 0.36), width, 0.13, label)
    for index in range(len(labels) - 1):
        _arrow(ax, (starts[index] + widths[index], 0.425), (starts[index + 1], 0.425))
    ax.plot((0.89, 0.89, 0.285), (0.36, 0.29, 0.29), color="black",
            linewidth=0.75, linestyle="--")
    _arrow(ax, (0.285, 0.29), (0.285, 0.36), style="--")
    ax.text(0.58, 0.255, "if gate is not reached: append observation and refit",
            fontsize=6.8, ha="center")
    ax.text(0.01, 0.19, "(c) Claim boundary", weight="bold", fontsize=9)
    _box(ax, (0.02, 0.015), 0.44, 0.135, "", facecolor="0.92")
    ax.text(0.24, 0.112, "SUPPORTED BY FROZEN EVIDENCE",
            ha="center", va="center", fontsize=6.7, weight="bold")
    ax.text(0.24, 0.063, "model-conditional recovery and\nlocal precision efficiency",
            ha="center", va="center", fontsize=7.2)
    _box(ax, (0.54, 0.015), 0.43, 0.135, "", linestyle="--")
    ax.text(0.755, 0.112, "NOT ESTABLISHED",
            ha="center", va="center", fontsize=6.7, weight="bold")
    ax.text(0.755, 0.063, "real-material optimality, global accuracy,\nor laboratory-time savings",
            ha="center", va="center", fontsize=7.2)
    destination = output_dir / FIGURE_NAMES[0]
    _save(fig, destination, "Study design and interpretation boundary", summary["release_id"])
    return destination


def render_synthetic(summary: dict[str, Any], output_dir: Path) -> Path:
    fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.7), constrained_layout=True)
    eigenvalues = summary["fisher"]["eigenvalues"]
    axes[0].semilogy(
        range(1, 7), eigenvalues, color="black", linewidth=1.2,
        marker="o", markersize=4.8, markerfacecolor="white",
    )
    axes[0].set(xlabel="Ascending mode", ylabel="Fisher eigenvalue",
                title="(a) Local Fisher spectrum")
    axes[0].grid(True, which="both", color="0.85", linewidth=0.45, linestyle=":")

    for index, parameter in enumerate(PARAMETERS):
        errors = summary["recovery"][parameter]["errors_pct"]
        offsets = np.linspace(-0.12, 0.12, len(errors))
        axes[1].scatter(
            index + offsets, errors, s=20, facecolors="white",
            edgecolors="black", linewidths=0.65, zorder=3,
        )
        axes[1].plot(index, np.median(errors), marker="_", markersize=13,
                     color="black", markeredgewidth=1.4)
    axes[1].set_xticks(range(6), [PARAMETER_LABELS[key] for key in PARAMETERS])
    axes[1].set(ylabel="Absolute median error (%)",
                title="(b) Five matched-model seeds")
    axes[1].grid(True, axis="y", color="0.85", linewidth=0.45, linestyle=":")

    inclusions = [summary["recovery"][key]["interval_inclusion_count"] for key in PARAMETERS]
    axes[2].bar(
        range(6), inclusions, width=0.72, facecolor="white",
        edgecolor="black", hatch="///", linewidth=0.8,
    )
    axes[2].axhline(5, color="black", linewidth=0.8, linestyle="--")
    axes[2].set_xticks(range(6), [PARAMETER_LABELS[key] for key in PARAMETERS])
    axes[2].set(ylim=(0, 5.5), yticks=range(0, 6),
                ylabel="Truths inside 90% interval",
                title="(c) Descriptive inclusion count")
    axes[2].grid(True, axis="y", color="0.88", linewidth=0.4, linestyle=":")
    destination = output_dir / FIGURE_NAMES[1]
    _save(fig, destination, "Expanded synthetic diagnostics", summary["release_id"])
    return destination


def render_acquisition(summary: dict[str, Any], output_dir: Path) -> Path:
    eig = summary["eig"]
    seeds = np.asarray(eig["seeds"], dtype=int)
    raw = np.asarray(eig["raw_counts"], dtype=float)
    fixed = np.asarray(eig["fixed_counts"], dtype=float)
    cost = np.asarray(eig["per_cost_modeled_costs"], dtype=float)
    fixed_cost = np.asarray(eig["fixed_modeled_costs"], dtype=float)
    differences = fixed - raw
    fig, axes = plt.subplots(1, 3, figsize=(7.2, 3.05))
    fig.subplots_adjust(left=0.075, right=0.99, bottom=0.20, top=0.88, wspace=0.38)

    axes[0].plot(seeds, raw, color="black", linewidth=0.9, marker="o",
                 markersize=3.1, markerfacecolor="white", label="Raw EIG")
    axes[0].plot(seeds, fixed, color="0.35", linewidth=1.0, linestyle="--",
                 marker="x", markersize=3.4, label="Fixed traversal")
    axes[0].set(xlabel="Paired seed", ylabel="Measurements to gate",
                title="(a) Count endpoint")
    seed_ticks = (seeds[0], seeds[9], seeds[19], seeds[-1])
    axes[0].set_xticks(seed_ticks)
    axes[0].tick_params(axis="x", labelrotation=35)
    axes[0].set_ylim(min(raw) - 0.5, max(fixed) + 0.5)
    axes[0].legend(
        frameon=True, facecolor="white", edgecolor="0.7", framealpha=1.0,
        loc="center", fontsize=6.6,
    )
    axes[0].grid(True, axis="y", color="0.86", linewidth=0.4, linestyle=":")

    values, counts = np.unique(differences, return_counts=True)
    axes[1].bar(values, counts, width=0.45, facecolor="white", edgecolor="black",
                hatch="///", linewidth=0.8)
    for x, count in zip(values, counts):
        axes[1].text(x, count + 0.5, f"n={count}", ha="center", va="bottom", fontsize=7)
    axes[1].set(xlabel="Fixed minus raw-EIG count",
                ylabel="Number of paired seeds", title="(b) Paired count gain")
    axes[1].set_xticks(values)
    axes[1].set_ylim(0, max(counts) * 1.14)
    axes[1].grid(True, axis="y", color="0.86", linewidth=0.4, linestyle=":")

    order = np.arange(1, len(seeds) + 1)
    axes[2].plot(order, cost, color="black", linewidth=0.9, marker="o",
                 markersize=3.1, markerfacecolor="white", label="EIG / cost")
    axes[2].plot(order, fixed_cost, color="0.35", linewidth=1.0, linestyle="--",
                 marker="x", markersize=3.4, label="Fixed traversal")
    axes[2].set(xlabel="Paired run (ordered seed)", ylabel="Modeled acquisition cost",
                title="(c) Prespecified cost endpoint")
    axes[2].set_xticks((1, 10, 20, 30))
    axes[2].set_ylim(min(cost) - 10, max(fixed_cost) + 10)
    axes[2].legend(
        frameon=True, facecolor="white", edgecolor="0.7", framealpha=1.0,
        loc="center", fontsize=6.6,
    )
    axes[2].grid(True, axis="y", color="0.86", linewidth=0.4, linestyle=":")
    destination = output_dir / FIGURE_NAMES[2]
    _save(fig, destination, "Expanded paired acquisition diagnostics", summary["release_id"])
    return destination


def render_measured(summary: dict[str, Any], output_dir: Path) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.0))
    fig.subplots_adjust(left=0.08, right=0.99, bottom=0.17, top=0.88, wspace=0.30)
    materials = ("N49", "N87", "N95", "3C95")
    core_values = [summary["measured_pcv"][key]["rms_pct"] for key in materials]
    axes[0].bar(
        range(4), core_values, width=0.68, facecolor="white",
        edgecolor="black", hatch="///", linewidth=0.8,
    )
    axes[0].set_xticks(range(4), materials)
    axes[0].set(ylabel="In-sample RRMSE (%)", title="(a) Isothermal core-loss fits")
    axes[0].grid(True, axis="y", color="0.86", linewidth=0.4, linestyle=":")

    groups = ("N87", "N95")
    records = ("N87_LEA_MTB", "N95_LEA_MTB")
    mu_real = [summary["measured_permeability"][key]["mu_real_rms_pct"] for key in records]
    mu_imag = [summary["measured_permeability"][key]["mu_imag_rms_pct"] for key in records]
    x = np.arange(2)
    axes[1].bar(x - 0.18, mu_real, width=0.36, facecolor="white",
                edgecolor="black", linewidth=0.8, label=r"$\mu'$")
    axes[1].bar(x + 0.18, mu_imag, width=0.36, facecolor="0.72",
                edgecolor="black", linewidth=0.8, hatch="xx", label=r"$\mu''$")
    axes[1].set_xticks(x, groups)
    axes[1].set(ylabel="In-sample RRMSE (%)",
                title="(b) Accepted permeability fits")
    axes[1].legend(frameon=False)
    axes[1].grid(True, axis="y", color="0.86", linewidth=0.4, linestyle=":")
    destination = output_dir / FIGURE_NAMES[3]
    _save(fig, destination, "Expanded measured-data model adequacy", summary["release_id"])
    return destination


def generate(summary_path: Path, output_dir: Path) -> dict[str, Any]:
    require_slurm()
    summary_path = summary_path.resolve(strict=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("schema_version") != "paper-summary/3.0":
        raise ValueError("current paper requires paper-summary/3.0 evidence")
    plt.rcParams.update({
        "font.family": "serif", "font.size": 8, "axes.labelsize": 8,
        "axes.titlesize": 8.6, "legend.fontsize": 7, "xtick.labelsize": 7,
        "ytick.labelsize": 7, "pdf.fonttype": 42, "text.color": "black",
        "axes.labelcolor": "black", "axes.edgecolor": "black",
        "xtick.color": "black", "ytick.color": "black",
        "figure.facecolor": "white", "axes.facecolor": "white",
    })
    outputs = [
        render_workflow(summary, output_dir),
        render_synthetic(summary, output_dir),
        render_acquisition(summary, output_dir),
        render_measured(summary, output_dir),
    ]
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "release_id": summary["release_id"],
        "style": "grayscale only; distinctions use marker, line style, fill, and hatch",
        "input": {"path": summary_path.name, "sha256": sha256(summary_path)},
        "outputs": [
            {"path": path.name, "sha256": sha256(path), "bytes": path.stat().st_size}
            for path in outputs
        ],
    }
    _atomic_json(output_dir / "full_figure_manifest.json", manifest)
    return manifest


def verify(summary_path: Path, output_dir: Path) -> dict[str, Any]:
    summary_path = summary_path.resolve(strict=True)
    output_dir = output_dir.resolve(strict=True)
    manifest_path = output_dir / "full_figure_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("wrong full-paper figure manifest schema")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if manifest.get("release_id") != summary.get("release_id"):
        raise ValueError("figure/release mismatch")
    if manifest.get("input", {}).get("sha256") != sha256(summary_path):
        raise ValueError("figure input checksum mismatch")
    declared = manifest.get("outputs", [])
    if {item.get("path") for item in declared} != set(FIGURE_NAMES):
        raise ValueError("figure manifest has an incomplete output set")
    for item in declared:
        path = output_dir / item["path"]
        if not path.is_file() or path.stat().st_size != item.get("bytes") \
                or sha256(path) != item.get("sha256"):
            raise ValueError(f"figure checksum mismatch: {item['path']}")
    return {
        "release_id": manifest["release_id"],
        "verified_figure_count": len(declared),
        "style": manifest["style"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("generate", "verify"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--summary", required=True, type=Path)
        subparser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    result = (
        generate(args.summary, args.output_dir)
        if args.command == "generate"
        else verify(args.summary, args.output_dir)
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
