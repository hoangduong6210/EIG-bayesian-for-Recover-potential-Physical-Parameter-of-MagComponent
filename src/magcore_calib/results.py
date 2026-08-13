"""Canonical immutable result records and provenance."""

from __future__ import annotations

import json
import hashlib
import math
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from .runtime import slurm_metadata

SCHEMA_VERSION = "magnetic-calibration/1.0"
REQUIRED_SECTIONS = {
    "schema_version", "case_study", "run_id", "provenance", "data", "model",
    "sampler", "posterior", "predictive", "design", "claim_context", "validity",
}
PARAMETERS = {"k", "alpha", "beta", "mu_s", "f_rel_hz", "alpha_cc"}
_HEX_DIGITS = frozenset("0123456789abcdef")


def _is_sha256(value: object) -> bool:
    """Return whether *value* is a lowercase hexadecimal SHA-256 digest."""
    return (
        isinstance(value, str)
        and len(value) == 64
        and set(value) <= _HEX_DIGITS
    )


def git_commit(cwd: str | None = None) -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=cwd, check=True,
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def provenance(*, seed: int, command: list[str] | None = None,
               cwd: str | None = None, data_paths: list[str | Path] | None = None) -> dict:
    command = command or sys.argv
    project_root = Path(__file__).resolve().parents[2]
    lock = project_root / "configs" / "dependencies.lock"
    command_hash = hashlib.sha256(
        json.dumps(command, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()
    configuration_hash = os.environ.get("MAGCORE_CONFIG_SHA256", command_hash)
    dependency_hash = sha256_file(lock)
    expected_dependency_hash = os.environ.get("MAGCORE_DEPENDENCY_LOCK_SHA256")
    if expected_dependency_hash and dependency_hash != expected_dependency_hash:
        raise RuntimeError("dependency lock differs from the submitted run snapshot")
    data_hashes = {str(path): sha256_file(path) for path in (data_paths or [])}
    if not data_hashes:
        # Synthetic studies have no external observation file. Bind their
        # generated observations to the declared seed and exact command so the
        # canonical schema still has a non-empty, reproducible data digest.
        synthetic_recipe = json.dumps(
            {"seed": seed, "command": command},
            sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        ).encode("utf-8")
        data_hashes["synthetic://seed-and-command"] = hashlib.sha256(
            synthetic_recipe
        ).hexdigest()
    return {
        "started_at_utc": os.environ.get("STARTED_AT"),
        "ended_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": os.environ.get("MAGCORE_GIT_REVISION") or git_commit(cwd),
        "seed": seed,
        "command": command,
        "command_sha256": command_hash,
        "configuration_sha256": configuration_hash,
        "data_sha256": data_hashes,
        "dependency_lock_sha256": dependency_hash,
        "python": platform.python_version(),
        "slurm": slurm_metadata(),
    }


def validate_result(record: dict) -> None:
    missing = REQUIRED_SECTIONS - record.keys()
    if missing:
        raise ValueError(f"result missing sections: {sorted(missing)}")
    if record["schema_version"] != SCHEMA_VERSION or record["case_study"] != "magnetic_core":
        raise ValueError("wrong result schema or case study")
    posterior = record["posterior"]
    if set(posterior) != PARAMETERS:
        raise ValueError("posterior must report exactly six canonical magnetic parameters")
    claims = record["claim_context"]
    if claims.get("oracle_initialized") is not False:
        raise ValueError("canonical results must explicitly certify non-oracle initialization")
    design = record["design"]
    if design.get("benchmark_version") in (2, 3):
        policies = design.get("policies", {})
        required_policies = {"eig_raw", "eig_per_cost", "fixed_channel_balanced"}
        if set(policies) != required_policies:
            raise ValueError("benchmark v2 must contain raw EIG, EIG/cost, and fixed policies")
        endpoints = design.get("paired_endpoints", {})
        if set(endpoints) != {"eig_raw_vs_fixed", "eig_per_cost_vs_fixed"}:
            raise ValueError("benchmark v2 must report paired count and modeled-cost endpoints")
        if not isinstance(design.get("eig_estimator_replicates"), int) \
                or design["eig_estimator_replicates"] < 2:
            raise ValueError("benchmark v2 requires repeated EIG estimates")
        expected_replicates = design["eig_estimator_replicates"]
        for policy_name in ("eig_raw", "eig_per_cost"):
            for row in policies[policy_name].get("trajectory", []):
                acquisition = row.get("acquisition")
                if not acquisition:
                    continue
                candidate_scores = acquisition.get("candidate_scores", [])
                if not candidate_scores:
                    raise ValueError("benchmark v2 EIG decisions require candidate uncertainty")
                required_score_fields = {
                    "eig_mean_nats", "eig_sd_nats", "eig_se_nats", "eig_ci95_nats",
                    "top_selection_rate", "replicate_scores_nats",
                }
                if any(required_score_fields - score.keys() for score in candidate_scores):
                    raise ValueError("benchmark v2 candidate score is incomplete")
                for score in candidate_scores:
                    replicates = score["replicate_scores_nats"]
                    interval = score["eig_ci95_nats"]
                    scalar_values = (
                        score["eig_mean_nats"], score["eig_sd_nats"],
                        score["eig_se_nats"], score["top_selection_rate"],
                    )
                    if not isinstance(replicates, list) or len(replicates) != expected_replicates:
                        raise ValueError("benchmark v2 candidate replicate count is inconsistent")
                    if not isinstance(interval, list) or len(interval) != 2:
                        raise ValueError("benchmark v2 candidate interval is malformed")
                    if not all(math.isfinite(float(value)) for value in (*scalar_values, *interval, *replicates)):
                        raise ValueError("benchmark v2 candidate uncertainty must be finite")
                    if score["eig_sd_nats"] < 0.0 or score["eig_se_nats"] < 0.0:
                        raise ValueError("benchmark v2 candidate uncertainty cannot be negative")
                    if not 0.0 <= score["top_selection_rate"] <= 1.0:
                        raise ValueError("benchmark v2 top-selection rate must be in [0, 1]")
        if design.get("benchmark_version") == 3:
            setting = design.get("eig_estimator_setting", {})
            if set(setting) != {"n_outer", "n_inner", "n_replicates"} or any(
                not isinstance(value, int) or value < 1 for value in setting.values()
            ):
                raise ValueError(
                    "benchmark v3 requires the validated estimator setting"
                )
            if setting["n_replicates"] != expected_replicates:
                raise ValueError("benchmark v3 setting/replicate mismatch")
            if not _is_sha256(design.get("estimator_decision_sha256")):
                raise ValueError("benchmark v3 requires an estimator-decision hash")
            for name in ("truth_sha256", "outcome_manifest_sha256"):
                if not _is_sha256(record.get("data", {}).get(name)):
                    raise ValueError(f"benchmark v3 requires {name}")
    provenance_record = record["provenance"]
    required_provenance = {
        "started_at_utc", "ended_at_utc", "git_commit", "seed", "command",
        "configuration_sha256", "data_sha256", "dependency_lock_sha256", "python", "slurm",
    }
    if required_provenance - provenance_record.keys():
        raise ValueError("canonical result has incomplete provenance")
    if not _is_sha256(provenance_record.get("configuration_sha256")):
        raise ValueError("canonical result has an invalid configuration hash")
    if not _is_sha256(provenance_record.get("dependency_lock_sha256")):
        raise ValueError("canonical result has an invalid dependency-lock hash")
    data_hashes = provenance_record.get("data_sha256")
    if not isinstance(data_hashes, dict):
        raise ValueError("canonical result data hashes must be a mapping")
    if not data_hashes:
        raise ValueError("canonical result is missing data hashes")
    if any(not _is_sha256(digest) for digest in data_hashes.values()):
        raise ValueError("canonical result contains an invalid data hash")
    slurm = provenance_record.get("slurm", {})
    required_slurm = {"job_id", "array_job_id", "array_task_id", "node_list", "partition"}
    if required_slurm - slurm.keys() or not slurm.get("job_id") or not slurm.get("node_list"):
        raise ValueError("heavy canonical results require SLURM provenance")


def write_immutable(record: dict, artifacts_root: str | Path) -> Path:
    validate_result(record)
    destination = Path(artifacts_root) / str(record["run_id"]) / "result.json"
    destination.parent.mkdir(parents=True, exist_ok=False)
    temporary = destination.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, destination)
    return destination


def write_result(record: dict, output: str | Path) -> Path:
    """Write a validated result to a run-managed path using atomic replacement."""
    validate_result(record)
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp-write")
    temporary.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, destination)
    return destination
