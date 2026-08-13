#!/usr/bin/env bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=12G
#SBATCH --time=00:45:00
#SBATCH --job-name=magcore-real-eig
#SBATCH --array=0-1%2

set -Eeuo pipefail
ROOT="$(cd "$1/source" && pwd -P)"
source "$ROOT/slurm/common.sh"
load_run "$1"
MATERIALS=(N95 N87)
MATERIAL="${MATERIALS[$SLURM_ARRAY_TASK_ID]}"
SOURCE=LEA_MTB
init_task measured_eig "${MATERIAL}_${SOURCE}"
STEM="$RESULT_DIR/measured_eig_${MATERIAL}_${SOURCE}"
run_experiment measured_eig eig_real.py --material "$MATERIAL" --source "$SOURCE" \
    --workers "$SLURM_CPUS_PER_TASK" --n-walkers 48 --n-steps 5000 --burn 1000 \
    --n-outer 300 --n-inner 80 --eig-replicates 20 --out "$STEM.partial"
validate_json "$STEM.partial.json"
mv "$STEM.partial.json" "$STEM.json"
[[ ! -f "$STEM.partial.png" ]] || mv "$STEM.partial.png" "$STEM.png"
task_done
