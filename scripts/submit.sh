#!/usr/bin/env bash
# Login-safe orchestration only: metadata, directories, and sbatch submissions.

set -Eeuo pipefail
umask 027

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
RETRY_OF=""
PREPARE_ONLY=false
while (( $# > 0 )); do
    case "$1" in
        --retry-of)
            [[ -n "${2:-}" ]] || { echo "usage: $0 [--prepare-only] [--retry-of RUN_DIR]" >&2; exit 64; }
            RETRY_OF="$(cd "$2" && pwd -P)"
            shift 2
            ;;
        --prepare-only)
            PREPARE_ONLY=true
            shift
            ;;
        *)
            echo "usage: $0 [--prepare-only] [--retry-of RUN_DIR]" >&2
            exit 64
            ;;
    esac
done
if [[ -n "$RETRY_OF" ]]; then
    case "$RETRY_OF/" in "$PROJECT_ROOT/runs/"*) ;; *) echo "retry source is outside project runs" >&2; exit 65;; esac
    [[ -f "$RETRY_OF/provenance/jobs.tsv" ]] || { echo "invalid retry source" >&2; exit 66; }
fi

for command in sbatch git sha256sum tar; do
    command -v "$command" >/dev/null || { echo "missing required command: $command" >&2; exit 69; }
done

# A claim-bearing campaign must be reproducible from the committed snapshot.
# Scope this check to the Magnetic manuscript project so unrelated ADE work is
# neither included nor allowed to block submission.
if [[ -n "$(git -C "$PROJECT_ROOT" status --porcelain --untracked-files=all -- .)" ]]; then
    echo "refusing claim run from a dirty Magnetic project; commit or remove all scoped changes" >&2
    git -C "$PROJECT_ROOT" status --short -- . >&2
    exit 65
fi
for script in "$PROJECT_ROOT"/slurm/*.sbatch "$PROJECT_ROOT"/slurm/common.sh; do
    bash -n "$script"
done

REVISION="$(git -C "$PROJECT_ROOT" rev-parse --verify HEAD)"
RUN_STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
MAGCORE_RUN_ID="${RUN_STAMP}_${REVISION:0:12}"
RUN_DIR="$PROJECT_ROOT/runs/$MAGCORE_RUN_ID"
if [[ -e "$RUN_DIR" ]]; then
    echo "refusing to overwrite existing run: $RUN_DIR" >&2
    exit 73
fi

mkdir -p "$RUN_DIR"/{config,figures,freeze,logs,paper,provenance/jobs,results,source,status,summary,tmp}
cp "$PROJECT_ROOT/configs/default.toml" "$RUN_DIR/config/default.toml"
cp "$PROJECT_ROOT/data/checksums.sha256" "$RUN_DIR/provenance/input-data-sha256.txt"
# Snapshot exactly the committed tree.  Unlike archiving the working directory,
# git archive cannot include .git, virtual environments, ignored staged data,
# caches, or other local-only files.
git -C "$PROJECT_ROOT" archive --format=tar.gz \
    --output="$RUN_DIR/provenance/source-tree.tar.gz" "$REVISION"
SOURCE_ARCHIVE_SHA256="$(sha256sum "$RUN_DIR/provenance/source-tree.tar.gz" | awk '{print $1}')"
tar -xzf "$RUN_DIR/provenance/source-tree.tar.gz" -C "$RUN_DIR/source"
CONFIG_SHA256="$(sha256sum "$RUN_DIR/config/default.toml" | awk '{print $1}')"
DATA_MANIFEST_SHA256="$(sha256sum "$PROJECT_ROOT/data/checksums.sha256" | awk '{print $1}')"
DEPENDENCY_LOCK_SHA256="$(sha256sum "$PROJECT_ROOT/configs/dependencies.lock" | awk '{print $1}')"
SOURCE_DIRTY="$(git -C "$PROJECT_ROOT" status --porcelain --untracked-files=no -- . | sha256sum | awk '{print $1}')"
MAGCORE_VENV_RESOLVED="${MAGCORE_VENV:-$PROJECT_ROOT/.venv}"
[[ -x "$MAGCORE_VENV_RESOLVED/bin/python" ]] || {
    echo "missing Magnetic pipeline Python environment: $MAGCORE_VENV_RESOLVED" >&2
    exit 69
}
MAGCORE_DATA_ROOT_RESOLVED="${MAGCORE_DATA_ROOT:-$PROJECT_ROOT/data/external/materialdatabase/data}"
[[ -d "$MAGCORE_DATA_ROOT_RESOLVED" ]] || {
    echo "missing staged material database: $MAGCORE_DATA_ROOT_RESOLVED" >&2
    exit 69
}
MAGCORE_DATA_ROOT_RESOLVED="$(cd "$MAGCORE_DATA_ROOT_RESOLVED" && pwd -P)"
MAGCORE_PARTITION_RESOLVED="${MAGCORE_PARTITION:-nextgen}"
[[ "$MAGCORE_PARTITION_RESOLVED" =~ ^[A-Za-z0-9._-]+$ ]] || {
    echo "invalid scheduler partition: $MAGCORE_PARTITION_RESOLVED" >&2
    exit 64
}
{
    printf 'MAGCORE_RUN_ID=%q\n' "$MAGCORE_RUN_ID"
    printf 'MAGCORE_PROJECT_ROOT=%q\n' "$PROJECT_ROOT"
    printf 'MAGCORE_CODE_ROOT=%q\n' "$RUN_DIR/source"
    printf 'MAGCORE_DATA_ROOT=%q\n' "$MAGCORE_DATA_ROOT_RESOLVED"
    printf 'MAGCORE_SUBMIT_PARTITION=%q\n' "$MAGCORE_PARTITION_RESOLVED"
    printf 'MAGCORE_GIT_REVISION=%q\n' "$REVISION"
    printf 'MAGCORE_SOURCE_STATUS_SHA256=%q\n' "$SOURCE_DIRTY"
    printf 'MAGCORE_SOURCE_ARCHIVE_SHA256=%q\n' "$SOURCE_ARCHIVE_SHA256"
    printf 'MAGCORE_CONFIG_SHA256=%q\n' "$CONFIG_SHA256"
    printf 'MAGCORE_DATA_MANIFEST_SHA256=%q\n' "$DATA_MANIFEST_SHA256"
    printf 'MAGCORE_DEPENDENCY_LOCK_SHA256=%q\n' "$DEPENDENCY_LOCK_SHA256"
    printf 'MAGCORE_CONFIG_MODE=%q\n' 'preregistered_eig_validation_benchmark_v1'
    printf 'MAGCORE_RETRY_OF=%q\n' "$RETRY_OF"
    printf 'MAGCORE_VENV=%q\n' "$MAGCORE_VENV_RESOLVED"
} > "$RUN_DIR/provenance/run.env"
git -C "$PROJECT_ROOT" status --short -- . > "$RUN_DIR/provenance/git-status.txt"
git -C "$PROJECT_ROOT" diff --binary -- . > "$RUN_DIR/provenance/source.patch"
# Record only the declared scientific inputs.  Machine-specific source paths
# remain in the private production provenance and are excluded from the public
# projection.
while read -r expected relative; do
    [[ -n "$expected" && -n "$relative" ]] || continue
    case "$relative" in
        data/external/materialdatabase/data/*)
            relative="${relative#data/external/materialdatabase/data/}"
            ;;
        *)
            echo "unsupported input-data manifest path: $relative" >&2
            exit 65
            ;;
    esac
    candidate="$MAGCORE_DATA_ROOT_RESOLVED/$relative"
    [[ -f "$candidate" ]] || { echo "missing declared input: $candidate" >&2; exit 66; }
    actual="$(sha256sum "$candidate" | awk '{print $1}')"
    [[ "$actual" == "$expected" ]] || {
        echo "input checksum mismatch: $relative" >&2
        exit 68
    }
    printf '%s  %s\n' "$actual" "$candidate"
done < "$PROJECT_ROOT/data/checksums.sha256" > "$RUN_DIR/provenance/data-sha256.txt"

if [[ "$PREPARE_ONLY" == true ]]; then
    printf '%s\n' "$MAGCORE_RUN_ID" > "$PROJECT_ROOT/runs/LATEST"
    printf 'prepared for scheduler submission\n' > "$RUN_DIR/status/PREPARED"
    printf 'Prepared immutable run: %s\nRun directory: %s\n' "$MAGCORE_RUN_ID" "$RUN_DIR"
    exit 0
fi

declare -a SUBMITTED=()
submission_failed() {
    local code="$?"
    printf 'submission failed with exit %s; already submitted jobs were not cancelled: %s\n' \
        "$code" "${SUBMITTED[*]:-none}" | tee "$RUN_DIR/status/SUBMISSION_FAILED" >&2
    exit "$code"
}
trap submission_failed ERR

submit() {
    local dependency="$1" script="$2"
    local -a options=(--parsable --partition="$MAGCORE_PARTITION_RESOLVED"
        --output="$RUN_DIR/logs/%x_%A_%a.out")
    local response
    [[ -z "$dependency" ]] || options+=(--dependency="$dependency")
    response="$(sbatch "${options[@]}" "$RUN_DIR/source/slurm/$script" "$RUN_DIR")"
    printf '%s\n' "${response%%;*}"
}

PREFLIGHT="$(submit "" 00_preflight.sbatch)"; SUBMITTED+=("$PREFLIGHT")
SMOKE="$(submit "afterok:$PREFLIGHT" 00_smoke.sbatch)"; SUBMITTED+=("$SMOKE")
POSTERIOR="$(submit "afterok:$SMOKE" 10_posterior.sbatch)"; SUBMITTED+=("$POSTERIOR")
ROBUSTNESS="$(submit "afterok:$SMOKE" 11_robustness.sbatch)"; SUBMITTED+=("$ROBUSTNESS")
IDENT="$(submit "afterok:$SMOKE" 13_identifiability.sbatch)"; SUBMITTED+=("$IDENT")
MEASURED_MU="$(submit "afterok:$SMOKE" 14_measured_mu.sbatch)"; SUBMITTED+=("$MEASURED_MU")
MEASURED_PCV="$(submit "afterok:$SMOKE" 15_measured_pcv.sbatch)"; SUBMITTED+=("$MEASURED_PCV")
MEASURED_EIG="$(submit "afterok:$SMOKE" 16_measured_eig.sbatch)"; SUBMITTED+=("$MEASURED_EIG")

# Estimator validation is preregistered and upstream of the confirmatory
# acquisition benchmark, so confirmatory seeds cannot influence tuning.
VALIDATION_STATES="$(submit "afterok:$SMOKE" 17_eig_validation_states.sbatch)"; SUBMITTED+=("$VALIDATION_STATES")
VALIDATION_GRID="$(submit "afterok:$VALIDATION_STATES" 18_eig_validation_grid.sbatch)"; SUBMITTED+=("$VALIDATION_GRID")
VALIDATION_REFERENCE="$(submit "afterok:$VALIDATION_STATES" 18_eig_validation_reference.sbatch)"; SUBMITTED+=("$VALIDATION_REFERENCE")
VALIDATION_AUDIT="$(submit "afterok:$VALIDATION_STATES" 18_eig_validation_reference_audit.sbatch)"; SUBMITTED+=("$VALIDATION_AUDIT")
VALIDATION_SCORE_DEPS="afterok:$VALIDATION_GRID:$VALIDATION_REFERENCE:$VALIDATION_AUDIT"
VALIDATION_SELECTION="$(submit "$VALIDATION_SCORE_DEPS" 19_eig_validation_selection.sbatch)"; SUBMITTED+=("$VALIDATION_SELECTION")
VALIDATION_DOWNSTREAM="$(submit "afterok:$VALIDATION_SELECTION" 20_eig_validation_downstream.sbatch)"; SUBMITTED+=("$VALIDATION_DOWNSTREAM")
VALIDATION_FINAL="$(submit "afterok:$VALIDATION_DOWNSTREAM" 21_eig_validation_finalize.sbatch)"; SUBMITTED+=("$VALIDATION_FINAL")
EIG="$(submit "afterok:$VALIDATION_FINAL" 12_eig.sbatch)"; SUBMITTED+=("$EIG")

EXPERIMENT_DEPS="afterany:$POSTERIOR:$ROBUSTNESS:$EIG:$IDENT:$MEASURED_MU:$MEASURED_PCV:$MEASURED_EIG:$VALIDATION_FINAL"
AUDIT="$(submit "$EXPERIMENT_DEPS" 80_audit.sbatch)"; SUBMITTED+=("$AUDIT")
AGGREGATE="$(submit "afterok:$AUDIT" 81_aggregate.sbatch)"; SUBMITTED+=("$AGGREGATE")
FREEZE="$(submit "afterok:$AGGREGATE" 82_freeze.sbatch)"; SUBMITTED+=("$FREEZE")
FIGURES="$(submit "afterok:$FREEZE" 90_figures.sbatch)"; SUBMITTED+=("$FIGURES")
PAPER="$(submit "afterok:$FIGURES" 95_paper.sbatch)"; SUBMITTED+=("$PAPER")
FINAL_DEPS="afterany:$AUDIT:$AGGREGATE:$FREEZE:$FIGURES:$PAPER"
FINALIZE="$(submit "$FINAL_DEPS" 99_finalize.sbatch)"; SUBMITTED+=("$FINALIZE")

{
    printf 'stage\tjob_id\tdependency\n'
    printf 'preflight\t%s\t-\n' "$PREFLIGHT"
    printf 'smoke\t%s\tafterok:%s\n' "$SMOKE" "$PREFLIGHT"
    printf 'posterior\t%s\tafterok:%s\n' "$POSTERIOR" "$SMOKE"
    printf 'robustness\t%s\tafterok:%s\n' "$ROBUSTNESS" "$SMOKE"
    printf 'identifiability\t%s\tafterok:%s\n' "$IDENT" "$SMOKE"
    printf 'measured_mu\t%s\tafterok:%s\n' "$MEASURED_MU" "$SMOKE"
    printf 'measured_pcv\t%s\tafterok:%s\n' "$MEASURED_PCV" "$SMOKE"
    printf 'measured_eig\t%s\tafterok:%s\n' "$MEASURED_EIG" "$SMOKE"
    printf 'eig_validation_states\t%s\tafterok:%s\n' "$VALIDATION_STATES" "$SMOKE"
    printf 'eig_validation_grid\t%s\tafterok:%s\n' "$VALIDATION_GRID" "$VALIDATION_STATES"
    printf 'eig_validation_reference\t%s\tafterok:%s\n' "$VALIDATION_REFERENCE" "$VALIDATION_STATES"
    printf 'eig_validation_reference_audit\t%s\tafterok:%s\n' "$VALIDATION_AUDIT" "$VALIDATION_STATES"
    printf 'eig_validation_selection\t%s\t%s\n' "$VALIDATION_SELECTION" "$VALIDATION_SCORE_DEPS"
    printf 'eig_validation_downstream\t%s\tafterok:%s\n' "$VALIDATION_DOWNSTREAM" "$VALIDATION_SELECTION"
    printf 'eig_validation_finalize\t%s\tafterok:%s\n' "$VALIDATION_FINAL" "$VALIDATION_DOWNSTREAM"
    printf 'eig\t%s\tafterok:%s\n' "$EIG" "$VALIDATION_FINAL"
    printf 'audit\t%s\t%s\n' "$AUDIT" "$EXPERIMENT_DEPS"
    printf 'aggregate\t%s\tafterok:%s\n' "$AGGREGATE" "$AUDIT"
    printf 'freeze\t%s\tafterok:%s\n' "$FREEZE" "$AGGREGATE"
    printf 'figures\t%s\tafterok:%s\n' "$FIGURES" "$FREEZE"
    printf 'paper\t%s\tafterok:%s\n' "$PAPER" "$FIGURES"
    printf 'finalize\t%s\t%s\n' "$FINALIZE" "$FINAL_DEPS"
} > "$RUN_DIR/provenance/jobs.tsv.partial"
mv "$RUN_DIR/provenance/jobs.tsv.partial" "$RUN_DIR/provenance/jobs.tsv"
printf '%s\n' "$MAGCORE_RUN_ID" > "$PROJECT_ROOT/runs/LATEST"
trap - ERR

printf 'Submitted immutable run: %s\nRun directory: %s\nFinal job: %s\n' \
    "$MAGCORE_RUN_ID" "$RUN_DIR" "$FINALIZE"
printf 'Monitor: %q %q\n' "$PROJECT_ROOT/scripts/watch.sh" "$RUN_DIR"
