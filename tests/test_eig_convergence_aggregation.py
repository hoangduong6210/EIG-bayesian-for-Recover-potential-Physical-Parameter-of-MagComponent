"""Focused tests for estimator-validation paired-bootstrap stability."""

from __future__ import annotations

from experiments.aggregate_eig_convergence import _comparison


def _record(a_scores: list[float], b_scores: list[float], *, namespace: str) -> dict:
    assert len(a_scores) == len(b_scores)
    return {
        "state": {"seed": 7100, "n_observations": 2},
        "estimator": {
            "namespace": namespace,
            "n_outer": 300 if namespace == "grid" else 1200,
            "n_inner": 100 if namespace == "grid" else 400,
            "n_replicates": len(a_scores),
            "prefix_nested_common_random_numbers": True,
            "seed": 710000002,
        },
        "candidate_scores": [
            {
                "design_key": "a",
                "channel_cost_units": 1.0,
                "replicate_scores_nats": a_scores,
            },
            {
                "design_key": "b",
                "channel_cost_units": 1.0,
                "replicate_scores_nats": b_scores,
            },
        ],
    }


def test_paired_bootstrap_reports_stable_replicate_mean_winner() -> None:
    candidate = _record([2.0] * 20, [1.0] * 20, namespace="grid")
    reference = _record([2.1] * 40, [0.9] * 40, namespace="reference")

    comparison = _comparison(candidate, reference, "raw", prefix=20)

    assert comparison["mean_top1_agreement"] is True
    assert comparison["top1_probability"] == 1.0
    assert comparison["candidate_winner_probability"] == 1.0
    assert comparison["reference_winner_probability"] == 1.0
    assert comparison["top1_probability_method"] == "paired-replicate-mean-bootstrap"
    assert comparison["top1_bootstrap_resamples"] == 4096


def test_paired_bootstrap_exposes_near_tie_hidden_by_mean_winner() -> None:
    # Candidate a wins by a tiny sample-mean margin, but resampled means often
    # select b. The reference mean selector is deliberately stable on a.
    candidate = _record([1.20, 0.81] * 10, [1.0] * 20, namespace="grid")
    reference = _record([1.02] * 40, [1.0] * 40, namespace="reference")

    first = _comparison(candidate, reference, "raw", prefix=20)
    second = _comparison(candidate, reference, "raw", prefix=20)

    assert first == second
    assert first["mean_top1_agreement"] is True
    assert 0.40 < first["top1_probability"] < 0.80
    assert first["candidate_winner_probability"] < 0.80
    assert first["reference_winner_probability"] == 1.0


def test_paired_bootstrap_preserves_per_cost_objective() -> None:
    candidate = _record([2.0] * 20, [1.5] * 20, namespace="grid")
    reference = _record([2.0] * 40, [1.5] * 40, namespace="reference")
    candidate["candidate_scores"][0]["channel_cost_units"] = 2.0
    reference["candidate_scores"][0]["channel_cost_units"] = 2.0

    raw = _comparison(candidate, reference, "raw", prefix=20)
    per_cost = _comparison(candidate, reference, "per_cost", prefix=20)

    assert raw["candidate_top_design_key"] == "a"
    assert per_cost["candidate_top_design_key"] == "b"
    assert raw["top1_probability"] == per_cost["top1_probability"] == 1.0


def test_comparison_is_invariant_to_candidate_input_order() -> None:
    candidate = _record([2.0] * 20, [1.0] * 20, namespace="grid")
    reference = _record([2.1] * 40, [0.9] * 40, namespace="reference")
    reversed_candidate = {**candidate, "candidate_scores": candidate["candidate_scores"][::-1]}
    reversed_reference = {**reference, "candidate_scores": reference["candidate_scores"][::-1]}

    assert _comparison(candidate, reference, "raw", 20) == _comparison(
        reversed_candidate, reversed_reference, "raw", 20,
    )


def test_comparison_rejects_nonmatching_rng_streams() -> None:
    candidate = _record([2.0] * 20, [1.0] * 20, namespace="grid")
    reference = _record([2.1] * 40, [0.9] * 40, namespace="reference")
    reference["estimator"]["seed"] += 1

    try:
        _comparison(candidate, reference, "raw", 20)
    except ValueError as error:
        assert "matching prefix-nested RNG streams" in str(error)
    else:
        raise AssertionError("comparison accepted nonmatching RNG streams")
