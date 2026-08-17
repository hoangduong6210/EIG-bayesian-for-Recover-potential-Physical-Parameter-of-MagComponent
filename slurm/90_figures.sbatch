#!/usr/bin/env bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --job-name=magcore-figures

set -Eeuo pipefail
ROOT="$(cd "$1/source" && pwd -P)"
source "$ROOT/slurm/common.sh"
load_run "$1"
init_task figures 0
run_python "$MAGCORE_CODE_ROOT/scripts/validate_run.py" --run-dir "$MAGCORE_RUN_DIR" --mode verify-lock
RELEASE_DIR="$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["release_dir"])' "$MAGCORE_RUN_DIR/freeze/release.json")"
FREEZE_ID="$(basename "$RELEASE_DIR")"
SUMMARY="$RELEASE_DIR/tables/paper_summary.json"
[[ -s "$SUMMARY" ]] || { echo "FATAL: frozen paper summary is missing" >&2; exit 67; }
run_python - "$SUMMARY" "$MAGCORE_RUN_DIR/freeze/release.json" <<'PY'
import json, pathlib, sys
summary = json.load(open(sys.argv[1], encoding="utf-8"))
release = json.load(open(sys.argv[2], encoding="utf-8"))
release_dir = pathlib.Path(release["release_dir"])
if release_dir.name != release["release_id"]:
    raise SystemExit("frozen release directory/ID mismatch")
if summary.get("release_id") != release["release_id"]:
    raise SystemExit("paper summary does not belong to the just-frozen release")
PY
run_python "$MAGCORE_CODE_ROOT/scripts/validate_run.py" --run-dir "$MAGCORE_RUN_DIR" --mode figures
[[ -s "$MAGCORE_RUN_DIR/figures/manifest.json" ]]
run_python - "$MAGCORE_RUN_DIR/figures/manifest.json" "$MAGCORE_RUN_DIR/freeze/release.json" <<'PY'
import json, sys
figures = json.load(open(sys.argv[1], encoding="utf-8"))
release = json.load(open(sys.argv[2], encoding="utf-8"))
if figures.get("freeze_id") != release["release_id"]:
    raise SystemExit("figure manifest freeze ID mismatch")
if figures.get("release_manifest_sha256") != release["manifest_sha256"]:
    raise SystemExit("figure manifest release digest mismatch")
PY
FULL_FIGURE_DIR="$MAGCORE_CODE_ROOT/paper/current_state/source/figures"
run_python "$MAGCORE_CODE_ROOT/scripts/generate_current_paper_figures.py" generate \
    --summary "$SUMMARY" \
    --output-dir "$FULL_FIGURE_DIR"
run_python "$MAGCORE_CODE_ROOT/scripts/generate_current_paper_figures.py" verify \
    --summary "$SUMMARY" \
    --output-dir "$FULL_FIGURE_DIR"
PROJECT_FULL_FIGURE_DIR="$MAGCORE_PROJECT_ROOT/paper/current_state/source/figures"
if [[ "$PROJECT_FULL_FIGURE_DIR" != "$FULL_FIGURE_DIR" ]]; then
    mkdir -p "$PROJECT_FULL_FIGURE_DIR"
    for ARTIFACT in \
        study_workflow_full.pdf \
        synthetic_diagnostics_full.pdf \
        acquisition_diagnostics_full.pdf \
        measured_adequacy_full.pdf \
        full_figure_manifest.json; do
        PARTIAL="$PROJECT_FULL_FIGURE_DIR/$ARTIFACT.partial"
        cp -- "$FULL_FIGURE_DIR/$ARTIFACT" "$PARTIAL"
        mv -f -- "$PARTIAL" "$PROJECT_FULL_FIGURE_DIR/$ARTIFACT"
    done
fi
run_python "$MAGCORE_CODE_ROOT/scripts/generate_current_paper_figures.py" verify \
    --summary "$SUMMARY" \
    --output-dir "$PROJECT_FULL_FIGURE_DIR"
task_done
