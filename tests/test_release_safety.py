"""Cheap login-node release gates for the Magnetic-only pipeline.

These tests never sample, fit, generate figures, or invoke the scheduler.  They
exercise fail-closed boundaries and immutable metadata only.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from magcore_calib.results import PARAMETERS, SCHEMA_VERSION, provenance, validate_result
from magcore_calib.study_plan import load_study_plan


ROOT = Path(__file__).resolve().parents[1]
_CONFIGURED_DATA_ROOT = os.environ.get("MAGCORE_DATA_ROOT")
EXPERIMENTS = sorted((ROOT / "experiments").glob("*.py"))
HEAVY_ARGUMENTS = {
    "aggregate_eig_convergence.py": ["--run-dir", "/does/not/exist", "--out", "/tmp/never.json"],
    "aggregate_results.py": ["--run-dir", "/does/not/exist", "--out", "/tmp/never.json"],
    "d5_identifiability_demo.py": ["--out", "/tmp/never.json"],
    "eig_efficiency.py": [
        "--seed", "42", "--selection-file", "/does/not/exist",
        "--config", "/does/not/exist",
        "--out", "/tmp/never.json",
    ],
    "eig_convergence_downstream.py": [
        "--seed", "7200", "--selection", "/does/not/exist", "--workers", "1",
        "--max-meas", "25", "--n-walkers", "48", "--n-steps", "5000",
        "--burn", "1000", "--out", "/tmp/never.json",
    ],
    "eig_convergence_scores.py": [
        "--state", "/does/not/exist", "--samples", "/does/not/exist",
        "--n-outer", "100", "--n-inner", "50", "--replicates", "20",
        "--namespace", "grid", "--out", "/tmp/never.json",
    ],
    "eig_convergence_states.py": [
        "--seed", "7100", "--n-observations", "2", "--n-walkers", "48",
        "--n-steps", "5000", "--burn", "1000", "--samples-out", "/tmp/x.npz",
        "--out", "/tmp/never.json",
    ],
    "finalize_eig_convergence.py": [
        "--run-dir", "/does/not/exist", "--out", "/tmp/never.json",
    ],
    "eig_real.py": [
        "--material", "N95", "--source", "LEA_MTB", "--out", "/tmp/never.json",
    ],
    "lot_variation.py": ["--seed", "42", "--out", "/tmp/never.json"],
    "posterior_recovery.py": ["--seed", "42", "--out", "/tmp/never.json"],
    "real_data_pcv.py": ["--material", "N95", "--out", "/tmp/never.json"],
    "real_data_recovery.py": [
        "--material", "N95", "--source", "LEA_MTB", "--out", "/tmp/never",
    ],
}


def _login_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.pop("SLURM_JOB_ID", None)
    environment.pop("SLURM_JOB_NODELIST", None)
    environment["PYTHONPATH"] = str(ROOT / "src")
    return environment


@pytest.mark.parametrize("script", EXPERIMENTS, ids=lambda path: path.name)
def test_experiment_help_is_login_safe(script: Path):
    completed = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=ROOT,
        env=_login_environment(),
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert completed.returncode == 0, completed.stderr
    assert "usage:" in completed.stdout.lower()


@pytest.mark.parametrize("script", EXPERIMENTS, ids=lambda path: path.name)
def test_every_experiment_rejects_execution_outside_slurm(script: Path):
    assert script.name in HEAVY_ARGUMENTS, f"classify new experiment {script.name} explicitly"
    completed = subprocess.run(
        [sys.executable, str(script), *HEAVY_ARGUMENTS[script.name]],
        cwd=ROOT,
        env=_login_environment(),
        capture_output=True,
        text=True,
        timeout=15,
    )
    output = (completed.stdout + completed.stderr).lower()
    assert completed.returncode != 0
    assert "slurm" in output, output


def test_manifest_hashes_are_complete_consistent_and_match_inputs():
    manifest = (ROOT / "data" / "manifest.yaml").read_text(encoding="utf-8")
    manifest_entries = re.findall(
        r"(?m)^    path: (\S+)\n    sha256: ([0-9a-f]{64})$", manifest
    )
    checksum_entries = []
    for line in (ROOT / "data" / "checksums.sha256").read_text(encoding="utf-8").splitlines():
        digest, relative = line.split(maxsplit=1)
        checksum_entries.append((relative.strip(), digest))

    assert manifest_entries
    assert dict(manifest_entries) == dict(checksum_entries)
    assert len(dict(manifest_entries)) == len(manifest_entries), "duplicate manifest input path"
    staged_prefix = Path("data/external/materialdatabase/data")
    missing = []
    for relative, expected in manifest_entries:
        relative_path = Path(relative)
        if _CONFIGURED_DATA_ROOT:
            path = Path(_CONFIGURED_DATA_ROOT).resolve() / relative_path.relative_to(
                staged_prefix
            )
        else:
            path = ROOT / relative_path
        if not path.is_file():
            missing.append(relative)
            continue
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected
    if _CONFIGURED_DATA_ROOT:
        assert not missing, f"configured dataset is incomplete: {missing}"


def _canonical_record() -> dict:
    digest = "a" * 64
    return {
        "schema_version": SCHEMA_VERSION,
        "case_study": "magnetic_core",
        "run_id": "release-test",
        "provenance": {
            "started_at_utc": "2026-08-05T00:00:00+00:00",
            "ended_at_utc": "2026-08-05T00:01:00+00:00",
            "git_commit": "b" * 40,
            "seed": 42,
            "command": ["posterior_recovery", "--seed", "42"],
            "configuration_sha256": digest,
            "data_sha256": {"N95.csv": digest},
            "dependency_lock_sha256": digest,
            "python": "3.12.0",
            "slurm": {
                "job_id": "123",
                "array_job_id": "123",
                "array_task_id": "0",
                "node_list": "node001",
                "partition": "nextgen",
            },
        },
        "data": {"temperature_c": 25.0},
        "model": {"temperature_mode": "isothermal"},
        "sampler": {"method": "emcee"},
        "posterior": {name: {"median": 1.0} for name in PARAMETERS},
        "predictive": {},
        "design": {},
        "claim_context": {"oracle_initialized": False},
        "validity": {"convergence_valid": True},
    }


def test_canonical_result_accepts_complete_magnetic_record():
    validate_result(_canonical_record())


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (lambda r: r["provenance"]["slurm"].update(node_list=""), "SLURM"),
        (lambda r: r["provenance"].update(data_sha256={}), "data"),
        (lambda r: r["provenance"].update(configuration_sha256="not-a-hash"), "hash"),
        (lambda r: r.update(case_study="unsupported_case"), "case study"),
        (lambda r: r["claim_context"].update(oracle_initialized=True), "oracle"),
    ],
)
def test_canonical_result_validation_fails_closed(mutator, message):
    record = _canonical_record()
    mutator(record)
    with pytest.raises(ValueError, match=message):
        validate_result(record)


def test_provenance_hashes_every_declared_input(tmp_path: Path, monkeypatch):
    data_a = tmp_path / "a.csv"
    data_b = tmp_path / "b.csv"
    data_a.write_text("a\n", encoding="utf-8")
    data_b.write_text("b\n", encoding="utf-8")
    monkeypatch.setenv("SLURM_JOB_ID", "123")
    monkeypatch.setenv("SLURM_JOB_NODELIST", "node001")
    record = provenance(seed=7, command=["experiment", "--seed", "7"], data_paths=[data_a, data_b])
    assert record["data_sha256"] == {
        str(data_a): hashlib.sha256(b"a\n").hexdigest(),
        str(data_b): hashlib.sha256(b"b\n").hexdigest(),
    }


def test_provenance_binds_submitted_revision_configuration_and_lock(tmp_path: Path, monkeypatch):
    digest = "c" * 64
    revision = "d" * 40
    project_root = Path(__file__).resolve().parents[1]
    lock_digest = hashlib.sha256(
        (project_root / "configs" / "dependencies.lock").read_bytes()
    ).hexdigest()
    monkeypatch.setenv("SLURM_JOB_ID", "123")
    monkeypatch.setenv("SLURM_JOB_NODELIST", "node001")
    monkeypatch.setenv("MAGCORE_GIT_REVISION", revision)
    monkeypatch.setenv("MAGCORE_CONFIG_SHA256", digest)
    monkeypatch.setenv("MAGCORE_DEPENDENCY_LOCK_SHA256", lock_digest)
    record = provenance(seed=7, command=["experiment", "--seed", "7"])
    assert record["git_commit"] == revision
    assert record["configuration_sha256"] == digest
    assert record["dependency_lock_sha256"] == lock_digest
    assert len(record["command_sha256"]) == 64


def _load_validate_run_module():
    path = ROOT / "scripts" / "validate_run.py"
    spec = importlib.util.spec_from_file_location("validate_run_for_tests", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_freeze_is_immutable_and_fails_closed(tmp_path: Path, monkeypatch):
    module = _load_validate_run_module()
    isolated_project = tmp_path / "project"
    (isolated_project / "results" / "frozen").mkdir(parents=True)
    (isolated_project / "paper").mkdir()
    monkeypatch.setattr(module, "PROJECT_ROOT", isolated_project)
    # Production freezes are read-only. Avoid leaving pytest's temporary tree
    # deliberately undeletable while retaining all immutability semantics.
    monkeypatch.setattr(Path, "chmod", lambda self, mode: None)
    run_dir = tmp_path / "20260806T120000Z_aaaaaaaaaaaa"
    for directory in ("status", "results", "summary", "figures", "freeze", "provenance", "logs"):
        (run_dir / directory).mkdir(parents=True, exist_ok=True)
    (run_dir / "provenance" / "jobs").mkdir()
    for stage, tasks in module.EXPECTED_TASKS.items():
        for task in tasks:
            (run_dir / "status" / f"{stage}_{task}.done").write_text("{}\n", encoding="utf-8")
    (run_dir / "results" / "artifact.txt").write_text("magnetic only\n", encoding="utf-8")
    monkeypatch.setenv("SLURM_JOB_ID", "123")
    monkeypatch.setenv("SLURM_JOB_NODELIST", "node001")
    monkeypatch.setenv("SLURM_JOB_PARTITION", "nextgen")
    monkeypatch.setenv("MAGCORE_GIT_REVISION", "b" * 40)
    monkeypatch.setenv("MAGCORE_SOURCE_STATUS_SHA256", "1" * 64)
    monkeypatch.setenv("MAGCORE_SOURCE_ARCHIVE_SHA256", "2" * 64)
    monkeypatch.setenv("MAGCORE_CONFIG_SHA256", "3" * 64)
    monkeypatch.setenv("MAGCORE_DATA_MANIFEST_SHA256", "4" * 64)
    monkeypatch.setenv("MAGCORE_DEPENDENCY_LOCK_SHA256", "5" * 64)
    monkeypatch.setenv("MAGCORE_CONFIG_MODE", "test_snapshot")
    monkeypatch.setenv("MAGCORE_SUBMIT_ACCOUNT", "pgs0407")
    monkeypatch.setenv("MAGCORE_SUBMIT_PARTITION", "nextgen")
    audit_payload = {
        "expected_task_count": sum(map(len, module.EXPECTED_TASKS.values())),
        "expected_result_artifact_count": 1,
        "tasks_without_result_artifacts": ["smoke_0"],
        "git_revision": "b" * 40,
        "source_status_sha256": "1" * 64,
        "source_archive_sha256": "2" * 64,
        "configuration_sha256": "3" * 64,
        "configuration_mode": "test_snapshot",
        "data_manifest_sha256": "4" * 64,
        "dependency_lock_sha256": "5" * 64,
        "measured_exclusion_policy": module.MEASURED_EXCLUSION_POLICY,
        "record_class_counts": {"supporting_artifact": 1},
        "artifacts": [],
    }
    monkeypatch.setattr(module, "audit", lambda _run_dir: audit_payload)
    (run_dir / "provenance" / "jobs" / "freeze_0.json.partial").write_text(
        '{"job_id":"123"}\n', encoding="utf-8"
    )
    monkeypatch.setattr(
        sys, "argv", ["validate_run.py", "--run-dir", str(run_dir), "--mode", "aggregate"]
    )
    module.main()
    monkeypatch.setattr(sys, "argv", ["validate_run.py", "--run-dir", str(run_dir), "--mode", "freeze"])
    module.main()
    release = json.loads((run_dir / "freeze" / "release.json").read_text(encoding="utf-8"))
    frozen_manifest = Path(release["release_dir"]) / "manifest.json"
    assert release["manifest_sha256"] == hashlib.sha256(frozen_manifest.read_bytes()).hexdigest()
    manifest = json.loads(frozen_manifest.read_text(encoding="utf-8"))
    assert manifest["git_revision"] == "b" * 40
    assert manifest["source_status_sha256"] == "1" * 64
    assert all("partial" not in entry["path"] for entry in manifest["files"])
    assert (Path(release["release_dir"]) / "provenance" / "jobs" / "freeze_0.json").is_file()
    module.read_lock(run_dir.name)
    with pytest.raises((FileExistsError, RuntimeError), match="exist|immutable|frozen|refus"):
        module.main()


def test_paper_job_requires_locked_release_and_never_uses_current_pointer():
    source = (ROOT / "slurm" / "95_paper.sbatch").read_text(encoding="utf-8")
    assert "validate_run.py" in source
    assert "--mode verify-lock" in source
    assert "results/CURRENT" not in source
    assert "freeze/release.json" in source
    assert 'SUMMARY="$RELEASE_DIR/tables/paper_summary.json"' in source
    assert "20260812T035654Z_a0703698ace9" not in source


def test_paper_job_validates_bibliography_from_staged_build_directory():
    source = (ROOT / "slurm" / "95_paper.sbatch").read_text(encoding="utf-8")
    assert 'BBL="$BUILD_DIR/main.bbl"' in source
    assert 'BBL="$(dirname "$MAIN_TEX")/main.bbl"' not in source


def test_final_job_replaces_stale_terminal_markers_before_retry():
    source = (ROOT / "slurm" / "99_finalize.sbatch").read_text(encoding="utf-8")
    cleanup = 'rm -f "$MAGCORE_RUN_DIR/status/SUCCESS" "$MAGCORE_RUN_DIR/status/FAILED"'
    assert cleanup in source
    assert source.index(cleanup) < source.index('touch "$MAGCORE_RUN_DIR/status/SUCCESS"')


def test_figure_job_regenerates_and_verifies_full_figures_from_frozen_summary():
    source = (ROOT / "slurm" / "90_figures.sbatch").read_text(encoding="utf-8")
    assert "freeze/release.json" in source
    assert 'SUMMARY="$RELEASE_DIR/tables/paper_summary.json"' in source
    assert "generate_current_paper_figures.py\" generate" in source
    assert source.count("generate_current_paper_figures.py\" verify") == 2
    assert 'PROJECT_FULL_FIGURE_DIR="$MAGCORE_PROJECT_ROOT/' in source
    assert "full_figure_manifest.json" in source


def test_all_shell_entry_points_pass_bash_syntax_check():
    scripts = sorted((ROOT / "scripts").glob("*.sh"))
    scripts += sorted((ROOT / "slurm").glob("*.sh"))
    scripts += sorted((ROOT / "slurm").glob("*.sbatch"))
    assert scripts
    for script in scripts:
        completed = subprocess.run(
            ["bash", "-n", str(script)], capture_output=True, text=True, timeout=10
        )
        assert completed.returncode == 0, f"{script.name}: {completed.stderr}"


def test_public_markdown_local_links_exist():
    markdown_files = sorted(ROOT.rglob("*.md"))
    assert markdown_files
    for source in markdown_files:
        for raw_target in re.findall(r"\[[^]]+\]\(([^)]+)\)", source.read_text("utf-8")):
            target = raw_target.strip().strip("<>").split("#", 1)[0]
            if not target or re.match(r"^[a-z][a-z0-9+.-]*:", target, re.IGNORECASE):
                continue
            resolved = (source.parent / target).resolve()
            assert resolved.exists(), f"broken link in {source.relative_to(ROOT)}: {raw_target}"


def test_current_and_historical_papers_have_explicit_provenance_boundaries():
    current = ROOT / "paper" / "current_state"
    snapshot = ROOT / "paper" / "conference_snapshot"
    current_source = (current / "source" / "main.tex").read_text(encoding="utf-8")
    current_readme = (current / "README.md").read_text(encoding="utf-8")
    snapshot_readme = (snapshot / "README.md").read_text(
        encoding="utf-8"
    )

    for author in ("Viet Hoang Duong", "Viet Huy Duong", "Lun-Min Shih"):
        assert author in current_source
    assert "20260812T035654Z_a0703698ace9" in current_readme
    assert (snapshot / "manuscript.pdf").is_file()
    assert "05588315a56e6c8460d43f8775d78d367953bde930e3c411c909bf7b8d700db2" in snapshot_readme
    assert "20260806T112202Z_9a37bcc67637" in snapshot_readme
    assert (snapshot / "CLAIMS_EVIDENCE.md").is_file()
    assert (snapshot / "ERRATA.md").is_file()


def test_conference_snapshot_lock_and_evidence_checksums_are_exact():
    snapshot = ROOT / "paper" / "conference_snapshot"
    historical = ROOT / "results" / "historical" / "20260806T112202Z_9a37bcc67637"
    lock = (snapshot / "results.lock.yaml").read_text(encoding="utf-8")

    pdf_digest = hashlib.sha256((snapshot / "manuscript.pdf").read_bytes()).hexdigest()
    assert pdf_digest == "05588315a56e6c8460d43f8775d78d367953bde930e3c411c909bf7b8d700db2"
    assert f"snapshot_pdf_sha256: {pdf_digest}" in lock
    assert "historical_release_id: 20260806T112202Z_9a37bcc67637" in lock

    checksum_file = historical / "checksums.sha256"
    checksum_digest = hashlib.sha256(checksum_file.read_bytes()).hexdigest()
    assert f"checksums_sha256: {checksum_digest}" in lock
    for line in checksum_file.read_text(encoding="utf-8").splitlines():
        expected, relative = line.split(maxsplit=1)
        path = historical / relative.strip()
        assert path.is_file(), relative
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected

    manifest_path = historical / "manifest.json"
    manifest_digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    assert f"manifest_sha256: {manifest_digest}" in lock
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    declared = {entry["path"]: entry for entry in manifest["artifacts"]}
    assert set(declared) == {
        line.split(maxsplit=1)[1].strip()
        for line in checksum_file.read_text(encoding="utf-8").splitlines()
    }
    for relative, entry in declared.items():
        path = historical / relative
        assert path.stat().st_size == entry["bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]

    for key, filename in (
        ("claim_ledger_sha256", "claims-evidence.json"),
        ("claim_register_sha256", "CLAIMS_EVIDENCE.md"),
        ("errata_sha256", "ERRATA.md"),
        ("bibliography_sha256", "references.bib"),
    ):
        digest = hashlib.sha256((snapshot / filename).read_bytes()).hexdigest()
        assert f"{key}: {digest}" in lock


def test_conference_snapshot_quantitative_claims_match_historical_work():
    historical = ROOT / "results" / "historical" / "20260806T112202Z_9a37bcc67637"
    summary = json.loads((historical / "tables" / "paper_summary.json").read_text("utf-8"))
    protocol = json.loads((historical / "protocol" / "protocol_audit.json").read_text("utf-8"))
    config = tomllib.loads((historical / "protocol" / "default.toml").read_text("utf-8"))

    assert summary["release_id"] == "20260806T112202Z_9a37bcc67637"
    assert summary["eig"]["seeds"] == [42, 43, 44, 45, 46]
    assert summary["eig"]["counts"] == [5, 6, 5, 5, 6]
    assert summary["eig"]["uniform_counts"] == [9, 9, 9, 9, 9]
    assert summary["eig"]["wins"] == 5
    paired = [
        100.0 * (baseline - eig) / baseline
        for eig, baseline in zip(summary["eig"]["counts"], summary["eig"]["uniform_counts"])
    ]
    assert sum(paired) / len(paired) == pytest.approx(40.0)
    assert summary["eig"]["mean_reduction_pct"] == pytest.approx(40.0)

    recovery = summary["recovery"]
    assert [round(recovery[name]["median_pct"], 2) for name in (
        "k", "alpha", "beta", "mu_s", "f_rel_hz", "alpha_cc"
    )] == [5.85, 0.27, 0.36, 0.38, 0.87, 0.62]
    assert sum(item["interval_inclusion_count"] for item in recovery.values()) == 28
    assert summary["recovery_interval_inclusion_total"] == 28
    assert summary["fisher"]["rank"] == 6
    assert summary["fisher"]["condition_number"] == pytest.approx(23474.30194565397)

    assert config["sampler"] == {"n_walkers": 48, "n_steps": 5000, "burn": 1000}
    assert config["eig"] == {"n_outer": 300, "n_inner": 100, "max_measurements": 25}
    assert config["stop_rule"] == {
        "pcv_ci_half_width_pct": 8.0,
        "lm_ci_half_width_pct": 5.0,
    }
    assert protocol["synthetic_protocol"]["common_random_outcomes_between_policies"] is True
    assert protocol["synthetic_protocol"]["prior_centered_on_realized_truth"] is False
    assert protocol["synthetic_protocol"]["sampler_initialized_at_realized_truth"] is False
    assert protocol["audit_findings"]["candidate_order_invariance_claim_supported"] is False
    assert protocol["audit_findings"]["stopping_interval_includes_observation_noise"] is False


def test_conference_claim_ledger_is_complete_and_all_evidence_paths_exist():
    snapshot = ROOT / "paper" / "conference_snapshot"
    ledger = json.loads((snapshot / "claims-evidence.json").read_text(encoding="utf-8"))
    claims = {claim["id"]: claim for claim in ledger["claims"]}
    required = {
        "CS-MOD-01", "CS-MOD-02", "CS-SCOPE-01", "CS-STAT-01", "CS-STAT-02",
        "CS-MCMC-01", "CS-FISH-METHOD-01", "CS-EIG-METHOD-01", "CS-EIG-SEED-01",
        "CS-SEQ-01", "CS-ORACLE-01", "CS-STOP-01", "CS-REP-01",
        "CS-RES-FISH-01", "CS-RES-REC-01", "CS-RES-EIG-01", "CS-RES-MU-01",
        "CS-RES-MU-EXCL-01", "CS-RES-PCV-01", "CS-INT-01", "CS-LIM-01",
        "CS-LIM-02", "CS-LIM-03", "CS-LIT-01-05",
    }
    assert set(claims) == required
    assert claims["CS-EIG-SEED-01"]["status"] == "contradicted"
    assert claims["CS-SCOPE-01"]["status"] == "corrected"
    assert claims["CS-STOP-01"]["status"] == "qualified"
    assert claims["CS-RES-EIG-01"]["currency"] == "superseded_by_current_30_seed_benchmark"

    for claim in claims.values():
        assert claim["evidence"], claim["id"]
        for item in claim["evidence"]:
            path = (snapshot / item["path"]).resolve()
            assert path.is_relative_to(ROOT), f"evidence escapes repository: {item['path']}"
            assert path.is_file(), f"missing evidence for {claim['id']}: {item['path']}"


def test_historical_public_bundle_contains_no_machine_or_credential_material():
    historical = ROOT / "results" / "historical" / "20260806T112202Z_9a37bcc67637"
    machine_root = "/" + "users" + "/"
    account_fragments = ("PGS" + "0407", "bin" + "ben14")
    token_prefix = "gh" + "p_"
    forbidden = re.compile(
        rf"{re.escape(machine_root)}|{'|'.join(account_fragments)}|"
        rf"{token_prefix}[A-Za-z0-9]+|PRIVATE KEY|"
        r"node_list|job_id|array_job_id|SLURM_|source-tree\.tar|run\.env|git-status",
        re.IGNORECASE,
    )
    for path in historical.rglob("*"):
        if path.is_file() and path.suffix.lower() not in {".pdf"}:
            assert not forbidden.search(path.read_text(encoding="utf-8")), path.relative_to(ROOT)


def test_public_paper_layout_has_exactly_two_version_directories():
    paper_root = ROOT / "paper"
    directories = {path.name for path in paper_root.iterdir() if path.is_dir()}
    assert directories == {"current_state", "conference_snapshot"}
    assert not any(paper_root.glob("main.*"))


def test_current_source_artifacts_match_frozen_release():
    release = ROOT / "results" / "frozen" / "20260812T035654Z_a0703698ace9"
    source = ROOT / "paper" / "current_state" / "source"
    for relative in (
        "figures/acquisition_measured_results.pdf",
        "figures/synthetic_results.pdf",
        "tables/frozen_result_macros.tex",
        "tables/frozen_results.tex",
    ):
        assert (source / relative).read_bytes() == (release / relative).read_bytes()


def test_current_manuscript_has_no_legacy_result_inputs():
    current = ROOT / "paper" / "current_state" / "source"
    for relative in ("tables/result_values.tex", "tables/recovery_table.tex"):
        assert not (current / relative).exists()


def test_current_manuscript_scope_contract_is_explicit():
    source = (ROOT / "paper" / "current_state" / "source" / "main.tex").read_text(
        encoding="utf-8"
    )
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    evidence_readme = (ROOT / "results" / "README.md").read_text(encoding="utf-8")
    required_manuscript_phrases = (
        "greedy one-step EIG over a finite library",
        "not a globally optimal sequential policy",
        "conditional on the retained posterior draws and model",
        "only the stopping and",
        "does not establish dominance over randomized balanced",
        "not total physical-uncertainty intervals",
    )
    for phrase in required_manuscript_phrases:
        assert phrase in source
    assert "matched-model" in readme
    assert "raw-to-aggregate" in readme
    assert "does not by itself reconstruct" in evidence_readme
    assert "optimal experimental design" not in source.lower()


def test_prespecified_seed_namespaces_are_disjoint_and_complete():
    plan = load_study_plan(ROOT)
    assert len(plan.recovery_seeds) == 5
    assert len(plan.acquisition_seeds) == 30
    assert len(plan.validation_state_seeds) == 4
    assert len(plan.downstream_validation_seeds) == 10
    namespaces = [
        set(plan.recovery_seeds), set(plan.acquisition_seeds),
        set(plan.validation_state_seeds), set(plan.downstream_validation_seeds),
    ]
    assert not any(
        left & right
        for index, left in enumerate(namespaces)
        for right in namespaces[index + 1:]
    )
    assert [plan.acquisition_seed(index) for index in range(30)] == list(
        plan.acquisition_seeds
    )


def test_estimator_validation_uses_prefix_grid_and_prespecified_sentinels():
    plan = load_study_plan(ROOT)
    assert plan.outer_grid == (100, 300, 900)
    assert plan.inner_grid == (50, 100, 300)
    assert plan.replicate_grid == (5, 10, 20)
    assert plan.reference.as_tuple() == (1200, 400, 40)
    assert plan.audit.as_tuple() == (2400, 800, 40)
    assert plan.validation_state_task_count == 12
    assert plan.validation_grid_task_count == 108
    assert [
        plan.validation_audit_task(index).n_observations for index in range(2)
    ] == [2, 6]


def test_v4_study_plan_serializes_the_exact_confirmatory_contract():
    plan = load_study_plan(ROOT)
    benchmark = plan.comparator_benchmark
    assert benchmark.version == 4
    assert benchmark.candidate_count == 37
    assert tuple(
        (item.name, item.policy, item.comparator, item.endpoint)
        for item in benchmark.direct_contrasts
    ) == (
        ("eig_raw_vs_predictive_variance_raw", "eig_raw", "predictive_variance_raw", "measurement_count_to_gate"),
        ("eig_raw_vs_laplace_d_opt_raw", "eig_raw", "laplace_d_opt_raw", "measurement_count_to_gate"),
        ("eig_per_cost_vs_predictive_variance_per_cost", "eig_per_cost", "predictive_variance_per_cost", "modeled_cost_to_gate"),
        ("eig_per_cost_vs_laplace_d_opt_per_cost", "eig_per_cost", "laplace_d_opt_per_cost", "modeled_cost_to_gate"),
    )
    assert benchmark.holdout_contract.as_dict() == {
        "total_points": 23,
        "channel_counts": {"pcv": 8, "mu_real": 6, "mu_imag": 6, "lm": 3},
        "used_for_acquisition_or_stopping": False,
    }
    assert dict(plan.modeled_cost_seconds) == {
        "pcv": 60.0, "mu_real": 20.0, "mu_imag": 20.0, "lm": 15.0,
    }
    assert plan.eig_objectives == ("raw", "per_cost")
    assert (plan.max_measurements, plan.n_walkers, plan.n_steps, plan.burn) == (
        25, 48, 20000, 4000,
    )
    assert (plan.max_sampler_steps, plan.sampler_check_interval) == (80000, 10000)
    acquisition_stage = (ROOT / "slurm" / "12_eig.sbatch").read_text(
        encoding="utf-8"
    )
    assert "--n-walkers 48 --n-steps 20000 --burn 4000" in acquisition_stage
    assert "--max-sampler-steps 80000 --sampler-check-interval 10000" in acquisition_stage


def test_submit_requires_clean_source_and_validation_before_acquisition():
    source = (ROOT / "scripts" / "submit.sh").read_text(encoding="utf-8")
    assert "--untracked-files=all -- ." in source
    dependency = 'EIG="$(submit "afterok:$VALIDATION_FINAL"'
    assert dependency in source
    assert source.index("VALIDATION_FINAL=") < source.index(dependency)


def test_public_tree_contains_no_internal_phase_labels():
    """Prevent workflow shorthand from leaking back into the public tree."""
    phase_pattern = re.compile(
        r"(?<![A-Za-z0-9])(?:" + "P" + r"\d+|p" + r"\d+_)"
    )
    tracked = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT, check=True, capture_output=True,
    ).stdout.decode("utf-8").split("\0")
    offenders = []
    for relative in filter(None, tracked):
        path = ROOT / relative
        if not path.is_file():
            continue
        if phase_pattern.search(relative):
            offenders.append(relative)
        if path.suffix.lower() in {".pdf", ".png", ".jpg", ".npz"}:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if phase_pattern.search(content):
            offenders.append(relative)
    assert not sorted(set(offenders))


def test_watcher_treats_submission_and_task_failures_as_terminal():
    source = (ROOT / "scripts" / "watch.sh").read_text(encoding="utf-8")
    assert "SUBMISSION_FAILED" in source
    assert "audit_failure.json" in source
    assert "*.failed" in source


def test_coincident_acquisition_outcomes_are_grouped_without_hiding_seeds():
    path = ROOT / "scripts" / "generate_paper_artifacts.py"
    spec = importlib.util.spec_from_file_location("paper_artifacts_for_tests", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    grouped = module.group_paired_outcomes(
        [42, 43, 44, 45, 46], [5, 6, 5, 5, 6], [9, 9, 9, 9, 9],
    )
    assert grouped == [(5, 9, (42, 44, 45)), (6, 9, (43, 46))]
    assert sorted(seed for _, _, seeds in grouped for seed in seeds) == [42, 43, 44, 45, 46]


def test_acquisition_grouping_rejects_misaligned_vectors():
    path = ROOT / "scripts" / "generate_paper_artifacts.py"
    spec = importlib.util.spec_from_file_location("paper_artifacts_bad_input", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(ValueError, match="equal lengths"):
        module.group_paired_outcomes([42], [5, 6], [9])


def test_paired_descriptive_is_deterministic_and_complete():
    path = ROOT / "scripts" / "generate_paper_artifacts.py"
    spec = importlib.util.spec_from_file_location("paper_artifacts_stats", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    first = module.paired_descriptive([4.0, 3.0, 4.0, 4.0, 3.0], seed=17)
    second = module.paired_descriptive([4.0, 3.0, 4.0, 4.0, 3.0], seed=17)

    assert first == second
    assert first["mean"] == pytest.approx(3.6)
    assert first["median"] == 4.0
    assert first["sample_sd"] > 0.0
    assert first["bootstrap_mean_ci95_low"] <= first["mean"]
    assert first["bootstrap_mean_ci95_high"] >= first["mean"]


def test_paired_descriptive_rejects_empty_or_nonfinite():
    path = ROOT / "scripts" / "generate_paper_artifacts.py"
    spec = importlib.util.spec_from_file_location("paper_artifacts_bad_stats", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(ValueError, match="at least one"):
        module.paired_descriptive([], seed=1)
    with pytest.raises(ValueError, match="nonfinite"):
        module.paired_descriptive([1.0, float("nan")], seed=1)


def test_publication_figure_styles_are_monochrome_and_redundant():
    path = ROOT / "scripts" / "generate_paper_artifacts.py"
    spec = importlib.util.spec_from_file_location("paper_artifacts_style", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    paired = module.PAIRED_GROUP_STYLES
    assert len(paired) >= 2
    assert paired[0]["linestyle"] != paired[1]["linestyle"]
    assert paired[0]["marker"] != paired[1]["marker"]
    assert all(
        style["color"] in {"black", "white"}
        or style["color"].replace(".", "", 1).isdigit()
        for style in paired
    )

    bars = module.CHANNEL_BAR_STYLES
    assert set(bars) == {"core loss", r"$\mu'$", r"$\mu''$"}
    assert len({(style["facecolor"], style["hatch"]) for style in bars.values()}) == 3


def test_full_paper_cites_every_declared_reference():
    paper = ROOT / "paper" / "current_state" / "source"
    source = (paper / "main.tex").read_text(encoding="utf-8")
    bibliography = (paper / "refs.bib").read_text(encoding="utf-8")
    declared = re.findall(r"(?m)^@\w+\{([^,]+),", bibliography)
    cited = {
        key.strip()
        for group in re.findall(r"\\cite\{([^}]+)\}", source)
        for key in group.split(",")
    }
    assert len(declared) == len(set(declared))
    assert len(declared) >= 45
    assert cited == set(declared), "every bibliography entry must be cited and every citation declared"
