#!/usr/bin/env python3
"""Export and verify the disclosure-safe SparseMix-1 diagnostic bundle.

The production run contains scheduler and machine provenance that is not part
of the scientific record.  This exporter copies only the validated diagnostic
manifest, task records, and deterministic thinned chains.  Files are copied
without transformation so every public digest remains directly comparable
with the validator manifest produced by the immutable run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
from pathlib import Path, PurePosixPath
from typing import Any

import numpy as np


BUNDLE_SCHEMA = "magnetic-sparse-mixing-audit/1.0"
SOURCE_MANIFEST_SCHEMA = "magcore-sparse-mixing-manifest/1.0"
RESULT_SCHEMA = "magcore-sparse-mixing-result/1.0"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
RUN_ID_RE = re.compile(r"^\d{8}T\d{6}Z_[0-9a-f]{12}$")
FORBIDDEN_TEXT = re.compile(
    r"/(?:users|home|tmp)/|[A-Za-z]:[/\\]Users[/\\]|PGS0407|binben14|"
    r"ghp_[A-Za-z0-9]+|github_pat_[A-Za-z0-9_]+|"
    r"(?:Bearer|Authorization:)\s+[A-Za-z0-9._-]+|"
    r"(?:API|SECRET)[_-]?KEY|PRIVATE KEY|private key|"
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|"
    r"SLURM_|node_list|job_id|array_job_id|\.environment\.txt|run\.env",
)


def sha256_file(path: Path) -> str:
    """Return the lowercase SHA-256 digest of a file."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"), parse_constant=(
        lambda token: (_ for _ in ()).throw(ValueError(
            f"nonfinite JSON value {token!r} in {path}"
        ))
    ))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _safe_path(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or "\\" in relative:
        raise ValueError("bundle paths must be relative POSIX paths")
    pure = PurePosixPath(relative)
    if pure.is_absolute() or relative in ("", ".") or ".." in pure.parts:
        raise ValueError(f"unsafe bundle path: {relative!r}")
    resolved = (root / Path(*pure.parts)).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError(f"bundle path escapes root: {relative!r}")
    return resolved


def _assert_sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise ValueError(f"invalid SHA-256 for {label}")
    return value


def _assert_finite(value: Any, label: str = "root") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            _assert_finite(child, f"{label}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_finite(child, f"{label}[{index}]")
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"nonfinite number at {label}")


def _read_run_identity(source_run: Path) -> tuple[str, str, str, str]:
    run_id = source_run.name
    if not RUN_ID_RE.fullmatch(run_id):
        raise ValueError(f"invalid immutable run identity: {run_id!r}")
    values: dict[str, str] = {}
    for line in (source_run / "provenance/run.env").read_text(
        encoding="utf-8"
    ).splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value.strip("'")
    if values.get("MAGCORE_RUN_ID") != run_id:
        raise ValueError("run identity differs from immutable provenance")
    revision = values.get("MAGCORE_GIT_REVISION", "")
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("invalid implementation source revision")
    source_archive = _assert_sha(
        values.get("MAGCORE_SOURCE_ARCHIVE_SHA256"), "source archive"
    )
    source_status = _assert_sha(
        values.get("MAGCORE_SOURCE_STATUS_SHA256"), "source status"
    )
    if source_status != hashlib.sha256(b"").hexdigest():
        raise ValueError("SparseMix source worktree was not clean")
    return run_id, revision, source_archive, source_status


def _validate_source_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("schema_version") != SOURCE_MANIFEST_SCHEMA:
        raise ValueError("unsupported SparseMix source manifest schema")
    if manifest.get("protocol_id") != "SparseMix-1":
        raise ValueError("unexpected SparseMix protocol")
    matrix = manifest.get("matrix", {})
    if matrix != {
        "artifact_count": 36,
        "expected_task_count": 18,
        "validated_task_count": 18,
    }:
        raise ValueError("SparseMix source matrix is not complete")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 18:
        raise ValueError("SparseMix source artifact registry is incomplete")
    task_ids = [entry.get("task_id") for entry in artifacts]
    if len(set(task_ids)) != 18:
        raise ValueError("SparseMix source task identities are not unique")
    disclosure = manifest.get("disclosure", {})
    if disclosure != {
        "claim_bearing_result": False,
        "mm2_admission_changed": False,
        "scientific_endpoints_included": False,
    }:
        raise ValueError("SparseMix disclosure boundary differs from protocol")
    _assert_finite(manifest)


def _validate_record(record: dict[str, Any], entry: dict[str, Any]) -> None:
    if record.get("schema_version") != RESULT_SCHEMA:
        raise ValueError("unsupported SparseMix task-record schema")
    if record.get("record_class") != "endpoint_free_sampler_diagnostic":
        raise ValueError("unexpected SparseMix task-record class")
    if record.get("protocol_id") != "SparseMix-1":
        raise ValueError("unexpected SparseMix task protocol")
    if record.get("task", {}).get("task_id") != entry["task_id"]:
        raise ValueError("SparseMix task identity mismatch")
    if record.get("disclosure") != {
        "claim_bearing_result": False,
        "retroactive_mm2_admission_allowed": False,
        "scientific_endpoints_included": False,
    }:
        raise ValueError("SparseMix task disclosure boundary differs")
    if record.get("thin", {}).get("sha256") != entry["thin_sha256"]:
        raise ValueError("SparseMix task thin digest differs from source manifest")
    _assert_finite(record)


def export_bundle(source_run: Path, destination: Path) -> dict[str, Any]:
    """Copy the exact validated SparseMix public record into a new directory."""

    source_run = source_run.resolve()
    if destination.exists():
        raise FileExistsError(f"destination already exists: {destination}")
    run_id, revision, source_archive, source_status = _read_run_identity(source_run)
    source_manifest_path = source_run / "summary/sparse_mixing/manifest.json"
    source_manifest = _load_json(source_manifest_path)
    _validate_source_manifest(source_manifest)
    source_results = source_run / "results/sparse_mixing"
    destination.mkdir(parents=True)
    copied: list[dict[str, Any]] = []
    exact_replay_count = 0
    try:
        public_source_manifest = destination / "source_manifest.json"
        shutil.copyfile(source_manifest_path, public_source_manifest)
        copied.append({
            "path": "source_manifest.json",
            "record_class": "validator_manifest",
            "sha256": sha256_file(public_source_manifest),
            "bytes": public_source_manifest.stat().st_size,
        })
        for entry in sorted(source_manifest["artifacts"], key=lambda row: row["task_id"]):
            task_id = entry["task_id"]
            result_source = _safe_path(source_results, entry["result_path"])
            thin_source = _safe_path(source_results, entry["thin_path"])
            if sha256_file(result_source) != _assert_sha(
                entry["result_sha256"], f"{task_id} result"
            ):
                raise ValueError(f"source result digest mismatch: {task_id}")
            if sha256_file(thin_source) != _assert_sha(
                entry["thin_sha256"], f"{task_id} thin"
            ):
                raise ValueError(f"source thin digest mismatch: {task_id}")
            record = _load_json(result_source)
            _validate_record(record, entry)
            exact_replay_count += int(record["task"].get("exact_replay") is True)
            with np.load(thin_source, allow_pickle=False) as archive:
                if set(archive.files) != {"chain"}:
                    raise ValueError(f"unexpected thin archive members: {task_id}")
                chain = archive["chain"]
                if chain.dtype != np.float64 or list(chain.shape) != record["thin"]["shape"]:
                    raise ValueError(f"thin archive contract mismatch: {task_id}")

            result_relative = f"records/{task_id}/result.json"
            thin_relative = f"records/{task_id}/thin.npz"
            result_public = _safe_path(destination, result_relative)
            thin_public = _safe_path(destination, thin_relative)
            result_public.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(result_source, result_public)
            shutil.copyfile(thin_source, thin_public)
            for relative, path, record_class in (
                (result_relative, result_public, "sampler_diagnostic"),
                (thin_relative, thin_public, "deterministic_thinned_chain"),
            ):
                copied.append({
                    "path": relative,
                    "record_class": record_class,
                    "sha256": sha256_file(path),
                    "bytes": path.stat().st_size,
                })

        bundle_manifest = {
            "schema_version": BUNDLE_SCHEMA,
            "protocol_id": source_manifest["protocol_id"],
            "run_id": run_id,
            "implementation": {
                "source_revision": revision,
                "source_archive_sha256": source_archive,
                "source_status_sha256": source_status,
            },
            "source_manifest_sha256": sha256_file(source_manifest_path),
            "config_sha256": source_manifest["config_sha256"],
            "parent": source_manifest["parent"],
            "matrix": source_manifest["matrix"],
            "classifications": source_manifest["classifications"],
            "validation": {
                "exact_replay_task_count": exact_replay_count,
                "exact_replay_match_required_by_source_validator": True,
                "full_chain_diagnostics_recomputable_from_bundle": False,
            },
            "scope": {
                "contains_deterministic_thinned_chains": True,
                "contains_full_walker_iteration_chains": False,
                "contains_scientific_endpoints": False,
                "changes_mm2_admission": False,
            },
            "files": copied,
        }
        _write_json(destination / "bundle.json", bundle_manifest)
        verify_bundle(destination)
        return bundle_manifest
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise


def verify_bundle(bundle: Path) -> dict[str, Any]:
    """Fail closed unless the bundle is complete, exact, and disclosure-safe."""

    bundle = bundle.resolve()
    manifest = _load_json(bundle / "bundle.json")
    if manifest.get("schema_version") != BUNDLE_SCHEMA:
        raise ValueError("unsupported SparseMix public-bundle schema")
    if not RUN_ID_RE.fullmatch(str(manifest.get("run_id", ""))):
        raise ValueError("invalid SparseMix bundle run identity")
    files = manifest.get("files")
    if not isinstance(files, list) or len(files) != 37:
        raise ValueError("SparseMix bundle must declare 37 payload files")
    declared = {entry.get("path") for entry in files}
    if len(declared) != 37 or None in declared:
        raise ValueError("SparseMix bundle has duplicate or missing paths")
    actual = {
        path.relative_to(bundle).as_posix()
        for path in bundle.rglob("*")
        if path.is_file() and not path.is_symlink()
    }
    if actual != declared | {"bundle.json"}:
        raise ValueError("SparseMix bundle contains undeclared or missing files")
    if any(path.is_symlink() for path in bundle.rglob("*")):
        raise ValueError("SparseMix bundle must not contain symbolic links")
    entries = {entry["path"]: entry for entry in files}
    for relative, entry in entries.items():
        path = _safe_path(bundle, relative)
        if sha256_file(path) != _assert_sha(entry.get("sha256"), relative):
            raise ValueError(f"checksum mismatch: {relative}")
        if path.stat().st_size != entry.get("bytes"):
            raise ValueError(f"byte-count mismatch: {relative}")

    source_manifest = _load_json(bundle / "source_manifest.json")
    _validate_source_manifest(source_manifest)
    if sha256_file(bundle / "source_manifest.json") != _assert_sha(
        manifest.get("source_manifest_sha256"), "source manifest"
    ):
        raise ValueError("source manifest binding differs")
    expected_artifacts = {
        entry["task_id"]: entry for entry in source_manifest["artifacts"]
    }
    exact_replay_count = 0
    for task_id, source_entry in expected_artifacts.items():
        result_path = bundle / f"records/{task_id}/result.json"
        thin_path = bundle / f"records/{task_id}/thin.npz"
        record = _load_json(result_path)
        _validate_record(record, source_entry)
        exact_replay_count += int(record["task"].get("exact_replay") is True)
        if sha256_file(result_path) != source_entry["result_sha256"]:
            raise ValueError(f"public result differs from source: {task_id}")
        if sha256_file(thin_path) != source_entry["thin_sha256"]:
            raise ValueError(f"public thin differs from source: {task_id}")
        with np.load(thin_path, allow_pickle=False) as archive:
            if set(archive.files) != {"chain"}:
                raise ValueError(f"unexpected thin archive members: {task_id}")
            chain = archive["chain"]
            if chain.dtype != np.float64 or list(chain.shape) != record["thin"]["shape"]:
                raise ValueError(f"thin archive contract mismatch: {task_id}")

    if manifest.get("classifications") != source_manifest["classifications"]:
        raise ValueError("public classifications differ from source manifest")
    if manifest.get("matrix") != source_manifest["matrix"]:
        raise ValueError("public matrix differs from source manifest")
    if manifest.get("validation") != {
        "exact_replay_match_required_by_source_validator": True,
        "exact_replay_task_count": 2,
        "full_chain_diagnostics_recomputable_from_bundle": False,
    } or exact_replay_count != 2:
        raise ValueError("SparseMix validation declaration differs from records")
    if manifest.get("scope") != {
        "changes_mm2_admission": False,
        "contains_deterministic_thinned_chains": True,
        "contains_full_walker_iteration_chains": False,
        "contains_scientific_endpoints": False,
    }:
        raise ValueError("SparseMix public scope differs from protocol")
    for path in (bundle / "bundle.json", bundle / "source_manifest.json", *(
        bundle / f"records/{task_id}/result.json" for task_id in expected_artifacts
    )):
        if FORBIDDEN_TEXT.search(path.read_text(encoding="utf-8")):
            raise ValueError(f"machine or credential material in {path.name}")
    return {
        "valid": True,
        "run_id": manifest["run_id"],
        "payload_file_count": len(files),
        "task_count": len(expected_artifacts),
        "classifications": manifest["classifications"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    export_parser = subparsers.add_parser("export")
    export_parser.add_argument("--source-run", required=True, type=Path)
    export_parser.add_argument("--destination", required=True, type=Path)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--bundle", required=True, type=Path)
    args = parser.parse_args()
    report = (
        export_bundle(args.source_run, args.destination)
        if args.command == "export"
        else verify_bundle(args.bundle)
    )
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
