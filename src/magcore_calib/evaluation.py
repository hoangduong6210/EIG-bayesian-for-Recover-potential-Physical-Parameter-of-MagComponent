"""Posterior-predictive precision and recovery metrics."""

from __future__ import annotations

import numpy as np

from .forward import predict_active_batch, predict_one
from .models import Channel, DesignPoint, Geometry, MagneticParams


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


def latent_holdout_summary(
    samples: np.ndarray,
    truth: MagneticParams,
    points: list[DesignPoint],
    geometry: Geometry | None = None,
) -> dict[str, dict[str, float | int]]:
    """Evaluate latent posterior predictions on a fixed, unobserved grid.

    Results are reported separately by channel so the very different physical
    units cannot dominate a pooled error. Intervals cover the noise-free
    generating mean, not future noisy observations.
    """

    if not points:
        raise ValueError("holdout grid must be nonempty")
    output: dict[str, dict[str, float | int]] = {}
    for channel in Channel:
        channel_points = [point for point in points if point.channel is channel]
        if not channel_points:
            raise ValueError(f"holdout grid has no {channel.value} designs")
        relative_errors: list[float] = []
        covered = 0
        for point in channel_points:
            predictions = predict_active_batch(samples, point, geometry)
            p05, median, p95 = np.percentile(predictions, [5, 50, 95])
            expected = predict_one(truth, point, geometry)
            if expected == 0.0:
                raise ValueError("holdout truth must be nonzero for relative metrics")
            relative_errors.append(float((median - expected) / expected))
            covered += int(
                p05 <= expected <= p95
                or np.isclose(expected, p05, rtol=1e-12, atol=0.0)
                or np.isclose(expected, p95, rtol=1e-12, atol=0.0)
            )
        errors = np.asarray(relative_errors, dtype=float)
        output[channel.value] = {
            "n_points": len(channel_points),
            "relative_rmse_pct": float(np.sqrt(np.mean(errors ** 2)) * 100.0),
            "median_absolute_relative_error_pct": float(
                np.median(np.abs(errors)) * 100.0
            ),
            "latent_ci90_coverage_fraction": float(covered / len(channel_points)),
        }
    return output
