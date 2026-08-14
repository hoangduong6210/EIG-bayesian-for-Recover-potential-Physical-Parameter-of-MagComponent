"""Deterministic tests for the sanitized public evidence projection."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_module():
    path = ROOT / "scripts" / "public_audit_bundle.py"
    spec = importlib.util.spec_from_file_location("public_audit_bundle_for_tests", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_sanitizer_removes_machine_provenance_and_rewrites_legacy_paths():
    module = load_module()
    phase = "p" + "2_"
    raw = {
        "provenance": {
            "command": ["/" + "users/account/run.py"],
            "slurm": {"node_list": "compute001", "job_id": "7"},
            "seed": 42,
            "git_commit": "a" * 40,
            "configuration_sha256": "b" * 64,
            "dependency_lock_sha256": "c" * 64,
            "command_sha256": "d" * 64,
            "data_sha256": {"synthetic://seed-and-command": "e" * 64},
            "python": "3.12.4",
            "started_at_utc": "2026-08-12T00:00:00Z",
            "ended_at_utc": "2026-08-12T00:01:00Z",
        },
        phase + "selection_sha256": "f" * 64,
        "path": "/" + "users/account/run/results/" + phase
                + "states/s7100_n2/state.json",
    }
    public = module._sanitize(raw)
    assert "command" not in public["provenance"]
    assert "slurm" not in public["provenance"]
    assert public["estimator_decision_sha256"] == "f" * 64
    assert public["path"] == "estimator_validation/states/s7100_n2/state.json"
    module._assert_safe_json(Path("record.json"), public)


def _write_minimal_bundle(module, bundle: Path) -> None:
    static_path = bundle / "estimator_validation/decisions/static_decision.json"
    module._write_json(static_path, {"inputs": [], "valid": True})
    final_path = bundle / "estimator_validation/decisions/final_decision.json"
    final = {
        "selection_sha256": module.sha256_file(static_path),
        "selection_path": "estimator_validation/decisions/static_decision.json",
        "objectives": {},
        "valid": True,
    }
    module._write_json(final_path, final)
    acquisition = {
        "provenance": {"seed": 7300},
        "data": {"common_random_outcomes": True},
        "design": {
            "estimator_decision_sha256": module.sha256_file(final_path),
            "policies": {
                "eig_raw": {
                    "n_measurements_to_gate": 5,
                    "modeled_cost_to_gate": 175.0,
                },
                "eig_per_cost": {
                    "n_measurements_to_gate": 6,
                    "modeled_cost_to_gate": 190.0,
                },
                "fixed_channel_balanced": {
                    "n_measurements_to_gate": 9,
                    "modeled_cost_to_gate": 290.0,
                },
            },
        },
    }
    acquisition_path = bundle / "acquisition/seed7300/eig_seed7300.json"
    module._write_json(acquisition_path, acquisition)
    summary_path = bundle / "aggregate/paper_summary.json"
    module._write_json(summary_path, {
        "eig": module._headline_from_trajectories([acquisition]),
    })

    artifacts = {
        "estimator_validation/decisions/static_decision.json": "estimator_static_decision",
        "estimator_validation/decisions/final_decision.json": "estimator_final_decision",
        "acquisition/seed7300/eig_seed7300.json": "acquisition_trajectory",
        "aggregate/paper_summary.json": "published_aggregate",
    }
    entries = []
    for relative, record_class in artifacts.items():
        path = bundle / relative
        entries.append({
            "path": relative,
            "record_class": record_class,
            "sha256": module.sha256_file(path),
            "bytes": path.stat().st_size,
            "source_sha256": "0" * 64,
        })
    checksum_path = bundle / "checksums.sha256"
    checksum_path.write_text(
        "\n".join(f"{entry['sha256']}  {entry['path']}" for entry in entries) + "\n",
        encoding="utf-8",
    )
    checksum_entry = {
        "path": "checksums.sha256",
        "record_class": "checksum_index",
        "sha256": module.sha256_file(checksum_path),
        "bytes": checksum_path.stat().st_size,
    }
    counts = {}
    for entry in entries:
        counts[entry["record_class"]] = counts.get(entry["record_class"], 0) + 1
    module._write_json(bundle / "manifest.json", {
        "schema_version": module.BUNDLE_SCHEMA,
        "release_id": "20260812T035654Z_a0703698ace9",
        "scope": {"contains_posterior_samples": False},
        "record_class_counts": counts,
        "files": [*entries, checksum_entry],
    })


def test_verifier_reconstructs_acquisition_aggregate_and_detects_tampering(tmp_path: Path):
    module = load_module()
    bundle = tmp_path / "audit"
    bundle.mkdir()
    _write_minimal_bundle(module, bundle)
    report = module.verify_bundle(bundle)
    assert report["acquisition_seed_count"] == 1
    assert report["raw_to_aggregate_match"] is True

    acquisition = bundle / "acquisition/seed7300/eig_seed7300.json"
    payload = json.loads(acquisition.read_text(encoding="utf-8"))
    payload["design"]["policies"]["eig_raw"]["n_measurements_to_gate"] = 4
    module._write_json(acquisition, payload)
    with pytest.raises(ValueError, match="checksum mismatch"):
        module.verify_bundle(bundle)


def test_public_projection_rejects_unrecognized_absolute_paths():
    module = load_module()
    with pytest.raises(ValueError, match="unrecognized absolute path"):
        module._sanitize({"path": "/" + "home/account/private.json"})


def test_public_projection_rejects_relative_path_traversal():
    module = load_module()
    with pytest.raises(ValueError, match="traversal"):
        module._sanitize({"path": "../../private.json"})
