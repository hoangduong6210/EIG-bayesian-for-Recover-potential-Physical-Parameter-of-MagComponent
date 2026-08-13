#!/usr/bin/env bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=4G
#SBATCH --time=00:30:00
#SBATCH --job-name=magcore-post
#SBATCH --array=0-4%5

set -Eeuo pipefail
ROOT="$(cd "$1/source" && pwd -P)"
source "$ROOT/slurm/common.sh"
load_run "$1"
SEED=$((42 + SLURM_ARRAY_TASK_ID))
init_task posterior "seed${SEED}"
OUT="$RESULT_DIR/posterior_seed${SEED}.json"
run_experiment posterior posterior_recovery.py --seed "$SEED" --n-walkers 48 --n-steps 5000 --burn 1000 \
    --workers "$SLURM_CPUS_PER_TASK" --out "$OUT.partial"
validate_json "$OUT.partial"
mv "$OUT.partial" "$OUT"
task_done
