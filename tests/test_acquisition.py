"""Cheap deterministic tests for comparator acquisition policies."""

from __future__ import annotations

import numpy as np
import pytest

import magcore_calib.acquisition as acquisition
from magcore_calib.models import Channel, DesignPoint, Geometry
from magcore_calib.prior import DatasheetPrior, prior_center_vector


def balanced_library() -> list[DesignPoint]:
    points: list[DesignPoint] = []
    for index, channel in enumerate(Channel):
        for frequency in (1.0e4, 1.0e5, 1.0e6):
            flux = 0.1 + index * 0.01 if channel is Channel.PCV else 0.0
            points.append(DesignPoint(channel, frequency, flux))
    return points


def posterior_samples() -> np.ndarray:
    center = prior_center_vector(DatasheetPrior())
    scales = np.array([0.18, 0.05, 0.06, 0.13, 0.17, 0.05])
    return center + np.random.default_rng(17).normal(size=(180, 6)) * scales


def identities(points: list[DesignPoint]) -> list[str]:
    return [acquisition.exact_design_identity(point) for point in points]


def test_random_balanced_order_is_deterministic_and_permutation_invariant():
    library = balanced_library()
    first = acquisition.random_channel_balanced_order(library, seed=41)
    repeated = acquisition.random_channel_balanced_order(library, seed=41)
    reversed_input = acquisition.random_channel_balanced_order(
        list(reversed(library)), seed=41
    )
    assert identities(first) == identities(repeated) == identities(reversed_input)
    assert len(set(identities(first))) == len(library)


def test_random_order_balances_every_prefix_and_excludes_selected():
    library = balanced_library()
    selected = [
        next(point for point in library if point.channel is Channel.PCV),
        next(point for point in library if point.channel is Channel.MU_REAL),
    ]
    order = acquisition.random_channel_balanced_order(
        library, seed=9, selected=selected
    )
    assert not set(identities(order)) & set(identities(selected))
    prefix = list(selected)
    for point in order:
        prefix.append(point)
        counts = [sum(item.channel is channel for item in prefix) for channel in Channel]
        assert max(counts) - min(counts) <= 1


def test_candidate_validation_rejects_duplicate_or_unknown_selection():
    library = balanced_library()
    with pytest.raises(ValueError, match="duplicate"):
        acquisition.random_channel_balanced_order(
            library, seed=1, selected=[library[0], library[0]]
        )
    with pytest.raises(ValueError, match="belong"):
        acquisition.random_channel_balanced_order(
            library, seed=1,
            selected=[DesignPoint(Channel.PCV, 9.9e9, 0.1)],
        )


def test_exact_identity_distinguishes_display_key_collision():
    first = DesignPoint(Channel.PCV, 1.0e5, 0.1)
    second = DesignPoint(Channel.PCV, np.nextafter(1.0e5, np.inf), 0.1)
    assert first.key() == second.key()
    assert acquisition.exact_design_identity(first) != acquisition.exact_design_identity(second)


def test_predictive_variance_is_dimensionless_epistemic_over_noise_variance():
    samples = posterior_samples()
    design = DesignPoint(Channel.PCV, 1.0e5, 0.1)
    predictions = acquisition.predict_active_batch(samples, design, None)
    sigma = acquisition.NOISE_FRACTION[Channel.PCV] * np.median(np.abs(predictions))
    expected = np.var(predictions, ddof=1) / sigma**2
    score, actual_sigma = acquisition.predictive_variance_score(design, samples)
    assert score == pytest.approx(expected)
    assert actual_sigma == pytest.approx(sigma)


def test_predictive_variance_cost_objective_and_stable_tie_break(monkeypatch):
    samples = posterior_samples()
    first = DesignPoint(Channel.PCV, 3.0e5, 0.1)
    second = DesignPoint(Channel.PCV, 1.0e5, 0.1)
    library = [first, second]
    monkeypatch.setattr(
        acquisition,
        "predict_active_batch",
        lambda values, design, geometry: np.linspace(1.0, 2.0, len(values)),
    )
    raw = acquisition.rank_predictive_variance(library, samples)
    reversed_raw = acquisition.rank_predictive_variance(list(reversed(library)), samples)
    assert identities([row.design for row in raw]) == identities(
        [row.design for row in reversed_raw]
    )
    assert acquisition.exact_design_identity(raw[0].design) == min(identities(library))
    cost = acquisition.rank_predictive_variance(
        library, samples, objective="per_cost", costs={Channel.PCV: 10.0}
    )
    assert cost[0].utility == pytest.approx(cost[0].score / 10.0)


def test_pcv_finite_difference_gradient_matches_analytic_gradient():
    center = prior_center_vector(DatasheetPrior())
    design = DesignPoint(Channel.PCV, 1.0e5, 0.1)
    prediction = acquisition.predict_active_batch(center[None, :], design)[0]
    expected = np.array(
        [prediction, prediction * np.log(design.f_hz),
         prediction * np.log(design.b_pk_t), 0.0, 0.0, 0.0]
    )
    actual = acquisition.finite_difference_gradient(design, center)
    assert actual == pytest.approx(expected, rel=2.0e-6, abs=1.0e-10)


def test_laplace_score_matches_rank_one_gaussian_information():
    samples = posterior_samples()
    design = DesignPoint(Channel.MU_REAL, 1.0e5, 0.0)
    center = np.mean(samples, axis=0)
    covariance = np.cov(samples, rowvar=False, ddof=1)
    gradient = acquisition.finite_difference_gradient(design, center, Geometry())
    predictions = acquisition.predict_active_batch(samples, design, Geometry())
    sigma = acquisition.NOISE_FRACTION[design.channel] * np.median(np.abs(predictions))
    expected = 0.5 * np.log1p(gradient @ covariance @ gradient / sigma**2)
    score, actual_sigma = acquisition.laplace_information_score(
        design, samples, Geometry()
    )
    assert score == pytest.approx(expected, rel=1.0e-10)
    assert actual_sigma == pytest.approx(sigma)


def test_rankers_never_return_selected_candidates():
    library = balanced_library()[:6]
    selected = library[:2]
    samples = posterior_samples()
    predictive = acquisition.rank_predictive_variance(
        library, samples, selected=selected, geometry=Geometry()
    )
    laplace = acquisition.rank_laplace_d_opt(
        library, samples, selected=selected, geometry=Geometry(),
        objective="per_cost",
    )
    selected_ids = set(identities(selected))
    assert not selected_ids & set(identities([row.design for row in predictive]))
    assert not selected_ids & set(identities([row.design for row in laplace]))
    assert len(predictive) == len(laplace) == len(library) - len(selected)


def test_laplace_ranking_uses_same_stable_tie_break(monkeypatch):
    samples = posterior_samples()
    library = [
        DesignPoint(Channel.MU_REAL, 3.0e5, 0.0),
        DesignPoint(Channel.MU_REAL, 1.0e5, 0.0),
    ]
    monkeypatch.setattr(
        acquisition,
        "_laplace_score_from_state",
        lambda *args, **kwargs: (1.0, 2.0),
    )
    forward = acquisition.rank_laplace_d_opt(library, samples)
    reverse = acquisition.rank_laplace_d_opt(list(reversed(library)), samples)
    expected = sorted(identities(library))
    assert identities([row.design for row in forward]) == expected
    assert identities([row.design for row in reverse]) == expected


def test_selectors_fail_when_all_candidates_are_already_selected():
    library = balanced_library()[:2]
    samples = posterior_samples()
    with pytest.raises(ValueError, match="no unobserved"):
        acquisition.select_predictive_variance(library, samples, selected=library)
    with pytest.raises(ValueError, match="no unobserved"):
        acquisition.select_laplace_d_opt(library, samples, selected=library)
