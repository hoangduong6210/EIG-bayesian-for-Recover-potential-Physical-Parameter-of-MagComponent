#!/usr/bin/env bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --job-name=magcore-pcv
#SBATCH --array=0-3%4

set -Eeuo pipefail
ROOT="$(cd "$1/source" && pwd -P)"
source "$ROOT/slurm/common.sh"
load_run "$1"
MATERIALS=(N49 N87 N95 3C95)
MATERIAL="${MATERIALS[$SLURM_ARRAY_TASK_ID]}"
init_task measured_pcv "$MATERIAL"
STEM="$RESULT_DIR/measured_pcv_${MATERIAL}"
run_experiment measured_pcv real_data_pcv.py --material "$MATERIAL" --workers "$SLURM_CPUS_PER_TASK" \
    --n-walkers 48 --n-steps 5000 --burn 1000 --out "$STEM.partial"
validate_json "$STEM.partial.json"
mv "$STEM.partial.json" "$STEM.json"
[[ ! -f "$STEM.partial.png" ]] || mv "$STEM.partial.png" "$STEM.png"
task_done
