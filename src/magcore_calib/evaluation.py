"""Posterior-predictive precision and recovery metrics."""

from __future__ import annotations

import numpy as np

from .forward import predict_active_batch
from .models import DesignPoint, Geometry, MagneticParams


def latent_mean_ci_half_width_pct(samples: np.ndarray, design: DesignPoint,
                                  geometry: Geometry | None = None) -> float:
    """Central-90% credible half-width of the noise-free mean response.

    This propagates parameter uncertainty through the deterministic forward
    model. It intentionally does not add observation noise and therefore is not
    an interval for a future noisy observation.
    """
    predictions = predict_active_batch(samples, design, geometry)
    p05, median, p95 = np.percentile(predictions, [5, 50, 95])
    if median == 0.0:
        return float("inf")
    return float((p95 - p05) / (2.0 * abs(median)) * 100.0)


def predictive_ci_half_width_pct(samples: np.ndarray, design: DesignPoint,
                                 geometry: Geometry | None = None) -> float:
    """Compatibility alias; use :func:`latent_mean_ci_half_width_pct`."""
    return latent_mean_ci_half_width_pct(samples, design, geometry)


def recovery_summary(samples: np.ndarray, truth: MagneticParams) -> dict[str, dict[str, float | bool]]:
    from .diagnostics import posterior_summary

    summary = posterior_summary(samples)
    truth_values = {
        "k": truth.k, "alpha": truth.alpha, "beta": truth.beta,
        "mu_s": truth.mu_s, "f_rel_hz": truth.f_rel_hz, "alpha_cc": truth.alpha_cc,
    }
    for name, value in truth_values.items():
        entry = summary[name]
        entry["truth"] = value
        entry["absolute_error_pct"] = abs(float(entry["median"]) - value) / abs(value) * 100.0
        entry["truth_in_ci90"] = bool(float(entry["p05"]) <= value <= float(entry["p95"]))
    return summary
