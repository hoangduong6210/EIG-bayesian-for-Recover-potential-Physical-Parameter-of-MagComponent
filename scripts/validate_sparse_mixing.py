#!/usr/bin/env python3
"""Build the complete endpoint-free SparseMix-1 diagnostic manifest."""

from __future__ import annotations

import argparse
import itertools
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from magcore_calib.sparse_mixing import (
    PARAMETER_NAMES,
    SPARSE_MIXING_MANIFEST_SCHEMA,
    SparseMixingPlan,
    load_sparse_mixing_plan,
    sha256_file,
    validate_sparse_mixing_result,
    write_json_create_only,
)


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _close(left: float, right: float, *, rtol: float, atol: float) -> bool:
    return math.isclose(float(left), float(right), rel_tol=rtol, abs_tol=atol)


def _verify_exact_replay(record: dict, sidecar_state: dict,
                         plan: SparseMixingPlan) -> None:
    observed = record["final_diagnostics"]["sampler_diagnostics"]
    expected = sidecar_state["sampler_diagnostics"]
    settings = plan.raw["diagnostics"]
    rtol = settings["exact_replay_numeric_rtol"]
    atol = settings["exact_replay_numeric_atol"]
    for key in ("acceptance_fraction", "finite_log_probability_fraction"):
        if not _close(observed[key], expected[key], rtol=rtol, atol=atol):
            raise ValueError(f"exact replay differs for {key}")
    for group in ("tau", "ess", "steps_per_tau"):
        for name in PARAMETER_NAMES:
            if not _close(
                observed[group][name], expected[group][name],
                rtol=rtol, atol=atol,
            ):
                raise ValueError(f"exact replay differs for {group}.{name}")


def _target_classification(records: list[dict], plan: SparseMixingPlan) -> dict:
    diagnostic = plan.raw["diagnostics"]
    independent = [record for record in records if not record["task"]["exact_replay"]]
    reasons: list[str] = []
    for record in independent:
        final = record["checkpoints"][-1]
        if final["finite_log_probability_fraction"] != 1.0:
            reasons.append(f"{record['task']['task_id']}:nonfinite_log_probability")
        acceptance = final["acceptance_fraction"]
        lower, upper = diagnostic["acceptance_range"]
        if not lower <= acceptance <= upper:
            reasons.append(f"{record['task']['task_id']}:acceptance_outside_range")
        if any(final["steps_per_tau"][name] is None
               or final["steps_per_tau"][name] < diagnostic["minimum_steps_per_tau"]
               for name in PARAMETER_NAMES):
            reasons.append(f"{record['task']['task_id']}:steps_per_tau")
        if any(final["ess"][name] is None
               or final["ess"][name] < diagnostic["minimum_effective_sample_size"]
               for name in PARAMETER_NAMES):
            reasons.append(f"{record['task']['task_id']}:effective_sample_size")
        checkpoints = {row["retained_steps"]: row for row in record["checkpoints"]}
        earlier, later = diagnostic["tau_stability_checkpoints"]
        for name in PARAMETER_NAMES:
            tau_earlier = checkpoints[earlier]["tau"][name]
            tau_later = checkpoints[later]["tau"][name]
            if tau_earlier is None or tau_later is None or tau_later <= 0.0 \
                    or abs(tau_later - tau_earlier) / tau_later \
                    > diagnostic["maximum_relative_tau_change"]:
                reasons.append(f"{record['task']['task_id']}:tau_instability:{name}")

    maximum_median_ratio = 0.0
    maximum_tail_ratio = 0.0
    for left, right in itertools.combinations(independent, 2):
        left_summary = left["final_diagnostics"]["parameter_summary"]
        right_summary = right["final_diagnostics"]["parameter_summary"]
        left_diag = left["checkpoints"][-1]
        right_diag = right["checkpoints"][-1]
        for name in PARAMETER_NAMES:
            pooled_sd = math.sqrt(
                (left_summary[name]["sd"] ** 2 + right_summary[name]["sd"] ** 2) / 2.0
            )
            pooled_iqr = (
                left_summary[name]["iqr"] + right_summary[name]["iqr"]
            ) / 2.0
            median_difference = abs(
                left_summary[name]["median"] - right_summary[name]["median"]
            )
            mcse = math.sqrt(
                left_summary[name]["sd"] ** 2 / left_diag["ess"][name]
                + right_summary[name]["sd"] ** 2 / right_diag["ess"][name]
            )
            allowed_median = max(
                2.0 * mcse,
                diagnostic["maximum_median_difference_pooled_sd"] * pooled_sd,
            )
            if allowed_median > 0.0:
                maximum_median_ratio = max(
                    maximum_median_ratio, median_difference / allowed_median
                )
            tail_difference = max(
                abs(left_summary[name]["quantile_05"]
                    - right_summary[name]["quantile_05"]),
                abs(left_summary[name]["quantile_95"]
                    - right_summary[name]["quantile_95"]),
            )
            allowed_tail = diagnostic["maximum_tail_difference_pooled_iqr"] * pooled_iqr
            if allowed_tail > 0.0:
                maximum_tail_ratio = max(
                    maximum_tail_ratio, tail_difference / allowed_tail
                )
    if maximum_median_ratio > 1.0:
        reasons.append("cross_ensemble_median_separation")
    if maximum_tail_ratio > 1.0:
        reasons.append("cross_ensemble_tail_separation")
    return {
        "classification": "mixing_supported" if not reasons else "mixing_not_supported",
        "criteria_passed": not reasons,
        "reason_codes": sorted(set(reasons)),
        "maximum_normalized_median_difference": maximum_median_ratio,
        "maximum_normalized_tail_difference": maximum_tail_ratio,
        "independent_ensemble_count": len(independent),
    }


def build_sparse_mixing_manifest(plan: SparseMixingPlan, results_root: Path,
                                 rejection_path: Path) -> dict:
    rejection = _load_json(rejection_path)
    if sha256_file(rejection_path) != plan.raw["parent"]["rejection_sha256"]:
        raise ValueError("locked MM-2 rejection digest mismatch")
    sidecar_by_state = {
        state["state_identity_sha256"]: state
        for states in rejection["failed_states"].values()
        for state in states
    }
    records: list[dict] = []
    artifacts: list[dict] = []
    for task in plan.tasks():
        result_path = results_root / task.task_id / "result.json"
        if not result_path.is_file():
            raise FileNotFoundError(f"missing SparseMix-1 result: {task.task_id}")
        record = _load_json(result_path)
        validate_sparse_mixing_result(record, plan)
        if record["task"] != {
            "index": task.index, "task_id": task.task_id,
            "target_id": task.target.target_id,
            "initialization": task.initialization,
            "replicate": task.replicate, "seed": task.seed,
            "exact_replay": task.exact_replay,
        }:
            raise ValueError(f"SparseMix-1 task identity mismatch: {task.task_id}")
        if record["parent"] != {
            "campaign_id": plan.raw["parent"]["campaign_id"],
            "run_id": plan.raw["parent"]["run_id"],
            "source_revision": plan.raw["parent"]["source_revision"],
            "source_archive_sha256": plan.raw["parent"]["source_archive_sha256"],
            "config_sha256": plan.raw["parent"]["config_sha256"],
            "rejection_sha256": plan.raw["parent"]["rejection_sha256"],
            "closeout_sha256": plan.raw["parent"]["closeout_sha256"],
        }:
            raise ValueError(f"SparseMix-1 parent identity mismatch: {task.task_id}")
        reconstruction = record["reconstruction"]
        if reconstruction.get("state_identity_sha256") \
                != task.target.state_identity_sha256 \
                or reconstruction.get("observation_count") \
                != task.target.n_measurements \
                or reconstruction.get("mcmc_seed") \
                != task.target.original_mcmc_seed \
                or reconstruction.get("observation_manifest_sha256") \
                != task.target.observation_manifest_sha256:
            raise ValueError(f"SparseMix-1 reconstruction mismatch: {task.task_id}")
        thin_name = record["thin"]["path"]
        if Path(thin_name).name != thin_name:
            raise ValueError(f"SparseMix-1 thin path is unsafe: {task.task_id}")
        thin_path = result_path.parent / record["thin"]["path"]
        if not thin_path.is_file() \
                or sha256_file(thin_path) != record["thin"]["sha256"]:
            raise ValueError(f"SparseMix-1 thin digest mismatch: {task.task_id}")
        with np.load(thin_path, allow_pickle=False) as archive:
            if set(archive.files) != {"chain"} \
                    or archive["chain"].dtype != np.float64 \
                    or list(archive["chain"].shape) != record["thin"]["shape"]:
                raise ValueError(f"SparseMix-1 thin content mismatch: {task.task_id}")
        if record["thin"]["stride"] != plan.raw["sampler"]["thin_stride"] \
                or record["sampler"]["retained_steps"] != task.retained_steps \
                or [row["retained_steps"] for row in record["checkpoints"]] \
                != list(task.checkpoints) \
                or len(record["chain_block_sha256"]) != len(task.checkpoints):
            raise ValueError(f"SparseMix-1 sampler contract mismatch: {task.task_id}")
        if task.exact_replay:
            _verify_exact_replay(
                record, sidecar_by_state[task.target.state_identity_sha256], plan
            )
        records.append(record)
        artifacts.append({
            "task_id": task.task_id,
            "result_path": f"{task.task_id}/result.json",
            "result_sha256": sha256_file(result_path),
            "thin_path": f"{task.task_id}/{thin_path.name}",
            "thin_sha256": sha256_file(thin_path),
        })
    classifications = {}
    for target in plan.targets:
        target_records = [
            record for record in records
            if record["task"]["target_id"] == target.target_id
        ]
        classifications[target.target_id] = _target_classification(
            target_records, plan
        )
    return {
        "schema_version": SPARSE_MIXING_MANIFEST_SCHEMA,
        "record_class": "endpoint_free_sampler_diagnostic_manifest",
        "protocol_id": plan.protocol_id,
        "config_sha256": plan.config_sha256,
        "parent": {
            "campaign_id": "MM-2",
            "rejection_sha256": plan.raw["parent"]["rejection_sha256"],
            "closeout_sha256": plan.raw["parent"]["closeout_sha256"],
            "retroactive_admission_allowed": False,
        },
        "matrix": {
            "expected_task_count": plan.task_count,
            "validated_task_count": len(records),
            "artifact_count": len(artifacts) * 2,
        },
        "classifications": classifications,
        "artifacts": artifacts,
        "disclosure": {
            "claim_bearing_result": False,
            "scientific_endpoints_included": False,
            "mm2_admission_changed": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--results-root", required=True, type=Path)
    parser.add_argument("--rejection", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    plan = load_sparse_mixing_plan(args.config)
    manifest = build_sparse_mixing_manifest(
        plan, args.results_root, args.rejection
    )
    write_json_create_only(args.out, manifest)


if __name__ == "__main__":
    main()
