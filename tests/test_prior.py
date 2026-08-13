import math

import numpy as np

from magcore_calib.prior import DatasheetPrior, log_prior_active, prior_center_vector


def test_prior_mode_is_declared_sampler_center():
    spec = DatasheetPrior()
    center = prior_center_vector(spec)
    assert log_prior_active(center, spec) > log_prior_active(center + 0.1, spec)


def test_one_sd_in_dex_has_half_log_density_penalty():
    spec = DatasheetPrior(log10_k_sd=0.15)
    center = prior_center_vector(spec)
    displaced = center.copy()
    displaced[0] += 0.15 * math.log(10.0)
    assert math.isclose(
        log_prior_active(displaced, spec) - log_prior_active(center, spec),
        -0.5, rel_tol=0.0, abs_tol=1e-12,
    )


def test_prior_rejects_wrong_dimension_and_bounds():
    spec = DatasheetPrior()
    assert log_prior_active(np.zeros(5), spec) == -math.inf
    x = prior_center_vector(spec)
    x[5] = 0.9
    assert log_prior_active(x, spec) == -math.inf
