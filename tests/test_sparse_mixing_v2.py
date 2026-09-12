"""Cheap registration and identity checks; these tests never run a sampler."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from magcore_calib.sparse_mixing import derive_task_seed, load_sparse_mixing_plan, sha256_file


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("sparse_mixing_v2_tested", ROOT / "experiments/sparse_mixing_v2.py")
assert SPEC and SPEC.loader
v2 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(v2)


@pytest.fixture
def registration(tmp_path):
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    parent = config_dir / "sparse_mixing_v1.toml"
    parent.write_bytes((ROOT / "configs/sparse_mixing_v1.toml").read_bytes())
    manifest = tmp_path / "pilot_manifest.json"
    manifest.write_text(json.dumps({
        "schema_version": "magcore-sparse-mixing-pilot-manifest/1.0",
        "protocol_id": "SparseMix-Pilot-1",
        "matrix": {"expected_task_count": 24, "validated_task_count": 24, "artifact_count": 72},
        "disclosure": {"automatic_admission": False},
        "method_summaries": {"n3": {"de_snooker": {}}, "n4": {"de_snooker": {}}},
    }))
    decision = tmp_path / "decision.json"
    decision.write_text(json.dumps({"selected_arm": "de_snooker", "complete_matrix": True,
                                    "pilot_manifest": "pilot_manifest.json",
                                    "pilot_manifest_sha256": sha256_file(manifest)}))
    config = config_dir / "sparse_mixing_v2.toml"
    config.write_text(f'''schema_version = "magcore-sparse-mixing-v2/1.0"
protocol_id = "SparseMix-2"
status = "preregistered_before_confirmatory_chains"
record_class = "endpoint_free_confirmatory_sampler_validation"
parent_config = "configs/sparse_mixing_v1.toml"
parent_config_sha256 = "{sha256_file(parent)}"
pilot_decision = "decision.json"
pilot_decision_sha256 = "{sha256_file(decision)}"
arms = ["de_snooker"]
families = ["local_prior_center", "overdispersed_prior_lhs"]
replicates = 4
warmup = 80000
retained = 800000
checkpoints = [20000, 40000, 80000, 160000, 320000, 480000, 640000, 800000]
n_walkers = 48
emcee_version = "3.1.6"
diagnostic_only = true
retroactive_mm2_admission_allowed = false
[selection]
require_complete_matrix = true
confirmatory_seeds_must_be_new = true
scientific_endpoints_allowed = false
[diagnostics]
minimum_finite_log_probability_fraction = 1.0
minimum_steps_per_tau = 50
minimum_effective_sample_size = 400
acceptance_range = [0.05, 0.80]
tau_stability_checkpoints = [640000, 800000]
maximum_relative_tau_change = 0.10
maximum_median_difference_pooled_sd = 0.10
maximum_tail_difference_pooled_iqr = 0.15
''')
    return config, decision


def test_registration_generates_sixteen_fresh_tasks(registration):
    path, _ = registration
    config = v2.load_config(path)
    matrix = v2.tasks(config)
    assert len(matrix) == 16
    assert len({row["task_id"] for row in matrix}) == 16
    assert len({row["initial_seed"] for row in matrix}) == 16
    assert len({row["sampler_seed"] for row in matrix}) == 16
    parent = load_sparse_mixing_plan(config["_parent_path"])
    prior_seeds = {row.seed for row in parent.tasks()}
    for target in parent.targets:
        for family in config["families"]:
            for replicate in range(2):
                prior_seeds.add(derive_task_seed("SparseMix-Pilot-1", target.state_identity_sha256, family, replicate))
                for arm in ("stretch", "de_snooker", "logit_stretch"):
                    prior_seeds.add(derive_task_seed("SparseMix-Pilot-1/" + arm, target.state_identity_sha256, family, replicate))
    assert not prior_seeds.intersection({row[key] for row in matrix for key in ("initial_seed", "sampler_seed")})
    assert [sum(row["target_id"] == name for row in matrix) for name in ("n3", "n4")] == [8, 8]


@pytest.mark.parametrize("old,new", [
    ('replicates = 4', 'replicates = 2'),
    ('warmup = 80000', 'warmup = 10000'),
    ('retained = 800000', 'retained = 80000'),
    ('n_walkers = 48', 'n_walkers = 24'),
    ('diagnostic_only = true', 'diagnostic_only = false'),
    ('retroactive_mm2_admission_allowed = false', 'retroactive_mm2_admission_allowed = true'),
    ('scientific_endpoints_allowed = false', 'scientific_endpoints_allowed = true'),
    ('require_complete_matrix = true', 'require_complete_matrix = false'),
    ('confirmatory_seeds_must_be_new = true', 'confirmatory_seeds_must_be_new = false'),
    ('arms = ["de_snooker"]', 'arms = ["de_snooker", "stretch"]'),
    ('arms = ["de_snooker"]', 'arms = ["unknown"]'),
    ('emcee_version = "3.1.6"', 'emcee_version = ">=3.1"'),
    ('preregistered_before_confirmatory_chains', 'posthoc'),
    ('640000, 800000]', '640000, 900000]'),
    ('pilot_decision = "decision.json"', 'pilot_decision = "../decision.json"'),
    ('pilot_decision = "decision.json"', 'pilot_decision = "/decision.json"'),
    ('minimum_finite_log_probability_fraction = 1.0', 'minimum_finite_log_probability_fraction = 0.99'),
    ('minimum_steps_per_tau = 50', 'minimum_steps_per_tau = 49'),
    ('minimum_effective_sample_size = 400', 'minimum_effective_sample_size = 200'),
    ('acceptance_range = [0.05, 0.80]', 'acceptance_range = [0.01, 0.95]'),
    ('tau_stability_checkpoints = [640000, 800000]', 'tau_stability_checkpoints = [320000, 800000]'),
    ('maximum_relative_tau_change = 0.10', 'maximum_relative_tau_change = 0.20'),
    ('maximum_median_difference_pooled_sd = 0.10', 'maximum_median_difference_pooled_sd = 0.20'),
    ('maximum_tail_difference_pooled_iqr = 0.15', 'maximum_tail_difference_pooled_iqr = 0.30'),
    ('minimum_finite_log_probability_fraction = 1.0', 'minimum_finite_log_probability_fraction = true'),
])
def test_registration_rejects_contract_changes(registration, old, new):
    path, _ = registration
    path.write_text(path.read_text().replace(old, new))
    with pytest.raises(ValueError):
        v2.load_config(path)


@pytest.mark.parametrize("key,value", [("selected_arm", "stretch"), ("complete_matrix", False),
                                        ("pilot_manifest_sha256", "broken")])
def test_bound_decision_must_support_registration(registration, key, value):
    path, decision = registration
    old_hash = sha256_file(decision)
    record = json.loads(decision.read_text())
    record[key] = value
    decision.write_text(json.dumps(record))
    path.write_text(path.read_text().replace(old_hash, sha256_file(decision)))
    with pytest.raises(ValueError):
        v2.load_config(path)


def test_changed_decision_bytes_are_rejected(registration):
    path, decision = registration
    decision.write_text(decision.read_text() + "\n")
    with pytest.raises(ValueError, match="decision checksum"):
        v2.load_config(path)


@pytest.mark.parametrize("mutation", ["hash", "protocol", "matrix", "admission", "target", "path"])
def test_referenced_manifest_is_verified(registration, mutation):
    path, decision = registration
    manifest = path.parent.parent / "pilot_manifest.json"
    old_decision_hash = sha256_file(decision)
    manifest_record = json.loads(manifest.read_text())
    if mutation == "protocol":
        manifest_record["protocol_id"] = "SparseMix-2"
    elif mutation == "matrix":
        manifest_record["matrix"]["validated_task_count"] = 23
    elif mutation == "admission":
        manifest_record["disclosure"]["automatic_admission"] = True
    elif mutation == "target":
        del manifest_record["method_summaries"]["n4"]["de_snooker"]
    manifest.write_text(json.dumps(manifest_record) + "\n")
    decision_record = json.loads(decision.read_text())
    if mutation != "hash":
        decision_record["pilot_manifest_sha256"] = sha256_file(manifest)
    if mutation == "path":
        decision_record["pilot_manifest"] = "../pilot_manifest.json"
    decision.write_text(json.dumps(decision_record))
    path.write_text(path.read_text().replace(old_decision_hash, sha256_file(decision)))
    with pytest.raises(ValueError):
        v2.load_config(path)


def test_move_constants_are_explicit():
    moves = v2.move_parameters("de_snooker")
    assert moves["DEMove"]["gamma0"] == 2.38 / np.sqrt(12)
    assert moves["DEMove"]["sigma"] == 1e-5
    assert moves["DEMove"]["weight"] == 0.8
    assert moves["DESnookerMove"]["weight"] == 0.2
    assert moves["DESnookerMove"]["nsplits"] == 4
    assert moves["DESnookerMove"]["gammas"] == 1.7
    assert v2.move_parameters("stretch") == v2.move_parameters("logit_stretch")
    with pytest.raises(ValueError):
        v2.move_parameters("unknown")


def test_runner_rejects_login_before_loading_data(monkeypatch, tmp_path):
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    monkeypatch.delenv("SLURM_JOB_NODELIST", raising=False)
    monkeypatch.setattr(v2, "tasks", lambda *_: pytest.fail("task data loaded before scheduler check"))
    with pytest.raises(RuntimeError):
        v2.run_task({}, {}, mm2_source=tmp_path, mm2_config=tmp_path, out_dir=tmp_path)


def test_runtime_version_must_match_before_data_load(monkeypatch, tmp_path):
    monkeypatch.setattr(v2, "require_slurm", lambda: None)
    monkeypatch.setattr(v2, "tasks", lambda *_: pytest.fail("task data loaded before version check"))
    with pytest.raises(ValueError, match="installed emcee"):
        v2.run_task({"emcee_version": "0.0.0"}, {}, mm2_source=tmp_path, mm2_config=tmp_path, out_dir=tmp_path)
