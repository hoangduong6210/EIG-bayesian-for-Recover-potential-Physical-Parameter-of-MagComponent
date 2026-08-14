#!/usr/bin/env python3
"""Audit, freeze, and verify immutable Magnetic Core SLURM evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from magcore_calib.results import validate_result
from magcore_calib.study_plan import load_study_plan


def expected_tasks(config_root: Path) -> dict[str, list[str]]:
    plan = load_study_plan(config_root)
    state_tasks = [
        plan.validation_state_task(index).state_id
        for index in range(plan.validation_state_task_count)
    ]
    grid_tasks = [
        plan.validation_grid_task(index).score_id
        for index in range(plan.validation_grid_task_count)
    ]
    reference_tasks = [
        plan.validation_reference_task(index).score_id
        for index in range(plan.validation_reference_task_count)
    ]
    audit_tasks = [
        plan.validation_audit_task(index).score_id
        for index in range(plan.validation_audit_task_count)
    ]
    return {
    "smoke": ["0"],
    "posterior": [f"seed{seed}" for seed in plan.recovery_seeds],
    "robustness": [
        *(f"prior_offset{level}_seed{seed}" for level in ("0.0", "0.15", "0.30") for seed in plan.recovery_seeds),
        *(f"lot_seed{seed}" for seed in plan.recovery_seeds),
    ],
    "eig": [f"seed{seed}" for seed in plan.acquisition_seeds],
    "identifiability": ["0"],
    "measured_mu": ["N95_LEA_MTB", "N87_LEA_MTB", "N87_MagNet", "3C95_MagNet"],
    "measured_pcv": ["N49", "N87", "N95", "3C95"],
    "measured_eig": ["N95_LEA_MTB", "N87_LEA_MTB"],
    "eig_validation_states": state_tasks,
    "eig_validation_grid": grid_tasks,
    "eig_validation_reference": reference_tasks,
    "eig_validation_audit": audit_tasks,
    "eig_validation_selection": ["decision"],
    "eig_validation_downstream": [
        f"seed{seed}" for seed in plan.downstream_validation_seeds
    ],
    "eig_validation_finalize": ["decision"],
    }


EXPECTED_TASKS = expected_tasks(Path(__file__).resolve().parents[1])
MEASURED_EXCLUSION_POLICY = "retain_diagnostics_but_exclude_invalid_records_from_claims"
CODE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(os.environ.get("MAGCORE_PROJECT_ROOT", CODE_ROOT)).resolve()
RUN_ID_RE = re.compile(r"^\d{8}T\d{6}Z_[0-9a-f]{12}$")
TRANSIENT_TOKENS = (".partial", ".tmp-write", ".tmp")


def is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def require_slurm() -> None:
    if not os.environ.get("SLURM_JOB_ID") or not os.environ.get("SLURM_JOB_NODELIST"):
        raise SystemExit("FATAL: production evidence operations are SLURM-only")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def check_finite(value: Any, path: Path) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"non-finite number in {path}")
    if isinstance(value, dict):
        for child in value.values():
            check_finite(child, path)
    elif isinstance(value, list):
        for child in value:
            check_finite(child, path)


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + f".partial.{os.environ['SLURM_JOB_ID']}")
    partial.write_text(text, encoding="utf-8")
    os.replace(partial, path)


def atomic_json(path: Path, payload: Any) -> None:
    atomic_text(path, json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n")


def validate_scientific_record(path: Path, payload: dict[str, Any]) -> str:
    """Return record class after schema, provenance, and convergence gates."""
    relative = path.as_posix()
    slurm = payload.get("provenance", {}).get("slurm", {})
    if not slurm.get("job_id") or not slurm.get("node_list"):
        raise ValueError(f"missing SLURM job/node provenance in {path}")
    provenance = payload.get("provenance", {})
    expected_revision = os.environ.get("MAGCORE_GIT_REVISION")
    if expected_revision and provenance.get("git_commit") != expected_revision:
        raise ValueError(f"mixed code revision in {path}")
    expected_lock = os.environ.get("MAGCORE_DEPENDENCY_LOCK_SHA256")
    if expected_lock and provenance.get("dependency_lock_sha256") != expected_lock:
        raise ValueError(f"mixed dependency lock in {path}")
    expected_config = os.environ.get("MAGCORE_CONFIG_SHA256")
    if expected_config and provenance.get("configuration_sha256") != expected_config:
        raise ValueError(f"mixed configuration snapshot in {path}")

    if not is_sha256(provenance.get("configuration_sha256")):
        raise ValueError(f"malformed configuration hash in {path}")
    if not is_sha256(provenance.get("dependency_lock_sha256")):
        raise ValueError(f"malformed dependency-lock hash in {path}")

    schema = payload.get("schema_version")
    if isinstance(schema, str) and schema.startswith("eig-convergence-"):
        if payload.get("case_study") != "magnetic_core":
            raise ValueError(
                f"estimator-validation record is outside the Magnetic case study: {path}"
            )
        if payload.get("validity", {}).get("valid") is not True:
            raise ValueError(f"estimator-validation record failed its gate: {path}")
        return schema.removesuffix("/1.0").replace(
            "eig-convergence-", "eig_validation_"
        )

    if "/identifiability/" in relative:
        validate_result(payload)
        spectrum = payload.get("design", {}).get("fisher_spectrum", {})
        if not spectrum.get("eigenvalues_ascending") or len(spectrum.get("parameter_names", [])) != 6:
            raise ValueError(f"invalid six-dimensional identifiability report: {path}")
        return "identifiability_report"

    if "/robustness/lot_seed" in relative:
        validate_result(payload)
        lots = payload.get("design", {}).get("lots", [])
        if len(lots) != 3:
            raise ValueError(f"lot-sensitivity design is incomplete: {path}")
        def target_valid(lot: dict[str, Any]) -> bool:
            diagnostics = lot.get("diagnostics", {})
            acceptance = diagnostics.get("acceptance_fraction")
            ess = diagnostics.get("ess", {}).get("ln_mu_s")
            ratio = diagnostics.get("steps_per_tau", {}).get("ln_mu_s")
            values = (acceptance, ess, ratio)
            return bool(
                all(isinstance(value, (int, float)) and math.isfinite(value) for value in values)
                and 0.20 <= acceptance <= 0.60 and ess >= 400.0 and ratio >= 50.0
            )
        return (
            "synthetic_lot_sensitivity_target_valid"
            if all(target_valid(lot) for lot in lots)
            else "synthetic_lot_sensitivity_excluded"
        )

    # Canonical posterior/measured/EIG records use the project validator.
    validate_result(payload)
    data_hashes = provenance.get("data_sha256", {})
    if payload.get("data", {}).get("kind") == "measured" and not data_hashes:
        raise ValueError(f"measured record has no input-data hashes: {path}")
    if not isinstance(data_hashes, dict) or any(not is_sha256(value) for value in data_hashes.values()):
        raise ValueError(f"malformed input-data hash mapping in {path}")
    validity = payload.get("validity", {})
    convergence = [value for key, value in validity.items() if "convergence_valid" in key]
    if not convergence or not all(value is True for value in convergence):
        kind = payload.get("data", {}).get("kind", "unknown")
        if kind == "measured":
            return "canonical_measured_excluded"
        raise ValueError(f"convergence gate failed: {path}")
    return "canonical_measured" if payload.get("data", {}).get("kind") == "measured" else "canonical_synthetic"


def audit(run_dir: Path) -> dict[str, Any]:
    tasks = expected_tasks(run_dir)
    failures = sorted((run_dir / "status").glob("*.failed"))
    missing = [
        str((Path("status") / f"{stage}_{task}.done"))
        for stage, task_ids in tasks.items()
        for task in task_ids
        if not (run_dir / "status" / f"{stage}_{task}.done").is_file()
    ]
    partials = [
        str(path.relative_to(run_dir)) for root in ("results", "summary")
        for path in (run_dir / root).rglob("*")
        if path.is_file() and any(token in path.name for token in TRANSIENT_TOKENS)
    ]
    if failures or missing or partials:
        details = {
            "failed_markers": [str(path.relative_to(run_dir)) for path in failures],
            "missing_markers": missing,
            "partial_artifacts": partials,
        }
        atomic_json(run_dir / "status" / "audit_failure.json", details)
        raise RuntimeError(json.dumps(details, indent=2))

    artifacts: list[dict[str, Any]] = []
    class_counts: dict[str, int] = {}
    for path in sorted((run_dir / "results").rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(run_dir)
        record_class = "supporting_artifact"
        if path.suffix == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            check_finite(payload, path)
            record_class = validate_scientific_record(path, payload)
        class_counts[record_class] = class_counts.get(record_class, 0) + 1
        artifacts.append({
            "path": str(relative), "sha256": sha256(path),
            "bytes": path.stat().st_size, "record_class": record_class,
        })
    if not artifacts:
        raise RuntimeError("no result artifacts were produced")

    validation_selection = (
        run_dir / "summary" / "eig_convergence" / "static_decision.json"
    )
    validation_final = run_dir / "summary" / "eig_convergence" / "final_decision.json"
    for decision_path, schema in (
        (validation_selection, "eig-convergence-selection/1.0"),
        (validation_final, "eig-convergence-final/1.0"),
    ):
        decision = json.loads(decision_path.read_text(encoding="utf-8"))
        check_finite(decision, decision_path)
        if decision.get("schema_version") != schema or decision.get("valid") is not True:
            raise ValueError(
                f"missing or invalid estimator-validation decision: {decision_path}"
            )

    final_hash = sha256(validation_final)
    plan = load_study_plan(run_dir)
    for seed in plan.acquisition_seeds:
        path = run_dir / "results" / "eig" / f"seed{seed}" / f"eig_seed{seed}.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("provenance", {}).get("seed") != seed:
            raise ValueError(f"acquisition seed/path mismatch: {path}")
        if record.get("design", {}).get("estimator_decision_sha256") != final_hash:
            raise ValueError(
                f"acquisition record is not bound to the estimator decision: {path}"
            )
    run_metadata = {
        "git_revision": os.environ.get("MAGCORE_GIT_REVISION"),
        "source_status_sha256": os.environ.get("MAGCORE_SOURCE_STATUS_SHA256"),
        "source_archive_sha256": os.environ.get("MAGCORE_SOURCE_ARCHIVE_SHA256"),
        "configuration_sha256": os.environ.get("MAGCORE_CONFIG_SHA256"),
        "configuration_mode": os.environ.get("MAGCORE_CONFIG_MODE"),
        "data_manifest_sha256": os.environ.get("MAGCORE_DATA_MANIFEST_SHA256"),
        "dependency_lock_sha256": os.environ.get("MAGCORE_DEPENDENCY_LOCK_SHA256"),
    }
    for key, value in run_metadata.items():
        if key == "configuration_mode":
            if not value:
                raise ValueError("missing configuration mode")
        elif key == "git_revision":
            if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value):
                raise ValueError("missing or malformed git revision")
        elif not is_sha256(value):
            raise ValueError(f"missing or malformed run provenance: {key}")
    return {
        "expected_task_count": sum(map(len, tasks.values())),
        "expected_result_artifact_count": len(artifacts),
        "tasks_without_result_artifacts": [
            "smoke_0",
            "eig_validation_selection_decision",
            "eig_validation_finalize_decision",
        ],
        "study_plan": plan.as_dict(),
        **run_metadata,
        "measured_exclusion_policy": MEASURED_EXCLUSION_POLICY,
        "record_class_counts": class_counts,
        "artifacts": artifacts,
    }


def freeze(run_dir: Path, audit_payload: dict[str, Any]) -> Path:
    run_id = run_dir.name
    if not RUN_ID_RE.fullmatch(run_id):
        raise ValueError(f"invalid immutable release ID: {run_id}")
    frozen_root = PROJECT_ROOT / "results" / "frozen"
    destination = frozen_root / run_id
    staging = frozen_root / f".{run_id}.partial.{os.environ['SLURM_JOB_ID']}"
    if destination.exists() or staging.exists():
        raise FileExistsError(f"immutable release already exists: {destination}")
    staging.mkdir(parents=True)
    try:
        allowed_live_partial = run_dir / "provenance" / "jobs" / "freeze_0.json.partial"
        for root_name in ("results", "summary", "figures", "provenance", "logs", "status"):
            for path in (run_dir / root_name).rglob("*"):
                if path.is_file() and any(token in path.name for token in TRANSIENT_TOKENS):
                    if path != allowed_live_partial:
                        raise RuntimeError(f"transient file cannot enter release: {path}")
        for source_name, target_name in (
            ("results", "metrics"), ("summary", "tables"),
            ("figures", "figures"), ("provenance", "provenance"),
            ("logs", "logs"), ("status", "status"),
        ):
            shutil.copytree(
                run_dir / source_name,
                staging / target_name,
                ignore=shutil.ignore_patterns("*.partial", "*.partial.*", "*.tmp", "*.tmp-write"),
            )
        licenses = CODE_ROOT / "data" / "licenses"
        if licenses.is_dir():
            shutil.copytree(licenses, staging / "licenses")
        atomic_json(staging / "provenance" / "jobs" / "freeze_0.json", {
            "stage": "freeze",
            "task": "0",
            "job_id": os.environ["SLURM_JOB_ID"],
            "node_list": os.environ["SLURM_JOB_NODELIST"],
            "partition": os.environ.get("SLURM_JOB_PARTITION"),
            "git_revision": audit_payload["git_revision"],
            "configuration_sha256": audit_payload["configuration_sha256"],
            "data_manifest_sha256": audit_payload["data_manifest_sha256"],
            "dependency_lock_sha256": audit_payload["dependency_lock_sha256"],
            "ended_at_utc": datetime.now(timezone.utc).isoformat(),
        })
        checksum_targets = sorted(
            path for path in staging.rglob("*")
            if path.is_file() and path.name not in {"manifest.json", "checksums.sha256"}
        )
        checksum_lines = [
            f"{sha256(path)}  {path.relative_to(staging).as_posix()}" for path in checksum_targets
        ]
        atomic_text(staging / "checksums.sha256", "\n".join(checksum_lines) + "\n")
        file_entries = [
            {
                "path": path.relative_to(staging).as_posix(),
                "sha256": sha256(path),
                "bytes": path.stat().st_size,
            }
            for path in sorted(path for path in staging.rglob("*") if path.is_file())
            if path.name != "manifest.json"
        ]
        manifest = {
            "schema_version": "magnetic-release/1.0",
            "release_id": run_id,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_run": str(run_dir),
            "git_revision": os.environ.get("MAGCORE_GIT_REVISION"),
            "source_status_sha256": os.environ.get("MAGCORE_SOURCE_STATUS_SHA256"),
            "source_archive_sha256": os.environ.get("MAGCORE_SOURCE_ARCHIVE_SHA256"),
            "configuration_sha256": os.environ.get("MAGCORE_CONFIG_SHA256"),
            "configuration_mode": os.environ.get("MAGCORE_CONFIG_MODE"),
            "data_manifest_sha256": os.environ.get("MAGCORE_DATA_MANIFEST_SHA256"),
            "dependency_lock_sha256": os.environ.get("MAGCORE_DEPENDENCY_LOCK_SHA256"),
            "slurm": {
                "job_id": os.environ["SLURM_JOB_ID"],
                "node_list": os.environ["SLURM_JOB_NODELIST"],
                "partition": os.environ.get("SLURM_JOB_PARTITION"),
            },
            "audit": audit_payload,
            "files": file_entries,
        }
        atomic_json(staging / "manifest.json", manifest)
        transient_release_paths = [
            path for path in staging.rglob("*")
            if path.is_file() and any(token in path.name for token in TRANSIENT_TOKENS)
        ]
        if transient_release_paths:
            raise RuntimeError(f"release still contains transient files: {transient_release_paths}")
        for path in (p for p in staging.rglob("*") if p.is_file()):
            path.chmod(0o440)
        for path in sorted((p for p in staging.rglob("*") if p.is_dir()), reverse=True):
            path.chmod(0o550)
        staging.chmod(0o550)
        os.replace(staging, destination)
    except BaseException:
        if staging.exists():
            for path in staging.rglob("*"):
                try:
                    path.chmod(0o700 if path.is_dir() else 0o600)
                except OSError:
                    pass
            staging.chmod(0o700)
            shutil.rmtree(staging)
        raise

    manifest_hash = sha256(destination / "manifest.json")
    atomic_text(PROJECT_ROOT / "results" / "CURRENT", run_id + "\n")
    lock = (
        "schema_version: 1\nstatus: FROZEN\n"
        f"release_id: {run_id}\nmanifest_sha256: {manifest_hash}\n"
        f"locked_at_utc: {datetime.now(timezone.utc).isoformat()}\n"
        "notes:\n  - Generated atomically by the SLURM freeze gate.\n"
    )
    atomic_text(PROJECT_ROOT / "paper" / "current_state" / "results.lock.yaml", lock)
    atomic_json(run_dir / "freeze" / "release.json", {
        "release_id": run_id, "release_dir": str(destination),
        "manifest_sha256": manifest_hash,
    })
    return destination


def read_lock(expected_release_id: str | None = None) -> tuple[Path, str, str]:
    values: dict[str, str] = {}
    lock_path = PROJECT_ROOT / "paper" / "current_state" / "results.lock.yaml"
    for line in lock_path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith((" ", "-")):
            continue
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            if key in values:
                raise RuntimeError(f"duplicate paper-lock key: {key}")
            values[key] = value.strip()
        else:
            raise RuntimeError("malformed paper result lock")
    if values.get("status") != "FROZEN" or not values.get("release_id"):
        raise RuntimeError("paper result lock is not frozen")
    if values.get("schema_version") != "1" or not RUN_ID_RE.fullmatch(values["release_id"]):
        raise RuntimeError("paper result lock has invalid schema or release ID")
    if expected_release_id is not None and values["release_id"] != expected_release_id:
        raise RuntimeError(
            f"paper lock points to {values['release_id']}, expected {expected_release_id}"
        )
    frozen_root = (PROJECT_ROOT / "results" / "frozen").resolve()
    release = (frozen_root / values["release_id"]).resolve()
    if release.parent != frozen_root:
        raise RuntimeError("paper lock release escapes frozen root")
    expected = values.get("manifest_sha256", "")
    if not is_sha256(expected) or not release.is_dir() or sha256(release / "manifest.json") != expected:
        raise RuntimeError("paper lock release/manifest mismatch")
    manifest = json.loads((release / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "magnetic-release/1.0" or manifest.get("release_id") != values["release_id"]:
        raise RuntimeError("release manifest identity mismatch")
    declared: dict[str, str] = {}
    for entry in manifest.get("files", []):
        relative = entry.get("path")
        digest = entry.get("sha256")
        pure = PurePosixPath(relative) if isinstance(relative, str) else None
        if (
            pure is None or pure.is_absolute() or not pure.parts or "." in pure.parts
            or ".." in pure.parts or "\\" in relative or relative in declared
            or not is_sha256(digest)
        ):
            raise RuntimeError(f"unsafe or duplicate release-manifest path: {relative}")
        target = release.joinpath(*pure.parts)
        if target.is_symlink() or not target.is_file() or sha256(target) != digest:
            raise RuntimeError(f"frozen file mismatch: {relative}")
        if entry.get("bytes") != target.stat().st_size:
            raise RuntimeError(f"frozen file size mismatch: {relative}")
        declared[relative] = digest
    actual = {
        path.relative_to(release).as_posix()
        for path in release.rglob("*") if path.is_file() and path.name != "manifest.json"
    }
    if actual != set(declared):
        raise RuntimeError("release contains missing or undeclared files")
    return release, values["release_id"], expected


def publish_frozen_figures(run_dir: Path) -> None:
    release, release_id, manifest_hash = read_lock(run_dir.name)
    copied = []
    figure_targets = [
        run_dir / "figures",
        CODE_ROOT / "figures" / "generated",
        PROJECT_ROOT / "figures" / "generated",
        CODE_ROOT / "paper" / "current_state" / "source" / "figures",
        PROJECT_ROOT / "paper" / "current_state" / "source" / "figures",
    ]
    for source in sorted((release / "figures").glob("*.pdf")):
        for target_dir in figure_targets:
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / source.name
            partial = target.with_name(target.name + ".partial")
            partial.write_bytes(source.read_bytes())
            os.replace(partial, target)
        copied.append({"path": f"figures/{source.name}", "sha256": sha256(source)})
    table_sources = [
        release / "tables" / "frozen_result_macros.tex",
        release / "tables" / "frozen_results.tex",
    ]
    if not all(source.is_file() for source in table_sources) or not copied:
        raise RuntimeError("locked release has no generated paper macros, table, or figures")
    table_targets = (
        CODE_ROOT / "paper" / "current_state" / "source" / "tables",
        PROJECT_ROOT / "paper" / "current_state" / "source" / "tables",
    )
    for target_dir in dict.fromkeys(table_targets):
        target_dir.mkdir(parents=True, exist_ok=True)
        for source in table_sources:
            target = target_dir / source.name
            partial = target.with_name(target.name + ".partial")
            partial.write_bytes(source.read_bytes())
            os.replace(partial, target)
    atomic_json(run_dir / "figures" / "manifest.json", {
        "freeze_id": release_id,
        "release_manifest_sha256": manifest_hash,
        "figures": copied,
        "tables": [
            {"path": f"tables/{source.name}", "sha256": sha256(source)}
            for source in table_sources
        ],
    })


def main() -> None:
    require_slurm()
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--mode", choices=("audit", "aggregate", "freeze", "figures", "verify-lock"), required=True,
    )
    args = parser.parse_args()
    run_dir = args.run_dir.resolve(strict=True)
    if args.mode == "verify-lock":
        read_lock(run_dir.name)
        return
    if args.mode == "figures":
        publish_frozen_figures(run_dir)
        return

    audit_payload = audit(run_dir)
    if args.mode == "audit":
        atomic_json(run_dir / "status" / "audit.json", audit_payload)
    elif args.mode == "aggregate":
        atomic_json(run_dir / "summary" / "result_manifest.json", audit_payload)
    else:
        source = run_dir / "summary" / "result_manifest.json"
        if not source.is_file() or json.loads(source.read_text()) != audit_payload:
            raise RuntimeError("aggregate manifest is missing or stale")
        freeze(run_dir, audit_payload)


if __name__ == "__main__":
    main()
