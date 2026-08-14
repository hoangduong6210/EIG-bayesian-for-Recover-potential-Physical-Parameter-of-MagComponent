#!/usr/bin/env bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=4G
#SBATCH --time=00:30:00
#SBATCH --job-name=magcore-robust
#SBATCH --array=0-19%10

set -Eeuo pipefail
ROOT="$(cd "$1/source" && pwd -P)"
source "$ROOT/slurm/common.sh"
load_run "$1"
IDX="$SLURM_ARRAY_TASK_ID"
if (( IDX < 15 )); then
    OFFSET_INDEX=$((IDX / 5))
    SEED=$((42 + IDX % 5))
    OFFSETS=(0.0 0.15 0.30)
    OFFSET="${OFFSETS[$OFFSET_INDEX]}"
    init_task robustness "prior_offset${OFFSET}_seed${SEED}"
    OUT="$RESULT_DIR/prior_offset_${OFFSET}_seed${SEED}.json"
    run_experiment prior_offset posterior_recovery.py --seed "$SEED" --prior-offset "$OFFSET" \
        --n-walkers 48 --n-steps 5000 --burn 1000 --workers "$SLURM_CPUS_PER_TASK" --out "$OUT.partial"
else
    SEED=$((42 + IDX - 15))
    init_task robustness "lot_seed${SEED}"
    OUT="$RESULT_DIR/lot_seed${SEED}.json"
    run_experiment lot lot_variation.py --seed "$SEED" --n-walkers 16 --n-steps 5000 --burn 1000 \
        --out "$OUT.partial"
fi
validate_json "$OUT.partial"
mv "$OUT.partial" "$OUT"
task_done
