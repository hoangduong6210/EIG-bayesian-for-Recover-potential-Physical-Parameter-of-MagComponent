#!/usr/bin/env bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=00:20:00
#SBATCH --job-name=magcore-aggregate

set -Eeuo pipefail
ROOT="$(cd "$1/source" && pwd -P)"
source "$ROOT/slurm/common.sh"
load_run "$1"
init_task aggregate 0
run_python "$MAGCORE_CODE_ROOT/scripts/validate_run.py" --run-dir "$MAGCORE_RUN_DIR" --mode aggregate
run_python "$MAGCORE_CODE_ROOT/scripts/generate_paper_artifacts.py" --run-dir "$MAGCORE_RUN_DIR"
[[ -s "$MAGCORE_RUN_DIR/summary/frozen_result_macros.tex" ]]
[[ -s "$MAGCORE_RUN_DIR/summary/frozen_results.tex" ]]
[[ -s "$MAGCORE_RUN_DIR/figures/synthetic_results.pdf" ]]
[[ -s "$MAGCORE_RUN_DIR/figures/acquisition_measured_results.pdf" ]]
task_done
