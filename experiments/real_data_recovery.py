#!/usr/bin/env python3
"""Heavy SLURM experiment: isothermal measured complex-permeability fit."""

from __future__ import annotations

import argparse
import os

import numpy as np

from magcore_calib.data import complex_mu_path, load_material_csv
from magcore_calib.diagnostics import posterior_summary
from magcore_calib.forward import predict_active_batch
from magcore_calib.inference import sample_emcee
from magcore_calib.models import Channel
from magcore_calib.prior import DatasheetPrior
from magcore_calib.results import SCHEMA_VERSION, provenance, write_result
from magcore_calib.runtime import require_slurm, sampling_pool


def target_temperature(material: str, source: str) -> float:
    return 30.0 if material == "N95" and source == "LEA_MTB" else 25.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--material", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--n-walkers", type=int, default=48)
    parser.add_argument("--n-steps", type=int, default=2000)
    parser.add_argument("--burn", type=int, default=500)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--out", required=True, help="output stem; .json is appended")
    args = parser.parse_args()
    require_slurm()

    target = target_temperature(args.material, args.source)
    path = complex_mu_path(args.material, args.source)
    observations = load_material_csv(
        str(path), target_temperature_c=target, tolerance_c=0.75,
        channels=(Channel.MU_REAL, Channel.MU_IMAG),
    )
    spec = DatasheetPrior(ln_mu_s_sd=0.40, ln_f_rel_hz_sd=0.60, alpha_cc_sd=0.20)
    with sampling_pool(args.workers) as pool:
        fit = sample_emcee(
            observations, spec, n_walkers=args.n_walkers, n_steps=args.n_steps,
            burn=args.burn, seed=42, pool=pool,
        )
    posterior = posterior_summary(fit.samples)
    relative_residuals: dict[str, float] = {}
    for channel in (Channel.MU_REAL, Channel.MU_IMAG):
        selected = [o for o in observations if o.design.channel is channel]
        med = np.median(fit.samples, axis=0, keepdims=True)
        predictions = np.array([predict_active_batch(med, o.design)[0] for o in selected])
        values = np.array([o.value for o in selected])
        relative_residuals[f"{channel.value}_rms_pct"] = float(
            np.sqrt(np.mean(((values - predictions) / np.maximum(np.abs(values), 1e-9)) ** 2)) * 100.0
        )
    temperatures = [o.design.temperature_c for o in observations]
    record = {
        "schema_version": SCHEMA_VERSION, "case_study": "magnetic_core",
        "run_id": f"measured-mu-{args.material}-{args.source}-{os.environ['SLURM_JOB_ID']}",
        "provenance": provenance(seed=42, data_paths=[path]),
        "data": {"kind": "measured", "material": args.material, "source": args.source,
                 "path": str(path), "n_observations": len(observations),
                 "temperature_target_c": target, "temperature_tolerance_c": 0.75,
                 "temperature_actual_range_c": [min(temperatures), max(temperatures)]},
        "model": {"name": "isothermal_cole_cole", "prior": spec.as_dict()},
        "sampler": {"n_walkers": args.n_walkers, "n_steps": args.n_steps,
                    "burn": args.burn, "diagnostics": fit.diagnostics},
        "posterior": posterior,
        "predictive": relative_residuals,
        "design": {"experiment": "measured_complex_permeability"},
        "claim_context": {"synthetic": False, "matched_model": False,
                          "prior_predictive_truth": False,
                          "datasheet_centered_on_realized_truth": False,
                          "oracle_initialized": False, "measured_data": True},
        "validity": {"convergence_valid": fit.diagnostics["valid"],
                     "alpha_cc_boundary_flag": posterior["alpha_cc"]["boundary_flag"]},
    }
    print(write_result(record, args.out + ".json"))


if __name__ == "__main__":
    main()
