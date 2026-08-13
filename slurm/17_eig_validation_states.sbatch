#!/usr/bin/env bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=8G
#SBATCH --time=01:00:00
#SBATCH --job-name=magcore-eig-val-state
#SBATCH --array=0-11%12

set -Eeuo pipefail
ROOT="$(cd "$1/source" && pwd -P)"
source "$ROOT/slurm/common.sh"
load_run "$1"
eval "$(python "$ROOT/scripts/study_plan.py" state \
    --config "$MAGCORE_RUN_DIR/config/default.toml" \
    --task-id "$SLURM_ARRAY_TASK_ID" --format shell)"
init_task eig_validation_states "$STATE_ID"
STATE="$RESULT_DIR/state.json"
SAMPLES="$RESULT_DIR/samples.npz"
run_experiment eig_validation_states eig_convergence_states.py \
    --seed "$SEED" --n-observations "$N_OBSERVATIONS" \
    --n-walkers 48 --n-steps 5000 --burn 1000 \
    --samples-out "$RESULT_DIR/samples.partial.npz" --out "$STATE.partial"
validate_json "$STATE.partial"
[[ -s "$RESULT_DIR/samples.partial.npz" ]]
mv "$RESULT_DIR/samples.partial.npz" "$SAMPLES"
mv "$STATE.partial" "$STATE"
task_done
