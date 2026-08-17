#!/usr/bin/env python3
"""Heavy SLURM experiment: paired eight-policy acquisition benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import defaultdict
from pathlib import Path

import numpy as np

from magcore_calib.acquisition import (
    AcquisitionScore,
    exact_design_identity,
    random_channel_balanced_order,
    rank_laplace_d_opt,
    rank_predictive_variance,
)
from magcore_calib.data import (
    default_library, stable_common_random_outcomes, validation_library,
)
from magcore_calib.diagnostics import posterior_summary
from magcore_calib.eig import (
    CHANNEL_COST_S, AcquisitionObjective, CandidateScore,
    rank_candidates_with_uncertainty, reveal,
)
from magcore_calib.evaluation import (
    latent_holdout_evaluation, latent_mean_ci_half_width_pct, recovery_summary,
)
from magcore_calib.inference import PosteriorResult, sample_emcee
from magcore_calib.models import Channel, DesignPoint, Geometry, Observation
from magcore_calib.prior import DatasheetPrior, draw_prior_predictive
from magcore_calib.results import (
    BENCHMARK_V4_POLICY_OBJECTIVES, SCHEMA_VERSION, provenance,
    write_immutable, write_result,
)
from magcore_calib.runtime import require_slurm, sampling_pool
from magcore_calib.study_plan import load_study_plan


BENCHMARK_V4_POLICIES = tuple(BENCHMARK_V4_POLICY_OBJECTIVES)
RANDOM_POLICY_NAMESPACE = "random_channel_balanced/v1"


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _payload_sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _namespaced_seed(base_seed: int, namespace: str) -> int:
    """Derive a reproducible policy seed without sharing the outcome RNG stream."""

    payload = f"magcore-policy-v1|{base_seed}|{namespace}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big", signed=False)


def load_locked_selection(path: str) -> tuple[dict, str, dict]:
    """Load the preregistered estimator decision used by the acquisition job."""
    with open(path, encoding="utf-8") as stream:
        decision = json.load(stream)
    if decision.get("schema_version") != "eig-convergence-final/1.0":
        raise ValueError("acquisition requires an eig-convergence-final/1.0 decision")
    if decision.get("valid") is not True:
        raise ValueError("acquisition cannot run without a valid estimator decision")
    setting = decision.get("selected_setting")
    required = {"n_outer", "n_inner", "n_replicates"}
    if not isinstance(setting, dict) or set(setting) != required:
        raise ValueError("estimator decision has no complete selected_setting")
    if any(
        isinstance(setting[key], bool) or not isinstance(setting[key], int)
        or setting[key] < 1 for key in required
    ):
        raise ValueError("selected estimator setting is malformed")
    if decision.get("raw_claim_gate_passed") is not True \
            or decision.get("per_cost_claim_gate_passed") is not True:
        raise ValueError("estimator decision did not pass both objective gates")
    if not isinstance(decision.get("selection_mode"), str) \
            or not decision["selection_mode"]:
        raise ValueError("estimator decision lacks a selection mode")
    decision_contents = {
        "schema_version": decision["schema_version"],
        "selected_setting": dict(setting),
        "selection_mode": decision.get("selection_mode"),
        "raw_claim_gate_passed": True,
        "per_cost_claim_gate_passed": True,
        "valid": True,
    }
    return setting, _sha256(path), decision_contents


def _posterior_state_seed(base_seed: int, state_key: tuple[str, ...]) -> int:
    """Bind MCMC draws to the observed state, independent of policy order."""

    ordered_state = tuple(sorted(state_key))
    payload = json.dumps(
        {
            "namespace": "magcore-posterior-state-v1",
            "base_seed": int(base_seed),
            "observed_design_identities": list(ordered_state),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    # emcee's compatibility RandomState accepts only unsigned 32-bit seeds.
    return int.from_bytes(hashlib.sha256(payload).digest()[:4], "big", signed=False)


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
        "design_identity": exact_design_identity(entry.design),
        "channel": entry.design.channel.value,
        "eig_mean_nats": entry.eig_mean_nats,
        "eig_sd_nats": entry.eig_sd_nats,
        "eig_se_nats": entry.eig_se_nats,
        "eig_ci95_nats": [entry.eig_ci95_low_nats, entry.eig_ci95_high_nats],
        "utility_mean": entry.utility_mean,
        "top_selection_rate": entry.top_selection_rate,
        "replicate_scores_nats": list(entry.replicate_scores_nats),
    }


def _comparator_score_record(entry: AcquisitionScore) -> dict:
    return {
        "design_key": entry.design.key(),
        "design_identity": exact_design_identity(entry.design),
        "channel": entry.design.channel.value,
        "method": entry.method,
        "objective": entry.objective,
        "score": entry.score,
        "score_units": (
            "nats" if entry.method == "laplace_d_opt" else "dimensionless_ratio"
        ),
        "utility": entry.utility,
        "noise_sigma": entry.noise_sigma,
    }


def run_policy(policy: str, library: list[DesignPoint], outcomes: dict[str, Observation],
               spec: DatasheetPrior, geometry: Geometry, *, seed: int,
               max_measurements: int, n_walkers: int, n_steps: int, burn: int,
               n_outer: int, n_inner: int, eig_replicates: int,
               objective: AcquisitionObjective, pool=None,
               fit_cache: dict[tuple[str, ...], PosteriorResult] | None = None,
               pcv_gate_pct: float = 8.0, lm_gate_pct: float = 5.0,
               ) -> tuple[dict, np.ndarray, dict]:
    method_by_policy = {
        "eig": "eig",
        "eig_raw": "eig",
        "eig_per_cost": "eig",
        "baseline": "fixed_channel_balanced",
        "fixed_channel_balanced": "fixed_channel_balanced",
        "random_channel_balanced": "random_channel_balanced",
        "predictive_variance_raw": "predictive_variance",
        "predictive_variance_per_cost": "predictive_variance",
        "laplace_d_opt_raw": "laplace_d_opt",
        "laplace_d_opt_per_cost": "laplace_d_opt",
    }
    try:
        method = method_by_policy[policy]
    except KeyError as error:
        raise ValueError(f"unsupported acquisition policy: {policy}") from error
    if policy.endswith("_raw") and objective != "raw":
        raise ValueError(f"policy {policy} requires the raw objective")
    if policy.endswith("_per_cost") and objective != "per_cost":
        raise ValueError(f"policy {policy} requires the per_cost objective")

    fixed_order = fixed_channel_balanced_order(library)
    selected = fixed_order[:2]
    random_policy_seed = _namespaced_seed(seed, RANDOM_POLICY_NAMESPACE)
    random_order = random_channel_balanced_order(
        library, seed=random_policy_seed, selected=selected,
    )
    observations = [reveal(outcomes, point) for point in selected]
    trajectory = []
    latest_samples = np.empty((0, 6))
    latest_diagnostics: dict = {}
    for step in range(max_measurements - 1):
        state_key = tuple(sorted(point.exact_key() for point in selected))
        fit = fit_cache.get(state_key) if fit_cache is not None else None
        fit_cache_reused = fit is not None
        fit_seed = _posterior_state_seed(seed, state_key)
        if fit is None:
            ordered_observations = sorted(
                observations, key=lambda item: item.design.exact_key()
            )
            fit = sample_emcee(
                ordered_observations, spec, geometry, n_walkers=n_walkers,
                n_steps=n_steps, burn=burn, seed=fit_seed, pool=pool,
            )
            if fit_cache is not None:
                fit_cache[state_key] = fit
        latest_samples, latest_diagnostics = fit.samples, fit.diagnostics
        pcv_ci = latent_mean_ci_half_width_pct(
            fit.samples, DesignPoint(Channel.PCV, 1e5, 0.1, 25.0), geometry
        )
        lm_ci = latent_mean_ci_half_width_pct(
            fit.samples, DesignPoint(Channel.LM, 1e5, 0.0, 25.0), geometry
        )
        reached = pcv_ci <= pcv_gate_pct and lm_ci <= lm_gate_pct
        trajectory.append({
            "n_measurements": len(selected),
            "pcv_latent_mean_ci90_half_width_pct": pcv_ci,
            "lm_latent_mean_ci90_half_width_pct": lm_ci,
            "reached": reached,
            "modeled_cost_units": sum(CHANNEL_COST_S[p.channel] for p in selected),
            "selected_keys": [p.key() for p in selected],
            "selected_identities": [p.exact_key() for p in selected],
            "decision_state": {
                "state_identity_sha256": _payload_sha256(list(state_key)),
                "observed_design_identities": list(state_key),
                "n_observations": len(state_key),
                "mcmc_seed_namespace": "magcore-posterior-state-v1",
                "mcmc_seed": fit_seed,
                "fit_cache_reused": fit_cache_reused,
                "sampler_diagnostics": fit.diagnostics,
                "valid": bool(fit.diagnostics.get("valid", False)),
            },
        })
        if reached or len(selected) >= max_measurements:
            break
        remaining = [point for point in library if point not in selected]
        if method == "eig":
            ranking = rank_candidates_with_uncertainty(
                remaining, fit.samples, seed=seed * 10000 + step,
                geometry=geometry, n_outer=n_outer, n_inner=n_inner,
                n_replicates=eig_replicates, objective=objective,
            )
            next_point = ranking[0].design
            trajectory[-1]["acquisition"] = {
                "objective": objective,
                "selected_key": next_point.key(),
                "selected_identity": exact_design_identity(next_point),
                "candidate_scores": [_score_record(entry) for entry in ranking],
            }
        elif method == "predictive_variance":
            ranking = rank_predictive_variance(
                library, fit.samples, selected=selected, objective=objective,
                geometry=geometry,
            )
            next_point = ranking[0].design
            trajectory[-1]["acquisition"] = {
                "objective": objective,
                "method": method,
                "selected_key": next_point.key(),
                "selected_identity": exact_design_identity(next_point),
                "candidate_scores": [
                    _comparator_score_record(entry) for entry in ranking
                ],
            }
        elif method == "laplace_d_opt":
            ranking = rank_laplace_d_opt(
                library, fit.samples, selected=selected, objective=objective,
                geometry=geometry,
            )
            next_point = ranking[0].design
            trajectory[-1]["acquisition"] = {
                "objective": objective,
                "method": method,
                "selected_key": next_point.key(),
                "selected_identity": exact_design_identity(next_point),
                "candidate_scores": [
                    _comparator_score_record(entry) for entry in ranking
                ],
            }
        elif method == "random_channel_balanced":
            next_point = next(point for point in random_order if point not in selected)
            trajectory[-1]["acquisition"] = {
                "objective": "random_channel_balanced_traversal",
                "selected_key": next_point.key(),
                "selected_identity": exact_design_identity(next_point),
                "seed_namespace": RANDOM_POLICY_NAMESPACE,
                "seed": random_policy_seed,
            }
        else:
            next_point = next(point for point in fixed_order if point not in selected)
            trajectory[-1]["acquisition"] = {
                "objective": "fixed_channel_balanced_traversal",
                "selected_key": next_point.key(),
                "selected_identity": exact_design_identity(next_point),
            }
        selected.append(next_point)
        observations.append(reveal(outcomes, next_point))
    return {
        "policy": policy,
        "objective": (
            objective if method in ("eig", "predictive_variance", "laplace_d_opt")
            else f"{method}_traversal"
        ),
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
    parser.add_argument("--selection-file", required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--eig-objectives", nargs="+", choices=("raw", "per_cost"),
        default=("raw", "per_cost"),
    )
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--out")
    parser.add_argument("--artifacts", default="artifacts")
    args = parser.parse_args()
    if set(args.eig_objectives) != {"raw", "per_cost"}:
        parser.error("benchmark v4 requires both raw and per_cost EIG objectives")
    require_slurm()

    selected, selection_sha256, selection_contents = load_locked_selection(
        args.selection_file
    )
    args.n_outer = selected["n_outer"]
    args.n_inner = selected["n_inner"]
    args.eig_replicates = selected["n_replicates"]

    plan = load_study_plan(args.config)
    benchmark = plan.comparator_benchmark
    if benchmark.policies != BENCHMARK_V4_POLICIES:
        raise ValueError("runtime policy order differs from the preregistered registry")
    if dict(plan.modeled_cost_seconds) != {
        channel.value: CHANNEL_COST_S[channel] for channel in Channel
    }:
        raise ValueError("runtime acquisition costs differ from the frozen study plan")
    runtime_contract = {
        "max_measurements": args.max_measurements,
        "n_walkers": args.n_walkers,
        "n_steps": args.n_steps,
        "burn": args.burn,
        "objectives": tuple(args.eig_objectives),
    }
    configured_contract = {
        "max_measurements": plan.max_measurements,
        "n_walkers": plan.n_walkers,
        "n_steps": plan.n_steps,
        "burn": plan.burn,
        "objectives": plan.eig_objectives,
    }
    if runtime_contract != configured_contract:
        raise ValueError("runtime CLI differs from the frozen study plan")

    spec, geometry = DatasheetPrior(), Geometry()
    truth = draw_prior_predictive(spec, np.random.default_rng(args.seed))
    library = default_library(25.0)
    if len(library) != benchmark.candidate_count:
        raise ValueError("candidate library differs from the frozen study contract")
    outcomes = stable_common_random_outcomes(
        truth, library, seed=args.seed + 1_000_003, geometry=geometry
    )
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
        pcv_gate_pct=plan.stop_rule.pcv_ci_half_width_pct,
        lm_gate_pct=plan.stop_rule.lm_ci_half_width_pct,
    )
    policy_objectives: dict[str, AcquisitionObjective] = {
        "eig_raw": "raw",
        "eig_per_cost": "per_cost",
        "fixed_channel_balanced": "raw",
        "random_channel_balanced": "raw",
        "predictive_variance_raw": "raw",
        "predictive_variance_per_cost": "per_cost",
        "laplace_d_opt_raw": "raw",
        "laplace_d_opt_per_cost": "per_cost",
    }
    with sampling_pool(args.workers) as pool:
        fit_cache: dict[tuple[str, ...], PosteriorResult] = {}
        policy_runs = {
            policy: run_policy(
                policy, library, outcomes, spec, geometry,
                objective=policy_objectives[policy], pool=pool,
                fit_cache=fit_cache, **common,
            )
            for policy in BENCHMARK_V4_POLICIES
        }

    baseline_result = policy_runs["fixed_channel_balanced"][0]

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

    policy_results = {policy: run[0] for policy, run in policy_runs.items()}
    holdout = validation_library(25.0)
    holdout_manifest_sha256 = _payload_sha256(
        sorted(point.exact_key() for point in holdout)
    )
    for policy, result in policy_results.items():
        samples = policy_runs[policy][1]
        parameter_recovery = recovery_summary(samples, truth)
        holdout_evaluation = latent_holdout_evaluation(
            samples, truth, holdout, geometry
        )
        result["validation_endpoints"] = {
            "used_for_acquisition_or_stopping": False,
            "evaluated_at_measurement_count": len(
                result["trajectory"][-1]["selected_identities"]
            ),
            "parameter_truth_in_ci90_count": sum(
                int(entry["truth_in_ci90"])
                for entry in parameter_recovery.values()
            ),
            "parameter_recovery": parameter_recovery,
            "holdout_latent_mean": holdout_evaluation["summary"],
            "holdout_point_records": holdout_evaluation["points"],
        }
    paired_endpoints = {
        f"{policy}_vs_fixed": paired_endpoint(run[0])
        for policy, run in policy_runs.items()
        if policy != "fixed_channel_balanced"
    }
    reference_samples = policy_runs["eig_per_cost"][1]
    posterior = posterior_summary(reference_samples)
    run_id = f"eig-efficiency-{os.environ['SLURM_JOB_ID']}-{args.seed}"
    record = {
        "schema_version": SCHEMA_VERSION, "case_study": "magnetic_core", "run_id": run_id,
        "provenance": provenance(seed=args.seed),
        "data": {"kind": "synthetic", "temperature_c": 25.0,
                 "temperature_tolerance_c": 0.5, "common_random_outcomes": True,
                 "candidate_count": len(library), "holdout_count": len(holdout),
                 "truth_sha256": truth_sha256,
                 "holdout_manifest_sha256": holdout_manifest_sha256,
                 "outcome_manifest_sha256": outcome_manifest_sha256},
        "model": {"name": "isothermal_steinmetz_cole_cole", "prior": spec.as_dict()},
        "sampler": {
            "policy_diagnostics": {policy: run[2] for policy, run in policy_runs.items()},
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
            "benchmark_version": 4,
            "runtime_contract": {
                **{key: value for key, value in runtime_contract.items() if key != "objectives"},
                "objectives": list(runtime_contract["objectives"]),
            },
            "policies": policy_results,
            "comparator_registry": [
                entry.as_dict() for entry in benchmark.policy_registry
            ],
            "direct_contrasts": [
                entry.as_dict() for entry in benchmark.direct_contrasts
            ],
            "paired_endpoints": paired_endpoints,
            "candidate_seed_scheme": "sha256(base_seed, replicate, exact_design_tuple)",
            "random_policy_seed_scheme": (
                "sha256(magcore-policy-v1, base_seed, random_channel_balanced/v1)"
            ),
            "modeled_cost_seconds": {
                channel.value: CHANNEL_COST_S[channel] for channel in Channel
            },
            "modeled_cost_interpretation": "prespecified assumption, not laboratory time",
            "posterior_state_cache": {
                "requested_fits": sum(len(run[0]["trajectory"]) for run in policy_runs.values()),
                "unique_fits": len(fit_cache),
                "key": "sorted exact observed-design identities",
            },
            "eig_estimator_replicates": args.eig_replicates,
            "eig_estimator_setting": {
                "n_outer": args.n_outer, "n_inner": args.n_inner,
                "n_replicates": args.eig_replicates,
            },
            "estimator_decision_sha256": selection_sha256,
            "estimator_decision": selection_contents,
            "primary_endpoints": benchmark.primary_endpoints,
            "gate_contract": plan.stop_rule.as_dict(),
            "holdout_contract": benchmark.holdout_contract.as_dict(),
            "secondary_validation_endpoints": {
                "used_for_acquisition_or_stopping": False,
                "parameter_recovery": (
                    "six parameter medians and equal-tailed 90% intervals"
                ),
                "holdout_prediction": (
                    "per-channel latent-mean relative error and interval coverage "
                    "on a prespecified grid disjoint from acquisition candidates"
                ),
            },
        },
        "claim_context": dict(benchmark.claim_context),
        "validity": {
            **{
                f"{policy}_convergence_valid": all(
                    row["decision_state"]["valid"]
                    for row in run[0]["trajectory"]
                )
                for policy, run in policy_runs.items()
            },
        },
    }
    output = write_result(record, args.out) if args.out else write_immutable(record, args.artifacts)
    print(output)


if __name__ == "__main__":
    main()
