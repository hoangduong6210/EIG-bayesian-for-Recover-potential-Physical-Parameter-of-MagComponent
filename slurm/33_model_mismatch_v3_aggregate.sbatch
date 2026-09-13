#!/usr/bin/env bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=64G
#SBATCH --time=00:30:00
#SBATCH --job-name=magcore-mm3-aggregate

set -Eeuo pipefail
ROOT="$(cd "$1/source" && pwd -P)"
source "$ROOT/slurm/common.sh"
load_run "$1"
init_task model_mismatch_v3_aggregate 0
CONFIG="$MAGCORE_CODE_ROOT/configs/model_mismatch_v3.toml"
OUT="$MAGCORE_RUN_DIR/summary/model_mismatch_v3/aggregate.json"
[[ ! -e "$OUT" ]] || {
    echo "FATAL: refusing to overwrite MM-3 aggregate: $OUT" >&2
    exit 73
}
run_experiment model_mismatch_v3_aggregate aggregate_model_mismatch.py \
    --input-dir "$MAGCORE_RUN_DIR/results/model_mismatch_v3" \
    --config "$CONFIG" --out "$OUT.partial"
validate_json "$OUT.partial"
mv "$OUT.partial" "$OUT"
task_done
