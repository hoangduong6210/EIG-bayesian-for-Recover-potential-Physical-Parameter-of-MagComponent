"""Prospective sampler admission requires every registered diagnostic."""

import copy

import pytest

from magcore_calib.sparse_mixing import PARAMETER_NAMES
from scripts.validate_sparse_mixing_v2 import classify_state, validate_criteria


@pytest.fixture
def criteria():
    return {
        "minimum_finite_log_probability_fraction": 1.0,
        "minimum_steps_per_tau": 50.0, "minimum_effective_sample_size": 400.0,
        "acceptance_range": [0.05, 0.80], "tau_stability_checkpoints": [640000, 800000],
        "maximum_relative_tau_change": 0.1,
        "maximum_median_difference_pooled_sd": 0.1,
        "maximum_tail_difference_pooled_iqr": 0.15,
    }


def _rows():
    return [{
        "task_id": f"ensemble_{i}",
        "diagnostics": {"finite_log_probability_fraction": 1.0, "acceptance_fraction": 0.15,
            "steps_per_tau": dict.fromkeys(PARAMETER_NAMES, 60.0),
            "ess": dict.fromkeys(PARAMETER_NAMES, 10000.0), "valid": False},
        "relative_tau_change": dict.fromkeys(PARAMETER_NAMES, 0.05),
        "parameter_summary": {name: {"sd": 1.0, "iqr": 2.0, "median": 0.0,
            "quantile_05": -2.0, "quantile_95": 2.0} for name in PARAMETER_NAMES},
    } for i in range(8)]


def test_registered_rule_overrides_legacy_acceptance_flag(criteria):
    result = classify_state(_rows(), criteria)
    assert result["criteria_passed"] is True
    assert result["comparison_count"] == 28 * 6


@pytest.mark.parametrize("group,value,reason", [
    ("steps_per_tau", 49.9, "steps_per_tau"),
    ("ess", None, "ess"),
    ("ess", float("nan"), "ess"),
])
def test_one_parameter_in_one_ensemble_blocks_state(criteria, group, value, reason):
    rows = _rows()
    rows[7]["diagnostics"][group]["alpha_cc"] = value
    result = classify_state(rows, criteria)
    assert result["criteria_passed"] is False
    assert any(reason in item for item in result["reason_codes"])


def test_thresholds_are_read_from_config(criteria):
    rows = _rows()
    criteria["minimum_steps_per_tau"] = 61.0
    assert not classify_state(rows, criteria)["criteria_passed"]
    criteria["minimum_steps_per_tau"] = 50.0
    criteria["acceptance_range"] = [0.2, 0.6]
    assert not classify_state(rows, criteria)["criteria_passed"]


def test_tail_and_median_separation_use_registered_scales(criteria):
    rows = _rows()
    rows[-1]["parameter_summary"]["alpha_cc"]["median"] = 0.11
    rows[-1]["parameter_summary"]["alpha_cc"]["quantile_95"] = 2.31
    result = classify_state(rows, criteria)
    assert not result["criteria_passed"]
    assert result["maximum_normalized_median_difference"] == pytest.approx(1.1)
    assert result["maximum_normalized_tail_difference"] == pytest.approx(0.31 / 0.30)
    criteria["maximum_median_difference_pooled_sd"] = 0.12
    criteria["maximum_tail_difference_pooled_iqr"] = 0.16
    assert classify_state(rows, criteria)["criteria_passed"]


def test_missing_or_duplicate_ensemble_blocks_state(criteria):
    assert not classify_state(_rows()[:-1], criteria)["criteria_passed"]
    rows = _rows()
    rows[-1]["task_id"] = rows[0]["task_id"]
    assert not classify_state(rows, criteria)["criteria_passed"]


def test_stability_and_finiteness_block_state(criteria):
    rows = _rows()
    rows[0]["relative_tau_change"]["alpha_cc"] = 0.101
    assert not classify_state(rows, criteria)["criteria_passed"]
    rows = _rows()
    rows[0]["diagnostics"]["finite_log_probability_fraction"] = 0.999
    assert not classify_state(rows, criteria)["criteria_passed"]


def test_invalid_criteria_fail_before_chain_read(criteria):
    validate_criteria(criteria, [640000, 800000])
    for key, value in (("maximum_relative_tau_change", float("nan")),
                       ("minimum_effective_sample_size", True),
                       ("acceptance_range", [0.8, 0.05]),
                       ("tau_stability_checkpoints", [800000, 640000])):
        broken = copy.deepcopy(criteria)
        broken[key] = value
        with pytest.raises(ValueError):
            validate_criteria(broken, [640000, 800000])
