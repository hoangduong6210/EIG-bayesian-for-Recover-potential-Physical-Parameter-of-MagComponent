"""Deterministic comparator policies for sequential magnetic-core acquisition.

The functions in this module are deliberately independent of the experiment
runner.  They consume a posterior sample and a finite candidate library, and
return auditable rankings or orders.  Every deterministic tie is resolved by
the exact floating-point design identity rather than the display-oriented
``DesignPoint.key()``.
"""

from __future__ import annotations

import hashlib
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np

from .data import NOISE_FRACTION
from .eig import CHANNEL_COST_S
from .forward import predict_active_batch
from .models import Channel, DesignPoint, Geometry

AcquisitionObjective = Literal["raw", "per_cost"]


@dataclass(frozen=True)
class AcquisitionScore:
    """One dimensionless comparator score and its acquisition utility."""

    design: DesignPoint
    method: Literal["predictive_variance", "laplace_d_opt"]
    objective: AcquisitionObjective
    score: float
    utility: float
    noise_sigma: float


def exact_design_identity(design: DesignPoint) -> str:
    """Return a collision-resistant identity for a design's exact float values."""

    return design.exact_key()


def _stable_priority(seed: int, namespace: str, identity: str) -> int:
    if isinstance(seed, bool) or not isinstance(seed, (int, np.integer)):
        raise TypeError("seed must be an integer")
    payload = f"magcore-acquisition-v1|{int(seed)}|{namespace}|{identity}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest(), "big", signed=False)


def _validate_unique(points: Sequence[DesignPoint], label: str) -> dict[str, DesignPoint]:
    by_identity = {exact_design_identity(point): point for point in points}
    if len(by_identity) != len(points):
        raise ValueError(f"{label} contains duplicate exact design identities")
    return by_identity


def _remaining(
    library: Sequence[DesignPoint], selected: Sequence[DesignPoint],
) -> tuple[list[DesignPoint], Counter[Channel]]:
    library_by_identity = _validate_unique(library, "library")
    selected_by_identity = _validate_unique(selected, "selected")
    unknown = selected_by_identity.keys() - library_by_identity.keys()
    if unknown:
        raise ValueError("selected designs must belong to the candidate library")
    remaining = [
        point
        for identity, point in library_by_identity.items()
        if identity not in selected_by_identity
    ]
    return remaining, Counter(point.channel for point in selected)


def random_channel_balanced_order(
    library: Sequence[DesignPoint], *, seed: int,
    selected: Sequence[DesignPoint] = (),
) -> list[DesignPoint]:
    """Order remaining candidates using reproducible channel-balanced randomization.

    At each step, selection is restricted to nonempty channels having the
    smallest acquisition count so far.  A hash-derived channel priority then
    breaks the channel tie, while a separate exact-design priority randomizes
    candidates within each channel.  Consequently the result is invariant to
    input-list permutation and does not depend on process-level RNG state.
    """

    remaining, counts = _remaining(library, selected)
    groups: dict[Channel, list[DesignPoint]] = {channel: [] for channel in Channel}
    for point in remaining:
        groups[point.channel].append(point)
    for channel, points in groups.items():
        points.sort(
            key=lambda point: (
                _stable_priority(seed, f"candidate:{channel.value}", exact_design_identity(point)),
                exact_design_identity(point),
            )
        )

    order: list[DesignPoint] = []
    while any(groups.values()):
        active = [channel for channel, points in groups.items() if points]
        smallest_count = min(counts[channel] for channel in active)
        eligible = [channel for channel in active if counts[channel] == smallest_count]
        step = len(selected) + len(order)
        channel = min(
            eligible,
            key=lambda item: (
                _stable_priority(seed, f"channel-step:{step}", item.value),
                item.value,
            ),
        )
        point = groups[channel].pop(0)
        order.append(point)
        counts[channel] += 1
    return order


def _posterior_samples(samples: np.ndarray) -> np.ndarray:
    values = np.asarray(samples, dtype=float)
    if values.ndim != 2 or values.shape[1] != 6 or len(values) < 2:
        raise ValueError("samples must have shape (n, 6) with n >= 2")
    if not np.all(np.isfinite(values)):
        raise ValueError("samples must contain only finite values")
    return values


def _predictions_and_noise(
    design: DesignPoint, samples: np.ndarray, geometry: Geometry | None,
) -> tuple[np.ndarray, float]:
    predictions = np.asarray(predict_active_batch(samples, design, geometry), dtype=float)
    if predictions.shape != (len(samples),) or not np.all(np.isfinite(predictions)):
        raise ValueError("posterior predictions must be a finite one-dimensional array")
    reference = max(float(np.median(np.abs(predictions))), 1.0e-9)
    sigma = max(1.0e-9, NOISE_FRACTION[design.channel] * reference)
    return predictions, sigma


def _utility(
    score: float, design: DesignPoint, objective: AcquisitionObjective,
    costs: Mapping[Channel, float],
) -> float:
    if objective == "raw":
        return score
    if objective != "per_cost":
        raise ValueError(f"unsupported acquisition objective: {objective}")
    try:
        cost = float(costs[design.channel])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"missing modeled cost for channel {design.channel.value}") from error
    if not math.isfinite(cost) or cost <= 0.0:
        raise ValueError("modeled acquisition costs must be finite and positive")
    return score / cost


def predictive_variance_score(
    design: DesignPoint, samples: np.ndarray, geometry: Geometry | None = None,
) -> tuple[float, float]:
    """Return epistemic predictive variance divided by observation-noise variance.

    The ratio is dimensionless, so unlike raw response variance it is comparable
    across channels having different physical units.  Observation variance is
    not added to the numerator because that would reward irreducible noise.
    """

    values = _posterior_samples(samples)
    predictions, sigma = _predictions_and_noise(design, values, geometry)
    score = float(np.var(predictions, ddof=1) / (sigma * sigma))
    if not math.isfinite(score) or score < 0.0:
        raise ValueError("predictive-variance score must be finite and non-negative")
    return score, sigma


def _posterior_covariance(samples: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return the active-coordinate center and a numerically projected PSD covariance."""

    center = np.mean(samples, axis=0)
    covariance = np.asarray(np.cov(samples, rowvar=False, ddof=1), dtype=float)
    covariance = (covariance + covariance.T) / 2.0
    if covariance.shape != (6, 6) or not np.all(np.isfinite(covariance)):
        raise ValueError("posterior covariance must be finite and six-dimensional")
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    tolerance = np.finfo(float).eps * max(float(np.max(np.abs(eigenvalues))), 1.0) * 64.0
    if float(np.min(eigenvalues)) < -tolerance:
        raise ValueError("posterior covariance is not positive semidefinite")
    projected = (eigenvectors * np.clip(eigenvalues, 0.0, None)) @ eigenvectors.T
    return center, projected


def finite_difference_gradient(
    design: DesignPoint, center: np.ndarray, geometry: Geometry | None = None,
    *, relative_step: float = 1.0e-5,
) -> np.ndarray:
    """Differentiate a scalar response in the canonical six active coordinates."""

    location = np.asarray(center, dtype=float)
    if location.shape != (6,) or not np.all(np.isfinite(location)):
        raise ValueError("center must be a finite six-dimensional active vector")
    if not math.isfinite(relative_step) or relative_step <= 0.0:
        raise ValueError("relative_step must be finite and positive")
    perturbations = relative_step * np.maximum(1.0, np.abs(location))
    evaluation_points = np.repeat(location[None, :], 12, axis=0)
    for index, step in enumerate(perturbations):
        evaluation_points[2 * index, index] += step
        evaluation_points[2 * index + 1, index] -= step
    predictions = np.asarray(
        predict_active_batch(evaluation_points, design, geometry), dtype=float
    )
    if predictions.shape != (12,) or not np.all(np.isfinite(predictions)):
        raise ValueError("finite-difference predictions must be finite")
    gradient = (predictions[0::2] - predictions[1::2]) / (2.0 * perturbations)
    if not np.all(np.isfinite(gradient)):
        raise ValueError("finite-difference gradient must be finite")
    return gradient


def laplace_information_score(
    design: DesignPoint, samples: np.ndarray, geometry: Geometry | None = None,
    *, relative_step: float = 1.0e-5,
) -> tuple[float, float]:
    """Return scalar-observation Laplace/D-opt information in natural-log units.

    For posterior covariance ``Sigma``, local response gradient ``g``, and
    assumed noise scale ``sigma``, the one-step Gaussian information is
    ``0.5 log(1 + g Sigma g.T / sigma**2)`` nats.
    """

    values = _posterior_samples(samples)
    center, covariance_psd = _posterior_covariance(values)
    return _laplace_score_from_state(
        design, values, center, covariance_psd, geometry,
        relative_step=relative_step,
    )


def _laplace_score_from_state(
    design: DesignPoint, samples: np.ndarray, center: np.ndarray,
    covariance_psd: np.ndarray, geometry: Geometry | None, *,
    relative_step: float,
) -> tuple[float, float]:
    """Score a design using posterior state shared across a candidate ranking."""

    gradient = finite_difference_gradient(
        design, center, geometry, relative_step=relative_step
    )
    _, sigma = _predictions_and_noise(design, samples, geometry)
    signal_to_noise = float(gradient @ covariance_psd @ gradient / (sigma * sigma))
    signal_to_noise = max(signal_to_noise, 0.0)
    score = 0.5 * math.log1p(signal_to_noise)
    if not math.isfinite(score):
        raise ValueError("Laplace information score must be finite")
    return score, sigma


def _rank(
    method: Literal["predictive_variance", "laplace_d_opt"],
    library: Sequence[DesignPoint], samples: np.ndarray, *,
    selected: Sequence[DesignPoint], objective: AcquisitionObjective,
    geometry: Geometry | None, costs: Mapping[Channel, float],
    relative_step: float,
) -> list[AcquisitionScore]:
    remaining, _ = _remaining(library, selected)
    values = _posterior_samples(samples)
    if objective not in ("raw", "per_cost"):
        raise ValueError(f"unsupported acquisition objective: {objective}")
    laplace_state = _posterior_covariance(values) if method == "laplace_d_opt" else None
    scored: list[AcquisitionScore] = []
    for design in remaining:
        if method == "predictive_variance":
            score, sigma = predictive_variance_score(design, values, geometry)
        else:
            assert laplace_state is not None
            score, sigma = _laplace_score_from_state(
                design, values, *laplace_state, geometry,
                relative_step=relative_step,
            )
        scored.append(
            AcquisitionScore(
                design=design,
                method=method,
                objective=objective,
                score=score,
                utility=_utility(score, design, objective, costs),
                noise_sigma=sigma,
            )
        )
    return sorted(scored, key=lambda item: (-item.utility, exact_design_identity(item.design)))


def rank_predictive_variance(
    library: Sequence[DesignPoint], samples: np.ndarray, *,
    selected: Sequence[DesignPoint] = (), objective: AcquisitionObjective = "raw",
    geometry: Geometry | None = None,
    costs: Mapping[Channel, float] = CHANNEL_COST_S,
) -> list[AcquisitionScore]:
    """Rank unobserved candidates by dimensionless epistemic variance."""

    return _rank(
        "predictive_variance", library, samples, selected=selected,
        objective=objective, geometry=geometry, costs=costs, relative_step=1.0e-5,
    )


def rank_laplace_d_opt(
    library: Sequence[DesignPoint], samples: np.ndarray, *,
    selected: Sequence[DesignPoint] = (), objective: AcquisitionObjective = "raw",
    geometry: Geometry | None = None,
    costs: Mapping[Channel, float] = CHANNEL_COST_S,
    relative_step: float = 1.0e-5,
) -> list[AcquisitionScore]:
    """Rank unobserved candidates by one-step Laplace/D-opt information."""

    return _rank(
        "laplace_d_opt", library, samples, selected=selected,
        objective=objective, geometry=geometry, costs=costs,
        relative_step=relative_step,
    )


def select_predictive_variance(
    library: Sequence[DesignPoint], samples: np.ndarray, *,
    selected: Sequence[DesignPoint] = (), objective: AcquisitionObjective = "raw",
    geometry: Geometry | None = None,
    costs: Mapping[Channel, float] = CHANNEL_COST_S,
) -> DesignPoint:
    """Select the highest-ranked unobserved predictive-variance candidate."""

    ranking = rank_predictive_variance(
        library, samples, selected=selected, objective=objective,
        geometry=geometry, costs=costs,
    )
    if not ranking:
        raise ValueError("no unobserved candidate remains")
    return ranking[0].design


def select_laplace_d_opt(
    library: Sequence[DesignPoint], samples: np.ndarray, *,
    selected: Sequence[DesignPoint] = (), objective: AcquisitionObjective = "raw",
    geometry: Geometry | None = None,
    costs: Mapping[Channel, float] = CHANNEL_COST_S,
    relative_step: float = 1.0e-5,
) -> DesignPoint:
    """Select the highest-ranked unobserved Laplace/D-opt candidate."""

    ranking = rank_laplace_d_opt(
        library, samples, selected=selected, objective=objective,
        geometry=geometry, costs=costs, relative_step=relative_step,
    )
    if not ranking:
        raise ValueError("no unobserved candidate remains")
    return ranking[0].design
