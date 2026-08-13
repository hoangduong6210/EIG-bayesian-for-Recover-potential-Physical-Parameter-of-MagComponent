#!/usr/bin/env python3
"""Estimate one physical EIG score cell for estimator validation."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path

import numpy as np

from magcore_calib.data import default_library
from magcore_calib.eig import CHANNEL_COST_S, rank_candidates_with_uncertainty
from magcore_calib.models import Geometry
from magcore_calib.results import provenance
from magcore_calib.runtime import require_slurm
from magcore_calib.study_plan import load_study_plan

SCHEMA = "eig-convergence-score/1.0"


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--samples", type=Path, required=True)
    parser.add_argument("--n-outer", type=int, required=True)
    parser.add_argument("--n-inner", type=int, required=True)
    parser.add_argument("--replicates", type=int, required=True)
    parser.add_argument("--namespace", choices=("grid", "reference", "audit"), required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    require_slurm()

    state = json.loads(args.state.read_text(encoding="utf-8"))
    if state.get("schema_version") != "eig-convergence-state/1.0":
        raise ValueError("state has the wrong schema")
    if state.get("validity", {}).get("valid") is not True:
        raise ValueError("state failed its convergence or finite-sample gate")
    if _sha256(args.samples) != state["posterior_samples"]["sha256"]:
        raise ValueError("posterior sample checksum does not match the state record")
    with np.load(args.samples, allow_pickle=False) as archive:
        samples = np.asarray(archive["samples"], dtype=float)
    if list(samples.shape) != state["posterior_samples"]["shape"]:
        raise ValueError("posterior sample shape does not match the state record")

    plan = load_study_plan(Path.cwd())
    setting = (args.n_outer, args.n_inner, args.replicates)
    physical_grid = {
        (item.n_outer, item.n_inner, item.n_replicates)
        for item in plan.grid_score_settings
    }
    expected = {
        "grid": physical_grid,
        "reference": {(
            plan.reference.n_outer, plan.reference.n_inner,
            plan.reference.n_replicates,
        )},
        "audit": {(
            plan.audit.n_outer, plan.audit.n_inner, plan.audit.n_replicates,
        )},
    }[args.namespace]
    if setting not in expected:
        parser.error(f"setting {setting} is not prespecified for {args.namespace}")
    seed = int(state["state"]["seed"])
    n_observations = int(state["state"]["n_observations"])
    if args.namespace == "audit" and not (
        seed == plan.validation_state_seeds[0]
        and n_observations in (
            min(plan.validation_observation_counts),
            max(plan.validation_observation_counts),
        )
    ):
        parser.error("audit namespace is restricted to the prespecified sentinel states")

    observed = set(state["state"]["observed_design_keys"])
    candidates = [point for point in default_library(25.0) if point.key() not in observed]
    # Deliberately use one namespace-independent base seed. Together with the
    # prefix-nested estimator, this gives common random numbers across budgets.
    estimator_seed = seed * 100_000 + n_observations
    ranking = rank_candidates_with_uncertainty(
        candidates, samples, seed=estimator_seed, geometry=Geometry(),
        n_outer=args.n_outer, n_inner=args.n_inner,
        n_replicates=args.replicates, objective="raw",
    )
    rows = []
    for item in ranking:
        values = [float(value) for value in item.replicate_scores_nats]
        if len(values) != args.replicates or not all(math.isfinite(value) for value in values):
            raise RuntimeError("EIG estimator returned incomplete or nonfinite scores")
        rows.append({
            "design_key": item.design.key(),
            "channel": item.design.channel.value,
            "channel_cost_units": CHANNEL_COST_S[item.design.channel],
            "replicate_scores_nats": values,
        })
    record = {
        "schema_version": SCHEMA,
        "case_study": "magnetic_core",
        "provenance": provenance(seed=estimator_seed),
        "state": {
            "path": str(args.state),
            "sha256": _sha256(args.state),
            "seed": seed,
            "n_observations": n_observations,
            "samples_sha256": state["posterior_samples"]["sha256"],
        },
        "estimator": {
            "namespace": args.namespace,
            "n_outer": args.n_outer,
            "n_inner": args.n_inner,
            "n_replicates": args.replicates,
            "seed": estimator_seed,
            "prefix_nested_common_random_numbers": True,
        },
        "candidate_scores": rows,
        "validity": {
            "candidate_count": len(rows),
            "complete": len(rows) == len(candidates),
            "finite": True,
            "valid": len(rows) == len(candidates),
        },
    }
    _atomic_json(args.out, record)
    print(args.out)


if __name__ == "__main__":
    main()
