from __future__ import annotations

import importlib.util
import json
import re
import shutil
from pathlib import Path

import pytest


WIKI = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("wiki_build", WIKI / "build.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_living_manuscript_contract_is_complete():
    report = MODULE.check()
    assert report["body_words"] >= 3500
    assert report["abstract_words"] >= 120
    assert report["citation_count"] >= 40
    assert report["bibliography_count"] >= 45


def test_split_retains_complete_paper_body():
    manifest = MODULE.load_manifest()
    text = (WIKI / manifest["canonical_page"]).read_text(encoding="utf-8")
    abstract, body = MODULE.split_manuscript(text)
    assert abstract.startswith("Magnetic-core models")
    assert body.startswith("# Introduction")
    assert "# Conclusion" in body


def test_document_links_are_revision_bound_and_figures_prefer_vectors():
    revision = "a" * 40
    rendered = MODULE.render_document_markdown(
        "[E16](../evidence/Evidence-Sources.md#e16)\n"
        "![Study](../assets/study-workflow.png)\n", revision
    )
    assert f"/blob/{revision}/wiki/evidence/Evidence-Sources.md#e16" in rendered
    assert "![Study](assets/study-workflow.pdf)" in rendered
    assert "../" not in rendered


def test_snapshot_inputs_bind_layout_bibliography_and_binary_assets():
    inputs = MODULE.check()["wiki_inputs"]
    for name in ("paper-layout.lua", "bibliography/IEEEtran.bst", "assets/study-workflow.pdf"):
        assert inputs[name] == MODULE.sha256(WIKI / name)


def test_ieee_projection_preserves_dois_and_adds_clickable_display():
    source = (WIKI / "bibliography/references.bib").read_text()
    rendered = MODULE.render_document_bibliography(source)
    dois = re.findall(r"\bdoi\s*=\s*\{([^{}]+)\}", source)
    assert len(dois) == 40
    assert MODULE.bibliography_keys(WIKI / "bibliography/references.bib") == MODULE.citation_keys(
        (WIKI / "manuscript/Full-Manuscript.md").read_text()
    )
    for doi in dois:
        assert f"doi={{{doi}}}" in rendered
        assert f"https://doi.org/{doi}" in rendered


def test_ieee_projection_refuses_to_overwrite_an_existing_note():
    with pytest.raises(MODULE.WikiError, match="already has a note"):
        MODULE.render_document_bibliography("@article{x, doi={10.1234/example}, note={original}}")


@pytest.fixture
def archived_document(tmp_path):
    names = ("main.pdf", "main.tex", "body.tex", "abstract.tex", "references.bib", "IEEEtran.bst", "main.bbl")
    for name in names:
        (tmp_path / name).write_text("fixture " + name)
    inputs = {"manuscript/Full-Manuscript.md": "a" * 64}
    record = {
        "schema_version": "magnetic-paper-snapshot/1.0",
        "document_release": {"kind": "journal", "name": "journal-test-2026", "source_direction": "wiki_to_document"},
        "source": {"wiki_commit": "a" * 40, "wiki_tree_sha256": MODULE.aggregate_digest(inputs)},
        "wiki_inputs": inputs,
        "generated": {name: MODULE.sha256(tmp_path / name) for name in names},
    }
    (tmp_path / "snapshot.json").write_text(json.dumps(record))
    return tmp_path


def test_archived_snapshot_verification_does_not_depend_on_current_wiki(archived_document):
    assert MODULE.verify_snapshot(archived_document)["verified_files"] == 7


def test_archived_snapshot_rejects_modified_document(archived_document):
    (archived_document / "main.pdf").write_text("changed")
    with pytest.raises(MODULE.WikiError, match="missing or changed"):
        MODULE.verify_snapshot(archived_document)


def test_archived_snapshot_rejects_manifest_escape(archived_document):
    path = archived_document / "snapshot.json"
    record = json.loads(path.read_text())
    record["generated"]["../outside.pdf"] = "a" * 64
    path.write_text(json.dumps(record))
    with pytest.raises(MODULE.WikiError, match="escapes"):
        MODULE.verify_snapshot(archived_document)


@pytest.mark.skipif(shutil.which("pandoc") is None, reason="optional document toolchain")
def test_two_column_export_has_bounded_floats_and_retains_caption(tmp_path):
    source = tmp_path / "body.md"
    source.write_text(
        "| Quantity | Result |\n|---|---|\n| Count | 5 |\n\n"
        "Table: Paired count.\n\n![Evidence diagram](assets/study-workflow.pdf)\n"
    )
    output = tmp_path / "body.tex"
    MODULE.run_pandoc(source, output)
    rendered = output.read_text()
    assert "\\begin{table*}" in rendered
    assert "\\caption{Paired count.}" in rendered
    assert "\\begin{figure*}" in rendered
    assert "\\textwidth" in rendered
    assert "longtable" not in rendered
    assert "\\endhead" not in rendered


def test_unresolved_citation_is_rejected():
    assert MODULE.citation_keys("statement [@missing2026]") == {"missing2026"}
    available = MODULE.bibliography_keys(WIKI / "bibliography" / "references.bib")
    assert "missing2026" not in available


def test_snapshot_refuses_existing_output(tmp_path: Path):
    output = tmp_path / "already-exists"
    output.mkdir()
    with pytest.raises(MODULE.WikiError, match="already exists"):
        MODULE.snapshot(output, "journal", "journal-example-2026")


@pytest.mark.parametrize(
    ("kind", "name"),
    [
        ("conference", "conference-example-2026"),
        ("journal", "journal-example-2026.1"),
    ],
)
def test_document_release_identity_accepts_named_submission_types(kind: str, name: str):
    MODULE.validate_document_release(kind, name)


@pytest.mark.parametrize(
    ("kind", "name"),
    [
        ("draft", "draft-example-2026"),
        ("conference", "journal-example-2026"),
        ("journal", "current_state"),
    ],
)
def test_document_release_identity_rejects_ambiguous_names(kind: str, name: str):
    with pytest.raises(MODULE.WikiError):
        MODULE.validate_document_release(kind, name)


def test_document_release_output_must_be_staged_outside_repository(monkeypatch):
    monkeypatch.setattr(MODULE, "require_snapshot_tools", lambda: ("pandoc", "latexmk"))
    output = WIKI.parent / "paper" / "journal-example-2026"
    with pytest.raises(MODULE.WikiError, match="outside the repository"):
        MODULE.snapshot(output, "journal", "journal-example-2026")


def test_scientific_job_registry_covers_declared_artifacts():
    evidence = json.loads(
        (WIKI / "evidence" / "results.json").read_text(encoding="utf-8")
    )
    assert len(evidence["scientific_jobs"]) == 13
    assert sum(job["artifacts"] for job in evidence["scientific_jobs"]) == 222
    assert evidence["campaign"]["result_artifact_count"] == 222
    assert evidence["sources"]["acquisition_record_set"]["record_count"] == 30


def test_comparator_explanation_is_source_bound():
    page = (WIKI / "results" / "Scientific-Job-Results.md").read_text(
        encoding="utf-8"
    )
    assert "Why EIG did not beat the strong comparators" in page
    assert "Evidence-Sources.md#e4" in page
    assert "Evidence-Sources.md#e5" in page
    for source_id in range(1, 15):
        assert f'<a id="e{source_id}"></a>' in (
            WIKI / "evidence" / "Evidence-Sources.md"
        ).read_text(encoding="utf-8")


def test_new_reader_index_covers_public_pages_and_evidence_lookup():
    manifest = MODULE.load_manifest()
    index_path = WIKI / manifest["wiki"]["index"]
    index = index_path.read_text(encoding="utf-8")
    targets = {
        str((index_path.parent / target).resolve().relative_to(WIKI))
        for target in MODULE.local_markdown_targets(index)
        if (index_path.parent / target).resolve().suffix == ".md"
    }
    expected = set(MODULE.declared_public_pages(manifest)) - {
        manifest["wiki"]["index"],
        manifest["wiki"]["sidebar"],
    }
    assert expected <= targets
    assert "Verify a number" in index
    assert "E1--E16" in index


def test_sparse_mixing_diagnostic_is_hash_bound_and_non_admitting():
    report = MODULE.check()
    assert report["sparse_mixing_manifest_sha256"] == (
        "9577a89b64207f17f241c52f68316eb2487a1ec31afbf3f9d77c45ea366e1a6e"
    )
    manifest = MODULE.load_manifest()
    contract = manifest["diagnostics"]["sparse_mixing"]
    descriptor = json.loads(
        (WIKI.parent / contract["asset_descriptor"]).read_text(encoding="utf-8")
    )
    assert descriptor["scope"]["changes_mm2_admission"] is False
    assert descriptor["validation"]["validated_task_count"] == 18


@pytest.fixture
def sparse_pilot_contract(tmp_path, monkeypatch):
    monkeypatch.setattr(MODULE, "WIKI_ROOT", tmp_path / "wiki")
    pilot = {
        "schema_version": "magcore-sparse-mixing-pilot-manifest/1.0",
        "record_class": "endpoint_free_sampler_pilot_manifest", "protocol_id": "SparseMix-Pilot-1",
        "matrix": {"expected_task_count": 24, "validated_task_count": 24, "artifact_count": 72},
        "disclosure": {"scientific_endpoints_included": False, "automatic_admission": False,
                       "claim_bearing_result": False, "retroactive_mm2_admission_allowed": False,
                       "confirmatory_sampler_validation": False},
        "method_summaries": {state: {"stretch": {"independent_ensemble_count": 4}}
                             for state in ("n3", "n4")},
    }
    pilot_path, decision_path = tmp_path / "manifest.json", tmp_path / "decision.json"
    pilot_path.write_text(json.dumps(pilot), encoding="utf-8")
    decision = {"schema_version": "magcore-sparse-pilot-selection/1.0",
                "complete_matrix": True, "selected_arm": "stretch",
                "pilot_manifest": "manifest.json", "pilot_manifest_sha256": MODULE.sha256(pilot_path)}
    decision_path.write_text(json.dumps(decision), encoding="utf-8")
    contract = {"manifest": "manifest.json", "manifest_sha256": MODULE.sha256(pilot_path),
                "decision": "decision.json", "decision_sha256": MODULE.sha256(decision_path)}
    return contract, pilot_path, decision_path


def test_sparse_pilot_contract_binds_both_hashes(sparse_pilot_contract):
    contract, pilot_path, _ = sparse_pilot_contract
    report = MODULE.check_sparse_pilot_contract(contract)
    assert report["sparse_pilot_manifest_sha256"] == contract["manifest_sha256"]
    pilot_path.write_text("{}", encoding="utf-8")
    with pytest.raises(MODULE.WikiError, match="SHA-256 mismatch"):
        MODULE.check_sparse_pilot_contract(contract)


@pytest.mark.parametrize("mutation", ["matrix", "disclosure", "missing_state", "schema"])
def test_sparse_pilot_invalid_evidence_fails_even_with_updated_hash(sparse_pilot_contract, mutation):
    contract, pilot_path, decision_path = sparse_pilot_contract
    pilot = json.loads(pilot_path.read_text())
    if mutation == "matrix":
        pilot["matrix"]["validated_task_count"] = 23
    elif mutation == "disclosure":
        pilot["disclosure"]["automatic_admission"] = True
    elif mutation == "missing_state":
        del pilot["method_summaries"]["n4"]
    else:
        pilot["schema_version"] = "unknown"
    pilot_path.write_text(json.dumps(pilot), encoding="utf-8")
    contract["manifest_sha256"] = MODULE.sha256(pilot_path)
    decision = json.loads(decision_path.read_text())
    decision["pilot_manifest_sha256"] = contract["manifest_sha256"]
    decision_path.write_text(json.dumps(decision), encoding="utf-8")
    contract["decision_sha256"] = MODULE.sha256(decision_path)
    with pytest.raises(MODULE.WikiError):
        MODULE.check_sparse_pilot_contract(contract)


@pytest.mark.parametrize("field,value", [("selected_arm", "invented"),
    ("pilot_manifest", "another.json"), ("pilot_manifest_sha256", "0" * 64),
    ("schema_version", "unknown")])
def test_sparse_pilot_decision_must_bind_manifest(sparse_pilot_contract, field, value):
    contract, _, decision_path = sparse_pilot_contract
    decision = json.loads(decision_path.read_text())
    decision[field] = value
    decision_path.write_text(json.dumps(decision), encoding="utf-8")
    contract["decision_sha256"] = MODULE.sha256(decision_path)
    with pytest.raises(MODULE.WikiError):
        MODULE.check_sparse_pilot_contract(contract)


@pytest.fixture
def sparse_v2_contract(tmp_path, monkeypatch):
    monkeypatch.setattr(MODULE, "WIKI_ROOT", tmp_path / "wiki")
    config_path, result_path = tmp_path / "config.toml", tmp_path / "manifest.json"
    config_path.write_text('''schema_version = "magcore-sparse-mixing-v2/1.0"
protocol_id = "SparseMix-2"
status = "preregistered_before_confirmatory_chains"
diagnostic_only = true
retroactive_mm2_admission_allowed = false
parent_config_sha256 = "parent"
pilot_decision_sha256 = "decision"
[diagnostics]
minimum_steps_per_tau = 50
''', encoding="utf-8")
    tasks = [{"task_id": f"{state}_{rep}", "target_id": state}
             for state in ("n3", "n4") for rep in range(8)]
    result = {
        "schema_version": "magcore-sparse-mixing-v2-manifest/1.0",
        "record_class": "endpoint_free_confirmatory_sampler_validation_manifest",
        "protocol_id": "SparseMix-2", "config_sha256": MODULE.sha256(config_path),
        "parent_config_sha256": "parent", "pilot_decision_sha256": "decision",
        "registered_criteria": {"minimum_steps_per_tau": 50},
        "matrix": {"expected_task_count": 16, "validated_task_count": 16, "artifact_count": 48},
        "tasks": tasks, "artifacts": [{"task_id": r["task_id"]} for r in tasks],
        "disclosure": {"scientific_endpoints_included": False, "retroactive_mm2_admission_allowed": False,
                       "model_mismatch_campaign_admitted": False, "confirmatory_sampler_validation": True},
        "classifications": {state: {"criteria_passed": True, "classification": "mixing_supported",
                                    "independent_ensemble_count": 8, "reason_codes": []}
                            for state in ("n3", "n4")},
        "both_states_pass": True,
    }
    result_path.write_text(json.dumps(result), encoding="utf-8")
    contract = {"manifest": "manifest.json", "manifest_sha256": MODULE.sha256(result_path),
                "config": "config.toml", "config_sha256": MODULE.sha256(config_path)}
    return contract, result_path, config_path


def test_sparse_v2_validated_completion_is_hash_bound(sparse_v2_contract):
    contract, _, config_path = sparse_v2_contract
    report = MODULE.check_sparse_mixing_v2_contract(contract)
    assert report["sparse_mixing_v2_both_states_pass"] is True
    config_path.write_text("", encoding="utf-8")
    with pytest.raises(MODULE.WikiError, match="SHA-256 mismatch"):
        MODULE.check_sparse_mixing_v2_contract(contract)


@pytest.mark.parametrize("mutation", ["matrix", "false_pass", "wrong_count", "reason",
    "config", "disclosure", "duplicate", "non_boolean"])
def test_sparse_v2_contradictory_claims_are_rejected(sparse_v2_contract, mutation):
    contract, path, _ = sparse_v2_contract
    result = json.loads(path.read_text())
    if mutation == "matrix":
        result["matrix"]["validated_task_count"] = 15
    elif mutation == "false_pass":
        result["classifications"]["n4"].update(criteria_passed=False,
            classification="mixing_not_supported", reason_codes=["tau_instability"])
    elif mutation == "wrong_count":
        result["classifications"]["n4"]["independent_ensemble_count"] = 7
    elif mutation == "reason":
        result["classifications"]["n4"]["reason_codes"] = ["tau_instability"]
    elif mutation == "config":
        result["config_sha256"] = "0" * 64
    elif mutation == "disclosure":
        result["disclosure"]["retroactive_mm2_admission_allowed"] = True
    elif mutation == "duplicate":
        result["tasks"][-1] = result["tasks"][0]
    else:
        result["both_states_pass"] = 1
    path.write_text(json.dumps(result), encoding="utf-8")
    contract["manifest_sha256"] = MODULE.sha256(path)
    with pytest.raises(MODULE.WikiError):
        MODULE.check_sparse_mixing_v2_contract(contract)


def test_sparse_v2_consistent_nonpass_remains_publishable(sparse_v2_contract):
    contract, path, _ = sparse_v2_contract
    result = json.loads(path.read_text())
    result["classifications"]["n4"].update(criteria_passed=False,
        classification="mixing_not_supported", reason_codes=["tau_instability"])
    result["both_states_pass"] = False
    path.write_text(json.dumps(result), encoding="utf-8")
    contract["manifest_sha256"] = MODULE.sha256(path)
    assert MODULE.check_sparse_mixing_v2_contract(contract)["sparse_mixing_v2_both_states_pass"] is False


def test_acquisition_figure_is_bound_to_evidence_projection():
    evidence = WIKI / "evidence" / "results.json"
    manifest = json.loads(
        (WIKI / "assets" / "acquisition-diagnostics.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["evidence_projection_sha256"] == MODULE.sha256(evidence)
    assert manifest["figure_sha256"] == MODULE.sha256(
        WIKI / "assets" / manifest["figure"]
    )
    assert manifest["evidence_sources"] == ["E4", "E5"]


@pytest.mark.parametrize(
    "text",
    [
        "token gh" + "p_ABCDEFGHIJKLMNOPQRSTUVWXYZ123456",
        "generated by "
        + "".join(chr(value) for value in (67, 104, 97, 116, 71, 80, 84)),
        "/" + "users/example/private/project",
        "Current Presen" + "tation note",
        "The current manuscript preser" + "ves the old layout",
        "a one-way mir" + "ror of the source",
        "This wiki is the liv" + "ing manuscript",
    ],
)
def test_public_disclosure_patterns_are_detected(text: str):
    assert any(pattern.search(text) for pattern in MODULE.BANNED_PUBLIC_PATTERNS.values())


def test_repository_landing_page_is_evidence_led():
    readme = (WIKI.parent / "README.md").read_text(encoding="utf-8")
    assert readme == MODULE.render_repository_readme()
    assert "## Why this study" in readme
    assert "## Contributions" in readme
    assert "## Main findings" in readme
    assert "wiki/evidence/Evidence-Sources.md#e4" in readme
    assert "wiki/evidence/Evidence-Sources.md#e5" in readme
    assert "wiki/evidence/Evidence-Sources.md#e7" in readme
    assert "wiki/evidence/Evidence-Sources.md#e9" in readme
    assert "20260817T072230Z_401e3030fe13" in readme
    assert MODULE.sha256(WIKI.parent / "README.md") == MODULE.check()[
        "repository_readme_sha256"
    ]


def test_public_wiki_projection_is_flat_and_rewrites_links():
    manifest = MODULE.load_manifest()
    pages = MODULE.declared_public_pages(manifest)
    assert len({Path(page).name for page in pages}) == len(pages)
    rendered = MODULE.render_public_wiki_page(
        "Home.md", manifest, "1" * 40
    )
    assert not rendered.startswith("---")
    assert "](Evidence-Sources.md#e4)" in rendered
    assert "](Project-Status.md)" in rendered
    assert "wiki/evidence/Evidence-Sources.md" not in rendered


def test_public_wiki_staging_refuses_existing_output(tmp_path: Path):
    output = tmp_path / "existing"
    output.mkdir()
    with pytest.raises(MODULE.WikiError, match="already exists"):
        MODULE.stage_public_wiki(output)


def test_staged_wiki_validation_rejects_broken_anchor(tmp_path: Path):
    (tmp_path / "Home.md").write_text(
        "# Home\n\n[Missing](Results.md#missing)\n", encoding="utf-8"
    )
    (tmp_path / "Results.md").write_text("# Results\n", encoding="utf-8")
    with pytest.raises(MODULE.WikiError, match="broken staged Wiki anchor"):
        MODULE.validate_public_wiki_tree(tmp_path)


def test_only_full_manuscript_is_a_paper_source():
    manifest = MODULE.load_manifest()
    paper_sources = []
    for page in MODULE.declared_public_pages(manifest):
        text = (WIKI / page).read_text(encoding="utf-8")
        if re.search(r"(?m)^paper_source:\s*true\s*$", text):
            paper_sources.append(page)
    assert paper_sources == [manifest["canonical_page"]]


def test_ci_validates_wiki_without_rendering_a_document_snapshot():
    workflow = (WIKI.parent / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    assert "python wiki/build.py check" in workflow
    assert "python wiki/build.py stage-wiki" in workflow
    assert "pytest -q wiki/tests" in workflow
    assert "latexmk" not in workflow
    assert "paper/current_state/source" not in workflow
    assert "20260812T035654Z_a0703698ace9" not in workflow
    assert "paper/current_state/results.lock.yaml" in workflow


def test_compatibility_docs_delegate_claims_and_protocol_to_wiki():
    for relative in ("docs/CLAIMS_EVIDENCE.md", "docs/EXPERIMENT_PROTOCOL.md"):
        text = (WIKI.parent / relative).read_text(encoding="utf-8")
        assert "../wiki/" in text
        assert not re.search(r"20\d{6}T\d{6}Z_[0-9a-f]{12}", text)
