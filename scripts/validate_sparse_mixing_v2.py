#!/usr/bin/env python3
"""Verify full retained chains against prospective SparseMix-2 criteria."""

from __future__ import annotations

import argparse
import itertools
import math
import re
from pathlib import Path

import numpy as np

from experiments.sparse_mixing_v2 import _parameter_summary, load_config, move_parameters, tasks
from magcore_calib.diagnostics import diagnostic_report
from magcore_calib.runtime import require_slurm
from magcore_calib.sparse_mixing import PARAMETER_NAMES, load_sparse_mixing_plan, payload_sha256, sha256_file, write_json_create_only
from scripts.validate_sparse_pilot import _equal_numeric, _json, _reject_forbidden_keys


def validate_criteria(criteria: dict, checkpoints: list[int]) -> None:
    if criteria.get("minimum_finite_log_probability_fraction") != 1.0:
        raise ValueError("SparseMix-2 requires finite log density for every retained draw")
    for key in ("minimum_steps_per_tau", "minimum_effective_sample_size",
                "maximum_relative_tau_change", "maximum_median_difference_pooled_sd",
                "maximum_tail_difference_pooled_iqr"):
        value = criteria.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"SparseMix-2 diagnostic threshold malformed: {key}")
    acceptance = criteria.get("acceptance_range")
    if not isinstance(acceptance, list) or len(acceptance) != 2 \
            or any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in acceptance) \
            or not 0 <= acceptance[0] < acceptance[1] <= 1:
        raise ValueError("SparseMix-2 acceptance bounds malformed")
    stability = criteria.get("tau_stability_checkpoints")
    if not isinstance(stability, list) or len(stability) != 2 \
            or any(type(v) is not int or v not in checkpoints for v in stability) \
            or not stability[0] < stability[1] or stability[1] != checkpoints[-1]:
        raise ValueError("SparseMix-2 stability checkpoints malformed")


def classify_state(rows: list[dict], criteria: dict, expected_count: int = 8) -> dict:
    """Apply the registered rule; missing diagnostics always fail closed."""
    reasons = []
    if len(rows) != expected_count or len({r["task_id"] for r in rows}) != expected_count:
        reasons.append("incomplete_independent_ensemble_matrix")
    for row in rows:
        label, final = row["task_id"], row["diagnostics"]
        finite = final.get("finite_log_probability_fraction")
        if finite != criteria["minimum_finite_log_probability_fraction"]:
            reasons.append(f"{label}:nonfinite_log_probability")
        acceptance = final.get("acceptance_fraction")
        lower, upper = criteria["acceptance_range"]
        if not isinstance(acceptance, (int, float)) or not lower <= acceptance <= upper:
            reasons.append(f"{label}:acceptance_sanity")
        for group, minimum in (
            ("steps_per_tau", criteria["minimum_steps_per_tau"]),
            ("ess", criteria["minimum_effective_sample_size"]),
        ):
            for name in PARAMETER_NAMES:
                value = final.get(group, {}).get(name)
                if value is None or not math.isfinite(value) or value < minimum:
                    reasons.append(f"{label}:{group}:{name}")
        for name in PARAMETER_NAMES:
            change = row["relative_tau_change"].get(name)
            if change is None or not math.isfinite(change) or change > criteria["maximum_relative_tau_change"]:
                reasons.append(f"{label}:tau_instability:{name}")
    median_ratios, tail_ratios = [], []
    for left, right in itertools.combinations(rows, 2):
        for name in PARAMETER_NAMES:
            label = f"{left['task_id']}:{right['task_id']}:{name}"
            ls, rs = left["parameter_summary"][name], right["parameter_summary"][name]
            le, re = left["diagnostics"]["ess"][name], right["diagnostics"]["ess"][name]
            if le is None or re is None or not np.all(np.isfinite([le, re])) or min(le, re) <= 0:
                reasons.append(f"{label}:undefined_comparison")
                continue
            sd = math.sqrt((ls["sd"] ** 2 + rs["sd"] ** 2) / 2)
            mcse = math.sqrt(ls["sd"] ** 2 / le + rs["sd"] ** 2 / re)
            median_scale = max(2 * mcse, criteria["maximum_median_difference_pooled_sd"] * sd)
            tail_scale = criteria["maximum_tail_difference_pooled_iqr"] * (ls["iqr"] + rs["iqr"]) / 2
            if not np.all(np.isfinite([median_scale, tail_scale])) or min(median_scale, tail_scale) <= 0:
                reasons.append(f"{label}:undefined_comparison")
                continue
            median_ratio = abs(ls["median"] - rs["median"]) / median_scale
            tail_ratio = max(abs(ls[q] - rs[q]) for q in ("quantile_05", "quantile_95")) / tail_scale
            median_ratios.append(median_ratio)
            tail_ratios.append(tail_ratio)
            if not math.isfinite(median_ratio) or median_ratio > 1:
                reasons.append(f"{label}:median_separation")
            if not math.isfinite(tail_ratio) or tail_ratio > 1:
                reasons.append(f"{label}:tail_separation")
    return {
        "criteria_passed": not reasons,
        "classification": "mixing_supported" if not reasons else "mixing_not_supported",
        "reason_codes": sorted(set(reasons)), "independent_ensemble_count": len(rows),
        "maximum_normalized_median_difference": max(median_ratios) if median_ratios else None,
        "maximum_normalized_tail_difference": max(tail_ratios) if tail_ratios else None,
        "comparison_count": len(median_ratios),
    }


def validate_task(config: dict, task: dict, target, root: Path) -> tuple[dict, dict]:
    """Reuse pilot numeric comparison rules while checking the v2 schema directly."""
    import emcee

    directory = root / str(task["index"])
    result_path = directory / f"{task['task_id']}.json"
    chain_path = directory / f"{task['task_id']}.chain.npz"
    success_path = directory / f"{task['task_id']}.SUCCESS.json"
    record, success = _json(result_path), _json(success_path)
    parent = load_sparse_mixing_plan(config["_parent_path"])
    _reject_forbidden_keys(record, parent.raw["outputs"]["forbidden_key_fragments"])
    for field, expected in {
        "schema_version": "magcore-sparse-mixing-v2-result/1.0",
        "record_class": "endpoint_free_confirmatory_sampler_validation",
        "protocol_id": config["protocol_id"], "config_sha256": config["_config_sha256"],
        "parent_config_sha256": config["parent_config_sha256"], "task": task,
        "pilot_decision_sha256": config["pilot_decision_sha256"],
        "pilot_manifest_sha256": config["_pilot_manifest_sha256"],
        "disclosure": {"claim_bearing_result": False, "scientific_endpoints_included": False,
                       "retroactive_mm2_admission_allowed": False, "confirmatory_sampler_validation": True},
    }.items():
        if record.get(field) != expected:
            raise ValueError(f"SparseMix-2 identity mismatch: {field}")
    for field, expected in {
        "state_identity_sha256": target.state_identity_sha256,
        "observation_manifest_sha256": target.observation_manifest_sha256,
        "observation_count": target.n_measurements,
    }.items():
        if record["reconstruction"].get(field) != expected:
            raise ValueError(f"SparseMix-2 reconstruction mismatch: {field}")
    density_coordinates = "alpha_cc_logit" if task["arm"] == "logit_stretch" else "original_active"
    for field, expected in {
        "implementation": "emcee.EnsembleSampler", "version": config["emcee_version"],
        "arm": task["arm"], "n_walkers": config["n_walkers"], "dimensions": 6,
        "warmup_steps": config["warmup"], "retained_steps": config["retained"],
        "early_stopping": False, "vectorize": True,
        "diagnostic_coordinates": list(PARAMETER_NAMES), "density_coordinates": density_coordinates,
        "acceptance_window": "retained_only", "move_parameters": move_parameters(task["arm"]),
    }.items():
        if record["sampler"].get(field) != expected:
            raise ValueError(f"SparseMix-2 sampler mismatch: {field}")
    parity = record.get("density_parity", {})
    if set(parity) != {"initial", "final"}:
        raise ValueError("SparseMix-2 density parity checkpoints differ")
    for report in parity.values():
        if report.get("rows") != config["n_walkers"] or report.get("rtol") != 1e-11 or report.get("atol") != 1e-8:
            raise ValueError("SparseMix-2 density parity contract differs")
        difference = report.get("maximum_absolute_difference")
        if not isinstance(difference, (int, float)) or not math.isfinite(difference) or difference < 0:
            raise ValueError("SparseMix-2 density parity record malformed")
    result_hash, chain_hash = sha256_file(result_path), sha256_file(chain_path)
    if success != {"task_id": task["task_id"], "record_sha256": result_hash, "chain_sha256": chain_hash}:
        raise ValueError("SparseMix-2 success marker mismatch")
    shape = [config["retained"], config["n_walkers"], 6]
    if record["chain"] != {
        "path": chain_path.name, "sha256": chain_hash, "shape": shape,
        "coordinates": list(PARAMETER_NAMES), "log_probability_coordinates": density_coordinates,
    }:
        raise ValueError("SparseMix-2 chain descriptor mismatch")
    with np.load(chain_path, allow_pickle=False) as archive:
        if set(archive.files) != {"chain", "log_probability", "initial"}:
            raise ValueError("SparseMix-2 chain archive members differ")
        arrays = {name: archive[name] for name in archive.files}
    for name, expected in (("chain", shape), ("log_probability", shape[:2]), ("initial", shape[1:])):
        array = arrays[name]
        if array.dtype != np.float64 or list(array.shape) != expected or not np.all(np.isfinite(array)):
            raise ValueError(f"SparseMix-2 array malformed: {name}")
    initial_hash = payload_sha256([[float(value).hex() for value in row] for row in arrays["initial"]])
    if initial_hash != record["reconstruction"]["initial_ensemble_sha256"]:
        raise ValueError("SparseMix-2 initial ensemble digest mismatch")
    chain, checkpoints = arrays["chain"], record["checkpoints"]
    if [r["retained_steps"] for r in checkpoints] != config["checkpoints"]:
        raise ValueError("SparseMix-2 checkpoint matrix differs")
    for checkpoint in checkpoints:
        n, acceptance = checkpoint["retained_steps"], checkpoint["acceptance_fraction"]
        if not isinstance(acceptance, (float, int)) or not 0 <= acceptance <= 1:
            raise ValueError("SparseMix-2 acceptance fraction malformed")
        try:
            tau = emcee.autocorr.integrated_time(chain[:n], tol=0)
        except emcee.autocorr.AutocorrError:
            tau = np.full(6, np.nan)
        # Retain the sampler's legacy report; the prospective decision below
        # applies the registered criteria rather than its legacy valid flag.
        recomputed = diagnostic_report(chain[:n], np.array([acceptance]), tau)
        recomputed.update(retained_steps=n, finite_log_probability_fraction=1.0)
        _equal_numeric(checkpoint, recomputed, "checkpoint")
    _equal_numeric(record["final_diagnostics"]["sampler_diagnostics"], checkpoints[-1], "final")
    summary = _parameter_summary(chain)
    _equal_numeric(record["final_diagnostics"]["parameter_summary"], summary, "summary")
    by_steps = {r["retained_steps"]: r for r in checkpoints}
    earlier, later = (by_steps[n] for n in config["diagnostics"]["tau_stability_checkpoints"])
    tau_change = {}
    for name in PARAMETER_NAMES:
        a, b = earlier["tau"][name], later["tau"][name]
        tau_change[name] = abs(b - a) / b if a is not None and b is not None and b > 0 else None
    row = {
        "task_id": task["task_id"], "target_id": task["target_id"],
        "initialization": task["initialization"], "replicate": task["replicate"],
        "diagnostics": checkpoints[-1], "parameter_summary": summary,
        "relative_tau_change": tau_change, "initial_ensemble_sha256": initial_hash,
    }
    artifact = {"task_id": task["task_id"]}
    verified_hashes = {"result": result_hash, "chain": chain_hash,
                       "success": sha256_file(success_path)}
    for name, path in (("result", result_path), ("chain", chain_path), ("success", success_path)):
        artifact[f"{name}_path"] = path.relative_to(root).as_posix()
        artifact[f"{name}_sha256"] = verified_hashes[name]
    return row, artifact


def build_manifest(config: dict, root: Path, *, run_id: str, validator_revision: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", validator_revision) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", run_id):
        raise ValueError("SparseMix-2 manifest source identity is malformed")
    validate_criteria(config["diagnostics"], config["checkpoints"])
    matrix = tasks(config)
    parent = load_sparse_mixing_plan(config["_parent_path"])
    entries = list(root.rglob("*"))
    if root.is_symlink() or any(p.is_symlink() for p in entries):
        raise ValueError("SparseMix-2 artifact matrix contains a symbolic link")
    expected = {f"{t['index']}/{t['task_id']}{suffix}" for t in matrix for suffix in (".json", ".chain.npz", ".SUCCESS.json")}
    if {p.relative_to(root).as_posix() for p in entries if p.is_file()} != expected:
        raise ValueError("SparseMix-2 artifact matrix is incomplete or contains unexpected files")
    rows, artifacts = [], []
    for task in matrix:
        target = next(t for t in parent.targets if t.target_id == task["target_id"])
        row, artifact = validate_task(config, task, target, root)
        rows.append(row)
        artifacts.append(artifact)
    classifications = {
        target.target_id: classify_state(
            [r for r in rows if r["target_id"] == target.target_id], config["diagnostics"],
            expected_count=len(config["families"]) * config["replicates"],
        ) for target in parent.targets
    }
    return {
        "schema_version": "magcore-sparse-mixing-v2-manifest/1.0",
        "record_class": "endpoint_free_confirmatory_sampler_validation_manifest",
        "protocol_id": config["protocol_id"], "run_id": run_id,
        "validator_revision": validator_revision, "validator_source_sha256": sha256_file(__file__),
        "config_sha256": config["_config_sha256"], "parent_config_sha256": parent.config_sha256,
        "pilot_decision_sha256": config["pilot_decision_sha256"], "pilot_manifest_sha256": config["_pilot_manifest_sha256"],
        "matrix": {"expected_task_count": len(matrix), "validated_task_count": len(rows), "artifact_count": len(artifacts) * 3},
        "registered_criteria": config["diagnostics"], "classifications": classifications,
        "both_states_pass": set(classifications) == {"n3", "n4"} and all(r["criteria_passed"] for r in classifications.values()),
        "tasks": rows, "artifacts": artifacts,
        "verification": {"all_checkpoint_tau_ess_and_parameter_summaries_recomputed": True,
                         "acceptance_recomputed": False, "density_parity_recomputed": False,
                         "numeric_rtol": 1e-9, "numeric_atol": 1e-11},
        "disclosure": {"scientific_endpoints_included": False, "retroactive_mm2_admission_allowed": False,
                       "confirmatory_sampler_validation": True, "model_mismatch_campaign_admitted": False},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--validator-revision", required=True)
    args = parser.parse_args()
    require_slurm()
    manifest = build_manifest(load_config(args.config), args.results_root,
                              run_id=args.run_id, validator_revision=args.validator_revision)
    write_json_create_only(args.out, manifest)


if __name__ == "__main__":
    main()
