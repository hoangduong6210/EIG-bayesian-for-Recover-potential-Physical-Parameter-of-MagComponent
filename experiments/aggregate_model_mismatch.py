#!/usr/bin/env python3
"""Aggregate complete MM-1 seed records without silently dropping failures."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
from pathlib import Path
from typing import Any

import numpy as np

from magcore_calib.model_mismatch import (
    MISMATCH_AGGREGATE_SCHEMA, POLICIES, config_sha256,
    load_model_mismatch_plan, validate_mismatch_result,
)
from magcore_calib.runtime import require_slurm


CONTRASTS = (
    ("eig_raw", "predictive_variance_raw", "n_measurements_to_gate"),
    ("eig_raw", "laplace_d_opt_raw", "n_measurements_to_gate"),
    ("eig_per_cost", "predictive_variance_per_cost", "modeled_cost_to_gate"),
    ("eig_per_cost", "laplace_d_opt_per_cost", "modeled_cost_to_gate"),
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mean(values: list[float]) -> float | None:
    return None if not values else float(statistics.mean(values))


def _median(values: list[float]) -> float | None:
    return None if not values else float(statistics.median(values))


def _paired_descriptive(
    values: list[float], *, seed: int, replicates: int = 10_000,
) -> dict[str, float | None]:
    """Return the preregistered deterministic paired summary."""

    if not values:
        return {
            "mean": None, "median": None, "sample_sd": None,
            "bootstrap_mean_ci95_low": None,
            "bootstrap_mean_ci95_high": None,
        }
    array = np.asarray(values, dtype=float)
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, array.size, size=(replicates, array.size))
    means = array[indices].mean(axis=1)
    return {
        "mean": float(array.mean()),
        "median": float(np.median(array)),
        "sample_sd": float(array.std(ddof=1)) if array.size > 1 else 0.0,
        "bootstrap_mean_ci95_low": float(np.quantile(means, 0.025)),
        "bootstrap_mean_ci95_high": float(np.quantile(means, 0.975)),
    }


def _bootstrap_seed(*parts: str) -> int:
    key = "|".join(("magcore-mm1-bootstrap-v1", *parts)).encode("utf-8")
    return int.from_bytes(hashlib.sha256(key).digest()[:8], "big")


def _policy_summary(records: list[dict[str, Any]], policy: str) -> dict[str, Any]:
    results = [record["policies"][policy] for record in records]
    reached = [result for result in results if result["reached"]]
    counts = [float(result["n_measurements_to_gate"]) for result in reached]
    costs = [float(result["modeled_cost_to_gate"]) for result in reached]
    false_confident = sum(
        int(result["mismatch_endpoints"]["gate_truth_accuracy"]["false_confident"])
        for result in results
    )
    holdout: dict[str, Any] = {}
    for channel in ("pcv", "mu_real", "mu_imag", "lm"):
        channel_rows = [
            result["mismatch_endpoints"]["holdout_latent_mean"][channel]
            for result in results
        ]
        holdout[channel] = {
            "mean_relative_rmse_pct": statistics.mean(
                row["relative_rmse_pct"] for row in channel_rows
            ),
            "mean_latent_ci90_coverage_fraction": statistics.mean(
                row["latent_ci90_coverage_fraction"] for row in channel_rows
            ),
        }
    temperatures = sorted(
        results[0]["mismatch_endpoints"]["holdout_pcv_by_temperature_c"],
        key=float,
    )
    pcv_by_temperature = {}
    for temperature in temperatures:
        rows = [
            result["mismatch_endpoints"]["holdout_pcv_by_temperature_c"][temperature]
            for result in results
        ]
        pcv_by_temperature[temperature] = {
            "mean_relative_rmse_pct": statistics.mean(
                row["relative_rmse_pct"] for row in rows
            ),
            "mean_latent_ci90_coverage_fraction": statistics.mean(
                row["latent_ci90_coverage_fraction"] for row in rows
            ),
        }
    return {
        "n_seeds": len(results), "reached_gate_count": len(reached),
        "failure_to_gate_count": len(results) - len(reached),
        "failure_to_gate_rate": (len(results) - len(reached)) / len(results),
        "measurement_count_reached_only": {
            "mean": _mean(counts), "median": _median(counts),
            "minimum": None if not counts else min(counts),
            "maximum": None if not counts else max(counts),
        },
        "modeled_cost_reached_only": {
            "mean": _mean(costs), "median": _median(costs),
            "minimum": None if not costs else min(costs),
            "maximum": None if not costs else max(costs),
        },
        "false_confidence_count": false_confident,
        "false_confidence_rate_all_seeds": false_confident / len(results),
        "false_confidence_rate_given_gate": (
            None if not reached else false_confident / len(reached)
        ),
        "holdout": holdout,
        "holdout_pcv_by_temperature_c": pcv_by_temperature,
    }


def _contrast_summary(
    records: list[dict[str, Any]], policy: str, comparator: str, endpoint: str,
    *, scenario: str,
) -> dict[str, Any]:
    differences: list[float] = []
    wins = ties = losses = 0
    for record in records:
        left = record["policies"][policy][endpoint]
        right = record["policies"][comparator][endpoint]
        if left is None or right is None:
            continue
        difference = float(right) - float(left)
        differences.append(difference)
        tied = bool(np.isclose(difference, 0.0, rtol=1.0e-12, atol=1.0e-9))
        wins += int(difference > 0.0 and not tied)
        ties += int(tied)
        losses += int(difference < 0.0 and not tied)
    policy_failures = sum(
        record["policies"][policy][endpoint] is None for record in records
    )
    comparator_failures = sum(
        record["policies"][comparator][endpoint] is None for record in records
    )
    return {
        "policy": policy, "comparator": comparator, "endpoint": endpoint,
        "difference_definition": "comparator_minus_policy",
        "positive_difference_favors": policy,
        "total_pair_count": len(records),
        "complete_pair_count": len(differences),
        "excluded_pair_count_due_to_gate_failure": len(records) - len(differences),
        "policy_gate_failure_count": policy_failures,
        "comparator_gate_failure_count": comparator_failures,
        "both_gate_failure_count": sum(
            record["policies"][policy][endpoint] is None
            and record["policies"][comparator][endpoint] is None
            for record in records
        ),
        "paired_differences": differences,
        "paired_difference": _paired_descriptive(
            differences,
            seed=_bootstrap_seed(scenario, policy, comparator, endpoint),
        ),
        "policy_wins": wins, "ties": ties, "policy_losses": losses,
        "win_rate_complete_pairs": wins / len(differences) if differences else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    require_slurm()
    plan = load_model_mismatch_plan(args.config)
    expected_config_sha = config_sha256(args.config)
    by_key: dict[tuple[str, int], tuple[Path, dict[str, Any]]] = {}
    for path in sorted(args.input_dir.glob("**/*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        validate_mismatch_result(record)
        if record["campaign_id"] != plan.campaign_id \
                or record["config_sha256"] != expected_config_sha:
            raise ValueError(f"record is outside the frozen MM-1 contract: {path}")
        key = record["scenario"]["name"], record["seed"]
        if record["scenario"] != plan.scenario(key[0]).as_dict():
            raise ValueError(f"record scenario differs from the preregistration: {path}")
        if record["provenance"].get("estimator_decision_sha256") \
                != plan.estimator_decision_sha256:
            raise ValueError(f"record uses the wrong estimator decision: {path}")
        if key in by_key:
            raise ValueError(f"duplicate model-mismatch result: {key}")
        by_key[key] = path, record
    expected = {
        (scenario.name, seed) for scenario in plan.scenarios for seed in plan.seeds
    }
    missing, extra = expected - by_key.keys(), by_key.keys() - expected
    if missing or extra:
        raise ValueError(
            f"MM-1 result matrix is incomplete: missing={sorted(missing)}, "
            f"extra={sorted(extra)}"
        )

    scenarios: dict[str, Any] = {}
    for scenario in plan.scenarios:
        records = [by_key[(scenario.name, seed)][1] for seed in plan.seeds]
        scenarios[scenario.name] = {
            "data_generating_contract": scenario.as_dict(),
            "policies": {
                policy: _policy_summary(records, policy) for policy in POLICIES
            },
            "paired_strong_comparator_contrasts": {
                f"{policy}_vs_{comparator}": _contrast_summary(
                    records, policy, comparator, endpoint, scenario=scenario.name
                )
                for policy, comparator, endpoint in CONTRASTS
            },
        }
    input_root = args.input_dir.resolve()
    source_files = [{
        "scenario": scenario, "seed": seed,
        "path": by_key[(scenario, seed)][0].resolve().relative_to(input_root).as_posix(),
        "sha256": _sha256(by_key[(scenario, seed)][0]),
    } for scenario, seed in sorted(by_key)]
    aggregate = {
        "schema_version": MISMATCH_AGGREGATE_SCHEMA,
        "campaign_id": plan.campaign_id,
        "config_sha256": expected_config_sha,
        "estimator_source_release_id": plan.estimator_source_release_id,
        "estimator_decision_sha256": plan.estimator_decision_sha256,
        "seed_count_per_scenario": len(plan.seeds),
        "scenario_count": len(plan.scenarios),
        "policy_count": len(POLICIES),
        "source_result_count": len(source_files),
        "source_files": source_files,
        "aggregation_rules": {
            "gate_failures_reported_separately": True,
            "count_and_cost_summaries_conditioned_on_reaching_gate": True,
            "paired_differences_exclude_pairs_with_either_gate_failure": True,
            "false_confidence_denominators": ["all_seeds", "reached_gate"],
            "holdout_used_for_stopping": False,
        },
        "scenarios": scenarios,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.out.exists():
        raise FileExistsError(f"refusing to overwrite MM-1 aggregate: {args.out}")
    temporary = args.out.with_name(args.out.name + ".tmp")
    temporary.write_text(
        json.dumps(aggregate, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, args.out)
    print(args.out)


if __name__ == "__main__":
    main()
