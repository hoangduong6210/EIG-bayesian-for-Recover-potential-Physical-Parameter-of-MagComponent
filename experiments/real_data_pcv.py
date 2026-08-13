#!/usr/bin/env python3
"""Heavy SLURM experiment: 25 C measured Steinmetz core-loss fit."""

from __future__ import annotations

import argparse
import os

import numpy as np

from magcore_calib.data import load_material_csv, pcv_paths
from magcore_calib.diagnostics import posterior_summary
from magcore_calib.forward import predict_active_batch
from magcore_calib.inference import sample_emcee
from magcore_calib.models import Channel
from magcore_calib.prior import DatasheetPrior
from magcore_calib.results import SCHEMA_VERSION, provenance, write_result
from magcore_calib.runtime import require_slurm, sampling_pool


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--material", required=True)
    parser.add_argument("--n-walkers", type=int, default=48)
    parser.add_argument("--n-steps", type=int, default=2000)
    parser.add_argument("--burn", type=int, default=500)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    require_slurm()

    paths = pcv_paths(args.material)
    observations = []
    target_temperature = 100.0 if args.material == "3C95" else 25.0
    load_reports = []
    for path in paths:
        load_report = {}
        try:
            observations.extend(load_material_csv(
                str(path), target_temperature_c=target_temperature, tolerance_c=0.5,
                channels=(Channel.PCV,), b_max_t=0.5,
                normalize_flux_above_1_as_millitesla=True, report=load_report,
            ))
        except ValueError:
            pass
        load_reports.append(load_report)
    if not observations:
        # Preserve the audit trail without silently fitting a different temperature.
        excluded = {
            "schema_version": SCHEMA_VERSION, "case_study": "magnetic_core",
            "run_id": f"measured-pcv-{args.material}-{os.environ['SLURM_JOB_ID']}",
            "provenance": provenance(seed=42, data_paths=paths),
            "data": {"kind": "measured", "material": args.material,
                     "paths": [str(path) for path in paths], "n_observations": 0,
                     "temperature_target_c": target_temperature, "temperature_tolerance_c": 0.5,
                     "files_read": load_reports},
            "model": {"name": "isothermal_steinmetz"}, "sampler": {"executed": False},
            "posterior": {name: {} for name in
                          ("k", "alpha", "beta", "mu_s", "f_rel_hz", "alpha_cc")},
            "predictive": {}, "design": {"experiment": "measured_core_loss"},
            "claim_context": {"synthetic": False, "matched_model": False,
                              "prior_predictive_truth": False,
                              "datasheet_centered_on_realized_truth": False,
                              "oracle_initialized": False, "measured_data": True},
            "validity": {"convergence_valid": False,
                         "excluded": True,
                         "reason": f"no observations in {target_temperature:g}+/-0.5 C cohort"},
        }
        print(write_result(excluded, args.out + ".json"))
        return
    spec = DatasheetPrior(log10_k_nom=0.0, log10_k_sd=1.0, alpha_sd=0.30, beta_sd=0.30)
    with sampling_pool(args.workers) as pool:
        fit = sample_emcee(
            observations, spec, n_walkers=args.n_walkers, n_steps=args.n_steps,
            burn=args.burn, seed=42, pool=pool,
        )
    posterior = posterior_summary(fit.samples)
    med = np.median(fit.samples, axis=0, keepdims=True)
    predictions = np.array([predict_active_batch(med, o.design)[0] for o in observations])
    values = np.array([o.value for o in observations])
    rms = float(np.sqrt(np.mean(((values - predictions) / np.maximum(np.abs(values), 1e-9)) ** 2)) * 100.0)
    temperatures = [o.design.temperature_c for o in observations]
    record = {
        "schema_version": SCHEMA_VERSION, "case_study": "magnetic_core",
        "run_id": f"measured-pcv-{args.material}-{os.environ['SLURM_JOB_ID']}",
        "provenance": provenance(seed=42, data_paths=paths),
        "data": {"kind": "measured", "material": args.material,
                 "paths": [str(path) for path in paths], "n_observations": len(observations),
                 "temperature_target_c": target_temperature, "temperature_tolerance_c": 0.5,
                 "temperature_actual_range_c": [min(temperatures), max(temperatures)],
                 "files_read": load_reports,
                 "flux_rows_normalized_millitesla_to_tesla": sum(
                     int(report.get("rows_flux_normalized_millitesla_to_tesla", 0))
                     for report in load_reports
                 )},
        "model": {"name": "isothermal_steinmetz", "prior": spec.as_dict()},
        "sampler": {"n_walkers": args.n_walkers, "n_steps": args.n_steps,
                    "burn": args.burn, "diagnostics": fit.diagnostics},
        "posterior": posterior, "predictive": {"pcv_relative_rms_pct": rms},
        "design": {"experiment": "measured_core_loss"},
        "claim_context": {"synthetic": False, "matched_model": False,
                          "prior_predictive_truth": False,
                          "datasheet_centered_on_realized_truth": False,
                          "oracle_initialized": False, "measured_data": True},
        "validity": {"convergence_valid": fit.diagnostics["valid"]},
    }
    print(write_result(record, args.out + ".json"))


if __name__ == "__main__":
    main()
