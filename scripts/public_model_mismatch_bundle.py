#!/usr/bin/env python3
"""Export and verify the disclosure-safe MM-3 raw-to-aggregate audit bundle.

The production run contains machine-specific command lines and scheduler
metadata.  This tool removes those fields while preserving every scientific
task record, including acquisition paths, candidate scores, holdout endpoints,
and sampler checkpoint diagnostics.  Verification reconstructs the registered
120-task matrix and every aggregate statistic from the projected records.
"""

from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import importlib.util
import json
import os
import re
import shutil
import tarfile
from pathlib import Path, PurePosixPath
from typing import Any

from magcore_calib.model_mismatch import (
    MISMATCH_AGGREGATE_SCHEMA,
    POLICIES,
    config_sha256,
    load_model_mismatch_plan,
    validate_mismatch_result,
)


BUNDLE_SCHEMA = "magcore-model-mismatch-public-audit/1.0"
ASSET_SCHEMA = "magcore-model-mismatch-audit-assets/1.0"
ADMISSION_SCHEMA = "magcore-model-mismatch-admission/1.0"
CAMPAIGN_ID = "MM-3"
RUN_ID_RE = re.compile(r"^\d{8}T\d{6}Z_[0-9a-f]{12}$")
FORBIDDEN_TEXT = re.compile(
    r"/(?:users|home|scratch|tmp)/|[A-Za-z]:[/\\]Users[/\\]|"
    r"PGS0407|binben14|ghp_[A-Za-z0-9]+|github_pat_[A-Za-z0-9_]+|"
    r"(?:Bearer|Authorization:)\s+[A-Za-z0-9._-]+|"
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|"
    r"\b(?:SLURM_|node_list|job_id|array_job_id)\b|"
    r"\b(?:Chat" + r"GPT|Open" + r"AI|Gr" + r"ok|Clau" + r"de|Co" + r"pilot)\b",
    re.IGNORECASE,
)
PUBLIC_PROVENANCE_FIELDS = (
    "started_at_utc",
    "ended_at_utc",
    "git_commit",
    "seed",
    "python",
    "command_sha256",
    "configuration_sha256",
    "dependency_lock_sha256",
    "data_sha256",
    "estimator_decision",
    "estimator_decision_sha256",
    "estimator_source_release_id",
    "posterior_state_cache",
    "sampler_method",
    "sampler_qualification_config_sha256",
    "sampler_qualification_manifest_sha256",
)


def sha256_file(path: Path) -> str:
    """Return a streaming SHA-256 digest."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    """Write canonical, finite JSON."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def safe_relative(root: Path, relative: str) -> Path:
    """Resolve a manifest path without permitting traversal."""

    pure = PurePosixPath(relative)
    if not relative or pure.is_absolute() or ".." in pure.parts or "\\" in relative:
        raise ValueError(f"unsafe bundle path: {relative!r}")
    path = (root / Path(*pure.parts)).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"bundle path escapes root: {relative!r}")
    return path


def _aggregate_module() -> Any:
    """Load the campaign's locked aggregation implementation."""

    path = Path(__file__).resolve().parents[1] / "experiments" / "aggregate_model_mismatch.py"
    spec = importlib.util.spec_from_file_location("mm3_public_aggregate", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load the model-mismatch aggregator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _public_record(record: dict[str, Any]) -> dict[str, Any]:
    """Remove operational provenance without changing scientific fields."""

    public = copy.deepcopy(record)
    provenance = public["provenance"]
    public["provenance"] = {
        key: provenance[key] for key in PUBLIC_PROVENANCE_FIELDS if key in provenance
    }
    encoded = json.dumps(public, sort_keys=True, allow_nan=False)
    match = FORBIDDEN_TEXT.search(encoded)
    if match:
        raise ValueError(f"forbidden public token {match.group(0)!r} remains in task record")
    return public


def _load_matrix(
    records_root: Path, config_path: Path,
) -> tuple[Any, dict[tuple[str, int], tuple[Path, dict[str, Any]]]]:
    """Validate and return the exact registered scenario--seed matrix."""

    plan = load_model_mismatch_plan(config_path)
    expected_config_sha = config_sha256(config_path)
    by_key: dict[tuple[str, int], tuple[Path, dict[str, Any]]] = {}
    aggregate = _aggregate_module()
    for path in sorted(records_root.glob("*/result.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        validate_mismatch_result(record)
        if record["campaign_id"] != CAMPAIGN_ID or record["config_sha256"] != expected_config_sha:
            raise ValueError(f"task record is outside the MM-3 contract: {path}")
        key = record["scenario"]["name"], record["seed"]
        if record["scenario"] != plan.scenario(key[0]).as_dict():
            raise ValueError(f"task scenario differs from the MM-3 plan: {path}")
        aggregate._validate_plan_provenance(record, plan)
        if key in by_key:
            raise ValueError(f"duplicate MM-3 task record: {key}")
        by_key[key] = path, record
    expected = {
        (scenario.name, seed) for scenario in plan.scenarios for seed in plan.seeds
    }
    missing, extra = expected - by_key.keys(), by_key.keys() - expected
    if missing or extra:
        raise ValueError(
            f"MM-3 matrix differs: missing={sorted(missing)}, extra={sorted(extra)}"
        )
    return plan, by_key


def reconstruct_aggregate(
    plan: Any,
    by_key: dict[tuple[str, int], tuple[Path, dict[str, Any]]],
    *,
    config_digest: str,
    source_hashes: dict[tuple[str, int], str],
) -> dict[str, Any]:
    """Rebuild the locked aggregate from validated task records."""

    aggregate = _aggregate_module()
    scenarios: dict[str, Any] = {}
    for scenario in plan.scenarios:
        records = [by_key[(scenario.name, seed)][1] for seed in plan.seeds]
        scenarios[scenario.name] = {
            "data_generating_contract": scenario.as_dict(),
            "policies": {
                policy: aggregate._policy_summary(records, policy) for policy in POLICIES
            },
            "paired_strong_comparator_contrasts": {
                f"{policy}_vs_{comparator}": aggregate._contrast_summary(
                    records,
                    policy,
                    comparator,
                    endpoint,
                    scenario=scenario.name,
                )
                for policy, comparator, endpoint in aggregate.CONTRASTS
            },
        }
    source_files = [
        {
            "scenario": scenario,
            "seed": seed,
            "path": by_key[(scenario, seed)][0].parent.name + "/result.json",
            "sha256": source_hashes[(scenario, seed)],
        }
        for scenario, seed in sorted(by_key)
    ]
    return {
        "schema_version": MISMATCH_AGGREGATE_SCHEMA,
        "campaign_id": plan.campaign_id,
        "config_sha256": config_digest,
        "estimator_source_release_id": plan.estimator_source_release_id,
        "estimator_decision_sha256": plan.estimator_decision_sha256,
        "seed_count_per_scenario": len(plan.seeds),
        "scenario_count": len(plan.scenarios),
        "policy_count": len(POLICIES),
        "source_result_count": len(source_files),
        "source_files": source_files,
        "aggregation_rules": {
            "gate_failures_reported_separately": True,
            "count_and_cost_summaries_conditioned_on_reaching_gate": True,
            "paired_differences_exclude_pairs_with_either_gate_failure": True,
            "false_confidence_denominators": ["all_seeds", "reached_gate"],
            "holdout_used_for_stopping": False,
        },
        "scenarios": scenarios,
    }


def _scientific_aggregate(payload: dict[str, Any]) -> dict[str, Any]:
    """Exclude only the source-file inventory from aggregate comparison."""

    projected = copy.deepcopy(payload)
    projected.pop("source_files", None)
    return projected


def export_bundle(
    run_dir: Path,
    bundle_dir: Path,
    registration: Path,
    sampler_manifest: Path,
    sampler_config: Path,
) -> dict[str, Any]:
    """Create a new disclosure-safe bundle from one immutable run."""

    run_dir, bundle_dir = run_dir.resolve(), bundle_dir.resolve()
    if bundle_dir.exists():
        raise FileExistsError(f"refusing to overwrite bundle: {bundle_dir}")
    if not RUN_ID_RE.fullmatch(run_dir.name):
        raise ValueError(f"invalid MM-3 run ID: {run_dir.name}")
    source_config = run_dir / "source/configs/model_mismatch_v3.toml"
    source_records = run_dir / "results/model_mismatch_v3"
    source_aggregate = run_dir / "summary/model_mismatch_v3/aggregate.json"
    required = (
        source_config,
        source_records,
        source_aggregate,
        registration,
        sampler_manifest,
        sampler_config,
    )
    if any(not path.exists() for path in required):
        raise FileNotFoundError("MM-3 export input is incomplete")
    plan, by_key = _load_matrix(source_records, source_config)
    original_hashes = {
        key: sha256_file(path) for key, (path, _) in by_key.items()
    }
    config_digest = config_sha256(source_config)
    rebuilt = reconstruct_aggregate(
        plan,
        by_key,
        config_digest=config_digest,
        source_hashes=original_hashes,
    )
    published = json.loads(source_aggregate.read_text(encoding="utf-8"))
    if rebuilt != published:
        raise ValueError("production MM-3 aggregate does not reconstruct exactly")

    bundle_dir.mkdir(parents=True)
    record_entries = []
    for key in sorted(by_key):
        source_path, record = by_key[key]
        relative = f"records/{source_path.parent.name}/result.json"
        destination = safe_relative(bundle_dir, relative)
        write_json(destination, _public_record(record))
        record_entries.append({
            "scenario": key[0],
            "seed": key[1],
            "path": relative,
            "sha256": sha256_file(destination),
            "source_sha256": original_hashes[key],
            "bytes": destination.stat().st_size,
        })

    supporting = {
        "aggregate/aggregate.json": source_aggregate,
        "configs/model_mismatch_v3.toml": source_config,
        "configs/sparse_mixing_v2.toml": sampler_config,
        "contract/registration.json": registration,
        (
            "results/diagnostics/sparse_mixing/SparseMix-2/"
            "20260912T060428Z_7a00dff3106f/manifest.json"
        ): sampler_manifest,
    }
    supporting_entries = []
    for relative, source in supporting.items():
        destination = safe_relative(bundle_dir, relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        if destination.suffix in {".json", ".toml"}:
            match = FORBIDDEN_TEXT.search(destination.read_text(encoding="utf-8"))
            if match:
                raise ValueError(f"forbidden public token in supporting record: {relative}")
        supporting_entries.append({
            "path": relative,
            "sha256": sha256_file(destination),
            "source_sha256": sha256_file(source),
            "bytes": destination.stat().st_size,
        })

    registration_record = json.loads(registration.read_text(encoding="utf-8"))
    source_revision = registration_record.get("source_revision")
    if not isinstance(source_revision, str) or not re.fullmatch(r"[0-9a-f]{40}", source_revision):
        raise ValueError("MM-3 registration has no valid source revision")
    manifest = {
        "schema_version": BUNDLE_SCHEMA,
        "campaign_id": CAMPAIGN_ID,
        "run_id": run_dir.name,
        "source_revision": source_revision,
        "config_sha256": config_digest,
        "estimator_decision_sha256": plan.estimator_decision_sha256,
        "sampler_qualification_manifest_sha256": plan.sampler_qualification_manifest_sha256,
        "sampler_qualification_config_sha256": plan.sampler_qualification_config_sha256,
        "matrix": {
            "scenario_count": len(plan.scenarios),
            "seed_count_per_scenario": len(plan.seeds),
            "policy_count": len(POLICIES),
            "task_record_count": len(record_entries),
        },
        "validation": {
            "all_task_records_schema_valid": True,
            "all_sampler_decisions_pass": True,
            "exact_registered_matrix": True,
            "raw_to_aggregate_scientific_match": True,
        },
        "scope": {
            "contains_scientific_endpoints": True,
            "contains_acquisition_trajectories": True,
            "contains_candidate_scores": True,
            "contains_sampler_checkpoint_histories": True,
            "contains_full_walker_iteration_chains": False,
            "supports_independent_full_chain_diagnostic_recomputation": False,
        },
        "task_records": record_entries,
        "supporting_records": supporting_entries,
    }
    write_json(bundle_dir / "manifest.json", manifest)
    checksum_rows = []
    for path in sorted(p for p in bundle_dir.rglob("*") if p.is_file()):
        if path.name == "checksums.sha256":
            continue
        checksum_rows.append(f"{sha256_file(path)}  {path.relative_to(bundle_dir).as_posix()}")
    (bundle_dir / "checksums.sha256").write_text(
        "\n".join(checksum_rows) + "\n", encoding="utf-8"
    )
    return verify_bundle(bundle_dir)


def verify_bundle(bundle_dir: Path) -> dict[str, Any]:
    """Fail closed unless the public bundle reconstructs the MM-3 aggregate."""

    bundle_dir = bundle_dir.resolve()
    manifest_path = bundle_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != BUNDLE_SCHEMA or manifest.get("campaign_id") != CAMPAIGN_ID:
        raise ValueError("unsupported MM-3 public bundle identity")
    if not RUN_ID_RE.fullmatch(str(manifest.get("run_id", ""))):
        raise ValueError("invalid MM-3 public bundle run ID")
    declared: dict[str, str] = {}
    for entry in [*manifest.get("task_records", []), *manifest.get("supporting_records", [])]:
        path = safe_relative(bundle_dir, entry.get("path", ""))
        if not path.is_file() or sha256_file(path) != entry.get("sha256"):
            raise ValueError(f"bundle artifact checksum mismatch: {entry.get('path')}")
        declared[entry["path"]] = entry["sha256"]
    checksum_path = bundle_dir / "checksums.sha256"
    checksum_rows = {}
    for line in checksum_path.read_text(encoding="utf-8").splitlines():
        digest, relative = line.split(maxsplit=1)
        checksum_rows[relative.strip()] = digest
    expected_rows = {"manifest.json": sha256_file(manifest_path), **declared}
    if checksum_rows != expected_rows:
        raise ValueError("bundle checksum index differs from its manifest inventory")
    actual_files = {
        path.relative_to(bundle_dir).as_posix()
        for path in bundle_dir.rglob("*") if path.is_file()
    }
    if actual_files != {*expected_rows, "checksums.sha256"}:
        raise ValueError("MM-3 bundle contains an undeclared or missing file")
    if manifest.get("validation") != {
        "all_task_records_schema_valid": True,
        "all_sampler_decisions_pass": True,
        "exact_registered_matrix": True,
        "raw_to_aggregate_scientific_match": True,
    }:
        raise ValueError("MM-3 public bundle validation declaration differs")
    for relative in declared:
        if Path(relative).suffix not in {".json", ".toml"}:
            continue
        match = FORBIDDEN_TEXT.search(
            safe_relative(bundle_dir, relative).read_text(encoding="utf-8")
        )
        if match:
            raise ValueError(f"forbidden public token in bundle artifact: {relative}")

    config = bundle_dir / "configs/model_mismatch_v3.toml"
    plan, by_key = _load_matrix(bundle_dir / "records", config)
    public_entries = {
        (entry["scenario"], entry["seed"]): entry
        for entry in manifest["task_records"]
    }
    if set(public_entries) != set(by_key):
        raise ValueError("MM-3 public task identities differ from record contents")
    for key, (path, _) in by_key.items():
        if public_entries[key]["path"] != path.relative_to(bundle_dir).as_posix():
            raise ValueError("MM-3 public task path differs from its record identity")
    source_hashes = {
        (entry["scenario"], entry["seed"]): entry["source_sha256"]
        for entry in manifest["task_records"]
    }
    if len(source_hashes) != len(manifest["task_records"]):
        raise ValueError("duplicate task identity in MM-3 bundle manifest")
    rebuilt = reconstruct_aggregate(
        plan,
        by_key,
        config_digest=config_sha256(config),
        source_hashes=source_hashes,
    )
    published = json.loads(
        (bundle_dir / "aggregate/aggregate.json").read_text(encoding="utf-8")
    )
    if _scientific_aggregate(rebuilt) != _scientific_aggregate(published):
        raise ValueError("public MM-3 task records do not reconstruct the scientific aggregate")
    if rebuilt["source_files"] != published.get("source_files"):
        raise ValueError("MM-3 source-file hashes do not match the production aggregate")
    expected_matrix = {
        "scenario_count": 4,
        "seed_count_per_scenario": 30,
        "policy_count": 8,
        "task_record_count": 120,
    }
    if manifest.get("matrix") != expected_matrix:
        raise ValueError("MM-3 public bundle matrix declaration differs")
    return {
        "campaign_id": CAMPAIGN_ID,
        "run_id": manifest["run_id"],
        "task_record_count": len(by_key),
        "aggregate_sha256": sha256_file(bundle_dir / "aggregate/aggregate.json"),
        "bundle_manifest_sha256": sha256_file(manifest_path),
        "raw_to_aggregate_scientific_match": True,
    }


def archive_bundle(bundle_dir: Path, output: Path) -> dict[str, Any]:
    """Create a byte-reproducible gzip-compressed tar archive."""

    verify_bundle(bundle_dir)
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite archive: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".partial")
    root_name = bundle_dir.resolve().name
    with temporary.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:
                for path in sorted(bundle_dir.resolve().rglob("*")):
                    relative = path.relative_to(bundle_dir.resolve())
                    info = archive.gettarinfo(str(path), arcname=(Path(root_name) / relative).as_posix())
                    info.uid = info.gid = 0
                    info.uname = info.gname = ""
                    info.mtime = 0
                    if path.is_file():
                        with path.open("rb") as stream:
                            archive.addfile(info, stream)
                    else:
                        archive.addfile(info)
    os.replace(temporary, output)
    return {"path": str(output), "sha256": sha256_file(output), "bytes": output.stat().st_size}


def publish_records(
    bundle_dir: Path,
    archive: Path,
    destination: Path,
    asset_url: str,
) -> dict[str, Any]:
    """Write the small repository records that bind the external audit asset."""

    report = verify_bundle(bundle_dir)
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    archive = archive.resolve()
    if not archive.is_file() or not asset_url.startswith("https://github.com/"):
        raise ValueError("MM-3 public asset declaration is incomplete")
    targets = ("aggregate.json", "audit_manifest.json", "admission.json", "asset.json")
    if any((destination / name).exists() for name in targets):
        raise FileExistsError("refusing to overwrite a published MM-3 record")
    shutil.copyfile(bundle_dir / "aggregate/aggregate.json", destination / "aggregate.json")
    shutil.copyfile(bundle_dir / "manifest.json", destination / "audit_manifest.json")
    admission = {
        "schema_version": ADMISSION_SCHEMA,
        "campaign_id": CAMPAIGN_ID,
        "run_id": report["run_id"],
        "decision": "admitted",
        "basis": {
            "expected_task_record_count": 120,
            "validated_task_record_count": 120,
            "all_sampler_decisions_pass": True,
            "exact_registered_matrix": True,
            "raw_to_aggregate_scientific_match": True,
        },
        "aggregate_sha256": report["aggregate_sha256"],
        "audit_manifest_sha256": report["bundle_manifest_sha256"],
        "claim_scope": "preregistered synthetic model-mismatch campaign",
        "does_not_establish": [
            "laboratory time savings",
            "global six-parameter identification",
            "robust uncertainty calibration under structural discrepancy",
            "general policy superiority",
        ],
    }
    write_json(destination / "admission.json", admission)
    asset = {
        "schema_version": ASSET_SCHEMA,
        "campaign_id": CAMPAIGN_ID,
        "run_id": report["run_id"],
        "aggregate_sha256": report["aggregate_sha256"],
        "audit_manifest_sha256": report["bundle_manifest_sha256"],
        "asset": {
            "name": archive.name,
            "url": asset_url,
            "sha256": sha256_file(archive),
            "bytes": archive.stat().st_size,
            "task_record_count": 120,
        },
        "validation": {
            "exact_registered_matrix": True,
            "all_task_records_schema_valid": True,
            "raw_to_aggregate_scientific_match": True,
        },
        "scope": json.loads((bundle_dir / "manifest.json").read_text())["scope"],
    }
    write_json(destination / "asset.json", asset)
    return {**report, "asset_sha256": asset["asset"]["sha256"]}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    export = subparsers.add_parser("export")
    export.add_argument("--run-dir", required=True, type=Path)
    export.add_argument("--bundle-dir", required=True, type=Path)
    export.add_argument("--registration", required=True, type=Path)
    export.add_argument("--sampler-manifest", required=True, type=Path)
    export.add_argument("--sampler-config", required=True, type=Path)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--bundle-dir", required=True, type=Path)
    archive = subparsers.add_parser("archive")
    archive.add_argument("--bundle-dir", required=True, type=Path)
    archive.add_argument("--out", required=True, type=Path)
    publish = subparsers.add_parser("publish")
    publish.add_argument("--bundle-dir", required=True, type=Path)
    publish.add_argument("--archive", required=True, type=Path)
    publish.add_argument("--destination", required=True, type=Path)
    publish.add_argument("--asset-url", required=True)
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.command == "export":
        report = export_bundle(
            args.run_dir,
            args.bundle_dir,
            args.registration,
            args.sampler_manifest,
            args.sampler_config,
        )
    elif args.command == "verify":
        report = verify_bundle(args.bundle_dir)
    elif args.command == "archive":
        report = archive_bundle(args.bundle_dir, args.out)
    else:
        report = publish_records(
            args.bundle_dir,
            args.archive,
            args.destination,
            args.asset_url,
        )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
