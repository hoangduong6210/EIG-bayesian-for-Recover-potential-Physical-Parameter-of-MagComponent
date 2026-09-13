#!/usr/bin/env bash
# Read-only MM-3 monitoring, including scheduler failures without trap markers.
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
[[ $# -eq 1 ]] || { echo "usage: $0 PREPARED_RUN_DIR" >&2; exit 64; }
RUN_DIR="$(cd "$1" && pwd -P)"
case "$RUN_DIR/" in
    "$PROJECT_ROOT/runs/"*) ;;
    *) echo "MM-3 run is outside the project runs directory" >&2; exit 65 ;;
esac
[[ -f "$RUN_DIR/provenance/run.env" ]] || { echo "missing MM-3 provenance" >&2; exit 66; }
# shellcheck disable=SC1090
source "$RUN_DIR/provenance/run.env"
exec "$MAGCORE_VENV/bin/python" - "$RUN_DIR" "${MAGCORE_WATCH_INTERVAL:-60}" <<'PY'
import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys

root = Path(sys.argv[1])
if not re.fullmatch(r"[0-9]+", sys.argv[2]) or int(sys.argv[2]) < 10:
    raise SystemExit("MAGCORE_WATCH_INTERVAL must be an integer >= 10 seconds")
interval = sys.argv[2]
status = root / "status"

def pause():
    subprocess.run(["sleep", interval], check=True)

def finish(message, code):
    print(message, flush=True)
    raise SystemExit(code)

while not (status / "MM3_SUBMITTED").is_file():
    if (status / "MM3_SUBMISSION_FAILED").is_file():
        finish("MM-3 submission failed; no admission.", 1)
    pause()
submission = json.loads((status / "MM3_SUBMITTED").read_text())
array, aggregate = (str(submission.get(name, "")) for name in ("array_job_id", "aggregate_job_id"))
count = submission.get("task_count")
if any(re.fullmatch(r"[1-9][0-9]*", value) is None for value in (array, aggregate)) \
        or type(count) is not int or count < 1:
    finish("Invalid MM-3 submitted job identities; no admission.", 1)

environment = dict(os.environ)
environment["PYTHONDONTWRITEBYTECODE"] = "1"
environment["PYTHONPATH"] = str(root / "source/src") + os.pathsep + environment.get("PYTHONPATH", "")
plan_process = subprocess.run([
    sys.executable, str(root / "source/scripts/model_mismatch_plan.py"), "plan",
    "--config", str(root / "source/configs/model_mismatch_v3.toml"),
], text=True, capture_output=True, env=environment)
if plan_process.returncode:
    finish("Cannot verify the immutable MM-3 task plan; no admission.", 1)
plan = json.loads(plan_process.stdout)
names = [f"{scenario['name']}_seed{seed}" for scenario in plan["scenarios"] for seed in plan["seeds"]]
if plan.get("campaign_id") != "MM-3" or len(names) != count or len(set(names)) != count \
        or any(re.fullmatch(r"[A-Za-z0-9_]+", name) is None for name in names):
    finish("MM-3 submitted matrix differs from its immutable plan; no admission.", 1)

terminal = {"COMPLETED", "FAILED", "CANCELLED", "TIMEOUT", "OUT_OF_MEMORY", "NODE_FAIL",
            "PREEMPTED", "BOOT_FAIL", "DEADLINE", "REVOKED"}
observed = {}
missing_polls = 0

def query(command):
    try:
        result = subprocess.run(command, text=True, capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None

while True:
    queue = query(["squeue", "--array", f"--jobs={array},{aggregate}", "--noheader", "--format=%i|%T"])
    accounting = query(["sacct", "-X", "-j", f"{array},{aggregate}", "--noheader", "--parsable2",
                        "--format=JobID,State,ExitCode"])
    active = set()
    if queue is not None:
        for line in queue.splitlines():
            fields = line.strip().split("|")
            if len(fields) >= 2 and fields[1].strip():
                job, state = fields[0].strip(), fields[1].strip().split()[0]
                if state not in terminal:
                    active.add(job)
    if accounting is not None:
        for line in accounting.splitlines():
            fields = line.strip().split("|")
            if len(fields) < 3:
                continue
            job, state, code = (field.strip() for field in fields[:3])
            state = state.split()[0].rstrip("+") if state else ""
            if job == aggregate or re.fullmatch(re.escape(array) + r"_[0-9]+", job):
                if state in terminal:
                    observed[job] = (state, code)
                elif state:
                    # A requeued task invalidates a previous terminal snapshot.
                    observed.pop(job, None)
                    active.add(job)
    completed = {i for i, name in enumerate(names)
                 if (root / "results/model_mismatch_v3" / name / "result.json").is_file()}
    failed_markers = {i for i, name in enumerate(names)
                      if (status / f"model_mismatch_v3_{name}.failed").is_file()}
    scheduler_terminal = {i for i in range(count) if f"{array}_{i}" in observed}
    scheduler_failed = {i for i in scheduler_terminal
                        if observed[f"{array}_{i}"] != ("COMPLETED", "0:0")}
    aggregate_failed = (status / "model_mismatch_v3_aggregate_0.failed").is_file() \
        or (aggregate in observed and observed[aggregate] != ("COMPLETED", "0:0"))
    failed = failed_markers | scheduler_failed
    array_active = any(job == array or job.startswith(array + "_") for job in active)
    matrix_terminal = len(completed | failed_markers | scheduler_terminal) == count and not array_active
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    print(f"{timestamp} MM-3 completed={len(completed)}/{count} task_failed={len(failed)} "
          f"aggregate_failed={aggregate_failed} scheduler_terminal={len(scheduler_terminal)}", flush=True)
    if failed or aggregate_failed:
        print("MM-3 has terminal failure evidence; no admission. Monitoring remaining array tasks.", flush=True)
    if (status / "MM3_SUBMISSION_FAILED").is_file():
        finish("MM-3 submission failed; no admission.", 1)
    if matrix_terminal and (failed or aggregate_failed):
        finish("MM-3 array is terminal with failed work; no admission.", 1)
    aggregate_done = (status / "model_mismatch_v3_aggregate_0.done").is_file()
    aggregate_path = root / "summary/model_mismatch_v3/aggregate.json"
    if len(completed) == count and not failed and not aggregate_failed \
            and aggregate_done and aggregate_path.is_file() and aggregate_path.stat().st_size > 0:
        finish("MM-3 completed successfully; aggregate artifact is available for scientific validation.", 0)
    # Three successful empty queue snapshots tolerate normal accounting/file lag.
    # Query errors do not count as evidence that a job has disappeared.
    if queue is not None and accounting is not None and not active:
        missing_polls += 1
    else:
        missing_polls = 0
    if missing_polls >= 3:
        finish("MM-3 scheduler is inactive but completion evidence is incomplete after three checks; "
               "no admission. Inspect accounting and artifacts.", 1)
    pause()
PY
