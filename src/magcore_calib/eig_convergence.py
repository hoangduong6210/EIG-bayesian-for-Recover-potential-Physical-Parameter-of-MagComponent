"""Static, fail-closed summaries for an EIG Monte Carlo convergence grid.

The helpers consume plain mappings of stable design keys to replicate scores,
which keeps the convergence decision independent of the experiment runner and
makes archived JSON results sufficient to reproduce the decision.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

import numpy as np


ScoreReplicates = Mapping[str, Sequence[float]]


@dataclass(frozen=True, order=True)
class EIGSetting:
    """One nested-Monte-Carlo budget in the prespecified convergence grid."""

    n_outer: int
    n_inner: int
    n_replicates: int

    def __post_init__(self) -> None:
        for name in ("n_outer", "n_inner", "n_replicates"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or value < 1:
                raise ValueError(f"{name} must be a positive integer")

    @property
    def work_units(self) -> int:
        """Dominant likelihood-evaluation proxy used to choose the smallest setting."""
        return int(self.n_outer * self.n_inner * self.n_replicates)


@dataclass(frozen=True)
class ConvergenceThresholds:
    """Prespecified acceptance thresholds relative to the reference setting."""

    min_top1_agreement_rate: float = 0.80
    min_rank_correlation: float = 0.95
    min_interval_overlap_rate: float = 0.80
    endpoint_absolute_tolerance: float = 0.0

    def __post_init__(self) -> None:
        for name in (
            "min_top1_agreement_rate",
            "min_rank_correlation",
            "min_interval_overlap_rate",
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be finite and in [0, 1]")
        if (
            not math.isfinite(float(self.endpoint_absolute_tolerance))
            or self.endpoint_absolute_tolerance < 0.0
        ):
            raise ValueError("endpoint_absolute_tolerance must be finite and non-negative")


@dataclass(frozen=True)
class ConvergenceMetrics:
    """Metrics and gate decision for one setting versus a high-budget reference."""

    top1_agreement_rate: float
    rank_correlation: float
    interval_overlap_rate: float
    downstream_endpoint_difference: float
    downstream_endpoint_agrees: bool
    stable: bool


@dataclass(frozen=True)
class SettingEvaluation:
    setting: EIGSetting
    metrics: ConvergenceMetrics


def _validated_scores(scores: ScoreReplicates, *, label: str) -> dict[str, np.ndarray]:
    if not scores:
        raise ValueError(f"{label} scores must not be empty")
    validated: dict[str, np.ndarray] = {}
    for raw_key, raw_values in scores.items():
        key = str(raw_key)
        if not key:
            raise ValueError(f"{label} score keys must not be empty")
        if key in validated:
            raise ValueError(f"duplicate {label} score key after string conversion: {key}")
        values = np.asarray(raw_values, dtype=float)
        if values.ndim != 1 or len(values) == 0:
            raise ValueError(f"{label} scores for {key} must be a non-empty vector")
        if not np.all(np.isfinite(values)):
            raise ValueError(f"{label} scores for {key} must be finite")
        validated[key] = values
    return validated


def _winner(scores: Mapping[str, np.ndarray], replicate: int) -> str:
    """Return a reproducible winner, resolving exact ties by stable key."""
    return min(scores, key=lambda key: (-float(scores[key][replicate]), key))


def _mean_order(scores: Mapping[str, np.ndarray]) -> list[str]:
    return sorted(scores, key=lambda key: (-float(np.mean(scores[key])), key))


def _strict_rank_correlation(
    scores: Mapping[str, np.ndarray], reference: Mapping[str, np.ndarray],
) -> float:
    """Spearman correlation of deterministic mean-score orders."""
    keys = sorted(scores)
    if len(keys) == 1:
        return 1.0
    rank = {key: index for index, key in enumerate(_mean_order(scores))}
    reference_rank = {
        key: index for index, key in enumerate(_mean_order(reference))
    }
    first = np.asarray([rank[key] for key in keys], dtype=float)
    second = np.asarray([reference_rank[key] for key in keys], dtype=float)
    correlation = float(np.corrcoef(first, second)[0, 1])
    return correlation


def _mean_ci95(values: np.ndarray) -> tuple[float, float]:
    mean = float(np.mean(values))
    if len(values) == 1:
        return mean, mean
    se = float(np.std(values, ddof=1)) / math.sqrt(len(values))
    return mean - 1.96 * se, mean + 1.96 * se


def evaluate_convergence(
    scores: ScoreReplicates,
    reference_scores: ScoreReplicates,
    *,
    downstream_endpoint: float,
    reference_endpoint: float,
    thresholds: ConvergenceThresholds | None = None,
) -> ConvergenceMetrics:
    """Evaluate a setting against the highest-budget reference.

    Top-1 agreement uses paired replicate prefixes and therefore requires the
    setting and reference to have been evaluated with the same base replicate
    streams.  Rank correlation compares deterministic mean-score rankings.
    Interval overlap is the fraction of candidate-wise 95% Monte Carlo mean
    intervals that intersect the reference interval.  All metrics are computed
    from saved scores, without simulation.
    """
    candidate = _validated_scores(scores, label="candidate")
    reference = _validated_scores(reference_scores, label="reference")
    if set(candidate) != set(reference):
        missing = sorted(set(reference) - set(candidate))
        extra = sorted(set(candidate) - set(reference))
        raise ValueError(f"candidate keys differ from reference; missing={missing}, extra={extra}")
    candidate_lengths = {len(values) for values in candidate.values()}
    reference_lengths = {len(values) for values in reference.values()}
    if len(candidate_lengths) != 1 or len(reference_lengths) != 1:
        raise ValueError("all candidates within a setting must have equal replicate counts")
    paired_replicates = min(next(iter(candidate_lengths)), next(iter(reference_lengths)))
    agreements = sum(
        _winner(candidate, index) == _winner(reference, index)
        for index in range(paired_replicates)
    )
    top1_agreement_rate = agreements / paired_replicates
    rank_correlation = _strict_rank_correlation(candidate, reference)
    overlaps = 0
    for key in candidate:
        low, high = _mean_ci95(candidate[key])
        reference_low, reference_high = _mean_ci95(reference[key])
        overlaps += low <= reference_high and reference_low <= high
    interval_overlap_rate = overlaps / len(candidate)

    endpoint = float(downstream_endpoint)
    reference_value = float(reference_endpoint)
    if not math.isfinite(endpoint) or not math.isfinite(reference_value):
        raise ValueError("downstream endpoints must be finite")
    endpoint_difference = abs(endpoint - reference_value)
    limits = thresholds or ConvergenceThresholds()
    endpoint_agrees = endpoint_difference <= limits.endpoint_absolute_tolerance
    stable = bool(
        top1_agreement_rate >= limits.min_top1_agreement_rate
        and rank_correlation >= limits.min_rank_correlation
        and interval_overlap_rate >= limits.min_interval_overlap_rate
        and endpoint_agrees
    )
    return ConvergenceMetrics(
        top1_agreement_rate=float(top1_agreement_rate),
        rank_correlation=rank_correlation,
        interval_overlap_rate=float(interval_overlap_rate),
        downstream_endpoint_difference=endpoint_difference,
        downstream_endpoint_agrees=endpoint_agrees,
        stable=stable,
    )


def select_smallest_stable_setting(
    evaluations: Iterable[SettingEvaluation],
) -> SettingEvaluation:
    """Select the least-work stable setting, failing closed if none qualifies."""
    values = list(evaluations)
    if not values:
        raise ValueError("at least one setting evaluation is required")
    stable = [evaluation for evaluation in values if evaluation.metrics.stable]
    if not stable:
        raise ValueError("no EIG setting satisfies all convergence thresholds")
    return min(
        stable,
        key=lambda evaluation: (
            evaluation.setting.work_units,
            -evaluation.setting.n_inner,
            -evaluation.setting.n_outer,
            -evaluation.setting.n_replicates,
        ),
    )
