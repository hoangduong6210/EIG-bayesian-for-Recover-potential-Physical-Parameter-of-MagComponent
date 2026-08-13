#!/usr/bin/env python3
"""Generate reusable posterior states for the EIG estimator-validation study."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import asdict
from pathlib import Path

import numpy as np

from eig_efficiency import fixed_channel_balanced_order
from magcore_calib.data import common_random_outcomes, default_library
from magcore_calib.eig import reveal
from magcore_calib.inference import sample_emcee
from magcore_calib.models import Geometry
from magcore_calib.prior import DatasheetPrior, draw_prior_predictive
from magcore_calib.results import provenance
from magcore_calib.runtime import require_slurm
from magcore_calib.study_plan import load_study_plan

SCHEMA = "eig-convergence-state/1.0"


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


def _atomic_samples(path: Path, samples: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp-write")
    with temporary.open("wb") as handle:
        np.savez_compressed(handle, samples=np.asarray(samples, dtype=np.float64))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--n-observations", type=int, required=True)
    parser.add_argument("--n-walkers", type=int, required=True)
    parser.add_argument("--n-steps", type=int, required=True)
    parser.add_argument("--burn", type=int, required=True)
    parser.add_argument("--samples-out", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    require_slurm()

    plan = load_study_plan(Path.cwd())
    if args.seed not in plan.validation_state_seeds:
        parser.error("seed is outside the prespecified validation state-seed set")
    if args.n_observations not in plan.validation_observation_counts:
        parser.error("n-observations is outside the prespecified validation state grid")

    spec, geometry = DatasheetPrior(), Geometry()
    truth = draw_prior_predictive(spec, np.random.default_rng(args.seed))
    library = default_library(25.0)
    outcomes = common_random_outcomes(
        truth, library, seed=args.seed + 1_000_003, geometry=geometry,
    )
    observed_designs = fixed_channel_balanced_order(library)[:args.n_observations]
    observations = [reveal(outcomes, point) for point in observed_designs]
    fit = sample_emcee(
        observations, spec, geometry, n_walkers=args.n_walkers,
        n_steps=args.n_steps, burn=args.burn, seed=args.seed * 1000 + args.n_observations,
    )
    if fit.samples.shape[1:] != (6,) or not np.all(np.isfinite(fit.samples)):
        raise RuntimeError(
            "estimator-validation state contains malformed or nonfinite samples"
        )
    _atomic_samples(args.samples_out, fit.samples)

    record = {
        "schema_version": SCHEMA,
        "case_study": "magnetic_core",
        "provenance": provenance(seed=args.seed),
        "state": {
            "seed": args.seed,
            "n_observations": args.n_observations,
            "observed_design_keys": [point.key() for point in observed_designs],
            "truth": asdict(truth),
            "common_random_outcomes": True,
            "candidate_temperature_c": 25.0,
        },
        "sampler": {
            "n_walkers": args.n_walkers,
            "n_steps": args.n_steps,
            "burn": args.burn,
            "diagnostics": fit.diagnostics,
        },
        "posterior_samples": {
            "path": str(args.samples_out),
            "sha256": _sha256(args.samples_out),
            "shape": list(fit.samples.shape),
            "dtype": str(fit.samples.dtype),
        },
        "validity": {
            "finite_samples": True,
            "sampler_convergence_valid": bool(fit.diagnostics.get("valid", False)),
            "valid": bool(fit.diagnostics.get("valid", False)),
        },
    }
    _atomic_json(args.out, record)
    print(args.out)


if __name__ == "__main__":
    main()
