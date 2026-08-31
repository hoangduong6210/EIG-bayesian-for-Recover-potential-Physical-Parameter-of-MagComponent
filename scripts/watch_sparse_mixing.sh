#!/usr/bin/env bash
# Read-only watcher for the diagnostic-only SparseMix-1 jobs.

set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
RUN_DIR="$(cd "${1:?usage: $0 PREPARED_RUN_DIR}" && pwd -P)"
INTERVAL="${MAGCORE_WATCH_INTERVAL:-60}"
case "$RUN_DIR/" in "$PROJECT_ROOT/runs/"*) ;; *)
    echo "SparseMix-1 run is outside project runs" >&2; exit 65;;
esac
[[ "$INTERVAL" =~ ^[0-9]+$ && "$INTERVAL" -ge 10 ]] || exit 64
while [[ ! -f "$RUN_DIR/status/SPARSEMIX_SUBMITTED" ]]; do
    if [[ -f "$RUN_DIR/status/SPARSEMIX_SUBMISSION_FAILED" ]]; then
        echo "SparseMix-1 submission failed before both job IDs were recorded." >&2
        exit 1
    fi
    sleep "$INTERVAL"
done
read -r ARRAY VALIDATOR TASK_COUNT < <(
    python - "$RUN_DIR/status/SPARSEMIX_SUBMITTED" <<'PY'
import json, pathlib, sys
record = json.loads(pathlib.Path(sys.argv[1]).read_text())
print(record["array_job_id"], record["validator_job_id"], record["task_count"])
PY
)
while :; do
    if [[ -d "$RUN_DIR/results/sparse_mixing" ]]; then
        COMPLETED="$(find "$RUN_DIR/results/sparse_mixing" -mindepth 2 -maxdepth 2 \
            -name result.json -type f | wc -l)"
    else
        COMPLETED=0
    fi
    FAILED="$(find "$RUN_DIR/status" -maxdepth 1 -name 'sparse_mixing_*.failed' \
        ! -name 'sparse_mixing_validate_*.failed' -type f 2>/dev/null | wc -l)"
    printf '%s SparseMix-1 diagnostic_records=%s/%s failed=%s array=%s validator=%s\n' \
        "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$COMPLETED" "$TASK_COUNT" \
        "$FAILED" "$ARRAY" "$VALIDATOR"
    if [[ -f "$RUN_DIR/status/sparse_mixing_validate_0.done" && \
          -s "$RUN_DIR/summary/sparse_mixing/manifest.json" ]]; then
        echo "SparseMix-1 diagnostic manifest completed; MM-2 admission is unchanged."
        exit 0
    fi
    if [[ -f "$RUN_DIR/status/sparse_mixing_validate_0.failed" ]]; then
        echo "SparseMix-1 validator failed; no diagnostic manifest was admitted." >&2
        exit 1
    fi
    if [[ -f "$RUN_DIR/status/SPARSEMIX_SUBMISSION_FAILED" ]]; then
        echo "SparseMix-1 submission failed; inspect the failure marker." >&2
        exit 1
    fi
    if (( COMPLETED + FAILED == TASK_COUNT && FAILED > 0 )); then
        echo "SparseMix-1 closed with failed diagnostic tasks; no manifest created." >&2
        exit 1
    fi
    squeue --jobs="$ARRAY,$VALIDATOR" --noheader \
        --format='%.18i %.24j %.10T %.10M %R' 2>/dev/null || true
    sleep "$INTERVAL"
done
