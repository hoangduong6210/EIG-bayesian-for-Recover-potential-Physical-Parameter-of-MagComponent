"""Focused tests for orchestration and v4 freeze gates."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_validate_run():
    path = ROOT / "scripts/validate_run.py"
    spec = importlib.util.spec_from_file_location("validate_run_campaign_tests", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_input_manifest_resolves_staged_root_and_paths_with_spaces(tmp_path: Path):
    module = load_validate_run()
    data_root = tmp_path / "staged data"
    input_path = data_root / "curves" / "material one.csv"
    input_path.parent.mkdir(parents=True)
    input_path.write_text("frequency,value\n1,2\n", encoding="utf-8")
    digest = hashlib.sha256(input_path.read_bytes()).hexdigest()
    manifest = tmp_path / "checksums.sha256"
    manifest.write_text(
        f"{digest}  data/external/materialdatabase/data/curves/material one.csv\n",
        encoding="utf-8",
    )
    report = module.verify_input_data_manifest(manifest, data_root)
    assert report == {
        "verified_file_count": 1,
        "files": [{"path": "curves/material one.csv", "sha256": digest}],
    }


@pytest.mark.parametrize(
    "line, message",
    [
        ("not-a-digest  data/external/materialdatabase/data/a.csv\n", "malformed"),
        ("{digest}  ../../outside.csv\n", "unsupported"),
        ("{digest}  data/external/materialdatabase/data/../outside.csv\n", "unsafe"),
    ],
)
def test_input_manifest_rejects_malformed_or_escaping_entries(
    tmp_path: Path, line: str, message: str,
):
    module = load_validate_run()
    data_root = tmp_path / "data"
    data_root.mkdir()
    manifest = tmp_path / "checksums.sha256"
    manifest.write_text(line.format(digest="a" * 64), encoding="utf-8")
    with pytest.raises((ValueError, FileNotFoundError), match=message):
        module.verify_input_data_manifest(manifest, data_root)


def _point_evidence(module) -> tuple[list[dict], dict[str, dict]]:
    rows = []
    for channel_index, (channel, n_points) in enumerate(
        module.BENCHMARK_V4_HOLDOUT_COUNTS.items()
    ):
        for index in range(n_points):
            error = 0.001 * (channel_index + index + 1)
            frequency = 1000.0 + index
            flux = 0.1
            temperature = 25.0
            rows.append({
                "design_key": f"{channel}-{index}",
                "design_identity": "|".join((
                    channel, frequency.hex(), flux.hex(), temperature.hex(),
                )),
                "channel": channel,
                "frequency_hz": frequency,
                "b_pk_t": flux,
                "temperature_c": temperature,
                "truth": 100.0,
                "posterior_median": 100.0 * (1.0 + error),
                "posterior_p05": 90.0,
                "posterior_p95": 110.0,
                "covered_by_latent_ci90": True,
                "relative_error": error,
            })
    summary = {}
    for channel, n_points in module.BENCHMARK_V4_HOLDOUT_COUNTS.items():
        errors = np.asarray([
            row["relative_error"] for row in rows if row["channel"] == channel
        ])
        summary[channel] = {
            "n_points": n_points,
            "relative_rmse_pct": float(np.sqrt(np.mean(errors ** 2)) * 100.0),
            "median_absolute_relative_error_pct": float(np.median(np.abs(errors)) * 100.0),
            "latent_ci90_coverage_fraction": 1.0,
        }
    return rows, summary


def _campaign_record(module, seed: int, estimator_hash: str) -> dict:
    rows, holdout = _point_evidence(module)
    holdout_payload = json.dumps(
        sorted(row["design_identity"] for row in rows),
        sort_keys=True, separators=(",", ":"),
    ).encode()
    policies = {}
    for index, (name, objective) in enumerate(module.BENCHMARK_V4_POLICY_OBJECTIVES.items()):
        count = 4 + index
        policies[name] = {
            "reached": True,
            "n_measurements_to_gate": count,
            "modeled_cost_to_gate": float(100 + index),
            "validation_endpoints": {
                "used_for_acquisition_or_stopping": False,
                "holdout_latent_mean": holdout,
                "holdout_point_records": rows,
            },
            "trajectory": [{
                "n_measurements": count,
                "selected_identities": [f"selected-{i}" for i in range(count)],
            }],
        }
    fixed = policies["fixed_channel_balanced"]
    endpoints = {}
    for name, policy in policies.items():
        if name == "fixed_channel_balanced":
            continue
        endpoints[f"{name}_vs_fixed"] = {
            "both_reached_gate": True,
            "measurement_count_difference": (
                fixed["n_measurements_to_gate"] - policy["n_measurements_to_gate"]
            ),
            "measurement_count_reduction_pct": (
                (fixed["n_measurements_to_gate"] - policy["n_measurements_to_gate"])
                / fixed["n_measurements_to_gate"] * 100.0
            ),
            "modeled_cost_difference": (
                fixed["modeled_cost_to_gate"] - policy["modeled_cost_to_gate"]
            ),
            "modeled_cost_reduction_pct": (
                (fixed["modeled_cost_to_gate"] - policy["modeled_cost_to_gate"])
                / fixed["modeled_cost_to_gate"] * 100.0
            ),
        }
    digest = lambda label: hashlib.sha256(f"{label}:{seed}".encode()).hexdigest()
    return {
        "provenance": {"seed": seed},
        "data": {
            "common_random_outcomes": True,
            "holdout_count": 23,
            "candidate_count": 30,
            "holdout_manifest_sha256": hashlib.sha256(holdout_payload).hexdigest(),
            "truth_sha256": digest("truth"),
            "outcome_manifest_sha256": digest("outcome"),
        },
        "design": {
            "benchmark_version": 4,
            "estimator_decision_sha256": estimator_hash,
            "primary_endpoints": module.BENCHMARK_V4_PRIMARY_ENDPOINTS,
            "comparator_registry": [
                {"policy": name, "method": module.BENCHMARK_V4_POLICY_METHODS[name],
                 "objective": module.BENCHMARK_V4_POLICY_OBJECTIVES[name],
                 "primary_endpoint": module.BENCHMARK_V4_PRIMARY_ENDPOINTS[name]}
                for name in module.BENCHMARK_V4_POLICY_OBJECTIVES
            ],
            "direct_contrasts": module.BENCHMARK_V4_DIRECT_CONTRASTS,
            "policies": policies,
            "paired_endpoints": endpoints,
        },
        "validity": {
            f"{name}_convergence_valid": True for name in policies
        },
    }


def test_v4_freeze_gate_reconstructs_point_and_paired_evidence(tmp_path: Path):
    module = load_validate_run()
    estimator_hash = "f" * 64
    records = []
    for seed in range(7300, 7330):
        path = tmp_path / f"seed{seed}.json"
        records.append((seed, path, _campaign_record(module, seed, estimator_hash)))
    report = module.validate_v4_campaign(
        records, estimator_decision_sha256=estimator_hash
    )
    assert report["acquisition_record_count"] == 30
    assert report["all_paired_endpoints_reconstructed"] is True

    records[0][2]["design"]["policies"]["eig_raw"]["validation_endpoints"][
        "holdout_latent_mean"
    ]["pcv"]["relative_rmse_pct"] += 1.0
    with pytest.raises(ValueError, match="holdout summary is stale"):
        module.validate_v4_campaign(records, estimator_decision_sha256=estimator_hash)


def test_submit_records_and_enforces_scoped_partition_and_git_archive():
    submit = (ROOT / "scripts" / "submit.sh").read_text(encoding="utf-8")
    common = (ROOT / "slurm" / "common.sh").read_text(encoding="utf-8")
    preflight = (ROOT / "slurm" / "00_preflight.sbatch").read_text(encoding="utf-8")
    assert 'MAGCORE_PARTITION_RESOLVED="${MAGCORE_PARTITION:-nextgen}"' in submit
    assert '--partition="$MAGCORE_PARTITION_RESOLVED"' in submit
    assert "MAGCORE_SUBMIT_PARTITION" in common
    assert 'SLURM_JOB_PARTITION:-}" == "$MAGCORE_SUBMIT_PARTITION"' in preflight
    assert 'git -C "$PROJECT_ROOT" archive' in submit
    assert "tar \\" not in submit
    assert ".venv/bin/python -m pip" not in preflight
