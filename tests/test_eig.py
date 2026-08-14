"""Cheap deterministic tests for EIG ranking correctness and uncertainty."""

from __future__ import annotations

from pathlib import Path
import tomllib

import numpy as np
import pytest

import magcore_calib.eig as eig
from magcore_calib.eig_convergence import (
    ConvergenceMetrics,
    ConvergenceThresholds,
    EIGSetting,
    SettingEvaluation,
    evaluate_convergence,
    select_smallest_stable_setting,
)
from magcore_calib.models import Channel, DesignPoint, Geometry
from magcore_calib.prior import DatasheetPrior, prior_center_vector
from magcore_calib.results import BENCHMARK_V4_POLICY_OBJECTIVES


def posterior_samples() -> np.ndarray:
    center = prior_center_vector(DatasheetPrior())
    scale = np.array([0.20, 0.08, 0.08, 0.15, 0.20, 0.08])
    return center + np.random.default_rng(11).normal(0.0, scale, size=(160, 6))


def library() -> list[DesignPoint]:
    return [
        DesignPoint(Channel.PCV, 1e5, 0.1),
        DesignPoint(Channel.MU_REAL, 1e5, 0.0),
        DesignPoint(Channel.MU_IMAG, 3e5, 0.0),
        DesignPoint(Channel.LM, 1e5, 0.0),
    ]


def test_design_seed_is_stable_and_identity_specific():
    point = library()[0]
    assert eig.stable_design_seed(7, point, 2) == eig.stable_design_seed(7, point, 2)
    assert eig.stable_design_seed(7, point, 2) != eig.stable_design_seed(7, point, 3)
    assert eig.stable_design_seed(7, point, 2) != eig.stable_design_seed(7, library()[1], 2)


def test_design_seed_uses_exact_float_identity_not_display_key():
    first = DesignPoint(Channel.PCV, 1e5, 0.1)
    second = DesignPoint(Channel.PCV, np.nextafter(1e5, np.inf), 0.1)
    assert first.key() == second.key()  # Human-facing key intentionally rounds.
    assert eig.stable_design_seed(7, first) != eig.stable_design_seed(7, second)


def test_candidate_scores_and_ranking_are_permutation_invariant():
    points = library()
    kwargs = dict(
        samples=posterior_samples(), seed=19, geometry=Geometry(),
        n_outer=20, n_inner=10, n_replicates=3, objective="per_cost",
    )
    forward = eig.rank_candidates_with_uncertainty(points, **kwargs)
    reverse = eig.rank_candidates_with_uncertainty(list(reversed(points)), **kwargs)
    assert [entry.design.key() for entry in forward] == [entry.design.key() for entry in reverse]
    first = {entry.design.key(): entry for entry in forward}
    second = {entry.design.key(): entry for entry in reverse}
    for key in first:
        assert first[key].replicate_scores_nats == second[key].replicate_scores_nats
        assert first[key].utility_mean == second[key].utility_mean
        assert first[key].top_selection_rate == second[key].top_selection_rate
    assert sum(entry.top_selection_rate for entry in forward) == pytest.approx(1.0)


def test_raw_and_per_cost_objectives_can_select_different_candidates(monkeypatch):
    points = [DesignPoint(Channel.PCV, 1e5, 0.1), DesignPoint(Channel.LM, 1e5, 0.0)]

    def fake_estimate(predictions, channel, **kwargs):
        return 2.0 if channel is Channel.PCV else 1.0

    monkeypatch.setattr(eig, "estimate_eig_from_predictions", fake_estimate)
    samples = posterior_samples()
    raw = eig.rank_candidates(
        points, samples, seed=1, geometry=Geometry(), n_replicates=3, objective="raw"
    )
    per_cost = eig.rank_candidates(
        points,
        samples,
        seed=1,
        geometry=Geometry(),
        n_replicates=3,
        objective="per_cost",
    )
    assert raw[0][0].channel is Channel.PCV
    assert per_cost[0][0].channel is Channel.LM


def test_modeled_cost_configuration_matches_runtime_policy_table():
    root = Path(__file__).resolve().parents[1]
    with (root / "configs" / "default.toml").open("rb") as stream:
        configured = tomllib.load(stream)["eig"]["modeled_cost_seconds"]
    assert configured == {
        channel.value: cost for channel, cost in eig.CHANNEL_COST_S.items()
    }


def test_preregistered_v4_policy_registry_matches_result_schema():
    root = Path(__file__).resolve().parents[1]
    with (root / "configs" / "default.toml").open("rb") as stream:
        configured = tomllib.load(stream)["study"]["comparator_benchmark"]
    assert configured["version"] == 4
    assert set(configured["policies"]) == set(BENCHMARK_V4_POLICY_OBJECTIVES)
    assert configured["reference_policy"] == "fixed_channel_balanced"
    assert configured["secondary_validation_used_for_stopping"] is False


@pytest.mark.parametrize("objective", ["unknown", "count"])
def test_invalid_objective_fails_closed(objective):
    with pytest.raises(ValueError, match="objective"):
        eig.rank_candidates_with_uncertainty(
            library(), posterior_samples(), seed=1, n_replicates=2, objective=objective
        )


def test_invalid_replicate_count_fails_closed():
    with pytest.raises(ValueError, match="replicates"):
        eig.rank_candidates_with_uncertainty(
            library(), posterior_samples(), seed=1, n_replicates=0
        )


def test_fixed_noise_sigma_uses_complete_posterior(monkeypatch):
    samples = np.zeros((5, 6))
    predictions = np.array([-2.0, 1.0, 9.0, 20.0, 1000.0])
    monkeypatch.setattr(eig, "predict_active_batch", lambda *args: predictions)
    design = DesignPoint(Channel.PCV, 1e5, 0.1)
    expected = eig.NOISE_FRACTION[Channel.PCV] * np.median(np.abs(predictions))
    assert eig.fixed_noise_sigma(samples, design) == pytest.approx(expected)


def test_estimator_uses_independent_prefix_streams(monkeypatch):
    samples = np.zeros((7, 6))
    samples[:, 0] = np.arange(1.0, 8.0)
    monkeypatch.setattr(
        eig, "predict_active_batch", lambda values, design, geometry: values[:, 0]
    )
    design = DesignPoint(Channel.PCV, 1e5, 0.1)
    seed, n_outer, n_inner = 1234, 5, 3
    outer_seed, inner_seed, noise_seed = np.random.SeedSequence(seed).spawn(3)
    outer = np.random.default_rng(outer_seed).choice(7, size=n_outer, replace=True)
    inner = np.random.default_rng(inner_seed).choice(7, size=n_inner, replace=True)
    sigma = eig.NOISE_FRACTION[Channel.PCV] * np.median(np.abs(samples[:, 0]))
    mu_outer, mu_inner = samples[outer, 0], samples[inner, 0]
    y = mu_outer + np.random.default_rng(noise_seed).normal(0.0, sigma, n_outer)
    constant = -np.log(sigma) - 0.5 * np.log(2.0 * np.pi)
    conditional = -0.5 * ((y - mu_outer) / sigma) ** 2 + constant
    terms = -0.5 * ((y[:, None] - mu_inner[None, :]) / sigma) ** 2 + constant
    expected = np.mean(conditional - eig.logsumexp(terms, axis=1) + np.log(n_inner))
    assert eig.estimate_eig(
        design, samples, seed=seed, n_outer=n_outer, n_inner=n_inner
    ) == pytest.approx(expected)


@pytest.mark.parametrize("name,value", [("n_outer", 0), ("n_inner", -1)])
def test_estimator_rejects_invalid_mc_budgets(name, value):
    kwargs = {"n_outer": 4, "n_inner": 3, name: value}
    with pytest.raises(ValueError, match=name):
        eig.estimate_eig(library()[0], posterior_samples(), seed=7, **kwargs)


def test_convergence_metrics_use_paired_top1_and_static_score_intervals():
    reference = {
        "a": [4.0, 1.0, 4.0, 4.0],
        "b": [1.0, 4.0, 1.0, 1.0],
        "c": [0.0, 0.0, 0.0, 0.0],
    }
    candidate = {
        "a": [3.8, 1.1, 3.9],
        "b": [1.1, 3.9, 1.2],
        "c": [0.0, 0.0, 0.0],
    }
    metrics = evaluate_convergence(
        candidate,
        reference,
        downstream_endpoint=5,
        reference_endpoint=5,
        thresholds=ConvergenceThresholds(
            min_top1_agreement_rate=1.0,
            min_rank_correlation=1.0,
            min_interval_overlap_rate=1.0,
        ),
    )
    assert metrics.top1_agreement_rate == 1.0
    assert metrics.rank_correlation == pytest.approx(1.0)
    assert metrics.interval_overlap_rate == 1.0
    assert metrics.downstream_endpoint_agrees
    assert metrics.stable


def test_convergence_fails_closed_for_key_mismatch_and_endpoint_drift():
    with pytest.raises(ValueError, match="keys differ"):
        evaluate_convergence(
            {"a": [1.0]}, {"b": [1.0]},
            downstream_endpoint=1, reference_endpoint=1,
        )
    metrics = evaluate_convergence(
        {"a": [1.0, 1.0]}, {"a": [1.0, 1.0]},
        downstream_endpoint=6, reference_endpoint=5,
    )
    assert metrics.downstream_endpoint_difference == 1.0
    assert not metrics.downstream_endpoint_agrees
    assert not metrics.stable


def test_select_smallest_stable_setting_uses_work_then_dimensions():
    stable = ConvergenceMetrics(1.0, 1.0, 1.0, 0.0, True, True)
    unstable = ConvergenceMetrics(1.0, 1.0, 1.0, 1.0, False, False)
    selected = select_smallest_stable_setting([
        SettingEvaluation(EIGSetting(20, 20, 2), stable),
        SettingEvaluation(EIGSetting(10, 20, 2), unstable),
        SettingEvaluation(EIGSetting(10, 10, 2), stable),
        SettingEvaluation(EIGSetting(10, 20, 1), stable),
    ])
    assert selected.setting == EIGSetting(10, 20, 1)


def test_select_smallest_stable_setting_fails_when_no_setting_qualifies():
    metrics = ConvergenceMetrics(0.0, 0.0, 0.0, 2.0, False, False)
    with pytest.raises(ValueError, match="no EIG setting"):
        select_smallest_stable_setting([
            SettingEvaluation(EIGSetting(10, 10, 2), metrics),
        ])
