#!/usr/bin/env bash
# Read-only watcher for the preregistered MM-2 array and aggregate jobs.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
RUN_ARG="${1:-}"
INTERVAL="${MAGCORE_WATCH_INTERVAL:-60}"
[[ "$INTERVAL" =~ ^[0-9]+$ && "$INTERVAL" -ge 10 ]] || {
    echo "MAGCORE_WATCH_INTERVAL must be an integer >= 10 seconds" >&2
    exit 64
}
[[ -n "$RUN_ARG" ]] || { echo "usage: $0 PREPARED_RUN_DIR" >&2; exit 64; }
RUN_DIR="$(cd "$RUN_ARG" && pwd -P)"
case "$RUN_DIR/" in
    "$PROJECT_ROOT/runs/"*) ;;
    *) echo "MM-2 run is outside $PROJECT_ROOT/runs" >&2; exit 65 ;;
esac
[[ -f "$RUN_DIR/provenance/run.env" ]] || {
    echo "missing MM-2 run provenance" >&2
    exit 66
}
# shellcheck disable=SC1090
source "$RUN_DIR/provenance/run.env"

while [[ ! -f "$RUN_DIR/status/MM2_SUBMITTED" ]]; do
    if [[ -f "$RUN_DIR/status/MM2_SUBMISSION_FAILED" ]]; then
        echo "MM-2 submission failed before valid job IDs were recorded." >&2
        exit 1
    fi
    sleep "$INTERVAL"
done

read -r ARRAY_JOB AGGREGATE_JOB TASK_COUNT < <(
    "$MAGCORE_VENV/bin/python" - "$RUN_DIR/status/MM2_SUBMITTED" <<'PY'
import json
import pathlib
import re
import sys

record = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
array_job = str(record.get("array_job_id", ""))
aggregate_job = str(record.get("aggregate_job_id", ""))
task_count = record.get("task_count")
if not re.fullmatch(r"[1-9][0-9]*", array_job):
    raise SystemExit("invalid MM-2 array job ID")
if not re.fullmatch(r"[1-9][0-9]*", aggregate_job):
    raise SystemExit("invalid MM-2 aggregate job ID")
if isinstance(task_count, bool) or not isinstance(task_count, int) or task_count <= 0:
    raise SystemExit("invalid MM-2 task count")
print(array_job, aggregate_job, task_count)
PY
)

while :; do
    if [[ -d "$RUN_DIR/results/model_mismatch_v2" ]]; then
        COMPLETED="$(find "$RUN_DIR/results/model_mismatch_v2" \
            -mindepth 2 -maxdepth 2 -name result.json -type f | wc -l)"
    else
        COMPLETED=0
    fi
    FAILED="$(find "$RUN_DIR/status" -maxdepth 1 \
        -name 'model_mismatch_v2_*.failed' -type f | wc -l)"
    if [[ -d "$RUN_DIR/status/model_mismatch_v2_rejections" ]]; then
        REJECTIONS="$(find "$RUN_DIR/status/model_mismatch_v2_rejections" \
            -maxdepth 1 -name '*.json' -type f | wc -l)"
    else
        REJECTIONS=0
    fi
    printf '%s MM-2 completed=%s/%s failed=%s rejection_records=%s array=%s aggregate=%s\n' \
        "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$COMPLETED" "$TASK_COUNT" \
        "$FAILED" "$REJECTIONS" "$ARRAY_JOB" "$AGGREGATE_JOB"

    if [[ -f "$RUN_DIR/status/model_mismatch_v2_aggregate_0.done" && \
          -s "$RUN_DIR/summary/model_mismatch_v2/aggregate.json" ]]; then
        echo "MM-2 completed successfully."
        exit 0
    fi
    if [[ -f "$RUN_DIR/status/MM2_SUBMISSION_FAILED" ]]; then
        echo "MM-2 submission failed; inspect the immutable failure marker." >&2
        exit 1
    fi
    if (( COMPLETED + FAILED == TASK_COUNT && FAILED > 0 )); then
        echo "MM-2 closed with failed tasks; no aggregate may be admitted." >&2
        exit 1
    fi
    if (( COMPLETED + FAILED > TASK_COUNT )); then
        echo "MM-2 marker matrix exceeds the preregistered task count." >&2
        exit 1
    fi

    squeue --jobs="$ARRAY_JOB,$AGGREGATE_JOB" --noheader \
        --format='%.18i %.24j %.10T %.10M %R' 2>/dev/null || true
    sacct -X -j "$ARRAY_JOB,$AGGREGATE_JOB" --noheader --parsable2 \
        --format=JobIDRaw,JobName%24,State,Elapsed,ExitCode 2>/dev/null || true
    sleep "$INTERVAL"
done
