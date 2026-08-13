#!/usr/bin/env python3
"""Generate publication tables and figures from one completed SLURM run."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from statistics import mean, stdev
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

from magcore_calib.results import validate_result
from magcore_calib.runtime import require_slurm
from magcore_calib.study_plan import load_study_plan


PARAMETER_LABELS = {
    "k": r"$k$",
    "alpha": r"$\alpha$",
    "beta": r"$\beta$",
    "mu_s": r"$\mu_s$",
    "f_rel_hz": r"$f_{\mathrm{rel}}$",
    "alpha_cc": r"$a_{\mathrm{cc}}$",
}
PARAMETER_ORDER = tuple(PARAMETER_LABELS)
PCV_ORDER = ("N49", "N87", "N95", "3C95")
MU_ORDER = ("N87_LEA_MTB", "N95_LEA_MTB")
PAIRED_GROUP_STYLES = (
    {
        "color": "0.35", "linestyle": "-", "marker": "o",
        "markerfacecolor": "white", "markeredgecolor": "0.15",
    },
    {
        "color": "0.10", "linestyle": "--", "marker": "x",
        "markeredgecolor": "0.10",
    },
)
CHANNEL_BAR_STYLES = {
    "core loss": {"facecolor": "0.82", "hatch": ""},
    r"$\mu'$": {"facecolor": "white", "hatch": "///"},
    r"$\mu''$": {"facecolor": "0.45", "hatch": "xx"},
}


def paired_descriptive(values: list[float], *, seed: int) -> dict[str, float]:
    """Deterministic descriptive summary for a small paired-seed endpoint."""
    if not values:
        raise ValueError("paired endpoint requires at least one finite value")
    array = np.asarray(values, dtype=float)
    if not np.all(np.isfinite(array)):
        raise ValueError("paired endpoint contains a nonfinite value")
    rng = np.random.default_rng(seed)
    bootstrap_indices = rng.integers(0, array.size, size=(10_000, array.size))
    bootstrap_means = array[bootstrap_indices].mean(axis=1)
    return {
        "mean": float(array.mean()),
        "median": float(np.median(array)),
        "sample_sd": float(array.std(ddof=1)) if array.size > 1 else 0.0,
        "bootstrap_mean_ci95_low": float(np.quantile(bootstrap_means, 0.025)),
        "bootstrap_mean_ci95_high": float(np.quantile(bootstrap_means, 0.975)),
    }


def group_paired_outcomes(
    seeds: list[int], eig_counts: list[int], uniform_counts: list[int],
) -> list[tuple[int, int, tuple[int, ...]]]:
    """Group coincident paired outcomes without visually hiding repetitions."""
    if not (len(seeds) == len(eig_counts) == len(uniform_counts)):
        raise ValueError("seeds and paired count vectors must have equal lengths")
    grouped: dict[tuple[int, int], list[int]] = {}
    for seed, eig_count, uniform_count in zip(seeds, eig_counts, uniform_counts):
        grouped.setdefault((eig_count, uniform_count), []).append(seed)
    return [
        (eig_count, uniform_count, tuple(group_seeds))
        for (eig_count, uniform_count), group_seeds in grouped.items()
    ]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_record(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    validate_result(payload)
    return payload


def summarize(run_dir: Path) -> tuple[dict[str, Any], list[Path]]:
    inputs: list[Path] = []
    plan = load_study_plan(run_dir)
    posterior_records = []
    eig_records = []
    for seed in plan.recovery_seeds:
        posterior_path = run_dir / "results" / "posterior" / f"seed{seed}" / f"posterior_seed{seed}.json"
        posterior_records.append(load_record(posterior_path))
        inputs.append(posterior_path)
    for seed in plan.acquisition_seeds:
        eig_path = run_dir / "results" / "eig" / f"seed{seed}" / f"eig_seed{seed}.json"
        eig_records.append(load_record(eig_path))
        inputs.append(eig_path)

    validation_path = run_dir / "summary" / "eig_convergence" / "final_decision.json"
    estimator_validation_decision = json.loads(
        validation_path.read_text(encoding="utf-8")
    )
    if estimator_validation_decision.get("schema_version") \
            != "eig-convergence-final/1.0" \
            or estimator_validation_decision.get("valid") is not True:
        raise ValueError("estimator-validation final decision is missing or invalid")
    inputs.append(validation_path)

    fisher_path = run_dir / "results" / "identifiability" / "0" / "identifiability.json"
    fisher_record = load_record(fisher_path)
    inputs.append(fisher_path)
    fisher = fisher_record["design"]["fisher_spectrum"]

    recovery: dict[str, Any] = {}
    total_inclusion = 0
    for parameter in PARAMETER_ORDER:
        errors = [record["posterior"][parameter]["absolute_error_pct"] for record in posterior_records]
        inclusions = [bool(record["posterior"][parameter]["truth_in_ci90"]) for record in posterior_records]
        total_inclusion += sum(inclusions)
        recovery[parameter] = {
            "errors_pct": errors,
            "mean_pct": mean(errors),
            "sample_sd_pct": stdev(errors),
            "median_pct": float(np.median(errors)),
            "interval_inclusion_count": sum(inclusions),
        }

    def policies(record: dict[str, Any]) -> tuple[dict, dict, dict]:
        design = record["design"]
        if design.get("benchmark_version") in (2, 3):
            available = design["policies"]
            return (
                available["eig_raw"], available["eig_per_cost"],
                available["fixed_channel_balanced"],
            )
        previous = design["eig"]
        return previous, previous, design["uniform"]

    policy_triplets = [policies(record) for record in eig_records]
    raw_counts = [raw["n_measurements_to_gate"] for raw, _, _ in policy_triplets]
    per_cost_counts = [policy["n_measurements_to_gate"] for _, policy, _ in policy_triplets]
    fixed_counts = [fixed["n_measurements_to_gate"] for _, _, fixed in policy_triplets]
    def modeled_cost(policy: dict) -> float | None:
        direct = policy.get("modeled_cost_to_gate")
        if direct is not None:
            return direct
        if not policy.get("reached") or not policy.get("trajectory"):
            return None
        final = policy["trajectory"][-1]
        return final.get("modeled_cost_units", final.get("cost_s"))

    per_cost_costs = [modeled_cost(policy) for _, policy, _ in policy_triplets]
    fixed_costs = [modeled_cost(fixed) for _, _, fixed in policy_triplets]
    raw_success = [raw is not None and fixed is not None for raw, fixed in zip(raw_counts, fixed_counts)]
    cost_success = [cost is not None and fixed is not None for cost, fixed in zip(per_cost_costs, fixed_costs)]
    raw_eig_failures = sum(value is None for value in raw_counts)
    per_cost_eig_failures = sum(value is None for value in per_cost_costs)
    fixed_failures = sum(value is None for value in fixed_counts)
    raw_reductions = [
        100.0 * (fixed - raw) / fixed
        for raw, fixed, success in zip(raw_counts, fixed_counts, raw_success) if success
    ]
    cost_reductions = [
        100.0 * (fixed - cost) / fixed
        for cost, fixed, success in zip(per_cost_costs, fixed_costs, cost_success) if success
    ]
    if not raw_reductions or not cost_reductions:
        raise ValueError("each primary endpoint requires at least one paired gate success")
    raw_differences = [
        fixed - raw
        for raw, fixed, success in zip(raw_counts, fixed_counts, raw_success)
        if success
    ]
    cost_differences = [
        fixed - cost
        for cost, fixed, success in zip(per_cost_costs, fixed_costs, cost_success)
        if success
    ]

    pcv: dict[str, Any] = {}
    for material in PCV_ORDER:
        path = run_dir / "results" / "measured_pcv" / material / f"measured_pcv_{material}.json"
        record = load_record(path)
        inputs.append(path)
        if record["validity"].get("convergence_valid") is not True:
            raise ValueError(f"measured core-loss result failed convergence: {material}")
        pcv[material] = {
            "rms_pct": record["predictive"]["pcv_relative_rms_pct"],
            "alpha": record["posterior"]["alpha"]["median"],
            "beta": record["posterior"]["beta"]["median"],
            "n": record["data"].get("n_observations"),
        }

    permeability: dict[str, Any] = {}
    for source_key in MU_ORDER:
        path = run_dir / "results" / "measured_mu" / source_key / f"measured_mu_{source_key}.json"
        record = load_record(path)
        inputs.append(path)
        if record["validity"].get("convergence_valid") is not True or record["validity"].get("alpha_cc_boundary_flag"):
            raise ValueError(f"measured permeability result failed publication gate: {source_key}")
        permeability[source_key] = {
            "mu_real_rms_pct": record["predictive"]["mu_real_rms_pct"],
            "mu_imag_rms_pct": record["predictive"]["mu_imag_rms_pct"],
            "n": record["data"].get("n_observations"),
        }

    return {
        "schema_version": "paper-summary/3.0",
        "release_id": run_dir.name,
        "fisher": {
            "eigenvalues": fisher["eigenvalues_ascending"],
            "condition_number": fisher["condition_number_resolved_subspace"],
            "rank": len(fisher["eigenvalues_ascending"]),
        },
        "recovery": recovery,
        "recovery_interval_inclusion_total": total_inclusion,
        "eig": {
            "seeds": list(plan.acquisition_seeds),
            "seed_count": len(plan.acquisition_seeds),
            "recovery_seeds": list(plan.recovery_seeds),
            "estimator_validation_decision": estimator_validation_decision,
            "raw_counts": raw_counts,
            "per_cost_counts": per_cost_counts,
            "fixed_counts": fixed_counts,
            "raw_mean_count": mean(value for value in raw_counts if value is not None),
            "raw_count_reduction_pct": raw_reductions,
            "raw_mean_count_reduction_pct": mean(raw_reductions),
            "raw_paired_difference": paired_descriptive(raw_differences, seed=20260811),
            "raw_paired_reduction_pct": paired_descriptive(raw_reductions, seed=20260812),
            "raw_count_wins": sum(
                raw < fixed for raw, fixed in zip(raw_counts, fixed_counts)
                if raw is not None and fixed is not None
            ),
            "raw_eig_failure_count": raw_eig_failures,
            "fixed_failure_count": fixed_failures,
            "raw_complete_pair_count": sum(raw_success),
            "raw_failure_count": raw_success.count(False),
            "raw_paired_win_rate": sum(
                raw < fixed for raw, fixed in zip(raw_counts, fixed_counts)
                if raw is not None and fixed is not None
            ) / sum(raw_success),
            "per_cost_modeled_costs": per_cost_costs,
            "fixed_modeled_costs": fixed_costs,
            "per_cost_reduction_pct": cost_reductions,
            "per_cost_mean_reduction_pct": mean(cost_reductions),
            "per_cost_paired_difference": paired_descriptive(cost_differences, seed=20260813),
            "per_cost_paired_reduction_pct": paired_descriptive(cost_reductions, seed=20260814),
            "per_cost_eig_failure_count": per_cost_eig_failures,
            "cost_complete_pair_count": sum(cost_success),
            "per_cost_failure_count": cost_success.count(False),
            "per_cost_paired_win_rate": sum(
                cost < fixed for cost, fixed in zip(per_cost_costs, fixed_costs)
                if cost is not None and fixed is not None
            ) / sum(cost_success),
            # Compatibility aliases used by the current table/figure writer.
            "counts": raw_counts,
            "uniform_counts": fixed_counts,
            "mean_reduction_pct": mean(raw_reductions),
        },
        "measured_pcv": pcv,
        "measured_permeability": permeability,
        "excluded_measured_permeability": ["N87_MagNet", "3C95_MagNet"],
    }, inputs


def atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def write_table_artifacts(
    summary: dict[str, Any], macros_destination: Path, table_destination: Path
) -> None:
    release_id = summary["release_id"]
    escaped_release_id = release_id.replace("_", "\\_")
    short_id = release_id.split("_")[0]
    fisher = summary["fisher"]
    eig = summary["eig"]
    recovery_medians = [summary["recovery"][name]["median_pct"] for name in PARAMETER_ORDER]
    pcv = summary["measured_pcv"]
    permeability = summary["measured_permeability"]
    successful_counts = [value for value in eig["counts"] if value is not None]
    successful_fixed_counts = [value for value in eig["uniform_counts"] if value is not None]
    paired_difference = eig["raw_paired_difference"]
    selected_setting = eig["estimator_validation_decision"]["selected_setting"]
    macro_lines = [
        f"% Generated from immutable release candidate {release_id}; do not edit.",
        f"\\newcommand{{\\ReleaseID}}{{\\texttt{{{escaped_release_id}}}}}",
        f"\\newcommand{{\\ReleaseShort}}{{{short_id}}}",
        f"\\newcommand{{\\FisherCondition}}{{{fisher['condition_number']:.2e}}}",
        f"\\newcommand{{\\FisherMin}}{{{min(fisher['eigenvalues']):.2e}}}",
        f"\\newcommand{{\\FisherMax}}{{{max(fisher['eigenvalues']):.2e}}}",
        f"\\newcommand{{\\RecoveryInclusion}}{{{summary['recovery_interval_inclusion_total']}/30}}",
        f"\\newcommand{{\\RecoveryMedianMin}}{{{min(recovery_medians):.2f}}}",
        f"\\newcommand{{\\RecoveryMedianMax}}{{{max(recovery_medians):.2f}}}",
        f"\\newcommand{{\\EIGRange}}{{{min(successful_counts)}--{max(successful_counts)}}}",
        f"\\newcommand{{\\UniformRange}}{{{min(successful_fixed_counts)}--{max(successful_fixed_counts)}}}",
        f"\\newcommand{{\\EIGReduction}}{{{eig['mean_reduction_pct']:.1f}}}",
        f"\\newcommand{{\\EIGSeedCount}}{{{eig['seed_count']}}}",
        f"\\newcommand{{\\EIGCountMeanDifference}}{{{paired_difference['mean']:.2f}}}",
        f"\\newcommand{{\\EIGCountMedianDifference}}{{{paired_difference['median']:.2f}}}",
        f"\\newcommand{{\\EIGCountDifferenceSD}}{{{paired_difference['sample_sd']:.2f}}}",
        f"\\newcommand{{\\EIGCountDifferenceCILow}}{{{paired_difference['bootstrap_mean_ci95_low']:.2f}}}",
        f"\\newcommand{{\\EIGCountDifferenceCIHigh}}{{{paired_difference['bootstrap_mean_ci95_high']:.2f}}}",
        f"\\newcommand{{\\EIGCountWinRate}}{{{100.0 * eig['raw_paired_win_rate']:.1f}}}",
        f"\\newcommand{{\\EIGRawFailureRate}}{{{100.0 * eig['raw_eig_failure_count'] / eig['seed_count']:.1f}}}",
        f"\\newcommand{{\\EIGOuter}}{{{selected_setting['n_outer']}}}",
        f"\\newcommand{{\\EIGInner}}{{{selected_setting['n_inner']}}}",
        f"\\newcommand{{\\EIGReplicates}}{{{selected_setting['n_replicates']}}}",
        f"\\newcommand{{\\EIGCostReduction}}{{{eig.get('per_cost_mean_reduction_pct', 0.0):.1f}}}",
        f"\\newcommand{{\\EIGCountFailures}}{{{eig.get('raw_failure_count', 0)}}}",
        f"\\newcommand{{\\EIGCostFailures}}{{{eig.get('per_cost_failure_count', 0)}}}",
        f"\\newcommand{{\\NFortyNinePcvRms}}{{{pcv['N49']['rms_pct']:.2f}}}",
        f"\\newcommand{{\\NEightySevenPcvRms}}{{{pcv['N87']['rms_pct']:.2f}}}",
        f"\\newcommand{{\\NNinetyFivePcvRms}}{{{pcv['N95']['rms_pct']:.2f}}}",
        f"\\newcommand{{\\ThreeCNinetyFivePcvRms}}{{{pcv['3C95']['rms_pct']:.2f}}}",
        f"\\newcommand{{\\NEightySevenMuRealRms}}{{{permeability['N87_LEA_MTB']['mu_real_rms_pct']:.2f}}}",
        f"\\newcommand{{\\NEightySevenMuImagRms}}{{{permeability['N87_LEA_MTB']['mu_imag_rms_pct']:.2f}}}",
        f"\\newcommand{{\\NNinetyFiveMuRealRms}}{{{permeability['N95_LEA_MTB']['mu_real_rms_pct']:.2f}}}",
        f"\\newcommand{{\\NNinetyFiveMuImagRms}}{{{permeability['N95_LEA_MTB']['mu_imag_rms_pct']:.2f}}}",
        "",
    ]
    table_lines = [
        f"% Generated from immutable release candidate {release_id}; do not edit.",
        "\\begin{table}[t]",
        "\\caption{Matched-model recovery and inclusion of the generating value in equal-tailed 90\\% posterior credible intervals (five synthetic seeds).}",
        "\\label{tab:recovery}",
        "\\centering\\small",
        "\\begin{tabular}{lrr}",
        "\\toprule Parameter & Median error (\\%) & Truth included \\\\",
        "\\midrule",
    ]
    for parameter in PARAMETER_ORDER:
        record = summary["recovery"][parameter]
        table_lines.append(
            f"{PARAMETER_LABELS[parameter]} & {record['median_pct']:.2f} & "
            f"{record['interval_inclusion_count']}/5 \\\\" 
        )
    table_lines.extend(("\\bottomrule", "\\end{tabular}", "\\end{table}", ""))
    atomic_text(macros_destination, "\n".join(macro_lines))
    atomic_text(table_destination, "\n".join(table_lines))


def save_figure(fig: plt.Figure, destination: Path, title: str, release_id: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".partial")
    fig.savefig(
        temporary,
        format="pdf",
        bbox_inches="tight",
        metadata={"Title": title, "Subject": f"Immutable release candidate {release_id}"},
    )
    plt.close(fig)
    os.replace(temporary, destination)


def render_figures(summary: dict[str, Any], output_dir: Path) -> list[Path]:
    plt.rcParams.update({
        "font.family": "serif", "font.size": 8, "axes.labelsize": 8,
        "axes.titlesize": 9, "legend.fontsize": 7, "xtick.labelsize": 7,
        "ytick.labelsize": 7, "pdf.fonttype": 42, "text.color": "black",
        "axes.labelcolor": "black", "axes.edgecolor": "black",
        "xtick.color": "black", "ytick.color": "black",
    })
    release_id = summary["release_id"]

    fig, axes = plt.subplots(1, 2, figsize=(7.05, 2.45), constrained_layout=True)
    eigenvalues = summary["fisher"]["eigenvalues"]
    axes[0].semilogy(
        range(1, 7), eigenvalues, color="0.10", linestyle="-", linewidth=1.3,
        marker="o", markersize=4.8, markerfacecolor="white",
        markeredgecolor="0.10", markeredgewidth=0.9,
    )
    axes[0].set(xlabel="Ascending mode", ylabel="Fisher eigenvalue", title="(a) Local Fisher spectrum")
    axes[0].grid(True, which="major", color="0.82", linewidth=0.55)
    axes[0].grid(True, which="minor", color="0.90", linewidth=0.35, linestyle=":")
    for index, parameter in enumerate(PARAMETER_ORDER):
        errors = summary["recovery"][parameter]["errors_pct"]
        offsets = np.linspace(-0.10, 0.10, len(errors))
        axes[1].scatter(
            index + offsets, errors, s=20, marker="o", facecolors="white",
            edgecolors="0.30", linewidths=0.75, zorder=3,
        )
        axes[1].plot(index, np.median(errors), marker="_", markersize=13, color="black", markeredgewidth=1.5)
    axes[1].set_xticks(range(len(PARAMETER_ORDER)), [PARAMETER_LABELS[p] for p in PARAMETER_ORDER])
    axes[1].set(ylabel="Absolute median error (%)", title="(b) Matched-model recovery")
    axes[1].set_axisbelow(True)
    axes[1].grid(True, axis="y", color="0.88", linewidth=0.45)
    synthetic_path = output_dir / "synthetic_results.pdf"
    save_figure(fig, synthetic_path, "Synthetic identifiability and recovery", release_id)

    fig, axes = plt.subplots(1, 2, figsize=(7.05, 2.55), constrained_layout=True)
    seeds = summary["eig"]["seeds"]
    eig_counts = summary["eig"]["counts"]
    uniform_counts = summary["eig"]["uniform_counts"]
    successful = [
        (seed, eig_count, fixed_count)
        for seed, eig_count, fixed_count in zip(seeds, eig_counts, uniform_counts)
        if eig_count is not None and fixed_count is not None
    ]
    for group_index, (eig_count, uniform_count, group_seeds) in enumerate(
        group_paired_outcomes(
            [row[0] for row in successful], [row[1] for row in successful],
            [row[2] for row in successful],
        )
    ):
        style = PAIRED_GROUP_STYLES[group_index % len(PAIRED_GROUP_STYLES)]
        axes[0].plot(
            (0, 1), (eig_count, uniform_count), linewidth=1.1, markersize=5.5,
            markeredgewidth=1.0, zorder=3 + group_index, **style,
        )
        axes[0].annotate(
            f"n={len(group_seeds)}", (0, eig_count), xytext=(8, 0),
            textcoords="offset points", ha="left", va="center", fontsize=6,
            bbox={
                "boxstyle": "round,pad=0.15", "facecolor": "white",
                "edgecolor": "0.70", "linewidth": 0.35, "alpha": 0.95,
            },
        )
    axes[0].set_xticks((0, 1), ("Raw EIG", "Fixed traversal"))
    axes[0].set(ylabel="Measurements to precision gate", title="(a) Paired synthetic acquisition")
    axes[0].set_axisbelow(True)
    axes[0].grid(True, axis="y", color="0.88", linewidth=0.45)

    labels = list(PCV_ORDER) + ["N87 $\\mu'$", "N87 $\\mu''$", "N95 $\\mu'$", "N95 $\\mu''$"]
    values = [summary["measured_pcv"][material]["rms_pct"] for material in PCV_ORDER]
    for key in MU_ORDER:
        values.extend((
            summary["measured_permeability"][key]["mu_real_rms_pct"],
            summary["measured_permeability"][key]["mu_imag_rms_pct"],
        ))
    channel_names = ["core loss"] * 4 + [r"$\mu'$", r"$\mu''$"] * 2
    for index, (value, channel_name) in enumerate(zip(values, channel_names)):
        axes[1].bar(
            index, value, width=0.8, edgecolor="0.10", linewidth=0.65,
            **CHANNEL_BAR_STYLES[channel_name],
        )
    axes[1].set_xticks(range(len(values)), labels, rotation=36, ha="right")
    axes[1].set(ylabel="In-sample relative RMS error (%)", title="(b) Measured model adequacy")
    axes[1].set_axisbelow(True)
    axes[1].grid(True, axis="y", color="0.88", linewidth=0.45)
    axes[1].legend(
        handles=[
            Patch(edgecolor="0.10", linewidth=0.65, label=name, **style)
            for name, style in CHANNEL_BAR_STYLES.items()
        ],
        loc="upper left", frameon=False,
    )
    acquisition_path = output_dir / "acquisition_measured_results.pdf"
    save_figure(fig, acquisition_path, "Synthetic acquisition and measured model error", release_id)
    return [synthetic_path, acquisition_path]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, type=Path)
    args = parser.parse_args()
    require_slurm()
    run_dir = args.run_dir.resolve(strict=True)
    summary, input_paths = summarize(run_dir)
    summary_path = run_dir / "summary" / "paper_summary.json"
    atomic_text(summary_path, json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n")
    macros_path = run_dir / "summary" / "frozen_result_macros.tex"
    table_path = run_dir / "summary" / "frozen_results.tex"
    write_table_artifacts(summary, macros_path, table_path)
    figure_paths = render_figures(summary, run_dir / "figures")
    outputs = [summary_path, macros_path, table_path, *figure_paths]
    manifest = {
        "schema_version": "paper-artifacts/2.0",
        "freeze_id": run_dir.name,
        "aggregation": {
            "mean": "arithmetic mean",
            "sample_sd": "sample standard deviation with denominator n-1",
            "paired_reduction_pct": "100 * (uniform_count - eig_count) / uniform_count",
            "measured_error": "direct in-sample relative RMS from convergence-valid records",
        },
        "inputs": [
            {"path": path.relative_to(run_dir).as_posix(), "sha256": sha256(path)}
            for path in sorted(input_paths)
        ],
        "outputs": [
            {"path": path.relative_to(run_dir).as_posix(), "sha256": sha256(path)}
            for path in outputs
        ],
    }
    atomic_text(
        run_dir / "summary" / "paper_artifacts_manifest.json",
        json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
    )


if __name__ == "__main__":
    main()
