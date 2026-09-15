"""Fail-closed checks for the MM-3 public raw-to-aggregate projection."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_module():
    path = ROOT / "scripts/public_model_mismatch_bundle.py"
    spec = importlib.util.spec_from_file_location("public_mm3_bundle_tested", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_public_record_removes_machine_provenance_and_preserves_science():
    module = load_module()
    record = {
        "provenance": {
            "command": ["/" + "users/account/run.py"],
            "slurm": {"job_id": "123", "node_list": "node1"},
            "seed": 10100,
            "git_commit": "a" * 40,
            "sampler_method": "de_snooker",
        },
        "policies": {"eig_raw": {"n_measurements_to_gate": 5}},
    }
    public = module._public_record(record)
    assert set(public["provenance"]) == {"seed", "git_commit", "sampler_method"}
    assert public["policies"] == record["policies"]
    assert "command" not in json.dumps(public)


@pytest.mark.parametrize("relative", ["../secret", "/absolute", "a\\b", ""])
def test_bundle_path_rejects_unsafe_references(tmp_path: Path, relative: str):
    module = load_module()
    with pytest.raises(ValueError, match="unsafe bundle path"):
        module.safe_relative(tmp_path, relative)


def test_scientific_comparison_excludes_only_source_inventory():
    module = load_module()
    left = {"campaign_id": "MM-3", "source_files": [{"sha256": "a"}], "scenarios": {"x": 1}}
    right = {"campaign_id": "MM-3", "source_files": [{"sha256": "b"}], "scenarios": {"x": 1}}
    assert module._scientific_aggregate(left) == module._scientific_aggregate(right)
    right["scenarios"]["x"] = 2
    assert module._scientific_aggregate(left) != module._scientific_aggregate(right)


def test_archive_is_byte_reproducible(tmp_path: Path, monkeypatch):
    module = load_module()
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "record.txt").write_text("scientific record\n", encoding="utf-8")
    monkeypatch.setattr(module, "verify_bundle", lambda _: {})
    first, second = tmp_path / "first.tar.gz", tmp_path / "second.tar.gz"
    first_report = module.archive_bundle(bundle, first)
    second_report = module.archive_bundle(bundle, second)
    assert first_report["sha256"] == second_report["sha256"]
