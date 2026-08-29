"""Scientific and operational contract tests for the MM-2 successor."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from magcore_calib.model_mismatch import (
    MISMATCH_CONFIG_SUCCESSOR_SCHEMA,
    MISMATCH_REJECTION_SCHEMA,
    POLICIES,
    load_model_mismatch_plan,
)


ROOT = Path(__file__).resolve().parents[1]
MM1_CONFIG = ROOT / "configs/model_mismatch.toml"
MM2_CONFIG = ROOT / "configs/model_mismatch_v2.toml"
MM1_CLOSEOUT = (
    ROOT / "results/diagnostics/model_mismatch/MM-1"
    / "20260827T045036Z_e4c674a6ff98/non_admission.json"
)


def test_mm2_is_an_independent_successor_with_only_declared_changes():
    mm1 = load_model_mismatch_plan(MM1_CONFIG)
    mm2 = load_model_mismatch_plan(MM2_CONFIG)
    assert mm2.schema_version == MISMATCH_CONFIG_SUCCESSOR_SCHEMA
    assert mm2.campaign_id == "MM-2"
    assert mm2.predecessor_campaign_id == "MM-1"
    assert mm2.predecessor_non_admission_sha256 == hashlib.sha256(
        MM1_CLOSEOUT.read_bytes()
    ).hexdigest()
    assert mm2.seed_namespace == "mm2_confirmatory_seed_v1"
    assert mm2.retain_rejection_diagnostics is True
    assert mm2.seeds == tuple(range(9100, 9130))
    assert set(mm1.seeds) <= set(mm2.forbidden_development_seeds)
    assert set(mm2.seeds).isdisjoint(mm2.forbidden_development_seeds)
    assert mm2.scenarios == mm1.scenarios
    assert mm2.temperatures_c == mm1.temperatures_c
    assert mm2.policies == mm1.policies == POLICIES
    assert mm2.estimator_source_release_id == mm1.estimator_source_release_id
    assert mm2.estimator_decision_sha256 == mm1.estimator_decision_sha256
    assert (
        mm2.n_walkers, mm2.n_steps, mm2.burn, mm2.check_interval,
        mm2.max_measurements, mm2.pcv_gate_pct, mm2.lm_gate_pct,
        mm2.false_confidence_pcv_error_pct,
        mm2.false_confidence_lm_error_pct,
    ) == (
        mm1.n_walkers, mm1.n_steps, mm1.burn, mm1.check_interval,
        mm1.max_measurements, mm1.pcv_gate_pct, mm1.lm_gate_pct,
        mm1.false_confidence_pcv_error_pct,
        mm1.false_confidence_lm_error_pct,
    )
    assert mm1.max_steps == 80_000
    assert mm2.max_steps == 320_000
    assert mm2.task_count == 120


def test_successor_loader_rejects_observed_mm1_seed(tmp_path: Path):
    text = MM2_CONFIG.read_text(encoding="utf-8").replace(
        "9100, 9101", "8100, 9101", 1
    )
    path = tmp_path / "invalid.toml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="overlap forbidden"):
        load_model_mismatch_plan(path)


def _campaign_module():
    experiments = str(ROOT / "experiments")
    if experiments not in sys.path:
        sys.path.insert(0, experiments)
    path = ROOT / "experiments/model_mismatch_campaign.py"
    spec = importlib.util.spec_from_file_location("model_mismatch_v2_campaign", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rejection_sidecar_contains_sampler_diagnostics_but_no_endpoints():
    module = _campaign_module()
    diagnostics = {
        "valid": False,
        "tau": {"k": 2000.0},
        "ess": {"k": 300.0},
        "steps_per_tau": {"k": 40.0},
        "acceptance_fraction": 0.31,
        "adaptive_sampling": {
            "actual_retained_steps": 80_000,
            "stopped_reason": "maximum_steps",
        },
    }
    validities = {f"{policy}_convergence_valid": True for policy in POLICIES}
    validities["eig_raw_convergence_valid"] = False
    record = {
        "campaign_id": "MM-2",
        "config_sha256": "a" * 64,
        "run_id": "test",
        "seed": 9100,
        "scenario": {"name": "matched_control"},
        "validity": validities,
        "policies": {
            policy: {"trajectory": ([{
                "n_measurements": 4,
                "decision_state": {
                    "valid": False,
                    "state_identity_sha256": "b" * 64,
                    "mcmc_seed": 123,
                    "sampler_diagnostics": diagnostics,
                },
                "n_measurements_to_gate": 7,
            }] if policy == "eig_raw" else [])}
            for policy in POLICIES
        },
        "provenance": {"estimator_decision_sha256": "c" * 64},
    }
    rejection = module._rejection_record(
        record, ValueError("model-mismatch result contains a nonconverged policy")
    )
    assert rejection["schema_version"] == MISMATCH_REJECTION_SCHEMA
    assert rejection["invalid_policies"] == ["eig_raw"]
    assert rejection["failed_states"]["eig_raw"][0][
        "sampler_diagnostics"
    ] == diagnostics
    assert rejection["disclosure"] == {
        "scientific_endpoint_values_included": False,
        "claim_bearing_result": False,
    }
    encoded = json.dumps(rejection, sort_keys=True)
    for prohibited in (
        "n_measurements_to_gate", "holdout", "relative_rmse_pct",
        "candidate_scores", "gate_truth_accuracy",
    ):
        assert prohibited not in encoded


def test_mm2_scheduler_contract_is_fail_closed_and_full_matrix():
    submit = ROOT / "scripts/submit_model_mismatch_v2.sh"
    watcher = ROOT / "scripts/watch_model_mismatch_v2.sh"
    array = ROOT / "slurm/24_model_mismatch_v2.sbatch"
    aggregate = ROOT / "slurm/25_model_mismatch_v2_aggregate.sbatch"
    for script in (submit, watcher, array, aggregate):
        subprocess.run(["bash", "-n", str(script)], check=True)
    submit_text = submit.read_text(encoding="utf-8")
    assert "predecessor_non_admission_sha256" in submit_text
    assert "prepared source differs from the immutable archive" in submit_text
    assert "MM2_SUBMISSION_FAILED" in submit_text
    assert '0-$((TASK_COUNT - 1))%10' in submit_text
    assert 'afterok:$ARRAY' in submit_text
    array_text = array.read_text(encoding="utf-8")
    assert "model_mismatch_v2.toml" in array_text
    assert "--rejection-out" in array_text
    assert "model_mismatch_v2_rejections" in array_text
    watcher_text = watcher.read_text(encoding="utf-8")
    assert "COMPLETED + FAILED == TASK_COUNT" in watcher_text
    assert "rejection_records" in watcher_text
