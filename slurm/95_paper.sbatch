#!/usr/bin/env bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=00:20:00
#SBATCH --job-name=magcore-paper
#SBATCH --mail-type=END,FAIL

set -Eeuo pipefail
ROOT="$(cd "$1/source" && pwd -P)"
source "$ROOT/slurm/common.sh"
load_run "$1"
init_task paper 0
run_python "$MAGCORE_CODE_ROOT/scripts/validate_run.py" --run-dir "$MAGCORE_RUN_DIR" --mode verify-lock
run_python - "$MAGCORE_RUN_DIR/figures/manifest.json" "$MAGCORE_RUN_DIR/freeze/release.json" <<'PY'
import json, sys
figures = json.load(open(sys.argv[1], encoding="utf-8"))
release = json.load(open(sys.argv[2], encoding="utf-8"))
if figures.get("freeze_id") != release["release_id"] or \
        figures.get("release_manifest_sha256") != release["manifest_sha256"]:
    raise SystemExit("paper figure provenance does not match locked release")
PY
RELEASE_DIR="$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["release_dir"])' "$MAGCORE_RUN_DIR/freeze/release.json")"
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
MAIN_TEX="$MAGCORE_CODE_ROOT/paper/current_state/source/main.tex"
[[ -f "$MAIN_TEX" ]] || { echo "FATAL: missing paper entry point $MAIN_TEX" >&2; exit 67; }
run_python "$MAGCORE_CODE_ROOT/scripts/check_current_manuscript.py" \
    --source "$MAIN_TEX" \
    --bibliography "$(dirname "$MAIN_TEX")/refs.bib"
run_python "$MAGCORE_CODE_ROOT/scripts/generate_current_paper_figures.py" verify \
    --summary "$SUMMARY" \
    --output-dir "$(dirname "$MAIN_TEX")/figures"
BUILD_DIR="$MAGCORE_RUN_DIR/paper"
mkdir -p "$BUILD_DIR"
cd "$(dirname "$MAIN_TEX")"
srun --ntasks=1 --cpus-per-task="$SLURM_CPUS_PER_TASK" --cpu-bind=cores \
    latexmk -pdf -interaction=nonstopmode -halt-on-error -outdir="$BUILD_DIR" "$(basename "$MAIN_TEX")"
PDF="$BUILD_DIR/$(basename "${MAIN_TEX%.tex}.pdf")"
[[ -s "$PDF" ]]
if command -v pdfinfo >/dev/null 2>&1; then
    PAGES="$(pdfinfo "$PDF" | awk '/^Pages:/ {print $2}')"
    (( PAGES > 6 )) || { echo "FATAL: full current paper must exceed the six-page snapshot" >&2; exit 68; }
    [[ "$(pdfinfo "$PDF" | awk '/^Page size:/ {print $3, $5}')" == "595.276 841.89" ]] || {
        echo "FATAL: current paper must remain A4" >&2
        exit 68
    }
fi
# With ``-outdir``, latexmk places BibTeX output beside the other build
# artifacts.  Validate that exact staged file so the publication gate does not
# depend on (or accidentally accept) a stale bibliography in the source tree.
BBL="$BUILD_DIR/main.bbl"
LOG="$BUILD_DIR/main.log"
FLS="$BUILD_DIR/main.fls"
[[ -s "$FLS" ]] || { echo "FATAL: missing LaTeX recorder output" >&2; exit 69; }
grep -Fq 'INPUT ./tables/frozen_result_macros.tex' "$FLS" || {
    echo "FATAL: paper did not consume locked result macros" >&2
    exit 69
}
grep -Fq 'INPUT ./tables/frozen_results.tex' "$FLS" || {
    echo "FATAL: paper did not consume locked recovery table" >&2
    exit 69
}
if grep -Eq 'INPUT (\./)?tables/(result_values|recovery_table)\.tex' "$FLS"; then
    echo "FATAL: paper consumed an unverified generated-result input" >&2
    exit 69
fi
[[ -s "$BBL" ]] || { echo "FATAL: missing generated bibliography $BBL" >&2; exit 69; }
(( $(grep -c '^\\bibitem' "$BBL") >= 45 )) || {
    echo "FATAL: full current paper must contain at least 45 bibliography items" >&2
    exit 69
}
if grep -Eq 'LaTeX Warning:.*undefined|Citation.*undefined|Reference.*undefined|Overfull|Fatal error|Emergency stop' "$LOG"; then
    echo "FATAL: publication-blocking LaTeX diagnostic found" >&2
    exit 70
fi
task_done
