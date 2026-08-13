#!/usr/bin/env bash
# Login-safe, read-only scheduler and marker summary.

set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
RUN_ARG="${1:-}"
if [[ -z "$RUN_ARG" ]]; then
    [[ -f "$PROJECT_ROOT/runs/LATEST" ]] || { echo "no runs have been submitted" >&2; exit 66; }
    RUN_ARG="$PROJECT_ROOT/runs/$(<"$PROJECT_ROOT/runs/LATEST")"
fi
RUN_DIR="$(cd "$RUN_ARG" && pwd -P)"
case "$RUN_DIR/" in "$PROJECT_ROOT/runs/"*) ;; *) echo "run is outside project" >&2; exit 65;; esac
JOBS="$RUN_DIR/provenance/jobs.tsv"
[[ -f "$JOBS" ]] || { echo "missing job map: $JOBS" >&2; exit 66; }

echo "run: $(basename "$RUN_DIR")"
if [[ -f "$RUN_DIR/status/final.json" ]]; then
    echo "final: $(<"$RUN_DIR/status/final.json")"
else
    echo "final: pending"
fi
printf 'done=%s failed=%s\n' \
    "$(find "$RUN_DIR/status" -maxdepth 1 -name '*.done' | wc -l)" \
    "$(find "$RUN_DIR/status" -maxdepth 1 -name '*.failed' | wc -l)"

JOB_IDS="$(awk 'NR > 1 {print $2}' "$JOBS" | paste -sd, -)"
if [[ -n "$JOB_IDS" ]]; then
    squeue --jobs="$JOB_IDS" --noheader --format='%.18i %.24j %.10T %.10M %R' || true
    sacct -X -j "$JOB_IDS" --noheader --parsable2 \
        --format=JobIDRaw,JobName%24,State,Elapsed,ExitCode 2>/dev/null || true
fi
