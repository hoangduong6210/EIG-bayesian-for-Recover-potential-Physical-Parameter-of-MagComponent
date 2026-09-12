#!/usr/bin/env python3
"""Fixed-horizon endpoint-free sampler pilot on two locked posterior states."""

from __future__ import annotations

import argparse
import os
import time
import tomllib
from pathlib import Path
from typing import Any

import numpy as np

from magcore_calib.runtime import require_slurm
from magcore_calib.sparse_mixing import (
    PARAMETER_NAMES, SparseMixingTask, contains_forbidden_key, derive_task_seed, initial_ensemble,
    load_sparse_mixing_plan, payload_sha256, reconstruct_state, sha256_file,
    write_json_create_only, write_npz_create_only,
)
from magcore_calib.sparse_transport import VectorizedPosterior, to_original, to_unconstrained


def load_config(path: Path) -> dict[str, Any]:
    path = Path(path).resolve()
    with path.open("rb") as stream:
        config = tomllib.load(stream)
    if config.get("schema_version") != "magcore-sparse-mixing-pilot/1.0" or config.get("protocol_id") != "SparseMix-Pilot-1":
        raise ValueError("unsupported sparse sampler pilot protocol")
    if config.get("record_class") != "endpoint_free_technical_pilot" or config.get("diagnostic_only") is not True or config.get("retroactive_mm2_admission_allowed") is not False or type(config.get("n_walkers")) is not int or config["n_walkers"] != 48:
        raise ValueError("pilot disclosure or walker contract is invalid")
    selection = config.get("selection", {})
    if selection.get("require_complete_matrix") is not True or selection.get("confirmatory_seeds_must_be_new") is not True or selection.get("scientific_endpoints_allowed") is not False:
        raise ValueError("pilot selection boundary is invalid")
    if config.get("arms") != ["stretch", "de_snooker", "logit_stretch"] or config.get("families") != ["local_prior_center", "overdispersed_prior_lhs"]:
        raise ValueError("pilot arms or initialization families differ from design")
    for field, expected in (("replicates", 2), ("warmup", 10000), ("retained", 80000)):
        if type(config.get(field)) is not int or config[field] != expected:
            raise ValueError(f"pilot {field} differs from fixed design")
    if config.get("checkpoints") != [20000, 40000, 60000, 80000]:
        raise ValueError("pilot checkpoint schedule differs from fixed design")
    parent = (path.parent.parent / config["parent_config"]).resolve()
    if sha256_file(parent) != config["parent_config_sha256"]:
        raise ValueError("pilot parent configuration checksum mismatch")
    load_sparse_mixing_plan(parent)
    return {**config, "_config_sha256": sha256_file(path), "_parent_path": str(parent)}


def tasks(config: dict[str, Any]) -> list[dict[str, Any]]:
    plan = load_sparse_mixing_plan(config["_parent_path"])
    result = []
    for target in plan.targets:
        for arm in config["arms"]:
            for family in config["families"]:
                for replicate in range(config["replicates"]):
                    initial_seed = derive_task_seed(config["protocol_id"], target.state_identity_sha256, family, replicate)
                    sampler_seed = derive_task_seed(config["protocol_id"] + "/" + arm, target.state_identity_sha256, family, replicate)
                    result.append({
                        "index": len(result), "task_id": f"{target.target_id}_{arm}_{family}_r{replicate}",
                        "target_id": target.target_id, "arm": arm,
                        "initialization": family, "replicate": replicate,
                        "initial_seed": initial_seed, "sampler_seed": sampler_seed,
                    })
    return result


def _diagnostics(chain: np.ndarray, sampler: Any, modules: Any) -> dict[str, Any]:
    import emcee

    # Transform proposals back before computing autocorrelation and ESS.
    try:
        tau = emcee.autocorr.integrated_time(chain, tol=0)
    except emcee.autocorr.AutocorrError:
        tau = np.full(6, np.nan)
    report = modules.diagnostics.diagnostic_report(chain, sampler.acceptance_fraction, tau)
    finite = float(np.mean(np.isfinite(sampler.get_log_prob())))
    report.update(retained_steps=len(chain), finite_log_probability_fraction=finite)
    report["valid"] = bool(report["valid"] and finite == 1.0)
    return report


def _parameter_summary(chain: np.ndarray) -> dict[str, dict[str, float]]:
    flat = chain.reshape(-1, 6)
    quantiles = np.percentile(flat, [5, 25, 50, 75, 95], axis=0)
    sd = np.std(flat, axis=0, ddof=1)
    return {name: {
        "quantile_05": float(quantiles[0, i]), "quantile_25": float(quantiles[1, i]),
        "median": float(quantiles[2, i]), "quantile_75": float(quantiles[3, i]),
        "quantile_95": float(quantiles[4, i]), "sd": float(sd[i]),
        "iqr": float(quantiles[3, i] - quantiles[1, i]),
    } for i, name in enumerate(PARAMETER_NAMES)}


def run_task(config: dict[str, Any], task: dict[str, Any], *, mm2_source: Path,
             mm2_config: Path, out_dir: Path) -> dict[str, Any]:
    require_slurm()
    import emcee

    expected_tasks = tasks(config)
    if task not in expected_tasks:
        raise ValueError("task does not belong to pilot matrix")
    out_dir = Path(out_dir)
    paths = {name: out_dir / f"{task['task_id']}{suffix}" for name, suffix in
             (("chain", ".chain.npz"), ("record", ".json"), ("success", ".SUCCESS.json"))}
    if any(path.exists() for path in paths.values()):
        raise FileExistsError("pilot task artifacts already exist; use a new attempt directory")
    plan = load_sparse_mixing_plan(config["_parent_path"])
    target = next(item for item in plan.targets if item.target_id == task["target_id"])
    state = reconstruct_state(plan, target, mm2_source, mm2_config)
    initialization_task = SparseMixingTask(
        index=task["index"], task_id=task["task_id"], target=target,
        initialization=task["initialization"], replicate=task["replicate"],
        seed=task["initial_seed"], warmup_steps=config["warmup"],
        retained_steps=config["retained"], checkpoints=tuple(config["checkpoints"]), exact_replay=False,
    )
    initial = initial_ensemble(state, initialization_task, n_walkers=48)
    prepared = state.modules.inference.prepare_likelihood(list(state.observations), state.geometry)
    posterior = VectorizedPosterior(prepared, state.spec, state.modules)
    parity = posterior.check_scalar_parity(initial)
    moves: Any = emcee.moves.StretchMove(a=2.0)
    transformed = task["arm"] == "logit_stretch"
    if task["arm"] == "de_snooker":
        moves = [(emcee.moves.DEMove(), 0.8), (emcee.moves.DESnookerMove(), 0.2)]
    sampler = emcee.EnsembleSampler(48, 6, posterior.transformed if transformed else posterior,
                                    moves=moves, vectorize=True)
    sampler.random_state = np.random.RandomState(task["sampler_seed"]).get_state()
    start = time.perf_counter()
    warm_state = sampler.run_mcmc(to_unconstrained(initial) if transformed else initial,
                                  config["warmup"], progress=False)
    sampler.reset()
    records = []
    retained = 0
    for checkpoint in config["checkpoints"]:
        warm_state = sampler.run_mcmc(warm_state, checkpoint - retained, progress=False)
        retained = checkpoint
        chain = to_original(sampler.get_chain()) if transformed else sampler.get_chain()
        records.append(_diagnostics(chain, sampler, state.modules))
    elapsed = time.perf_counter() - start
    expected_shape = (config["retained"], 48, 6)
    if chain.shape != expected_shape or not np.all(np.isfinite(chain)):
        raise RuntimeError("pilot retained chain is malformed")
    final_parity = posterior.check_scalar_parity(chain[-1])
    # Store original active coordinates for every retained draw, with no thinning.
    write_npz_create_only(paths["chain"], chain=chain, log_probability=sampler.get_log_prob(), initial=initial)
    result = {
        "schema_version": "magcore-sparse-mixing-pilot-result/1.0",
        "record_class": "endpoint_free_sampler_pilot", "protocol_id": config["protocol_id"],
        "config_sha256": config["_config_sha256"], "parent_config_sha256": plan.config_sha256,
        "task": task, "reconstruction": {
            "state_identity_sha256": state.state_identity_sha256,
            "observation_manifest_sha256": state.observation_manifest_sha256,
            "observation_count": len(state.observations),
            "initial_ensemble_sha256": payload_sha256([[float(value).hex() for value in row] for row in initial]),
        },
        "sampler": {"implementation": "emcee.EnsembleSampler", "version": emcee.__version__,
                    "arm": task["arm"], "n_walkers": 48, "dimensions": 6,
                    "warmup_steps": config["warmup"], "retained_steps": config["retained"],
                    "early_stopping": False, "vectorize": True,
                    "diagnostic_coordinates": list(PARAMETER_NAMES),
                    "density_coordinates": "alpha_cc_logit" if transformed else "original_active",
                    "acceptance_window": "retained_only"},
        "density_parity": {"initial": parity, "final": final_parity},
        "checkpoints": records, "final_diagnostics": {
            "sampler_diagnostics": records[-1], "parameter_summary": _parameter_summary(chain)},
        "chain": {"path": paths["chain"].name, "sha256": sha256_file(paths["chain"]),
                  "shape": list(chain.shape), "coordinates": list(PARAMETER_NAMES),
                  "log_probability_coordinates": "alpha_cc_logit" if transformed else "original_active"},
        "execution": {"sampling_and_diagnostics_seconds": elapsed,
                      "scheduler": {name: os.environ[name] for name in
                                    ("SLURM_JOB_ID", "SLURM_JOB_NODELIST", "SLURM_ARRAY_JOB_ID", "SLURM_ARRAY_TASK_ID") if name in os.environ}},
        "disclosure": {"claim_bearing_result": False, "scientific_endpoints_included": False,
                       "retroactive_mm2_admission_allowed": False,
                       "confirmatory_sampler_validation": False},
    }
    forbidden = contains_forbidden_key(result, plan.raw["outputs"]["forbidden_key_fragments"])
    if forbidden is not None:
        raise ValueError(f"pilot result contains forbidden key: {forbidden}")
    write_json_create_only(paths["record"], result)
    write_json_create_only(paths["success"], {"task_id": task["task_id"], "record_sha256": sha256_file(paths["record"]),
                                            "chain_sha256": result["chain"]["sha256"]})
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--task-id", type=int, required=True)
    parser.add_argument("--mm2-source", type=Path, required=True)
    parser.add_argument("--mm2-config", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    require_slurm()  # Reject login execution before reading any config or data.
    config = load_config(args.config)
    matrix = tasks(config)
    if not 0 <= args.task_id < len(matrix):
        parser.error("task id is outside the pilot matrix")
    run_task(config, matrix[args.task_id], mm2_source=args.mm2_source,
             mm2_config=args.mm2_config, out_dir=args.out_dir)


if __name__ == "__main__":
    main()
