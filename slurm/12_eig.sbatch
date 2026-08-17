#!/usr/bin/env bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=8G
#SBATCH --time=12:00:00
#SBATCH --job-name=magcore-eig
#SBATCH --array=0-29%10

set -Eeuo pipefail
ROOT="$(cd "$1/source" && pwd -P)"
source "$ROOT/slurm/common.sh"
load_run "$1"
eval "$(python "$ROOT/scripts/study_plan.py" acquisition \
    --config "$MAGCORE_RUN_DIR/config/default.toml" \
    --task-id "$SLURM_ARRAY_TASK_ID" --format shell)"
init_task eig "seed${SEED}"
OUT="$RESULT_DIR/eig_seed${SEED}.json"
SELECTION="$MAGCORE_RUN_DIR/summary/eig_convergence/final_decision.json"
[[ -s "$SELECTION" ]] || {
    echo "FATAL: missing frozen estimator decision: $SELECTION" >&2
    exit 66
}
run_experiment eig eig_efficiency.py --seed "$SEED" --workers "$SLURM_CPUS_PER_TASK" \
    --max-meas 25 --n-walkers 48 --n-steps 20000 --burn 4000 \
    --eig-objectives raw per_cost \
    --config "$MAGCORE_RUN_DIR/config/default.toml" \
    --selection-file "$SELECTION" \
    --out "$OUT.partial"
validate_json "$OUT.partial"
mv "$OUT.partial" "$OUT"
task_done
