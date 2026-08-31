#!/usr/bin/env python3
"""Close an incomplete model-mismatch campaign without aggregating endpoints."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
from pathlib import Path
from typing import Any

from magcore_calib.model_mismatch import (
    MISMATCH_NON_ADMISSION_SCHEMA,
    config_sha256,
    load_model_mismatch_plan,
    validate_mismatch_result,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_run_environment(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#"):
            continue
        key, separator, encoded = line.partition("=")
        if not separator or not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            raise ValueError("run.env contains a malformed assignment")
        decoded = shlex.split(encoded, posix=True)
        if len(decoded) != 1:
            raise ValueError(f"run.env value is malformed: {key}")
        values[key] = decoded[0]
    required = {
        "MAGCORE_RUN_ID", "MAGCORE_GIT_REVISION",
        "MAGCORE_SOURCE_ARCHIVE_SHA256", "MAGCORE_SOURCE_STATUS_SHA256",
    }
    if not required <= values.keys():
        raise ValueError("run.env lacks required immutable-run provenance")
    if not re.fullmatch(r"[0-9a-f]{40}", values["MAGCORE_GIT_REVISION"]):
        raise ValueError("run.env has an invalid git revision")
    for key in ("MAGCORE_SOURCE_ARCHIVE_SHA256", "MAGCORE_SOURCE_STATUS_SHA256"):
        if not re.fullmatch(r"[0-9a-f]{64}", values[key]):
            raise ValueError(f"run.env has an invalid digest: {key}")
    return values


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def _expected_tasks(plan) -> dict[str, tuple[str, int]]:
    return {
        f"{scenario.name}_seed{seed}": (scenario.name, seed)
        for scenario in plan.scenarios
        for seed in plan.seeds
    }


def _campaign_layout(campaign_id: str) -> dict[str, str]:
    layouts = {
        "MM-1": {
            "config": "model_mismatch.toml",
            "submission": "MM1_SUBMITTED",
            "stage": "model_mismatch",
            "summary": "model_mismatch",
            "aggregate_stage": "model_mismatch_aggregate",
            "rejection_directory": "",
        },
        "MM-2": {
            "config": "model_mismatch_v2.toml",
            "submission": "MM2_SUBMITTED",
            "stage": "model_mismatch_v2",
            "summary": "model_mismatch_v2",
            "aggregate_stage": "model_mismatch_v2_aggregate",
            "rejection_directory": "model_mismatch_v2_rejections",
        },
    }
    try:
        return layouts[campaign_id]
    except KeyError as error:
        raise ValueError(f"unsupported model-mismatch campaign: {campaign_id}") from error


def _write_atomic_new(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"refusing to overwrite non-admission record: {path}")
    partial = path.with_name(f".{path.name}.{os.getpid()}.partial")
    try:
        with partial.open("x", encoding="utf-8") as stream:
            json.dump(payload, stream, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(partial, 0o640)
        os.link(partial, path)
    finally:
        partial.unlink(missing_ok=True)


def build_non_admission_record(
    run_dir: Path, *, campaign_id: str = "MM-1",
) -> dict[str, Any]:
    run_dir = run_dir.expanduser().resolve()
    layout = _campaign_layout(campaign_id)
    config = run_dir / "source" / "configs" / layout["config"]
    run_env_path = run_dir / "provenance" / "run.env"
    submission_path = run_dir / "status" / layout["submission"]
    decision_path = (
        run_dir / "summary" / layout["summary"] / "estimator_decision.json"
    )
    for required in (config, run_env_path, submission_path, decision_path):
        if not required.is_file():
            raise FileNotFoundError(f"missing {campaign_id} closeout input: {required}")

    plan = load_model_mismatch_plan(config)
    if plan.campaign_id != campaign_id:
        raise ValueError("campaign layout differs from the frozen configuration")
    run_env = _read_run_environment(run_env_path)
    submission = _load_json(submission_path)
    expected = _expected_tasks(plan)
    expected_config_sha = config_sha256(config)
    if _sha256(decision_path) != plan.estimator_decision_sha256:
        raise ValueError("locked estimator decision differs from the campaign contract")
    for key in ("array_job_id", "aggregate_job_id"):
        if not re.fullmatch(r"[1-9][0-9]*", str(submission.get(key, ""))):
            raise ValueError(f"{layout['submission']} has an invalid {key}")
    if submission.get("task_count") != len(expected):
        raise ValueError(
            f"{layout['submission']} task count differs from the campaign contract"
        )

    status_dir = run_dir / "status"
    stage = layout["stage"]
    results_root = run_dir / "results" / stage
    result_paths = {
        path.parent.name: path
        for path in results_root.glob("*/result.json")
    }
    done_paths = {
        path.name.removeprefix(f"{stage}_").removesuffix(".done"): path
        for path in status_dir.glob(f"{stage}_*.done")
        if not path.name.startswith(f"{layout['aggregate_stage']}_")
    }
    failed_paths = {
        path.name.removeprefix(f"{stage}_").removesuffix(".failed"): path
        for path in status_dir.glob(f"{stage}_*.failed")
        if not path.name.startswith(f"{layout['aggregate_stage']}_")
    }
    observed = set(result_paths) | set(done_paths) | set(failed_paths)
    extra = sorted(observed - expected.keys())
    if extra:
        raise ValueError(f"{campaign_id} closeout contains undeclared tasks: {extra}")

    rejection_paths: dict[str, Path] = {}
    if layout["rejection_directory"]:
        rejection_root = status_dir / layout["rejection_directory"]
        rejection_paths = {
            path.stem: path for path in rejection_root.glob("*.json")
        }
        extra_rejections = sorted(rejection_paths.keys() - expected.keys())
        if extra_rejections:
            raise ValueError(
                f"{campaign_id} closeout contains undeclared rejections: "
                f"{extra_rejections}"
            )

    validated_results: list[dict[str, Any]] = []
    failed_tasks: list[dict[str, Any]] = []
    unexplained: list[str] = []
    for task_id, (scenario, seed) in expected.items():
        has_result = task_id in result_paths
        has_done = task_id in done_paths
        has_failed = task_id in failed_paths
        if has_result and has_done and not has_failed:
            if task_id in rejection_paths:
                raise ValueError(
                    f"successful task cannot have a rejection record: {task_id}"
                )
            path = result_paths[task_id]
            record = _load_json(path)
            validate_mismatch_result(record)
            if record["campaign_id"] != plan.campaign_id \
                    or record["config_sha256"] != expected_config_sha \
                    or record["scenario"] != plan.scenario(scenario).as_dict() \
                    or record["seed"] != seed \
                    or record["provenance"].get("estimator_decision_sha256") \
                    != plan.estimator_decision_sha256:
                raise ValueError(f"result differs from the frozen contract: {task_id}")
            done = _load_json(done_paths[task_id])
            if done.get("stage") != stage \
                    or done.get("task") != task_id \
                    or done.get("exit_code") != 0:
                raise ValueError(f"success marker is malformed: {task_id}")
            validated_results.append({
                "task_id": task_id,
                "scenario": scenario,
                "seed": seed,
                "path": path.relative_to(run_dir).as_posix(),
                "sha256": _sha256(path),
                "done_marker_sha256": _sha256(done_paths[task_id]),
            })
        elif has_failed and not has_result and not has_done:
            marker_path = failed_paths[task_id]
            marker = _load_json(marker_path)
            exit_code = marker.get("exit_code")
            if marker.get("stage") != stage \
                    or marker.get("task") != task_id \
                    or isinstance(exit_code, bool) \
                    or not isinstance(exit_code, int) \
                    or exit_code == 0:
                raise ValueError(f"failure marker is malformed: {task_id}")
            failed_entry = {
                "task_id": task_id,
                "scenario": scenario,
                "seed": seed,
                "marker": {
                    "path": marker_path.relative_to(run_dir).as_posix(),
                    "sha256": _sha256(marker_path),
                    "exit_code": exit_code,
                    "ended_at": marker.get("ended_at"),
                },
            }
            rejection_path = rejection_paths.get(task_id)
            if rejection_path is not None:
                rejection = _load_json(rejection_path)
                if rejection.get("campaign_id") != campaign_id \
                        or rejection.get("config_sha256") != expected_config_sha \
                        or rejection.get("scenario") != scenario \
                        or rejection.get("seed") != seed \
                        or rejection.get("record_class") \
                        != "sampler_rejection_diagnostic" \
                        or rejection.get("disclosure") != {
                            "scientific_endpoint_values_included": False,
                            "claim_bearing_result": False,
                        }:
                    raise ValueError(f"rejection record is malformed: {task_id}")
                failed_entry["rejection"] = {
                    "path": rejection_path.relative_to(run_dir).as_posix(),
                    "sha256": _sha256(rejection_path),
                    "reason": rejection.get("reason"),
                    "invalid_policies": rejection.get("invalid_policies"),
                    "failed_state_count": sum(
                        len(states)
                        for states in rejection.get("failed_states", {}).values()
                    ),
                    "diagnostic": {
                        "schema_version": rejection.get("schema_version"),
                        "reason": rejection.get("reason"),
                        "invalid_policies": rejection.get("invalid_policies"),
                        "failed_states": rejection.get("failed_states"),
                        "disclosure": rejection.get("disclosure"),
                    },
                }
            elif plan.retain_rejection_diagnostics:
                raise ValueError(f"required rejection record is missing: {task_id}")
            failed_tasks.append(failed_entry)
        else:
            unexplained.append(task_id)
    if unexplained:
        raise ValueError(
            f"{campaign_id} closeout matrix is incomplete or contradictory: "
            f"{sorted(unexplained)}"
        )
    if not failed_tasks:
        raise ValueError("non-admission requires at least one declared failed task")

    aggregate_path = run_dir / "summary" / layout["summary"] / "aggregate.json"
    aggregate_marker = status_dir / f"{layout['aggregate_stage']}_0.done"
    if aggregate_path.exists() or aggregate_marker.exists():
        raise ValueError("non-admission cannot coexist with an admitted aggregate")

    validated_results.sort(key=lambda item: item["task_id"])
    failed_tasks.sort(key=lambda item: item["task_id"])
    return {
        "schema_version": MISMATCH_NON_ADMISSION_SCHEMA,
        "record_class": "diagnostic_campaign_closeout",
        "campaign_id": plan.campaign_id,
        "frozen_contract": {
            "config_sha256": expected_config_sha,
            "estimator_source_release_id": plan.estimator_source_release_id,
            "estimator_decision_sha256": plan.estimator_decision_sha256,
            "campaign_source_revision": run_env["MAGCORE_GIT_REVISION"],
            "source_archive_sha256": run_env["MAGCORE_SOURCE_ARCHIVE_SHA256"],
            "source_status_sha256": run_env["MAGCORE_SOURCE_STATUS_SHA256"],
        },
        "run_provenance": {"run_id": run_env["MAGCORE_RUN_ID"]},
        "scheduler_submission": {
            "array_job_id": str(submission["array_job_id"]),
            "aggregate_job_id": str(submission["aggregate_job_id"]),
        },
        "admission": {
            "decision": "not_admitted",
            "confirmatory_claims_allowed": False,
            "endpoint_aggregation_performed": False,
            "reason_codes": [
                "declared_task_failed",
                "incomplete_result_matrix",
                "aggregate_not_created",
            ],
        },
        "matrix": {
            "expected_task_count": len(expected),
            "validated_result_count": len(validated_results),
            "done_marker_count": len(done_paths),
            "failed_marker_count": len(failed_tasks),
            **({"rejection_record_count": len(rejection_paths)}
               if layout["rejection_directory"] else {}),
            "unexplained_missing_task_count": 0,
            "extra_task_count": 0,
        },
        "failed_tasks": failed_tasks,
        "validated_results": validated_results,
        "disclosure": {
            "scientific_endpoint_values_included": False,
            "scientific_endpoint_summaries_included": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--campaign-id", choices=("MM-1", "MM-2"), default="MM-1")
    args = parser.parse_args()
    record = build_non_admission_record(
        args.run_dir, campaign_id=args.campaign_id
    )
    _write_atomic_new(args.out.expanduser().resolve(), record)
    print(args.out)


if __name__ == "__main__":
    main()
