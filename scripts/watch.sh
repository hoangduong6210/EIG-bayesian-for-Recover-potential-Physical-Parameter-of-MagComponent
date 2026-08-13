#!/usr/bin/env bash
# Login-safe watcher. It performs scheduler queries and small marker reads only.

set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
RUN_DIR="${1:-}"
INTERVAL="${MAGCORE_WATCH_INTERVAL:-30}"
[[ "$INTERVAL" =~ ^[0-9]+$ && "$INTERVAL" -ge 10 ]] || {
    echo "MAGCORE_WATCH_INTERVAL must be an integer >= 10 seconds" >&2
    exit 64
}
if [[ -z "$RUN_DIR" ]]; then
    [[ -f "$PROJECT_ROOT/runs/LATEST" ]] || { echo "no submitted run" >&2; exit 66; }
    RUN_DIR="$PROJECT_ROOT/runs/$(<"$PROJECT_ROOT/runs/LATEST")"
fi
RUN_DIR="$(cd "$RUN_DIR" && pwd -P)"

while :; do
    clear 2>/dev/null || true
    date -u '+%Y-%m-%dT%H:%M:%SZ'
    "$PROJECT_ROOT/scripts/status.sh" "$RUN_DIR"
    if [[ -f "$RUN_DIR/status/SUCCESS" ]]; then
        echo "Magnetic Core pipeline completed successfully."
        exit 0
    fi
    if [[ -f "$RUN_DIR/status/FAILED" ]]; then
        echo "Magnetic Core pipeline failed; inspect status/*.failed and logs/." >&2
        exit 1
    fi
    if [[ -f "$RUN_DIR/status/SUBMISSION_FAILED" ]]; then
        echo "Magnetic Core submission failed; inspect status/SUBMISSION_FAILED." >&2
        exit 1
    fi
    if [[ -f "$RUN_DIR/status/audit_failure.json" ]] || \
       find "$RUN_DIR/status" -maxdepth 1 -name '*.failed' -print -quit | grep -q .; then
        echo "Magnetic Core task/audit failure detected; stopping watcher." >&2
        exit 1
    fi
    sleep "$INTERVAL"
done
