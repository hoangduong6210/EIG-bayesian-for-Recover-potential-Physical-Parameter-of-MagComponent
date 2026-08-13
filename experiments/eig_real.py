#!/usr/bin/env python3
"""Heavy SLURM experiment: EIG recommendations from an isothermal measured posterior."""

from __future__ import annotations

import argparse
import os

import numpy as np

from magcore_calib.data import complex_mu_path, load_material_csv
from magcore_calib.diagnostics import posterior_summary
from magcore_calib.eig import rank_candidates_with_uncertainty
from magcore_calib.inference import sample_emcee
from magcore_calib.models import Channel, DesignPoint
from magcore_calib.prior import DatasheetPrior
from magcore_calib.results import SCHEMA_VERSION, provenance, write_result
from magcore_calib.runtime import require_slurm, sampling_pool


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--material", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--n-walkers", type=int, default=48)
    parser.add_argument("--n-steps", type=int, default=2000)
    parser.add_argument("--burn", type=int, default=500)
    parser.add_argument("--n-outer", type=int, default=300)
    parser.add_argument("--n-inner", type=int, default=80)
    parser.add_argument("--eig-replicates", type=int, default=20)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    require_slurm()
    target = 30.0 if args.material == "N95" and args.source == "LEA_MTB" else 25.0
    path = complex_mu_path(args.material, args.source)
    observations = load_material_csv(
        str(path), target_temperature_c=target, tolerance_c=0.75,
        channels=(Channel.MU_REAL, Channel.MU_IMAG),
    )
    spec = DatasheetPrior(ln_mu_s_sd=0.40, ln_f_rel_hz_sd=0.60, alpha_cc_sd=0.20)
    with sampling_pool(args.workers) as pool:
        fit = sample_emcee(observations, spec, n_walkers=args.n_walkers,
                           n_steps=args.n_steps, burn=args.burn, seed=42, pool=pool)
    frequencies = np.logspace(4, 7, 30)
    candidates = [DesignPoint(channel, float(frequency), 0.0, target)
                  for channel in (Channel.MU_REAL, Channel.MU_IMAG)
                  for frequency in frequencies]
    ranking = rank_candidates_with_uncertainty(
        candidates, fit.samples, seed=7, n_outer=args.n_outer,
        n_inner=args.n_inner, n_replicates=args.eig_replicates, objective="raw",
    )
    top = [{
        "design_key": entry.design.key(), "channel": entry.design.channel.value,
        "frequency_hz": entry.design.f_hz, "eig_mean_nats": entry.eig_mean_nats,
        "eig_sd_nats": entry.eig_sd_nats, "eig_se_nats": entry.eig_se_nats,
        "eig_ci95_nats": [entry.eig_ci95_low_nats, entry.eig_ci95_high_nats],
        "top_selection_rate": entry.top_selection_rate,
        "replicate_scores_nats": list(entry.replicate_scores_nats),
    } for entry in ranking]
    record = {
        "schema_version": SCHEMA_VERSION, "case_study": "magnetic_core",
        "run_id": f"measured-eig-{args.material}-{args.source}-{os.environ['SLURM_JOB_ID']}",
        "provenance": provenance(seed=42, data_paths=[path]),
        "data": {"kind": "measured", "material": args.material, "source": args.source,
                 "path": str(path), "n_observations": len(observations),
                 "temperature_target_c": target, "temperature_tolerance_c": 0.75},
        "model": {"name": "isothermal_cole_cole", "prior": spec.as_dict()},
        "sampler": {"diagnostics": fit.diagnostics},
        "posterior": posterior_summary(fit.samples),
        "predictive": {},
        "design": {
            "objective": "raw_eig",
            "estimator_replicates": args.eig_replicates,
            "candidate_seed_scheme": "sha256(base_seed, replicate, exact_design_tuple)",
            "candidate_scores": top,
            "model_conditional_acquisition_only": True,
        },
        "claim_context": {"synthetic": False, "matched_model": False,
                          "prior_predictive_truth": False,
                          "datasheet_centered_on_realized_truth": False,
                          "oracle_initialized": False, "measured_data": True,
                          "validated_laboratory_plan": False},
        "validity": {"convergence_valid": fit.diagnostics["valid"]},
    }
    print(write_result(record, args.out + ".json"))


if __name__ == "__main__":
    main()
