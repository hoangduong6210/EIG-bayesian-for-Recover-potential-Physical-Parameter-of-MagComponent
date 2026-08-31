"""Endpoint-blind closeout tests for a non-admitted mismatch campaign."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from magcore_calib.model_mismatch import (
    MISMATCH_NON_ADMISSION_SCHEMA,
    MISMATCH_RESULT_SCHEMA,
    POLICIES,
    config_sha256,
    load_model_mismatch_plan,
    payload_sha256,
)


ROOT = Path(__file__).resolve().parents[1]


def _module():
    path = ROOT / "scripts" / "record_model_mismatch_non_admission.py"
    spec = importlib.util.spec_from_file_location("model_mismatch_closeout", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _result(plan, config_hash: str, scenario, seed: int) -> dict:
    endpoint = {
        "holdout_latent_mean": {},
        "holdout_pcv_by_temperature_c": {},
        "holdout_point_records": [],
        "gate_truth_accuracy": {"false_confident": False},
    }
    return {
        "schema_version": MISMATCH_RESULT_SCHEMA,
        "campaign_id": plan.campaign_id,
        "config_sha256": config_hash,
        "run_id": "test-run",
        "seed": seed,
        "scenario": scenario.as_dict(),
        "truth_anchor": {"values": {}, "sha256": payload_sha256({})},
        "data": {
            "common_candidate_outcomes_across_policies": True,
            "holdout_used_for_acquisition_or_stopping": False,
        },
        "inference_model": {
            "name": "isothermal_steinmetz_one_pole_cole_cole",
            "structural_discrepancy_terms_in_likelihood": False,
        },
        "policies": {
            policy: {
                "reached": False,
                "n_measurements_to_gate": None,
                "modeled_cost_to_gate": None,
                "mismatch_endpoints": endpoint,
            }
            for policy in POLICIES
        },
        "endpoint_contract": {},
        "validity": {
            f"{policy}_convergence_valid": True for policy in POLICIES
        },
        "provenance": {
            "estimator_decision_sha256": plan.estimator_decision_sha256,
        },
    }


def _run_fixture(
    tmp_path: Path, *, campaign_id: str = "MM-1",
) -> tuple[Path, str]:
    is_v2 = campaign_id == "MM-2"
    config_name = "model_mismatch_v2.toml" if is_v2 else "model_mismatch.toml"
    stage = "model_mismatch_v2" if is_v2 else "model_mismatch"
    summary = stage
    submission = "MM2_SUBMITTED" if is_v2 else "MM1_SUBMITTED"
    run = tmp_path / "run"
    for relative in (
        "source/configs", "provenance", "status",
        f"summary/{summary}", f"results/{stage}",
    ):
        (run / relative).mkdir(parents=True, exist_ok=True)
    decision = run / f"summary/{summary}/estimator_decision.json"
    decision.write_text('{"setting":"test"}\n', encoding="utf-8")
    decision_hash = hashlib.sha256(decision.read_bytes()).hexdigest()
    source_config = (ROOT / "configs" / config_name).read_text(encoding="utf-8")
    source_config = source_config.replace(
        "eb334ae2c188f12e7f544be71b6f0c40be15913ceec0df60e5bf9a9258ed82b6",
        decision_hash,
    )
    config = run / "source/configs" / config_name
    config.write_text(source_config, encoding="utf-8")
    plan = load_model_mismatch_plan(config)
    config_hash = config_sha256(config)
    (run / "provenance/run.env").write_text(
        "MAGCORE_RUN_ID=test-run\n"
        f"MAGCORE_GIT_REVISION={'a' * 40}\n"
        f"MAGCORE_SOURCE_ARCHIVE_SHA256={'b' * 64}\n"
        f"MAGCORE_SOURCE_STATUS_SHA256={'c' * 64}\n",
        encoding="utf-8",
    )
    (run / "status" / submission).write_text(
        '{"array_job_id":"123","aggregate_job_id":"456","task_count":120}\n',
        encoding="utf-8",
    )
    failed_task = (
        "combined_mismatch_seed9123" if is_v2
        else "permeability_two_pole_seed8108"
    )
    for scenario in plan.scenarios:
        for seed in plan.seeds:
            task = f"{scenario.name}_seed{seed}"
            if task == failed_task:
                (run / f"status/{stage}_{task}.failed").write_text(
                    json.dumps({
                        "stage": stage, "task": task,
                        "job_id": "789", "exit_code": 1, "line": 143,
                        "ended_at": "2026-08-27T07:52:33Z",
                    }) + "\n",
                    encoding="utf-8",
                )
                if is_v2:
                    rejection_dir = run / "status/model_mismatch_v2_rejections"
                    rejection_dir.mkdir(exist_ok=True)
                    (rejection_dir / f"{task}.json").write_text(
                        json.dumps({
                            "schema_version": "magcore-model-mismatch-rejection/1.0",
                            "record_class": "sampler_rejection_diagnostic",
                            "campaign_id": campaign_id,
                            "config_sha256": config_hash,
                            "seed": seed,
                            "scenario": scenario.name,
                            "reason": "posterior_convergence_gate_failed",
                            "invalid_policies": ["random_channel_balanced"],
                            "failed_states": {
                                "random_channel_balanced": [{"state": "test"}],
                            },
                            "disclosure": {
                                "scientific_endpoint_values_included": False,
                                "claim_bearing_result": False,
                            },
                        }) + "\n",
                        encoding="utf-8",
                    )
                continue
            result_dir = run / "results" / stage / task
            result_dir.mkdir()
            (result_dir / "result.json").write_text(
                json.dumps(_result(plan, config_hash, scenario, seed)) + "\n",
                encoding="utf-8",
            )
            (run / f"status/{stage}_{task}.done").write_text(
                json.dumps({
                    "stage": stage, "task": task,
                    "job_id": "789", "exit_code": 0,
                    "ended_at": "2026-08-27T07:00:00Z",
                }) + "\n",
                encoding="utf-8",
            )
    return run, failed_task


def test_closeout_records_complete_non_admission_without_endpoints(tmp_path: Path):
    module = _module()
    run, failed_task = _run_fixture(tmp_path)
    record = module.build_non_admission_record(run)
    assert record["schema_version"] == MISMATCH_NON_ADMISSION_SCHEMA
    assert record["admission"] == {
        "decision": "not_admitted",
        "confirmatory_claims_allowed": False,
        "endpoint_aggregation_performed": False,
        "reason_codes": [
            "declared_task_failed",
            "incomplete_result_matrix",
            "aggregate_not_created",
        ],
    }
    assert record["matrix"] == {
        "expected_task_count": 120,
        "validated_result_count": 119,
        "done_marker_count": 119,
        "failed_marker_count": 1,
        "unexplained_missing_task_count": 0,
        "extra_task_count": 0,
    }
    assert [item["task_id"] for item in record["failed_tasks"]] == [failed_task]
    encoded = json.dumps(record, sort_keys=True)
    for prohibited in (
        '"policies"', "holdout_latent_mean", "relative_rmse_pct",
        "paired_differences", "n_measurements_to_gate",
    ):
        assert prohibited not in encoded


def test_mm2_closeout_binds_rejection_without_aggregating_endpoints(tmp_path: Path):
    module = _module()
    run, failed_task = _run_fixture(tmp_path, campaign_id="MM-2")
    record = module.build_non_admission_record(run, campaign_id="MM-2")
    assert record["campaign_id"] == "MM-2"
    assert record["matrix"] == {
        "expected_task_count": 120,
        "validated_result_count": 119,
        "done_marker_count": 119,
        "failed_marker_count": 1,
        "rejection_record_count": 1,
        "unexplained_missing_task_count": 0,
        "extra_task_count": 0,
    }
    failed = record["failed_tasks"][0]
    assert failed["task_id"] == failed_task
    assert failed["rejection"]["reason"] == "posterior_convergence_gate_failed"
    assert failed["rejection"]["invalid_policies"] == [
        "random_channel_balanced"
    ]
    assert failed["rejection"]["failed_state_count"] == 1
    encoded = json.dumps(record, sort_keys=True)
    for prohibited in (
        '"policies"', "holdout_latent_mean", "relative_rmse_pct",
        "paired_differences", "n_measurements_to_gate",
    ):
        assert prohibited not in encoded


def test_closeout_rejects_unexplained_or_contradictory_task(tmp_path: Path):
    module = _module()
    run, failed_task = _run_fixture(tmp_path)
    failure = run / f"status/model_mismatch_{failed_task}.failed"
    failure.unlink()
    with pytest.raises(ValueError, match="incomplete or contradictory"):
        module.build_non_admission_record(run)

    scenario, seed_text = failed_task.rsplit("_seed", 1)
    plan = load_model_mismatch_plan(run / "source/configs/model_mismatch.toml")
    result_dir = run / "results/model_mismatch" / failed_task
    result_dir.mkdir()
    (result_dir / "result.json").write_text(
        json.dumps(_result(
            plan,
            config_sha256(run / "source/configs/model_mismatch.toml"),
            plan.scenario(scenario),
            int(seed_text),
        )) + "\n",
        encoding="utf-8",
    )
    failure.write_text(json.dumps({
        "stage": "model_mismatch", "task": failed_task,
        "exit_code": 1,
    }) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="incomplete or contradictory"):
        module.build_non_admission_record(run)


def test_closeout_write_is_atomic_and_append_only(tmp_path: Path):
    module = _module()
    run, _ = _run_fixture(tmp_path)
    record = module.build_non_admission_record(run)
    out = tmp_path / "public/non_admission.json"
    module._write_atomic_new(out, record)
    original = out.read_bytes()
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        module._write_atomic_new(out, record)
    assert out.read_bytes() == original
    assert not list(out.parent.glob("*.partial"))


def test_closeout_rejects_malformed_failure_marker(tmp_path: Path):
    module = _module()
    run, failed_task = _run_fixture(tmp_path)
    marker = run / f"status/model_mismatch_{failed_task}.failed"
    value = json.loads(marker.read_text(encoding="utf-8"))
    value["exit_code"] = 0
    marker.write_text(json.dumps(value) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="failure marker is malformed"):
        module.build_non_admission_record(run)
