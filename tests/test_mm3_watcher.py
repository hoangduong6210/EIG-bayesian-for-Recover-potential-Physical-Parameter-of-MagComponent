"""Scheduler snapshots exercise the read-only MM-3 watcher without real jobs."""

import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def watcher(tmp_path):
    project = tmp_path / "project"
    scripts = project / "scripts"
    scripts.mkdir(parents=True)
    script = scripts / "watch_model_mismatch_v3.sh"
    shutil.copyfile(ROOT / "scripts/watch_model_mismatch_v3.sh", script)
    run = project / "runs/test"
    for folder in ("provenance", "status", "source/scripts", "source/configs", "summary/model_mismatch_v3"):
        (run / folder).mkdir(parents=True)
    (run / "provenance/run.env").write_text(f"MAGCORE_VENV={shlex.quote(sys.prefix)}\n")
    (run / "status/MM3_SUBMITTED").write_text(json.dumps({"array_job_id": "100", "aggregate_job_id": "200", "task_count": 2}))
    (run / "source/scripts/model_mismatch_plan.py").write_text(
        "import json\nprint(json.dumps({'campaign_id':'MM-3','scenarios':[{'name':'case'}],'seeds':[1,2]}))\n"
    )
    mocks = tmp_path / "bin"
    mocks.mkdir()
    common = f"#!{sys.executable}\nimport json, os\nfrom pathlib import Path\nroot=Path(os.environ['WATCH_ROOT'])\nstep_path=root/'mock_step'\nstep=int(step_path.read_text()) if step_path.exists() else 0\n"
    for tool, variable in (("squeue", "WATCH_QUEUE"), ("sacct", "WATCH_ACCOUNTING")):
        path = mocks / tool
        path.write_text(common + f"rows=json.loads(os.environ['{variable}'])\nvalue=rows[min(step,len(rows)-1)]\nif value is None: raise SystemExit(1)\nprint(value)\n")
        path.chmod(0o755)
    sleep = mocks / "sleep"
    sleep.write_text(common + """step += 1
step_path.write_text(str(step))
if step > 5:
    raise SystemExit('watcher failed to terminate within mocked snapshots')
if step == int(os.environ.get('WATCH_SUCCESS_AT', '-1')):
    for seed in (1,2):
        path=root/f'results/model_mismatch_v3/case_seed{seed}/result.json'
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text('{}')
    (root/'status/model_mismatch_v3_aggregate_0.done').write_text('done')
    (root/'summary/model_mismatch_v3/aggregate.json').write_text('{}')
""")
    sleep.chmod(0o755)

    def invoke(queue, accounting, success_at=None):
        env = dict(os.environ, PATH=str(mocks) + os.pathsep + os.environ["PATH"],
                   WATCH_ROOT=str(run), WATCH_QUEUE=json.dumps(queue),
                   WATCH_ACCOUNTING=json.dumps(accounting), MAGCORE_WATCH_INTERVAL="10")
        if success_at is not None:
            env["WATCH_SUCCESS_AT"] = str(success_at)
        result = subprocess.run(["bash", str(script), str(run)], env=env,
                                text=True, capture_output=True, timeout=10)
        return result, int((run / "mock_step").read_text()) if (run / "mock_step").exists() else 0
    return run, invoke


def test_oom_without_trap_marker_waits_for_other_tasks_then_rejects(watcher):
    _, invoke = watcher
    result, sleeps = invoke(
        ["100_1|RUNNING\n200|PENDING", "200|PENDING"],
        ["100_0|OUT_OF_MEMORY|0:9\n100_1|RUNNING|0:0", "100_0|OUT_OF_MEMORY|0:9\n100_1|COMPLETED|0:0"],
    )
    assert result.returncode == 1
    assert sleeps == 1
    assert "task_failed=1" in result.stdout
    assert "array is terminal with failed work; no admission" in result.stdout


@pytest.mark.parametrize("state,code", [("TIMEOUT", "0:0"), ("FAILED", "0:9"), ("CANCELLED by 123", "0:15")])
def test_terminal_failures_without_files_do_not_loop(watcher, state, code):
    _, invoke = watcher
    result, sleeps = invoke(["200|PENDING"], [f"100_0|{state}|{code}\n100_1|COMPLETED|0:0"])
    assert result.returncode == 1
    assert sleeps == 0
    assert "no admission" in result.stdout


def test_aggregate_failure_is_separate_from_task_failures(watcher):
    run, invoke = watcher
    (run / "status/model_mismatch_v3_aggregate_0.failed").write_text("failed")
    result, _ = invoke([""], ["100_0|COMPLETED|0:0\n100_1|COMPLETED|0:0\n200|FAILED|1:0"])
    assert result.returncode == 1
    assert "task_failed=0 aggregate_failed=True" in result.stdout


def test_transient_absence_does_not_immediately_fail(watcher):
    _, invoke = watcher
    result, sleeps = invoke(["", ""], ["", "100_0|COMPLETED|0:0\n100_1|COMPLETED|0:0\n200|COMPLETED|0:0"], success_at=1)
    assert result.returncode == 0
    assert sleeps == 1
    assert "completed successfully" in result.stdout


def test_persistent_absence_reports_incomplete_evidence(watcher):
    _, invoke = watcher
    result, sleeps = invoke([""], [""])
    assert result.returncode == 1
    assert sleeps == 2
    assert "after three checks" in result.stdout


def test_scheduler_query_failure_does_not_imply_terminal_campaign(watcher):
    _, invoke = watcher
    result, sleeps = invoke([None, ""], [None, "200|COMPLETED|0:0"], success_at=1)
    assert result.returncode == 0
    assert sleeps == 1


def test_array_failed_marker_uses_scenario_seed_identity(watcher):
    run, invoke = watcher
    (run / "status/model_mismatch_v3_case_seed1.failed").write_text("failed")
    result, _ = invoke(["200|PENDING"], ["100_1|COMPLETED|0:0"])
    assert result.returncode == 1
    assert "task_failed=1" in result.stdout
