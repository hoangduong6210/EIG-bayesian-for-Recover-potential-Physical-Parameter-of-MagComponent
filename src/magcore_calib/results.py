"""Canonical immutable result records and provenance."""

from __future__ import annotations

import json
import hashlib
import math
import os
import platform
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


def _validate_benchmark_v4(record: dict, design: dict) -> None:
    """Fail closed on the exact v4 policy registry and auditable decisions."""

    policies = design.get("policies")
    if not isinstance(policies, dict) or set(policies) != set(BENCHMARK_V4_POLICY_OBJECTIVES):
        raise ValueError("benchmark v4 has an incomplete or unexpected policy set")
    expected_endpoints = {
        f"{policy}_vs_fixed"
        for policy in policies
        if policy != "fixed_channel_balanced"
    }
    endpoints = design.get("paired_endpoints")
    if not isinstance(endpoints, dict) or set(endpoints) != expected_endpoints:
        raise ValueError("benchmark v4 must pair every non-fixed policy with fixed")
    endpoint_fields = {
        "both_reached_gate", "measurement_count_difference",
        "measurement_count_reduction_pct", "modeled_cost_difference",
        "modeled_cost_reduction_pct",
    }
    for endpoint in endpoints.values():
        if not isinstance(endpoint, dict) or set(endpoint) != endpoint_fields:
            raise ValueError("benchmark v4 paired endpoint is malformed")
        if not isinstance(endpoint["both_reached_gate"], bool):
            raise ValueError("benchmark v4 gate-pair status must be boolean")
        for field in endpoint_fields - {"both_reached_gate"}:
            if endpoint[field] is not None and not _finite_number(endpoint[field]):
                raise ValueError("benchmark v4 paired endpoint must be finite or null")

    expected_replicates = design.get("eig_estimator_replicates")
    if isinstance(expected_replicates, bool) or not isinstance(expected_replicates, int) \
            or expected_replicates < 2:
        raise ValueError("benchmark v4 requires repeated EIG estimates")
    setting = design.get("eig_estimator_setting", {})
    if set(setting) != {"n_outer", "n_inner", "n_replicates"} or any(
        isinstance(value, bool) or not isinstance(value, int) or value < 1
        for value in setting.values()
    ):
        raise ValueError("benchmark v4 requires the validated estimator setting")
    if setting["n_replicates"] != expected_replicates:
        raise ValueError("benchmark v4 setting/replicate mismatch")
    if not _is_sha256(design.get("estimator_decision_sha256")):
        raise ValueError("benchmark v4 requires an estimator-decision hash")
    for name in ("truth_sha256", "outcome_manifest_sha256", "holdout_manifest_sha256"):
        if not _is_sha256(record.get("data", {}).get(name)):
            raise ValueError(f"benchmark v4 requires {name}")
    holdout_count = record.get("data", {}).get("holdout_count")
    if isinstance(holdout_count, bool) or not isinstance(holdout_count, int) \
            or holdout_count < 1:
        raise ValueError("benchmark v4 requires a nonempty holdout grid")
    if record.get("data", {}).get("common_random_outcomes") is not True:
        raise ValueError("benchmark v4 policies must share candidate-indexed outcomes")

    diagnostics = record.get("sampler", {}).get("policy_diagnostics")
    if not isinstance(diagnostics, dict) or set(diagnostics) != set(policies):
        raise ValueError("benchmark v4 requires diagnostics for the exact policy set")
    expected_validity = {f"{policy}_convergence_valid" for policy in policies}
    validity = record.get("validity", {})
    if not expected_validity <= validity.keys() or any(
        not isinstance(validity[key], bool) for key in expected_validity
    ):
        raise ValueError("benchmark v4 requires a convergence flag for every policy")
    primary = design.get("primary_endpoints")
    if not isinstance(primary, dict) or set(primary) != set(policies):
        raise ValueError("benchmark v4 requires one declared endpoint per policy")
    modeled_costs = design.get("modeled_cost_seconds")
    expected_channels = {"pcv", "mu_real", "mu_imag", "lm"}
    if not isinstance(modeled_costs, dict) or set(modeled_costs) != expected_channels \
            or any(not _finite_number(value) or value <= 0.0 for value in modeled_costs.values()):
        raise ValueError("benchmark v4 requires a positive four-channel cost model")
    if design.get("modeled_cost_interpretation") != \
            "prespecified assumption, not laboratory time":
        raise ValueError("benchmark v4 must qualify the modeled-cost interpretation")
    secondary = design.get("secondary_validation_endpoints")
    if not isinstance(secondary, dict) \
            or secondary.get("used_for_acquisition_or_stopping") is not False:
        raise ValueError("benchmark v4 must keep secondary validation out of decisions")

    initial_selected: set[tuple[str, ...]] = set()
    initial_identities: set[tuple[str, ...]] = set()
    for policy_name, expected_objective in BENCHMARK_V4_POLICY_OBJECTIVES.items():
        policy = policies[policy_name]
        if not isinstance(policy, dict) or policy.get("policy") != policy_name:
            raise ValueError("benchmark v4 policy record/name mismatch")
        if policy.get("objective") != expected_objective:
            raise ValueError("benchmark v4 policy objective mismatch")
        trajectory = policy.get("trajectory")
        if not isinstance(trajectory, list) or not trajectory:
            raise ValueError("benchmark v4 policy trajectory must be nonempty")
        validation = policy.get("validation_endpoints")
        if not isinstance(validation, dict) \
                or validation.get("used_for_acquisition_or_stopping") is not False:
            raise ValueError("benchmark v4 lacks decision-independent validation")
        final_count = trajectory[-1].get("n_measurements")
        if validation.get("evaluated_at_measurement_count") != final_count:
            raise ValueError("benchmark v4 validation is not aligned with final state")
        recovery = validation.get("parameter_recovery")
        if not isinstance(recovery, dict) or set(recovery) != PARAMETERS:
            raise ValueError("benchmark v4 validation requires all six parameters")
        required_recovery = {
            "truth", "median", "p05", "p95", "absolute_error_pct", "truth_in_ci90",
        }
        for entry in recovery.values():
            if not isinstance(entry, dict) or required_recovery - entry.keys() \
                    or not all(_finite_number(entry[key]) for key in required_recovery - {"truth_in_ci90"}) \
                    or not isinstance(entry["truth_in_ci90"], bool):
                raise ValueError("benchmark v4 parameter validation is malformed")
        truth_count = validation.get("parameter_truth_in_ci90_count")
        if isinstance(truth_count, bool) or not isinstance(truth_count, int) \
                or truth_count != sum(int(entry["truth_in_ci90"]) for entry in recovery.values()):
            raise ValueError("benchmark v4 parameter coverage count is inconsistent")
        holdout = validation.get("holdout_latent_mean")
        if not isinstance(holdout, dict) or set(holdout) != expected_channels:
            raise ValueError("benchmark v4 requires all four holdout channels")
        for channel in holdout.values():
            if not isinstance(channel, dict) or set(channel) != {
                "n_points", "relative_rmse_pct", "median_absolute_relative_error_pct",
                "latent_ci90_coverage_fraction",
            }:
                raise ValueError("benchmark v4 holdout validation is malformed")
            n_points = channel["n_points"]
            numeric = (
                channel["relative_rmse_pct"],
                channel["median_absolute_relative_error_pct"],
                channel["latent_ci90_coverage_fraction"],
            )
            if isinstance(n_points, bool) or not isinstance(n_points, int) or n_points < 1 \
                    or not all(_finite_number(value) for value in numeric) \
                    or numeric[0] < 0.0 or numeric[1] < 0.0 \
                    or not 0.0 <= numeric[2] <= 1.0:
                raise ValueError("benchmark v4 holdout validation is outside its domain")
        first_keys = trajectory[0].get("selected_keys")
        if not isinstance(first_keys, list) or len(first_keys) != 2:
            raise ValueError("benchmark v4 requires the same two initial observations")
        initial_selected.add(tuple(first_keys))
        for row in trajectory:
            selected_keys = row.get("selected_keys")
            if not isinstance(selected_keys, list):
                raise ValueError("benchmark v4 trajectory lacks display keys")
            selected_identities = row.get("selected_identities")
            if not isinstance(selected_identities, list) \
                    or len(selected_identities) != len(selected_keys) \
                    or len(selected_identities) != len(set(selected_identities)):
                raise ValueError("benchmark v4 trajectory requires unique exact identities")
            if row is trajectory[0]:
                initial_identities.add(tuple(selected_identities))
            acquisition = row.get("acquisition")
            if acquisition is None:
                continue
            selected_key = acquisition.get("selected_key")
            if not isinstance(selected_key, str):
                raise ValueError("benchmark v4 acquisition lacks a display key")
            selected_identity = acquisition.get("selected_identity")
            if not isinstance(selected_identity, str) \
                    or selected_identity in selected_identities:
                raise ValueError("benchmark v4 acquisition repeats an exact design identity")
            if policy_name in ("eig_raw", "eig_per_cost"):
                candidate_scores = acquisition.get("candidate_scores")
                if not isinstance(candidate_scores, list) or not candidate_scores:
                    raise ValueError("benchmark v4 EIG decision lacks candidate scores")
                required = {
                    "design_key", "design_identity", "channel",
                    "eig_mean_nats", "eig_sd_nats", "eig_se_nats", "eig_ci95_nats",
                    "utility_mean", "top_selection_rate", "replicate_scores_nats",
                }
                if any(
                    not isinstance(score, dict) or required - score.keys()
                    for score in candidate_scores
                ):
                    raise ValueError("benchmark v4 EIG candidate score is incomplete")
                for score in candidate_scores:
                    replicates = score["replicate_scores_nats"]
                    interval = score["eig_ci95_nats"]
                    scalars = (
                        score["eig_mean_nats"], score["eig_sd_nats"],
                        score["eig_se_nats"], score["utility_mean"],
                        score["top_selection_rate"],
                    )
                    if not isinstance(replicates, list) \
                            or len(replicates) != expected_replicates:
                        raise ValueError("benchmark v4 EIG replicate count is inconsistent")
                    if not isinstance(interval, list) or len(interval) != 2 \
                            or not all(_finite_number(value) for value in (*scalars, *interval, *replicates)):
                        raise ValueError("benchmark v4 EIG uncertainty must be finite")
                    if score["eig_sd_nats"] < 0.0 or score["eig_se_nats"] < 0.0 \
                            or not 0.0 <= score["top_selection_rate"] <= 1.0:
                        raise ValueError("benchmark v4 EIG uncertainty is outside its domain")
                identities = [score["design_identity"] for score in candidate_scores]
                if not all(isinstance(identity, str) for identity in identities) \
                        or len(identities) != len(set(identities)):
                    raise ValueError("benchmark v4 EIG ranking has invalid exact identities")
                if candidate_scores[0]["design_key"] != selected_key \
                        or candidate_scores[0]["design_identity"] != selected_identity:
                    raise ValueError("benchmark v4 EIG did not select its top-ranked design")
                utilities = [float(score["utility_mean"]) for score in candidate_scores]
                if any(left < right for left, right in zip(utilities, utilities[1:])):
                    raise ValueError("benchmark v4 EIG ranking is not utility-sorted")
                if not math.isclose(
                    sum(float(score["top_selection_rate"]) for score in candidate_scores),
                    1.0, rel_tol=1e-9, abs_tol=1e-9,
                ):
                    raise ValueError("benchmark v4 EIG top-selection rates must sum to one")
            elif policy_name in BENCHMARK_V4_COMPARATOR_METHODS:
                candidate_scores = acquisition.get("candidate_scores")
                if not isinstance(candidate_scores, list) or not candidate_scores:
                    raise ValueError("benchmark v4 comparator decision lacks ranking scores")
                required = {
                    "design_key", "design_identity", "channel", "method", "objective",
                    "score", "score_units", "utility", "noise_sigma",
                }
                identities: list[str] = []
                for score in candidate_scores:
                    if not isinstance(score, dict) or required - score.keys():
                        raise ValueError("benchmark v4 comparator score is incomplete")
                    if score["method"] != BENCHMARK_V4_COMPARATOR_METHODS[policy_name] \
                            or score["objective"] != expected_objective:
                        raise ValueError("benchmark v4 comparator score metadata mismatch")
                    if not all(_finite_number(score[key]) for key in ("score", "utility", "noise_sigma")) \
                            or score["score"] < 0.0 or score["utility"] < 0.0 \
                            or score["noise_sigma"] <= 0.0:
                        raise ValueError("benchmark v4 comparator score is outside its domain")
                    expected_units = (
                        "nats" if score["method"] == "laplace_d_opt"
                        else "dimensionless_ratio"
                    )
                    if not isinstance(score["design_identity"], str) \
                            or score["score_units"] != expected_units:
                        raise ValueError("benchmark v4 comparator score units/identity are invalid")
                    identities.append(score["design_identity"])
                if len(identities) != len(set(identities)):
                    raise ValueError("benchmark v4 comparator ranking contains duplicates")
                if candidate_scores[0]["design_key"] != selected_key \
                        or candidate_scores[0]["design_identity"] != acquisition.get("selected_identity"):
                    raise ValueError("benchmark v4 comparator did not select its top-ranked design")
                utilities = [float(score["utility"]) for score in candidate_scores]
                if any(left < right for left, right in zip(utilities, utilities[1:])):
                    raise ValueError("benchmark v4 comparator ranking is not utility-sorted")
            elif policy_name == "random_channel_balanced":
                if acquisition.get("seed_namespace") != "random_channel_balanced/v1" \
                        or isinstance(acquisition.get("seed"), bool) \
                        or not isinstance(acquisition.get("seed"), int):
                    raise ValueError("benchmark v4 random policy lacks its independent seed")
    if len(initial_selected) != 1:
        raise ValueError("benchmark v4 policies do not share the same initial observations")
    if len(initial_identities) != 1:
        raise ValueError("benchmark v4 policies do not share exact initial identities")


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
