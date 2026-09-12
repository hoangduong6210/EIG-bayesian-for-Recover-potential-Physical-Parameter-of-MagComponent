#!/usr/bin/env bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=6G
#SBATCH --time=02:00:00
#SBATCH --job-name=magcore-sparse-pilot

set -Eeuo pipefail
ROOT="$(cd "$1/source" && pwd -P)"
source "$ROOT/slurm/common.sh"
load_run "$1"
INPUT_ROOT="$MAGCORE_RUN_DIR/inputs/sparse_mixing"
python scripts/verify_sparse_mixing_inputs.py \
    --config configs/sparse_mixing_v1.toml --input-root "$INPUT_ROOT"
init_task sparse_pilot "$SLURM_ARRAY_TASK_ID"
run_python experiments/sparse_mixing_pilot.py \
    --config configs/sparse_mixing_pilot.toml --task-id "$SLURM_ARRAY_TASK_ID" \
    --mm2-source "$INPUT_ROOT/mm2_source" \
    --mm2-config "$INPUT_ROOT/mm2_config.toml" --out-dir "$RESULT_DIR"
task_done
