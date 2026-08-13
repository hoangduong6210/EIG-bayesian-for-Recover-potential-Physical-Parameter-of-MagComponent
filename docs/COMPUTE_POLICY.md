# Compute policy

## Principle

Login nodes coordinate research; compute nodes perform research solves. A command is heavy based on what it does, not how quickly it happened to run previously.

## Login-safe operations

- Read and edit text files.
- Inspect small JSON/CSV metadata.
- Verify configuration schemas and SHA-256 checksums.
- Run formatting, linting, and cheap deterministic unit tests that do not sample or sweep.
- Submit and monitor jobs with `sbatch`, `squeue`, and `sacct`.
- Review already-generated plots and reports.

## SLURM-only operations

- Any posterior sampler or optimizer used as an inferential result.
- Synthetic or measured-data fitting.
- EIG estimation over candidate libraries or sequential acquisition.
- Fisher-information sweeps and multi-seed analyses.
- Prior-misspecification and lot-sensitivity experiment matrices.
- Full integration/scientific test suites.
- Production aggregation, release freezing, and paper figure generation.
- End-to-end reproduction.

Every SLURM-only command must fail before loading data when scheduler provenance is missing. Required environment fields are `SLURM_JOB_ID` and `SLURM_JOB_NODELIST`; array jobs additionally record `SLURM_ARRAY_JOB_ID` and `SLURM_ARRAY_TASK_ID`.

## Resource and output rules

- Pin the Python/module environment and cap BLAS/OpenMP thread counts to allocated CPUs.
- Use task-unique output directories; array tasks cannot write the same filename.
- Write `.partial` artifacts first, flush them, then atomically rename and emit `SUCCESS.json`.
- Scheduler logs are research artifacts and enter the frozen release provenance bundle.
- A failed or pre-empted task is rerun with the same configuration and seed under a new attempt identifier; it never overwrites an earlier attempt.

## Pipeline dependency order

`preflight -> smoke -> experiment arrays -> aggregate/validate -> freeze -> tables/figures -> paper build`

Dependent jobs use `afterok`. A freeze job must not run after `afterany`.

