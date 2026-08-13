import pytest

from magcore_calib.results import SCHEMA_VERSION, validate_result
from magcore_calib.runtime import require_slurm


def valid_record():
    return {
        "schema_version": SCHEMA_VERSION, "case_study": "magnetic_core", "run_id": "x",
        "provenance": {"slurm": {"job_id": "123"}}, "data": {}, "model": {}, "sampler": {},
        "posterior": {name: {} for name in ("k", "alpha", "beta", "mu_s", "f_rel_hz", "alpha_cc")},
        "predictive": {}, "design": {},
        "claim_context": {"oracle_initialized": False}, "validity": {},
    }


def test_schema_rejects_five_dimensional_result():
    record = valid_record()
    record["posterior"].pop("alpha_cc")
    with pytest.raises(ValueError, match="exactly six"):
        validate_result(record)


def test_schema_rejects_incomplete_benchmark_v2():
    record = valid_record()
    record["design"] = {"benchmark_version": 2, "policies": {}}
    with pytest.raises(ValueError, match="benchmark v2"):
        validate_result(record)


def test_heavy_runtime_requires_slurm(monkeypatch):
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    monkeypatch.delenv("SLURM_JOB_NODELIST", raising=False)
    with pytest.raises(RuntimeError, match="SLURM"):
        require_slurm()
    monkeypatch.setenv("SLURM_JOB_ID", "999")
    with pytest.raises(RuntimeError, match="SLURM"):
        require_slurm()
    monkeypatch.setenv("SLURM_JOB_NODELIST", "node001")
    require_slurm()
