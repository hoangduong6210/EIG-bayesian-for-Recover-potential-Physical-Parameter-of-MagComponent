from copy import deepcopy
import hashlib
import json

import pytest

from magcore_calib.results import (
    BENCHMARK_V4_DIRECT_CONTRASTS,
    BENCHMARK_V4_POLICY_REGISTRY,
    SCHEMA_VERSION,
    validate_result,
)
from magcore_calib.runtime import require_slurm


def valid_record():
    return {
        "schema_version": SCHEMA_VERSION, "case_study": "magnetic_core", "run_id": "x",
        "provenance": {"slurm": {"job_id": "123"}}, "data": {}, "model": {}, "sampler": {},
        "posterior": {name: {} for name in ("k", "alpha", "beta", "mu_s", "f_rel_hz", "alpha_cc")},
        "predictive": {}, "design": {},
        "claim_context": {"oracle_initialized": False}, "validity": {},
    }


V4_OBJECTIVES = {
    "eig_raw": "raw",
    "eig_per_cost": "per_cost",
    "fixed_channel_balanced": "fixed_channel_balanced_traversal",
    "random_channel_balanced": "random_channel_balanced_traversal",
    "predictive_variance_raw": "raw",
    "predictive_variance_per_cost": "per_cost",
    "laplace_d_opt_raw": "raw",
    "laplace_d_opt_per_cost": "per_cost",
}


def complete_provenance(record):
    digest = "a" * 64
    record["provenance"] = {
        "started_at_utc": "2026-08-14T00:00:00Z",
        "ended_at_utc": "2026-08-14T00:01:00Z",
        "git_commit": "b" * 40,
        "seed": 7300,
        "command": ["experiment"],
        "configuration_sha256": digest,
        "data_sha256": {"synthetic://test": digest},
        "dependency_lock_sha256": digest,
        "python": "3.12.0",
        "slurm": {
            "job_id": "123", "array_job_id": "123", "array_task_id": "0",
            "node_list": "node001", "partition": "test",
        },
    }
    return record


def v4_policy(name, objective):
    initial_identities = [
        "pcv|0x1.d4c0000000000p+14|0x1.999999999999ap-5|0x1.9000000000000p+4",
        "mu_real|0x1.3880000000000p+13|0x0.0p+0|0x1.9000000000000p+4",
    ]
    selected_identity = (
        "mu_real|0x1.86a0000000000p+16|0x0.0p+0|0x1.9000000000000p+4"
    )
    ranking_identities = [selected_identity] + [
        f"pcv|{float(200000 + index).hex()}|{float(0.1).hex()}|{float(25).hex()}"
        for index in range(34)
    ]
    acquisition = {
        "objective": objective,
        "selected_key": "candidate-c",
        "selected_identity": selected_identity,
    }
    if name in ("eig_raw", "eig_per_cost"):
        acquisition["candidate_scores"] = [{
            "design_key": "candidate-c" if index == 0 else f"candidate-{index}",
            "design_identity": identity,
            "channel": "mu_real" if index == 0 else "pcv",
            "eig_mean_nats": 1.0, "eig_sd_nats": 0.1, "eig_se_nats": 0.07,
            "eig_ci95_nats": [0.86, 1.14],
            "top_selection_rate": 1.0 if index == 0 else 0.0,
            "utility_mean": (
                1.0 if objective == "raw" else 1.0 / (20.0 if index == 0 else 60.0)
            ),
            "replicate_scores_nats": [0.9, 1.1],
        } for index, identity in enumerate(ranking_identities)]
        acquisition["candidate_scores"].sort(
            key=lambda score: score["utility_mean"], reverse=True
        )
    elif name.startswith("predictive_variance") or name.startswith("laplace_d_opt"):
        method = "predictive_variance" if name.startswith("predictive") else "laplace_d_opt"
        acquisition.update({
            "method": method,
            "selected_identity": selected_identity,
            "candidate_scores": [{
                "design_key": "candidate-c" if index == 0 else f"candidate-{index}",
                "design_identity": identity,
                "channel": "mu_real" if index == 0 else "pcv",
                "method": method, "objective": objective,
                "score": 1.0,
                "score_units": "dimensionless_ratio" if method == "predictive_variance" else "nats",
                "utility": (
                    1.0 if objective == "raw" else 1.0 / (20.0 if index == 0 else 60.0)
                ),
                "noise_sigma": 0.1,
            } for index, identity in enumerate(ranking_identities)],
        })
        acquisition["candidate_scores"].sort(
            key=lambda score: score["utility"], reverse=True
        )
    elif name == "random_channel_balanced":
        acquisition.update({
            "selected_identity": selected_identity,
            "seed_namespace": "random_channel_balanced/v1", "seed": 12345,
        })
    recovery = {
        parameter: {
            "truth": 1.0, "median": 1.0, "p05": 0.9, "p95": 1.1,
            "absolute_error_pct": 0.0, "truth_in_ci90": True,
        }
        for parameter in ("k", "alpha", "beta", "mu_s", "f_rel_hz", "alpha_cc")
    }
    counts = {"pcv": 8, "mu_real": 6, "mu_imag": 6, "lm": 3}
    holdout = {
        channel: {
            "n_points": count, "relative_rmse_pct": 0.0,
            "median_absolute_relative_error_pct": 0.0,
            "latent_ci90_coverage_fraction": 1.0,
        }
        for channel, count in counts.items()
    }
    point_rows = []
    for channel, count in counts.items():
        for index in range(count):
            frequency = float(40000 + 1000 * index)
            flux = 0.075 if channel == "pcv" else 0.0
            temperature = 25.0
            point_rows.append({
                "design_key": f"{channel}-{index}",
                "design_identity": "|".join((
                    channel, frequency.hex(), float(flux).hex(), temperature.hex(),
                )),
                "channel": channel,
                "frequency_hz": frequency,
                "b_pk_t": flux,
                "temperature_c": temperature,
                "truth": 1.0,
                "posterior_median": 1.0,
                "posterior_p05": 0.9,
                "posterior_p95": 1.1,
                "covered_by_latent_ci90": True,
                "relative_error": 0.0,
            })
    def state(ids, _seed):
        ordered = sorted(ids)
        digest = hashlib.sha256(json.dumps(
            ordered, sort_keys=True, separators=(",", ":")
        ).encode()).hexdigest()
        diagnostics = {"valid": True}
        seed_payload = json.dumps({
            "namespace": "magcore-posterior-state-v1",
            "base_seed": 7300,
            "observed_design_identities": ordered,
        }, sort_keys=True, separators=(",", ":")).encode()
        return {
            "state_identity_sha256": digest,
            "observed_design_identities": ordered,
            "n_observations": len(ordered),
            "mcmc_seed_namespace": "magcore-posterior-state-v1",
            "mcmc_seed": int.from_bytes(
                hashlib.sha256(seed_payload).digest()[:4], "big", signed=False
            ),
            "fit_cache_reused": False,
            "sampler_diagnostics": diagnostics,
            "valid": True,
        }
    return {
        "policy": name,
        "objective": objective,
        "reached": True,
        "n_measurements_to_gate": 3,
        "modeled_cost_to_gate": 100.0,
        "validation_endpoints": {
            "used_for_acquisition_or_stopping": False,
            "evaluated_at_measurement_count": 3,
            "parameter_truth_in_ci90_count": 6,
            "parameter_recovery": recovery,
            "holdout_latent_mean": holdout,
            "holdout_point_records": point_rows,
        },
        "trajectory": [
            {
                "n_measurements": 2, "selected_keys": ["initial-a", "initial-b"],
                "selected_identities": initial_identities,
                "reached": False, "modeled_cost_units": 80.0,
                "pcv_latent_mean_ci90_half_width_pct": 9.0,
                "lm_latent_mean_ci90_half_width_pct": 6.0,
                "decision_state": state(initial_identities, 123),
                "acquisition": acquisition,
            },
            {
                "n_measurements": 3,
                "selected_keys": ["initial-a", "initial-b", "candidate-c"],
                "selected_identities": initial_identities + [selected_identity],
                "reached": True, "modeled_cost_units": 100.0,
                "pcv_latent_mean_ci90_half_width_pct": 8.0,
                "lm_latent_mean_ci90_half_width_pct": 5.0,
                "decision_state": state(initial_identities + [selected_identity], 124),
            },
        ],
    }


def valid_v4_record():
    record = complete_provenance(valid_record())
    digest = "a" * 64
    policies = {name: v4_policy(name, objective) for name, objective in V4_OBJECTIVES.items()}
    holdout_identities = sorted(
        row["design_identity"]
        for row in policies["eig_raw"]["validation_endpoints"]["holdout_point_records"]
    )
    holdout_digest = hashlib.sha256(json.dumps(
        holdout_identities, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()
    endpoint = {
        "both_reached_gate": True,
        "measurement_count_difference": 0,
        "measurement_count_reduction_pct": 0.0,
        "modeled_cost_difference": 0.0,
        "modeled_cost_reduction_pct": 0.0,
    }
    record["data"] = {
        "common_random_outcomes": True,
        "truth_sha256": digest,
        "outcome_manifest_sha256": digest,
        "holdout_manifest_sha256": holdout_digest,
        "candidate_count": 37,
        "holdout_count": 23,
    }
    record["sampler"] = {
        "policy_diagnostics": {
            name: policy["trajectory"][-1]["decision_state"]["sampler_diagnostics"]
            for name, policy in policies.items()
        }
    }
    record["design"] = {
        "benchmark_version": 4,
        "runtime_contract": {
            "max_measurements": 25, "n_walkers": 48, "n_steps": 5000,
            "burn": 1000, "objectives": ["raw", "per_cost"],
        },
        "policies": policies,
        "comparator_registry": deepcopy(BENCHMARK_V4_POLICY_REGISTRY),
        "direct_contrasts": deepcopy(BENCHMARK_V4_DIRECT_CONTRASTS),
        "paired_endpoints": {
            f"{name}_vs_fixed": deepcopy(endpoint)
            for name in policies if name != "fixed_channel_balanced"
        },
        "eig_estimator_replicates": 2,
        "eig_estimator_setting": {"n_outer": 10, "n_inner": 5, "n_replicates": 2},
        "estimator_decision_sha256": digest,
        "estimator_decision": {
            "schema_version": "eig-convergence-final/1.0",
            "selected_setting": {"n_outer": 10, "n_inner": 5, "n_replicates": 2},
            "selection_mode": "selected",
            "raw_claim_gate_passed": True,
            "per_cost_claim_gate_passed": True,
            "valid": True,
        },
        "posterior_state_cache": {
            "requested_fits": 16,
            "unique_fits": 2,
            "key": "sorted exact observed-design identities",
        },
        "primary_endpoints": {
            entry["policy"]: entry["primary_endpoint"]
            for entry in BENCHMARK_V4_POLICY_REGISTRY
        },
        "modeled_cost_seconds": {
            "pcv": 60.0, "mu_real": 20.0, "mu_imag": 20.0, "lm": 15.0,
        },
        "modeled_cost_interpretation": "prespecified assumption, not laboratory time",
        "gate_contract": {
            "quantity": "latent_mean_response",
            "pcv_ci_half_width_pct": 8.0,
            "lm_ci_half_width_pct": 5.0,
            "pcv_target": {
                "frequency_hz": 100000.0, "b_pk_t": 0.1, "temperature_c": 25.0,
            },
            "lm_target": {
                "frequency_hz": 100000.0, "b_pk_t": 0.0, "temperature_c": 25.0,
            },
        },
        "holdout_contract": {
            "total_points": 23,
            "channel_counts": {"pcv": 8, "mu_real": 6, "mu_imag": 6, "lm": 3},
            "used_for_acquisition_or_stopping": False,
        },
        "secondary_validation_endpoints": {
            "used_for_acquisition_or_stopping": False,
            "parameter_recovery": "declared",
            "holdout_prediction": "declared",
        },
    }
    record["validity"] = {
        f"{name}_convergence_valid": True for name in policies
    }
    record["predictive"] = {
        "gate": "two-output latent-mean-response precision gate",
        "targets": {
            "pcv": {
                "frequency_hz": 100000.0, "b_pk_t": 0.1, "temperature_c": 25.0,
                "ci90_half_width_pct_max": 8.0,
            },
            "lm": {
                "frequency_hz": 100000.0, "b_pk_t": 0.0, "temperature_c": 25.0,
                "ci90_half_width_pct_max": 5.0,
            },
        },
    }
    record["claim_context"] = {
        "synthetic": True,
        "matched_model": True,
        "prior_predictive_truth": True,
        "datasheet_centered_on_realized_truth": False,
        "oracle_initialized": False,
        "measured_data": False,
        "scope": (
            "algorithmic matched-model synthetic benchmark; "
            "not validated laboratory efficiency"
        ),
    }
    return record


def test_schema_rejects_five_dimensional_result():
    record = valid_record()
    record["posterior"].pop("alpha_cc")
    with pytest.raises(ValueError, match="exactly six"):
        validate_result(record)


def test_schema_rejects_incomplete_benchmark_v2():
    record = valid_record()
    record["design"] = {"benchmark_version": 2, "policies": {}}
    with pytest.raises(ValueError, match="benchmark v2"):
        validate_result(record)


def test_schema_accepts_complete_benchmark_v4():
    validate_result(valid_v4_record())


@pytest.mark.parametrize("mutation", ["missing_policy", "extra_policy", "missing_endpoint"])
def test_schema_v4_requires_exact_dynamic_policy_and_endpoint_sets(mutation):
    record = valid_v4_record()
    if mutation == "missing_policy":
        record["design"]["policies"].pop("laplace_d_opt_per_cost")
    elif mutation == "extra_policy":
        record["design"]["policies"]["unexpected"] = deepcopy(
            record["design"]["policies"]["fixed_channel_balanced"]
        )
    else:
        record["design"]["paired_endpoints"].pop("random_channel_balanced_vs_fixed")
    with pytest.raises(ValueError, match="benchmark v4"):
        validate_result(record)


def test_schema_v4_rejects_comparator_that_did_not_select_top_rank():
    record = valid_v4_record()
    acquisition = record["design"]["policies"]["predictive_variance_raw"] \
        ["trajectory"][0]["acquisition"]
    acquisition["selected_key"] = "not-the-top-candidate"
    record["design"]["policies"]["predictive_variance_raw"]["trajectory"][1] \
        ["selected_keys"][-1] = "not-the-top-candidate"
    with pytest.raises(ValueError, match="top-ranked"):
        validate_result(record)


def test_schema_v4_requires_shared_initial_observations_and_random_seed_namespace():
    record = valid_v4_record()
    random_policy = record["design"]["policies"]["random_channel_balanced"]
    random_policy["trajectory"][0]["selected_keys"] = ["different-a", "different-b"]
    random_policy["trajectory"][1]["selected_keys"][:2] = ["different-a", "different-b"]
    with pytest.raises(ValueError, match="same initial"):
        validate_result(record)
    record = valid_v4_record()
    random_policy = record["design"]["policies"]["random_channel_balanced"]
    random_policy["trajectory"][0]["acquisition"]["seed_namespace"] = "outcome_rng"
    with pytest.raises(ValueError, match="independent seed"):
        validate_result(record)


def test_schema_v4_recomputes_utility_final_endpoint_and_holdout_summary():
    record = valid_v4_record()
    record["design"]["policies"]["eig_per_cost"]["trajectory"][0] \
        ["acquisition"]["candidate_scores"][0]["utility_mean"] = 999.0
    with pytest.raises(ValueError, match="utility/objective"):
        validate_result(record)

    record = valid_v4_record()
    record["design"]["policies"]["eig_raw"]["n_measurements_to_gate"] = 4
    with pytest.raises(ValueError, match="final count/cost"):
        validate_result(record)

    record = valid_v4_record()
    record["design"]["policies"]["eig_raw"]["validation_endpoints"] \
        ["holdout_latent_mean"]["pcv"]["relative_rmse_pct"] = 1.0
    with pytest.raises(ValueError, match="not reconstructable"):
        validate_result(record)


def test_schema_v4_binds_every_state_diagnostic_and_estimator_decision():
    record = valid_v4_record()
    state = record["design"]["policies"]["eig_raw"]["trajectory"][0]["decision_state"]
    state["mcmc_seed"] += 1
    with pytest.raises(ValueError, match="decision-state"):
        validate_result(record)

    record = valid_v4_record()
    record["design"]["estimator_decision"]["selected_setting"]["n_outer"] += 1
    with pytest.raises(ValueError, match="does not match"):
        validate_result(record)


def test_heavy_runtime_requires_slurm(monkeypatch):
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    monkeypatch.delenv("SLURM_JOB_NODELIST", raising=False)
    with pytest.raises(RuntimeError, match="SLURM"):
        require_slurm()
    monkeypatch.setenv("SLURM_JOB_ID", "999")
    with pytest.raises(RuntimeError, match="SLURM"):
        require_slurm()
    monkeypatch.setenv("SLURM_JOB_NODELIST", "node001")
    require_slurm()
