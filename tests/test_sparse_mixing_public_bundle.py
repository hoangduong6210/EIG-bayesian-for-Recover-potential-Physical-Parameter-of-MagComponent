"""Tests for the SparseMix disclosure-safe public projection."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]


def _module():
    path = ROOT / "scripts/public_sparse_mixing_bundle.py"
    spec = importlib.util.spec_from_file_location("sparse_public_bundle", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def _source_run(tmp_path: Path) -> Path:
    module = _module()
    run = tmp_path / "20260831T054419Z_44edb519aa48"
    results = run / "results/sparse_mixing"
    artifacts = []
    for index in range(18):
        task_id = f"task_{index:02d}"
        task_dir = results / task_id
        task_dir.mkdir(parents=True)
        chain = np.full((2, 3, 6), float(index), dtype=np.float64)
        np.savez_compressed(task_dir / "thin.npz", chain=chain)
        thin_sha = module.sha256_file(task_dir / "thin.npz")
        record = {
            "schema_version": module.RESULT_SCHEMA,
            "record_class": "endpoint_free_sampler_diagnostic",
            "protocol_id": "SparseMix-1",
            "task": {"task_id": task_id, "exact_replay": index in (0, 9)},
            "thin": {"path": "thin.npz", "sha256": thin_sha,
                     "shape": [2, 3, 6]},
            "disclosure": {
                "claim_bearing_result": False,
                "retroactive_mm2_admission_allowed": False,
                "scientific_endpoints_included": False,
            },
        }
        _write_json(task_dir / "result.json", record)
        artifacts.append({
            "task_id": task_id,
            "result_path": f"{task_id}/result.json",
            "result_sha256": module.sha256_file(task_dir / "result.json"),
            "thin_path": f"{task_id}/thin.npz",
            "thin_sha256": thin_sha,
        })
    manifest = {
        "schema_version": module.SOURCE_MANIFEST_SCHEMA,
        "record_class": "endpoint_free_sampler_diagnostic_manifest",
        "protocol_id": "SparseMix-1",
        "config_sha256": "1" * 64,
        "parent": {"campaign_id": "MM-2"},
        "matrix": {"artifact_count": 36, "expected_task_count": 18,
                   "validated_task_count": 18},
        "classifications": {
            "n3": {"classification": "mixing_supported"},
            "n4": {"classification": "mixing_not_supported"},
        },
        "artifacts": artifacts,
        "disclosure": {
            "claim_bearing_result": False,
            "mm2_admission_changed": False,
            "scientific_endpoints_included": False,
        },
    }
    _write_json(run / "summary/sparse_mixing/manifest.json", manifest)
    provenance = run / "provenance/run.env"
    provenance.parent.mkdir(parents=True)
    provenance.write_text(
        "\n".join((
            f"MAGCORE_RUN_ID={run.name}",
            f"MAGCORE_GIT_REVISION={'2' * 40}",
            f"MAGCORE_SOURCE_ARCHIVE_SHA256={'3' * 64}",
            f"MAGCORE_SOURCE_STATUS_SHA256={hashlib.sha256(b'').hexdigest()}",
        )) + "\n",
        encoding="utf-8",
    )
    return run


def test_export_is_exact_complete_and_verifiable(tmp_path: Path):
    module = _module()
    source = _source_run(tmp_path)
    destination = tmp_path / "public"
    exported = module.export_bundle(source, destination)
    report = module.verify_bundle(destination)
    assert exported["scope"]["contains_deterministic_thinned_chains"] is True
    assert report["valid"] is True
    assert report["task_count"] == 18
    assert report["payload_file_count"] == 37
    assert exported["validation"] == {
        "exact_replay_match_required_by_source_validator": True,
        "exact_replay_task_count": 2,
        "full_chain_diagnostics_recomputable_from_bundle": False,
    }


def test_verifier_rejects_tampering_and_undeclared_files(tmp_path: Path):
    module = _module()
    source = _source_run(tmp_path)
    destination = tmp_path / "public"
    module.export_bundle(source, destination)
    result = destination / "records/task_00/result.json"
    result.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum mismatch"):
        module.verify_bundle(destination)

    destination = tmp_path / "public-extra"
    module.export_bundle(source, destination)
    (destination / "undeclared.txt").write_text("extra\n", encoding="utf-8")
    with pytest.raises(ValueError, match="undeclared or missing"):
        module.verify_bundle(destination)


def test_export_refuses_dirty_source_and_machine_text(tmp_path: Path):
    module = _module()
    source = _source_run(tmp_path)
    run_env = source / "provenance/run.env"
    run_env.write_text(
        run_env.read_text(encoding="utf-8").replace(
            hashlib.sha256(b"").hexdigest(), "4" * 64
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="worktree was not clean"):
        module.export_bundle(source, tmp_path / "dirty-public")

    source = _source_run(tmp_path / "second")
    result = source / "results/sparse_mixing/task_00/result.json"
    payload = json.loads(result.read_text(encoding="utf-8"))
    payload["machine_path"] = "/" + "users/account/private"
    _write_json(result, payload)
    manifest_path = source / "summary/sparse_mixing/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"][0]["result_sha256"] = module.sha256_file(result)
    _write_json(manifest_path, manifest)
    with pytest.raises(ValueError, match="machine or credential material"):
        module.export_bundle(source, tmp_path / "unsafe-public")
