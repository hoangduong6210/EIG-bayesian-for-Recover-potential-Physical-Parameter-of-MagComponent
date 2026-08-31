#!/usr/bin/env bash
# Submit the diagnostic-only SparseMix-1 matrix from immutable inputs.

set -Eeuo pipefail
umask 027

if [[ $# -ne 2 ]]; then
    echo "usage: $0 PREPARED_RUN_DIR MM2_RUN_DIR" >&2
    exit 64
fi
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
RUN_DIR="$(cd "$1" && pwd -P)"
MM2_RUN="$(cd "$2" && pwd -P)"
case "$RUN_DIR/" in "$PROJECT_ROOT/runs/"*) ;; *)
    echo "prepared run is outside $PROJECT_ROOT/runs" >&2; exit 65;;
esac
[[ -f "$RUN_DIR/status/PREPARED" && -f "$RUN_DIR/provenance/run.env" ]] || {
    echo "prepared run is incomplete" >&2; exit 66;
}
for command in sbatch sha256sum tar diff mktemp; do
    command -v "$command" >/dev/null || { echo "missing command: $command" >&2; exit 69; }
done
for script in 26_sparse_mixing.sbatch 27_sparse_mixing_validate.sbatch; do
    bash -n "$RUN_DIR/source/slurm/$script"
done

# shellcheck disable=SC1090
source "$RUN_DIR/provenance/run.env"
CURRENT_ARCHIVE="$RUN_DIR/provenance/source-tree.tar.gz"
[[ "$(sha256sum "$CURRENT_ARCHIVE" | awk '{print $1}')" == "$MAGCORE_SOURCE_ARCHIVE_SHA256" ]] || {
    echo "prepared diagnostic source archive digest mismatch" >&2; exit 68;
}
VERIFY_ROOT="$(mktemp -d "$RUN_DIR/tmp/sparse-submit-verify.XXXXXX")"
trap 'rm -rf -- "$VERIFY_ROOT"' EXIT
tar -xzf "$CURRENT_ARCHIVE" -C "$VERIFY_ROOT"
diff -qr --no-dereference "$VERIFY_ROOT" "$RUN_DIR/source" >/dev/null || {
    echo "prepared diagnostic source differs from immutable archive" >&2; exit 68;
}
rm -rf -- "$VERIFY_ROOT"
trap - EXIT

CONFIG="$RUN_DIR/source/configs/sparse_mixing_v1.toml"
TASK_COUNT="$($MAGCORE_VENV/bin/python \
    "$RUN_DIR/source/scripts/sparse_mixing_plan.py" plan --config "$CONFIG" | \
    $MAGCORE_VENV/bin/python -c 'import json,sys; print(json.load(sys.stdin)["task_count"])')"
[[ "$TASK_COUNT" == "18" ]] || { echo "invalid SparseMix-1 task count" >&2; exit 65; }

INPUT_ROOT="$RUN_DIR/inputs/sparse_mixing"
[[ ! -e "$INPUT_ROOT" ]] || {
    echo "refusing to replace locked SparseMix-1 inputs" >&2; exit 73;
}
mkdir -p "$INPUT_ROOT/mm2_source"
cp "$MM2_RUN/provenance/source-tree.tar.gz" "$INPUT_ROOT/mm2_source.tar.gz"
cp "$MM2_RUN/source/configs/model_mismatch_v2.toml" "$INPUT_ROOT/mm2_config.toml"
cp "$MM2_RUN/status/model_mismatch_v2_rejections/combined_mismatch_seed9123.json" \
    "$INPUT_ROOT/mm2_rejection.json"
cp "$MM2_RUN/status/model_mismatch_v2_combined_mismatch_seed9123.failed" \
    "$INPUT_ROOT/mm2_failed_marker.json"
cp "$RUN_DIR/source/results/diagnostics/model_mismatch/MM-2/20260829T041912Z_002a58340aa0/non_admission.json" \
    "$INPUT_ROOT/mm2_closeout.json"
tar -xzf "$INPUT_ROOT/mm2_source.tar.gz" -C "$INPUT_ROOT/mm2_source"
$MAGCORE_VENV/bin/python "$RUN_DIR/source/scripts/verify_sparse_mixing_inputs.py" \
    --config "$CONFIG" --input-root "$INPUT_ROOT"
find "$INPUT_ROOT" -type f -print0 | sort -z | xargs -0 sha256sum \
    > "$RUN_DIR/provenance/sparse_mixing_inputs.sha256"

for marker in SPARSEMIX_ARRAY_SUBMITTED SPARSEMIX_JOBS_ACCEPTED SPARSEMIX_SUBMITTED; do
    [[ ! -e "$RUN_DIR/status/$marker" ]] || {
        echo "refusing to resubmit SparseMix-1: $marker exists" >&2; exit 73;
    }
done

record_submission_failure() {
    local stage="$1" exit_status="$2" array_job_id="$3" validator_job_id="$4"
    printf '{"stage":"%s","array_job_id":"%s","validator_job_id":"%s","exit_status":%s}\n' \
        "$stage" "$array_job_id" "$validator_job_id" "$exit_status" \
        > "$RUN_DIR/status/SPARSEMIX_SUBMISSION_FAILED.partial"
    mv "$RUN_DIR/status/SPARSEMIX_SUBMISSION_FAILED.partial" \
        "$RUN_DIR/status/SPARSEMIX_SUBMISSION_FAILED"
}

submit() {
    local dependency="$1" script="$2"
    shift 2
    local -a options=(--parsable --account="$MAGCORE_SUBMIT_ACCOUNT"
        --partition="$MAGCORE_SUBMIT_PARTITION"
        --output="$RUN_DIR/logs/%x_%A_%a.out")
    [[ -z "$dependency" ]] || options+=(--dependency="$dependency")
    options+=("$@")
    local response job_id
    response="$(sbatch "${options[@]}" "$RUN_DIR/source/slurm/$script" "$RUN_DIR")"
    [[ "$response" =~ ^([1-9][0-9]*)(\;[A-Za-z0-9._-]+)?$ ]] || {
        echo "scheduler returned an invalid job ID for $script" >&2; return 76;
    }
    job_id="${BASH_REMATCH[1]}"
    printf '%s\n' "$job_id"
}

if ARRAY="$(submit "" 26_sparse_mixing.sbatch --array="0-$((TASK_COUNT - 1))%8")"; then
    :
else
    STATUS="$?"
    record_submission_failure array "$STATUS" "" ""
    exit "$STATUS"
fi
printf '{"array_job_id":"%s","task_count":%s}\n' "$ARRAY" "$TASK_COUNT" \
    > "$RUN_DIR/status/SPARSEMIX_ARRAY_SUBMITTED.partial"
mv "$RUN_DIR/status/SPARSEMIX_ARRAY_SUBMITTED.partial" \
    "$RUN_DIR/status/SPARSEMIX_ARRAY_SUBMITTED"
if VALIDATOR="$(submit "afterok:$ARRAY" 27_sparse_mixing_validate.sbatch)"; then
    :
else
    STATUS="$?"
    record_submission_failure validator "$STATUS" "$ARRAY" ""
    exit "$STATUS"
fi
printf '{"array_job_id":"%s","validator_job_id":"%s","task_count":%s}\n' \
    "$ARRAY" "$VALIDATOR" "$TASK_COUNT" \
    > "$RUN_DIR/status/SPARSEMIX_JOBS_ACCEPTED.partial"
mv "$RUN_DIR/status/SPARSEMIX_JOBS_ACCEPTED.partial" \
    "$RUN_DIR/status/SPARSEMIX_JOBS_ACCEPTED"
{
    printf 'stage\tjob_id\tdependency\ttask_count\n'
    printf 'sparse_mixing\t%s\t-\t%s\n' "$ARRAY" "$TASK_COUNT"
    printf 'sparse_mixing_validate\t%s\tafterok:%s\t1\n' "$VALIDATOR" "$ARRAY"
} > "$RUN_DIR/provenance/sparse_mixing_jobs.tsv.partial"
mv "$RUN_DIR/provenance/sparse_mixing_jobs.tsv.partial" \
    "$RUN_DIR/provenance/sparse_mixing_jobs.tsv"
printf '{"array_job_id":"%s","validator_job_id":"%s","task_count":%s}\n' \
    "$ARRAY" "$VALIDATOR" "$TASK_COUNT" \
    > "$RUN_DIR/status/SPARSEMIX_SUBMITTED.partial"
mv "$RUN_DIR/status/SPARSEMIX_SUBMITTED.partial" "$RUN_DIR/status/SPARSEMIX_SUBMITTED"
printf 'Submitted SparseMix-1 diagnostic array: %s (%s tasks)\nValidator job: %s\nRun: %s\n' \
    "$ARRAY" "$TASK_COUNT" "$VALIDATOR" "$RUN_DIR"
