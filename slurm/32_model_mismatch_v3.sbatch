#!/usr/bin/env bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=64G
#SBATCH --time=24:00:00
#SBATCH --job-name=magcore-mm3

set -Eeuo pipefail
ROOT="$(cd "$1/source" && pwd -P)"
source "$ROOT/slurm/common.sh"
load_run "$1"
CONFIG="$MAGCORE_CODE_ROOT/configs/model_mismatch_v3.toml"
eval "$(python "$MAGCORE_CODE_ROOT/scripts/model_mismatch_plan.py" task \
    --config "$CONFIG" --task-id "$SLURM_ARRAY_TASK_ID" --format shell)"
init_task model_mismatch_v3 "$TASK_ID"
SELECTION="$MAGCORE_RUN_DIR/summary/model_mismatch_v3/estimator_decision.json"
[[ -s "$SELECTION" ]] || {
    echo "FATAL: missing locked estimator decision: $SELECTION" >&2
    exit 66
}
REJECTION_DIR="$MAGCORE_RUN_DIR/status/model_mismatch_v3_rejections"
mkdir -p "$REJECTION_DIR"
OUT="$RESULT_DIR/result.json"
[[ ! -e "$OUT" && ! -e "$OUT.partial" && ! -e "$REJECTION_DIR/$TASK_ID.json" ]] || {
    echo "FATAL: refusing to replace MM-3 task artifacts" >&2
    exit 73
}
run_experiment model_mismatch_v3 model_mismatch_campaign.py \
    --seed "$SEED" --scenario "$SCENARIO" --workers 1 \
    --config "$CONFIG" --selection-file "$SELECTION" \
    --rejection-out "$REJECTION_DIR/$TASK_ID.json" --out "$OUT.partial"
validate_json "$OUT.partial"
mv "$OUT.partial" "$OUT"
task_done
