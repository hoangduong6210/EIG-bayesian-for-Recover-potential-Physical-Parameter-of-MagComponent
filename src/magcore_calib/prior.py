"""Datasheet prior defined directly in the sampler's natural-log coordinates."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np

from .models import MagneticParams


@dataclass(frozen=True)
class DatasheetPrior:
    """Prior units are explicit: k uses dex; other scale parameters use natural log."""

    log10_k_nom: float = -7.5
    log10_k_sd: float = 0.15
    alpha_nom: float = 1.55
    alpha_sd: float = 0.15
    beta_nom: float = 2.55
    beta_sd: float = 0.15
    ln_mu_s_nom: float = math.log(2200.0)
    ln_mu_s_sd: float = 0.20
    ln_f_rel_hz_nom: float = math.log(9.0e5)
    ln_f_rel_hz_sd: float = 0.35
    alpha_cc_nom: float = 0.25
    alpha_cc_sd: float = 0.15

    def as_dict(self) -> dict[str, float]:
        return asdict(self)


BOUNDS = {
    "ln_k": (-math.inf, math.inf),
    "alpha": (1.0, 3.0),
    "beta": (2.0, 4.0),
    "ln_mu_s": (math.log(1.0), math.inf),
    "ln_f_rel_hz": (math.log(1.0e3), math.inf),
    "alpha_cc": (0.0, 0.85),
}


def prior_center_vector(spec: DatasheetPrior) -> np.ndarray:
    return np.array([
        spec.log10_k_nom * math.log(10.0), spec.alpha_nom, spec.beta_nom,
        spec.ln_mu_s_nom, spec.ln_f_rel_hz_nom, spec.alpha_cc_nom,
    ])


def _normal_kernel(value: float, mean: float, sd: float, bounds: tuple[float, float]) -> float:
    if not math.isfinite(value) or sd <= 0.0 or not bounds[0] <= value <= bounds[1]:
        return -math.inf
    return -0.5 * ((value - mean) / sd) ** 2 - math.log(sd)


def log_prior_active(x: np.ndarray, spec: DatasheetPrior) -> float:
    """Log density with respect to d(ln k) d(alpha) ... d(alpha_cc).

    No inverse-transform Jacobian belongs here because emcee samples this exact
    coordinate system. The k standard deviation is converted from dex to ln.
    """
    x = np.asarray(x, dtype=float)
    if x.shape != (6,):
        return -math.inf
    means = prior_center_vector(spec)
    sds = np.array([
        spec.log10_k_sd * math.log(10.0), spec.alpha_sd, spec.beta_sd,
        spec.ln_mu_s_sd, spec.ln_f_rel_hz_sd, spec.alpha_cc_sd,
    ])
    return float(sum(
        _normal_kernel(float(value), float(mean), float(sd), BOUNDS[name])
        for value, mean, sd, name in zip(x, means, sds, BOUNDS)
    ))


def draw_prior_predictive(spec: DatasheetPrior, rng: np.random.Generator) -> MagneticParams:
    """Draw a matched-model truth without centering the prior on its realization."""
    center = prior_center_vector(spec)
    sds = np.array([
        spec.log10_k_sd * math.log(10.0), spec.alpha_sd, spec.beta_sd,
        spec.ln_mu_s_sd, spec.ln_f_rel_hz_sd, spec.alpha_cc_sd,
    ])
    while True:
        x = rng.normal(center, sds)
        if math.isfinite(log_prior_active(x, spec)):
            return MagneticParams.from_active(x)
