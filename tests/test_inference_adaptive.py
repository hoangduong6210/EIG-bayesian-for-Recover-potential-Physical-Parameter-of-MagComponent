"""Adaptive MCMC extension tests."""

import numpy as np

from magcore_calib.inference import sample_emcee
from magcore_calib.models import Channel, DesignPoint, Observation
from magcore_calib.prior import DatasheetPrior


def test_sampler_extends_to_declared_maximum_when_short_chain_is_invalid():
    observation = Observation(
        DesignPoint(Channel.PCV, 100_000.0, 0.1, 25.0), 1.0e5, 5.0e3,
    )
    result = sample_emcee(
        [observation], DatasheetPrior(), n_walkers=12, n_steps=10, burn=2,
        max_steps=30, check_interval=10, seed=7,
    )
    adaptive = result.diagnostics["adaptive_sampling"]
    assert adaptive == {
        "minimum_retained_steps": 10,
        "maximum_retained_steps": 30,
        "check_interval_steps": 10,
        "actual_retained_steps": 30,
        "extension_count": 2,
        "stopped_reason": "maximum_steps",
    }
    assert result.chain.shape == (30, 12, 6)
    assert result.samples.shape == (360, 6)


def test_sampler_rejects_an_adaptive_maximum_below_minimum():
    observation = Observation(
        DesignPoint(Channel.PCV, 100_000.0, 0.1, 25.0), 1.0e5, 5.0e3,
    )
    with np.testing.assert_raises_regex(ValueError, "max_steps"):
        sample_emcee(
            [observation], DatasheetPrior(), n_walkers=12, n_steps=20,
            burn=2, max_steps=10, check_interval=5, seed=7,
        )
