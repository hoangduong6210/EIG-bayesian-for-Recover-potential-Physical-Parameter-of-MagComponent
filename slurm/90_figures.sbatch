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
task_done
