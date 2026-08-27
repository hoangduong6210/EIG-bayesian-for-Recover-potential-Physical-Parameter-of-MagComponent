"""Scientific-contract tests for the prospective MM-1 campaign."""

from __future__ import annotations

import json
import importlib.util
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from magcore_calib.forward import predict_one
from magcore_calib.model_mismatch import (
    MISMATCH_RESULT_SCHEMA, POLICIES, gate_truth_evaluation,
    load_model_mismatch_plan, mismatch_candidate_library,
    mismatch_holdout_evaluation, mismatch_predict_one,
    mismatch_validation_library, stable_mismatch_outcomes,
    validate_mismatch_result,
)
from magcore_calib.models import Channel, DesignPoint, Geometry, MagneticParams


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "model_mismatch.toml"
TRUTH = MagneticParams(
    k=1.2e-3, alpha=1.45, beta=2.35,
    mu_s=2100.0, f_rel_hz=2.2e5, alpha_cc=0.18,
)


def test_preregistered_plan_is_disjoint_and_complete():
    plan = load_model_mismatch_plan(CONFIG)
    assert plan.campaign_id == "MM-1"
    assert plan.estimator_source_release_id == "20260817T072230Z_401e3030fe13"
    assert plan.estimator_decision_sha256 == (
        "eb334ae2c188f12e7f544be71b6f0c40be15913ceec0df60e5bf9a9258ed82b6"
    )
    assert len(plan.seeds) == 30
    assert len(plan.scenarios) == 4
    assert plan.task_count == 120
    assert not set(plan.seeds) & set(plan.forbidden_development_seeds)
    assert set(range(7300, 7330)) <= set(plan.forbidden_development_seeds)
    assert plan.policies == POLICIES
    assert plan.task(0) == (plan.scenarios[0], 8100)
    assert plan.task(30) == (plan.scenarios[1], 8100)
    assert plan.task(119) == (plan.scenarios[-1], 8129)


def test_candidate_and_holdout_contracts_are_unique_and_disjoint():
    plan = load_model_mismatch_plan(CONFIG)
    candidates = mismatch_candidate_library(plan.temperatures_c)
    holdout = mismatch_validation_library(plan.temperatures_c)
    assert len(candidates) == 37
    assert len(holdout) == 39
    assert len({point.exact_key() for point in candidates}) == 37
    assert not (
        {point.exact_key() for point in candidates}
        & {point.exact_key() for point in holdout}
    )
    assert sum(point.channel is Channel.PCV for point in candidates) == 18
    assert {
        point.temperature_c for point in candidates if point.channel is Channel.PCV
    } == {25.0}


def test_matched_control_exactly_recovers_inference_forward_model():
    plan = load_model_mismatch_plan(CONFIG)
    matched = plan.scenario("matched_control")
    for point in mismatch_candidate_library(plan.temperatures_c):
        assert mismatch_predict_one(TRUTH, matched, point, Geometry()) == pytest.approx(
            predict_one(TRUTH, point, Geometry()), rel=2e-15
        )


def test_scenarios_create_declared_structural_discrepancy():
    plan = load_model_mismatch_plan(CONFIG)
    permeability = DesignPoint(Channel.MU_IMAG, 7.0e5, 0.0, 25.0)
    hot_loss = DesignPoint(Channel.PCV, 3.0e5, 0.2, 100.0)
    matched = plan.scenario("matched_control")
    two_pole = plan.scenario("permeability_two_pole")
    core_loss = plan.scenario("core_loss_temperature_curvature")
    assert mismatch_predict_one(TRUTH, two_pole, permeability) != pytest.approx(
        mismatch_predict_one(TRUTH, matched, permeability)
    )
    assert mismatch_predict_one(TRUTH, core_loss, hot_loss) > mismatch_predict_one(
        TRUTH, matched, hot_loss
    )


def test_common_noise_is_candidate_indexed_and_shared_across_scenarios():
    plan = load_model_mismatch_plan(CONFIG)
    library = mismatch_candidate_library(plan.temperatures_c)[:12]
    matched = plan.scenario("matched_control")
    combined = plan.scenario("combined_mismatch")
    first = stable_mismatch_outcomes(
        TRUTH, matched, library, seed=100_001, geometry=Geometry()
    )
    reordered = stable_mismatch_outcomes(
        TRUTH, matched, list(reversed(library)), seed=100_001, geometry=Geometry()
    )
    changed_dgp = stable_mismatch_outcomes(
        TRUTH, combined, library, seed=100_001, geometry=Geometry()
    )
    assert {
        key: (value.value, value.sigma) for key, value in first.items()
    } == {
        key: (value.value, value.sigma) for key, value in reordered.items()
    }
    for point in library:
        identity = point.exact_key()
        matched_mean = mismatch_predict_one(TRUTH, matched, point, Geometry())
        changed_mean = mismatch_predict_one(TRUTH, combined, point, Geometry())
        matched_z = (first[identity].value - matched_mean) / first[identity].sigma
        changed_z = (
            changed_dgp[identity].value - changed_mean
        ) / changed_dgp[identity].sigma
        assert matched_z == pytest.approx(changed_z, abs=1e-12)


def test_holdout_and_false_confidence_are_evaluated_against_dgp_truth():
    plan = load_model_mismatch_plan(CONFIG)
    matched = plan.scenario("matched_control")
    samples = np.repeat(TRUTH.to_active()[None, :], 20, axis=0)
    holdout = mismatch_holdout_evaluation(
        samples, TRUTH, matched,
        mismatch_validation_library(plan.temperatures_c), Geometry(),
    )
    assert set(holdout["summary"]) == {"pcv", "mu_real", "mu_imag", "lm"}
    assert holdout["summary"]["pcv"]["relative_rmse_pct"] < 1e-10
    assert holdout["summary"]["pcv"]["latent_ci90_coverage_fraction"] == 1.0
    gate = gate_truth_evaluation(
        samples, TRUTH, matched, reached_precision_gate=True, geometry=Geometry(),
        pcv_error_threshold_pct=8.0, lm_error_threshold_pct=5.0,
    )
    assert gate["target_accuracy_passed"] is True
    assert gate["false_confident"] is False


def test_plan_rejects_reuse_of_observed_v4_seed(tmp_path):
    text = CONFIG.read_text(encoding="utf-8").replace("8100, 8101", "7300, 8101", 1)
    path = tmp_path / "invalid.toml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="overlap forbidden"):
        load_model_mismatch_plan(path)


def test_result_validator_rejects_false_confidence_without_gate():
    def endpoint(false_confident=False):
        return {
            "holdout_latent_mean": {}, "holdout_pcv_by_temperature_c": {},
            "holdout_point_records": [],
            "gate_truth_accuracy": {"false_confident": false_confident},
        }

    record = {
        "schema_version": MISMATCH_RESULT_SCHEMA, "campaign_id": "MM-1",
        "config_sha256": "0" * 64, "run_id": "test", "seed": 8100,
        "scenario": {"name": "matched_control"},
        "truth_anchor": {
            "values": {},
            "sha256": (
                "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"
            ),
        },
        "data": {
            "common_candidate_outcomes_across_policies": True,
            "holdout_used_for_acquisition_or_stopping": False,
        },
        "inference_model": {
            "name": "isothermal_steinmetz_one_pole_cole_cole",
            "structural_discrepancy_terms_in_likelihood": False,
        },
        "policies": {
            policy: {
                "reached": False, "n_measurements_to_gate": None,
                "modeled_cost_to_gate": None,
                "mismatch_endpoints": endpoint(policy == POLICIES[0]),
            }
            for policy in POLICIES
        },
        "endpoint_contract": {},
        "validity": {f"{policy}_convergence_valid": True for policy in POLICIES},
        "provenance": {},
    }
    with pytest.raises(ValueError, match="False confidence|false confidence"):
        validate_mismatch_result(record)


def test_task_cli_is_deterministic():
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "model_mismatch_plan.py"),
         "task", "--config", str(CONFIG), "--task-id", "31"],
        check=True, capture_output=True, text=True,
    )
    assert json.loads(completed.stdout) == {
        "scenario": "permeability_two_pole", "seed": 8101,
        "task_id": "permeability_two_pole_seed8101",
    }


def test_aggregation_keeps_failures_out_of_reached_only_summaries():
    spec = importlib.util.spec_from_file_location(
        "aggregate_model_mismatch",
        ROOT / "experiments" / "aggregate_model_mismatch.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def policy_result(reached: bool, count, cost, false_confident: bool):
        channel_summary = {
            "relative_rmse_pct": 10.0,
            "latent_ci90_coverage_fraction": 0.5,
        }
        return {
            "reached": reached, "n_measurements_to_gate": count,
            "modeled_cost_to_gate": cost,
            "mismatch_endpoints": {
                "gate_truth_accuracy": {"false_confident": false_confident},
                "holdout_latent_mean": {
                    channel: dict(channel_summary)
                    for channel in ("pcv", "mu_real", "mu_imag", "lm")
                },
                "holdout_pcv_by_temperature_c": {
                    "25.0": dict(channel_summary),
                    "60.0": dict(channel_summary),
                    "100.0": dict(channel_summary),
                },
            },
        }

    records = [
        {"policies": {"eig_raw": policy_result(True, 5, 175.0, True)}},
        {"policies": {"eig_raw": policy_result(False, None, None, False)}},
    ]
    summary = module._policy_summary(records, "eig_raw")
    assert summary["failure_to_gate_count"] == 1
    assert summary["measurement_count_reached_only"]["mean"] == 5.0
    assert summary["false_confidence_rate_all_seeds"] == 0.5
    assert summary["false_confidence_rate_given_gate"] == 1.0


def test_paired_contrast_uses_existing_sign_and_deterministic_bootstrap():
    spec = importlib.util.spec_from_file_location(
        "aggregate_model_mismatch_contrast",
        ROOT / "experiments" / "aggregate_model_mismatch.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    records = [
        {"policies": {
            "eig_raw": {"n_measurements_to_gate": 5},
            "predictive_variance_raw": {"n_measurements_to_gate": 6},
        }},
        {"policies": {
            "eig_raw": {"n_measurements_to_gate": 5},
            "predictive_variance_raw": {"n_measurements_to_gate": 5},
        }},
        {"policies": {
            "eig_raw": {"n_measurements_to_gate": None},
            "predictive_variance_raw": {"n_measurements_to_gate": 7},
        }},
    ]
    first = module._contrast_summary(
        records, "eig_raw", "predictive_variance_raw",
        "n_measurements_to_gate", scenario="test_scenario",
    )
    second = module._contrast_summary(
        records, "eig_raw", "predictive_variance_raw",
        "n_measurements_to_gate", scenario="test_scenario",
    )
    assert first == second
    assert first["difference_definition"] == "comparator_minus_policy"
    assert first["paired_differences"] == [1.0, 0.0]
    assert first["policy_wins"] == 1
    assert first["ties"] == 1
    assert first["policy_gate_failure_count"] == 1
    assert first["paired_difference"]["sample_sd"] == pytest.approx(2 ** -0.5)
