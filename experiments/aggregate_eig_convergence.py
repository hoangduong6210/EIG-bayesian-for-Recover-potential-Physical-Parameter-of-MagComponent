#!/usr/bin/env python3
"""Aggregate estimator-validation scores and make the prespecified selection."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

from magcore_calib.results import provenance
from magcore_calib.runtime import require_slurm
from magcore_calib.study_plan import load_study_plan

SCORE_SCHEMA = "eig-convergence-score/1.0"
SCHEMA = "eig-convergence-selection/1.0"
TOP1_BOOTSTRAP_RESAMPLES = 4096
TOP1_BOOTSTRAP_CHUNK_SIZE = 512


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp-write")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _setting(record: dict) -> tuple[int, int, int]:
    estimator = record["estimator"]
    return (
        int(estimator["n_outer"]), int(estimator["n_inner"]),
        int(estimator["n_replicates"]),
    )


def _state(record: dict) -> tuple[int, int]:
    return int(record["state"]["seed"]), int(record["state"]["n_observations"])


def _load_scores(run_dir: Path) -> tuple[dict[tuple[str, tuple[int, int], tuple[int, int, int]], dict], list[dict]]:
    indexed: dict[tuple[str, tuple[int, int], tuple[int, int, int]], dict] = {}
    inputs: list[dict] = []
    for path in sorted(run_dir.rglob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if record.get("schema_version") != SCORE_SCHEMA:
            continue
        if record.get("validity", {}).get("valid") is not True:
            raise ValueError(f"invalid estimator-validation score record: {path}")
        key = (record["estimator"]["namespace"], _state(record), _setting(record))
        if key in indexed:
            raise ValueError(f"duplicate estimator-validation score cell {key}")
        indexed[key] = record
        inputs.append({"path": str(path), "sha256": _sha256(path)})
    if not indexed:
        raise ValueError("no estimator-validation score records found")
    return indexed, inputs


def _score_vectors(record: dict, objective: str, prefix: int) -> tuple[list[str], np.ndarray]:
    rows = sorted(record["candidate_scores"], key=lambda row: row["design_key"])
    keys = [row["design_key"] for row in rows]
    values = np.array([row["replicate_scores_nats"][:prefix] for row in rows], dtype=float)
    if values.shape != (len(rows), prefix) or not np.all(np.isfinite(values)):
        raise ValueError("score record cannot supply the requested replicate prefix")
    if objective == "per_cost":
        costs = np.array([float(row["channel_cost_units"]) for row in rows])
        values = values / costs[:, None]
    return keys, values


def _bootstrap_seed(candidate: dict, reference: dict, objective: str, prefix: int) -> int:
    """Derive a stable stream without making the result depend on file ordering."""
    payload = {
        "method": "paired-replicate-mean-top1-bootstrap/1.0",
        "state": candidate["state"],
        "candidate_estimator": candidate["estimator"],
        "reference_estimator": reference["estimator"],
        "objective": objective,
        "replicate_prefix": prefix,
        "resamples": TOP1_BOOTSTRAP_RESAMPLES,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return int.from_bytes(hashlib.sha256(encoded).digest()[:8], "big", signed=False)


def _paired_bootstrap_top1_diagnostics(
    values: np.ndarray,
    reference_values: np.ndarray,
    *,
    seed: int,
    n_resamples: int = TOP1_BOOTSTRAP_RESAMPLES,
) -> dict[str, float]:
    """Estimate stability and agreement of two replicate-mean selectors.

    Candidate and reference replicate ``j`` share the same EIG random-number
    stream, so their common prefix is resampled with the same indices.  When the
    reference has additional replicates, those are resampled separately and
    retained in its bootstrap mean.  Thus the comparison preserves both the
    paired common-random-number design and each estimator's actual replicate
    budget; it does not conflate mean-estimator stability with agreement of
    noisy, single-replicate winners.
    """
    values = np.asarray(values, dtype=float)
    reference_values = np.asarray(reference_values, dtype=float)
    if values.ndim != 2 or reference_values.ndim != 2:
        raise ValueError("bootstrap score arrays must be two-dimensional")
    if values.shape[0] != reference_values.shape[0] or values.shape[0] == 0:
        raise ValueError("bootstrap score arrays must have the same nonzero candidate count")
    candidate_count = values.shape[1]
    reference_count = reference_values.shape[1]
    if candidate_count < 1 or reference_count < candidate_count:
        raise ValueError("reference must contain the complete candidate replicate prefix")
    if not np.all(np.isfinite(values)) or not np.all(np.isfinite(reference_values)):
        raise ValueError("bootstrap scores must be finite")
    if isinstance(n_resamples, bool) or not isinstance(n_resamples, int) or n_resamples < 1:
        raise ValueError("n_resamples must be a positive integer")

    rng = np.random.default_rng(seed)
    candidate_winner = int(np.argmax(np.mean(values, axis=1)))
    reference_winner = int(np.argmax(np.mean(reference_values, axis=1)))
    agreements = 0
    candidate_winner_matches = 0
    reference_winner_matches = 0
    completed = 0
    while completed < n_resamples:
        batch = min(TOP1_BOOTSTRAP_CHUNK_SIZE, n_resamples - completed)
        paired_indices = rng.integers(0, candidate_count, size=(batch, candidate_count))
        candidate_means = np.mean(values[:, paired_indices], axis=2)
        reference_sums = np.sum(reference_values[:, paired_indices], axis=2)
        extra_count = reference_count - candidate_count
        if extra_count:
            extra_indices = rng.integers(
                candidate_count, reference_count, size=(batch, extra_count),
            )
            reference_sums += np.sum(reference_values[:, extra_indices], axis=2)
        reference_means = reference_sums / reference_count
        # Rows are already sorted by stable design key, giving deterministic
        # tie-breaking without introducing candidate-list order dependence.
        candidate_top = np.argmax(candidate_means, axis=0)
        reference_top = np.argmax(reference_means, axis=0)
        agreements += int(np.count_nonzero(candidate_top == reference_top))
        candidate_winner_matches += int(np.count_nonzero(candidate_top == candidate_winner))
        reference_winner_matches += int(np.count_nonzero(reference_top == reference_winner))
        completed += batch
    return {
        "agreement_probability": agreements / n_resamples,
        "candidate_winner_probability": candidate_winner_matches / n_resamples,
        "reference_winner_probability": reference_winner_matches / n_resamples,
    }


def _comparison(candidate: dict, reference: dict, objective: str, prefix: int) -> dict:
    candidate_estimator = candidate["estimator"]
    reference_estimator = reference["estimator"]
    if (
        candidate_estimator.get("prefix_nested_common_random_numbers") is not True
        or reference_estimator.get("prefix_nested_common_random_numbers") is not True
        or candidate_estimator.get("seed") != reference_estimator.get("seed")
    ):
        raise ValueError(
            "paired estimator comparison requires matching prefix-nested RNG streams"
        )
    keys, values = _score_vectors(candidate, objective, prefix)
    reference_keys, reference_values = _score_vectors(
        reference, objective, int(reference["estimator"]["n_replicates"]),
    )
    if keys != reference_keys:
        raise ValueError("candidate library differs between a grid state and its reference")
    candidate_means = np.mean(values, axis=1)
    reference_means = np.mean(reference_values, axis=1)
    correlation = float(spearmanr(candidate_means, reference_means).statistic)
    if not math.isfinite(correlation):
        correlation = 1.0 if np.allclose(candidate_means, reference_means) else 0.0

    candidate_sd = np.std(values, axis=1, ddof=1) if prefix > 1 else np.zeros(len(keys))
    reference_count = reference_values.shape[1]
    reference_sd = np.std(reference_values, axis=1, ddof=1)
    candidate_low = candidate_means - 1.96 * candidate_sd / math.sqrt(prefix)
    candidate_high = candidate_means + 1.96 * candidate_sd / math.sqrt(prefix)
    reference_low = reference_means - 1.96 * reference_sd / math.sqrt(reference_count)
    reference_high = reference_means + 1.96 * reference_sd / math.sqrt(reference_count)
    overlap = (candidate_low <= reference_high) & (reference_low <= candidate_high)

    top1 = _paired_bootstrap_top1_diagnostics(
        values,
        reference_values,
        seed=_bootstrap_seed(candidate, reference, objective, prefix),
    )
    candidate_winner = int(np.argmax(candidate_means))
    best_reference = float(np.max(reference_means))
    relative_regret = max(
        0.0,
        (best_reference - float(reference_means[candidate_winner]))
        / max(abs(best_reference), 1.0e-12),
    )
    return {
        "top1_probability": top1["agreement_probability"],
        "candidate_winner_probability": top1["candidate_winner_probability"],
        "reference_winner_probability": top1["reference_winner_probability"],
        "top1_probability_method": "paired-replicate-mean-bootstrap",
        "top1_bootstrap_resamples": TOP1_BOOTSTRAP_RESAMPLES,
        "mean_top1_agreement": bool(np.argmax(candidate_means) == np.argmax(reference_means)),
        "spearman_rank_correlation": correlation,
        "interval_overlap_rate": float(np.mean(overlap)),
        "relative_reference_regret": relative_regret,
        "candidate_top_design_key": keys[int(np.argmax(candidate_means))],
        "reference_top_design_key": keys[int(np.argmax(reference_means))],
    }


def _summary(comparisons: list[dict], thresholds) -> dict:
    if not comparisons:
        raise ValueError("cannot summarize an empty comparison set")
    metrics = {
        "min_top1_probability": min(row["top1_probability"] for row in comparisons),
        "min_candidate_winner_probability": min(
            row["candidate_winner_probability"] for row in comparisons
        ),
        "min_reference_winner_probability": min(
            row["reference_winner_probability"] for row in comparisons
        ),
        "min_spearman_rank_correlation": min(
            row["spearman_rank_correlation"] for row in comparisons
        ),
        "min_interval_overlap_rate": min(row["interval_overlap_rate"] for row in comparisons),
        "all_mean_top1_agree": all(row["mean_top1_agreement"] for row in comparisons),
        "max_relative_reference_regret": max(
            row["relative_reference_regret"] for row in comparisons
        ),
    }
    metrics["passed"] = bool(
        metrics["min_top1_probability"] >= thresholds.min_top1_probability
        and metrics["min_candidate_winner_probability"] >= thresholds.min_top1_probability
        and metrics["min_reference_winner_probability"] >= thresholds.min_top1_probability
        and metrics["min_spearman_rank_correlation"] >= thresholds.min_rank_correlation
        and metrics["min_interval_overlap_rate"] >= thresholds.min_interval_overlap_rate
        and metrics["max_relative_reference_regret"]
        <= thresholds.max_relative_reference_regret
        and metrics["all_mean_top1_agree"]
    )
    return metrics


def _as_setting(setting: tuple[int, int, int]) -> dict[str, int]:
    return {"n_outer": setting[0], "n_inner": setting[1], "n_replicates": setting[2]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    require_slurm()
    plan = load_study_plan(args.run_dir)
    indexed, inputs = _load_scores(args.run_dir)
    states = [
        (seed, nobs)
        for seed in plan.validation_state_seeds
        for nobs in plan.validation_observation_counts
    ]
    reference_setting = (
        plan.reference.n_outer, plan.reference.n_inner, plan.reference.n_replicates,
    )
    audit_setting = (plan.audit.n_outer, plan.audit.n_inner, plan.audit.n_replicates)
    physical_replicates = max(plan.replicate_grid)

    references = {}
    for state in states:
        key = ("reference", state, reference_setting)
        if key not in indexed:
            raise ValueError(f"missing reference score for state {state}")
        references[state] = indexed[key]

    setting_results = []
    for setting_obj in plan.candidate_settings:
        setting = (
            setting_obj.n_outer, setting_obj.n_inner, setting_obj.n_replicates,
        )
        physical_setting = (setting[0], setting[1], physical_replicates)
        objective_results = {}
        for objective in ("raw", "per_cost"):
            comparisons = []
            for state in states:
                key = ("grid", state, physical_setting)
                if key not in indexed:
                    raise ValueError(f"missing physical grid score {physical_setting} for {state}")
                comparison = _comparison(
                    indexed[key], references[state], objective, setting[2],
                )
                comparison["state"] = {"seed": state[0], "n_observations": state[1]}
                comparisons.append(comparison)
            objective_results[objective] = {
                "summary": _summary(comparisons, plan.thresholds),
                "state_comparisons": comparisons,
            }
        passed = all(value["summary"]["passed"] for value in objective_results.values())
        setting_results.append({
            "setting": _as_setting(setting),
            "estimated_work": setting[0] * setting[1] * setting[2],
            "objectives": objective_results,
            "passed": passed,
        })

    sentinel_states = [
        (plan.validation_state_seeds[0], min(plan.validation_observation_counts)),
        (plan.validation_state_seeds[0], max(plan.validation_observation_counts)),
    ]
    audit_objectives = {}
    for objective in ("raw", "per_cost"):
        comparisons = []
        for state in sentinel_states:
            key = ("audit", state, audit_setting)
            if key not in indexed:
                raise ValueError(f"missing audit score for sentinel state {state}")
            comparison = _comparison(
                references[state], indexed[key], objective, reference_setting[2],
            )
            comparison["state"] = {"seed": state[0], "n_observations": state[1]}
            comparisons.append(comparison)
        audit_objectives[objective] = {
            "summary": _summary(comparisons, plan.thresholds),
            "state_comparisons": comparisons,
        }
    reference_audit_passed = all(
        value["summary"]["passed"] for value in audit_objectives.values()
    )
    if not reference_audit_passed:
        raise RuntimeError("reference setting failed the prespecified audit adequacy gate")

    passing = [row for row in setting_results if row["passed"]]
    if passing:
        selected = min(
            passing,
            key=lambda row: (
                row["estimated_work"], -row["setting"]["n_inner"],
                -row["setting"]["n_outer"], -row["setting"]["n_replicates"],
            ),
        )["setting"]
        mode = "grid"
    else:
        selected = _as_setting(reference_setting)
        mode = "reference_fallback"

    record = {
        "schema_version": SCHEMA,
        "case_study": "magnetic_core",
        "provenance": provenance(seed=plan.validation_state_seeds[0]),
        "study_plan": plan.as_dict(),
        "thresholds": plan.thresholds.as_dict(),
        "reference_setting": _as_setting(reference_setting),
        "audit_setting": _as_setting(audit_setting),
        "reference_audit": {
            "objectives": audit_objectives,
            "passed": reference_audit_passed,
        },
        "settings": setting_results,
        "selected_setting": selected,
        "selection_mode": mode,
        "inputs": inputs,
        "valid": True,
        "validity": {
            "reference_audit_passed": reference_audit_passed,
            "all_expected_states_present": len(references) == len(states),
            "valid": True,
        },
    }
    _atomic_json(args.out, record)
    print(args.out)


if __name__ == "__main__":
    main()
