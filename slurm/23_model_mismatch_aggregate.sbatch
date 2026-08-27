#!/usr/bin/env bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=00:30:00
#SBATCH --job-name=magcore-mm1-aggregate

set -Eeuo pipefail
ROOT="$(cd "$1/source" && pwd -P)"
source "$ROOT/slurm/common.sh"
load_run "$1"
init_task model_mismatch_aggregate 0
CONFIG="$MAGCORE_CODE_ROOT/configs/model_mismatch.toml"
OUT="$MAGCORE_RUN_DIR/summary/model_mismatch/aggregate.json"
[[ ! -e "$OUT" ]] || {
    echo "FATAL: refusing to overwrite MM-1 aggregate: $OUT" >&2
    exit 73
}
run_experiment model_mismatch_aggregate aggregate_model_mismatch.py \
    --input-dir "$MAGCORE_RUN_DIR/results/model_mismatch" \
    --config "$CONFIG" --out "$OUT.partial"
validate_json "$OUT.partial"
mv "$OUT.partial" "$OUT"
task_done
