"""Preregistered structural-mismatch data generators and evaluation contracts.

The inference model remains the six-parameter isothermal Steinmetz/Cole--Cole
model.  This module is intentionally limited to simulation and evaluation: it
must never be imported by the likelihood or posterior sampler.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .data import NOISE_FRACTION, default_library, validation_library
from .forward import MU0, predict_active_batch
from .models import Channel, DesignPoint, Geometry, MagneticParams, Observation

try:
    import tomllib
except ModuleNotFoundError as exc:  # pragma: no cover - production is Python 3.12
    raise RuntimeError("model-mismatch configuration requires Python 3.11+") from exc


MISMATCH_CONFIG_SCHEMA = "magcore-model-mismatch-preregistration/1.0"
MISMATCH_RESULT_SCHEMA = "magcore-model-mismatch-result/1.0"
MISMATCH_AGGREGATE_SCHEMA = "magcore-model-mismatch-aggregate/1.0"
MISMATCH_NON_ADMISSION_SCHEMA = "magcore-model-mismatch-non-admission/1.0"
POLICIES = (
    "eig_raw", "eig_per_cost", "fixed_channel_balanced",
    "random_channel_balanced", "predictive_variance_raw",
    "predictive_variance_per_cost", "laplace_d_opt_raw",
    "laplace_d_opt_per_cost",
)


@dataclass(frozen=True)
class MismatchScenario:
    """One fixed data-generating mechanism outside the inference family."""

    name: str
    second_pole_fraction: float
    first_pole_frequency_multiplier: float
    second_pole_frequency_multiplier: float
    first_pole_alpha_offset: float
    second_pole_alpha_offset: float
    pcv_temperature_log_slope_per_c: float
    pcv_log_frequency_curvature: float
    pcv_log_frequency_flux_interaction: float

    @property
    def matched(self) -> bool:
        return (
            self.second_pole_fraction == 0.0
            and self.pcv_temperature_log_slope_per_c == 0.0
            and self.pcv_log_frequency_curvature == 0.0
            and self.pcv_log_frequency_flux_interaction == 0.0
        )

    def as_dict(self) -> dict[str, Any]:
        return {**asdict(self), "matched": self.matched}


@dataclass(frozen=True)
class ModelMismatchPlan:
    """Frozen task, model, runtime, and endpoint definitions."""

    campaign_id: str
    status: str
    estimator_source_release_id: str
    estimator_decision_sha256: str
    seeds: tuple[int, ...]
    forbidden_development_seeds: tuple[int, ...]
    temperatures_c: tuple[float, ...]
    scenarios: tuple[MismatchScenario, ...]
    policies: tuple[str, ...]
    n_walkers: int
    n_steps: int
    burn: int
    max_steps: int
    check_interval: int
    max_measurements: int
    pcv_gate_pct: float
    lm_gate_pct: float
    false_confidence_pcv_error_pct: float
    false_confidence_lm_error_pct: float

    @property
    def task_count(self) -> int:
        return len(self.seeds) * len(self.scenarios)

    def task(self, task_id: int) -> tuple[MismatchScenario, int]:
        if isinstance(task_id, bool) or not isinstance(task_id, int):
            raise TypeError("task_id must be an integer")
        if not 0 <= task_id < self.task_count:
            raise IndexError(f"model-mismatch task {task_id} outside [0, {self.task_count - 1}]")
        scenario_index, seed_index = divmod(task_id, len(self.seeds))
        return self.scenarios[scenario_index], self.seeds[seed_index]

    def scenario(self, name: str) -> MismatchScenario:
        matches = [scenario for scenario in self.scenarios if scenario.name == name]
        if len(matches) != 1:
            raise KeyError(f"unknown model-mismatch scenario: {name}")
        return matches[0]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": MISMATCH_CONFIG_SCHEMA,
            "campaign_id": self.campaign_id,
            "status": self.status,
            "estimator_source_release_id": self.estimator_source_release_id,
            "estimator_decision_sha256": self.estimator_decision_sha256,
            "seeds": list(self.seeds),
            "forbidden_development_seeds": list(self.forbidden_development_seeds),
            "temperatures_c": list(self.temperatures_c),
            "scenarios": [scenario.as_dict() for scenario in self.scenarios],
            "policies": list(self.policies),
            "runtime": {
                "n_walkers": self.n_walkers, "n_steps": self.n_steps,
                "burn": self.burn, "max_steps": self.max_steps,
                "check_interval": self.check_interval,
                "max_measurements": self.max_measurements,
            },
            "endpoints": {
                "pcv_gate_pct": self.pcv_gate_pct,
                "lm_gate_pct": self.lm_gate_pct,
                "false_confidence_pcv_error_pct": (
                    self.false_confidence_pcv_error_pct
                ),
                "false_confidence_lm_error_pct": self.false_confidence_lm_error_pct,
            },
        }


def _unique_positive_ints(value: Any, label: str) -> tuple[int, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must be a nonempty array")
    if any(isinstance(item, bool) or not isinstance(item, int) or item <= 0 for item in value):
        raise ValueError(f"{label} must contain positive integers")
    if len(value) != len(set(value)):
        raise ValueError(f"{label} must not contain duplicates")
    return tuple(value)


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _positive_float(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a positive number")
    converted = float(value)
    if not math.isfinite(converted) or converted <= 0.0:
        raise ValueError(f"{label} must be a positive number")
    return converted


def _finite_float(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    converted = float(value)
    if not math.isfinite(converted):
        raise ValueError(f"{label} must be a finite number")
    return converted


def load_model_mismatch_plan(path: str | Path) -> ModelMismatchPlan:
    """Load and fail closed on the preregistered campaign contract."""

    config_path = Path(path).expanduser().resolve()
    with config_path.open("rb") as stream:
        raw = tomllib.load(stream)
    try:
        if raw["schema_version"] != MISMATCH_CONFIG_SCHEMA:
            raise ValueError("unsupported model-mismatch config schema")
        runtime = raw["runtime"]
        endpoints = raw["endpoints"]
        seeds = _unique_positive_ints(raw["seeds"], "confirmatory seeds")
        forbidden = _unique_positive_ints(
            raw["forbidden_development_seeds"], "forbidden development seeds"
        )
        temperatures = tuple(
            _finite_float(value, "candidate temperature")
            for value in raw["temperatures_c"]
        )
        scenarios = tuple(MismatchScenario(
            name=entry["name"],
            second_pole_fraction=_finite_float(
                entry["second_pole_fraction"], "second-pole fraction"
            ),
            first_pole_frequency_multiplier=_positive_float(
                entry["first_pole_frequency_multiplier"], "first-pole frequency multiplier"
            ),
            second_pole_frequency_multiplier=_positive_float(
                entry["second_pole_frequency_multiplier"], "second-pole frequency multiplier"
            ),
            first_pole_alpha_offset=_finite_float(
                entry["first_pole_alpha_offset"], "first-pole alpha offset"
            ),
            second_pole_alpha_offset=_finite_float(
                entry["second_pole_alpha_offset"], "second-pole alpha offset"
            ),
            pcv_temperature_log_slope_per_c=_finite_float(
                entry["pcv_temperature_log_slope_per_c"], "PCV temperature slope"
            ),
            pcv_log_frequency_curvature=_finite_float(
                entry["pcv_log_frequency_curvature"], "PCV frequency curvature"
            ),
            pcv_log_frequency_flux_interaction=_finite_float(
                entry["pcv_log_frequency_flux_interaction"], "PCV interaction"
            ),
        ) for entry in raw["scenarios"])
        plan = ModelMismatchPlan(
            campaign_id=raw["campaign_id"], status=raw["status"],
            estimator_source_release_id=raw["estimator_source_release_id"],
            estimator_decision_sha256=raw["estimator_decision_sha256"],
            seeds=seeds, forbidden_development_seeds=forbidden,
            temperatures_c=temperatures, scenarios=scenarios,
            policies=tuple(raw["policies"]),
            n_walkers=_positive_int(runtime["n_walkers"], "walker count"),
            n_steps=_positive_int(runtime["n_steps"], "sampler steps"),
            burn=_positive_int(runtime["burn"], "sampler burn"),
            max_steps=_positive_int(runtime["max_steps"], "maximum sampler steps"),
            check_interval=_positive_int(
                runtime["check_interval"], "sampler check interval"
            ),
            max_measurements=_positive_int(
                runtime["max_measurements"], "measurement budget"
            ),
            pcv_gate_pct=_positive_float(endpoints["pcv_gate_pct"], "PCV gate"),
            lm_gate_pct=_positive_float(endpoints["lm_gate_pct"], "Lm gate"),
            false_confidence_pcv_error_pct=_positive_float(
                endpoints["false_confidence_pcv_error_pct"],
                "false-confidence PCV error",
            ),
            false_confidence_lm_error_pct=_positive_float(
                endpoints["false_confidence_lm_error_pct"],
                "false-confidence Lm error",
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"invalid model-mismatch plan in {config_path}: {exc}") from exc

    if not isinstance(plan.campaign_id, str) or not plan.campaign_id:
        raise ValueError("campaign_id must be a nonempty string")
    if plan.status != "preregistered_before_confirmatory_outcomes":
        raise ValueError("campaign status must declare prospective preregistration")
    if not re.fullmatch(
        r"\d{8}T\d{6}Z_[0-9a-f]{12}", plan.estimator_source_release_id
    ):
        raise ValueError("estimator source release ID is invalid")
    if not re.fullmatch(r"[0-9a-f]{64}", plan.estimator_decision_sha256):
        raise ValueError("estimator decision SHA-256 is invalid")
    if set(plan.seeds) & set(plan.forbidden_development_seeds):
        raise ValueError("confirmatory seeds overlap forbidden development outcomes")
    if len(plan.seeds) < 30:
        raise ValueError("model-mismatch campaign requires at least 30 paired seeds")
    if len(set(plan.temperatures_c)) != len(plan.temperatures_c) \
            or tuple(sorted(plan.temperatures_c)) != plan.temperatures_c \
            or 25.0 not in plan.temperatures_c:
        raise ValueError("temperatures must be unique, sorted, and include 25 C")
    if plan.policies != POLICIES:
        raise ValueError("policy registry differs from the frozen eight-policy set")
    if len({scenario.name for scenario in plan.scenarios}) != len(plan.scenarios) \
            or len(plan.scenarios) < 4:
        raise ValueError("at least four uniquely named scenarios are required")
    if any(not re.fullmatch(r"[a-z][a-z0-9_]{2,63}", scenario.name)
           for scenario in plan.scenarios):
        raise ValueError("scenario names must be stable lowercase identifiers")
    if sum(scenario.matched for scenario in plan.scenarios) != 1:
        raise ValueError("exactly one matched control scenario is required")
    for scenario in plan.scenarios:
        if not 0.0 <= scenario.second_pole_fraction < 1.0:
            raise ValueError("second-pole fractions must lie in [0, 1)")
    if plan.burn >= plan.n_steps or plan.max_steps < plan.n_steps \
            or plan.check_interval > plan.max_steps - plan.n_steps:
        raise ValueError("sampler runtime contract is inconsistent")
    candidate_count = len(mismatch_candidate_library(plan.temperatures_c))
    if plan.max_measurements > candidate_count:
        raise ValueError("measurement budget exceeds the mismatch candidate library")
    return plan


def mismatch_candidate_library(
    temperatures_c: tuple[float, ...] = (25.0, 60.0, 100.0),
) -> list[DesignPoint]:
    """Retain the 37 unique 25 C candidates used by benchmark v4.

    Temperatures outside 25 C are deliberately holdout-only.  Adding them to
    acquisition would create information-identical candidates under the
    temperature-independent inference model and confound policy comparisons
    with arbitrary tie breaking.
    """

    if 25.0 not in temperatures_c:
        raise ValueError("model-mismatch evaluation temperatures must include 25 C")
    points = default_library(25.0)
    identities = [point.exact_key() for point in points]
    if len(identities) != len(set(identities)):
        raise ValueError("model-mismatch candidate library contains duplicates")
    return points


def mismatch_validation_library(
    temperatures_c: tuple[float, ...] = (25.0, 60.0, 100.0),
) -> list[DesignPoint]:
    """Return a disjoint 39-point latent holdout including PCV temperatures."""

    base = validation_library(25.0)
    non_pcv = [point for point in base if point.channel is not Channel.PCV]
    pcv_template = [point for point in base if point.channel is Channel.PCV]
    points = list(non_pcv)
    for temperature in temperatures_c:
        points.extend(
            DesignPoint(Channel.PCV, point.f_hz, point.b_pk_t, temperature)
            for point in pcv_template
        )
    candidate_ids = {
        point.exact_key() for point in mismatch_candidate_library(temperatures_c)
    }
    if candidate_ids & {point.exact_key() for point in points}:
        raise ValueError("mismatch holdout must be disjoint from acquisition candidates")
    return points


def _cole_cole_component(
    delta_mu: float, f_rel_hz: float, alpha_cc: float, f_hz: float,
) -> tuple[float, float]:
    if f_hz <= 0.0:
        return delta_mu, 0.0
    exponent = 1.0 - min(max(alpha_cc, 0.0), 0.95)
    magnitude = (f_hz / f_rel_hz) ** exponent
    angle = exponent * math.pi / 2.0
    den_real = 1.0 + magnitude * math.cos(angle)
    den_imag = magnitude * math.sin(angle)
    denominator = den_real * den_real + den_imag * den_imag
    return delta_mu * den_real / denominator, delta_mu * den_imag / denominator


def mismatch_predict_one(
    truth: MagneticParams, scenario: MismatchScenario, design: DesignPoint,
    geometry: Geometry | None = None,
) -> float:
    """Evaluate the fixed data generator; this function is not an inference model."""

    if design.channel is Channel.PCV:
        if design.f_hz <= 0.0 or design.b_pk_t <= 0.0:
            return 0.0
        log_f = math.log10(design.f_hz / 1.0e5)
        log_b = math.log10(design.b_pk_t / 0.1)
        log_discrepancy = (
            scenario.pcv_temperature_log_slope_per_c
            * (design.temperature_c - 25.0)
            + scenario.pcv_log_frequency_curvature * log_f * log_f
            + scenario.pcv_log_frequency_flux_interaction * log_f * log_b
        )
        base = truth.k * design.f_hz ** truth.alpha * design.b_pk_t ** truth.beta
        return base * math.exp(log_discrepancy)

    second_weight = scenario.second_pole_fraction
    first_weight = 1.0 - second_weight
    delta_mu = truth.mu_s - 1.0
    first = _cole_cole_component(
        first_weight * delta_mu,
        truth.f_rel_hz * scenario.first_pole_frequency_multiplier,
        truth.alpha_cc + scenario.first_pole_alpha_offset,
        design.f_hz,
    )
    second = _cole_cole_component(
        second_weight * delta_mu,
        truth.f_rel_hz * scenario.second_pole_frequency_multiplier,
        truth.alpha_cc + scenario.second_pole_alpha_offset,
        design.f_hz,
    )
    mu_real = 1.0 + first[0] + second[0]
    mu_imag = first[1] + second[1]
    if design.channel is Channel.MU_REAL:
        return mu_real
    if design.channel is Channel.MU_IMAG:
        return mu_imag
    if design.channel is Channel.LM:
        if geometry is None:
            raise ValueError("Geometry is required for the Lm channel")
        return MU0 * mu_real * geometry.turns ** 2 * geometry.area_m2 / geometry.path_m
    raise ValueError(f"unsupported magnetic channel: {design.channel}")


def stable_mismatch_outcomes(
    truth: MagneticParams, scenario: MismatchScenario,
    library: list[DesignPoint], *, seed: int,
    geometry: Geometry | None = None,
) -> dict[str, Observation]:
    """Generate candidate-indexed outcomes shared by every policy.

    The standard-normal draw depends only on seed and exact design identity,
    not scenario.  Scenario contrasts therefore use common standardized noise
    as well as a common six-parameter truth anchor.
    """

    identities = [point.exact_key() for point in library]
    if len(identities) != len(set(identities)):
        raise ValueError("candidate library contains duplicate exact identities")
    outcomes: dict[str, Observation] = {}
    for point, identity in zip(library, identities):
        payload = f"magcore-mismatch-outcome-v1|{seed}|{identity}".encode("utf-8")
        point_seed = int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")
        mean = mismatch_predict_one(truth, scenario, point, geometry)
        sigma = max(1.0e-9, NOISE_FRACTION[point.channel] * abs(mean))
        value = mean + np.random.default_rng(point_seed).normal(0.0, sigma)
        outcomes[identity] = Observation(point, float(value), sigma)
    return outcomes


def mismatch_holdout_evaluation(
    samples: np.ndarray, truth: MagneticParams, scenario: MismatchScenario,
    points: list[DesignPoint], geometry: Geometry | None = None,
) -> dict[str, Any]:
    """Evaluate misspecified posterior predictions against the true DGP mean."""

    if not points:
        raise ValueError("holdout grid must be nonempty")
    rows: list[dict[str, Any]] = []
    for point in points:
        predictions = predict_active_batch(samples, point, geometry)
        p05, median, p95 = np.percentile(predictions, [5, 50, 95])
        expected = mismatch_predict_one(truth, scenario, point, geometry)
        relative_error = float((median - expected) / expected)
        covered = bool(
            p05 <= expected <= p95
            or np.isclose(expected, p05, rtol=1.0e-12, atol=0.0)
            or np.isclose(expected, p95, rtol=1.0e-12, atol=0.0)
        )
        rows.append({
            "design_key": point.key(), "design_identity": point.exact_key(),
            "channel": point.channel.value, "frequency_hz": float(point.f_hz),
            "b_pk_t": float(point.b_pk_t),
            "temperature_c": float(point.temperature_c), "truth": float(expected),
            "posterior_median": float(median), "posterior_p05": float(p05),
            "posterior_p95": float(p95), "relative_error": relative_error,
            "covered_by_latent_ci90": covered,
        })

    def summarize(group: list[dict[str, Any]]) -> dict[str, float | int]:
        errors = [float(row["relative_error"]) for row in group]
        return {
            "n_points": len(group),
            "relative_rmse_pct": math.sqrt(
                sum(value * value for value in errors) / len(errors)
            ) * 100.0,
            "median_absolute_relative_error_pct": statistics.median(
                abs(value) for value in errors
            ) * 100.0,
            "latent_ci90_coverage_fraction": sum(
                int(row["covered_by_latent_ci90"]) for row in group
            ) / len(group),
        }

    summary = {
        channel.value: summarize([
            row for row in rows if row["channel"] == channel.value
        ])
        for channel in Channel
    }
    pcv_by_temperature = {
        float(temperature): summarize([
            row for row in rows
            if row["channel"] == Channel.PCV.value
            and row["temperature_c"] == float(temperature)
        ])
        for temperature in sorted({
            row["temperature_c"] for row in rows
            if row["channel"] == Channel.PCV.value
        })
    }
    return {
        "summary": summary, "pcv_by_temperature_c": pcv_by_temperature,
        "points": rows,
    }


def gate_truth_evaluation(
    samples: np.ndarray, truth: MagneticParams, scenario: MismatchScenario,
    *, reached_precision_gate: bool, geometry: Geometry,
    pcv_error_threshold_pct: float, lm_error_threshold_pct: float,
) -> dict[str, Any]:
    """Detect a precise posterior whose target medians are materially wrong."""

    targets = {
        "pcv": DesignPoint(Channel.PCV, 1.0e5, 0.1, 25.0),
        "lm": DesignPoint(Channel.LM, 1.0e5, 0.0, 25.0),
    }
    errors: dict[str, float] = {}
    for name, point in targets.items():
        median = float(np.median(predict_active_batch(samples, point, geometry)))
        expected = mismatch_predict_one(truth, scenario, point, geometry)
        errors[name] = abs(median - expected) / abs(expected) * 100.0
    accurate = (
        errors["pcv"] <= pcv_error_threshold_pct
        and errors["lm"] <= lm_error_threshold_pct
    )
    return {
        "pcv_absolute_relative_error_pct": errors["pcv"],
        "lm_absolute_relative_error_pct": errors["lm"],
        "accuracy_thresholds_pct": {
            "pcv": pcv_error_threshold_pct, "lm": lm_error_threshold_pct,
        },
        "target_accuracy_passed": accurate,
        "false_confident": bool(reached_precision_gate and not accurate),
        "definition": (
            "precision gate reached while either target posterior median exceeds "
            "its preregistered absolute-relative-error threshold"
        ),
    }


def config_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def payload_sha256(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def validate_mismatch_result(record: dict[str, Any]) -> None:
    """Validate the structural and reconstructable parts of a seed result."""

    required = {
        "schema_version", "campaign_id", "config_sha256", "run_id", "seed",
        "scenario", "truth_anchor", "data", "inference_model", "policies",
        "endpoint_contract", "validity", "provenance",
    }
    if set(record) != required or record.get("schema_version") != MISMATCH_RESULT_SCHEMA:
        raise ValueError("model-mismatch result has an invalid top-level schema")
    if not isinstance(record["seed"], int) or record["seed"] <= 0:
        raise ValueError("model-mismatch result seed is invalid")
    if len(record["policies"]) != len(POLICIES) \
            or set(record["policies"]) != set(POLICIES):
        raise ValueError("model-mismatch result does not contain the exact policy registry")
    scenario = record["scenario"]
    if not isinstance(scenario, dict) or not isinstance(scenario.get("name"), str):
        raise ValueError("model-mismatch scenario is malformed")
    if record["inference_model"] != {
        "name": "isothermal_steinmetz_one_pole_cole_cole",
        "structural_discrepancy_terms_in_likelihood": False,
    }:
        raise ValueError("inference model must remain the original misspecified family")
    truth_anchor = record["truth_anchor"]
    if not isinstance(truth_anchor, dict) or not isinstance(
        truth_anchor.get("values"), dict
    ) or truth_anchor.get("sha256") != payload_sha256(truth_anchor["values"]):
        raise ValueError("truth anchor is not self-consistent")
    data = record["data"]
    if data.get("common_candidate_outcomes_across_policies") is not True \
            or data.get("holdout_used_for_acquisition_or_stopping") is not False:
        raise ValueError("paired-outcome or holdout separation contract was violated")
    for policy in POLICIES:
        result = record["policies"][policy]
        if set(result.get("mismatch_endpoints", {})) != {
            "holdout_latent_mean", "holdout_pcv_by_temperature_c",
            "holdout_point_records", "gate_truth_accuracy",
        }:
            raise ValueError(f"policy {policy} lacks mismatch endpoints")
        reached = result.get("reached")
        count = result.get("n_measurements_to_gate")
        cost = result.get("modeled_cost_to_gate")
        if not isinstance(reached, bool) or reached != (count is not None and cost is not None):
            raise ValueError(f"policy {policy} gate endpoints are inconsistent")
        false_confident = result["mismatch_endpoints"]["gate_truth_accuracy"][
            "false_confident"
        ]
        if false_confident and not reached:
            raise ValueError("false confidence requires reaching the precision gate")
    if set(record["validity"]) != {f"{policy}_convergence_valid" for policy in POLICIES}:
        raise ValueError("model-mismatch convergence-validity registry is incomplete")
    if any(value is not True for value in record["validity"].values()):
        raise ValueError("model-mismatch result contains a nonconverged policy")
