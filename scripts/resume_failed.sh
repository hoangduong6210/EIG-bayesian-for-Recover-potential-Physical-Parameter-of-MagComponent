#!/usr/bin/env bash
# Safe retry: create a new immutable run linked to the failed attempt.

set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
[[ $# -eq 1 ]] || { echo "usage: $0 FAILED_RUN_DIR" >&2; exit 64; }
FAILED_RUN="$(cd "$1" && pwd -P)"
case "$FAILED_RUN/" in "$PROJECT_ROOT/runs/"*) ;; *) echo "run is outside project" >&2; exit 65;; esac
if [[ ! -f "$FAILED_RUN/status/FAILED" && ! -f "$FAILED_RUN/status/SUBMISSION_FAILED" ]]; then
    echo "refusing retry: source run is not marked failed" >&2
    exit 67
fi
echo "Retries never overwrite an attempt. Submitting a complete evidence matrix linked to: $FAILED_RUN"
exec "$PROJECT_ROOT/scripts/submit.sh" --retry-of "$FAILED_RUN"
