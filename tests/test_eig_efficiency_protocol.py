"""Focused invariance tests for the preregistered acquisition runner."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))

import eig_efficiency as experiment  # noqa: E402
from magcore_calib.acquisition import AcquisitionScore  # noqa: E402
from magcore_calib.data import default_library  # noqa: E402
from magcore_calib.eig import CandidateScore  # noqa: E402
from magcore_calib.inference import PosteriorResult  # noqa: E402
from magcore_calib.models import Geometry, Observation  # noqa: E402
from magcore_calib.prior import DatasheetPrior  # noqa: E402


def test_posterior_state_seed_is_order_invariant_and_uint32():
    state = ("mu_real|a", "pcv|b", "lm|c")
    forward = experiment._posterior_state_seed(7300, state)
    reverse = experiment._posterior_state_seed(7300, tuple(reversed(state)))
    # The helper itself canonicalizes the state as a defensive boundary.
    assert forward == experiment._posterior_state_seed(7300, tuple(sorted(state)))
    assert reverse == forward
    assert 0 <= forward <= 2**32 - 1


def test_all_policy_paths_are_invariant_to_execution_order(monkeypatch):
    library = default_library()
    outcomes = {
        point.exact_key(): Observation(point, 1.0, 0.1) for point in library
    }
    samples = np.zeros((4, 6), dtype=float)

    def fake_fit(*_args, seed, **_kwargs):
        return PosteriorResult(
            chain=np.empty((0, 0, 6)), samples=samples,
            log_probabilities=np.empty(0), diagnostics={"valid": True, "seed": seed},
        )

    def fake_eig(points, *_args, objective, **_kwargs):
        return [
            CandidateScore(
                design=point, eig_mean_nats=1.0, eig_sd_nats=0.0,
                eig_se_nats=0.0, eig_ci95_low_nats=1.0,
                eig_ci95_high_nats=1.0,
                utility_mean=1.0 if objective == "raw" else 1.0,
                top_selection_rate=1.0 if index == 0 else 0.0,
                replicate_scores_nats=(1.0, 1.0),
            )
            for index, point in enumerate(points)
        ]

    def fake_comparator(points, *_args, selected, objective, **_kwargs):
        remaining = [point for point in points if point not in selected]
        method = "predictive_variance"
        return [
            AcquisitionScore(point, method, objective, 1.0, 1.0, 0.1)
            for point in remaining
        ]

    def fake_laplace(points, *_args, selected, objective, **_kwargs):
        return [
            AcquisitionScore(point, "laplace_d_opt", objective, 1.0, 1.0, 0.1)
            for point in points if point not in selected
        ]

    monkeypatch.setattr(experiment, "sample_emcee", fake_fit)
    monkeypatch.setattr(experiment, "latent_mean_ci_half_width_pct", lambda *_args: 10.0)
    monkeypatch.setattr(experiment, "rank_candidates_with_uncertainty", fake_eig)
    monkeypatch.setattr(experiment, "rank_predictive_variance", fake_comparator)
    monkeypatch.setattr(experiment, "rank_laplace_d_opt", fake_laplace)

    objectives = {
        name: "per_cost" if name.endswith("_per_cost") else "raw"
        for name in experiment.BENCHMARK_V4_POLICIES
    }

    def execute(order):
        cache = {}
        output = {}
        for policy in order:
            result, _, _ = experiment.run_policy(
                policy, library, outcomes, DatasheetPrior(), Geometry(), seed=7300,
                max_measurements=3, n_walkers=12, n_steps=10, burn=2,
                n_outer=1, n_inner=1, eig_replicates=2,
                objective=objectives[policy], fit_cache=cache,
            )
            output[policy] = [
                {
                    "selected": row["selected_identities"],
                    "state_seed": row["decision_state"]["mcmc_seed"],
                    "diagnostics": row["decision_state"]["sampler_diagnostics"],
                }
                for row in result["trajectory"]
            ]
        return output

    forward = execute(experiment.BENCHMARK_V4_POLICIES)
    reverse = execute(tuple(reversed(experiment.BENCHMARK_V4_POLICIES)))
    assert forward == reverse
