#!/usr/bin/env bash
# Read-only watcher for the preregistered MM-1 array and aggregate jobs.

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
    *) echo "MM-1 run is outside $PROJECT_ROOT/runs" >&2; exit 65 ;;
esac
[[ -f "$RUN_DIR/provenance/run.env" ]] || {
    echo "missing MM-1 run provenance" >&2
    exit 66
}
# shellcheck disable=SC1090
source "$RUN_DIR/provenance/run.env"

while [[ ! -f "$RUN_DIR/status/MM1_SUBMITTED" ]]; do
    if [[ -f "$RUN_DIR/status/MM1_SUBMISSION_FAILED" ]]; then
        echo "MM-1 submission failed before valid job IDs were recorded." >&2
        exit 1
    fi
    sleep "$INTERVAL"
done

read -r ARRAY_JOB AGGREGATE_JOB < <(
    "$MAGCORE_VENV/bin/python" - "$RUN_DIR/status/MM1_SUBMITTED" <<'PY'
import json
import pathlib
import re
import sys

record = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
array_job = str(record.get("array_job_id", ""))
aggregate_job = str(record.get("aggregate_job_id", ""))
if not re.fullmatch(r"[1-9][0-9]*", array_job):
    raise SystemExit("invalid MM-1 array job ID")
if not re.fullmatch(r"[1-9][0-9]*", aggregate_job):
    raise SystemExit("invalid MM-1 aggregate job ID")
print(array_job, aggregate_job)
PY
)

while :; do
    COMPLETED="$(find "$RUN_DIR/results/model_mismatch" -mindepth 2 -maxdepth 2 \
        -name result.json -type f 2>/dev/null | wc -l)"
    FAILED="$(find "$RUN_DIR/status" -maxdepth 1 -name 'model_mismatch_*.failed' \
        -type f 2>/dev/null | wc -l)"
    printf '%s MM-1 completed=%s/120 failed=%s array=%s aggregate=%s\n' \
        "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$COMPLETED" "$FAILED" \
        "$ARRAY_JOB" "$AGGREGATE_JOB"

    if [[ -f "$RUN_DIR/status/model_mismatch_aggregate_0.done" && \
          -s "$RUN_DIR/summary/model_mismatch/aggregate.json" ]]; then
        echo "MM-1 completed successfully."
        exit 0
    fi
    if [[ "$FAILED" -gt 0 || -f "$RUN_DIR/status/MM1_SUBMISSION_FAILED" ]]; then
        echo "MM-1 failed; inspect status markers and scheduler logs." >&2
        exit 1
    fi

    squeue --jobs="$ARRAY_JOB,$AGGREGATE_JOB" --noheader \
        --format='%.18i %.24j %.10T %.10M %R' 2>/dev/null || true
    sacct -X -j "$ARRAY_JOB,$AGGREGATE_JOB" --noheader --parsable2 \
        --format=JobIDRaw,JobName%24,State,Elapsed,ExitCode 2>/dev/null || true
    sleep "$INTERVAL"
done
