"""Nested Monte Carlo EIG and paired acquisition utilities."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Literal

import numpy as np
from scipy.special import logsumexp

from .data import NOISE_FRACTION
from .forward import predict_active_batch
from .models import Channel, DesignPoint, Geometry, Observation

CHANNEL_COST_S = {
    Channel.PCV: 60.0,
    Channel.MU_REAL: 20.0,
    Channel.MU_IMAG: 20.0,
    Channel.LM: 15.0,
}

AcquisitionObjective = Literal["raw", "per_cost"]


@dataclass(frozen=True)
class CandidateScore:
    """Repeated nested-Monte-Carlo score for one candidate."""

    design: DesignPoint
    eig_mean_nats: float
    eig_sd_nats: float
    eig_se_nats: float
    eig_ci95_low_nats: float
    eig_ci95_high_nats: float
    utility_mean: float
    top_selection_rate: float
    replicate_scores_nats: tuple[float, ...]


def stable_design_seed(base_seed: int, design: DesignPoint, replicate: int = 0) -> int:
    """Derive an order-invariant RNG seed from an exact design identity."""
    if replicate < 0:
        raise ValueError("replicate must be non-negative")
    identity = "|".join((
        design.channel.value,
        float(design.f_hz).hex(),
        float(design.b_pk_t).hex(),
        float(design.temperature_c).hex(),
    ))
    payload = f"magcore-eig-v2|{base_seed}|{replicate}|{identity}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big", signed=False)


def acquisition_utility(
    design: DesignPoint, eig_nats: float, objective: AcquisitionObjective,
) -> float:
    if objective == "raw":
        return float(eig_nats)
    if objective == "per_cost":
        return float(eig_nats) / CHANNEL_COST_S[design.channel]
    raise ValueError(f"unsupported acquisition objective: {objective}")


def _noise_sigma_from_predictions(predictions: np.ndarray, channel: Channel) -> float:
    if not np.all(np.isfinite(predictions)):
        raise ValueError("posterior predictive values must be finite")
    reference = max(float(np.median(np.abs(predictions))), 1e-9)
    return max(1e-9, NOISE_FRACTION[channel] * reference)


def fixed_noise_sigma(
    samples: np.ndarray, design: DesignPoint, geometry: Geometry | None = None,
) -> float:
    """Return the design's observation scale from the full posterior sample."""
    samples = np.asarray(samples, dtype=float)
    if samples.ndim != 2 or samples.shape[1] != 6 or len(samples) == 0:
        raise ValueError("samples must have shape (n, 6) with n > 0")
    if not np.all(np.isfinite(samples)):
        raise ValueError("samples must contain only finite values")
    predictions = predict_active_batch(samples, design, geometry)
    return _noise_sigma_from_predictions(predictions, design.channel)


def estimate_eig(design: DesignPoint, samples: np.ndarray, *, seed: int,
                 geometry: Geometry | None = None, n_outer: int = 300,
                 n_inner: int = 100) -> float:
    """Estimate EIG with streams that are prefix-nested across MC budgets.

    Outer posterior indices, inner posterior indices, and synthetic observation
    noise use independent child streams.  Re-running with the same seed and a
    larger ``n_outer`` or ``n_inner`` therefore preserves every draw from the
    smaller calculation.  The observation scale is computed from the complete
    posterior sample rather than the random outer subset, so it is fixed across
    the convergence grid as well.
    """
    samples = np.asarray(samples, dtype=float)
    if samples.ndim != 2 or samples.shape[1] != 6 or len(samples) == 0:
        raise ValueError("samples must have shape (n, 6) with n > 0")
    if not np.all(np.isfinite(samples)):
        raise ValueError("samples must contain only finite values")
    if isinstance(n_outer, bool) or not isinstance(n_outer, (int, np.integer)) or n_outer < 1:
        raise ValueError("n_outer must be a positive integer")
    if isinstance(n_inner, bool) or not isinstance(n_inner, (int, np.integer)) or n_inner < 1:
        raise ValueError("n_inner must be a positive integer")

    outer_seed, inner_seed, noise_seed = np.random.SeedSequence(seed).spawn(3)
    outer_rng = np.random.default_rng(outer_seed)
    inner_rng = np.random.default_rng(inner_seed)
    noise_rng = np.random.default_rng(noise_seed)
    outer_indices = outer_rng.choice(len(samples), size=n_outer, replace=True)
    inner_indices = inner_rng.choice(len(samples), size=n_inner, replace=True)

    # Predict once for the complete posterior. Besides fixing sigma, indexing
    # this array avoids repeating the forward model for duplicate MC draws.
    mu_posterior = predict_active_batch(samples, design, geometry)
    mu_outer = mu_posterior[outer_indices]
    mu_inner = mu_posterior[inner_indices]
    sigma = _noise_sigma_from_predictions(mu_posterior, design.channel)
    y = mu_outer + noise_rng.normal(0.0, sigma, n_outer)
    constant = -math.log(sigma) - 0.5 * math.log(2.0 * math.pi)
    conditional = -0.5 * ((y - mu_outer) / sigma) ** 2 + constant
    mixture_terms = -0.5 * ((y[:, None] - mu_inner[None, :]) / sigma) ** 2 + constant
    marginal = logsumexp(mixture_terms, axis=1) - math.log(n_inner)
    return float(np.mean(conditional - marginal))


def rank_candidates_with_uncertainty(
    library: list[DesignPoint], samples: np.ndarray, *, seed: int,
    geometry: Geometry | None = None, n_outer: int = 300, n_inner: int = 100,
    n_replicates: int = 1, objective: AcquisitionObjective = "per_cost",
) -> list[CandidateScore]:
    """Rank candidates with stable streams and repeated-estimator uncertainty."""
    if not library:
        return []
    if n_replicates < 1:
        raise ValueError("n_replicates must be at least one")
    if objective not in ("raw", "per_cost"):
        raise ValueError(f"unsupported acquisition objective: {objective}")

    estimates = np.empty((len(library), n_replicates), dtype=float)
    for candidate_index, design in enumerate(library):
        for replicate in range(n_replicates):
            estimates[candidate_index, replicate] = estimate_eig(
                design, samples, seed=stable_design_seed(seed, design, replicate),
                geometry=geometry, n_outer=n_outer, n_inner=n_inner,
            )

    utilities = np.array([
        [acquisition_utility(design, score, objective) for score in row]
        for design, row in zip(library, estimates)
    ])
    # Stable-key tie breaking makes top-selection rates independent of input order.
    top_keys: list[str] = []
    for replicate in range(n_replicates):
        best_utility = float(np.max(utilities[:, replicate]))
        tied = [
            design.key() for design, utility in zip(library, utilities[:, replicate])
            if np.isclose(utility, best_utility, rtol=0.0, atol=1e-15)
        ]
        top_keys.append(min(tied))

    scored: list[CandidateScore] = []
    for design, row in zip(library, estimates):
        mean_score = float(np.mean(row))
        sd = float(np.std(row, ddof=1)) if n_replicates > 1 else 0.0
        se = sd / math.sqrt(n_replicates)
        scored.append(CandidateScore(
            design=design,
            eig_mean_nats=mean_score,
            eig_sd_nats=sd,
            eig_se_nats=se,
            eig_ci95_low_nats=mean_score - 1.96 * se,
            eig_ci95_high_nats=mean_score + 1.96 * se,
            utility_mean=acquisition_utility(design, mean_score, objective),
            top_selection_rate=top_keys.count(design.key()) / n_replicates,
            replicate_scores_nats=tuple(float(value) for value in row),
        ))
    return sorted(scored, key=lambda item: (-item.utility_mean, item.design.key()))


def rank_candidates(
    library: list[DesignPoint], samples: np.ndarray, *, seed: int,
    geometry: Geometry | None = None, n_outer: int = 300, n_inner: int = 100,
    n_replicates: int = 1, objective: AcquisitionObjective = "per_cost",
) -> list[tuple[DesignPoint, float]]:
    """Backward-compatible mean-score view of the uncertainty-aware ranking."""
    return [
        (entry.design, entry.eig_mean_nats)
        for entry in rank_candidates_with_uncertainty(
            library, samples, seed=seed, geometry=geometry, n_outer=n_outer,
            n_inner=n_inner, n_replicates=n_replicates, objective=objective,
        )
    ]


def reveal(outcomes: dict[str, Observation], design: DesignPoint) -> Observation:
    """Reveal the common-random-number observation assigned to a design."""
    try:
        return outcomes[design.key()]
    except KeyError as error:
        raise KeyError(f"design {design.key()} has no pre-generated outcome") from error
