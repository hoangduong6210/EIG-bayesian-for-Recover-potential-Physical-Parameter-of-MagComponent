#!/usr/bin/env bash
# Submit the independent MM-2 successor from a prepared immutable run.

set -Eeuo pipefail
umask 027

if [[ $# -ne 3 ]]; then
    echo "usage: $0 PREPARED_RUN_DIR ESTIMATOR_DECISION_JSON MM1_NON_ADMISSION_JSON" >&2
    exit 64
fi
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
RUN_DIR="$(cd "$1" && pwd -P)"
SELECTION="$(cd "$(dirname "$2")" && pwd -P)/$(basename "$2")"
PREDECESSOR="$(cd "$(dirname "$3")" && pwd -P)/$(basename "$3")"
case "$RUN_DIR/" in
    "$PROJECT_ROOT/runs/"*) ;;
    *) echo "prepared run is outside $PROJECT_ROOT/runs" >&2; exit 65 ;;
esac
case "$RUN_DIR/" in
    /tmp/*|/var/tmp/*)
        [[ "${MAGCORE_TEST_ALLOW_EPHEMERAL_RUN_ROOT:-0}" == "1" ]] || {
            echo "MM-2 run must be on a compute-node shared filesystem" >&2
            exit 65
        }
        ;;
esac
[[ -f "$RUN_DIR/status/PREPARED" \
    && -f "$RUN_DIR/provenance/run.env" \
    && -d "$RUN_DIR/source" ]] || {
    echo "prepared run is incomplete" >&2
    exit 66
}
[[ -s "$SELECTION" ]] || { echo "missing estimator decision: $SELECTION" >&2; exit 66; }
[[ -s "$PREDECESSOR" ]] || { echo "missing MM-1 non-admission record: $PREDECESSOR" >&2; exit 66; }
for command in sbatch sha256sum tar diff mktemp; do
    command -v "$command" >/dev/null || { echo "missing command: $command" >&2; exit 69; }
done
for script in 24_model_mismatch_v2.sbatch 25_model_mismatch_v2_aggregate.sbatch; do
    bash -n "$RUN_DIR/source/slurm/$script"
done

# The archive digest and extracted tree must both match before scheduling.
# shellcheck disable=SC1090
source "$RUN_DIR/provenance/run.env"
ARCHIVE="$RUN_DIR/provenance/source-tree.tar.gz"
[[ "$(sha256sum "$ARCHIVE" | awk '{print $1}')" == "$MAGCORE_SOURCE_ARCHIVE_SHA256" ]] || {
    echo "prepared source archive digest mismatch" >&2
    exit 68
}
VERIFY_ROOT="$(mktemp -d "$RUN_DIR/tmp/source-submit-verify.XXXXXX")"
trap 'rm -rf -- "$VERIFY_ROOT"' EXIT
tar -xzf "$ARCHIVE" -C "$VERIFY_ROOT"
diff -qr --no-dereference "$VERIFY_ROOT" "$RUN_DIR/source" >/dev/null || {
    echo "prepared source differs from the immutable archive" >&2
    exit 68
}
rm -rf -- "$VERIFY_ROOT"
trap - EXIT

CONFIG="$RUN_DIR/source/configs/model_mismatch_v2.toml"
[[ -s "$CONFIG" ]] || { echo "prepared source does not contain MM-2" >&2; exit 66; }
PLAN="$($MAGCORE_VENV/bin/python \
    "$RUN_DIR/source/scripts/model_mismatch_plan.py" plan --config "$CONFIG")"
EXPECTED_SELECTION_SHA="$(printf '%s' "$PLAN" | $MAGCORE_VENV/bin/python -c \
    'import json,sys; print(json.load(sys.stdin)["estimator_decision_sha256"])')"
EXPECTED_PREDECESSOR_SHA="$(printf '%s' "$PLAN" | $MAGCORE_VENV/bin/python -c \
    'import json,sys; print(json.load(sys.stdin)["lineage"]["predecessor_non_admission_sha256"])')"
TASK_COUNT="$(printf '%s' "$PLAN" | $MAGCORE_VENV/bin/python -c \
    'import json,sys; print(json.load(sys.stdin)["task_count"])')"
[[ "$TASK_COUNT" =~ ^[1-9][0-9]*$ ]] || { echo "invalid MM-2 task count" >&2; exit 65; }
[[ "$(sha256sum "$SELECTION" | awk '{print $1}')" == "$EXPECTED_SELECTION_SHA" ]] || {
    echo "estimator decision does not match the MM-2 preregistration" >&2
    exit 65
}
[[ "$(sha256sum "$PREDECESSOR" | awk '{print $1}')" == "$EXPECTED_PREDECESSOR_SHA" ]] || {
    echo "MM-1 closeout does not match the MM-2 preregistration" >&2
    exit 65
}
$MAGCORE_VENV/bin/python - "$PREDECESSOR" <<'PY'
import json, pathlib, sys
record = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
if record.get("campaign_id") != "MM-1" \
        or record.get("admission", {}).get("decision") != "not_admitted" \
        or record.get("admission", {}).get("confirmatory_claims_allowed") is not False:
    raise SystemExit("predecessor is not the final MM-1 non-admission record")
PY

record_submission_failure() {
    local stage="$1" exit_status="$2" array_job_id="$3" aggregate_job_id="$4"
    printf '{"stage":"%s","array_job_id":"%s","aggregate_job_id":"%s","exit_status":%s}\n' \
        "$stage" "$array_job_id" "$aggregate_job_id" "$exit_status" \
        > "$RUN_DIR/status/MM2_SUBMISSION_FAILED.partial"
    mv "$RUN_DIR/status/MM2_SUBMISSION_FAILED.partial" \
        "$RUN_DIR/status/MM2_SUBMISSION_FAILED"
}

DESTINATION="$RUN_DIR/summary/model_mismatch_v2"
mkdir -p "$DESTINATION"
for marker in MM2_ARRAY_SUBMITTED MM2_JOBS_ACCEPTED MM2_SUBMITTED; do
    [[ ! -e "$RUN_DIR/status/$marker" ]] || {
        echo "refusing to resubmit MM-2 with an existing scheduler marker: $marker" >&2
        exit 73
    }
done
for destination in estimator_decision.json predecessor_non_admission.json; do
    [[ ! -e "$DESTINATION/$destination" ]] || {
        echo "refusing to replace locked MM-2 input: $destination" >&2
        exit 73
    }
done
cp "$SELECTION" "$DESTINATION/estimator_decision.json"
cp "$PREDECESSOR" "$DESTINATION/predecessor_non_admission.json"
sha256sum "$DESTINATION/estimator_decision.json" \
    > "$DESTINATION/estimator_decision.sha256"
sha256sum "$DESTINATION/predecessor_non_admission.json" \
    > "$DESTINATION/predecessor_non_admission.sha256"

submit() {
    local dependency="$1" script="$2"
    shift 2
    local -a options=(--parsable --account="$MAGCORE_SUBMIT_ACCOUNT"
        --partition="$MAGCORE_SUBMIT_PARTITION"
        --output="$RUN_DIR/logs/%x_%A_%a.out")
    [[ -z "$dependency" ]] || options+=(--dependency="$dependency")
    options+=("$@")
    local response job_id status
    if response="$(sbatch "${options[@]}" "$RUN_DIR/source/slurm/$script" "$RUN_DIR")"; then
        :
    else
        status="$?"
        echo "scheduler rejected $script with exit status $status" >&2
        return "$status"
    fi
    if [[ "$response" =~ ^([1-9][0-9]*)(\;[A-Za-z0-9._-]+)?$ ]]; then
        job_id="${BASH_REMATCH[1]}"
    else
        echo "scheduler returned an invalid job ID for $script" >&2
        return 76
    fi
    printf '%s\n' "$job_id"
}

if ARRAY="$(submit "" 24_model_mismatch_v2.sbatch --array="0-$((TASK_COUNT - 1))%10")"; then
    :
else
    STATUS="$?"; record_submission_failure array "$STATUS" "" ""; exit "$STATUS"
fi
printf '{"array_job_id":"%s","task_count":%s}\n' "$ARRAY" "$TASK_COUNT" \
    > "$RUN_DIR/status/MM2_ARRAY_SUBMITTED.partial"
mv "$RUN_DIR/status/MM2_ARRAY_SUBMITTED.partial" "$RUN_DIR/status/MM2_ARRAY_SUBMITTED"
if AGGREGATE="$(submit "afterok:$ARRAY" 25_model_mismatch_v2_aggregate.sbatch)"; then
    :
else
    STATUS="$?"; record_submission_failure aggregate "$STATUS" "$ARRAY" ""; exit "$STATUS"
fi
printf '{"array_job_id":"%s","aggregate_job_id":"%s","task_count":%s}\n' \
    "$ARRAY" "$AGGREGATE" "$TASK_COUNT" > "$RUN_DIR/status/MM2_JOBS_ACCEPTED.partial"
mv "$RUN_DIR/status/MM2_JOBS_ACCEPTED.partial" "$RUN_DIR/status/MM2_JOBS_ACCEPTED"
{
    printf 'stage\tjob_id\tdependency\ttask_count\n'
    printf 'model_mismatch_v2\t%s\t-\t%s\n' "$ARRAY" "$TASK_COUNT"
    printf 'model_mismatch_v2_aggregate\t%s\tafterok:%s\t1\n' "$AGGREGATE" "$ARRAY"
} > "$RUN_DIR/provenance/model_mismatch_v2_jobs.tsv.partial"
mv "$RUN_DIR/provenance/model_mismatch_v2_jobs.tsv.partial" \
    "$RUN_DIR/provenance/model_mismatch_v2_jobs.tsv"
printf '{"array_job_id":"%s","aggregate_job_id":"%s","task_count":%s}\n' \
    "$ARRAY" "$AGGREGATE" "$TASK_COUNT" > "$RUN_DIR/status/MM2_SUBMITTED.partial"
mv "$RUN_DIR/status/MM2_SUBMITTED.partial" "$RUN_DIR/status/MM2_SUBMITTED"
printf 'Submitted MM-2 array: %s (%s tasks)\nAggregate job: %s\nRun: %s\n' \
    "$ARRAY" "$TASK_COUNT" "$AGGREGATE" "$RUN_DIR"
