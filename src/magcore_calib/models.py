"""Typed contracts for the six-parameter, isothermal magnetic model."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

import numpy as np

ACTIVE_NAMES = ("ln_k", "alpha", "beta", "ln_mu_s", "ln_f_rel_hz", "alpha_cc")


class Channel(str, Enum):
    PCV = "pcv"
    MU_REAL = "mu_real"
    MU_IMAG = "mu_imag"
    LM = "lm"


@dataclass(frozen=True)
class DesignPoint:
    channel: Channel
    f_hz: float
    b_pk_t: float
    temperature_c: float = 25.0

    def key(self) -> str:
        return f"{self.channel.value}|{self.f_hz:.12g}|{self.b_pk_t:.12g}|{self.temperature_c:.6g}"


@dataclass(frozen=True)
class Observation:
    design: DesignPoint
    value: float
    sigma: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.value):
            raise ValueError("observation value must be finite")
        if not math.isfinite(self.sigma) or self.sigma <= 0.0:
            raise ValueError("observation sigma must be finite and positive")


@dataclass(frozen=True)
class Geometry:
    turns: float = 10.0
    area_m2: float = 1.58e-4
    path_m: float = 0.102


@dataclass(frozen=True)
class MagneticParams:
    k: float
    alpha: float
    beta: float
    mu_s: float
    f_rel_hz: float
    alpha_cc: float

    def to_active(self) -> np.ndarray:
        return np.array(
            [math.log(self.k), self.alpha, self.beta, math.log(self.mu_s),
             math.log(self.f_rel_hz), self.alpha_cc],
            dtype=float,
        )

    @classmethod
    def from_active(cls, x: np.ndarray) -> "MagneticParams":
        if np.asarray(x).shape != (6,):
            raise ValueError("magnetic active vector must have exactly six entries")
        return cls(
            k=math.exp(float(x[0])), alpha=float(x[1]), beta=float(x[2]),
            mu_s=math.exp(float(x[3])), f_rel_hz=math.exp(float(x[4])),
            alpha_cc=float(x[5]),
        )
