#!/usr/bin/env python3
"""Compare the statically selected and reference estimators downstream."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import numpy as np

from eig_efficiency import run_policy
from magcore_calib.data import common_random_outcomes, default_library
from magcore_calib.models import Geometry
from magcore_calib.prior import DatasheetPrior, draw_prior_predictive
from magcore_calib.results import provenance
from magcore_calib.runtime import require_slurm, sampling_pool
from magcore_calib.study_plan import load_study_plan

SCHEMA = "eig-convergence-downstream/1.0"


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


def _run_root(path: Path) -> Path:
    for candidate in (path.resolve(), *path.resolve().parents):
        if (candidate / "config" / "default.toml").is_file():
            return candidate
        if (candidate / "configs" / "default.toml").is_file():
            return candidate
    raise FileNotFoundError("cannot locate the frozen study config above selection path")


def _setting_tuple(setting: dict) -> tuple[int, int, int]:
    required = {"n_outer", "n_inner", "n_replicates"}
    if set(setting) != required:
        raise ValueError("estimator setting must contain exactly n_outer, n_inner, n_replicates")
    values = tuple(int(setting[key]) for key in ("n_outer", "n_inner", "n_replicates"))
    if any(value < 1 for value in values):
        raise ValueError("estimator setting values must be positive")
    return values


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument("--max-meas", type=int, required=True)
    parser.add_argument("--n-walkers", type=int, required=True)
    parser.add_argument("--n-steps", type=int, required=True)
    parser.add_argument("--burn", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    require_slurm()

    selection = json.loads(args.selection.read_text(encoding="utf-8"))
    if selection.get("schema_version") != "eig-convergence-selection/1.0":
        raise ValueError("selection has the wrong schema")
    if selection.get("validity", {}).get("valid") is not True:
        raise ValueError("static selection is invalid")
    if selection.get("reference_audit", {}).get("passed") is not True:
        raise ValueError("reference audit did not pass")
    plan = load_study_plan(_run_root(args.selection))
    if args.seed not in plan.downstream_validation_seeds:
        parser.error("seed is outside the prespecified downstream seed set")

    selected_setting = _setting_tuple(selection["selected_setting"])
    reference_setting = _setting_tuple(selection["reference_setting"])
    spec, geometry = DatasheetPrior(), Geometry()
    truth = draw_prior_predictive(spec, np.random.default_rng(args.seed))
    library = default_library(25.0)
    outcomes = common_random_outcomes(
        truth, library, seed=args.seed + 1_000_003, geometry=geometry,
    )

    def execute(setting: tuple[int, int, int], objective: str, pool) -> tuple[dict, dict]:
        result, _, diagnostics = run_policy(
            "eig", library, outcomes, spec, geometry, seed=args.seed,
            max_measurements=args.max_meas, n_walkers=args.n_walkers,
            n_steps=args.n_steps, burn=args.burn, n_outer=setting[0],
            n_inner=setting[1], eig_replicates=setting[2],
            objective=objective, pool=pool,
        )
        return result, diagnostics

    runs: dict[str, dict] = {}
    with sampling_pool(args.workers) as pool:
        for objective in ("raw", "per_cost"):
            selected_result, selected_diagnostics = execute(selected_setting, objective, pool)
            if selected_setting == reference_setting:
                reference_result = selected_result
                reference_diagnostics = selected_diagnostics
            else:
                reference_result, reference_diagnostics = execute(
                    reference_setting, objective, pool,
                )
            runs[objective] = {
                "selected": {
                    "result": selected_result,
                    "sampler_diagnostics": selected_diagnostics,
                },
                "reference": {
                    "result": reference_result,
                    "sampler_diagnostics": reference_diagnostics,
                },
            }

    all_reached = all(
        branch[role]["result"]["reached"]
        for branch in runs.values() for role in ("selected", "reference")
    )
    all_converged = all(
        branch[role]["sampler_diagnostics"].get("valid", False)
        for branch in runs.values() for role in ("selected", "reference")
    )
    reference_valid = all(
        branch["reference"]["result"]["reached"]
        and branch["reference"]["sampler_diagnostics"].get("valid", False)
        for branch in runs.values()
    )
    record = {
        "schema_version": SCHEMA,
        "case_study": "magnetic_core",
        "provenance": provenance(seed=args.seed),
        "seed": args.seed,
        "selection": {
            "path": str(args.selection),
            "sha256": _sha256(args.selection),
            "selection_mode": selection["selection_mode"],
            "selected_setting": selection["selected_setting"],
            "reference_setting": selection["reference_setting"],
        },
        "sampler": {
            "n_walkers": args.n_walkers,
            "n_steps": args.n_steps,
            "burn": args.burn,
            "max_measurements": args.max_meas,
        },
        "objectives": runs,
        "validity": {
            "all_policies_reached_gate": all_reached,
            "all_sampler_diagnostics_valid": all_converged,
            "reference_reached_and_converged": reference_valid,
            # Candidate failure is an estimand, not a corrupt record. It is
            # adjudicated by finalize_eig_convergence and may trigger the
            # preregistered reference fallback.
            "valid": bool(reference_valid),
        },
    }
    _atomic_json(args.out, record)
    print(args.out)


if __name__ == "__main__":
    main()
