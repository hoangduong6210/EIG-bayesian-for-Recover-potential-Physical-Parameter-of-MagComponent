"""Cheap checks of the Wiki's protocol-to-evidence binding."""
import copy
import importlib.util
import json
from pathlib import Path
import tomllib

import pytest

WIKI = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("wiki_mm3_contract", WIKI / "build.py")
build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build)


def test_current_mm3_prerequisites_are_hash_bound():
    with (WIKI / "manuscript.toml").open("rb") as stream:
        manifest = tomllib.load(stream)
    report = build.check_mm3_readiness(manifest)
    assert report["model_mismatch_v3_sha256"] == manifest["campaigns"]["model_mismatch_v3"]["config_sha256"]
    assert report["production_integration_sha256"] == manifest["diagnostics"]["production_integration"]["record_sha256"]


def test_current_mm3_result_is_hash_bound_and_admitted():
    with (WIKI / "manuscript.toml").open("rb") as stream:
        manifest = tomllib.load(stream)
    contract = manifest["campaigns"]["model_mismatch_v3"]
    report = build.check_mm3_result_contract(contract)
    assert report["model_mismatch_v3_aggregate_sha256"] == contract["aggregate_sha256"]
    assert report["model_mismatch_v3_audit_manifest_sha256"] == contract["audit_manifest_sha256"]


@pytest.mark.parametrize(
    "label", ["aggregate", "audit_manifest", "admission", "asset_descriptor"]
)
def test_mm3_result_record_is_not_allowed_to_drift(label):
    with (WIKI / "manuscript.toml").open("rb") as stream:
        manifest = tomllib.load(stream)
    contract = copy.deepcopy(manifest["campaigns"]["model_mismatch_v3"])
    contract[f"{label}_sha256"] = "0" * 64
    with pytest.raises(build.WikiError, match="SHA-256 mismatch"):
        build.check_mm3_result_contract(contract)


@pytest.mark.parametrize("change", ["task_count", "scenario", "source_hash", "decision"])
def test_mm3_result_contract_rejects_semantic_tampering(tmp_path, monkeypatch, change):
    with (WIKI / "manuscript.toml").open("rb") as stream:
        manifest = tomllib.load(stream)
    original = manifest["campaigns"]["model_mismatch_v3"]
    contract = copy.deepcopy(original)
    repository = tmp_path
    (repository / "wiki").mkdir()
    payloads = {}
    for label in ("aggregate", "audit_manifest", "admission", "asset_descriptor"):
        source = WIKI.parent / original[label]
        payloads[label] = json.loads(source.read_text(encoding="utf-8"))
    if change == "task_count":
        payloads["audit_manifest"]["matrix"]["task_record_count"] = 119
    elif change == "scenario":
        payloads["aggregate"]["scenarios"].pop("combined_mismatch")
    elif change == "source_hash":
        payloads["audit_manifest"]["task_records"][0]["source_sha256"] = "0" * 64
    else:
        payloads["admission"]["decision"] = "not_admitted"
    for label, payload in payloads.items():
        relative = Path("records") / f"{label}.json"
        path = repository / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        contract[label] = relative.as_posix()
        contract[f"{label}_sha256"] = build.sha256(path)
    monkeypatch.setattr(build, "WIKI_ROOT", repository / "wiki")
    with pytest.raises(build.WikiError):
        build.check_mm3_result_contract(contract)


def test_submission_record_is_not_allowed_to_drift():
    with (WIKI / "manuscript.toml").open("rb") as stream:
        manifest = tomllib.load(stream)
    manifest["campaigns"]["model_mismatch_v3"]["registration_sha256"] = "0" * 64
    with pytest.raises(build.WikiError, match="registration checksum"):
        build.check_mm3_readiness(manifest)


@pytest.mark.parametrize("change", ["digest", "overall", "missing_state", "endpoint", "admission"])
def test_integration_cannot_claim_a_false_pass(tmp_path, monkeypatch, change):
    with (WIKI / "manuscript.toml").open("rb") as stream:
        original = tomllib.load(stream)
    contract = copy.deepcopy(original["diagnostics"]["production_integration"])
    value = json.loads((WIKI.parent / contract["record"]).read_text())
    if change == "overall":
        value["all_checks_passed"] = False
    elif change == "missing_state":
        value["states"].pop()
    elif change == "endpoint":
        value["scientific_endpoints_included"] = True
    elif change == "admission":
        value["new_mismatch_campaign_admitted"] = True
    path = tmp_path / "record.json"
    path.write_text(json.dumps(value))
    contract["record"] = "record.json"
    contract["record_sha256"] = "0" * 64 if change == "digest" else build.sha256(path)
    monkeypatch.setattr(build, "WIKI_ROOT", tmp_path / "wiki")
    with pytest.raises(build.WikiError):
        build.check_mm3_readiness({"diagnostics": {"production_integration": contract}})
