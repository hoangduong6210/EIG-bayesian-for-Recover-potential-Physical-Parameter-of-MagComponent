#!/usr/bin/env bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=2G
#SBATCH --time=00:10:00
#SBATCH --job-name=magcore-preflight

set -Eeuo pipefail
ROOT="$(cd "$1/source" && pwd -P)"
source "$ROOT/slurm/common.sh"
load_run "$1"
init_task preflight 0
[[ "$(sha256sum "$MAGCORE_RUN_DIR/provenance/source-tree.tar.gz" | awk '{print $1}')" == \
    "$MAGCORE_SOURCE_ARCHIVE_SHA256" ]] || {
    echo "FATAL: standalone source archive hash mismatch" >&2
    exit 68
}
run_python -c 'import numpy, scipy, emcee, matplotlib, magcore_calib; print("scientific imports OK")'
for entrypoint in posterior_recovery.py eig_efficiency.py lot_variation.py d5_identifiability_demo.py real_data_recovery.py real_data_pcv.py eig_real.py aggregate_results.py eig_convergence_states.py eig_convergence_scores.py aggregate_eig_convergence.py eig_convergence_downstream.py finalize_eig_convergence.py; do
    [[ -f "$MAGCORE_CODE_ROOT/experiments/$entrypoint" ]] || {
        echo "FATAL: required standalone entry point is missing: experiments/$entrypoint" >&2
        exit 69
    }
done
[[ -f "$MAGCORE_CODE_ROOT/scripts/generate_paper_artifacts.py" ]]
(cd "$PROJECT_ROOT/../.." && sha256sum --check "$MAGCORE_CODE_ROOT/data/checksums.sha256")
run_python - "$MAGCORE_CODE_ROOT/configs/default.toml" <<'PY'
import sys, tomllib
with open(sys.argv[1], "rb") as handle:
    cfg = tomllib.load(handle)
expected = {
    ("sampler", "n_walkers"): 48, ("sampler", "n_steps"): 5000,
    ("sampler", "burn"): 1000, ("eig", "n_outer"): 300,
    ("eig", "n_inner"): 100, ("eig", "max_measurements"): 25,
}
bad = {".".join(key): (cfg[key[0]][key[1]], value) for key, value in expected.items()
       if cfg[key[0]][key[1]] != value}
if bad:
    raise SystemExit(
        f"preregistered_eig_validation_benchmark_v1 no longer matches config: {bad}"
    )

study = cfg["study"]
replication = study["seeds"]
convergence = study["estimator_validation"]
sets = {
    "recovery": replication["recovery"],
    "acquisition": replication["acquisition"],
    "validation_state": replication["validation_state"],
    "downstream_validation": replication["downstream_validation"],
}
if len(sets["recovery"]) != 5 or len(sets["acquisition"]) != 30:
    raise SystemExit(f"invalid preregistered seed cardinality: {sets}")
if any(len(values) != len(set(values)) for values in sets.values()):
    raise SystemExit("duplicate seed inside preregistered seed set")
for name, values in sets.items():
    for other, other_values in sets.items():
        if name < other and set(values) & set(other_values):
            raise SystemExit(f"seed leakage between {name} and {other}")
if convergence["outer_grid"] != [100, 300, 900] or \
   convergence["inner_grid"] != [50, 100, 300] or \
   convergence["replicate_grid"] != [5, 10, 20]:
    raise SystemExit("estimator-validation grid differs from preregistration")
PY
CURRENT_PAPER="$MAGCORE_CODE_ROOT/paper/current_state"
PAPER_SOURCE="$CURRENT_PAPER/source"
[[ -f "$PAPER_SOURCE/main.tex" && -f "$CURRENT_PAPER/results.lock.yaml" ]]
command -v latexmk >/dev/null
kpsewhich mathptmx.sty >/dev/null
mkdir -p "$MAGCORE_RUN_DIR/tmp/preflight-paper"
(
    cd "$PAPER_SOURCE"
    latexmk -pdf -interaction=nonstopmode -halt-on-error \
        -outdir="$MAGCORE_RUN_DIR/tmp/preflight-paper" main.tex
)
[[ -s "$MAGCORE_RUN_DIR/tmp/preflight-paper/main.pdf" ]]
run_python -m pip freeze > "$MAGCORE_RUN_DIR/provenance/pip-freeze.txt.partial"
mv "$MAGCORE_RUN_DIR/provenance/pip-freeze.txt.partial" "$MAGCORE_RUN_DIR/provenance/pip-freeze.txt"
module list 2> "$MAGCORE_RUN_DIR/provenance/modules.txt.partial"
mv "$MAGCORE_RUN_DIR/provenance/modules.txt.partial" "$MAGCORE_RUN_DIR/provenance/modules.txt"
task_done
