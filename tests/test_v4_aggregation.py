"""Contracts for preregistered v4 paired-comparator aggregation."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from magcore_calib.study_plan import load_study_plan


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "generate_paper_artifacts.py"
SPEC = importlib.util.spec_from_file_location("generate_paper_artifacts_v4", SCRIPT)
assert SPEC and SPEC.loader
AGGREGATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AGGREGATOR)


def test_primary_contrasts_align_policy_objective_and_endpoint() -> None:
    plan = load_study_plan(ROOT)
    observed = {
        (spec.policy, spec.comparator, spec.endpoint)
        for spec in plan.comparator_benchmark.direct_contrasts
    }
    assert observed == {
        ("eig_raw", "predictive_variance_raw", "measurement_count_to_gate"),
        ("eig_raw", "laplace_d_opt_raw", "measurement_count_to_gate"),
        (
            "eig_per_cost", "predictive_variance_per_cost",
            "modeled_cost_to_gate",
        ),
        ("eig_per_cost", "laplace_d_opt_per_cost", "modeled_cost_to_gate"),
    }


def test_paired_policy_contrast_reports_complete_pairs_wtl_and_both_failures() -> None:
    result = AGGREGATOR.paired_policy_contrast(
        [4, 5, None, 6, None],
        [6, 5, 7, None, None],
        eig_policy="eig_raw",
        comparator_policy="predictive_variance_raw",
        endpoint="measurement_count_to_gate",
        bootstrap_seed=17,
    )
    assert result["difference_definition"] == "comparator_minus_eig"
    assert result["positive_difference_favors"] == "eig_raw"
    assert result["paired_differences"] == [2.0, 0.0]
    assert result["total_pair_count"] == 5
    assert result["complete_pair_count"] == 2
    assert result["incomplete_pair_count"] == 3
    assert result["eig_gate_failure_count"] == 2
    assert result["comparator_gate_failure_count"] == 2
    assert result["both_gate_failure_count"] == 1
    assert (result["wins"], result["ties"], result["losses"]) == (1, 1, 0)
    assert result["wtl_denominator"] == result["complete_pair_count"] == 2
    assert result["win_rate_complete_pairs"] == pytest.approx(0.5)
    assert result["paired_difference"] == {
        "mean": 1.0,
        "median": 1.0,
        "sample_sd": pytest.approx(2 ** 0.5),
        "bootstrap_mean_ci95_low": 0.0,
        "bootstrap_mean_ci95_high": 2.0,
    }


def test_paired_policy_contrast_retains_losses_and_is_deterministic() -> None:
    arguments = {
        "eig_policy": "eig_per_cost",
        "comparator_policy": "laplace_d_opt_per_cost",
        "endpoint": "modeled_cost_to_gate",
        "bootstrap_seed": 23,
    }
    first = AGGREGATOR.paired_policy_contrast(
        [100.0, 130.0, 90.0], [120.0, 110.0, 90.0], **arguments
    )
    second = AGGREGATOR.paired_policy_contrast(
        [100.0, 130.0, 90.0], [120.0, 110.0, 90.0], **arguments
    )
    assert first == second
    assert first["paired_differences"] == [20.0, -20.0, 0.0]
    assert (first["wins"], first["ties"], first["losses"]) == (1, 1, 1)


def test_paired_policy_contrast_treats_roundoff_as_a_tie() -> None:
    result = AGGREGATOR.paired_policy_contrast(
        [0.1 + 0.2], [0.3],
        eig_policy="eig_per_cost",
        comparator_policy="predictive_variance_per_cost",
        endpoint="modeled_cost_to_gate",
        bootstrap_seed=29,
    )
    assert (result["wins"], result["ties"], result["losses"]) == (0, 1, 0)


def test_paired_policy_contrast_keeps_statistic_keys_when_every_pair_fails() -> None:
    result = AGGREGATOR.paired_policy_contrast(
        [None, None], [None, None],
        eig_policy="eig_raw",
        comparator_policy="laplace_d_opt_raw",
        endpoint="measurement_count_to_gate",
        bootstrap_seed=31,
    )
    assert result["complete_pair_count"] == result["wtl_denominator"] == 0
    assert result["both_gate_failure_count"] == 2
    assert all(value is None for value in result["paired_difference"].values())
    assert result["win_rate_complete_pairs"] is None


def test_paired_policy_contrast_rejects_malformed_endpoints() -> None:
    arguments = {
        "eig_policy": "eig_raw",
        "comparator_policy": "predictive_variance_raw",
        "endpoint": "measurement_count_to_gate",
        "bootstrap_seed": 1,
    }
    with pytest.raises(ValueError, match="equal lengths"):
        AGGREGATOR.paired_policy_contrast([1], [1, 2], **arguments)
    with pytest.raises(ValueError, match="at least one seed"):
        AGGREGATOR.paired_policy_contrast([], [], **arguments)
    with pytest.raises(ValueError, match="nonfinite"):
        AGGREGATOR.paired_policy_contrast([1], [float("nan")], **arguments)
