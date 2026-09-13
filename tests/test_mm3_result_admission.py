"""Adversarial record checks without sampling or generating campaign outcomes."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from magcore_calib.inference import _de_checkpoint_report
from magcore_calib.model_mismatch import (
    MISMATCH_RESULT_SCHEMA, POLICIES, _validate_de_admission_diagnostic,
    payload_sha256, validate_mismatch_result,
)


def _diagnostic(taus=(100.0, 100.0, 100.0)):
    history = []
    previous, changes = None, 0
    for index, value in enumerate(taus, 1):
        tau = np.full(6, value)
        report, changes = _de_checkpoint_report(
            np.broadcast_to(0.0, (index * 20000, 48, 6)), np.array([0.3]),
            tau, np.array([0.0]), previous, changes,
        )
        previous = tau
        history.append(report)
    diagnostic = copy.deepcopy(history[-1])
    diagnostic["adaptive_sampling"] = {
        "minimum_retained_steps": 20000, "maximum_retained_steps": 800000,
        "check_interval_steps": 20000, "actual_retained_steps": len(history) * 20000,
        "extension_count": len(history) - 1, "stopped_reason": "converged",
        "checkpoint_history": history,
    }
    parity = {"rows": 48, "rtol": 1e-11, "atol": 1e-8, "maximum_absolute_difference": 0.0}
    diagnostic["sampler"] = {
        "method": "de_snooker", "implementation": "emcee.EnsembleSampler", "version": "3.1.6",
        "vectorize": True, "acceptance_window": "retained_only", "warmup_steps": 80000,
        "move_parameters": {
            "DEMove": {"weight": 0.8, "sigma": 1e-5, "gamma0": float(2.38 / np.sqrt(12)), "nsplits": 2, "randomize_split": True},
            "DESnookerMove": {"weight": 0.2, "gammas": 1.7, "nsplits": 4, "randomize_split": True},
        },
        "density_parity": {"initial": parity.copy(), "final": parity.copy()},
        "qualification_scope": "One adaptive ensemble; independent agreement established only at locked states.",
    }
    return diagnostic


def _replace_final(diagnostic, key, value):
    diagnostic[key] = copy.deepcopy(value)
    diagnostic["adaptive_sampling"]["checkpoint_history"][-1][key] = copy.deepcopy(value)


def test_consistent_three_checkpoint_admission():
    _validate_de_admission_diagnostic(_diagnostic())


def test_early_undefined_tau_can_recover_with_two_subsequent_stable_changes():
    _validate_de_admission_diagnostic(_diagnostic((np.nan, 100, 100, 100)))


@pytest.mark.parametrize("field", ["ess", "steps_per_tau", "tau"])
def test_forged_final_numeric_values_rejected_even_with_valid_flags(field):
    diagnostic = _diagnostic()
    changed = diagnostic[field].copy()
    changed["ln_k"] *= 2
    _replace_final(diagnostic, field, changed)
    with pytest.raises(ValueError):
        _validate_de_admission_diagnostic(diagnostic)


@pytest.mark.parametrize("fraction,value", [("acceptance_fraction", 0.01),
                                             ("acceptance_fraction", 0.9),
                                             ("finite_log_probability_fraction", 0.99)])
def test_forged_fraction_validity_rejected(fraction, value):
    diagnostic = _diagnostic()
    _replace_final(diagnostic, fraction, value)
    with pytest.raises(ValueError):
        _validate_de_admission_diagnostic(diagnostic)


@pytest.mark.parametrize("mutation", ["streak", "relative", "denominator", "early", "horizon", "history", "move", "version", "threshold", "final"])
def test_admission_rejects_history_and_runtime_tampering(mutation):
    diagnostic = _diagnostic()
    history = diagnostic["adaptive_sampling"]["checkpoint_history"]
    if mutation == "streak":
        history[0]["tau_stability"]["consecutive_stable_changes"] = 1
    elif mutation == "relative":
        history[1]["tau_stability"]["relative_change"]["ln_k"] = 0.09
    elif mutation == "denominator":
        history[1]["tau_stability"]["denominator"] = "previous_checkpoint_tau"
    elif mutation == "early":
        diagnostic = _diagnostic((100, 100, 100, 100))
    elif mutation == "horizon":
        diagnostic["adaptive_sampling"]["actual_retained_steps"] = 40000
    elif mutation == "history":
        history.pop(0)
    elif mutation == "move":
        diagnostic["sampler"]["move_parameters"]["DEMove"]["sigma"] = 0.1
    elif mutation == "version":
        diagnostic["sampler"]["version"] = "3.2.0"
    elif mutation == "threshold":
        diagnostic["thresholds"]["min_steps_per_tau"] = 1
    elif mutation == "final":
        diagnostic["acceptance_fraction"] = 0.4
    with pytest.raises(ValueError):
        _validate_de_admission_diagnostic(diagnostic)


def _result():
    policy = {
        "trajectory": [{"decision_state": {"valid": True, "sampler_diagnostics": _diagnostic()}}],
        "reached": False, "n_measurements_to_gate": None, "modeled_cost_to_gate": None,
        "mismatch_endpoints": {"holdout_latent_mean": {}, "holdout_pcv_by_temperature_c": {},
                               "holdout_point_records": [], "gate_truth_accuracy": {"false_confident": False}},
    }
    return {
        "schema_version": MISMATCH_RESULT_SCHEMA, "campaign_id": "MM-3", "config_sha256": "a" * 64,
        "run_id": "test", "seed": 10100, "scenario": {"name": "test"},
        "truth_anchor": {"values": {}, "sha256": payload_sha256({})},
        "data": {"common_candidate_outcomes_across_policies": True, "holdout_used_for_acquisition_or_stopping": False},
        "inference_model": {"name": "isothermal_steinmetz_one_pole_cole_cole", "structural_discrepancy_terms_in_likelihood": False},
        "policies": {name: copy.deepcopy(policy) for name in POLICIES}, "endpoint_contract": {},
        "validity": {f"{name}_convergence_valid": True for name in POLICIES},
        "provenance": {"sampler_method": "de_snooker", "sampler_qualification_manifest_sha256": "b" * 64,
                       "sampler_qualification_config_sha256": "c" * 64},
    }


def test_result_validator_invokes_numeric_admission_reconstruction():
    record = _result()
    validate_mismatch_result(record)
    diagnostic = record["policies"][POLICIES[0]]["trajectory"][0]["decision_state"]["sampler_diagnostics"]
    _replace_final(diagnostic, "acceptance_fraction", 0.01)
    with pytest.raises(ValueError):
        validate_mismatch_result(record)


def test_genuine_exhausted_failure_preserves_endpoint_free_rejection_route():
    record = _result()
    diagnostic = _diagnostic((20000.0,) * 40)
    diagnostic["adaptive_sampling"]["stopped_reason"] = "maximum_steps"
    policy = POLICIES[0]
    state = record["policies"][policy]["trajectory"][0]["decision_state"]
    state.update(valid=False, sampler_diagnostics=diagnostic)
    record["validity"][f"{policy}_convergence_valid"] = False
    with pytest.raises(ValueError, match="nonconverged policy"):
        validate_mismatch_result(record)
    diagnostic["sampler"]["version"] = "wrong"
    with pytest.raises(ValueError) as error:
        validate_mismatch_result(record)
    assert "nonconverged policy" not in str(error.value)


@pytest.mark.parametrize("field", ["sampler_method", "sampler_qualification_manifest_sha256", "sampler_qualification_config_sha256"])
def test_aggregation_binds_qualification_to_registered_plan(field):
    spec = importlib.util.spec_from_file_location("mm3_aggregate_tested", Path(__file__).resolve().parents[1] / "experiments/aggregate_model_mismatch.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    plan = SimpleNamespace(campaign_id="MM-3", estimator_decision_sha256="d" * 64,
                           sampler_method="de_snooker", sampler_qualification_manifest_sha256="b" * 64,
                           sampler_qualification_config_sha256="c" * 64)
    record = _result()
    record["provenance"]["estimator_decision_sha256"] = plan.estimator_decision_sha256
    module._validate_plan_provenance(record, plan)
    record["provenance"][field] = "different"
    with pytest.raises(ValueError):
        module._validate_plan_provenance(record, plan)
