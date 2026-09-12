#!/usr/bin/env bash
# Submit the technical pilot from a prepared immutable source revision.
set -Eeuo pipefail
umask 027
[[ $# == 2 ]] || { echo "usage: $0 PREPARED_RUN SPARSEMIX1_RUN" >&2; exit 64; }
PILOT_RUN="$(cd "$1" && pwd -P)"
PARENT_RUN="$(cd "$2" && pwd -P)"
[[ -f "$PILOT_RUN/status/PREPARED" ]] || exit 66
source "$PILOT_RUN/provenance/run.env"
[[ ! -e "$PILOT_RUN/status/PILOT_SUBMISSION_STARTED" ]] || {
    echo "pilot submission already attempted" >&2; exit 73;
}
[[ ! -e "$PILOT_RUN/inputs/sparse_mixing" ]] || exit 73
mkdir -p "$PILOT_RUN/inputs"
cp -a "$PARENT_RUN/inputs/sparse_mixing" "$PILOT_RUN/inputs/sparse_mixing"
"$MAGCORE_VENV/bin/python" "$PILOT_RUN/source/scripts/verify_sparse_mixing_inputs.py" \
    --config "$PILOT_RUN/source/configs/sparse_mixing_v1.toml" \
    --input-root "$PILOT_RUN/inputs/sparse_mixing"
touch "$PILOT_RUN/status/PILOT_SUBMISSION_STARTED"
PILOT_ARRAY="$(sbatch --parsable --account="$MAGCORE_SUBMIT_ACCOUNT" \
    --partition="$MAGCORE_SUBMIT_PARTITION" --array=0-23%8 \
    --output="$PILOT_RUN/logs/%x_%A_%a.out" \
    "$PILOT_RUN/source/slurm/28_sparse_pilot.sbatch" "$PILOT_RUN")"
PILOT_ARRAY="${PILOT_ARRAY%%;*}"
[[ "$PILOT_ARRAY" =~ ^[1-9][0-9]*$ ]] || exit 76
printf '%s\n' "$PILOT_ARRAY" > "$PILOT_RUN/status/PILOT_ARRAY_SUBMITTED"
printf 'Pilot array %s: %s\n' "$PILOT_ARRAY" "$PILOT_RUN"
