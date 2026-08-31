"""Scientific and disclosure contracts for SparseMix-1."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tarfile
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from magcore_calib.sparse_mixing import (
    SPARSE_MIXING_RESULT_SCHEMA,
    contains_forbidden_key,
    initial_ensemble,
    load_sparse_mixing_plan,
    reconstruct_state,
    validate_sparse_mixing_result,
    write_json_create_only,
    write_npz_create_only,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/sparse_mixing_v1.toml"


def _script_module(relative: str, name: str):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sparse_mixing_plan_is_fixed_and_endpoint_free():
    plan = load_sparse_mixing_plan(CONFIG)
    assert plan.protocol_id == "SparseMix-1"
    assert plan.task_count == 18
    tasks = plan.tasks()
    assert len({task.task_id for task in tasks}) == 18
    assert len({task.seed for task in tasks}) == 18
    assert sum(task.exact_replay for task in tasks) == 2
    assert all(
        task.retained_steps == (320_000 if task.exact_replay else 800_000)
        for task in tasks
    )
    assert "endpoints" not in plan.raw
    assert "scientific_results" not in plan.raw


def test_locked_states_reconstruct_without_acquisition_or_endpoint_records():
    plan = load_sparse_mixing_plan(CONFIG)
    expected_manifests = {
        "n3": "707cba89c075e58049321786fac51ada819e707697b2132670268a0bb8f7edf9",
        "n4": "22b7d356e2240d9490932336d82899efaa2a195cfcc3632f82bc631754b09a5c",
    }
    for target in plan.targets:
        state = reconstruct_state(plan, target, ROOT, ROOT / "configs/model_mismatch_v2.toml")
        assert len(state.observations) == target.n_measurements
        assert tuple(sorted(state.identities)) == state.identities
        assert state.state_identity_sha256 == target.state_identity_sha256
        assert state.mcmc_seed == target.original_mcmc_seed
        if target.target_id in expected_manifests:
            assert state.observation_manifest_sha256 == expected_manifests[target.target_id]
        assert all(set(row) == {"identity", "value_hex", "sigma_hex"}
                   for row in state.observation_manifest)


def test_exact_and_overdispersed_initializations_are_finite_and_locked():
    plan = load_sparse_mixing_plan(CONFIG)
    target = plan.targets[0]
    state = reconstruct_state(plan, target, ROOT, ROOT / "configs/model_mismatch_v2.toml")
    exact = initial_ensemble(state, plan.tasks()[0])
    assert exact.shape == (48, 6)
    encoded = [[float(value).hex() for value in row] for row in exact]
    assert hashlib.sha256(json.dumps(
        encoded, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest() == target.exact_initial_ensemble_sha256
    over_task = next(
        task for task in plan.tasks()
        if task.target == target and task.initialization == "overdispersed_prior_lhs"
    )
    over = initial_ensemble(state, over_task)
    assert over.shape == (48, 6)
    assert np.all(np.isfinite(over))
    assert not np.allclose(exact, over)


def _valid_record(plan, thin: Path) -> dict:
    return {
        "schema_version": SPARSE_MIXING_RESULT_SCHEMA,
        "record_class": "endpoint_free_sampler_diagnostic",
        "protocol_id": plan.protocol_id,
        "config_sha256": plan.config_sha256,
        "task": {}, "parent": {}, "reconstruction": {}, "sampler": {},
        "checkpoints": [], "final_diagnostics": {},
        "thin": {
            "path": thin.name,
            "sha256": hashlib.sha256(thin.read_bytes()).hexdigest(),
            "shape": [1, 48, 6], "stride": 200,
        },
        "chain_block_sha256": [],
        "disclosure": {
            "claim_bearing_result": False,
            "scientific_endpoints_included": False,
            "retroactive_mm2_admission_allowed": False,
        },
    }


def test_output_validator_rejects_nested_endpoint_keys(tmp_path: Path):
    plan = load_sparse_mixing_plan(CONFIG)
    thin = write_npz_create_only(tmp_path / "thin.npz", chain=np.zeros((1, 48, 6)))
    record = _valid_record(plan, thin)
    validate_sparse_mixing_result(record, plan)
    record["final_diagnostics"]["holdout"] = 1.0
    with pytest.raises(ValueError, match="forbidden key"):
        validate_sparse_mixing_result(record, plan)
    assert contains_forbidden_key(
        record, plan.raw["outputs"]["forbidden_key_fragments"]
    ) == "holdout"


def test_sparse_mixing_artifacts_are_create_only(tmp_path: Path):
    json_path = tmp_path / "record.json"
    write_json_create_only(json_path, {"value": 1})
    with pytest.raises(FileExistsError):
        write_json_create_only(json_path, {"value": 2})
    npz_path = tmp_path / "thin.npz"
    write_npz_create_only(npz_path, chain=np.zeros((2, 2, 6)))
    with pytest.raises(FileExistsError):
        write_npz_create_only(npz_path, chain=np.ones((2, 2, 6)))
    assert not list(tmp_path.glob("*.partial"))


def test_sparse_mixing_plan_cli_and_scheduler_are_diagnostic_only():
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/sparse_mixing_plan.py"), "plan",
            "--config", str(CONFIG),
        ],
        check=True, capture_output=True, text=True,
    )
    assert json.loads(completed.stdout)["task_count"] == 18
    for relative in (
        "scripts/submit_sparse_mixing.sh", "scripts/watch_sparse_mixing.sh",
        "slurm/26_sparse_mixing.sbatch", "slurm/27_sparse_mixing_validate.sbatch",
    ):
        subprocess.run(["bash", "-n", str(ROOT / relative)], check=True)
    submit = (ROOT / "scripts/submit_sparse_mixing.sh").read_text(encoding="utf-8")
    assert '--array="0-$((TASK_COUNT - 1))%8"' in submit
    assert 'afterok:$ARRAY' in submit
    assert "aggregate" not in submit.lower()
    validator = (
        ROOT / "slurm/27_sparse_mixing_validate.sbatch"
    ).read_text(encoding="utf-8")
    assert "validate_sparse_mixing.py" in validator
    assert "model_mismatch" not in validator


def test_locked_input_verifier_detects_post_submission_mutation(tmp_path: Path):
    module = _script_module(
        "scripts/verify_sparse_mixing_inputs.py", "sparse_input_verifier"
    )
    input_root = tmp_path / "inputs"
    source = input_root / "mm2_source"
    (source / "configs").mkdir(parents=True)
    mm2_config = (ROOT / "configs/model_mismatch_v2.toml").read_bytes()
    (source / "configs/model_mismatch_v2.toml").write_bytes(mm2_config)
    archive = input_root / "mm2_source.tar.gz"
    with tarfile.open(archive, "w:gz") as stream:
        stream.add(
            source / "configs/model_mismatch_v2.toml",
            arcname="configs/model_mismatch_v2.toml",
        )
    payloads = {
        "mm2_config.toml": mm2_config,
        "mm2_rejection.json": b"{}\n",
        "mm2_failed_marker.json": b"{}\n",
        "mm2_closeout.json": b"{}\n",
    }
    for name, payload in payloads.items():
        (input_root / name).write_bytes(payload)
    text = CONFIG.read_text(encoding="utf-8")
    replacements = {
        "6c864d5e2dcc5156970eaadb051dba5f266ddd4a6f102a9fc9fa4407e06d9f04": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "d081298e546a92887519cb98a65e3c0bd4930590e0c26394a6a49f1ac8cd3984": hashlib.sha256(mm2_config).hexdigest(),
        "e98dcd1ef6c6c5f1590263bde56d83d579aba2ffd87869d7de04cf30ace67cf1": hashlib.sha256(payloads["mm2_rejection.json"]).hexdigest(),
        "4a852b0b6650a83df56b16e8036ce401d3ee39ca20a6e40482c50e032431ea92": hashlib.sha256(payloads["mm2_failed_marker.json"]).hexdigest(),
        "bf11358cbdb411532d2b3e9695d1e4c82585ba8751912ef98a495f8c334e6cb8": hashlib.sha256(payloads["mm2_closeout.json"]).hexdigest(),
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    config = tmp_path / "sparse.toml"
    config.write_text(text, encoding="utf-8")
    module.verify_inputs(config, input_root)
    (source / "configs/model_mismatch_v2.toml").write_text(
        "mutated\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="extracted MM-2 source differs"):
        module.verify_inputs(config, input_root)


def test_tiny_sampler_path_emits_only_diagnostic_fields(tmp_path: Path):
    module = _script_module(
        "experiments/sparse_mixing_diagnostic.py", "sparse_mixing_experiment"
    )
    plan = load_sparse_mixing_plan(CONFIG)
    base = next(task for task in plan.tasks() if not task.exact_replay)
    task = replace(
        base, warmup_steps=5, retained_steps=20, checkpoints=(10, 20)
    )
    thin = tmp_path / "thin.npz"
    record = module.run_sparse_mixing_task(
        plan, task, mm2_source=ROOT,
        mm2_config=ROOT / "configs/model_mismatch_v2.toml",
        thin_out=thin, workers=1,
    )
    validate_sparse_mixing_result(record, plan)
    assert record["sampler"]["early_stopping"] is False
    assert [row["retained_steps"] for row in record["checkpoints"]] == [10, 20]
    assert record["reconstruction"]["observation_count"] == 3
    assert contains_forbidden_key(
        record, plan.raw["outputs"]["forbidden_key_fragments"]
    ) is None
