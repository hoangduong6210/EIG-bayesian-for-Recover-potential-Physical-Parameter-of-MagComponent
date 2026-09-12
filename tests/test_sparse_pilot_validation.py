"""Portable pilot summaries fail closed when diagnostic evidence is incomplete."""

import copy

import pytest

from magcore_calib.sparse_mixing import PARAMETER_NAMES
from scripts.validate_sparse_pilot import _equal_numeric, _reject_forbidden_keys, pairwise_summary


def _row(task_id, shift=0.0):
    return {
        "task_id": task_id,
        "parameter_summary": {name: {"sd": 1.0, "iqr": 2.0,
            "median": shift, "quantile_05": -2.0 + shift, "quantile_95": 2.0 + shift}
            for name in PARAMETER_NAMES},
        "diagnostics": {"ess": dict.fromkeys(PARAMETER_NAMES, 10000.0)},
    }


def test_pairwise_uses_declared_normalization():
    summary = pairwise_summary([_row("a"), _row("b", 0.15)])
    assert summary["comparison_count"] == 6
    assert summary["maximum_normalized_median_difference"] == pytest.approx(1.5)
    assert summary["maximum_normalized_tail_difference"] == pytest.approx(0.5)
    assert summary["undefined_comparisons"] == []


def test_missing_ess_is_not_silently_treated_as_agreement():
    left, right = _row("a"), _row("b")
    right["diagnostics"]["ess"]["alpha_cc"] = None
    summary = pairwise_summary([left, right])
    assert summary["comparison_count"] == 5
    assert summary["undefined_comparisons"] == ["a:b:alpha_cc:ess"]


def test_recomputed_diagnostics_reject_nan_and_missing_values():
    expected = {"tau": {"alpha": 100.0}, "valid": True}
    _equal_numeric(copy.deepcopy(expected), expected, "test")
    for invalid in (float("nan"), None, True, 102.0):
        observed = copy.deepcopy(expected)
        observed["tau"]["alpha"] = invalid
        with pytest.raises(ValueError, match="diagnostic value differs"):
            _equal_numeric(observed, expected, "test")
    with pytest.raises(ValueError, match="diagnostic keys differ"):
        _equal_numeric({"tau": {}}, expected, "test")


def test_nested_endpoint_keys_are_rejected():
    with pytest.raises(ValueError, match="forbidden endpoint key"):
        _reject_forbidden_keys({"notes": [{"HOLDOUT_error": 0.1}]}, ["holdout"])
    _reject_forbidden_keys({"notes": [{"tau": 20.0}]}, ["holdout"])
