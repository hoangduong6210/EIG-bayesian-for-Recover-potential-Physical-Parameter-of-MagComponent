#!/usr/bin/env bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=2G
#SBATCH --time=00:15:00
#SBATCH --job-name=magcore-audit

set -Eeuo pipefail
ROOT="$(cd "$1/source" && pwd -P)"
source "$ROOT/slurm/common.sh"
load_run "$1"
init_task audit 0
run_python "$MAGCORE_CODE_ROOT/scripts/validate_run.py" --run-dir "$MAGCORE_RUN_DIR" --mode audit
task_done
