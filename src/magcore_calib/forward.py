"""Isothermal Steinmetz and Cole-Cole forward model."""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from .models import Channel, DesignPoint, Geometry, MagneticParams

MU0 = 4.0e-7 * math.pi
REFERENCE_TEMPERATURE_C = 25.0


def ensure_isothermal(points: Sequence[DesignPoint], *, target_c: float = 25.0,
                      tolerance_c: float = 0.5) -> None:
    outside = [p.temperature_c for p in points if abs(p.temperature_c - target_c) > tolerance_c]
    if outside:
        raise ValueError(
            f"temperature-independent model requires {target_c:g}+/-{tolerance_c:g} C; "
            f"found range {min(outside):g}..{max(outside):g} C"
        )


def cole_cole(mu_s: float, f_rel_hz: float, alpha_cc: float,
              f_hz: float) -> tuple[float, float]:
    if f_hz <= 0.0:
        return mu_s, 0.0
    exponent = 1.0 - alpha_cc
    magnitude = (f_hz / f_rel_hz) ** exponent
    angle = exponent * math.pi / 2.0
    den_real = 1.0 + magnitude * math.cos(angle)
    den_imag = magnitude * math.sin(angle)
    denominator = den_real * den_real + den_imag * den_imag
    delta = mu_s - 1.0
    return 1.0 + delta * den_real / denominator, delta * den_imag / denominator


def predict_one(params: MagneticParams, design: DesignPoint,
                geometry: Geometry | None = None) -> float:
    if design.channel is Channel.PCV:
        if design.f_hz <= 0.0 or design.b_pk_t <= 0.0:
            return 0.0
        return params.k * design.f_hz ** params.alpha * design.b_pk_t ** params.beta
    mu_real, mu_imag = cole_cole(
        params.mu_s, params.f_rel_hz, params.alpha_cc, design.f_hz
    )
    if design.channel is Channel.MU_REAL:
        return mu_real
    if design.channel is Channel.MU_IMAG:
        return mu_imag
    if design.channel is Channel.LM:
        if geometry is None:
            raise ValueError("Geometry is required for the Lm channel")
        return MU0 * mu_real * geometry.turns ** 2 * geometry.area_m2 / geometry.path_m
    raise ValueError(f"unsupported magnetic channel: {design.channel}")


def predict(params: MagneticParams, points: Sequence[DesignPoint],
            geometry: Geometry | None = None, *, target_c: float = 25.0,
            tolerance_c: float = 0.5) -> np.ndarray:
    ensure_isothermal(points, target_c=target_c, tolerance_c=tolerance_c)
    return np.array([predict_one(params, p, geometry) for p in points], dtype=float)


def predict_active_batch(samples: np.ndarray, design: DesignPoint,
                         geometry: Geometry | None = None) -> np.ndarray:
    """Vectorized prediction used by EIG; samples use the canonical six coordinates."""
    x = np.asarray(samples, dtype=float)
    if x.ndim != 2 or x.shape[1] != 6:
        raise ValueError("samples must have shape (n, 6)")
    k = np.exp(x[:, 0])
    alpha, beta = x[:, 1], x[:, 2]
    if design.channel is Channel.PCV:
        return k * design.f_hz ** alpha * design.b_pk_t ** beta
    mu_s, f_rel, alpha_cc = np.exp(x[:, 3]), np.exp(x[:, 4]), x[:, 5]
    exponent = 1.0 - alpha_cc
    magnitude = (design.f_hz / f_rel) ** exponent
    angle = exponent * math.pi / 2.0
    den_real = 1.0 + magnitude * np.cos(angle)
    den_imag = magnitude * np.sin(angle)
    denominator = den_real ** 2 + den_imag ** 2
    mu_real = 1.0 + (mu_s - 1.0) * den_real / denominator
    mu_imag = (mu_s - 1.0) * den_imag / denominator
    if design.channel is Channel.MU_REAL:
        return mu_real
    if design.channel is Channel.MU_IMAG:
        return mu_imag
    if design.channel is Channel.LM:
        if geometry is None:
            raise ValueError("Geometry is required for the Lm channel")
        return MU0 * mu_real * geometry.turns ** 2 * geometry.area_m2 / geometry.path_m
    raise ValueError(f"unsupported magnetic channel: {design.channel}")
