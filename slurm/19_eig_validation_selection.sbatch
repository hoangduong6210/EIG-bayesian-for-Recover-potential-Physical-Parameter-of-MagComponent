#!/usr/bin/env bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:15:00
#SBATCH --job-name=magcore-eig-val-select

set -Eeuo pipefail
ROOT="$(cd "$1/source" && pwd -P)"
source "$ROOT/slurm/common.sh"
load_run "$1"
init_task eig_validation_selection decision
OUT="$MAGCORE_RUN_DIR/summary/eig_convergence/static_decision.json"
mkdir -p "$(dirname "$OUT")"
run_experiment eig_validation_selection aggregate_eig_convergence.py \
    --run-dir "$MAGCORE_RUN_DIR" --out "$OUT.partial"
validate_json "$OUT.partial"
mv "$OUT.partial" "$OUT"
task_done
