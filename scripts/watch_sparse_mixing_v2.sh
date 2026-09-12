#!/usr/bin/env bash
# Read-only watcher: completion of compute is distinct from scientific passage.
set -Eeuo pipefail
[[ $# == 1 ]] || { echo "usage: $0 CONFIRMATORY_RUN" >&2; exit 64; }
CONFIRM_RUN="$(cd "$1" && pwd -P)"
source "$CONFIRM_RUN/provenance/run.env"
[[ -f "$CONFIRM_RUN/status/SPARSEMIX2_VALIDATOR_SUBMITTED" ]] || exit 66
CONFIRM_VALIDATOR="$(<"$CONFIRM_RUN/status/SPARSEMIX2_VALIDATOR_SUBMITTED")"
while :; do
    if [[ -f "$CONFIRM_RUN/summary/sparse_mixing_v2/manifest.json" ]]; then
        "$MAGCORE_VENV/bin/python" -c \
            'import json,sys; r=json.load(open(sys.argv[1])); print("SparseMix-2 audit completed; both_states_pass=" + str(r["both_states_pass"])); [print(k + ": " + v["classification"]) for k,v in r["classifications"].items()]' \
            "$CONFIRM_RUN/summary/sparse_mixing_v2/manifest.json"
        exit 0
    fi
    if [[ -f "$CONFIRM_RUN/status/SUBMISSION_FAILED" ]] || \
       find "$CONFIRM_RUN/status" -maxdepth 1 -name '*.failed' -print -quit | grep -q .; then
        echo "SparseMix-2 execution failed; no campaign admission." >&2
        exit 1
    fi
    CONFIRM_STATE="$(squeue -h -j "$CONFIRM_VALIDATOR" -o '%T %r')"
    if [[ -z "$CONFIRM_STATE" || "$CONFIRM_STATE" == *DependencyNeverSatisfied* ]]; then
        echo "Validator is no longer runnable and no manifest is present; inspect accounting." >&2
        exit 1
    fi
    printf '%s validator %s: %s\n' "$(date -u +%FT%TZ)" "$CONFIRM_VALIDATOR" "$CONFIRM_STATE"
    sleep 30
done
