#!/usr/bin/env bash
# Submit only a registered confirmatory sampler study; no scientific endpoints.
set -Eeuo pipefail
umask 027
[[ $# == 2 ]] || { echo "usage: $0 PREPARED_RUN SPARSEMIX1_RUN" >&2; exit 64; }
CONFIRM_RUN="$(cd "$1" && pwd -P)"
PARENT_RUN="$(cd "$2" && pwd -P)"
[[ -f "$CONFIRM_RUN/status/PREPARED" ]] || exit 66
source "$CONFIRM_RUN/provenance/run.env"
[[ ! -e "$CONFIRM_RUN/status/SPARSEMIX2_SUBMISSION_STARTED" ]] || exit 73
[[ ! -e "$CONFIRM_RUN/inputs/sparse_mixing" ]] || exit 73
export PYTHONPATH="$CONFIRM_RUN/source:$CONFIRM_RUN/source/src"
export PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1
# Validate decision hashes and prospective criteria before any submission.
"$MAGCORE_VENV/bin/python" -c \
    'import sys; from pathlib import Path; from experiments.sparse_mixing_v2 import load_config, tasks; assert len(tasks(load_config(Path(sys.argv[1])))) == 16' \
    "$CONFIRM_RUN/source/configs/sparse_mixing_v2.toml"
mkdir -p "$CONFIRM_RUN/inputs"
cp -a "$PARENT_RUN/inputs/sparse_mixing" "$CONFIRM_RUN/inputs/sparse_mixing"
"$MAGCORE_VENV/bin/python" "$CONFIRM_RUN/source/scripts/verify_sparse_mixing_inputs.py" \
    --config "$CONFIRM_RUN/source/configs/sparse_mixing_v1.toml" \
    --input-root "$CONFIRM_RUN/inputs/sparse_mixing"
touch "$CONFIRM_RUN/status/SPARSEMIX2_SUBMISSION_STARTED"
trap 'printf "submission failed; inspect saved job markers before retrying\n" > "$CONFIRM_RUN/status/SUBMISSION_FAILED"' ERR
CONFIRM_ARRAY="$(sbatch --parsable --account="$MAGCORE_SUBMIT_ACCOUNT" \
    --partition="$MAGCORE_SUBMIT_PARTITION" --array=0-15%8 \
    --output="$CONFIRM_RUN/logs/%x_%A_%a.out" \
    "$CONFIRM_RUN/source/slurm/30_sparse_mixing_v2.sbatch" "$CONFIRM_RUN")"
CONFIRM_ARRAY="${CONFIRM_ARRAY%%;*}"
[[ "$CONFIRM_ARRAY" =~ ^[1-9][0-9]*$ ]] || exit 76
printf '%s\n' "$CONFIRM_ARRAY" > "$CONFIRM_RUN/status/SPARSEMIX2_ARRAY_SUBMITTED"
CONFIRM_VALIDATOR="$(sbatch --parsable --account="$MAGCORE_SUBMIT_ACCOUNT" \
    --partition="$MAGCORE_SUBMIT_PARTITION" --dependency="afterok:$CONFIRM_ARRAY" \
    --output="$CONFIRM_RUN/logs/%x_%j.out" \
    "$CONFIRM_RUN/source/slurm/31_sparse_mixing_v2_validate.sbatch" "$CONFIRM_RUN")"
CONFIRM_VALIDATOR="${CONFIRM_VALIDATOR%%;*}"
[[ "$CONFIRM_VALIDATOR" =~ ^[1-9][0-9]*$ ]] || exit 76
printf '%s\n' "$CONFIRM_VALIDATOR" > "$CONFIRM_RUN/status/SPARSEMIX2_VALIDATOR_SUBMITTED"
printf 'SparseMix-2 array %s; validator %s: %s\n' "$CONFIRM_ARRAY" "$CONFIRM_VALIDATOR" "$CONFIRM_RUN"
