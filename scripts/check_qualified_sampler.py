#!/usr/bin/env python3
"""Endpoint-free integration check of the production sampler on locked states."""

from __future__ import annotations

import argparse
from pathlib import Path

from magcore_calib.inference import sample_emcee
from magcore_calib.runtime import require_slurm
from magcore_calib.sparse_mixing import (
    load_sparse_mixing_plan, reconstruct_state, sha256_file, write_json_create_only,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--mm2-source", required=True, type=Path)
    parser.add_argument("--mm2-config", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    require_slurm()
    if args.out.exists():
        raise FileExistsError("integration record already exists")
    plan = load_sparse_mixing_plan(args.config)
    rows = []
    for index, target in enumerate(plan.targets):
        state = reconstruct_state(plan, target, args.mm2_source, args.mm2_config)
        fit = sample_emcee(
            list(state.observations), state.spec, state.geometry,
            sampler_method="de_snooker", seed=2026091300 + index,
            n_walkers=48, n_steps=20000, burn=80000,
            max_steps=800000, check_interval=20000,
        )
        rows.append({"target_id": target.target_id,
                     "state_identity_sha256": state.state_identity_sha256,
                     "seed": 2026091300 + index, "diagnostics": fit.diagnostics})
        del fit
    passed = len(rows) == 2 and all(r["diagnostics"]["valid"] for r in rows)
    write_json_create_only(args.out, {
        "record_class": "endpoint_free_production_sampler_integration_check",
        "source_sha256": sha256_file(__file__), "parent_config_sha256": plan.config_sha256,
        "scientific_endpoints_included": False, "new_mismatch_campaign_admitted": False,
        "all_checks_passed": passed, "states": rows,
    })
    if not passed:
        raise RuntimeError("production sampler integration did not pass both locked states")


if __name__ == "__main__":
    main()
