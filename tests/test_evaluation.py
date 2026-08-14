"""Tests for endpoints that are deliberately independent of acquisition."""

import numpy as np

from magcore_calib.data import validation_library
from magcore_calib.evaluation import latent_holdout_summary
from magcore_calib.models import Geometry, MagneticParams


def test_latent_holdout_is_exact_for_degenerate_truth_posterior():
    truth = MagneticParams(
        k=2.5e-8, alpha=1.45, beta=2.55,
        mu_s=2200.0, f_rel_hz=3.5e5, alpha_cc=0.22,
    )
    samples = np.repeat(truth.to_active()[None, :], 20, axis=0)
    summary = latent_holdout_summary(
        samples, truth, validation_library(), Geometry()
    )
    assert set(summary) == {"pcv", "mu_real", "mu_imag", "lm"}
    for channel in summary.values():
        assert channel["relative_rmse_pct"] < 1e-10
        assert channel["median_absolute_relative_error_pct"] < 1e-10
        assert channel["latent_ci90_coverage_fraction"] == 1.0
