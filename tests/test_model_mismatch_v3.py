"""Cheap MM-3 prerequisite checks; no posterior chains or outcomes are run."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pytest

from magcore_calib.model_mismatch import (
    MISMATCH_CONFIG_QUALIFIED_SCHEMA, MISMATCH_REJECTION_SCHEMA,
    load_model_mismatch_plan, validate_mismatch_rejection,
)


ROOT = Path(__file__).resolve().parents[1]
QUALIFICATION = ROOT / "results/diagnostics/sparse_mixing/SparseMix-2/20260912T060428Z_7a00dff3106f/manifest.json"


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def registration(tmp_path):
    configs = tmp_path / "configs"
    configs.mkdir()
    qualified_config = configs / "sparse_mixing_v2.toml"
    qualified_config.write_bytes((ROOT / "configs/sparse_mixing_v2.toml").read_bytes())
    manifest = tmp_path / "qualification.json"
    manifest.write_bytes(QUALIFICATION.read_bytes())
    text = (ROOT / "configs/model_mismatch_v2.toml").read_text()
    text = text.replace('preregistration/1.1', 'preregistration/1.2')
    text = text.replace('campaign_id = "MM-2"', 'campaign_id = "MM-3"', 1)
    text = text.replace('predecessor_campaign_id = "MM-1"', 'predecessor_campaign_id = "MM-2"')
    text = text.replace('dba31b989debfe1729261a0fb42e07317069a97095b743c0d73237500e5a5207', 'bf11358cbdb411532d2b3e9695d1e4c82585ba8751912ef98a495f8c334e6cb8')
    text = text.replace('mm2_confirmatory_seed_v1', 'mm3_confirmatory_seed_v1')
    text = re.sub(r'^seeds = \[.*?\]', 'seeds = ' + str(list(range(10100, 10130))), text, flags=re.M | re.S)
    text = re.sub(r'^forbidden_development_seeds = \[.*?\]', 'forbidden_development_seeds = ' + str(list(range(7300, 7330)) + list(range(8100, 8130)) + list(range(9100, 9130))), text, flags=re.M | re.S)
    text = text.replace('[runtime]', '[runtime]\nsampler_method = "de_snooker"')
    text = text.replace('burn = 4000', 'burn = 80000').replace('max_steps = 320000', 'max_steps = 800000').replace('check_interval = 10000', 'check_interval = 20000')
    text = (
        'sampler_qualification_manifest = "qualification.json"\n'
        f'sampler_qualification_manifest_sha256 = "{_sha(manifest)}"\n'
        'sampler_qualification_config = "configs/sparse_mixing_v2.toml"\n'
        f'sampler_qualification_config_sha256 = "{_sha(qualified_config)}"\n'
    ) + text
    config = configs / "model_mismatch_v3.toml"
    config.write_text(text)
    return config, manifest


def test_mm3_requires_actual_completed_qualification_and_fresh_seeds(registration):
    path, manifest = registration
    plan = load_model_mismatch_plan(path)
    assert plan.schema_version == MISMATCH_CONFIG_QUALIFIED_SCHEMA
    assert plan.campaign_id == "MM-3"
    assert plan.seeds == tuple(range(10100, 10130))
    assert plan.task_count == 120
    assert plan.sampler_method == "de_snooker"
    assert plan.sampler_qualification_manifest_sha256 == _sha(manifest)
    assert (plan.n_walkers, plan.n_steps, plan.burn, plan.max_steps, plan.check_interval) == (48, 20000, 80000, 800000, 20000)
    assert plan.as_dict()["runtime"]["sampler_method"] == "de_snooker"


def test_legacy_plan_serialization_and_runtime_are_unchanged():
    for name in ("model_mismatch.toml", "model_mismatch_v2.toml"):
        plan = load_model_mismatch_plan(ROOT / "configs" / name)
        assert plan.sampler_method == "stretch"
        assert "sampler_method" not in plan.as_dict()["runtime"]
        assert "sampler_qualification" not in plan.as_dict()
        assert plan.burn == 4000


@pytest.mark.parametrize("old,new", [
    ('sampler_method = "de_snooker"', 'sampler_method = "stretch"'),
    ('burn = 80000', 'burn = 4000'),
    ('check_interval = 20000', 'check_interval = 10000'),
    ('max_steps = 800000', 'max_steps = 320000'),
    ('10100, 10101', '9100, 10101'),
    ('9100, 9101', '9900, 9101'),
    ('mm3_confirmatory_seed_v1', 'mm2_confirmatory_seed_v1'),
    ('predecessor_campaign_id = "MM-2"', 'predecessor_campaign_id = "MM-1"'),
    ('"qualification.json"', '"../qualification.json"'),
    ('"qualification.json"', '"/qualification.json"'),
])
def test_mm3_rejects_runtime_lineage_and_namespace_changes(registration, old, new):
    path, _ = registration
    assert old in path.read_text()
    path.write_text(path.read_text().replace(old, new))
    with pytest.raises(ValueError):
        load_model_mismatch_plan(path)


def _rejection(undefined_tau=False):
    from magcore_calib.inference import _de_checkpoint_report

    history = []
    previous, stable = None, 0
    tau = np.full(6, np.nan if undefined_tau else 20000.0)
    for retained in range(20000, 800001, 20000):
        # Shape-only read-only broadcast: no chain allocation or sampling.
        view = np.broadcast_to(0.0, (retained, 48, 6))
        report, stable = _de_checkpoint_report(view, np.array([0.3]), tau, np.array([0.0]), previous, stable)
        history.append(report)
        previous = tau
    diagnostic = dict(history[-1])
    diagnostic["adaptive_sampling"] = {
        "minimum_retained_steps": 20000, "maximum_retained_steps": 800000,
        "check_interval_steps": 20000, "actual_retained_steps": 800000,
        "extension_count": 39, "stopped_reason": "maximum_steps", "checkpoint_history": history,
    }
    parity = {"rows": 48, "rtol": 1e-11, "atol": 1e-8, "maximum_absolute_difference": 0.0}
    diagnostic["sampler"] = {
        "method": "de_snooker", "implementation": "emcee.EnsembleSampler", "version": "3.1.6",
        "vectorize": True, "acceptance_window": "retained_only", "warmup_steps": 80000,
        "move_parameters": {
            "DEMove": {"weight": 0.8, "sigma": 1e-5, "gamma0": float(2.38 / np.sqrt(12)), "nsplits": 2, "randomize_split": True},
            "DESnookerMove": {"weight": 0.2, "gammas": 1.7, "nsplits": 4, "randomize_split": True},
        },
        "density_parity": {"initial": parity.copy(), "final": parity.copy()},
        "qualification_scope": "Production evaluates one adaptive ensemble per state.",
    }
    return {
        "schema_version": MISMATCH_REJECTION_SCHEMA, "record_class": "sampler_rejection_diagnostic",
        "campaign_id": "MM-3", "config_sha256": "a" * 64,
        "estimator_decision_sha256": "b" * 64, "run_id": "test", "seed": 10100,
        "scenario": "combined_mismatch", "reason": "posterior_convergence_gate_failed",
        "validator_message": "nonconverged policy", "invalid_policies": ["eig_raw"],
        "failed_states": {"eig_raw": [{"state_identity_sha256": "c" * 64,
                                      "n_measurements": 3, "mcmc_seed": 19,
                                      "sampler_diagnostics": diagnostic}]},
        "disclosure": {"scientific_endpoint_values_included": False, "claim_bearing_result": False},
    }


@pytest.mark.parametrize("undefined_tau", [False, True])
def test_mm3_rejection_retains_exhausted_diagnostics_including_undefined_tau(undefined_tau):
    validate_mismatch_rejection(_rejection(undefined_tau))


@pytest.mark.parametrize("change", ["legacy", "endpoint", "history", "move", "method", "parity", "fraction"])
def test_mm3_rejection_schema_remains_strict_and_does_not_weaken_legacy(change):
    record = _rejection()
    diagnostic = record["failed_states"]["eig_raw"][0]["sampler_diagnostics"]
    if change == "legacy":
        record["campaign_id"] = "MM-2"
    elif change == "endpoint":
        diagnostic["adaptive_sampling"]["checkpoint_history"][0]["holdout_error"] = 10.0
    elif change == "history":
        diagnostic["adaptive_sampling"]["checkpoint_history"].pop()
    elif change == "move":
        diagnostic["sampler"]["move_parameters"]["DEMove"]["weight"] = 0.5
    elif change == "method":
        diagnostic["sampler"]["method"] = "stretch"
    elif change == "parity":
        diagnostic["sampler"]["density_parity"]["final"]["maximum_absolute_difference"] = float("nan")
    else:
        diagnostic["acceptance_fraction"] = float("nan")
    with pytest.raises(ValueError):
        validate_mismatch_rejection(record)


def test_mm3_rejects_manifest_byte_mutation(registration):
    path, manifest = registration
    manifest.write_bytes(manifest.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="checksum"):
        load_model_mismatch_plan(path)


@pytest.mark.parametrize("change", ["overall", "one_state", "count", "duplicate", "artifact", "config", "disclosure", "protocol"])
def test_mm3_rejects_incomplete_or_unqualified_manifest_even_when_rehashed(registration, change):
    path, manifest_path = registration
    old_sha = _sha(manifest_path)
    manifest = json.loads(manifest_path.read_text())
    if change == "overall":
        manifest["both_states_pass"] = False
    elif change == "one_state":
        manifest["classifications"]["n4"]["criteria_passed"] = False
    elif change == "count":
        manifest["matrix"]["validated_task_count"] = 15
    elif change == "duplicate":
        manifest["tasks"][-1] = manifest["tasks"][0]
    elif change == "artifact":
        manifest["artifacts"][0]["chain_sha256"] = "unknown"
    elif change == "config":
        manifest["config_sha256"] = "a" * 64
    elif change == "disclosure":
        manifest["disclosure"]["retroactive_mm2_admission_allowed"] = True
    else:
        manifest["protocol_id"] = "SparseMix-1"
    manifest_path.write_text(json.dumps(manifest))
    path.write_text(path.read_text().replace(old_sha, _sha(manifest_path)))
    with pytest.raises(ValueError):
        load_model_mismatch_plan(path)
