#!/usr/bin/env bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=01:00:00
#SBATCH --job-name=magcore-pilot-validate

set -Eeuo pipefail
[[ -n "${SLURM_JOB_ID:-}" && -n "${SLURM_JOB_NODELIST:-}" ]] || exit 70
PILOT_RUN="$(cd "$1" && pwd -P)"
VALIDATOR_ROOT="$(cd "$2" && pwd -P)"
source "$PILOT_RUN/provenance/run.env"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$VALIDATOR_ROOT:$VALIDATOR_ROOT/src"
VALIDATOR_REVISION="$(git -C "$VALIDATOR_ROOT" rev-parse HEAD)"
[[ -z "$(git -C "$VALIDATOR_ROOT" status --porcelain --untracked-files=all)" ]] || exit 65
mkdir -p "$PILOT_RUN/summary/sparse_pilot"
"$MAGCORE_VENV/bin/python" "$VALIDATOR_ROOT/scripts/validate_sparse_pilot.py" \
    --config "$PILOT_RUN/source/configs/sparse_mixing_pilot.toml" \
    --results-root "$PILOT_RUN/results/sparse_pilot" \
    --validator-revision "$VALIDATOR_REVISION" --run-id "$MAGCORE_RUN_ID" \
    --out "$PILOT_RUN/summary/sparse_pilot/manifest.json"
