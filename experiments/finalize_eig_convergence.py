#!/usr/bin/env python3
"""Finalize estimator validation with downstream fail-closed endpoint gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from magcore_calib.results import provenance
from magcore_calib.runtime import require_slurm
from magcore_calib.study_plan import load_study_plan

SELECTION_SCHEMA = "eig-convergence-selection/1.0"
DOWNSTREAM_SCHEMA = "eig-convergence-downstream/1.0"
SCHEMA = "eig-convergence-final/1.0"


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


def _records(run_dir: Path, schema: str) -> list[tuple[Path, dict]]:
    found = []
    for path in sorted(run_dir.rglob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if record.get("schema_version") == schema:
            found.append((path, record))
    return found


def _endpoint(record: dict, objective: str, role: str) -> float | None:
    result = record["objectives"][objective][role]["result"]
    key = "n_measurements_to_gate" if objective == "raw" else "modeled_cost_to_gate"
    value = result.get(key)
    return None if value is None else float(value)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    require_slurm()
    plan = load_study_plan(args.run_dir)

    selections = _records(args.run_dir, SELECTION_SCHEMA)
    if len(selections) != 1:
        raise ValueError(f"expected exactly one static selection, found {len(selections)}")
    selection_path, selection = selections[0]
    if selection.get("validity", {}).get("valid") is not True:
        raise ValueError("static selection is invalid")
    selection_sha256 = _sha256(selection_path)

    downstream_by_seed: dict[int, tuple[Path, dict]] = {}
    for path, record in _records(args.run_dir, DOWNSTREAM_SCHEMA):
        seed = int(record["seed"])
        if seed in downstream_by_seed:
            raise ValueError(f"duplicate downstream seed {seed}")
        if record.get("selection", {}).get("sha256") != selection_sha256:
            raise ValueError(f"downstream record is bound to another selection: {path}")
        downstream_by_seed[seed] = (path, record)
    expected = set(plan.downstream_validation_seeds)
    if set(downstream_by_seed) != expected:
        raise ValueError(
            f"downstream seed set mismatch: missing={sorted(expected - set(downstream_by_seed))}, "
            f"unexpected={sorted(set(downstream_by_seed) - expected)}"
        )

    objective_reports = {}
    reference_downstream_passed = True
    for objective in ("raw", "per_cost"):
        rows = []
        for seed in plan.downstream_validation_seeds:
            path, record = downstream_by_seed[seed]
            selected_value = _endpoint(record, objective, "selected")
            reference_value = _endpoint(record, objective, "reference")
            selected_branch = record["objectives"][objective]["selected"]
            reference_branch = record["objectives"][objective]["reference"]
            selected_valid = bool(
                selected_branch["result"].get("reached")
                and selected_branch["sampler_diagnostics"].get("valid", False)
            )
            reference_valid = bool(
                reference_branch["result"].get("reached")
                and reference_branch["sampler_diagnostics"].get("valid", False)
            )
            reference_downstream_passed = reference_downstream_passed and reference_valid
            difference = (
                None if selected_value is None or reference_value is None
                else selected_value - reference_value
            )
            endpoint_stable = bool(
                selected_valid and reference_valid and difference is not None
                and abs(difference) <= plan.thresholds.endpoint_atol
            )
            rows.append({
                "seed": seed,
                "path": str(path),
                "sha256": _sha256(path),
                "selected_endpoint": selected_value,
                "reference_endpoint": reference_value,
                "selected_minus_reference": difference,
                "selected_valid": selected_valid,
                "reference_valid": reference_valid,
                "endpoint_stable": endpoint_stable,
            })
        objective_reports[objective] = {
            "endpoint": (
                "measurement_count_to_gate" if objective == "raw"
                else "modeled_cost_to_gate"
            ),
            "atol": plan.thresholds.endpoint_atol,
            "all_seeds_stable": all(row["endpoint_stable"] for row in rows),
            "seed_comparisons": rows,
        }

    reference_audit_passed = selection.get("reference_audit", {}).get("passed") is True
    if not reference_audit_passed:
        raise RuntimeError(
            "reference audit failed; no estimator decision can be released"
        )
    downstream_candidate_passed = all(
        report["all_seeds_stable"] for report in objective_reports.values()
    )
    if downstream_candidate_passed:
        final_setting = selection["selected_setting"]
        selection_mode = selection["selection_mode"]
    else:
        # This conservative fallback is prespecified: reference adequacy has
        # already passed the independent high-budget sentinel audit.
        final_setting = selection["reference_setting"]
        selection_mode = "reference_fallback"

    raw_claim_gate_passed = bool(reference_audit_passed and reference_downstream_passed and (
        downstream_candidate_passed or final_setting == selection["reference_setting"]
    ))
    per_cost_claim_gate_passed = raw_claim_gate_passed
    valid = bool(raw_claim_gate_passed and per_cost_claim_gate_passed)
    record = {
        "schema_version": SCHEMA,
        "case_study": "magnetic_core",
        "provenance": provenance(seed=plan.downstream_validation_seeds[0]),
        "selection_path": str(selection_path),
        "selection_sha256": selection_sha256,
        "candidate_selected_setting": selection["selected_setting"],
        "selected_setting": final_setting,
        "reference_setting": selection["reference_setting"],
        "selection_mode": selection_mode,
        "reference_audit_passed": reference_audit_passed,
        "reference_downstream_passed": reference_downstream_passed,
        "downstream_candidate_passed": downstream_candidate_passed,
        "objectives": objective_reports,
        "raw_claim_gate_passed": raw_claim_gate_passed,
        "per_cost_claim_gate_passed": per_cost_claim_gate_passed,
        "valid": valid,
    }
    if not valid:
        raise RuntimeError("estimator-validation final claim gate failed")
    _atomic_json(args.out, record)
    print(args.out)


if __name__ == "__main__":
    main()
