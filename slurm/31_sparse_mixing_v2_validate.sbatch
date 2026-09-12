#!/usr/bin/env bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=32G
#SBATCH --time=02:00:00
#SBATCH --job-name=magcore-sparse-confirm-audit

set -Eeuo pipefail
ROOT="$(cd "$1/source" && pwd -P)"
source "$ROOT/slurm/common.sh"
load_run "$1"
export PYTHONPATH="$MAGCORE_CODE_ROOT:$MAGCORE_CODE_ROOT/src"
init_task sparse_mixing_v2_validate final
run_python scripts/validate_sparse_mixing_v2.py \
    --config configs/sparse_mixing_v2.toml \
    --results-root "$MAGCORE_RUN_DIR/results/sparse_mixing_v2" \
    --run-id "$MAGCORE_RUN_ID" --validator-revision "$MAGCORE_GIT_REVISION" \
    --out "$MAGCORE_RUN_DIR/summary/sparse_mixing_v2/manifest.json"
task_done
