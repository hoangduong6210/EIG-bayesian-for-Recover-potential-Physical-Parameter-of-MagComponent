#!/usr/bin/env python3
"""Heavy SLURM sensitivity: recover three synthetic permeability lots."""

from __future__ import annotations

import argparse
import os

import numpy as np

from magcore_calib.data import default_library, observation_for
from magcore_calib.diagnostics import posterior_summary
from magcore_calib.inference import sample_emcee
from magcore_calib.models import Channel, Geometry, MagneticParams
from magcore_calib.prior import DatasheetPrior, draw_prior_predictive
from magcore_calib.results import SCHEMA_VERSION, provenance, write_result
from magcore_calib.runtime import require_slurm, sampling_pool


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--n-walkers", type=int, default=16)
    parser.add_argument("--n-steps", type=int, default=5000)
    parser.add_argument("--burn", type=int, default=1000)
    parser.add_argument("--workers", type=int, default=int(os.environ.get("SLURM_CPUS_PER_TASK", "1")))
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    require_slurm()
    spec, geometry = DatasheetPrior(), Geometry()
    base = draw_prior_predictive(spec, np.random.default_rng(args.seed))
    points = [p for p in default_library() if p.channel in (Channel.MU_REAL, Channel.MU_IMAG)]
    lots = []
    with sampling_pool(args.workers) as pool:
        for index, shift in enumerate((0.0, 0.08, -0.06)):
            truth = MagneticParams(base.k, base.alpha, base.beta, base.mu_s * (1.0 + shift),
                                  base.f_rel_hz, base.alpha_cc)
            rng = np.random.default_rng(args.seed * 100 + index)
            observations = [observation_for(truth, point, rng, geometry) for point in points]
            fit = sample_emcee(observations, spec, geometry, n_walkers=args.n_walkers,
                               n_steps=args.n_steps, burn=args.burn, seed=args.seed + index,
                               pool=pool)
            lots.append({"relative_shift": shift, "truth_mu_s": truth.mu_s,
                         "posterior_mu_s": posterior_summary(fit.samples)["mu_s"],
                         "diagnostics": fit.diagnostics})
    record = {
        "schema_version": SCHEMA_VERSION, "case_study": "magnetic_core",
        "run_id": f"lot-sensitivity-{os.environ['SLURM_JOB_ID']}-{args.seed}",
        "provenance": provenance(seed=args.seed),
        "data": {"kind": "synthetic", "temperature_c": 25.0,
                 "lot_relative_shifts": [0.0, 0.08, -0.06]},
        "model": {"name": "isothermal_cole_cole_lot_sensitivity",
                  "prior": spec.as_dict()},
        "sampler": {"n_walkers": args.n_walkers, "n_steps": args.n_steps,
                    "burn": args.burn},
        "posterior": {name: {"status": "reported_per_lot_in_design"} for name in
                      ("k", "alpha", "beta", "mu_s", "f_rel_hz", "alpha_cc")},
        "predictive": {}, "design": {"lots": lots},
        "claim_context": {"synthetic": True, "matched_model": True,
                          "prior_predictive_truth": True,
                          "datasheet_centered_on_realized_truth": False,
                          "oracle_initialized": False, "measured_data": False},
        "validity": {
            "all_parameter_convergence_valid": all(
                lot["diagnostics"].get("valid", False) for lot in lots
            ),
            "target_mu_s_convergence_valid": all(
                lot["diagnostics"]["steps_per_tau"]["ln_mu_s"] >= 50.0
                and lot["diagnostics"]["ess"]["ln_mu_s"] >= 400.0
                and 0.20 <= lot["diagnostics"]["acceptance_fraction"] <= 0.60
                for lot in lots
            ),
        },
    }
    print(write_result(record, args.out))


if __name__ == "__main__":
    main()
