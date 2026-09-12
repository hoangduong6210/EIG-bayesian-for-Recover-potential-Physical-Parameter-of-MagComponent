"""Density-preserving transport and batched evaluation for sparse posteriors."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.special import expit

CC_UPPER = 0.85


def _coordinates(value: np.ndarray) -> np.ndarray:
    array = np.asarray(value, dtype=float)
    if array.ndim < 1 or array.shape[-1] != 6:
        raise ValueError("coordinates must have final dimension six")
    return array


def to_unconstrained(x: np.ndarray) -> np.ndarray:
    """Logit only alpha_cc; preserve the five existing active coordinates."""
    x = _coordinates(x)
    if np.any(~np.isfinite(x)) or np.any((x[..., 5] <= 0) | (x[..., 5] >= CC_UPPER)):
        raise ValueError("logit transport requires finite interior coordinates")
    z = x.copy()
    z[..., 5] = np.log(x[..., 5]) - np.log(CC_UPPER - x[..., 5])
    return z


def to_original(z: np.ndarray) -> np.ndarray:
    z = _coordinates(z)
    x = z.copy()
    x[..., 5] = CC_UPPER * expit(z[..., 5])
    return x


def log_abs_det_jacobian(z: np.ndarray) -> np.ndarray:
    """log |dx/dz|, evaluated without exponentiating large logits."""
    value = _coordinates(z)[..., 5]
    with np.errstate(invalid="ignore"):
        return math.log(CC_UPPER) - np.logaddexp(0.0, -value) - np.logaddexp(0.0, value)


class VectorizedPosterior:
    """Evaluate the frozen Gaussian prior and magnetic likelihood in batches.

    The caller verifies numerical parity with the frozen scalar implementation
    before sampling. This object uses frozen bounds, channel codes and geometry.
    """

    def __init__(self, prepared: Any, spec: Any, modules: Any):
        self.data = prepared
        self.modules = modules
        self.spec = spec
        self.means = modules.prior.prior_center_vector(spec)
        self.sds = np.array([
            spec.log10_k_sd * math.log(10), spec.alpha_sd, spec.beta_sd,
            spec.ln_mu_s_sd, spec.ln_f_rel_hz_sd, spec.alpha_cc_sd,
        ])
        if np.any(self.sds <= 0) or not np.all(np.isfinite(self.sds)):
            raise ValueError("prior scales must be finite and positive")
        self.bounds = np.array(list(modules.prior.BOUNDS.values()))
        self.codes = {channel.value: index for index, channel in enumerate(modules.models.Channel)}

    def __call__(self, x: np.ndarray) -> np.ndarray:
        x = _coordinates(x)
        if x.ndim != 2:
            raise ValueError("batched posterior requires shape (n, 6)")
        answer = np.full(len(x), -np.inf)
        valid = np.all(np.isfinite(x) & (x >= self.bounds[:, 0]) & (x <= self.bounds[:, 1]), axis=1)
        if not np.any(valid):
            return answer
        active = x[valid]
        data = self.data
        prediction = np.empty((len(active), len(data.values)))
        with np.errstate(over="ignore", invalid="ignore", divide="ignore", under="ignore"):
            prior = np.sum(-0.5 * ((active - self.means) / self.sds) ** 2 - np.log(self.sds), axis=1)
            for column, channel in enumerate(data.channel):
                frequency = data.frequency_hz[column]
                if channel == self.codes["pcv"]:
                    prediction[:, column] = np.exp(active[:, 0]) * frequency ** active[:, 1] * data.flux_t[column] ** active[:, 2]
                    continue
                exponent = 1.0 - active[:, 5]
                magnitude = (frequency / np.exp(active[:, 4])) ** exponent
                angle = exponent * math.pi / 2
                den_real = 1 + magnitude * np.cos(angle)
                den_imag = magnitude * np.sin(angle)
                denominator = den_real ** 2 + den_imag ** 2
                permeability = np.exp(active[:, 3]) - 1
                real = 1 + permeability * den_real / denominator
                if channel == self.codes["mu_real"]:
                    prediction[:, column] = real
                elif channel == self.codes["mu_imag"]:
                    prediction[:, column] = permeability * den_imag / denominator
                elif channel == self.codes["lm"]:
                    geometry = data.geometry
                    if geometry is None:
                        raise ValueError("Geometry is required for the Lm channel")
                    scale = self.modules.inference.MU0 * geometry.turns ** 2 * geometry.area_m2 / geometry.path_m
                    prediction[:, column] = real * scale
                else:
                    raise ValueError("unsupported frozen channel")
            residual = (data.values - prediction) / data.sigma
            total = prior + np.sum(-0.5 * residual ** 2 - np.log(data.sigma) - 0.5 * math.log(2 * math.pi), axis=1)
        answer[valid] = np.where(np.isfinite(total), total, -np.inf)
        return answer

    def transformed(self, z: np.ndarray) -> np.ndarray:
        z = _coordinates(z)
        x = to_original(z)
        output = self(x) + log_abs_det_jacobian(z)
        # Finite-precision sigmoid saturation is outside the representable open
        # transform domain; never admit a rounded boundary as interior mass.
        interior = np.all(np.isfinite(z), axis=1) & (x[:, 5] > 0) & (x[:, 5] < CC_UPPER)
        return np.where(interior & np.isfinite(output), output, -np.inf)

    def check_scalar_parity(self, x: np.ndarray) -> dict[str, float | int]:
        expected = np.array([
            self.modules.inference._log_posterior_prepared(row, self.data, self.spec)
            for row in x
        ])
        actual = self(x)
        np.testing.assert_allclose(actual, expected, rtol=1e-11, atol=1e-8)
        finite = np.isfinite(expected)
        return {"rows": len(x), "rtol": 1e-11, "atol": 1e-8,
                "maximum_absolute_difference": float(np.max(np.abs(actual[finite] - expected[finite]))) if finite.any() else 0.0}
