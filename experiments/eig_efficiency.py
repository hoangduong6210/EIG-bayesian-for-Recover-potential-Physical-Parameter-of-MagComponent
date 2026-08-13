#!/usr/bin/env python3
"""Heavy SLURM experiment: paired EIG-versus-fixed-schedule acquisition."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import defaultdict

import numpy as np

from magcore_calib.data import common_random_outcomes, default_library
from magcore_calib.diagnostics import posterior_summary
from magcore_calib.eig import (
    CHANNEL_COST_S, AcquisitionObjective, CandidateScore,
    rank_candidates_with_uncertainty, reveal,
)
from magcore_calib.evaluation import latent_mean_ci_half_width_pct
from magcore_calib.inference import sample_emcee
from magcore_calib.models import Channel, DesignPoint, Geometry, Observation
from magcore_calib.prior import DatasheetPrior, draw_prior_predictive
from magcore_calib.results import SCHEMA_VERSION, provenance, write_immutable, write_result
from magcore_calib.runtime import require_slurm, sampling_pool


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _payload_sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_locked_selection(path: str) -> tuple[dict, str]:
    """Load the preregistered estimator decision used by the acquisition job."""
    with open(path, encoding="utf-8") as stream:
        decision = json.load(stream)
    if decision.get("schema_version") != "eig-convergence-final/1.0":
        raise ValueError("acquisition requires an eig-convergence-final/1.0 decision")
    if decision.get("valid") is not True:
        raise ValueError("acquisition cannot run without a valid estimator decision")
    setting = decision.get("selected_setting")
    required = {"n_outer", "n_inner", "n_replicates"}
    if not isinstance(setting, dict) or required - setting.keys():
        raise ValueError("estimator decision has no complete selected_setting")
    if any(not isinstance(setting[key], int) or setting[key] < 1 for key in required):
        raise ValueError("selected estimator setting is malformed")
    return setting, _sha256(path)


def fixed_channel_balanced_order(library: list[DesignPoint]) -> list[DesignPoint]:
    groups: dict[Channel, list[DesignPoint]] = defaultdict(list)
    for point in library:
        groups[point.channel].append(point)
    order: list[DesignPoint] = []
    channels = (Channel.PCV, Channel.MU_REAL, Channel.MU_IMAG, Channel.LM)
    while any(groups[channel] for channel in channels):
        for channel in channels:
            if groups[channel]:
                order.append(groups[channel].pop(0))
    return order


def _score_record(entry: CandidateScore) -> dict:
    return {
        "design_key": entry.design.key(),
        "channel": entry.design.channel.value,
        "eig_mean_nats": entry.eig_mean_nats,
        "eig_sd_nats": entry.eig_sd_nats,
        "eig_se_nats": entry.eig_se_nats,
        "eig_ci95_nats": [entry.eig_ci95_low_nats, entry.eig_ci95_high_nats],
        "utility_mean": entry.utility_mean,
        "top_selection_rate": entry.top_selection_rate,
        "replicate_scores_nats": list(entry.replicate_scores_nats),
    }


def run_policy(policy: str, library: list[DesignPoint], outcomes: dict[str, Observation],
               spec: DatasheetPrior, geometry: Geometry, *, seed: int,
               max_measurements: int, n_walkers: int, n_steps: int, burn: int,
               n_outer: int, n_inner: int, eig_replicates: int,
               objective: AcquisitionObjective, pool=None) -> tuple[dict, np.ndarray, dict]:
    fixed_order = fixed_channel_balanced_order(library)
    selected = fixed_order[:2]
    observations = [reveal(outcomes, point) for point in selected]
    trajectory = []
    latest_samples = np.empty((0, 6))
    latest_diagnostics: dict = {}
    for step in range(max_measurements - 1):
        fit = sample_emcee(
            observations, spec, geometry, n_walkers=n_walkers, n_steps=n_steps,
            burn=burn, seed=seed * 1000 + step, pool=pool,
        )
        latest_samples, latest_diagnostics = fit.samples, fit.diagnostics
        pcv_ci = latent_mean_ci_half_width_pct(
            fit.samples, DesignPoint(Channel.PCV, 1e5, 0.1, 25.0), geometry
        )
        lm_ci = latent_mean_ci_half_width_pct(
            fit.samples, DesignPoint(Channel.LM, 1e5, 0.0, 25.0), geometry
        )
        reached = pcv_ci <= 8.0 and lm_ci <= 5.0
        trajectory.append({
            "n_measurements": len(selected),
            "pcv_latent_mean_ci90_half_width_pct": pcv_ci,
            "lm_latent_mean_ci90_half_width_pct": lm_ci,
            "reached": reached,
            "modeled_cost_units": sum(CHANNEL_COST_S[p.channel] for p in selected),
            "selected_keys": [p.key() for p in selected],
        })
        if reached or len(selected) >= max_measurements:
            break
        remaining = [point for point in library if point not in selected]
        if policy == "eig":
            ranking = rank_candidates_with_uncertainty(
                remaining, fit.samples, seed=seed * 10000 + step,
                geometry=geometry, n_outer=n_outer, n_inner=n_inner,
                n_replicates=eig_replicates, objective=objective,
            )
            next_point = ranking[0].design
            trajectory[-1]["acquisition"] = {
                "objective": objective,
                "selected_key": next_point.key(),
                "candidate_scores": [_score_record(entry) for entry in ranking],
            }
        else:
            next_point = next(point for point in fixed_order if point not in selected)
            trajectory[-1]["acquisition"] = {
                "objective": "fixed_channel_balanced_traversal",
                "selected_key": next_point.key(),
            }
        selected.append(next_point)
        observations.append(reveal(outcomes, next_point))
    return {
        "policy": policy,
        "objective": objective if policy == "eig" else "fixed_channel_balanced_traversal",
        "reached": bool(trajectory and trajectory[-1]["reached"]),
        "n_measurements_to_gate": len(selected) if trajectory and trajectory[-1]["reached"] else None,
        "modeled_cost_to_gate": (
            trajectory[-1]["modeled_cost_units"]
            if trajectory and trajectory[-1]["reached"] else None
        ),
        "trajectory": trajectory,
    }, latest_samples, latest_diagnostics


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--max-measurements", "--max-meas", type=int, default=25)
    parser.add_argument("--n-walkers", type=int, default=48)
    parser.add_argument("--n-steps", type=int, default=1200)
    parser.add_argument("--burn", type=int, default=400)
    parser.add_argument("--n-outer", type=int, default=300)
    parser.add_argument("--n-inner", type=int, default=100)
    parser.add_argument("--eig-replicates", type=int, default=20)
    parser.add_argument("--selection-file")
    parser.add_argument(
        "--eig-objectives", nargs="+", choices=("raw", "per_cost"),
        default=("raw", "per_cost"),
    )
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--out")
    parser.add_argument("--artifacts", default="artifacts")
    args = parser.parse_args()
    if set(args.eig_objectives) != {"raw", "per_cost"}:
        parser.error("benchmark v2 requires both raw and per_cost EIG objectives")
    require_slurm()

    selection_sha256 = None
    if args.selection_file:
        selected, selection_sha256 = load_locked_selection(args.selection_file)
        args.n_outer = selected["n_outer"]
        args.n_inner = selected["n_inner"]
        args.eig_replicates = selected["n_replicates"]

    spec, geometry = DatasheetPrior(), Geometry()
    truth = draw_prior_predictive(spec, np.random.default_rng(args.seed))
    library = default_library(25.0)
    outcomes = common_random_outcomes(truth, library, seed=args.seed + 1_000_003, geometry=geometry)
    truth_sha256 = _payload_sha256([float(value) for value in truth.to_active()])
    outcome_manifest_sha256 = _payload_sha256([
        {
            "design_key": key, "value_hex": float(outcomes[key].value).hex(),
            "sigma_hex": float(outcomes[key].sigma).hex(),
        }
        for key in sorted(outcomes)
    ])
    common = dict(
        seed=args.seed, max_measurements=args.max_measurements,
        n_walkers=args.n_walkers, n_steps=args.n_steps, burn=args.burn,
        n_outer=args.n_outer, n_inner=args.n_inner,
        eig_replicates=args.eig_replicates,
    )
    with sampling_pool(args.workers) as pool:
        eig_runs = {
            objective: run_policy(
                "eig", library, outcomes, spec, geometry,
                objective=objective, pool=pool, **common,
            )
            for objective in dict.fromkeys(args.eig_objectives)
        }
        baseline_result, _, baseline_diag = run_policy(
            "baseline", library, outcomes, spec, geometry,
            objective="raw", pool=pool, **common,
        )

    def paired_endpoint(result: dict) -> dict:
        count = result["n_measurements_to_gate"]
        baseline_count = baseline_result["n_measurements_to_gate"]
        cost = result["modeled_cost_to_gate"]
        baseline_cost = baseline_result["modeled_cost_to_gate"]
        return {
            "both_reached_gate": bool(result["reached"] and baseline_result["reached"]),
            "measurement_count_difference": (
                None if count is None or baseline_count is None else baseline_count - count
            ),
            "measurement_count_reduction_pct": (
                None if not count or not baseline_count
                else (baseline_count - count) / baseline_count * 100.0
            ),
            "modeled_cost_difference": (
                None if cost is None or baseline_cost is None else baseline_cost - cost
            ),
            "modeled_cost_reduction_pct": (
                None if not cost or not baseline_cost
                else (baseline_cost - cost) / baseline_cost * 100.0
            ),
        }

    policy_results = {f"eig_{objective}": run[0] for objective, run in eig_runs.items()}
    policy_results["fixed_channel_balanced"] = baseline_result
    paired_endpoints = {
        f"eig_{objective}_vs_fixed": paired_endpoint(run[0])
        for objective, run in eig_runs.items()
    }
    reference_objective = "per_cost" if "per_cost" in eig_runs else next(iter(eig_runs))
    reference_samples = eig_runs[reference_objective][1]
    posterior = posterior_summary(reference_samples)
    run_id = f"eig-efficiency-{os.environ['SLURM_JOB_ID']}-{args.seed}"
    record = {
        "schema_version": SCHEMA_VERSION, "case_study": "magnetic_core", "run_id": run_id,
        "provenance": provenance(seed=args.seed),
        "data": {"kind": "synthetic", "temperature_c": 25.0,
                 "temperature_tolerance_c": 0.5, "common_random_outcomes": True,
                 "candidate_count": len(library), "truth_sha256": truth_sha256,
                 "outcome_manifest_sha256": outcome_manifest_sha256},
        "model": {"name": "isothermal_steinmetz_cole_cole", "prior": spec.as_dict()},
        "sampler": {
            "policy_diagnostics": {
                f"eig_{objective}": run[2] for objective, run in eig_runs.items()
            },
            "fixed_channel_balanced_diagnostics": baseline_diag,
        },
        "posterior": posterior,
        "predictive": {
            "gate": "two-output latent-mean-response precision gate",
            "targets": {
                "pcv": {"frequency_hz": 1e5, "b_pk_t": 0.1, "temperature_c": 25.0,
                        "ci90_half_width_pct_max": 8.0},
                "lm": {"frequency_hz": 1e5, "b_pk_t": 0.0, "temperature_c": 25.0,
                       "ci90_half_width_pct_max": 5.0},
            },
        },
        "design": {
            "benchmark_version": 3,
            "policies": policy_results,
            "paired_endpoints": paired_endpoints,
            "candidate_seed_scheme": "sha256(base_seed, replicate, exact_design_tuple)",
            "eig_estimator_replicates": args.eig_replicates,
            "eig_estimator_setting": {
                "n_outer": args.n_outer, "n_inner": args.n_inner,
                "n_replicates": args.eig_replicates,
            },
            "estimator_decision_sha256": selection_sha256,
            "primary_endpoints": {
                "eig_raw": "measurement_count_to_gate",
                "eig_per_cost": "modeled_cost_to_gate",
            },
        },
        "claim_context": {
            "synthetic": True, "matched_model": True, "prior_predictive_truth": True,
            "datasheet_centered_on_realized_truth": False, "oracle_initialized": False,
            "measured_data": False,
        },
        "validity": {
            **{
                f"eig_{objective}_convergence_valid": run[2].get("valid", False)
                for objective, run in eig_runs.items()
            },
            "fixed_channel_balanced_convergence_valid": baseline_diag.get("valid", False),
        },
    }
    output = write_result(record, args.out) if args.out else write_immutable(record, args.artifacts)
    print(output)


if __name__ == "__main__":
    main()
