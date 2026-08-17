"""Canonical immutable result records and provenance."""

from __future__ import annotations

import json
import hashlib
import math
import os
import platform
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from .runtime import slurm_metadata

SCHEMA_VERSION = "magnetic-calibration/1.0"
REQUIRED_SECTIONS = {
    "schema_version", "case_study", "run_id", "provenance", "data", "model",
    "sampler", "posterior", "predictive", "design", "claim_context", "validity",
}
PARAMETERS = {"k", "alpha", "beta", "mu_s", "f_rel_hz", "alpha_cc"}
_HEX_DIGITS = frozenset("0123456789abcdef")
BENCHMARK_V4_POLICY_OBJECTIVES = {
    "eig_raw": "raw",
    "eig_per_cost": "per_cost",
    "fixed_channel_balanced": "fixed_channel_balanced_traversal",
    "random_channel_balanced": "random_channel_balanced_traversal",
    "predictive_variance_raw": "raw",
    "predictive_variance_per_cost": "per_cost",
    "laplace_d_opt_raw": "raw",
    "laplace_d_opt_per_cost": "per_cost",
}
BENCHMARK_V4_COMPARATOR_METHODS = {
    "predictive_variance_raw": "predictive_variance",
    "predictive_variance_per_cost": "predictive_variance",
    "laplace_d_opt_raw": "laplace_d_opt",
    "laplace_d_opt_per_cost": "laplace_d_opt",
}
BENCHMARK_V4_POLICY_REGISTRY = [
    {"policy": "eig_raw", "method": "eig", "objective": "raw", "primary_endpoint": "measurement_count_to_gate"},
    {"policy": "eig_per_cost", "method": "eig", "objective": "per_cost", "primary_endpoint": "modeled_cost_to_gate"},
    {"policy": "fixed_channel_balanced", "method": "fixed_channel_balanced", "objective": "fixed_channel_balanced_traversal", "primary_endpoint": "descriptive_count_and_modeled_cost"},
    {"policy": "random_channel_balanced", "method": "random_channel_balanced", "objective": "random_channel_balanced_traversal", "primary_endpoint": "descriptive_count_and_modeled_cost"},
    {"policy": "predictive_variance_raw", "method": "predictive_variance", "objective": "raw", "primary_endpoint": "measurement_count_to_gate"},
    {"policy": "predictive_variance_per_cost", "method": "predictive_variance", "objective": "per_cost", "primary_endpoint": "modeled_cost_to_gate"},
    {"policy": "laplace_d_opt_raw", "method": "laplace_d_opt", "objective": "raw", "primary_endpoint": "measurement_count_to_gate"},
    {"policy": "laplace_d_opt_per_cost", "method": "laplace_d_opt", "objective": "per_cost", "primary_endpoint": "modeled_cost_to_gate"},
]
BENCHMARK_V4_DIRECT_CONTRASTS = [
    {"name": "eig_raw_vs_predictive_variance_raw", "policy": "eig_raw", "comparator": "predictive_variance_raw", "endpoint": "measurement_count_to_gate"},
    {"name": "eig_raw_vs_laplace_d_opt_raw", "policy": "eig_raw", "comparator": "laplace_d_opt_raw", "endpoint": "measurement_count_to_gate"},
    {"name": "eig_per_cost_vs_predictive_variance_per_cost", "policy": "eig_per_cost", "comparator": "predictive_variance_per_cost", "endpoint": "modeled_cost_to_gate"},
    {"name": "eig_per_cost_vs_laplace_d_opt_per_cost", "policy": "eig_per_cost", "comparator": "laplace_d_opt_per_cost", "endpoint": "modeled_cost_to_gate"},
]
BENCHMARK_V4_COSTS = {"pcv": 60.0, "mu_real": 20.0, "mu_imag": 20.0, "lm": 15.0}
BENCHMARK_V4_HOLDOUT_COUNTS = {"pcv": 8, "mu_real": 6, "mu_imag": 6, "lm": 3}
BENCHMARK_V4_PRIMARY_ENDPOINTS = {
    entry["policy"]: entry["primary_endpoint"] for entry in BENCHMARK_V4_POLICY_REGISTRY
}


def _is_sha256(value: object) -> bool:
    """Return whether *value* is a lowercase hexadecimal SHA-256 digest."""
    return (
        isinstance(value, str)
        and len(value) == 64
        and set(value) <= _HEX_DIGITS
    )


def _finite_number(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
    )


def _payload_sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _posterior_state_seed(base_seed: int, state_key: tuple[str, ...]) -> int:
    payload = json.dumps(
        {
            "namespace": "magcore-posterior-state-v1",
            "base_seed": base_seed,
            "observed_design_identities": list(sorted(state_key)),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:4], "big", signed=False)


def _same_number(left: object, right: object) -> bool:
    return _finite_number(left) and _finite_number(right) and math.isclose(
        float(left), float(right), rel_tol=1e-10, abs_tol=1e-10,
    )


def _expected_paired_endpoint(policy: dict, fixed: dict) -> dict:
    count, fixed_count = policy["n_measurements_to_gate"], fixed["n_measurements_to_gate"]
    cost, fixed_cost = policy["modeled_cost_to_gate"], fixed["modeled_cost_to_gate"]
    return {
        "both_reached_gate": bool(policy["reached"] and fixed["reached"]),
        "measurement_count_difference": (
            None if count is None or fixed_count is None else fixed_count - count
        ),
        "measurement_count_reduction_pct": (
            None if count is None or fixed_count is None
            else (fixed_count - count) / fixed_count * 100.0
        ),
        "modeled_cost_difference": (
            None if cost is None or fixed_cost is None else fixed_cost - cost
        ),
        "modeled_cost_reduction_pct": (
            None if cost is None or fixed_cost is None
            else (fixed_cost - cost) / fixed_cost * 100.0
        ),
    }


def _validate_holdout(validation: dict) -> list[str]:
    summary = validation.get("holdout_latent_mean")
    rows = validation.get("holdout_point_records")
    if not isinstance(summary, dict) or set(summary) != set(BENCHMARK_V4_HOLDOUT_COUNTS):
        raise ValueError("benchmark v4 requires all four holdout channels")
    if not isinstance(rows, list) or len(rows) != 23:
        raise ValueError("benchmark v4 requires 23 point-level holdout records")
    required = {
        "design_key", "design_identity", "channel", "frequency_hz", "b_pk_t",
        "temperature_c", "truth", "posterior_median", "posterior_p05",
        "posterior_p95", "covered_by_latent_ci90", "relative_error",
    }
    identities: set[str] = set()
    grouped: dict[str, list[dict]] = {channel: [] for channel in BENCHMARK_V4_HOLDOUT_COUNTS}
    for row in rows:
        if not isinstance(row, dict) or set(row) != required:
            raise ValueError("benchmark v4 holdout point record is malformed")
        channel = row["channel"]
        identity = row["design_identity"]
        numeric = tuple(row[key] for key in required - {
            "design_key", "design_identity", "channel", "covered_by_latent_ci90",
        })
        if channel not in grouped or not isinstance(identity, str) or identity in identities \
                or not isinstance(row["design_key"], str) \
                or not isinstance(row["covered_by_latent_ci90"], bool) \
                or not all(_finite_number(value) for value in numeric):
            raise ValueError("benchmark v4 holdout point record is outside its domain")
        exact_identity = "|".join((
            channel, float(row["frequency_hz"]).hex(), float(row["b_pk_t"]).hex(),
            float(row["temperature_c"]).hex(),
        ))
        if identity != exact_identity or row["truth"] == 0.0 \
                or not row["posterior_p05"] <= row["posterior_median"] <= row["posterior_p95"]:
            raise ValueError("benchmark v4 holdout point identity/quantiles are inconsistent")
        expected_error = (row["posterior_median"] - row["truth"]) / row["truth"]
        expected_covered = bool(
            row["posterior_p05"] <= row["truth"] <= row["posterior_p95"]
            or math.isclose(row["truth"], row["posterior_p05"], rel_tol=1e-12, abs_tol=0.0)
            or math.isclose(row["truth"], row["posterior_p95"], rel_tol=1e-12, abs_tol=0.0)
        )
        if not _same_number(row["relative_error"], expected_error) \
                or row["covered_by_latent_ci90"] != expected_covered:
            raise ValueError("benchmark v4 holdout point metrics are inconsistent")
        identities.add(identity)
        grouped[channel].append(row)
    if {channel: len(items) for channel, items in grouped.items()} != BENCHMARK_V4_HOLDOUT_COUNTS:
        raise ValueError("benchmark v4 holdout channel counts differ from the contract")
    for channel, items in grouped.items():
        errors = [float(item["relative_error"]) for item in items]
        expected = {
            "n_points": len(items),
            "relative_rmse_pct": math.sqrt(sum(value * value for value in errors) / len(errors)) * 100.0,
            "median_absolute_relative_error_pct": statistics.median(abs(value) for value in errors) * 100.0,
            "latent_ci90_coverage_fraction": sum(
                int(item["covered_by_latent_ci90"]) for item in items
            ) / len(items),
        }
        actual = summary.get(channel)
        if not isinstance(actual, dict) or set(actual) != set(expected) \
                or actual["n_points"] != expected["n_points"] \
                or any(not _same_number(actual[key], expected[key]) for key in expected if key != "n_points"):
            raise ValueError("benchmark v4 holdout summary is not reconstructable from point rows")
    return sorted(identities)


def _validate_benchmark_v4(record: dict, design: dict) -> None:
    """Fail closed on the exact v4 protocol and every auditable state transition."""

    policies = design.get("policies")
    if not isinstance(policies, dict) or set(policies) != set(BENCHMARK_V4_POLICY_OBJECTIVES):
        raise ValueError("benchmark v4 has an incomplete or unexpected policy set")
    if design.get("comparator_registry") != BENCHMARK_V4_POLICY_REGISTRY \
            or design.get("direct_contrasts") != BENCHMARK_V4_DIRECT_CONTRASTS \
            or design.get("primary_endpoints") != BENCHMARK_V4_PRIMARY_ENDPOINTS:
        raise ValueError("benchmark v4 registry, contrasts, or primary endpoints differ from preregistration")
    if record.get("claim_context") != {
        "synthetic": True, "matched_model": True, "prior_predictive_truth": True,
        "datasheet_centered_on_realized_truth": False, "oracle_initialized": False,
        "measured_data": False,
        "scope": "algorithmic matched-model synthetic benchmark; not validated laboratory efficiency",
    }:
        raise ValueError("benchmark v4 claim context must state exact matched-model non-oracle scope")
    predictive = record.get("predictive")
    if predictive != {
        "gate": "two-output latent-mean-response precision gate",
        "targets": {
            "pcv": {
                "frequency_hz": 100000.0, "b_pk_t": 0.1, "temperature_c": 25.0,
                "ci90_half_width_pct_max": 8.0,
            },
            "lm": {
                "frequency_hz": 100000.0, "b_pk_t": 0.0, "temperature_c": 25.0,
                "ci90_half_width_pct_max": 5.0,
            },
        },
    }:
        raise ValueError("benchmark v4 predictive gate record differs from its contract")
    data = record.get("data", {})
    if data.get("candidate_count") != 37 or data.get("holdout_count") != 23 \
            or data.get("common_random_outcomes") is not True:
        raise ValueError("benchmark v4 requires exactly 37 candidates and 23 shared-outcome holdouts")
    for name in ("truth_sha256", "outcome_manifest_sha256", "holdout_manifest_sha256"):
        if not _is_sha256(data.get(name)):
            raise ValueError(f"benchmark v4 requires {name}")
    if design.get("modeled_cost_seconds") != BENCHMARK_V4_COSTS \
            or design.get("modeled_cost_interpretation") != "prespecified assumption, not laboratory time":
        raise ValueError("benchmark v4 modeled-cost contract is not exact")
    expected_gate = {
        "quantity": "latent_mean_response", "pcv_ci_half_width_pct": 8.0,
        "lm_ci_half_width_pct": 5.0,
        "pcv_target": {"frequency_hz": 100000.0, "b_pk_t": 0.1, "temperature_c": 25.0},
        "lm_target": {"frequency_hz": 100000.0, "b_pk_t": 0.0, "temperature_c": 25.0},
    }
    if design.get("gate_contract") != expected_gate or design.get("holdout_contract") != {
        "total_points": 23, "channel_counts": BENCHMARK_V4_HOLDOUT_COUNTS,
        "used_for_acquisition_or_stopping": False,
    }:
        raise ValueError("benchmark v4 gate or holdout contract is not exact")
    runtime = design.get("runtime_contract")
    if runtime != {
        "max_measurements": 25, "n_walkers": 48, "n_steps": 20000,
        "burn": 4000, "objectives": ["raw", "per_cost"],
    }:
        raise ValueError("benchmark v4 runtime contract differs from preregistration")
    secondary = design.get("secondary_validation_endpoints")
    if not isinstance(secondary, dict) or secondary.get("used_for_acquisition_or_stopping") is not False:
        raise ValueError("benchmark v4 must keep secondary validation out of decisions")

    expected_replicates = design.get("eig_estimator_replicates")
    setting = design.get("eig_estimator_setting")
    if isinstance(expected_replicates, bool) or not isinstance(expected_replicates, int) \
            or expected_replicates < 2 or not isinstance(setting, dict) \
            or set(setting) != {"n_outer", "n_inner", "n_replicates"} \
            or any(isinstance(value, bool) or not isinstance(value, int) or value < 1 for value in setting.values()) \
            or setting["n_replicates"] != expected_replicates:
        raise ValueError("benchmark v4 estimator setting is malformed")
    decision = design.get("estimator_decision")
    if not _is_sha256(design.get("estimator_decision_sha256")) \
            or not isinstance(decision, dict) \
            or decision.get("schema_version") != "eig-convergence-final/1.0" \
            or decision.get("selected_setting") != setting \
            or decision.get("valid") is not True \
            or decision.get("raw_claim_gate_passed") is not True \
            or decision.get("per_cost_claim_gate_passed") is not True:
        raise ValueError("benchmark v4 estimator setting does not match its decision contents")

    diagnostics = record.get("sampler", {}).get("policy_diagnostics")
    validity = record.get("validity", {})
    if not isinstance(diagnostics, dict) or set(diagnostics) != set(policies):
        raise ValueError("benchmark v4 requires final diagnostics for every policy")
    initial_keys: set[tuple[str, ...]] = set()
    initial_identities: set[tuple[str, ...]] = set()
    state_audit: dict[str, tuple[tuple[str, ...], int, dict]] = {}
    candidate_universes: set[frozenset[str]] = set()
    policy_selected_sets: list[set[str]] = []
    for policy_name, expected_objective in BENCHMARK_V4_POLICY_OBJECTIVES.items():
        policy = policies[policy_name]
        if not isinstance(policy, dict) or policy.get("policy") != policy_name \
                or policy.get("objective") != expected_objective:
            raise ValueError("benchmark v4 policy name/objective mismatch")
        trajectory = policy.get("trajectory")
        if not isinstance(trajectory, list) or not trajectory:
            raise ValueError("benchmark v4 policy trajectory must be nonempty")
        if len(trajectory) > 24:
            raise ValueError("benchmark v4 trajectory exceeds its measurement budget")
        validation = policy.get("validation_endpoints")
        if not isinstance(validation, dict) or validation.get("used_for_acquisition_or_stopping") is not False:
            raise ValueError("benchmark v4 lacks decision-independent validation")
        recovery = validation.get("parameter_recovery")
        if not isinstance(recovery, dict) or set(recovery) != PARAMETERS:
            raise ValueError("benchmark v4 validation requires all six parameters")
        required_recovery = {"truth", "median", "p05", "p95", "absolute_error_pct", "truth_in_ci90"}
        for entry in recovery.values():
            if not isinstance(entry, dict) or required_recovery - entry.keys() \
                    or not all(_finite_number(entry[key]) for key in required_recovery - {"truth_in_ci90"}) \
                    or not isinstance(entry["truth_in_ci90"], bool):
                raise ValueError("benchmark v4 parameter validation is malformed")
        truth_count = validation.get("parameter_truth_in_ci90_count")
        if truth_count != sum(int(entry["truth_in_ci90"]) for entry in recovery.values()):
            raise ValueError("benchmark v4 parameter coverage count is inconsistent")
        holdout_identities = _validate_holdout(validation)
        if _payload_sha256(holdout_identities) != data["holdout_manifest_sha256"]:
            raise ValueError("benchmark v4 holdout records do not match their manifest hash")

        for index, row in enumerate(trajectory):
            keys = row.get("selected_keys")
            identities = row.get("selected_identities")
            expected_count = index + 2
            if not isinstance(keys, list) or not isinstance(identities, list) \
                    or row.get("n_measurements") != expected_count \
                    or len(keys) != expected_count or len(identities) != expected_count \
                    or len(set(identities)) != expected_count:
                raise ValueError("benchmark v4 trajectory measurement sequence is inconsistent")
            if index == 0:
                initial_keys.add(tuple(keys))
                initial_identities.add(tuple(identities))
            state = row.get("decision_state")
            state_key = tuple(sorted(identities))
            base_seed = record.get("provenance", {}).get("seed")
            if not isinstance(state, dict) or state.get("observed_design_identities") != list(state_key) \
                    or state.get("n_observations") != expected_count \
                    or state.get("state_identity_sha256") != _payload_sha256(list(state_key)) \
                    or state.get("mcmc_seed_namespace") != "magcore-posterior-state-v1" \
                    or isinstance(state.get("mcmc_seed"), bool) \
                    or not isinstance(state.get("mcmc_seed"), int) \
                    or not 0 <= state["mcmc_seed"] <= 2**32 - 1 \
                    or isinstance(base_seed, bool) or not isinstance(base_seed, int) \
                    or state["mcmc_seed"] != _posterior_state_seed(base_seed, state_key) \
                    or not isinstance(state.get("fit_cache_reused"), bool) \
                    or not isinstance(state.get("sampler_diagnostics"), dict) \
                    or not isinstance(state["sampler_diagnostics"].get("valid"), bool) \
                    or state.get("valid") != state["sampler_diagnostics"]["valid"]:
                raise ValueError("benchmark v4 decision-state audit is malformed")
            state_signature = (state_key, state["mcmc_seed"], state["sampler_diagnostics"])
            prior_signature = state_audit.setdefault(state["state_identity_sha256"], state_signature)
            if prior_signature != state_signature:
                raise ValueError("benchmark v4 identical posterior states have inconsistent draws")
            pcv_ci = row.get("pcv_latent_mean_ci90_half_width_pct")
            lm_ci = row.get("lm_latent_mean_ci90_half_width_pct")
            expected_reached = _finite_number(pcv_ci) and _finite_number(lm_ci) \
                and float(pcv_ci) <= 8.0 and float(lm_ci) <= 5.0
            if row.get("reached") is not expected_reached:
                raise ValueError("benchmark v4 stopping decision differs from the declared gate")
            expected_cost = sum(BENCHMARK_V4_COSTS[identity.split("|", 1)[0]] for identity in identities)
            if not _same_number(row.get("modeled_cost_units"), expected_cost):
                raise ValueError("benchmark v4 trajectory cost is inconsistent")
            acquisition = row.get("acquisition")
            is_final = index == len(trajectory) - 1
            if is_final:
                if acquisition is not None:
                    raise ValueError("benchmark v4 final state must not contain an unused acquisition")
            else:
                if not isinstance(acquisition, dict) or row["reached"]:
                    raise ValueError("benchmark v4 nonterminal state must contain one acquisition")
                next_row = trajectory[index + 1]
                if next_row.get("selected_keys") != keys + [acquisition.get("selected_key")] \
                        or next_row.get("selected_identities") != identities + [acquisition.get("selected_identity")]:
                    raise ValueError("benchmark v4 selected acquisition was not appended exactly once")
            if acquisition is None:
                continue
            selected_key, selected_identity = acquisition.get("selected_key"), acquisition.get("selected_identity")
            if not isinstance(selected_key, str) or not isinstance(selected_identity, str) \
                    or selected_identity in identities or acquisition.get("objective") != expected_objective:
                raise ValueError("benchmark v4 acquisition identity/objective is invalid")
            if policy_name in ("eig_raw", "eig_per_cost"):
                scores = acquisition.get("candidate_scores")
                if not isinstance(scores, list) or len(scores) != 37 - expected_count:
                    raise ValueError("benchmark v4 EIG ranking does not cover every remaining candidate")
                score_identities = []
                for score in scores:
                    required = {"design_key", "design_identity", "channel", "eig_mean_nats", "eig_sd_nats", "eig_se_nats", "eig_ci95_nats", "utility_mean", "top_selection_rate", "replicate_scores_nats"}
                    if not isinstance(score, dict) or required - score.keys() or score.get("channel") not in BENCHMARK_V4_COSTS:
                        raise ValueError("benchmark v4 EIG candidate score is incomplete")
                    replicates, interval = score["replicate_scores_nats"], score["eig_ci95_nats"]
                    scalars = (score["eig_mean_nats"], score["eig_sd_nats"], score["eig_se_nats"], score["utility_mean"], score["top_selection_rate"])
                    if not isinstance(replicates, list) or len(replicates) != expected_replicates \
                            or not isinstance(interval, list) or len(interval) != 2 \
                            or not all(_finite_number(value) for value in (*scalars, *interval, *replicates)) \
                            or score["eig_sd_nats"] < 0 or score["eig_se_nats"] < 0 \
                            or not 0 <= score["top_selection_rate"] <= 1:
                        raise ValueError("benchmark v4 EIG uncertainty is malformed")
                    expected_utility = score["eig_mean_nats"] if expected_objective == "raw" else score["eig_mean_nats"] / BENCHMARK_V4_COSTS[score["channel"]]
                    if not _same_number(score["utility_mean"], expected_utility):
                        raise ValueError("benchmark v4 EIG utility/objective is inconsistent")
                    score_identities.append(score["design_identity"])
                if len(set(score_identities)) != len(score_identities) or set(score_identities) & set(identities) \
                        or scores[0]["design_key"] != selected_key or scores[0]["design_identity"] != selected_identity \
                        or any(left["utility_mean"] < right["utility_mean"] for left, right in zip(scores, scores[1:])) \
                        or not math.isclose(sum(score["top_selection_rate"] for score in scores), 1.0, rel_tol=1e-9, abs_tol=1e-9):
                    raise ValueError("benchmark v4 EIG ranking/top selection is inconsistent")
                if index == 0:
                    candidate_universes.add(frozenset((*identities, *score_identities)))
            elif policy_name in BENCHMARK_V4_COMPARATOR_METHODS:
                scores = acquisition.get("candidate_scores")
                if not isinstance(scores, list) or len(scores) != 37 - expected_count:
                    raise ValueError("benchmark v4 comparator ranking does not cover remaining candidates")
                score_identities = []
                for score in scores:
                    method = BENCHMARK_V4_COMPARATOR_METHODS[policy_name]
                    required = {"design_key", "design_identity", "channel", "method", "objective", "score", "score_units", "utility", "noise_sigma"}
                    if not isinstance(score, dict) or required - score.keys() or score.get("method") != method \
                            or score.get("objective") != expected_objective or score.get("channel") not in BENCHMARK_V4_COSTS \
                            or not all(_finite_number(score.get(key)) for key in ("score", "utility", "noise_sigma")) \
                            or score["score"] < 0 or score["noise_sigma"] <= 0 \
                            or score.get("score_units") != ("nats" if method == "laplace_d_opt" else "dimensionless_ratio"):
                        raise ValueError("benchmark v4 comparator score metadata is malformed")
                    expected_utility = score["score"] if expected_objective == "raw" else score["score"] / BENCHMARK_V4_COSTS[score["channel"]]
                    if not _same_number(score["utility"], expected_utility):
                        raise ValueError("benchmark v4 comparator utility/objective is inconsistent")
                    score_identities.append(score["design_identity"])
                if len(set(score_identities)) != len(score_identities) or set(score_identities) & set(identities) \
                        or scores[0]["design_key"] != selected_key or scores[0]["design_identity"] != selected_identity \
                        or any(left["utility"] < right["utility"] for left, right in zip(scores, scores[1:])):
                    raise ValueError("benchmark v4 comparator did not select its top-ranked design")
                if index == 0:
                    candidate_universes.add(frozenset((*identities, *score_identities)))
            elif policy_name == "random_channel_balanced":
                if acquisition.get("seed_namespace") != "random_channel_balanced/v1" \
                        or isinstance(acquisition.get("seed"), bool) or not isinstance(acquisition.get("seed"), int):
                    raise ValueError("benchmark v4 random policy lacks its independent seed")
            elif acquisition.get("objective") != "fixed_channel_balanced_traversal":
                raise ValueError("benchmark v4 fixed traversal objective is inconsistent")

        final = trajectory[-1]
        reached = bool(final["reached"])
        if policy.get("reached") is not reached \
                or validation.get("evaluated_at_measurement_count") != final["n_measurements"] \
                or (not reached and final["n_measurements"] != 25) \
                or policy.get("n_measurements_to_gate") != (final["n_measurements"] if reached else None) \
                or policy.get("modeled_cost_to_gate") != (final["modeled_cost_units"] if reached else None):
            raise ValueError("benchmark v4 final count/cost endpoint is inconsistent")
        overall_valid = all(row["decision_state"]["valid"] for row in trajectory)
        policy_selected_sets.append(set(final["selected_identities"]))
        validity_key = f"{policy_name}_convergence_valid"
        if validity.get(validity_key) is not overall_valid \
                or diagnostics[policy_name] != final["decision_state"]["sampler_diagnostics"]:
            raise ValueError("benchmark v4 policy convergence validity is inconsistent")

    if len(initial_keys) != 1 or len(initial_identities) != 1:
        raise ValueError("benchmark v4 policies do not share the same initial two observations")
    if len(candidate_universes) != 1:
        raise ValueError("benchmark v4 scored policies do not share one exact candidate library")
    candidate_universe = set(next(iter(candidate_universes)))
    if len(candidate_universe) != 37 or any(
        not selected <= candidate_universe for selected in policy_selected_sets
    ):
        raise ValueError("benchmark v4 selected designs are outside the exact candidate library")
    cache = design.get("posterior_state_cache")
    requested_fits = sum(len(policy["trajectory"]) for policy in policies.values())
    if cache != {
        "requested_fits": requested_fits,
        "unique_fits": len(state_audit),
        "key": "sorted exact observed-design identities",
    }:
        raise ValueError("benchmark v4 posterior-state cache provenance is inconsistent")
    endpoints = design.get("paired_endpoints")
    expected_endpoint_names = {f"{policy}_vs_fixed" for policy in policies if policy != "fixed_channel_balanced"}
    if not isinstance(endpoints, dict) or set(endpoints) != expected_endpoint_names:
        raise ValueError("benchmark v4 must pair every non-fixed policy with fixed")
    fixed = policies["fixed_channel_balanced"]
    for policy_name in policies:
        if policy_name == "fixed_channel_balanced":
            continue
        expected = _expected_paired_endpoint(policies[policy_name], fixed)
        actual = endpoints[f"{policy_name}_vs_fixed"]
        if not isinstance(actual, dict) or set(actual) != set(expected) or any(
            actual[key] != value if value is None or isinstance(value, bool)
            else not _same_number(actual[key], value)
            for key, value in expected.items()
        ):
            raise ValueError("benchmark v4 paired endpoint is inconsistent with policy results")


def git_commit(cwd: str | None = None) -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=cwd, check=True,
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def provenance(*, seed: int, command: list[str] | None = None,
               cwd: str | None = None, data_paths: list[str | Path] | None = None) -> dict:
    command = command or sys.argv
    project_root = Path(__file__).resolve().parents[2]
    lock = project_root / "configs" / "dependencies.lock"
    command_hash = hashlib.sha256(
        json.dumps(command, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()
    configuration_hash = os.environ.get("MAGCORE_CONFIG_SHA256", command_hash)
    dependency_hash = sha256_file(lock)
    expected_dependency_hash = os.environ.get("MAGCORE_DEPENDENCY_LOCK_SHA256")
    if expected_dependency_hash and dependency_hash != expected_dependency_hash:
        raise RuntimeError("dependency lock differs from the submitted run snapshot")
    data_hashes = {str(path): sha256_file(path) for path in (data_paths or [])}
    if not data_hashes:
        # Synthetic studies have no external observation file. Bind their
        # generated observations to the declared seed and exact command so the
        # canonical schema still has a non-empty, reproducible data digest.
        synthetic_recipe = json.dumps(
            {"seed": seed, "command": command},
            sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        ).encode("utf-8")
        data_hashes["synthetic://seed-and-command"] = hashlib.sha256(
            synthetic_recipe
        ).hexdigest()
    return {
        "started_at_utc": os.environ.get("STARTED_AT"),
        "ended_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": os.environ.get("MAGCORE_GIT_REVISION") or git_commit(cwd),
        "seed": seed,
        "command": command,
        "command_sha256": command_hash,
        "configuration_sha256": configuration_hash,
        "data_sha256": data_hashes,
        "dependency_lock_sha256": dependency_hash,
        "python": platform.python_version(),
        "slurm": slurm_metadata(),
    }


def validate_result(record: dict) -> None:
    missing = REQUIRED_SECTIONS - record.keys()
    if missing:
        raise ValueError(f"result missing sections: {sorted(missing)}")
    if record["schema_version"] != SCHEMA_VERSION or record["case_study"] != "magnetic_core":
        raise ValueError("wrong result schema or case study")
    posterior = record["posterior"]
    if set(posterior) != PARAMETERS:
        raise ValueError("posterior must report exactly six canonical magnetic parameters")
    claims = record["claim_context"]
    if claims.get("oracle_initialized") is not False:
        raise ValueError("canonical results must explicitly certify non-oracle initialization")
    design = record["design"]
    if design.get("benchmark_version") == 4:
        _validate_benchmark_v4(record, design)
    if design.get("benchmark_version") in (2, 3):
        policies = design.get("policies", {})
        required_policies = {"eig_raw", "eig_per_cost", "fixed_channel_balanced"}
        if set(policies) != required_policies:
            raise ValueError("benchmark v2 must contain raw EIG, EIG/cost, and fixed policies")
        endpoints = design.get("paired_endpoints", {})
        if set(endpoints) != {"eig_raw_vs_fixed", "eig_per_cost_vs_fixed"}:
            raise ValueError("benchmark v2 must report paired count and modeled-cost endpoints")
        if not isinstance(design.get("eig_estimator_replicates"), int) \
                or design["eig_estimator_replicates"] < 2:
            raise ValueError("benchmark v2 requires repeated EIG estimates")
        expected_replicates = design["eig_estimator_replicates"]
        for policy_name in ("eig_raw", "eig_per_cost"):
            for row in policies[policy_name].get("trajectory", []):
                acquisition = row.get("acquisition")
                if not acquisition:
                    continue
                candidate_scores = acquisition.get("candidate_scores", [])
                if not candidate_scores:
                    raise ValueError("benchmark v2 EIG decisions require candidate uncertainty")
                required_score_fields = {
                    "eig_mean_nats", "eig_sd_nats", "eig_se_nats", "eig_ci95_nats",
                    "top_selection_rate", "replicate_scores_nats",
                }
                if any(required_score_fields - score.keys() for score in candidate_scores):
                    raise ValueError("benchmark v2 candidate score is incomplete")
                for score in candidate_scores:
                    replicates = score["replicate_scores_nats"]
                    interval = score["eig_ci95_nats"]
                    scalar_values = (
                        score["eig_mean_nats"], score["eig_sd_nats"],
                        score["eig_se_nats"], score["top_selection_rate"],
                    )
                    if not isinstance(replicates, list) or len(replicates) != expected_replicates:
                        raise ValueError("benchmark v2 candidate replicate count is inconsistent")
                    if not isinstance(interval, list) or len(interval) != 2:
                        raise ValueError("benchmark v2 candidate interval is malformed")
                    if not all(math.isfinite(float(value)) for value in (*scalar_values, *interval, *replicates)):
                        raise ValueError("benchmark v2 candidate uncertainty must be finite")
                    if score["eig_sd_nats"] < 0.0 or score["eig_se_nats"] < 0.0:
                        raise ValueError("benchmark v2 candidate uncertainty cannot be negative")
                    if not 0.0 <= score["top_selection_rate"] <= 1.0:
                        raise ValueError("benchmark v2 top-selection rate must be in [0, 1]")
        if design.get("benchmark_version") == 3:
            setting = design.get("eig_estimator_setting", {})
            if set(setting) != {"n_outer", "n_inner", "n_replicates"} or any(
                not isinstance(value, int) or value < 1 for value in setting.values()
            ):
                raise ValueError(
                    "benchmark v3 requires the validated estimator setting"
                )
            if setting["n_replicates"] != expected_replicates:
                raise ValueError("benchmark v3 setting/replicate mismatch")
            if not _is_sha256(design.get("estimator_decision_sha256")):
                raise ValueError("benchmark v3 requires an estimator-decision hash")
            for name in ("truth_sha256", "outcome_manifest_sha256"):
                if not _is_sha256(record.get("data", {}).get(name)):
                    raise ValueError(f"benchmark v3 requires {name}")
    provenance_record = record["provenance"]
    required_provenance = {
        "started_at_utc", "ended_at_utc", "git_commit", "seed", "command",
        "configuration_sha256", "data_sha256", "dependency_lock_sha256", "python", "slurm",
    }
    if required_provenance - provenance_record.keys():
        raise ValueError("canonical result has incomplete provenance")
    if not _is_sha256(provenance_record.get("configuration_sha256")):
        raise ValueError("canonical result has an invalid configuration hash")
    if not _is_sha256(provenance_record.get("dependency_lock_sha256")):
        raise ValueError("canonical result has an invalid dependency-lock hash")
    data_hashes = provenance_record.get("data_sha256")
    if not isinstance(data_hashes, dict):
        raise ValueError("canonical result data hashes must be a mapping")
    if not data_hashes:
        raise ValueError("canonical result is missing data hashes")
    if any(not _is_sha256(digest) for digest in data_hashes.values()):
        raise ValueError("canonical result contains an invalid data hash")
    slurm = provenance_record.get("slurm", {})
    required_slurm = {"job_id", "array_job_id", "array_task_id", "node_list", "partition"}
    if required_slurm - slurm.keys() or not slurm.get("job_id") or not slurm.get("node_list"):
        raise ValueError("heavy canonical results require SLURM provenance")


def write_immutable(record: dict, artifacts_root: str | Path) -> Path:
    validate_result(record)
    destination = Path(artifacts_root) / str(record["run_id"]) / "result.json"
    destination.parent.mkdir(parents=True, exist_ok=False)
    temporary = destination.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, destination)
    return destination


def write_result(record: dict, output: str | Path) -> Path:
    """Write a validated result to a run-managed path using atomic replacement."""
    validate_result(record)
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp-write")
    temporary.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, destination)
    return destination
