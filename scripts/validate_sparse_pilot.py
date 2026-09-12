#!/usr/bin/env python3
"""Recompute a complete SparseMix pilot record from retained chains."""

from __future__ import annotations

import argparse
import itertools
import json
import math
import re
from pathlib import Path
from typing import Any

import numpy as np

from experiments.sparse_mixing_pilot import _parameter_summary, load_config, tasks
from magcore_calib.diagnostics import diagnostic_report
from magcore_calib.runtime import require_slurm
from magcore_calib.sparse_mixing import (
    PARAMETER_NAMES, load_sparse_mixing_plan, payload_sha256, sha256_file,
    write_json_create_only,
)


def _equal_numeric(observed: Any, expected: Any, label: str) -> None:
    """Check persisted diagnostics without interpreting missing IAT as zero."""
    if isinstance(expected, dict):
        if not isinstance(observed, dict) or observed.keys() != expected.keys():
            raise ValueError(f"diagnostic keys differ: {label}")
        for key, value in expected.items():
            _equal_numeric(observed[key], value, f"{label}.{key}")
    elif isinstance(expected, (float, int)) and not isinstance(expected, bool):
        if isinstance(observed, bool) or not isinstance(observed, (float, int)) \
                or not math.isclose(observed, expected, rel_tol=1e-9, abs_tol=1e-11):
            raise ValueError(f"diagnostic value differs: {label}")
    elif observed != expected:
        raise ValueError(f"diagnostic value differs: {label}")


def _json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("artifact must contain a JSON object")
    return value


def _reject_forbidden_keys(value: Any, fragments: list[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if any(fragment.lower() in key.lower() for fragment in fragments):
                raise ValueError("pilot result contains a forbidden endpoint key")
            _reject_forbidden_keys(item, fragments)
    elif isinstance(value, list):
        for item in value:
            _reject_forbidden_keys(item, fragments)


def pairwise_summary(records: list[dict]) -> dict:
    """Descriptive legacy all-pair differences, with undefined scales explicit."""
    medians, tails = [], []
    undefined = []
    for left, right in itertools.combinations(records, 2):
        for name in PARAMETER_NAMES:
            ls, rs = left["parameter_summary"][name], right["parameter_summary"][name]
            le, re = left["diagnostics"]["ess"][name], right["diagnostics"]["ess"][name]
            if le is None or re is None or min(le, re) <= 0:
                undefined.append(f"{left['task_id']}:{right['task_id']}:{name}:ess")
                continue
            sd = math.sqrt((ls["sd"] ** 2 + rs["sd"] ** 2) / 2)
            mcse = math.sqrt(ls["sd"] ** 2 / le + rs["sd"] ** 2 / re)
            allowed_median = max(2 * mcse, 0.1 * sd)
            allowed_tail = 0.15 * (ls["iqr"] + rs["iqr"]) / 2
            if allowed_median <= 0 or allowed_tail <= 0:
                undefined.append(f"{left['task_id']}:{right['task_id']}:{name}:scale")
                continue
            medians.append(abs(ls["median"] - rs["median"]) / allowed_median)
            tails.append(max(abs(ls[q] - rs[q]) for q in ("quantile_05", "quantile_95")) / allowed_tail)
    return {
        "maximum_normalized_median_difference": max(medians) if medians else None,
        "maximum_normalized_tail_difference": max(tails) if tails else None,
        "undefined_comparisons": undefined,
        "comparison_count": len(medians),
    }


def validate_task(config: dict, task: dict, target: Any, root: Path) -> tuple[dict, dict]:
    import emcee

    directory = root / str(task["index"])
    result_path = directory / f"{task['task_id']}.json"
    chain_path = directory / f"{task['task_id']}.chain.npz"
    success_path = directory / f"{task['task_id']}.SUCCESS.json"
    record, success = _json(result_path), _json(success_path)
    parent_plan = load_sparse_mixing_plan(config["_parent_path"])
    _reject_forbidden_keys(record, parent_plan.raw["outputs"]["forbidden_key_fragments"])
    if record.get("schema_version") != "magcore-sparse-mixing-pilot-result/1.0" \
            or record.get("record_class") != "endpoint_free_sampler_pilot" \
            or record.get("protocol_id") != config["protocol_id"] \
            or record.get("config_sha256") != config["_config_sha256"] \
            or record.get("parent_config_sha256") != config["parent_config_sha256"] \
            or record.get("task") != task:
        raise ValueError(f"pilot identity mismatch: {task['task_id']}")
    expected_disclosure = {
        "claim_bearing_result": False, "scientific_endpoints_included": False,
        "retroactive_mm2_admission_allowed": False,
        "confirmatory_sampler_validation": False,
    }
    if record.get("disclosure") != expected_disclosure:
        raise ValueError("pilot disclosure mismatch")
    parity = record.get("density_parity", {})
    if set(parity) != {"initial", "final"}:
        raise ValueError("pilot density parity checkpoints differ")
    for report in parity.values():
        if report.get("rows") != 48 or report.get("rtol") != 1e-11 \
                or report.get("atol") != 1e-8:
            raise ValueError("pilot density parity contract differs")
        difference = report.get("maximum_absolute_difference")
        if not isinstance(difference, (int, float)) or not math.isfinite(difference) or difference < 0:
            raise ValueError("pilot density parity record malformed")
    reconstruction = record["reconstruction"]
    for field, expected in (
        ("state_identity_sha256", target.state_identity_sha256),
        ("observation_manifest_sha256", target.observation_manifest_sha256),
        ("observation_count", target.n_measurements),
    ):
        if reconstruction.get(field) != expected:
            raise ValueError(f"pilot reconstruction mismatch: {field}")
    transformed = task["arm"] == "logit_stretch"
    coordinates = "alpha_cc_logit" if transformed else "original_active"
    sampler = record["sampler"]
    for field, expected in {
        "implementation": "emcee.EnsembleSampler", "arm": task["arm"],
        "n_walkers": 48, "dimensions": 6, "warmup_steps": config["warmup"],
        "retained_steps": config["retained"], "early_stopping": False,
        "vectorize": True, "diagnostic_coordinates": list(PARAMETER_NAMES),
        "density_coordinates": coordinates, "acceptance_window": "retained_only",
    }.items():
        if sampler.get(field) != expected:
            raise ValueError(f"pilot sampler mismatch: {field}")
    result_hash, chain_hash = sha256_file(result_path), sha256_file(chain_path)
    if success != {"task_id": task["task_id"], "record_sha256": result_hash,
                   "chain_sha256": chain_hash}:
        raise ValueError("pilot success marker mismatch")
    shape = [config["retained"], 48, 6]
    if record["chain"] != {
        "path": chain_path.name, "sha256": chain_hash, "shape": shape,
        "coordinates": list(PARAMETER_NAMES), "log_probability_coordinates": coordinates,
    }:
        raise ValueError("pilot chain descriptor mismatch")
    with np.load(chain_path, allow_pickle=False) as archive:
        if set(archive.files) != {"chain", "log_probability", "initial"}:
            raise ValueError("pilot chain archive members differ")
        arrays = {name: archive[name] for name in archive.files}
    for name, expected in (("chain", shape), ("log_probability", shape[:2]), ("initial", [48, 6])):
        array = arrays[name]
        if array.dtype != np.float64 or list(array.shape) != expected or not np.all(np.isfinite(array)):
            raise ValueError(f"pilot chain array malformed: {name}")
    initial_hash = payload_sha256([[float(value).hex() for value in row] for row in arrays["initial"]])
    if reconstruction["initial_ensemble_sha256"] != initial_hash:
        raise ValueError("pilot initial ensemble digest mismatch")
    chain = arrays["chain"]
    checkpoints = record["checkpoints"]
    if [row["retained_steps"] for row in checkpoints] != config["checkpoints"]:
        raise ValueError("pilot checkpoint schedule mismatch")
    for checkpoint in checkpoints:
        n = checkpoint["retained_steps"]
        try:
            tau = emcee.autocorr.integrated_time(chain[:n], tol=0)
        except emcee.autocorr.AutocorrError:
            tau = np.full(6, np.nan)
        acceptance = checkpoint["acceptance_fraction"]
        if not isinstance(acceptance, (float, int)) or not 0 <= acceptance <= 1:
            raise ValueError("pilot acceptance fraction malformed")
        recalculated = diagnostic_report(chain[:n], np.array([acceptance]), tau)
        recalculated.update(retained_steps=n, finite_log_probability_fraction=1.0)
        _equal_numeric(checkpoint, recalculated, "checkpoint")
    _equal_numeric(record["final_diagnostics"]["sampler_diagnostics"], checkpoints[-1], "final")
    summary = _parameter_summary(chain)
    _equal_numeric(record["final_diagnostics"]["parameter_summary"], summary, "summary")
    tau_changes = {}
    for name in PARAMETER_NAMES:
        earlier, later = (row["tau"][name] for row in checkpoints[-2:])
        tau_changes[name] = abs(later - earlier) / later if earlier is not None and later is not None and later > 0 else None
    portable = {
        "task_id": task["task_id"], "target_id": task["target_id"], "arm": task["arm"],
        "initialization": task["initialization"], "replicate": task["replicate"],
        "initial_ensemble_sha256": initial_hash,
        "diagnostics": checkpoints[-1], "parameter_summary": summary,
        "relative_tau_change": tau_changes,
    }
    artifact = {
        "task_id": task["task_id"], "result_path": result_path.relative_to(root).as_posix(),
        "result_sha256": result_hash, "chain_path": chain_path.relative_to(root).as_posix(),
        "chain_sha256": chain_hash, "success_path": success_path.relative_to(root).as_posix(),
        "success_sha256": sha256_file(success_path),
    }
    return portable, artifact


def build_manifest(config: dict, root: Path, *, run_id: str, validator_revision: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", validator_revision):
        raise ValueError("validator revision must be a full Git commit hash")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", run_id):
        raise ValueError("run id must be a portable identifier")
    matrix = tasks(config)
    plan = load_sparse_mixing_plan(config["_parent_path"])
    expected_files = {f"{task['index']}/{task['task_id']}{suffix}" for task in matrix
                      for suffix in (".json", ".chain.npz", ".SUCCESS.json")}
    entries = list(root.rglob("*"))
    if root.is_symlink() or any(p.is_symlink() for p in entries):
        raise ValueError("pilot artifact matrix contains a symbolic link")
    actual_files = {p.relative_to(root).as_posix() for p in entries if p.is_file()}
    if actual_files != expected_files:
        raise ValueError("pilot artifact matrix is incomplete or contains unexpected files")
    rows, artifacts = [], []
    for task in matrix:
        target = next(t for t in plan.targets if t.target_id == task["target_id"])
        row, artifact = validate_task(config, task, target, root)
        rows.append(row)
        artifacts.append(artifact)
    # All arms start at the same physical ensemble within each state/family/replicate.
    paired_initials: dict[tuple, str] = {}
    for row in rows:
        key = (row["target_id"], row["initialization"], row["replicate"])
        if paired_initials.setdefault(key, row["initial_ensemble_sha256"]) != row["initial_ensemble_sha256"]:
            raise ValueError("pilot paired initial ensembles differ between arms")
    groups = {}
    for target in plan.targets:
        groups[target.target_id] = {}
        for arm in config["arms"]:
            selected = [r for r in rows if r["target_id"] == target.target_id and r["arm"] == arm]
            ratios = [v for r in selected for v in r["diagnostics"]["steps_per_tau"].values()]
            changes = [v for r in selected for v in r["relative_tau_change"].values()]
            groups[target.target_id][arm] = {
                "independent_ensemble_count": len(selected),
                "minimum_steps_per_tau": min(ratios) if all(v is not None for v in ratios) else None,
                "maximum_relative_tau_change": max(changes) if all(v is not None for v in changes) else None,
                **pairwise_summary(selected),
            }
    return {
        "schema_version": "magcore-sparse-mixing-pilot-manifest/1.0",
        "record_class": "endpoint_free_sampler_pilot_manifest", "protocol_id": config["protocol_id"],
        "run_id": run_id, "validator_revision": validator_revision,
        "config_sha256": config["_config_sha256"], "parent_config_sha256": plan.config_sha256,
        "validator_source_sha256": sha256_file(__file__),
        "matrix": {"expected_task_count": len(matrix), "validated_task_count": len(rows), "artifact_count": len(artifacts) * 3},
        "method_summaries": groups, "tasks": rows, "artifacts": artifacts,
        "verification": {"all_checkpoint_tau_ess_and_parameter_summaries_recomputed": True,
                         "acceptance_recomputed": False,
                         "density_parity_recomputed": False,
                         "acceptance_note": "Proposal acceptance fractions are checked for range and consistency; proposal histories are not stored.",
                         "numeric_rtol": 1e-9, "numeric_atol": 1e-11},
        "comparison_rules": {"median": "max(2 * pooled MCSE, 0.10 * pooled SD)",
                             "tail": "0.15 * pooled IQR", "tau_stability_checkpoints": config["checkpoints"][-2:]},
        "disclosure": {"claim_bearing_result": False, "scientific_endpoints_included": False,
                       "retroactive_mm2_admission_allowed": False, "confirmatory_sampler_validation": False,
                       "automatic_admission": False},
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
    write_json_create_only(args.out, build_manifest(
        load_config(args.config), args.results_root,
        run_id=args.run_id, validator_revision=args.validator_revision,
    ))


if __name__ == "__main__":
    main()
