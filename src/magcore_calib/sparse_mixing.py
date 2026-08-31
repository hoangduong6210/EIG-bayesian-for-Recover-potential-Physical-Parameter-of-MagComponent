"""Prospective endpoint-free diagnostics for rejected sparse posteriors."""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import math
import os
import re
import sys
import tomllib
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
from scipy.stats import norm


SPARSE_MIXING_CONFIG_SCHEMA = "magcore-sparse-mixing-preregistration/1.0"
SPARSE_MIXING_RESULT_SCHEMA = "magcore-sparse-mixing-result/1.0"
SPARSE_MIXING_MANIFEST_SCHEMA = "magcore-sparse-mixing-manifest/1.0"
PARAMETER_NAMES = (
    "ln_k", "alpha", "beta", "ln_mu_s", "ln_f_rel_hz", "alpha_cc",
)


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def payload_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class SparseMixingTarget:
    target_id: str
    n_measurements: int
    state_identity_sha256: str
    original_mcmc_seed: int
    observation_manifest_sha256: str | None
    exact_initial_ensemble_sha256: str | None


@dataclass(frozen=True)
class SparseMixingTask:
    index: int
    task_id: str
    target: SparseMixingTarget
    initialization: str
    replicate: int
    seed: int
    warmup_steps: int
    retained_steps: int
    checkpoints: tuple[int, ...]
    exact_replay: bool


@dataclass(frozen=True)
class SparseMixingPlan:
    raw: dict[str, Any]
    config_sha256: str
    targets: tuple[SparseMixingTarget, ...]

    @property
    def protocol_id(self) -> str:
        return str(self.raw["protocol_id"])

    @property
    def task_count(self) -> int:
        return len(self.tasks())

    def tasks(self) -> tuple[SparseMixingTask, ...]:
        sampler = self.raw["sampler"]
        tasks: list[SparseMixingTask] = []
        for target in self.targets:
            tasks.append(SparseMixingTask(
                index=len(tasks),
                task_id=f"{target.target_id}_exact_replay_r0",
                target=target,
                initialization="exact_replay",
                replicate=0,
                seed=target.original_mcmc_seed,
                warmup_steps=sampler["exact_replay_burn_steps"],
                retained_steps=sampler["exact_replay_retained_steps"],
                checkpoints=(sampler["exact_replay_retained_steps"],),
                exact_replay=True,
            ))
            for family in sampler["initialization_families"]:
                for replicate in range(
                    sampler["independent_replicates_per_initialization"]
                ):
                    seed = derive_task_seed(
                        self.protocol_id, target.state_identity_sha256,
                        family, replicate,
                    )
                    tasks.append(SparseMixingTask(
                        index=len(tasks),
                        task_id=f"{target.target_id}_{family}_r{replicate}",
                        target=target,
                        initialization=family,
                        replicate=replicate,
                        seed=seed,
                        warmup_steps=sampler["independent_warmup_steps"],
                        retained_steps=sampler["independent_retained_steps"],
                        checkpoints=tuple(sampler["checkpoints"]),
                        exact_replay=False,
                    ))
        return tuple(tasks)

    def task(self, index: int) -> SparseMixingTask:
        if isinstance(index, bool) or not isinstance(index, int):
            raise TypeError("task index must be an integer")
        tasks = self.tasks()
        if not 0 <= index < len(tasks):
            raise IndexError("sparse-mixing task index is outside the matrix")
        return tasks[index]


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError(f"{label} must be a SHA-256 digest")
    return value


def load_sparse_mixing_plan(path: str | Path) -> SparseMixingPlan:
    config = Path(path).expanduser().resolve()
    with config.open("rb") as stream:
        raw = tomllib.load(stream)
    if raw.get("schema_version") != SPARSE_MIXING_CONFIG_SCHEMA:
        raise ValueError("unsupported sparse-mixing configuration schema")
    if raw.get("protocol_id") != "SparseMix-1" \
            or raw.get("status") != "preregistered_before_diagnostic_chains" \
            or raw.get("record_class") != "endpoint_free_sampler_diagnostic" \
            or raw.get("diagnostic_only") is not True \
            or raw.get("retroactive_mm2_admission_allowed") is not False:
        raise ValueError("sparse-mixing scope declaration is invalid")
    parent = raw.get("parent")
    if not isinstance(parent, dict) or parent.get("campaign_id") != "MM-2" \
            or parent.get("scenario") != "combined_mismatch" \
            or parent.get("seed") != 9123 \
            or parent.get("policy") != "random_channel_balanced":
        raise ValueError("sparse-mixing parent identity is invalid")
    for key in (
        "source_archive_sha256", "source_status_sha256", "config_sha256",
        "rejection_sha256", "failed_marker_sha256", "closeout_sha256",
        "truth_anchor_sha256",
    ):
        _digest(parent.get(key), f"parent {key}")
    if not re.fullmatch(r"[0-9a-f]{40}", str(parent.get("source_revision", ""))):
        raise ValueError("parent source revision is invalid")

    sampler = raw.get("sampler")
    if not isinstance(sampler, dict) \
            or sampler.get("implementation") != "emcee.EnsembleSampler" \
            or sampler.get("move") != "default_stretch_move" \
            or sampler.get("n_walkers") != 48 \
            or sampler.get("dimensions") != 6 \
            or sampler.get("initialization_families") != [
                "local_prior_center", "overdispersed_prior_lhs"
            ] \
            or sampler.get("early_stopping") is not False:
        raise ValueError("sparse-mixing sampler contract is invalid")
    for key in (
        "exact_replay_burn_steps", "exact_replay_retained_steps",
        "independent_warmup_steps", "independent_retained_steps",
        "independent_replicates_per_initialization", "thin_stride",
    ):
        _positive_int(sampler.get(key), f"sampler {key}")
    checkpoints = sampler.get("checkpoints")
    if not isinstance(checkpoints, list) or not checkpoints \
            or any(_positive_int(value, "checkpoint") != value
                   for value in checkpoints) \
            or checkpoints != sorted(set(checkpoints)) \
            or checkpoints[-1] != sampler["independent_retained_steps"]:
        raise ValueError("sparse-mixing checkpoints are invalid")

    outputs = raw.get("outputs")
    if not isinstance(outputs, dict) \
            or outputs.get("persist_full_chain_publicly") is not False \
            or outputs.get("persist_deterministic_thin") is not True \
            or outputs.get("persist_chain_block_hashes") is not True \
            or outputs.get("validator_requires_complete_matrix") is not True:
        raise ValueError("sparse-mixing output boundary is invalid")
    forbidden = outputs.get("forbidden_key_fragments")
    if not isinstance(forbidden, list) or not forbidden \
            or any(not isinstance(value, str) or not value for value in forbidden):
        raise ValueError("sparse-mixing endpoint denylist is invalid")

    raw_targets = raw.get("targets")
    if not isinstance(raw_targets, list) or len(raw_targets) != 2:
        raise ValueError("SparseMix-1 requires exactly two targets")
    targets: list[SparseMixingTarget] = []
    for entry in raw_targets:
        if not isinstance(entry, dict) or not {
            "target_id", "n_measurements", "state_identity_sha256",
            "original_mcmc_seed",
        } <= set(entry):
            raise ValueError("sparse-mixing target schema is invalid")
        targets.append(SparseMixingTarget(
            target_id=str(entry["target_id"]),
            n_measurements=_positive_int(
                entry["n_measurements"], "target measurement count"
            ),
            state_identity_sha256=_digest(
                entry["state_identity_sha256"], "target state identity"
            ),
            original_mcmc_seed=_positive_int(
                entry["original_mcmc_seed"], "target MCMC seed"
            ),
            observation_manifest_sha256=(
                _digest(entry["observation_manifest_sha256"],
                        "target observation manifest")
                if "observation_manifest_sha256" in entry else None
            ),
            exact_initial_ensemble_sha256=(
                _digest(entry["exact_initial_ensemble_sha256"],
                        "target exact initial ensemble")
                if "exact_initial_ensemble_sha256" in entry else None
            ),
        ))
    if [(target.target_id, target.n_measurements) for target in targets] \
            != [("n3", 3), ("n4", 4)] \
            or len({target.state_identity_sha256 for target in targets}) != 2:
        raise ValueError("sparse-mixing targets differ from the locked rejection")
    plan = SparseMixingPlan(raw=raw, config_sha256=sha256_file(config),
                            targets=tuple(targets))
    if plan.task_count != 18:
        raise ValueError("SparseMix-1 task matrix must contain 18 ensembles")
    return plan


def derive_task_seed(protocol_id: str, state_sha256: str,
                     initialization: str, replicate: int) -> int:
    payload = "|".join((
        protocol_id, state_sha256, initialization, str(replicate)
    )).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:4], "big")


@dataclass(frozen=True)
class FrozenModules:
    acquisition: ModuleType
    diagnostics: ModuleType
    inference: ModuleType
    model_mismatch: ModuleType
    models: ModuleType
    prior: ModuleType


def load_frozen_modules(source_root: str | Path) -> FrozenModules:
    """Load the MM-2 package under an isolated name from its frozen tree."""

    root = Path(source_root).expanduser().resolve()
    package = root / "src/magcore_calib"
    init = package / "__init__.py"
    if not init.is_file():
        raise FileNotFoundError("frozen MM-2 package is missing")
    prefix = "mm2_frozen_magcore_calib"
    for name in tuple(sys.modules):
        if name == prefix or name.startswith(prefix + "."):
            del sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        prefix, init, submodule_search_locations=[str(package)]
    )
    if spec is None or spec.loader is None:
        raise ImportError("cannot load frozen MM-2 package")
    module = importlib.util.module_from_spec(spec)
    sys.modules[prefix] = module
    spec.loader.exec_module(module)
    return FrozenModules(**{
        name: importlib.import_module(f"{prefix}.{name}")
        for name in (
            "acquisition", "diagnostics", "inference", "model_mismatch",
            "models", "prior",
        )
    })


def _namespaced_policy_seed(base_seed: int, namespace: str) -> int:
    payload = f"magcore-policy-v1|{base_seed}|{namespace}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def _posterior_state_seed(base_seed: int, state_key: tuple[str, ...]) -> int:
    encoded = json.dumps({
        "namespace": "magcore-posterior-state-v1",
        "base_seed": int(base_seed),
        "observed_design_identities": list(sorted(state_key)),
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return int.from_bytes(hashlib.sha256(encoded).digest()[:4], "big")


def _fixed_channel_balanced_order(library: list[Any], channel_enum: Any) -> list[Any]:
    groups: dict[Any, list[Any]] = defaultdict(list)
    for point in library:
        groups[point.channel].append(point)
    channels = (
        channel_enum.PCV, channel_enum.MU_REAL,
        channel_enum.MU_IMAG, channel_enum.LM,
    )
    order: list[Any] = []
    while any(groups[channel] for channel in channels):
        for channel in channels:
            if groups[channel]:
                order.append(groups[channel].pop(0))
    return order


@dataclass(frozen=True)
class ReconstructedState:
    observations: tuple[Any, ...]
    identities: tuple[str, ...]
    observation_manifest: tuple[dict[str, str], ...]
    observation_manifest_sha256: str
    truth_anchor_sha256: str
    state_identity_sha256: str
    mcmc_seed: int
    spec: Any
    geometry: Any
    modules: FrozenModules


def reconstruct_state(plan: SparseMixingPlan, target: SparseMixingTarget,
                      source_root: str | Path, mm2_config: str | Path
                      ) -> ReconstructedState:
    modules = load_frozen_modules(source_root)
    parent = plan.raw["parent"]
    config = Path(mm2_config).expanduser().resolve()
    if sha256_file(config) != parent["config_sha256"]:
        raise ValueError("MM-2 configuration digest mismatch")
    mm2_plan = modules.model_mismatch.load_model_mismatch_plan(config)
    if mm2_plan.campaign_id != "MM-2" \
            or parent["seed"] not in mm2_plan.seeds:
        raise ValueError("MM-2 configuration identity mismatch")
    spec = modules.prior.DatasheetPrior()
    geometry = modules.models.Geometry()
    truth = modules.prior.draw_prior_predictive(
        spec, np.random.default_rng(parent["seed"])
    )
    truth_values = {
        "k": truth.k, "alpha": truth.alpha, "beta": truth.beta,
        "mu_s": truth.mu_s, "f_rel_hz": truth.f_rel_hz,
        "alpha_cc": truth.alpha_cc,
    }
    truth_hash = payload_sha256(truth_values)
    if truth_hash != parent["truth_anchor_sha256"]:
        raise ValueError("MM-2 truth reconstruction digest mismatch")
    scenario = mm2_plan.scenario(parent["scenario"])
    library = modules.model_mismatch.mismatch_candidate_library(
        mm2_plan.temperatures_c
    )
    outcomes = modules.model_mismatch.stable_mismatch_outcomes(
        truth, scenario, library, seed=parent["seed"], geometry=geometry
    )
    selected = _fixed_channel_balanced_order(library, modules.models.Channel)[:2]
    random_order = modules.acquisition.random_channel_balanced_order(
        library,
        seed=_namespaced_policy_seed(
            parent["seed"], "random_channel_balanced/v1"
        ),
        selected=selected,
    )
    while len(selected) < target.n_measurements:
        selected.append(next(point for point in random_order if point not in selected))
    identities = tuple(sorted(point.exact_key() for point in selected))
    observations = tuple(outcomes[identity] for identity in identities)
    manifest = tuple({
        "identity": identity,
        "value_hex": float(outcomes[identity].value).hex(),
        "sigma_hex": float(outcomes[identity].sigma).hex(),
    } for identity in identities)
    state_hash = payload_sha256(list(identities))
    mcmc_seed = _posterior_state_seed(parent["seed"], identities)
    manifest_hash = payload_sha256(list(manifest))
    if state_hash != target.state_identity_sha256 \
            or mcmc_seed != target.original_mcmc_seed:
        raise ValueError("reconstructed posterior state differs from MM-2 rejection")
    if target.observation_manifest_sha256 is not None \
            and manifest_hash != target.observation_manifest_sha256:
        raise ValueError("reconstructed observation manifest digest mismatch")
    return ReconstructedState(
        observations=observations, identities=identities,
        observation_manifest=manifest,
        observation_manifest_sha256=manifest_hash,
        truth_anchor_sha256=truth_hash,
        state_identity_sha256=state_hash, mcmc_seed=mcmc_seed,
        spec=spec, geometry=geometry, modules=modules,
    )


def initial_ensemble(state: ReconstructedState, task: SparseMixingTask,
                     n_walkers: int = 48) -> np.ndarray:
    prior = state.modules.prior
    center = prior.prior_center_vector(state.spec)
    rng = np.random.default_rng(task.seed)
    if task.initialization in {"exact_replay", "local_prior_center"}:
        scales = np.array([0.05, 0.02, 0.02, 0.05, 0.05, 0.02])
        initial = center + rng.normal(size=(n_walkers, 6)) * scales
    elif task.initialization == "overdispersed_prior_lhs":
        sds = np.array([
            state.spec.log10_k_sd * math.log(10.0), state.spec.alpha_sd,
            state.spec.beta_sd, state.spec.ln_mu_s_sd,
            state.spec.ln_f_rel_hz_sd, state.spec.alpha_cc_sd,
        ])
        initial = np.empty((n_walkers, 6), dtype=float)
        for column, name in enumerate(PARAMETER_NAMES):
            order = rng.permutation(n_walkers)
            unit = (order + rng.random(n_walkers)) / n_walkers
            lower, upper = prior.BOUNDS[name]
            cdf_low = 0.0 if not math.isfinite(lower) else norm.cdf(
                (lower - center[column]) / sds[column]
            )
            cdf_high = 1.0 if not math.isfinite(upper) else norm.cdf(
                (upper - center[column]) / sds[column]
            )
            probabilities = cdf_low + unit * (cdf_high - cdf_low)
            initial[:, column] = (
                center[column] + sds[column] * norm.ppf(probabilities)
            )
    else:  # pragma: no cover - plan validation prevents this branch
        raise ValueError("unsupported sparse-mixing initialization")
    if any(not math.isfinite(state.modules.prior.log_prior_active(row, state.spec))
           for row in initial):
        raise ValueError("sparse-mixing initialization contains an invalid walker")
    if task.exact_replay and task.target.exact_initial_ensemble_sha256 is not None:
        encoded = [[float(value).hex() for value in row] for row in initial]
        if payload_sha256(encoded) != task.target.exact_initial_ensemble_sha256:
            raise ValueError("exact replay initial ensemble digest mismatch")
    return initial


def contains_forbidden_key(value: Any, fragments: list[str]) -> str | None:
    if isinstance(value, dict):
        for key, nested in value.items():
            lowered = str(key).lower()
            for fragment in fragments:
                if fragment.lower() in lowered:
                    return str(key)
            found = contains_forbidden_key(nested, fragments)
            if found is not None:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = contains_forbidden_key(nested, fragments)
            if found is not None:
                return found
    return None


def validate_sparse_mixing_result(record: dict[str, Any],
                                  plan: SparseMixingPlan) -> None:
    required = {
        "schema_version", "record_class", "protocol_id", "config_sha256",
        "task", "parent", "reconstruction", "sampler", "checkpoints",
        "final_diagnostics", "thin", "chain_block_sha256", "disclosure",
    }
    if set(record) != required \
            or record.get("schema_version") != SPARSE_MIXING_RESULT_SCHEMA \
            or record.get("record_class") != "endpoint_free_sampler_diagnostic" \
            or record.get("protocol_id") != plan.protocol_id \
            or record.get("config_sha256") != plan.config_sha256:
        raise ValueError("sparse-mixing result schema is invalid")
    if record.get("disclosure") != {
        "claim_bearing_result": False,
        "scientific_endpoints_included": False,
        "retroactive_mm2_admission_allowed": False,
    }:
        raise ValueError("sparse-mixing disclosure is invalid")
    forbidden = contains_forbidden_key(
        record, plan.raw["outputs"]["forbidden_key_fragments"]
    )
    if forbidden is not None:
        raise ValueError(f"sparse-mixing result contains forbidden key: {forbidden}")
    thin = record.get("thin")
    if not isinstance(thin, dict) or set(thin) != {
        "path", "sha256", "shape", "stride",
    } or not re.fullmatch(r"[0-9a-f]{64}", str(thin.get("sha256", ""))):
        raise ValueError("sparse-mixing thin artifact is invalid")


def write_json_create_only(path: str | Path, payload: dict[str, Any]) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite sparse-mixing record: {destination}")
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.partial")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(payload, stream, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o640)
        os.link(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def write_npz_create_only(path: str | Path, **arrays: np.ndarray) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite sparse-mixing thin: {destination}")
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.partial")
    try:
        with temporary.open("xb") as stream:
            np.savez_compressed(stream, **arrays)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o640)
        os.link(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination
