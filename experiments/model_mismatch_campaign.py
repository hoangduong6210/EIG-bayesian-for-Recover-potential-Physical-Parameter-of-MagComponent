#!/usr/bin/env python3
"""Confirmatory paired-policy campaign under prespecified model mismatch."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import numpy as np

from eig_efficiency import BENCHMARK_V4_POLICIES, load_locked_selection, run_policy
from magcore_calib.inference import PosteriorResult
from magcore_calib.model_mismatch import (
    MISMATCH_REJECTION_SCHEMA, MISMATCH_RESULT_SCHEMA, POLICIES, config_sha256,
    gate_truth_evaluation, load_model_mismatch_plan, mismatch_candidate_library,
    mismatch_holdout_evaluation, mismatch_validation_library, payload_sha256,
    stable_mismatch_outcomes, validate_mismatch_result,
)
from magcore_calib.models import Channel, Geometry
from magcore_calib.prior import DatasheetPrior, draw_prior_predictive
from magcore_calib.results import provenance
from magcore_calib.runtime import require_slurm, sampling_pool


POLICY_OBJECTIVES = {
    "eig_raw": "raw", "eig_per_cost": "per_cost",
    "fixed_channel_balanced": "raw", "random_channel_balanced": "raw",
    "predictive_variance_raw": "raw",
    "predictive_variance_per_cost": "per_cost",
    "laplace_d_opt_raw": "raw", "laplace_d_opt_per_cost": "per_cost",
}


def _truth_anchor(seed: int, spec: DatasheetPrior):
    """Use a fixed prior-predictive draw independent of scenario and outcomes."""

    return draw_prior_predictive(spec, np.random.default_rng(seed))


def _write_immutable_json_unvalidated(
    record: dict, destination: Path, *, label: str,
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite {label}: {destination}")
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.partial")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(record, stream, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o640)
        os.link(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def _write_immutable_json(record: dict, destination: Path) -> Path:
    validate_mismatch_result(record)
    return _write_immutable_json_unvalidated(
        record, destination, label="model-mismatch result"
    )


def _rejection_record(record: dict, error: ValueError) -> dict:
    invalid_policies = [
        policy for policy in POLICIES
        if record["validity"][f"{policy}_convergence_valid"] is not True
    ]
    failed_states = {}
    for policy in invalid_policies:
        failed_states[policy] = [{
            "n_measurements": row["n_measurements"],
            "state_identity_sha256": row["decision_state"][
                "state_identity_sha256"
            ],
            "mcmc_seed": row["decision_state"]["mcmc_seed"],
            "sampler_diagnostics": row["decision_state"]["sampler_diagnostics"],
        } for row in record["policies"][policy]["trajectory"]
            if row["decision_state"]["valid"] is not True]
    return {
        "schema_version": MISMATCH_REJECTION_SCHEMA,
        "record_class": "sampler_rejection_diagnostic",
        "campaign_id": record["campaign_id"],
        "config_sha256": record["config_sha256"],
        "run_id": record["run_id"],
        "seed": record["seed"],
        "scenario": record["scenario"]["name"],
        "reason": "posterior_convergence_gate_failed",
        "validator_message": str(error),
        "invalid_policies": invalid_policies,
        "failed_states": failed_states,
        "estimator_decision_sha256": record["provenance"][
            "estimator_decision_sha256"
        ],
        "disclosure": {
            "scientific_endpoint_values_included": False,
            "claim_bearing_result": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--selection-file", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--rejection-out", type=Path)
    args = parser.parse_args()
    require_slurm()

    plan = load_model_mismatch_plan(args.config)
    if plan.retain_rejection_diagnostics and args.rejection_out is None:
        parser.error("this campaign requires --rejection-out")
    if args.seed not in plan.seeds:
        parser.error("seed is outside the preregistered confirmatory set")
    scenario = plan.scenario(args.scenario)
    setting, selection_sha256, selection_contents = load_locked_selection(
        str(args.selection_file)
    )
    if selection_sha256 != plan.estimator_decision_sha256:
        raise RuntimeError("estimator decision differs from the preregistered digest")
    if tuple(BENCHMARK_V4_POLICIES) != POLICIES:
        raise RuntimeError("policy implementation differs from the frozen registry")

    spec, geometry = DatasheetPrior(), Geometry()
    truth = _truth_anchor(args.seed, spec)
    library = mismatch_candidate_library(plan.temperatures_c)
    holdout = mismatch_validation_library(plan.temperatures_c)
    outcomes = stable_mismatch_outcomes(
        truth, scenario, library, seed=args.seed, geometry=geometry
    )
    common = dict(
        seed=args.seed, max_measurements=plan.max_measurements,
        n_walkers=plan.n_walkers, n_steps=plan.n_steps, burn=plan.burn,
        max_sampler_steps=plan.max_steps,
        sampler_check_interval=plan.check_interval,
        n_outer=setting["n_outer"], n_inner=setting["n_inner"],
        eig_replicates=setting["n_replicates"],
        pcv_gate_pct=plan.pcv_gate_pct, lm_gate_pct=plan.lm_gate_pct,
    )
    with sampling_pool(args.workers) as pool:
        fit_cache: dict[tuple[str, ...], PosteriorResult] = {}
        runs = {
            policy: run_policy(
                policy, library, outcomes, spec, geometry,
                objective=POLICY_OBJECTIVES[policy], pool=pool,
                fit_cache=fit_cache, **common,
            )
            for policy in POLICIES
        }

    policy_results: dict[str, dict] = {}
    validity: dict[str, bool] = {}
    for policy, (result, samples, _diagnostics) in runs.items():
        holdout_evaluation = mismatch_holdout_evaluation(
            samples, truth, scenario, holdout, geometry
        )
        gate_accuracy = gate_truth_evaluation(
            samples, truth, scenario,
            reached_precision_gate=result["reached"], geometry=geometry,
            pcv_error_threshold_pct=plan.false_confidence_pcv_error_pct,
            lm_error_threshold_pct=plan.false_confidence_lm_error_pct,
        )
        result["mismatch_endpoints"] = {
            "holdout_latent_mean": holdout_evaluation["summary"],
            "holdout_pcv_by_temperature_c": holdout_evaluation[
                "pcv_by_temperature_c"
            ],
            "holdout_point_records": holdout_evaluation["points"],
            "gate_truth_accuracy": gate_accuracy,
        }
        policy_results[policy] = result
        validity[f"{policy}_convergence_valid"] = all(
            row["decision_state"]["valid"] for row in result["trajectory"]
        )

    outcome_manifest = [{
        "design_identity": identity,
        "value_hex": float(observation.value).hex(),
        "sigma_hex": float(observation.sigma).hex(),
    } for identity, observation in sorted(outcomes.items())]
    truth_values = {
        "k": truth.k, "alpha": truth.alpha, "beta": truth.beta,
        "mu_s": truth.mu_s, "f_rel_hz": truth.f_rel_hz,
        "alpha_cc": truth.alpha_cc,
    }
    record = {
        "schema_version": MISMATCH_RESULT_SCHEMA,
        "campaign_id": plan.campaign_id,
        "config_sha256": config_sha256(args.config),
        "run_id": (
            f"model-mismatch-{os.environ['SLURM_JOB_ID']}-"
            f"{scenario.name}-{args.seed}"
        ),
        "seed": args.seed,
        "scenario": scenario.as_dict(),
        "truth_anchor": {
            "generation": "DatasheetPrior prior-predictive draw using seed",
            "shared_across_scenarios_for_seed": True,
            "datasheet_centered_on_realized_truth": False,
            "values": truth_values,
            "sha256": payload_sha256(truth_values),
        },
        "data": {
            "kind": "synthetic_structural_mismatch",
            "candidate_count": len(library), "holdout_count": len(holdout),
            "temperatures_c": list(plan.temperatures_c),
            "candidate_manifest_sha256": payload_sha256([
                point.exact_key() for point in library
            ]),
            "holdout_manifest_sha256": payload_sha256([
                point.exact_key() for point in holdout
            ]),
            "outcome_manifest_sha256": payload_sha256(outcome_manifest),
            "outcome_noise_namespace": "magcore-mismatch-outcome-v1",
            "common_standardized_noise_across_scenarios_for_seed": True,
            "common_candidate_outcomes_across_policies": True,
            "holdout_used_for_acquisition_or_stopping": False,
        },
        "inference_model": {
            "name": "isothermal_steinmetz_one_pole_cole_cole",
            "structural_discrepancy_terms_in_likelihood": False,
        },
        "policies": policy_results,
        "endpoint_contract": {
            "primary": [
                "gate_reach/failure by measurement budget",
                "measurement_count_to_gate", "modeled_cost_to_gate",
                "holdout_relative_error", "holdout_latent_ci90_coverage",
                "false_confidence_rate",
            ],
            "precision_gate": {
                "pcv_ci90_half_width_pct_max": plan.pcv_gate_pct,
                "lm_ci90_half_width_pct_max": plan.lm_gate_pct,
            },
            "false_confidence": {
                "pcv_absolute_relative_error_pct_max": (
                    plan.false_confidence_pcv_error_pct
                ),
                "lm_absolute_relative_error_pct_max": (
                    plan.false_confidence_lm_error_pct
                ),
            },
            "reached_only_count_and_cost_reported_with_failure_rate": True,
            "no_outcome_dependent_utility_tuning": True,
        },
        "validity": validity,
        "provenance": {
            **provenance(seed=args.seed),
            "estimator_decision_sha256": selection_sha256,
            "estimator_source_release_id": plan.estimator_source_release_id,
            "estimator_decision": selection_contents,
            "posterior_state_cache": {
                "requested_fits": sum(
                    len(result[0]["trajectory"]) for result in runs.values()
                ),
                "unique_fits": len(fit_cache),
                "key": "sorted exact observed-design identities",
            },
        },
    }
    try:
        validate_mismatch_result(record)
    except ValueError as error:
        if "nonconverged policy" not in str(error):
            raise
        if plan.retain_rejection_diagnostics and args.rejection_out is not None:
            _write_immutable_json_unvalidated(
                _rejection_record(record, error), args.rejection_out,
                label="model-mismatch rejection diagnostic",
            )
        raise
    print(_write_immutable_json(record, args.out))


if __name__ == "__main__":
    main()
