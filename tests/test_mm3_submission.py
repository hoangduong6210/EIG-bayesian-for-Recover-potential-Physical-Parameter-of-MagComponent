"""Submission boundary tests with an isolated fake scheduler."""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def harness(tmp_path):
    project = tmp_path / "project"
    run = project / "runs/run"
    source = run / "source"
    for relative in ("provenance", "status", "logs", "tmp", "source/scripts", "source/slurm", "source/configs"):
        (run / relative).mkdir(parents=True)
    (project / "scripts").mkdir()
    wrapper = project / "scripts/submit_model_mismatch_v3.sh"
    shutil.copy2(ROOT / "scripts/submit_model_mismatch_v3.sh", wrapper)
    wrapper.chmod(0o755)
    for name in ("32_model_mismatch_v3.sbatch", "33_model_mismatch_v3_aggregate.sbatch"):
        shutil.copy2(ROOT / "slurm" / name, source / "slurm" / name)
    selection = project / "selection.json"
    selection.write_text('{"decision":"fixture"}\n')
    predecessor = project / "non_admission.json"
    predecessor.write_text(json.dumps({"campaign_id": "MM-2", "admission": {"decision": "not_admitted", "confirmatory_claims_allowed": False}}))
    plan = {
        "campaign_id": "MM-3", "schema_version": "magcore-model-mismatch-preregistration/1.2",
        "runtime": {"sampler_method": "de_snooker"}, "task_count": 120,
        "estimator_decision_sha256": _sha(selection),
        "lineage": {"predecessor_campaign_id": "MM-2", "predecessor_non_admission_sha256": _sha(predecessor)},
    }
    (source / "scripts/model_mismatch_plan.py").write_text("import json\nprint(json.dumps(" + repr(plan) + "))\n")
    (source / "configs/model_mismatch_v3.toml").write_text("fixture = true\n")
    (run / "status/PREPARED").write_text("prepared\n")
    (run / "provenance/git-status.txt").write_text("")
    archive = run / "provenance/source-tree.tar.gz"
    with tarfile.open(archive, "w:gz") as stream:
        for path in sorted(source.rglob("*")):
            stream.add(path, arcname=path.relative_to(source), recursive=False)
    (run / "provenance/run.env").write_text(
        "MAGCORE_VENV=" + shlex.quote(str(Path(sys.executable).parent.parent)) + "\n"
        "MAGCORE_SUBMIT_ACCOUNT=test\nMAGCORE_SUBMIT_PARTITION=test\n"
        f"MAGCORE_SOURCE_ARCHIVE_SHA256={_sha(archive)}\n"
        f"MAGCORE_SOURCE_STATUS_SHA256={hashlib.sha256(b'').hexdigest()}\n"
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    sbatch = fake_bin / "sbatch"
    sbatch.write_text('''#!/usr/bin/env bash
set -euo pipefail
count=0
[[ ! -f "$FAKE_COUNT" ]] || count="$(<"$FAKE_COUNT")"
count=$((count + 1))
printf '%s\n' "$count" > "$FAKE_COUNT"
printf '%s\n' "$*" >> "$FAKE_ARGS"
case "$FAKE_MODE:$count" in
  reject:1) exit 1 ;;
  empty:1) exit 0 ;;
  malformed:1) printf 'Submitted batch job 123\n' ;;
  partial:1|success:1) printf '123;cluster\n' ;;
  partial:2) exit 1 ;;
  success:2) printf '456;cluster\n' ;;
  *) exit 2 ;;
esac
''')
    sbatch.chmod(0o755)
    env = {**os.environ, "PATH": str(fake_bin) + ":" + os.environ["PATH"],
           "MAGCORE_TEST_ALLOW_EPHEMERAL_RUN_ROOT": "1", "FAKE_MODE": "success",
           "FAKE_COUNT": str(tmp_path / "count"), "FAKE_ARGS": str(tmp_path / "args")}
    return wrapper, run, selection, predecessor, env


def _run(harness):
    wrapper, run, selection, predecessor, env = harness
    return subprocess.run([str(wrapper), str(run), str(selection), str(predecessor)], env=env, text=True, capture_output=True, timeout=15)


@pytest.mark.parametrize("mode", ["reject", "empty", "malformed", "partial", "success"])
def test_mm3_scheduler_responses_are_fail_closed_and_not_repeatable(harness, mode):
    _, run, _, _, env = harness
    env["FAKE_MODE"] = mode
    result = _run(harness)
    assert (result.returncode == 0) == (mode == "success"), result.stderr
    if mode == "success":
        assert json.loads((run / "status/MM3_SUBMITTED").read_text()) == {"array_job_id": "123", "aggregate_job_id": "456", "task_count": 120}
        args = Path(env["FAKE_ARGS"]).read_text()
        assert "--array=0-119%10" in args
        assert "--dependency=afterok:123" in args
    else:
        failure = json.loads((run / "status/MM3_SUBMISSION_FAILED").read_text())
        assert failure["stage"] == ("aggregate" if mode == "partial" else "array")
        assert failure["array_job_id"] == ("123" if mode == "partial" else "")
        assert not (run / "status/MM3_SUBMITTED").exists()
    count = Path(env["FAKE_COUNT"]).read_text()
    assert _run(harness).returncode != 0
    assert Path(env["FAKE_COUNT"]).read_text() == count


@pytest.mark.parametrize("change", ["archive", "source", "dirty", "selection", "predecessor", "prior_failure", "prior_lock"])
def test_mm3_refuses_tampering_or_previous_attempt_before_scheduler(harness, change):
    _, run, selection, predecessor, env = harness
    if change == "archive":
        path = run / "provenance/source-tree.tar.gz"
        path.write_bytes(path.read_bytes() + b"mutated")
    elif change == "source":
        (run / "source/extra.txt").write_text("mutation")
    elif change == "dirty":
        (run / "provenance/git-status.txt").write_text(" M tracked.py\n")
    elif change == "selection":
        selection.write_text("{}")
    elif change == "predecessor":
        predecessor.write_text("{}")
    elif change == "prior_failure":
        (run / "status/MM3_SUBMISSION_FAILED").write_text("{}")
    else:
        (run / "status/MM3_SUBMISSION_LOCK").mkdir()
    assert _run(harness).returncode != 0
    assert not Path(env["FAKE_COUNT"]).exists()


def test_mm3_resource_and_shell_contracts():
    for name in ("scripts/submit_model_mismatch_v3.sh", "slurm/32_model_mismatch_v3.sbatch", "slurm/33_model_mismatch_v3_aggregate.sbatch"):
        subprocess.run(["bash", "-n", str(ROOT / name)], check=True)
    array = (ROOT / "slurm/32_model_mismatch_v3.sbatch").read_text()
    assert "--cpus-per-task=1" in array and "--mem=64G" in array
    assert "--time=24:00:00" in array and "--workers 1" in array
    assert "--rejection-out" in array
    assert 'PYTHONPATH="$RUN_DIR/source/src"' in (ROOT / "scripts/submit_model_mismatch_v3.sh").read_text()
