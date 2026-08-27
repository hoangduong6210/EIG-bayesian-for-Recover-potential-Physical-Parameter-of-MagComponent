#!/usr/bin/env bash
# Submit MM-1 from an immutable run prepared by scripts/submit.sh --prepare-only.

set -Eeuo pipefail
umask 027

if [[ $# -ne 2 ]]; then
    echo "usage: $0 PREPARED_RUN_DIR ESTIMATOR_FINAL_DECISION_JSON" >&2
    exit 64
fi
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
RUN_DIR="$(cd "$1" && pwd -P)"
SELECTION="$(cd "$(dirname "$2")" && pwd -P)/$(basename "$2")"
case "$RUN_DIR/" in
    "$PROJECT_ROOT/runs/"*) ;;
    *) echo "prepared run is outside $PROJECT_ROOT/runs" >&2; exit 65 ;;
esac
[[ -f "$RUN_DIR/status/PREPARED" ]] || {
    echo "run was not created with scripts/submit.sh --prepare-only" >&2
    exit 66
}
[[ -f "$RUN_DIR/provenance/run.env" && -d "$RUN_DIR/source" ]] || {
    echo "prepared run is incomplete" >&2
    exit 66
}
[[ -s "$SELECTION" ]] || { echo "missing estimator decision: $SELECTION" >&2; exit 66; }
for command in sbatch sha256sum; do
    command -v "$command" >/dev/null || { echo "missing command: $command" >&2; exit 69; }
done
for script in 22_model_mismatch.sbatch 23_model_mismatch_aggregate.sbatch; do
    bash -n "$RUN_DIR/source/slurm/$script"
done

# The prepared source tree, not the live checkout, defines this campaign.
# shellcheck disable=SC1090
source "$RUN_DIR/provenance/run.env"
CONFIG="$RUN_DIR/source/configs/model_mismatch.toml"
[[ -s "$CONFIG" ]] || { echo "prepared source does not contain MM-1" >&2; exit 66; }
EXPECTED_SELECTION_SHA="$($MAGCORE_VENV/bin/python \
    "$RUN_DIR/source/scripts/model_mismatch_plan.py" plan --config "$CONFIG" \
    | $MAGCORE_VENV/bin/python -c 'import json,sys; print(json.load(sys.stdin)["estimator_decision_sha256"])')"
ACTUAL_SELECTION_SHA="$(sha256sum "$SELECTION" | awk '{print $1}')"
[[ "$ACTUAL_SELECTION_SHA" == "$EXPECTED_SELECTION_SHA" ]] || {
    echo "estimator decision does not match the preregistered SHA-256" >&2
    exit 65
}
TASK_COUNT="$($MAGCORE_VENV/bin/python \
    "$RUN_DIR/source/scripts/model_mismatch_plan.py" plan --config "$CONFIG" \
    | $MAGCORE_VENV/bin/python -c 'import json,sys; print(json.load(sys.stdin)["task_count"])')"
[[ "$TASK_COUNT" =~ ^[1-9][0-9]*$ ]] || { echo "invalid MM-1 task count" >&2; exit 65; }

DESTINATION="$RUN_DIR/summary/model_mismatch/estimator_decision.json"
mkdir -p "$RUN_DIR/summary/model_mismatch"
[[ ! -e "$DESTINATION" ]] || {
    echo "refusing to replace locked estimator decision: $DESTINATION" >&2
    exit 73
}
cp "$SELECTION" "$DESTINATION"
sha256sum "$DESTINATION" > "$RUN_DIR/summary/model_mismatch/estimator_decision.sha256"

submit() {
    local dependency="$1" script="$2"
    shift 2
    local -a options=(--parsable --account="$MAGCORE_SUBMIT_ACCOUNT"
        --partition="$MAGCORE_SUBMIT_PARTITION"
        --output="$RUN_DIR/logs/%x_%A_%a.out")
    [[ -z "$dependency" ]] || options+=(--dependency="$dependency")
    options+=("$@")
    local response
    response="$(sbatch "${options[@]}" "$RUN_DIR/source/slurm/$script" "$RUN_DIR")"
    printf '%s\n' "${response%%;*}"
}

ARRAY="$(submit "" 22_model_mismatch.sbatch --array="0-$((TASK_COUNT - 1))%10")"
AGGREGATE="$(submit "afterok:$ARRAY" 23_model_mismatch_aggregate.sbatch)"
{
    printf 'stage\tjob_id\tdependency\ttask_count\n'
    printf 'model_mismatch\t%s\t-\t%s\n' "$ARRAY" "$TASK_COUNT"
    printf 'model_mismatch_aggregate\t%s\tafterok:%s\t1\n' "$AGGREGATE" "$ARRAY"
} > "$RUN_DIR/provenance/model_mismatch_jobs.tsv"
printf '{"array_job_id":"%s","aggregate_job_id":"%s","task_count":%s}\n' \
    "$ARRAY" "$AGGREGATE" "$TASK_COUNT" > "$RUN_DIR/status/MM1_SUBMITTED"
printf 'Submitted MM-1 array: %s (%s tasks)\nAggregate job: %s\nRun: %s\n' \
    "$ARRAY" "$TASK_COUNT" "$AGGREGATE" "$RUN_DIR"
