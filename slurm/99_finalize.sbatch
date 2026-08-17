#!/usr/bin/env bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=1G
#SBATCH --time=00:10:00
#SBATCH --job-name=magcore-final
#SBATCH --mail-type=END,FAIL

set -Eeuo pipefail
ROOT="$(cd "$1/source" && pwd -P)"
source "$ROOT/slurm/common.sh"
load_run "$1"
init_task finalize 0
# A post-processing retry may follow a failed publication gate after all
# scientific artifacts were already frozen. Replace, rather than accumulate,
# terminal markers so a run can never advertise both SUCCESS and FAILED.
rm -f "$MAGCORE_RUN_DIR/status/SUCCESS" "$MAGCORE_RUN_DIR/status/FAILED"
if [[ -f "$MAGCORE_RUN_DIR/status/paper_0.done" ]]; then
    printf '{"run_id":"%s","state":"SUCCESS","job_id":"%s","ended_at":"%s"}\n' \
        "$MAGCORE_RUN_ID" "$SLURM_JOB_ID" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        > "$MAGCORE_RUN_DIR/status/final.json.partial"
    mv "$MAGCORE_RUN_DIR/status/final.json.partial" "$MAGCORE_RUN_DIR/status/final.json"
    touch "$MAGCORE_RUN_DIR/status/SUCCESS"
    task_done
    exit 0
fi
printf '{"run_id":"%s","state":"FAILED","job_id":"%s","ended_at":"%s"}\n' \
    "$MAGCORE_RUN_ID" "$SLURM_JOB_ID" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    > "$MAGCORE_RUN_DIR/status/final.json.partial"
mv "$MAGCORE_RUN_DIR/status/final.json.partial" "$MAGCORE_RUN_DIR/status/final.json"
touch "$MAGCORE_RUN_DIR/status/FAILED"
exit 1
