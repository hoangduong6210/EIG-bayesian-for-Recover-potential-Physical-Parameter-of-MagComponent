"""Diagnostics and complete six-parameter posterior summaries."""

from __future__ import annotations

import math

import numpy as np

from .models import ACTIVE_NAMES


def effective_sample_size(n_steps: int, n_walkers: int, tau: np.ndarray) -> np.ndarray:
    tau = np.asarray(tau, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return n_steps * n_walkers / tau


def diagnostic_report(chain: np.ndarray, acceptance_fraction: np.ndarray,
                      tau: np.ndarray) -> dict:
    """Build diagnostics from an emcee post-burn chain and its IAT estimate."""
    chain = np.asarray(chain)
    tau = np.asarray(tau, dtype=float)
    if chain.ndim != 3 or chain.shape[2] != 6 or tau.shape != (6,):
        raise ValueError("expected chain (steps, walkers, 6) and tau (6,)")
    n_steps, n_walkers, _ = chain.shape
    ess = effective_sample_size(n_steps, n_walkers, tau)
    ratios = n_steps / tau
    acceptance = float(np.mean(acceptance_fraction))
    finite = bool(np.all(np.isfinite(tau)) and np.all(tau > 0.0))
    valid = bool(
        finite and np.min(ess) >= 400.0 and np.min(ratios) >= 50.0
        and 0.20 <= acceptance <= 0.60
    )
    def finite_or_none(value: float) -> float | None:
        return float(value) if math.isfinite(float(value)) else None

    return {
        "method": "emcee_integrated_autocorrelation_time",
        "parameter_names": list(ACTIVE_NAMES),
        "tau": {name: finite_or_none(value) for name, value in zip(ACTIVE_NAMES, tau)},
        "ess": {name: finite_or_none(value) for name, value in zip(ACTIVE_NAMES, ess)},
        "steps_per_tau": {name: finite_or_none(value) for name, value in zip(ACTIVE_NAMES, ratios)},
        "acceptance_fraction": acceptance,
        "thresholds": {
            "min_ess": 400.0, "min_steps_per_tau": 50.0,
            "acceptance_range": [0.20, 0.60],
        },
        "valid": valid,
        "note": "R-hat is not claimed for interacting affine-invariant walkers.",
    }


def posterior_summary(samples: np.ndarray) -> dict[str, dict[str, float | bool]]:
    samples = np.asarray(samples, dtype=float)
    if samples.ndim != 2 or samples.shape[1] != 6:
        raise ValueError("posterior samples must have shape (n, 6)")
    output_names = ("k", "alpha", "beta", "mu_s", "f_rel_hz", "alpha_cc")
    transformed = samples.copy()
    transformed[:, (0, 3, 4)] = np.exp(transformed[:, (0, 3, 4)])
    result: dict[str, dict[str, float | bool]] = {}
    for index, name in enumerate(output_names):
        p05, median, p95 = np.percentile(transformed[:, index], [5, 50, 95])
        entry: dict[str, float | bool] = {
            "median": float(median), "p05": float(p05), "p95": float(p95),
            "ci90_half_width_absolute": float((p95 - p05) / 2.0),
        }
        if name != "alpha_cc" and not math.isclose(median, 0.0):
            entry["ci90_half_width_pct"] = float((p95 - p05) / (2.0 * abs(median)) * 100.0)
        if name == "alpha_cc":
            lower_mass = float(np.mean(transformed[:, index] <= 0.01))
            upper_mass = float(np.mean(transformed[:, index] >= 0.84))
            entry.update({
                "mass_within_0p01_lower_bound": lower_mass,
                "mass_within_0p01_upper_bound": upper_mass,
                "boundary_flag": bool(max(lower_mass, upper_mass) > 0.05),
            })
        result[name] = entry
    return result
