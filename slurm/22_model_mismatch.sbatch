#!/usr/bin/env bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=10G
#SBATCH --time=18:00:00
#SBATCH --job-name=magcore-mm1

set -Eeuo pipefail
ROOT="$(cd "$1/source" && pwd -P)"
source "$ROOT/slurm/common.sh"
load_run "$1"
CONFIG="$MAGCORE_CODE_ROOT/configs/model_mismatch.toml"
eval "$(python "$MAGCORE_CODE_ROOT/scripts/model_mismatch_plan.py" task \
    --config "$CONFIG" --task-id "$SLURM_ARRAY_TASK_ID" --format shell)"
init_task model_mismatch "$TASK_ID"
SELECTION="$MAGCORE_RUN_DIR/summary/model_mismatch/estimator_decision.json"
[[ -s "$SELECTION" ]] || {
    echo "FATAL: missing locked estimator decision: $SELECTION" >&2
    exit 66
}
OUT="$RESULT_DIR/result.json"
run_experiment model_mismatch model_mismatch_campaign.py \
    --seed "$SEED" --scenario "$SCENARIO" --workers "$SLURM_CPUS_PER_TASK" \
    --config "$CONFIG" --selection-file "$SELECTION" --out "$OUT.partial"
validate_json "$OUT.partial"
mv "$OUT.partial" "$OUT"
task_done
