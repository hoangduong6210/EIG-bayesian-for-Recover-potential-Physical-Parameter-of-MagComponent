#!/usr/bin/env bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=8G
#SBATCH --time=12:00:00
#SBATCH --job-name=magcore-eig-val-down
#SBATCH --array=0-9%10

set -Eeuo pipefail
ROOT="$(cd "$1/source" && pwd -P)"
source "$ROOT/slurm/common.sh"
load_run "$1"
eval "$(python "$ROOT/scripts/study_plan.py" downstream \
    --config "$MAGCORE_RUN_DIR/config/default.toml" \
    --task-id "$SLURM_ARRAY_TASK_ID" --format shell)"
init_task eig_validation_downstream "$TASK_ID"
SELECTION="$MAGCORE_RUN_DIR/summary/eig_convergence/static_decision.json"
OUT="$RESULT_DIR/downstream.json"
[[ -s "$SELECTION" ]]
run_experiment eig_validation_downstream eig_convergence_downstream.py \
    --seed "$SEED" --selection "$SELECTION" --workers "$SLURM_CPUS_PER_TASK" \
    --max-meas 25 --n-walkers 48 --n-steps 5000 --burn 1000 \
    --out "$OUT.partial"
validate_json "$OUT.partial"
mv "$OUT.partial" "$OUT"
task_done
