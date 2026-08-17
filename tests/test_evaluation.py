"""Tests for endpoints that are deliberately independent of acquisition."""

import numpy as np

from magcore_calib.data import validation_library
from magcore_calib.evaluation import latent_holdout_evaluation, latent_holdout_summary
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


def test_latent_holdout_point_rows_reconstruct_all_23_predictions():
    truth = MagneticParams(
        k=2.5e-8, alpha=1.45, beta=2.55,
        mu_s=2200.0, f_rel_hz=3.5e5, alpha_cc=0.22,
    )
    samples = np.repeat(truth.to_active()[None, :], 20, axis=0)
    evaluation = latent_holdout_evaluation(
        samples, truth, validation_library(), Geometry()
    )
    rows = evaluation["points"]
    assert len(rows) == 23
    assert len({row["design_identity"] for row in rows}) == 23
    assert {channel: sum(row["channel"] == channel for row in rows) for channel in (
        "pcv", "mu_real", "mu_imag", "lm",
    )} == {"pcv": 8, "mu_real": 6, "mu_imag": 6, "lm": 3}
    for row in rows:
        assert set(row) == {
            "design_key", "design_identity", "channel", "frequency_hz", "b_pk_t",
            "temperature_c", "truth", "posterior_median", "posterior_p05",
            "posterior_p95", "covered_by_latent_ci90", "relative_error",
        }
        assert row["covered_by_latent_ci90"] is True
        assert abs(row["relative_error"]) < 1e-12
