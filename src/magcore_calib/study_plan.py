"""Single source of truth for acquisition and estimator-validation studies."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import product
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError as exc:  # pragma: no cover - production uses Python 3.12
    raise RuntimeError("study-plan loading requires Python 3.11 or newer") from exc


@dataclass(frozen=True, order=True)
class EstimatorSetting:
    n_outer: int
    n_inner: int
    n_replicates: int

    def as_tuple(self) -> tuple[int, int, int]:
        return self.n_outer, self.n_inner, self.n_replicates

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass(frozen=True)
class EstimatorValidationThresholds:
    min_top1_probability: float
    min_rank_correlation: float
    min_interval_overlap_rate: float
    max_relative_reference_regret: float
    endpoint_atol: int

    def as_dict(self) -> dict[str, float | int]:
        return asdict(self)


@dataclass(frozen=True)
class StateTask:
    seed: int
    n_observations: int

    @property
    def state_id(self) -> str:
        return f"s{self.seed}_n{self.n_observations}"

    def as_dict(self) -> dict[str, int | str]:
        return {**asdict(self), "state_id": self.state_id}


@dataclass(frozen=True)
class ScoreTask:
    seed: int
    n_observations: int
    setting: EstimatorSetting
    namespace: str

    @property
    def state_id(self) -> str:
        return f"s{self.seed}_n{self.n_observations}"

    @property
    def score_id(self) -> str:
        o, i, r = self.setting.as_tuple()
        return f"{self.namespace}_{self.state_id}_o{o}_i{i}_r{r}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "n_observations": self.n_observations,
            "namespace": self.namespace,
            "state_id": self.state_id,
            "score_id": self.score_id,
            **self.setting.as_dict(),
        }


@dataclass(frozen=True)
class DownstreamTask:
    seed: int

    @property
    def task_id(self) -> str:
        return f"seed{self.seed}"

    def as_dict(self) -> dict[str, int | str]:
        return {"seed": self.seed, "task_id": self.task_id}


@dataclass(frozen=True)
class StudyPlan:
    recovery_seeds: tuple[int, ...]
    acquisition_seeds: tuple[int, ...]
    validation_state_seeds: tuple[int, ...]
    validation_observation_counts: tuple[int, ...]
    downstream_validation_seeds: tuple[int, ...]
    outer_grid: tuple[int, ...]
    inner_grid: tuple[int, ...]
    replicate_grid: tuple[int, ...]
    reference: EstimatorSetting
    audit: EstimatorSetting
    thresholds: EstimatorValidationThresholds

    @property
    def validation_state_task_count(self) -> int:
        return len(self.validation_state_seeds) * len(self.validation_observation_counts)

    @property
    def validation_grid_task_count(self) -> int:
        return self.validation_state_task_count * len(self.grid_score_settings)

    @property
    def validation_reference_task_count(self) -> int:
        return self.validation_state_task_count

    @property
    def validation_audit_task_count(self) -> int:
        return 2

    @property
    def downstream_validation_task_count(self) -> int:
        return len(self.downstream_validation_seeds)

    @property
    def candidate_settings(self) -> tuple[EstimatorSetting, ...]:
        return tuple(
            EstimatorSetting(outer, inner, replicates)
            for outer, inner, replicates in product(
                self.outer_grid, self.inner_grid, self.replicate_grid
            )
        )

    @property
    def grid_settings(self) -> tuple[EstimatorSetting, ...]:
        """Alias for the 27 settings evaluated from replicate prefixes."""

        return self.candidate_settings

    @property
    def grid_score_settings(self) -> tuple[EstimatorSetting, ...]:
        """Nine physical score tasks; each stores all configured prefixes."""

        max_replicates = max(self.replicate_grid)
        return tuple(
            EstimatorSetting(outer, inner, max_replicates)
            for outer, inner in product(self.outer_grid, self.inner_grid)
        )

    def validation_state_task(self, task_id: int) -> StateTask:
        return _indexed(
            tuple(
                StateTask(seed, n_observations)
                for seed, n_observations in product(
                    self.validation_state_seeds, self.validation_observation_counts
                )
            ),
            task_id,
            "estimator-validation state",
        )

    def validation_grid_task(self, task_id: int) -> ScoreTask:
        return _indexed(
            tuple(
                ScoreTask(seed, n_observations, setting, "grid")
                for seed, n_observations, setting in product(
                    self.validation_state_seeds,
                    self.validation_observation_counts,
                    self.grid_score_settings,
                )
            ),
            task_id,
            "estimator-validation grid",
        )

    def validation_reference_task(self, task_id: int) -> ScoreTask:
        state = self.validation_state_task(task_id)
        return ScoreTask(state.seed, state.n_observations, self.reference, "reference")

    def validation_audit_task(self, task_id: int) -> ScoreTask:
        # Prespecified sentinels: first state seed at the smallest/largest state.
        sentinels = (
            self.validation_observation_counts[0],
            self.validation_observation_counts[-1],
        )
        n_observations = _indexed(sentinels, task_id, "estimator-validation audit")
        return ScoreTask(self.validation_state_seeds[0], n_observations, self.audit, "audit")

    def downstream_validation_task(self, task_id: int) -> DownstreamTask:
        return DownstreamTask(
            _indexed(
                self.downstream_validation_seeds,
                task_id,
                "downstream estimator validation",
            )
        )

    def acquisition_seed(self, task_id: int) -> int:
        return _indexed(self.acquisition_seeds, task_id, "paired acquisition benchmark")

    def as_dict(self) -> dict[str, Any]:
        return {
            "recovery_seeds": list(self.recovery_seeds),
            "acquisition_seeds": list(self.acquisition_seeds),
            "validation_state_seeds": list(self.validation_state_seeds),
            "validation_observation_counts": list(self.validation_observation_counts),
            "downstream_validation_seeds": list(self.downstream_validation_seeds),
            "outer_grid": list(self.outer_grid),
            "inner_grid": list(self.inner_grid),
            "replicate_grid": list(self.replicate_grid),
            "reference": self.reference.as_dict(),
            "audit": self.audit.as_dict(),
            "thresholds": self.thresholds.as_dict(),
        }


def _indexed(values: tuple[Any, ...], task_id: int, label: str) -> Any:
    if not 0 <= task_id < len(values):
        raise IndexError(f"{label} task id {task_id} outside [0, {len(values) - 1}]")
    return values[task_id]


def _positive_int_tuple(value: Any, name: str) -> tuple[int, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{name} must be a non-empty TOML array")
    converted = tuple(value)
    if any(isinstance(item, bool) or not isinstance(item, int) or item <= 0 for item in converted):
        raise ValueError(f"{name} must contain positive integers")
    if len(set(converted)) != len(converted):
        raise ValueError(f"{name} must not contain duplicates")
    return converted


def _setting(raw: dict[str, Any], name: str) -> EstimatorSetting:
    try:
        setting = EstimatorSetting(
            n_outer=raw["n_outer"],
            n_inner=raw["n_inner"],
            n_replicates=raw["n_replicates"],
        )
    except (KeyError, TypeError) as exc:
        raise ValueError(f"invalid {name} estimator setting") from exc
    if any(isinstance(v, bool) or not isinstance(v, int) or v <= 0 for v in setting.as_tuple()):
        raise ValueError(f"{name} estimator values must be positive integers")
    return setting


def _resolve_config(path: str | Path) -> Path:
    candidate = Path(path).expanduser().resolve()
    if candidate.is_file():
        return candidate
    alternatives = (
        candidate / "default.toml",
        candidate / "config" / "default.toml",
        candidate / "configs" / "default.toml",
    )
    for alternative in alternatives:
        if alternative.is_file():
            return alternative
    raise FileNotFoundError(f"cannot locate default.toml from {candidate}")


def load_study_plan(path: str | Path) -> StudyPlan:
    """Load and validate a study plan from a config file, project, or run root."""

    config_path = _resolve_config(path)
    with config_path.open("rb") as stream:
        raw = tomllib.load(stream)
    try:
        seeds = raw["study"]["seeds"]
        validation = raw["study"]["estimator_validation"]
        thresholds = validation["thresholds"]
        plan = StudyPlan(
            recovery_seeds=_positive_int_tuple(seeds["recovery"], "recovery seeds"),
            acquisition_seeds=_positive_int_tuple(seeds["acquisition"], "acquisition seeds"),
            validation_state_seeds=_positive_int_tuple(
                seeds["validation_state"], "estimator-validation state seeds"
            ),
            validation_observation_counts=_positive_int_tuple(
                validation["observation_counts"],
                "estimator-validation observation counts",
            ),
            downstream_validation_seeds=_positive_int_tuple(
                seeds["downstream_validation"], "downstream-validation seeds"
            ),
            outer_grid=_positive_int_tuple(validation["outer_grid"], "outer grid"),
            inner_grid=_positive_int_tuple(validation["inner_grid"], "inner grid"),
            replicate_grid=_positive_int_tuple(
                validation["replicate_grid"], "replicate grid"
            ),
            reference=_setting(validation["reference"], "reference"),
            audit=_setting(validation["audit"], "audit"),
            thresholds=EstimatorValidationThresholds(
                min_top1_probability=float(thresholds["min_top1_probability"]),
                min_rank_correlation=float(thresholds["min_rank_correlation"]),
                min_interval_overlap_rate=float(thresholds["min_interval_overlap_rate"]),
                max_relative_reference_regret=float(
                    thresholds["max_relative_reference_regret"]
                ),
                endpoint_atol=int(thresholds["endpoint_atol"]),
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"invalid study plan in {config_path}: {exc}") from exc

    seed_sets = (
        set(plan.recovery_seeds), set(plan.acquisition_seeds),
        set(plan.validation_state_seeds), set(plan.downstream_validation_seeds),
    )
    if any(left & right for index, left in enumerate(seed_sets) for right in seed_sets[index + 1 :]):
        raise ValueError("study seed namespaces must be pairwise disjoint")
    if len(plan.acquisition_seeds) < 30:
        raise ValueError("paired acquisition benchmark requires at least 30 seeds")
    if plan.validation_audit_task_count != 2 \
            or len(plan.validation_observation_counts) < 2:
        raise ValueError(
            "estimator-validation audit requires distinct smallest/largest states"
        )
    for name, value in plan.thresholds.as_dict().items():
        if name == "endpoint_atol":
            if value < 0:
                raise ValueError("endpoint_atol must be nonnegative")
        elif not 0.0 <= value <= 1.0:
            raise ValueError(f"{name} must be in [0, 1]")
    return plan
