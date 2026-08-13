#!/usr/bin/env bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=12G
#SBATCH --time=18:00:00
#SBATCH --job-name=magcore-eig-val-ref
#SBATCH --array=0-11%12

set -Eeuo pipefail
ROOT="$(cd "$1/source" && pwd -P)"
source "$ROOT/slurm/common.sh"
load_run "$1"
eval "$(python "$ROOT/scripts/study_plan.py" reference \
    --config "$MAGCORE_RUN_DIR/config/default.toml" \
    --task-id "$SLURM_ARRAY_TASK_ID" --format shell)"
init_task eig_validation_reference "$SCORE_ID"
STATE_DIR="$MAGCORE_RUN_DIR/results/eig_validation_states/$STATE_ID"
OUT="$RESULT_DIR/score.json"
[[ -s "$STATE_DIR/state.json" && -s "$STATE_DIR/samples.npz" ]]
run_experiment eig_validation_reference eig_convergence_scores.py \
    --state "$STATE_DIR/state.json" --samples "$STATE_DIR/samples.npz" \
    --n-outer "$N_OUTER" --n-inner "$N_INNER" --replicates "$N_REPLICATES" \
    --namespace reference --out "$OUT.partial"
validate_json "$OUT.partial"
mv "$OUT.partial" "$OUT"
task_done
