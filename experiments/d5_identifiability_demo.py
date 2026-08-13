#!/usr/bin/env python3
"""SLURM-only six-dimensional Fisher spectrum generation."""

from __future__ import annotations

import argparse
import os

import numpy as np

from magcore_calib.data import default_library, observation_for
from magcore_calib.identifiability import fisher_spectrum
from magcore_calib.models import Geometry, MagneticParams
from magcore_calib.prior import DatasheetPrior, prior_center_vector
from magcore_calib.results import SCHEMA_VERSION, provenance, write_result
from magcore_calib.runtime import require_slurm


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    require_slurm()
    spec = DatasheetPrior()
    params = MagneticParams.from_active(prior_center_vector(spec))
    geometry = Geometry()
    rng = np.random.default_rng(args.seed)
    observations = [observation_for(params, point, rng, geometry) for point in default_library()]
    spectrum = fisher_spectrum(params, observations, geometry)
    record = {
        "schema_version": SCHEMA_VERSION, "case_study": "magnetic_core",
        "run_id": f"identifiability-{os.environ['SLURM_JOB_ID']}-{args.seed}",
        "provenance": provenance(seed=args.seed),
        "data": {"kind": "synthetic_design", "n_observations": len(observations),
                 "temperature_c": 25.0},
        "model": {"name": "isothermal_steinmetz_cole_cole",
                  "active_coordinates": spectrum["parameter_names"]},
        "sampler": {"executed": False, "reason": "Fisher finite-difference analysis"},
        "posterior": {name: {"status": "not_applicable_identifiability_stage"} for name in
                      ("k", "alpha", "beta", "mu_s", "f_rel_hz", "alpha_cc")},
        "predictive": {}, "design": {"fisher_spectrum": spectrum},
        "claim_context": {"synthetic": True, "matched_model": True,
                          "prior_predictive_truth": False,
                          "datasheet_centered_on_realized_truth": False,
                          "oracle_initialized": False, "measured_data": False},
        "validity": {"fisher_rank": spectrum["rank"],
                     "full_rank": spectrum["rank"] == 6},
    }
    print(write_result(record, args.out))


if __name__ == "__main__":
    main()
