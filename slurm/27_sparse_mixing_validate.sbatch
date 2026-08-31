#!/usr/bin/env bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=00:20:00
#SBATCH --job-name=magcore-sparsemix-validate

set -Eeuo pipefail
ROOT="$(cd "$1/source" && pwd -P)"
source "$ROOT/slurm/common.sh"
load_run "$1"
CONFIG="$MAGCORE_CODE_ROOT/configs/sparse_mixing_v1.toml"
INPUT_ROOT="$MAGCORE_RUN_DIR/inputs/sparse_mixing"
python "$MAGCORE_CODE_ROOT/scripts/verify_sparse_mixing_inputs.py" \
    --config "$CONFIG" --input-root "$INPUT_ROOT"
init_task sparse_mixing_validate 0
DESTINATION="$MAGCORE_RUN_DIR/summary/sparse_mixing"
mkdir -p "$DESTINATION"
OUT="$DESTINATION/manifest.json"
run_python "$MAGCORE_CODE_ROOT/scripts/validate_sparse_mixing.py" \
    --config "$CONFIG" \
    --results-root "$MAGCORE_RUN_DIR/results/sparse_mixing" \
    --rejection "$INPUT_ROOT/mm2_rejection.json" --out "$OUT.partial"
validate_json "$OUT.partial"
mv "$OUT.partial" "$OUT"
task_done
