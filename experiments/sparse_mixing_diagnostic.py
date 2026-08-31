#!/usr/bin/env python3
"""Run one fixed SparseMix-1 ensemble without scientific endpoints."""

from __future__ import annotations

import argparse
import hashlib
import math
import multiprocessing
from contextlib import nullcontext
from pathlib import Path
from typing import Any

import numpy as np

from magcore_calib.runtime import require_slurm
from magcore_calib.sparse_mixing import (
    PARAMETER_NAMES,
    SPARSE_MIXING_RESULT_SCHEMA,
    SparseMixingPlan,
    SparseMixingTask,
    initial_ensemble,
    load_sparse_mixing_plan,
    reconstruct_state,
    sha256_file,
    validate_sparse_mixing_result,
    write_json_create_only,
    write_npz_create_only,
)


def _checkpoint_diagnostics(sampler: Any, warmup: int, modules: Any) -> dict:
    chain = sampler.get_chain(discard=warmup, flat=False)
    log_probability = sampler.get_log_prob(discard=warmup, flat=True)
    try:
        tau = np.asarray(sampler.get_autocorr_time(discard=warmup, tol=0), dtype=float)
    except Exception:
        tau = np.full(6, np.nan)
    report = modules.diagnostics.diagnostic_report(
        chain, sampler.acceptance_fraction, tau
    )
    report["finite_log_probability_fraction"] = float(
        np.mean(np.isfinite(log_probability))
    )
    report["valid"] = bool(
        report["valid"]
        and report["finite_log_probability_fraction"] == 1.0
    )
    report["retained_steps"] = int(chain.shape[0])
    report["acceptance_by_walker"] = {
        "minimum": float(np.min(sampler.acceptance_fraction)),
        "median": float(np.median(sampler.acceptance_fraction)),
        "maximum": float(np.max(sampler.acceptance_fraction)),
    }
    return report


def _parameter_summary(chain: np.ndarray) -> dict[str, dict[str, float]]:
    flat = chain.reshape((-1, 6))
    summary: dict[str, dict[str, float]] = {}
    first = chain[: chain.shape[0] // 2].reshape((-1, 6))
    second = chain[chain.shape[0] // 2:].reshape((-1, 6))
    for index, name in enumerate(PARAMETER_NAMES):
        quantile_05, quantile_25, median, quantile_75, quantile_95 = np.percentile(
            flat[:, index], [5, 25, 50, 75, 95]
        )
        first_quantiles = np.percentile(first[:, index], [5, 50, 95])
        second_quantiles = np.percentile(second[:, index], [5, 50, 95])
        sd = float(np.std(flat[:, index], ddof=1))
        iqr = float(quantile_75 - quantile_25)
        summary[name] = {
            "quantile_05": float(quantile_05),
            "quantile_25": float(quantile_25),
            "median": float(median),
            "quantile_75": float(quantile_75),
            "quantile_95": float(quantile_95),
            "sd": sd, "iqr": iqr,
            "split_half_lower_tail_difference": float(
                second_quantiles[0] - first_quantiles[0]
            ),
            "split_half_median_difference": float(
                second_quantiles[1] - first_quantiles[1]
            ),
            "split_half_upper_tail_difference": float(
                second_quantiles[2] - first_quantiles[2]
            ),
        }
    return summary


def _boundary_mass(chain: np.ndarray, modules: Any) -> dict[str, dict[str, float]]:
    flat = chain.reshape((-1, 6))
    output: dict[str, dict[str, float]] = {}
    for index, name in enumerate(PARAMETER_NAMES):
        lower, upper = modules.prior.BOUNDS[name]
        entry: dict[str, float] = {}
        if math.isfinite(lower):
            width = max(0.01, 0.01 * max(1.0, abs(lower)))
            entry["near_lower_fraction"] = float(np.mean(flat[:, index] <= lower + width))
        if math.isfinite(upper):
            width = max(0.01, 0.01 * max(1.0, abs(upper)))
            entry["near_upper_fraction"] = float(np.mean(flat[:, index] >= upper - width))
        output[name] = entry
    return output


def _magnetic_geometry(chain: np.ndarray) -> dict[str, Any]:
    magnetic = chain[:, :, 3:6].reshape((-1, 3))
    covariance = np.cov(magnetic, rowvar=False)
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    largest = float(np.max(eigenvalues))
    smallest = float(np.min(eigenvalues))
    return {
        "parameter_names": list(PARAMETER_NAMES[3:6]),
        "covariance_condition_number": (
            float(largest / smallest) if smallest > 0.0 else None
        ),
        "eigenvalues_ascending": [float(value) for value in eigenvalues],
        "principal_direction": [float(value) for value in eigenvectors[:, -1]],
    }


def _hash_chain_blocks(chain: np.ndarray, checkpoints: tuple[int, ...]) -> list[dict]:
    records: list[dict] = []
    start = 0
    for stop in checkpoints:
        digest = hashlib.sha256()
        for block_start in range(start, stop, 4096):
            block = np.ascontiguousarray(chain[block_start:min(stop, block_start + 4096)])
            digest.update(block.tobytes(order="C"))
        records.append({
            "start_step": start,
            "stop_step": stop,
            "sha256": digest.hexdigest(),
        })
        start = stop
    return records


def run_sparse_mixing_task(
    plan: SparseMixingPlan,
    task: SparseMixingTask,
    *,
    mm2_source: Path,
    mm2_config: Path,
    thin_out: Path,
    workers: int = 1,
) -> dict:
    """Run a fixed ensemble. Tests may replace emcee; production requires SLURM."""

    import emcee

    state = reconstruct_state(plan, task.target, mm2_source, mm2_config)
    initial = initial_ensemble(
        state, task, n_walkers=plan.raw["sampler"]["n_walkers"]
    )
    prepared = state.modules.inference.prepare_likelihood(
        list(state.observations), state.geometry
    )
    pool_context = (
        multiprocessing.get_context("fork").Pool(workers)
        if workers > 1 else nullcontext(None)
    )
    with pool_context as pool:
        sampler = emcee.EnsembleSampler(
            plan.raw["sampler"]["n_walkers"], 6,
            state.modules.inference._log_posterior_prepared,
            args=(prepared, state.spec), pool=pool,
        )
        sampler.random_state = np.random.RandomState(task.seed).get_state()
        sampler.run_mcmc(initial, task.warmup_steps, progress=False)
        checkpoint_records: list[dict] = []
        retained = 0
        for checkpoint in task.checkpoints:
            sampler.run_mcmc(None, checkpoint - retained, progress=False)
            retained = checkpoint
            checkpoint_records.append(
                _checkpoint_diagnostics(sampler, task.warmup_steps, state.modules)
            )
        chain = sampler.get_chain(discard=task.warmup_steps, flat=False)
    if chain.shape != (task.retained_steps, 48, 6):
        raise RuntimeError("SparseMix-1 retained chain has an unexpected shape")
    stride = plan.raw["sampler"]["thin_stride"]
    thin = np.ascontiguousarray(chain[stride - 1::stride], dtype=np.float64)
    write_npz_create_only(thin_out, chain=thin)
    final_report = checkpoint_records[-1]
    final = {
        "sampler_diagnostics": final_report,
        "parameter_summary": _parameter_summary(chain),
        "boundary_mass": _boundary_mass(chain, state.modules),
        "magnetic_covariance_geometry": _magnetic_geometry(chain),
    }
    return {
        "schema_version": SPARSE_MIXING_RESULT_SCHEMA,
        "record_class": "endpoint_free_sampler_diagnostic",
        "protocol_id": plan.protocol_id,
        "config_sha256": plan.config_sha256,
        "task": {
            "index": task.index, "task_id": task.task_id,
            "target_id": task.target.target_id,
            "initialization": task.initialization,
            "replicate": task.replicate, "seed": task.seed,
            "exact_replay": task.exact_replay,
        },
        "parent": {
            "campaign_id": plan.raw["parent"]["campaign_id"],
            "run_id": plan.raw["parent"]["run_id"],
            "source_revision": plan.raw["parent"]["source_revision"],
            "source_archive_sha256": plan.raw["parent"]["source_archive_sha256"],
            "config_sha256": plan.raw["parent"]["config_sha256"],
            "rejection_sha256": plan.raw["parent"]["rejection_sha256"],
            "closeout_sha256": plan.raw["parent"]["closeout_sha256"],
        },
        "reconstruction": {
            "state_identity_sha256": state.state_identity_sha256,
            "observation_count": len(state.observations),
            "observation_manifest_sha256": state.observation_manifest_sha256,
            "mcmc_seed": state.mcmc_seed,
        },
        "sampler": {
            "implementation": plan.raw["sampler"]["implementation"],
            "move": plan.raw["sampler"]["move"],
            "n_walkers": 48, "dimensions": 6,
            "warmup_steps": task.warmup_steps,
            "retained_steps": task.retained_steps,
            "early_stopping": False,
        },
        "checkpoints": checkpoint_records,
        "final_diagnostics": final,
        "thin": {
            "path": thin_out.name,
            "sha256": sha256_file(thin_out),
            "shape": list(thin.shape),
            "stride": stride,
        },
        "chain_block_sha256": _hash_chain_blocks(chain, task.checkpoints),
        "disclosure": {
            "claim_bearing_result": False,
            "scientific_endpoints_included": False,
            "retroactive_mm2_admission_allowed": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--task-id", required=True, type=int)
    parser.add_argument("--mm2-source", required=True, type=Path)
    parser.add_argument("--mm2-config", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--thin-out", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    require_slurm()
    plan = load_sparse_mixing_plan(args.config)
    task = plan.task(args.task_id)
    record = run_sparse_mixing_task(
        plan, task, mm2_source=args.mm2_source, mm2_config=args.mm2_config,
        thin_out=args.thin_out, workers=args.workers,
    )
    validate_sparse_mixing_result(record, plan)
    write_json_create_only(args.out, record)


if __name__ == "__main__":
    main()
