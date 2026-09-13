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
