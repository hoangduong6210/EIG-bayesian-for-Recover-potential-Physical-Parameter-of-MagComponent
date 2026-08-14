#!/usr/bin/env python3
"""Heavy SLURM experiment: prior-predictive matched-model recovery."""

from __future__ import annotations

import argparse
import os

import numpy as np

from magcore_calib.data import default_library, observation_for
from magcore_calib.evaluation import latent_mean_ci_half_width_pct, recovery_summary
from magcore_calib.inference import sample_emcee
from magcore_calib.models import Channel, DesignPoint, Geometry
from magcore_calib.prior import DatasheetPrior, draw_prior_predictive
from magcore_calib.results import SCHEMA_VERSION, provenance, write_immutable, write_result
from magcore_calib.runtime import require_slurm, sampling_pool


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--n-walkers", type=int, default=48)
    parser.add_argument("--n-steps", type=int, default=5000)
    parser.add_argument("--burn", type=int, default=1000)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument(
        "--prior-offset", dest="prior_offset", type=float, default=0.0,
        help="Offset the inference prior center; this is not structural model mismatch.",
    )
    parser.add_argument("--out")
    parser.add_argument("--artifacts", default="artifacts")
    args = parser.parse_args()
    require_slurm()

    rng = np.random.default_rng(args.seed)
    spec = DatasheetPrior()
    truth = draw_prior_predictive(spec, rng)
    if args.prior_offset:
        spec = DatasheetPrior(
            log10_k_nom=spec.log10_k_nom + args.prior_offset,
            alpha_nom=spec.alpha_nom + 0.5 * args.prior_offset,
            beta_nom=spec.beta_nom + 0.5 * args.prior_offset,
            ln_mu_s_nom=spec.ln_mu_s_nom + args.prior_offset,
            ln_f_rel_hz_nom=spec.ln_f_rel_hz_nom + args.prior_offset,
            alpha_cc_nom=min(0.80, spec.alpha_cc_nom + 0.25 * args.prior_offset),
        )
    geometry = Geometry()
    library = default_library(25.0)
    observations = [observation_for(truth, point, rng, geometry) for point in library]
    with sampling_pool(args.workers) as pool:
        result = sample_emcee(
            observations, spec, geometry, n_walkers=args.n_walkers,
            n_steps=args.n_steps, burn=args.burn, seed=args.seed, pool=pool,
        )
    posterior = recovery_summary(result.samples, truth)
    pcv_ref = DesignPoint(Channel.PCV, 1e5, 0.1, 25.0)
    lm_ref = DesignPoint(Channel.LM, 1e5, 0.0, 25.0)
    predictive = {
        "pcv_latent_mean_ci90_half_width_pct": latent_mean_ci_half_width_pct(
            result.samples, pcv_ref, geometry
        ),
        "lm_latent_mean_ci90_half_width_pct": latent_mean_ci_half_width_pct(
            result.samples, lm_ref, geometry
        ),
        "gate": "two-output posterior-precision gate",
    }
    job_id = os.environ["SLURM_JOB_ID"]
    run_id = f"posterior-recovery-{job_id}-{args.seed}"
    record = {
        "schema_version": SCHEMA_VERSION,
        "case_study": "magnetic_core",
        "run_id": run_id,
        "provenance": provenance(seed=args.seed),
        "data": {
            "kind": "synthetic", "n_observations": len(observations),
            "temperature_c": 25.0, "temperature_tolerance_c": 0.5,
            "channels": sorted({o.design.channel.value for o in observations}),
        },
        "model": {
            "name": "isothermal_steinmetz_cole_cole",
            "active_coordinates": ["ln_k", "alpha", "beta", "ln_mu_s", "ln_f_rel_hz", "alpha_cc"],
            "prior": spec.as_dict(),
        },
        "sampler": {"n_walkers": args.n_walkers, "n_steps": args.n_steps,
                    "burn": args.burn, "diagnostics": result.diagnostics},
        "posterior": posterior,
        "predictive": predictive,
        "design": {"experiment": "prior_predictive_recovery"},
        "claim_context": {
            "synthetic": True, "matched_model": True,
            "prior_predictive_truth": args.prior_offset == 0.0,
            "datasheet_centered_on_realized_truth": False, "oracle_initialized": False,
            "measured_data": False, "structural_model_mismatch": False,
        },
        "validity": {
            "convergence_valid": result.diagnostics["valid"],
            "alpha_cc_boundary_flag": posterior["alpha_cc"]["boundary_flag"],
        },
    }
    record["design"]["prior_center_offset"] = args.prior_offset
    output = write_result(record, args.out) if args.out else write_immutable(record, args.artifacts)
    print(output)


if __name__ == "__main__":
    main()
