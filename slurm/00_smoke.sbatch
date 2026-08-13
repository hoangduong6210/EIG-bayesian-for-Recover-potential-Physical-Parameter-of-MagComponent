#!/usr/bin/env bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=4G
#SBATCH --time=00:15:00
#SBATCH --job-name=magcore-smoke

set -Eeuo pipefail
ROOT="$(cd "$1/source" && pwd -P)"
# shellcheck disable=SC1091
source "$ROOT/slurm/common.sh"
load_run "$1"
init_task smoke 0

run_python -m pytest "$MAGCORE_CODE_ROOT/tests" -q -p no:cacheprovider
run_python -c 'import magcore_calib; print("magcore_calib", magcore_calib.__version__)'
task_done
