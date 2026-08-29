#!/usr/bin/env bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=10G
#SBATCH --time=18:00:00
#SBATCH --job-name=magcore-mm2

set -Eeuo pipefail
ROOT="$(cd "$1/source" && pwd -P)"
source "$ROOT/slurm/common.sh"
load_run "$1"
CONFIG="$MAGCORE_CODE_ROOT/configs/model_mismatch_v2.toml"
eval "$(python "$MAGCORE_CODE_ROOT/scripts/model_mismatch_plan.py" task \
    --config "$CONFIG" --task-id "$SLURM_ARRAY_TASK_ID" --format shell)"
init_task model_mismatch_v2 "$TASK_ID"
SELECTION="$MAGCORE_RUN_DIR/summary/model_mismatch_v2/estimator_decision.json"
[[ -s "$SELECTION" ]] || {
    echo "FATAL: missing locked estimator decision: $SELECTION" >&2
    exit 66
}
REJECTION_DIR="$MAGCORE_RUN_DIR/status/model_mismatch_v2_rejections"
mkdir -p "$REJECTION_DIR"
OUT="$RESULT_DIR/result.json"
run_experiment model_mismatch_v2 model_mismatch_campaign.py \
    --seed "$SEED" --scenario "$SCENARIO" --workers "$SLURM_CPUS_PER_TASK" \
    --config "$CONFIG" --selection-file "$SELECTION" \
    --rejection-out "$REJECTION_DIR/$TASK_ID.json" --out "$OUT.partial"
validate_json "$OUT.partial"
mv "$OUT.partial" "$OUT"
task_done
