#!/usr/bin/env bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=10G
#SBATCH --time=04:00:00
#SBATCH --job-name=magcore-sparsemix

set -Eeuo pipefail
ROOT="$(cd "$1/source" && pwd -P)"
source "$ROOT/slurm/common.sh"
load_run "$1"
CONFIG="$MAGCORE_CODE_ROOT/configs/sparse_mixing_v1.toml"
INPUT_ROOT="$MAGCORE_RUN_DIR/inputs/sparse_mixing"
python "$MAGCORE_CODE_ROOT/scripts/verify_sparse_mixing_inputs.py" \
    --config "$CONFIG" --input-root "$INPUT_ROOT"
eval "$(python "$MAGCORE_CODE_ROOT/scripts/sparse_mixing_plan.py" task \
    --config "$CONFIG" --task-id "$SLURM_ARRAY_TASK_ID" --format shell)"
init_task sparse_mixing "$TASK_ID"
OUT="$RESULT_DIR/result.json"
THIN="$RESULT_DIR/thin.npz"
run_experiment sparse_mixing sparse_mixing_diagnostic.py \
    --config "$CONFIG" --task-id "$SLURM_ARRAY_TASK_ID" \
    --mm2-source "$INPUT_ROOT/mm2_source" \
    --mm2-config "$INPUT_ROOT/mm2_config.toml" \
    --workers "$SLURM_CPUS_PER_TASK" --thin-out "$THIN" --out "$OUT.partial"
validate_json "$OUT.partial"
mv "$OUT.partial" "$OUT"
task_done
