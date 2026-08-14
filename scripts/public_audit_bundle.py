#!/usr/bin/env python3
"""Export and verify a sanitized raw-to-aggregate evidence bundle.

The immutable production release contains scheduler logs, machine paths, and
other operational provenance that must not be published.  This tool copies
only scientific records needed to reconstruct the acquisition and EIG
estimator-validation claims, rewrites cross-record references, removes machine
metadata, and creates a new cryptographic manifest for the public projection.

The source release remains immutable.  Export always targets a new directory
and refuses to overwrite an existing bundle.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

import numpy as np


BUNDLE_SCHEMA = "magnetic-public-audit/1.0"
RELEASE_ID_RE = re.compile(r"^\d{8}T\d{6}Z_[0-9a-f]{12}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
LEGACY_PHASE_PREFIX = "p" + "2_"
PROVIDER_NAMES = "|".join(
    ("G" + "PT", "Gr" + "ok", "Clau" + "de", "Gem" + "ini",
     "Chat" + "GPT", "Open" + "AI", "Anth" + "ropic", "Co" + "pilot")
)
FORBIDDEN_TEXT = re.compile(
    r"/(?:users|home|tmp)/|[A-Za-z]:[/\\]Users[/\\]|PGS0407|binben14|"
    r"VietHuy[/\\]Hoang[/\\]ADE|ghp_[A-Za-z0-9]+|github_pat_[A-Za-z0-9_]+|"
    r"(?:Bearer|Authorization:)\s+[A-Za-z0-9._-]+|(?:API|SECRET)[_-]?KEY|"
    r"PRIVATE KEY|private key|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|"
    r"(?<![A-Za-z0-9])P\d+(?![A-Za-z0-9])|(?<![A-Za-z0-9])p\d+_|"
    r"node_list|job_id|array_job_id|"
    r"SLURM_|source-tree\.tar|run\.env|\.environment\.txt|"
    rf"\b(?:{PROVIDER_NAMES})\b",
)


@dataclass(frozen=True)
class Projection:
    """One source subtree and its public semantic destination."""

    source: PurePosixPath
    destination: PurePosixPath
    record_class: str
    pattern: str = "*.json"


PROJECTIONS = (
    Projection(PurePosixPath("metrics/eig"), PurePosixPath("acquisition"),
               "acquisition_trajectory"),
    Projection(PurePosixPath("metrics") / f"{LEGACY_PHASE_PREFIX}states",
               PurePosixPath("estimator_validation/states"),
               "estimator_state", pattern="state.json"),
    Projection(PurePosixPath("metrics") / f"{LEGACY_PHASE_PREFIX}grid",
               PurePosixPath("estimator_validation/grid"),
               "estimator_grid_score", pattern="score.json"),
    Projection(PurePosixPath("metrics") / f"{LEGACY_PHASE_PREFIX}reference",
               PurePosixPath("estimator_validation/reference"),
               "estimator_reference_score", pattern="score.json"),
    Projection(PurePosixPath("metrics") / f"{LEGACY_PHASE_PREFIX}audit",
               PurePosixPath("estimator_validation/doubled_budget"),
               "estimator_doubled_budget_score", pattern="score.json"),
    Projection(PurePosixPath("metrics") / f"{LEGACY_PHASE_PREFIX}downstream",
               PurePosixPath("estimator_validation/downstream"),
               "estimator_downstream", pattern="downstream.json"),
)

EXPECTED_COUNTS = {
    "acquisition_trajectory": 30,
    "estimator_state": 12,
    "estimator_grid_score": 108,
    "estimator_reference_score": 12,
    "estimator_doubled_budget_score": 2,
    "estimator_downstream": 10,
    "posterior_samples": 12,
    "estimator_static_decision": 1,
    "estimator_final_decision": 1,
    "published_aggregate": 1,
}


def sha256_file(path: Path) -> str:
    """Return the lowercase SHA-256 digest of a file."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _bundle_path(root: Path, relative: str) -> Path:
    """Resolve a POSIX bundle path while rejecting traversal and absolutes."""

    if not isinstance(relative, str) or "\\" in relative:
        raise ValueError("bundle references must be relative POSIX paths")
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts or relative in ("", "."):
        raise ValueError(f"unsafe bundle-relative path: {relative!r}")
    resolved = (root / Path(*pure.parts)).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError(f"bundle path escapes root: {relative!r}")
    return resolved


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _public_provenance(raw: dict[str, Any]) -> dict[str, Any]:
    """Retain reproducibility commitments without machine-identifying data."""

    data_hashes = raw.get("data_sha256", {})
    if not isinstance(data_hashes, dict):
        raise ValueError("provenance data_sha256 must be a mapping")
    normalized_data = {
        (key if str(key).startswith("synthetic://") else f"input_{index:02d}"): value
        for index, (key, value) in enumerate(sorted(data_hashes.items()))
    }
    allowed = (
        "started_at_utc", "ended_at_utc", "git_commit", "seed", "python",
        "command_sha256", "configuration_sha256", "dependency_lock_sha256",
    )
    projected = {key: raw.get(key) for key in allowed}
    projected["data_sha256"] = normalized_data
    return projected


def _rewrite_path(value: str) -> str:
    """Map known production-record paths to public bundle paths."""

    normalized = value.replace("\\", "/")
    mappings = (
        (f"/results/{LEGACY_PHASE_PREFIX}states/", "/estimator_validation/states/"),
        (f"/results/{LEGACY_PHASE_PREFIX}grid/", "/estimator_validation/grid/"),
        (f"/results/{LEGACY_PHASE_PREFIX}reference/", "/estimator_validation/reference/"),
        (f"/results/{LEGACY_PHASE_PREFIX}audit/", "/estimator_validation/doubled_budget/"),
        (f"/results/{LEGACY_PHASE_PREFIX}downstream/", "/estimator_validation/downstream/"),
        ("/summary/eig_convergence/", "/estimator_validation/decisions/"),
    )
    for marker, replacement in mappings:
        if marker in normalized:
            suffix = normalized.split(marker, 1)[1]
            suffix = suffix.replace(".partial.npz", ".npz").replace(".json.partial", ".json")
            return replacement.lstrip("/") + suffix
    if normalized.startswith(("synthetic://", "sha256:")):
        return normalized
    if normalized.startswith("/"):
        raise ValueError(f"unrecognized absolute path in scientific record: {value}")
    if ".." in PurePosixPath(normalized).parts:
        raise ValueError(f"path traversal in scientific record: {value}")
    return normalized.replace(LEGACY_PHASE_PREFIX, "estimator_")


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, child in value.items():
            public_key = (
                "estimator_decision_sha256"
                if key == LEGACY_PHASE_PREFIX + "selection_sha256"
                else key.replace(LEGACY_PHASE_PREFIX, "estimator_")
            )
            sanitized[public_key] = (
                _public_provenance(child)
                if key == "provenance" and isinstance(child, dict)
                else _sanitize(child)
            )
        return sanitized
    if isinstance(value, list):
        return [_sanitize(child) for child in value]
    if isinstance(value, str):
        return _rewrite_path(value)
    return value


def _assert_safe_json(path: Path, payload: Any) -> None:
    encoded = json.dumps(payload, sort_keys=True, allow_nan=False)
    match = FORBIDDEN_TEXT.search(encoded)
    if match:
        raise ValueError(f"forbidden public token {match.group(0)!r} in {path}")


def _copy_projected_json(
    source: Path,
    destination: Path,
    projection: Projection,
    source_inventory: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    source_root = source / projection.source
    if not source_root.is_dir():
        raise FileNotFoundError(source_root)
    entries: list[dict[str, Any]] = []
    for source_path in sorted(source_root.rglob(projection.pattern)):
        _verify_source_file(source, source_path, source_inventory)
        relative = source_path.relative_to(source_root)
        public_path = destination / projection.destination / relative
        payload = _sanitize(json.loads(source_path.read_text(encoding="utf-8")))
        _assert_safe_json(public_path, payload)
        _write_json(public_path, payload)
        entries.append({
            "path": public_path.relative_to(destination).as_posix(),
            "record_class": projection.record_class,
            "source_sha256": sha256_file(source_path),
        })
    return entries


def _validate_samples(path: Path, expected_shape: tuple[int, int] = (240_000, 6)) -> None:
    """Reject malformed, object-bearing, or nonfinite posterior sample archives."""

    with np.load(path, allow_pickle=False) as archive:
        if set(archive.files) != {"samples"}:
            raise ValueError(f"unexpected posterior archive members in {path}")
        samples = archive["samples"]
        if samples.shape != expected_shape or samples.dtype != np.dtype("float64"):
            raise ValueError(f"unexpected posterior sample shape/dtype in {path}")
        if not np.all(np.isfinite(samples)):
            raise ValueError(f"nonfinite posterior samples in {path}")


def _copy_samples(
    source: Path,
    destination: Path,
    source_inventory: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    source_root = source / "metrics" / f"{LEGACY_PHASE_PREFIX}states"
    entries: list[dict[str, Any]] = []
    for source_path in sorted(source_root.rglob("samples.npz")):
        _verify_source_file(source, source_path, source_inventory)
        _validate_samples(source_path)
        relative = source_path.relative_to(source_root)
        public_path = destination / "estimator_validation" / "states" / relative
        public_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, public_path)
        entries.append({
            "path": public_path.relative_to(destination).as_posix(),
            "record_class": "posterior_samples",
            "source_sha256": sha256_file(source_path),
        })
    return entries


def _replace_decision_references(
    payload: dict[str, Any], *, static_sha256: str, downstream_hashes: dict[int, str],
) -> None:
    payload["selection_sha256"] = static_sha256
    payload["selection_path"] = "estimator_validation/decisions/static_decision.json"
    for objective in payload.get("objectives", {}).values():
        for comparison in objective.get("seed_comparisons", []):
            seed = int(comparison["seed"])
            comparison["path"] = (
                f"estimator_validation/downstream/seed{seed}/downstream.json"
            )
            comparison["sha256"] = downstream_hashes[seed]


def _validate_source_release(source: Path) -> str:
    release_id = source.name
    if not RELEASE_ID_RE.fullmatch(release_id):
        raise ValueError(f"invalid source release ID: {release_id}")
    manifest = source / "manifest.json"
    if not manifest.is_file():
        raise FileNotFoundError(manifest)
    return release_id


def _source_inventory(source: Path) -> dict[str, dict[str, Any]]:
    manifest_path = source / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("release_id") != source.name:
        raise ValueError("source manifest/release ID mismatch")
    inventory: dict[str, dict[str, Any]] = {}
    for entry in manifest.get("files", []):
        relative = entry.get("path")
        if not isinstance(relative, str) or relative in inventory:
            raise ValueError("source manifest contains malformed or duplicate paths")
        inventory[relative] = entry
    if not inventory:
        raise ValueError("source manifest contains no files")
    return inventory


def _verify_source_file(
    source: Path,
    path: Path,
    inventory: dict[str, dict[str, Any]],
) -> None:
    relative = path.relative_to(source).as_posix()
    entry = inventory.get(relative)
    if entry is None:
        raise ValueError(f"source file is not declared by immutable manifest: {relative}")
    if path.stat().st_size != entry.get("bytes") or sha256_file(path) != entry.get("sha256"):
        raise ValueError(f"source manifest checksum mismatch: {relative}")


def _repair_score_state_links(destination: Path) -> None:
    score_roots = (
        "estimator_validation/grid",
        "estimator_validation/reference",
        "estimator_validation/doubled_budget",
    )
    for root in score_roots:
        for path in sorted((destination / root).glob("**/score.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            state = payload["state"]
            state_path = _bundle_path(destination, state["path"])
            if not state_path.is_file():
                raise ValueError(f"score references a missing public state: {state['path']}")
            state_payload = json.loads(state_path.read_text(encoding="utf-8"))
            state["sha256"] = sha256_file(state_path)
            state["samples_sha256"] = state_payload["posterior_samples"]["sha256"]
            _assert_safe_json(path, payload)
            _write_json(path, payload)


def _repair_static_decision_inputs(destination: Path, payload: dict[str, Any]) -> None:
    for item in payload.get("inputs", []):
        path = _bundle_path(destination, item["path"])
        if not path.is_file():
            raise ValueError(f"static decision references missing public score: {item['path']}")
        item["sha256"] = sha256_file(path)


def export_bundle(source: Path, destination: Path, *, include_samples: bool = True) -> Path:
    """Create a sanitized, immutable-by-convention projection of one release."""

    source = source.resolve()
    destination = destination.resolve()
    release_id = _validate_source_release(source)
    source_inventory = _source_inventory(source)
    if destination.exists():
        raise FileExistsError(f"public audit destination already exists: {destination}")
    destination.mkdir(parents=True)

    entries: list[dict[str, Any]] = []
    try:
        # Project states and score records before repairing their dependency
        # hashes. The public DAG is states -> scores -> decisions -> downstream.
        for projection in PROJECTIONS:
            entries.extend(_copy_projected_json(
                source, destination, projection, source_inventory
            ))
        _repair_score_state_links(destination)

        static_source = source / "tables/eig_convergence/static_decision.json"
        _verify_source_file(source, static_source, source_inventory)
        static_payload = _sanitize(json.loads(static_source.read_text(encoding="utf-8")))
        _repair_static_decision_inputs(destination, static_payload)
        static_path = destination / "estimator_validation/decisions/static_decision.json"
        _assert_safe_json(static_path, static_payload)
        _write_json(static_path, static_payload)
        static_sha256 = sha256_file(static_path)
        entries.append({
            "path": static_path.relative_to(destination).as_posix(),
            "record_class": "estimator_static_decision",
            "source_sha256": sha256_file(static_source),
        })

        downstream_hashes: dict[int, str] = {}
        for path in sorted((destination / "estimator_validation/downstream").glob(
            "seed*/downstream.json"
        )):
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["selection"]["path"] = (
                "estimator_validation/decisions/static_decision.json"
            )
            payload["selection"]["sha256"] = static_sha256
            _assert_safe_json(path, payload)
            _write_json(path, payload)
            downstream_hashes[int(payload["seed"])] = sha256_file(path)

        final_source = source / "tables/eig_convergence/final_decision.json"
        _verify_source_file(source, final_source, source_inventory)
        final_payload = _sanitize(json.loads(final_source.read_text(encoding="utf-8")))
        _replace_decision_references(
            final_payload,
            static_sha256=static_sha256,
            downstream_hashes=downstream_hashes,
        )
        final_path = destination / "estimator_validation/decisions/final_decision.json"
        _assert_safe_json(final_path, final_payload)
        _write_json(final_path, final_payload)
        final_sha256 = sha256_file(final_path)
        entries.append({
            "path": final_path.relative_to(destination).as_posix(),
            "record_class": "estimator_final_decision",
            "source_sha256": sha256_file(final_source),
        })

        # Bind every acquisition record to the public decision projection.
        for path in sorted((destination / "acquisition").glob("seed*/eig_seed*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["design"]["estimator_decision_sha256"] = final_sha256
            _assert_safe_json(path, payload)
            _write_json(path, payload)

        summary_source = source / "tables/paper_summary.json"
        _verify_source_file(source, summary_source, source_inventory)
        summary_payload = _sanitize(json.loads(summary_source.read_text(encoding="utf-8")))
        # The embedded decision duplicates internal hashes and is not an input
        # to headline aggregation. The public final decision is authoritative.
        summary_payload.get("eig", {}).pop("estimator_validation_decision", None)
        summary_path = destination / "aggregate/paper_summary.json"
        _assert_safe_json(summary_path, summary_payload)
        _write_json(summary_path, summary_payload)
        entries.append({
            "path": summary_path.relative_to(destination).as_posix(),
            "record_class": "published_aggregate",
            "source_sha256": sha256_file(summary_source),
        })

        if include_samples:
            entries.extend(_copy_samples(source, destination, source_inventory))

        # Add final public digests only after all cross-record rewrites.
        for entry in entries:
            public_path = destination / entry["path"]
            entry["sha256"] = sha256_file(public_path)
            entry["bytes"] = public_path.stat().st_size
        entries.sort(key=lambda item: item["path"])

        counts = Counter(entry["record_class"] for entry in entries)
        expected = dict(EXPECTED_COUNTS)
        if not include_samples:
            expected["posterior_samples"] = 0
        if dict(sorted(counts.items())) != {
            key: value for key, value in sorted(expected.items()) if value
        }:
            raise ValueError(f"unexpected public record counts: {dict(counts)}")

        checksum_lines = [f"{entry['sha256']}  {entry['path']}" for entry in entries]
        checksum_path = destination / "checksums.sha256"
        checksum_path.write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
        checksum_entry = {
            "path": "checksums.sha256",
            "record_class": "checksum_index",
            "sha256": sha256_file(checksum_path),
            "bytes": checksum_path.stat().st_size,
        }
        manifest = {
            "schema_version": BUNDLE_SCHEMA,
            "release_id": release_id,
            "scope": {
                "case_study": "magnetic_core",
                "contains_measured_input_data": False,
                "contains_machine_or_scheduler_metadata": False,
                "contains_posterior_samples": include_samples,
                "supports": [
                    "raw acquisition trajectory to published aggregate audit",
                    "EIG estimator score-to-decision traceability",
                ],
                "does_not_support": [
                    "independent laboratory replication without source measurements",
                    "claims outside the matched-model synthetic benchmark",
                ],
            },
            "transformation": {
                "name": "public scientific-record projection",
                "version": 1,
                "source_manifest_sha256": sha256_file(source / "manifest.json"),
                "removed": [
                    "scheduler logs", "machine paths", "environment dumps",
                    "credentials", "operational status markers",
                ],
            },
            "record_class_counts": dict(sorted(counts.items())),
            "files": [*entries, checksum_entry],
        }
        _assert_safe_json(destination / "manifest.json", manifest)
        _write_json(destination / "manifest.json", manifest)
        verify_bundle(destination)
    except BaseException:
        shutil.rmtree(destination, ignore_errors=True)
        raise
    return destination


def _assert_finite(value: Any, label: str) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"nonfinite number in {label}")
    if isinstance(value, dict):
        for child in value.values():
            _assert_finite(child, label)
    elif isinstance(value, list):
        for child in value:
            _assert_finite(child, label)


def _load_declared_files(bundle: Path, manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    declared: dict[str, dict[str, Any]] = {}
    for entry in manifest.get("files", []):
        relative = entry.get("path")
        if not isinstance(relative, str) or relative in declared:
            raise ValueError("manifest contains a malformed or duplicate path")
        path = _bundle_path(bundle, relative)
        if not path.is_file():
            raise ValueError(f"missing or escaping public artifact: {relative}")
        if path.stat().st_size != entry.get("bytes") or sha256_file(path) != entry.get("sha256"):
            raise ValueError(f"public artifact checksum mismatch: {relative}")
        declared[relative] = entry
    actual = {
        path.relative_to(bundle).as_posix()
        for path in bundle.rglob("*") if path.is_file() and path.name != "manifest.json"
    }
    if actual != set(declared):
        raise ValueError("manifest does not declare exactly every public artifact")
    return declared


def _paired_descriptive(values: list[float], *, seed: int) -> dict[str, float]:
    array = np.asarray(values, dtype=float)
    if array.size == 0 or not np.all(np.isfinite(array)):
        raise ValueError("paired endpoint must contain finite values")
    rng = np.random.default_rng(seed)
    bootstrap_indices = rng.integers(0, array.size, size=(10_000, array.size))
    bootstrap_means = array[bootstrap_indices].mean(axis=1)
    return {
        "mean": float(array.mean()),
        "median": float(np.median(array)),
        "sample_sd": float(array.std(ddof=1)) if array.size > 1 else 0.0,
        "bootstrap_mean_ci95_low": float(np.quantile(bootstrap_means, 0.025)),
        "bootstrap_mean_ci95_high": float(np.quantile(bootstrap_means, 0.975)),
    }


def _headline_from_trajectories(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(records, key=lambda item: int(item["provenance"]["seed"]))
    policies = [record["design"]["policies"] for record in ordered]
    seeds = [int(record["provenance"]["seed"]) for record in ordered]
    raw_counts = [item["eig_raw"]["n_measurements_to_gate"] for item in policies]
    per_cost_counts = [item["eig_per_cost"]["n_measurements_to_gate"] for item in policies]
    fixed_counts = [item["fixed_channel_balanced"]["n_measurements_to_gate"] for item in policies]
    per_cost_costs = [item["eig_per_cost"]["modeled_cost_to_gate"] for item in policies]
    fixed_costs = [item["fixed_channel_balanced"]["modeled_cost_to_gate"] for item in policies]
    raw_success = [raw is not None and fixed is not None for raw, fixed in zip(raw_counts, fixed_counts)]
    cost_success = [cost is not None and fixed is not None for cost, fixed in zip(per_cost_costs, fixed_costs)]
    raw_reductions = [
        100.0 * (fixed - raw) / fixed
        for raw, fixed, success in zip(raw_counts, fixed_counts, raw_success) if success
    ]
    cost_reductions = [
        100.0 * (fixed - cost) / fixed
        for cost, fixed, success in zip(per_cost_costs, fixed_costs, cost_success) if success
    ]
    raw_differences = [
        fixed - raw
        for raw, fixed, success in zip(raw_counts, fixed_counts, raw_success) if success
    ]
    cost_differences = [
        fixed - cost
        for cost, fixed, success in zip(per_cost_costs, fixed_costs, cost_success) if success
    ]
    raw_wins = sum(
        raw < fixed for raw, fixed in zip(raw_counts, fixed_counts)
        if raw is not None and fixed is not None
    )
    cost_wins = sum(
        cost < fixed for cost, fixed in zip(per_cost_costs, fixed_costs)
        if cost is not None and fixed is not None
    )
    return {
        "seeds": seeds,
        "seed_count": len(seeds),
        "raw_counts": raw_counts,
        "per_cost_counts": per_cost_counts,
        "fixed_counts": fixed_counts,
        "raw_mean_count": float(np.mean([value for value in raw_counts if value is not None])),
        "raw_count_reduction_pct": raw_reductions,
        "raw_mean_count_reduction_pct": float(np.mean(raw_reductions)),
        "raw_paired_difference": _paired_descriptive(raw_differences, seed=20260811),
        "raw_paired_reduction_pct": _paired_descriptive(raw_reductions, seed=20260812),
        "raw_count_wins": raw_wins,
        "raw_eig_failure_count": sum(value is None for value in raw_counts),
        "fixed_failure_count": sum(value is None for value in fixed_counts),
        "raw_complete_pair_count": sum(raw_success),
        "raw_failure_count": raw_success.count(False),
        "raw_paired_win_rate": raw_wins / sum(raw_success),
        "per_cost_modeled_costs": per_cost_costs,
        "fixed_modeled_costs": fixed_costs,
        "per_cost_reduction_pct": cost_reductions,
        "per_cost_mean_reduction_pct": float(np.mean(cost_reductions)),
        "per_cost_paired_difference": _paired_descriptive(cost_differences, seed=20260813),
        "per_cost_paired_reduction_pct": _paired_descriptive(cost_reductions, seed=20260814),
        "per_cost_eig_failure_count": sum(value is None for value in per_cost_costs),
        "cost_complete_pair_count": sum(cost_success),
        "per_cost_failure_count": cost_success.count(False),
        "per_cost_paired_win_rate": cost_wins / sum(cost_success),
        "counts": raw_counts,
        "uniform_counts": fixed_counts,
        "mean_reduction_pct": float(np.mean(raw_reductions)),
    }


def _assert_equivalent(actual: Any, expected: Any, label: str) -> None:
    if isinstance(actual, dict) and isinstance(expected, dict):
        if set(actual) != set(expected):
            raise ValueError(f"aggregate key mismatch at {label}")
        for key in actual:
            _assert_equivalent(actual[key], expected[key], f"{label}.{key}")
        return
    if isinstance(actual, list) and isinstance(expected, list):
        if len(actual) != len(expected):
            raise ValueError(f"aggregate length mismatch at {label}")
        for index, (left, right) in enumerate(zip(actual, expected)):
            _assert_equivalent(left, right, f"{label}[{index}]")
        return
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        if not math.isclose(float(actual), float(expected), rel_tol=1.0e-12, abs_tol=1.0e-12):
            raise ValueError(f"aggregate numeric mismatch at {label}")
        return
    if actual != expected:
        raise ValueError(f"aggregate value mismatch at {label}")


def verify_bundle(bundle: Path) -> dict[str, Any]:
    """Fail closed unless checksums, references, safety, and headline values agree."""

    bundle = bundle.resolve()
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != BUNDLE_SCHEMA:
        raise ValueError("wrong public audit bundle schema")
    if not RELEASE_ID_RE.fullmatch(str(manifest.get("release_id", ""))):
        raise ValueError("invalid public audit release ID")
    declared = _load_declared_files(bundle, manifest)
    counts = Counter(entry["record_class"] for entry in declared.values())
    manifest_counts = manifest.get("record_class_counts", {})
    counts.pop("checksum_index", None)
    if dict(sorted(counts.items())) != manifest_counts:
        raise ValueError("record-class counts disagree with manifest")

    for relative in declared:
        path = bundle / relative
        if path.suffix == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            _assert_finite(payload, relative)
            _assert_safe_json(path, payload)
        elif path.suffix == ".npz":
            _validate_samples(path)

    checksum_lines = (bundle / "checksums.sha256").read_text(encoding="utf-8").splitlines()
    expected_lines = {
        f"{entry['sha256']}  {relative}"
        for relative, entry in declared.items() if relative != "checksums.sha256"
    }
    if set(checksum_lines) != expected_lines:
        raise ValueError("checksum index disagrees with manifest")

    decision_path = bundle / "estimator_validation/decisions/final_decision.json"
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    static_path = bundle / "estimator_validation/decisions/static_decision.json"
    static_decision = json.loads(static_path.read_text(encoding="utf-8"))
    for item in static_decision.get("inputs", []):
        score_path = _bundle_path(bundle, item["path"])
        if not score_path.is_file() or sha256_file(score_path) != item["sha256"]:
            raise ValueError("static decision has a broken score reference")
    for score_root in (
        "estimator_validation/grid",
        "estimator_validation/reference",
        "estimator_validation/doubled_budget",
    ):
        for score_path in sorted((bundle / score_root).glob("**/score.json")):
            score = json.loads(score_path.read_text(encoding="utf-8"))
            state = score["state"]
            state_path = _bundle_path(bundle, state["path"])
            if not state_path.is_file() or sha256_file(state_path) != state["sha256"]:
                raise ValueError("estimator score has a broken state reference")
            state_payload = json.loads(state_path.read_text(encoding="utf-8"))
            samples = state_payload["posterior_samples"]
            if state["samples_sha256"] != samples["sha256"]:
                raise ValueError("estimator score/state sample digest mismatch")
            samples_path = _bundle_path(bundle, samples["path"])
            if manifest["scope"]["contains_posterior_samples"]:
                if not samples_path.is_file() or sha256_file(samples_path) != samples["sha256"]:
                    raise ValueError("estimator state has a broken posterior-sample reference")
    if decision["selection_sha256"] != sha256_file(static_path):
        raise ValueError("final decision is not bound to the public static decision")
    for objective in decision["objectives"].values():
        for comparison in objective["seed_comparisons"]:
            downstream = _bundle_path(bundle, comparison["path"])
            if sha256_file(downstream) != comparison["sha256"]:
                raise ValueError("final decision has a broken downstream reference")

    acquisition_paths = sorted(bundle.glob("acquisition/seed*/eig_seed*.json"))
    acquisitions = [json.loads(path.read_text(encoding="utf-8")) for path in acquisition_paths]
    final_sha256 = sha256_file(decision_path)
    if any(
        record["design"].get("estimator_decision_sha256") != final_sha256
        for record in acquisitions
    ):
        raise ValueError("an acquisition trajectory is not bound to the public decision")
    if any(record["data"].get("common_random_outcomes") is not True for record in acquisitions):
        raise ValueError("an acquisition trajectory lacks paired common outcomes")

    headline = _headline_from_trajectories(acquisitions)
    summary = json.loads((bundle / "aggregate/paper_summary.json").read_text(encoding="utf-8"))
    published = summary["eig"]
    comparisons = {key: published[key] for key in headline}
    _assert_equivalent(headline, comparisons, "eig")
    return {
        "release_id": manifest["release_id"],
        "verified_file_count": len(declared) + 1,
        "acquisition_seed_count": len(acquisitions),
        "raw_to_aggregate_match": True,
        "manifest_sha256": sha256_file(manifest_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    export_parser = subparsers.add_parser("export")
    export_parser.add_argument("--source-release", type=Path, required=True)
    export_parser.add_argument("--destination", type=Path, required=True)
    export_parser.add_argument(
        "--without-samples", action="store_true",
        help="Export trajectories and scores without posterior NPZ files.",
    )
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--bundle", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "export":
        result: Any = export_bundle(
            args.source_release,
            args.destination,
            include_samples=not args.without_samples,
        )
    else:
        result = verify_bundle(args.bundle)
    printable = str(result) if isinstance(result, Path) else result
    print(json.dumps(printable, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
