#!/usr/bin/env bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=12G
#SBATCH --time=02:00:00
#SBATCH --job-name=magcore-mu
#SBATCH --array=0-3%4

set -Eeuo pipefail
ROOT="$(cd "$1/source" && pwd -P)"
source "$ROOT/slurm/common.sh"
load_run "$1"
PAIRS=("N95:LEA_MTB" "N87:LEA_MTB" "N87:MagNet" "3C95:MagNet")
PAIR="${PAIRS[$SLURM_ARRAY_TASK_ID]}"
MATERIAL="${PAIR%%:*}"
SOURCE="${PAIR##*:}"
init_task measured_mu "${MATERIAL}_${SOURCE}"
STEM="$RESULT_DIR/measured_mu_${MATERIAL}_${SOURCE}"
run_experiment measured_mu real_data_recovery.py --material "$MATERIAL" --source "$SOURCE" \
    --workers "$SLURM_CPUS_PER_TASK" --n-walkers 48 --n-steps 5000 --burn 1000 --out "$STEM.partial"
validate_json "$STEM.partial.json"
mv "$STEM.partial.json" "$STEM.json"
[[ ! -f "$STEM.partial.png" ]] || mv "$STEM.partial.png" "$STEM.png"
task_done
