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
class PolicySpec:
    policy: str
    method: str
    objective: str
    primary_endpoint: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class DirectContrast:
    name: str
    policy: str
    comparator: str
    endpoint: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class HoldoutContract:
    total_points: int
    channel_counts: tuple[tuple[str, int], ...]
    used_for_acquisition_or_stopping: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_points": self.total_points,
            "channel_counts": dict(self.channel_counts),
            "used_for_acquisition_or_stopping": self.used_for_acquisition_or_stopping,
        }


@dataclass(frozen=True)
class ComparatorBenchmark:
    version: int
    candidate_count: int
    policies: tuple[str, ...]
    policy_registry: tuple[PolicySpec, ...]
    reference_policy: str
    direct_contrasts: tuple[DirectContrast, ...]
    secondary_validation_used_for_stopping: bool
    holdout_contract: HoldoutContract
    claim_context: tuple[tuple[str, Any], ...]

    @property
    def primary_endpoints(self) -> dict[str, str]:
        return {entry.policy: entry.primary_endpoint for entry in self.policy_registry}

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "candidate_count": self.candidate_count,
            "policies": list(self.policies),
            "policy_registry": [entry.as_dict() for entry in self.policy_registry],
            "reference_policy": self.reference_policy,
            "direct_contrasts": [entry.as_dict() for entry in self.direct_contrasts],
            "secondary_validation_used_for_stopping": (
                self.secondary_validation_used_for_stopping
            ),
            "holdout_contract": self.holdout_contract.as_dict(),
            "claim_context": dict(self.claim_context),
        }


@dataclass(frozen=True)
class StopRule:
    quantity: str
    pcv_ci_half_width_pct: float
    lm_ci_half_width_pct: float
    pcv_target: tuple[tuple[str, float], ...]
    lm_target: tuple[tuple[str, float], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "quantity": self.quantity,
            "pcv_ci_half_width_pct": self.pcv_ci_half_width_pct,
            "lm_ci_half_width_pct": self.lm_ci_half_width_pct,
            "pcv_target": dict(self.pcv_target),
            "lm_target": dict(self.lm_target),
        }


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
    comparator_benchmark: ComparatorBenchmark
    modeled_cost_seconds: tuple[tuple[str, float], ...]
    stop_rule: StopRule
    eig_objectives: tuple[str, ...]
    max_measurements: int
    n_walkers: int
    n_steps: int
    burn: int
    max_sampler_steps: int
    sampler_check_interval: int

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
            "comparator_benchmark": self.comparator_benchmark.as_dict(),
            "modeled_cost_seconds": dict(self.modeled_cost_seconds),
            "stop_rule": self.stop_rule.as_dict(),
            "eig_objectives": list(self.eig_objectives),
            "max_measurements": self.max_measurements,
            "sampler": {
                "n_walkers": self.n_walkers,
                "n_steps": self.n_steps,
                "burn": self.burn,
                "max_steps": self.max_sampler_steps,
                "check_interval": self.sampler_check_interval,
            },
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


def _positive_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"{name} must be a positive number")
    return float(value)


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _comparator_benchmark(raw: dict[str, Any]) -> ComparatorBenchmark:
    expected_channels = ("pcv", "mu_real", "mu_imag", "lm")
    try:
        registry = tuple(PolicySpec(**entry) for entry in raw["policy_registry"])
        contrasts = tuple(DirectContrast(**entry) for entry in raw["direct_contrasts"])
        holdout_raw = raw["holdout_contract"]
        holdout = HoldoutContract(
            total_points=_positive_int(holdout_raw["total_points"], "holdout total"),
            channel_counts=tuple(
                (channel, _positive_int(holdout_raw[channel], f"{channel} holdout count"))
                for channel in expected_channels
            ),
            used_for_acquisition_or_stopping=holdout_raw[
                "used_for_acquisition_or_stopping"
            ],
        )
        claim_context = tuple(sorted(raw["claim_context"].items()))
        benchmark = ComparatorBenchmark(
            version=int(raw["version"]),
            candidate_count=_positive_int(raw["candidate_count"], "candidate count"),
            policies=tuple(raw["policies"]),
            policy_registry=registry,
            reference_policy=raw["reference_policy"],
            direct_contrasts=contrasts,
            secondary_validation_used_for_stopping=raw[
                "secondary_validation_used_for_stopping"
            ],
            holdout_contract=holdout,
            claim_context=claim_context,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("invalid comparator benchmark contract") from exc
    expected_registry = (
        ("eig_raw", "eig", "raw", "measurement_count_to_gate"),
        ("eig_per_cost", "eig", "per_cost", "modeled_cost_to_gate"),
        ("fixed_channel_balanced", "fixed_channel_balanced", "fixed_channel_balanced_traversal", "descriptive_count_and_modeled_cost"),
        ("random_channel_balanced", "random_channel_balanced", "random_channel_balanced_traversal", "descriptive_count_and_modeled_cost"),
        ("predictive_variance_raw", "predictive_variance", "raw", "measurement_count_to_gate"),
        ("predictive_variance_per_cost", "predictive_variance", "per_cost", "modeled_cost_to_gate"),
        ("laplace_d_opt_raw", "laplace_d_opt", "raw", "measurement_count_to_gate"),
        ("laplace_d_opt_per_cost", "laplace_d_opt", "per_cost", "modeled_cost_to_gate"),
    )
    expected_contrasts = (
        ("eig_raw_vs_predictive_variance_raw", "eig_raw", "predictive_variance_raw", "measurement_count_to_gate"),
        ("eig_raw_vs_laplace_d_opt_raw", "eig_raw", "laplace_d_opt_raw", "measurement_count_to_gate"),
        ("eig_per_cost_vs_predictive_variance_per_cost", "eig_per_cost", "predictive_variance_per_cost", "modeled_cost_to_gate"),
        ("eig_per_cost_vs_laplace_d_opt_per_cost", "eig_per_cost", "laplace_d_opt_per_cost", "modeled_cost_to_gate"),
    )
    policy_set = set(benchmark.policies)
    if benchmark.version != 4 or benchmark.candidate_count != 37:
        raise ValueError("comparator benchmark must declare v4 and 37 candidates")
    if len(policy_set) != len(benchmark.policies) or {
        entry.policy for entry in registry
    } != policy_set or len(registry) != len(policy_set):
        raise ValueError("policy registry must exactly cover unique benchmark policies")
    if tuple(
        (entry.policy, entry.method, entry.objective, entry.primary_endpoint)
        for entry in registry
    ) != expected_registry or benchmark.policies != tuple(row[0] for row in expected_registry):
        raise ValueError("benchmark v4 policy registry semantics are not exact")
    if benchmark.reference_policy not in policy_set:
        raise ValueError("reference policy is outside the benchmark registry")
    if benchmark.secondary_validation_used_for_stopping is not False \
            or holdout.used_for_acquisition_or_stopping is not False:
        raise ValueError("secondary validation must not influence acquisition or stopping")
    if holdout.total_points != 23 or dict(holdout.channel_counts) != {
        "pcv": 8, "mu_real": 6, "mu_imag": 6, "lm": 3,
    }:
        raise ValueError("holdout contract must be the prespecified 23-point grid")
    names = {entry.name for entry in contrasts}
    if len(names) != len(contrasts) or any(
        entry.policy not in policy_set or entry.comparator not in policy_set
        for entry in contrasts
    ):
        raise ValueError("direct contrasts must be unique and reference registered policies")
    if tuple(
        (entry.name, entry.policy, entry.comparator, entry.endpoint)
        for entry in contrasts
    ) != expected_contrasts:
        raise ValueError("benchmark v4 requires the exact four confirmatory contrasts")
    expected_claim_context = {
        "synthetic": True,
        "matched_model": True,
        "prior_predictive_truth": True,
        "datasheet_centered_on_realized_truth": False,
        "oracle_initialized": False,
        "measured_data": False,
        "scope": (
            "algorithmic matched-model synthetic benchmark; "
            "not validated laboratory efficiency"
        ),
    }
    if dict(benchmark.claim_context) != expected_claim_context:
        raise ValueError("benchmark v4 claim context is not the exact non-oracle scope")
    return benchmark


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
        comparator = raw["study"]["comparator_benchmark"]
        costs = raw["eig"]["modeled_cost_seconds"]
        eig = raw["eig"]
        sampler = comparator["sampler"]
        stop = raw["stop_rule"]
        if set(costs) != {"pcv", "mu_real", "mu_imag", "lm"}:
            raise ValueError("modeled cost contract must contain exactly four channels")
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
            comparator_benchmark=_comparator_benchmark(comparator),
            modeled_cost_seconds=tuple(
                (channel, _positive_number(costs[channel], f"{channel} modeled cost"))
                for channel in ("pcv", "mu_real", "mu_imag", "lm")
            ),
            stop_rule=StopRule(
                quantity=stop["quantity"],
                pcv_ci_half_width_pct=_positive_number(
                    stop["pcv_ci_half_width_pct"], "PCV gate"
                ),
                lm_ci_half_width_pct=_positive_number(
                    stop["lm_ci_half_width_pct"], "Lm gate"
                ),
                pcv_target=tuple(sorted(
                    (key, float(value)) for key, value in stop["pcv_target"].items()
                )),
                lm_target=tuple(sorted(
                    (key, float(value)) for key, value in stop["lm_target"].items()
                )),
            ),
            eig_objectives=tuple(eig["objectives"]),
            max_measurements=_positive_int(eig["max_measurements"], "measurement budget"),
            n_walkers=_positive_int(sampler["n_walkers"], "walker count"),
            n_steps=_positive_int(sampler["n_steps"], "MCMC steps"),
            burn=_positive_int(sampler["burn"], "MCMC burn"),
            max_sampler_steps=_positive_int(
                sampler["max_steps"], "maximum MCMC steps"
            ),
            sampler_check_interval=_positive_int(
                sampler["check_interval"], "MCMC check interval"
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
    if plan.eig_objectives != ("raw", "per_cost"):
        raise ValueError("benchmark v4 requires exact raw and per_cost objectives")
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value <= 0
        for value in (
            plan.max_measurements, plan.n_walkers, plan.n_steps, plan.burn,
        )
    ) or plan.burn >= plan.n_steps \
            or plan.max_sampler_steps < plan.n_steps \
            or plan.sampler_check_interval > plan.max_sampler_steps - plan.n_steps \
            or plan.max_measurements > plan.comparator_benchmark.candidate_count:
        raise ValueError("benchmark runtime counts are outside their valid domain")
    expected_stop = {
        "quantity": "latent_mean_response",
        "pcv_ci_half_width_pct": 8.0,
        "lm_ci_half_width_pct": 5.0,
        "pcv_target": {
            "frequency_hz": 100000.0, "b_pk_t": 0.1, "temperature_c": 25.0,
        },
        "lm_target": {
            "frequency_hz": 100000.0, "b_pk_t": 0.0, "temperature_c": 25.0,
        },
    }
    if plan.stop_rule.as_dict() != expected_stop:
        raise ValueError("stop rule differs from the exact v4 precision gate")
    return plan
