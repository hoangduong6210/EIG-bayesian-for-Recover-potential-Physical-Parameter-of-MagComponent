"""Deterministic tests for the sanitized public evidence projection."""

from __future__ import annotations

import importlib.util
import hashlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_module():
    path = ROOT / "scripts" / "public_audit_bundle.py"
    spec = importlib.util.spec_from_file_location("public_audit_bundle_for_tests", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_published_v2_asset_descriptor_is_complete_and_source_bound():
    path = (
        ROOT / "results" / "audit" / "20260817T072230Z_401e3030fe13"
        / "asset.json"
    )
    descriptor = json.loads(path.read_text(encoding="utf-8"))
    assert descriptor["schema_version"] == "magnetic-public-audit-assets/2.0"
    assert descriptor["source_release_manifest_sha256"] == (
        "85448a2c3c9db2db051c94543d8a336e7157d55289f10c1792e9c57d433812f7"
    )
    assets = {item["scope"]: item for item in descriptor["assets"]}
    assert set(assets) == {"records_only", "with_samples"}
    assert assets["records_only"]["root_manifest_sha256"] == (
        "fa0f25c2d497bdd02445f8bb51a056ba814a231af29981bf39d83fb5c7e6d103"
    )
    assert assets["with_samples"]["root_manifest_sha256"] == (
        "7de184a33e69dd3ecdb58919cbd1a9162626460d4b2bcc678abfa7ff0735b753"
    )
    assert all("/releases/download/evidence-20260817-audit-v2/" in item["asset_url"]
               for item in assets.values())
    assert descriptor["raw_to_aggregate_match"] is True


def test_sanitizer_removes_machine_provenance_and_rewrites_legacy_paths():
    module = load_module()
    phase = "p" + "2_"
    raw = {
        "provenance": {
            "command": ["/" + "users/account/run.py"],
            "slurm": {"node_list": "compute001", "job_id": "7"},
            "seed": 42,
            "git_commit": "a" * 40,
            "configuration_sha256": "b" * 64,
            "dependency_lock_sha256": "c" * 64,
            "command_sha256": "d" * 64,
            "data_sha256": {"synthetic://seed-and-command": "e" * 64},
            "python": "3.12.4",
            "started_at_utc": "2026-08-12T00:00:00Z",
            "ended_at_utc": "2026-08-12T00:01:00Z",
        },
        phase + "selection_sha256": "f" * 64,
        "path": "/" + "users/account/run/results/" + phase
                + "states/s7100_n2/state.json",
    }
    public = module._sanitize(raw)
    assert "command" not in public["provenance"]
    assert "slurm" not in public["provenance"]
    assert public["estimator_decision_sha256"] == "f" * 64
    assert public["path"] == "estimator_validation/states/s7100_n2/state.json"
    module._assert_safe_json(Path("record.json"), public)


def _write_minimal_bundle(module, bundle: Path) -> None:
    static_path = bundle / "estimator_validation/decisions/static_decision.json"
    module._write_json(static_path, {"inputs": [], "valid": True})
    final_path = bundle / "estimator_validation/decisions/final_decision.json"
    final = {
        "selection_sha256": module.sha256_file(static_path),
        "selection_path": "estimator_validation/decisions/static_decision.json",
        "objectives": {},
        "valid": True,
    }
    module._write_json(final_path, final)
    acquisition = {
        "provenance": {"seed": 7300},
        "data": {"common_random_outcomes": True},
        "design": {
            "estimator_decision_sha256": module.sha256_file(final_path),
            "policies": {
                "eig_raw": {
                    "n_measurements_to_gate": 5,
                    "modeled_cost_to_gate": 175.0,
                },
                "eig_per_cost": {
                    "n_measurements_to_gate": 6,
                    "modeled_cost_to_gate": 190.0,
                },
                "fixed_channel_balanced": {
                    "n_measurements_to_gate": 9,
                    "modeled_cost_to_gate": 290.0,
                },
            },
        },
    }
    acquisition_path = bundle / "acquisition/seed7300/eig_seed7300.json"
    module._write_json(acquisition_path, acquisition)
    summary_path = bundle / "aggregate/paper_summary.json"
    module._write_json(summary_path, {
        "eig": module._headline_from_trajectories([acquisition]),
    })

    artifacts = {
        "estimator_validation/decisions/static_decision.json": "estimator_static_decision",
        "estimator_validation/decisions/final_decision.json": "estimator_final_decision",
        "acquisition/seed7300/eig_seed7300.json": "acquisition_trajectory",
        "aggregate/paper_summary.json": "published_aggregate",
    }
    entries = []
    for relative, record_class in artifacts.items():
        path = bundle / relative
        entries.append({
            "path": relative,
            "record_class": record_class,
            "sha256": module.sha256_file(path),
            "bytes": path.stat().st_size,
            "source_sha256": "0" * 64,
        })
    checksum_path = bundle / "checksums.sha256"
    checksum_path.write_text(
        "\n".join(f"{entry['sha256']}  {entry['path']}" for entry in entries) + "\n",
        encoding="utf-8",
    )
    checksum_entry = {
        "path": "checksums.sha256",
        "record_class": "checksum_index",
        "sha256": module.sha256_file(checksum_path),
        "bytes": checksum_path.stat().st_size,
    }
    counts = {}
    for entry in entries:
        counts[entry["record_class"]] = counts.get(entry["record_class"], 0) + 1
    module._write_json(bundle / "manifest.json", {
        "schema_version": module.BUNDLE_SCHEMA,
        "release_id": "20260812T035654Z_a0703698ace9",
        "scope": {"contains_posterior_samples": False},
        "record_class_counts": counts,
        "files": [*entries, checksum_entry],
    })


def test_verifier_reconstructs_acquisition_aggregate_and_detects_tampering(tmp_path: Path):
    module = load_module()
    bundle = tmp_path / "audit"
    bundle.mkdir()
    _write_minimal_bundle(module, bundle)
    report = module.verify_bundle(bundle)
    assert report["acquisition_seed_count"] == 1
    assert report["raw_to_aggregate_match"] is True

    acquisition = bundle / "acquisition/seed7300/eig_seed7300.json"
    payload = json.loads(acquisition.read_text(encoding="utf-8"))
    payload["design"]["policies"]["eig_raw"]["n_measurements_to_gate"] = 4
    module._write_json(acquisition, payload)
    with pytest.raises(ValueError, match="checksum mismatch"):
        module.verify_bundle(bundle)


def test_verifier_remains_compatible_with_published_v1_bundle_schema(tmp_path: Path):
    module = load_module()
    bundle = tmp_path / "audit-v1"
    bundle.mkdir()
    _write_minimal_bundle(module, bundle)
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    manifest["schema_version"] = module.LEGACY_BUNDLE_SCHEMA
    module._write_json(bundle / "manifest.json", manifest)
    report = module.verify_bundle(bundle)
    assert report["raw_to_aggregate_match"] is True
    assert report["benchmark_version"] is None


def test_public_projection_rejects_unrecognized_absolute_paths():
    module = load_module()
    with pytest.raises(ValueError, match="unrecognized absolute path"):
        module._sanitize({"path": "/" + "home/account/private.json"})


def test_public_projection_rejects_relative_path_traversal():
    module = load_module()
    with pytest.raises(ValueError, match="traversal"):
        module._sanitize({"path": "../../private.json"})


def test_current_estimator_stage_paths_project_to_stable_public_names(tmp_path: Path):
    module = load_module()
    release = tmp_path / "release"
    current = release / "metrics/eig_validation_states"
    current.mkdir(parents=True)
    resolved = module._resolve_projection_source(release, module.PROJECTIONS[1].sources)
    assert resolved == current
    assert module._rewrite_path(
        "/private/run/results/eig_validation_states/s7100_n2/state.json"
    ) == "estimator_validation/states/s7100_n2/state.json"

    legacy = release / "metrics" / ("p" + "2_states")
    legacy.mkdir(parents=True)
    with pytest.raises(ValueError, match="ambiguous"):
        module._resolve_projection_source(release, module.PROJECTIONS[1].sources)


def _v4_policy(module, name: str, count: int, cost: float) -> dict:
    point_rows = []
    for channel_index, (channel, n_points) in enumerate(module.V4_HOLDOUT_COUNTS.items()):
        for point_index in range(n_points):
            relative_error = 0.01 * (channel_index + 1) + 0.001 * point_index
            frequency = 1000.0 + point_index
            flux = 0.1
            temperature = 25.0
            point_rows.append({
                "design_key": f"{channel}-{point_index}",
                "design_identity": "|".join((
                    channel, frequency.hex(), flux.hex(), temperature.hex(),
                )),
                "channel": channel,
                "frequency_hz": frequency,
                "b_pk_t": flux,
                "temperature_c": temperature,
                "truth": 100.0,
                "posterior_median": 100.0 * (1.0 + relative_error),
                "posterior_p05": 90.0,
                "posterior_p95": 110.0,
                "covered_by_latent_ci90": True,
                "relative_error": relative_error,
            })
    provisional = {"holdout_point_records": point_rows}
    summary = {}
    for channel, n_points in module.V4_HOLDOUT_COUNTS.items():
        errors = [
            row["relative_error"] for row in point_rows if row["channel"] == channel
        ]
        import numpy as np
        values = np.asarray(errors)
        summary[channel] = {
            "n_points": n_points,
            "relative_rmse_pct": float(np.sqrt(np.mean(values ** 2)) * 100.0),
            "median_absolute_relative_error_pct": float(np.median(np.abs(values)) * 100.0),
            "latent_ci90_coverage_fraction": 1.0,
        }
    validation = {
        "used_for_acquisition_or_stopping": False,
        "parameter_truth_in_ci90_count": 5,
        "holdout_latent_mean": summary,
        "holdout_point_records": provisional["holdout_point_records"],
    }
    return {
        "policy": name,
        "objective": module.V4_POLICY_OBJECTIVES[name],
        "reached": True,
        "n_measurements_to_gate": count,
        "modeled_cost_to_gate": cost,
        "validation_endpoints": validation,
    }


def _v4_acquisition(module, seed: int, final_sha256: str) -> dict:
    offsets = {
        "eig_raw": (5, 170.0),
        "eig_per_cost": (6, 150.0),
        "fixed_channel_balanced": (10, 300.0),
        "random_channel_balanced": (9, 280.0),
        "predictive_variance_raw": (7, 220.0),
        "predictive_variance_per_cost": (8, 190.0),
        "laplace_d_opt_raw": (6, 200.0),
        "laplace_d_opt_per_cost": (7, 180.0),
    }
    jitter = seed % 3
    policies = {
        name: _v4_policy(module, name, count + jitter, cost + jitter)
        for name, (count, cost) in offsets.items()
    }
    fixed = policies["fixed_channel_balanced"]
    paired = {}
    for name, policy in policies.items():
        if name == "fixed_channel_balanced":
            continue
        paired[f"{name}_vs_fixed"] = {
            "both_reached_gate": True,
            "measurement_count_difference": (
                fixed["n_measurements_to_gate"] - policy["n_measurements_to_gate"]
            ),
            "measurement_count_reduction_pct": (
                (fixed["n_measurements_to_gate"] - policy["n_measurements_to_gate"])
                / fixed["n_measurements_to_gate"] * 100.0
            ),
            "modeled_cost_difference": (
                fixed["modeled_cost_to_gate"] - policy["modeled_cost_to_gate"]
            ),
            "modeled_cost_reduction_pct": (
                (fixed["modeled_cost_to_gate"] - policy["modeled_cost_to_gate"])
                / fixed["modeled_cost_to_gate"] * 100.0
            ),
        }
    digest = lambda label: hashlib.sha256(f"{label}:{seed}".encode()).hexdigest()
    holdout_grid = sorted(
        row["design_identity"]
        for row in next(iter(policies.values()))["validation_endpoints"]
        ["holdout_point_records"]
    )
    holdout_hash = hashlib.sha256(json.dumps(
        holdout_grid, sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()
    return {
        "provenance": {"seed": seed},
        "data": {
            "common_random_outcomes": True,
            "holdout_count": 23,
            "holdout_manifest_sha256": holdout_hash,
            "truth_sha256": digest("truth"),
            "outcome_manifest_sha256": digest("outcome"),
        },
        "design": {
            "benchmark_version": 4,
            "estimator_decision_sha256": final_sha256,
            "primary_endpoints": module.V4_PRIMARY_ENDPOINTS,
            "comparator_registry": [
                {"policy": name, "method": module.V4_POLICY_METHODS[name],
                 "objective": module.V4_POLICY_OBJECTIVES[name],
                 "primary_endpoint": module.V4_PRIMARY_ENDPOINTS[name]}
                for name in module.V4_POLICY_OBJECTIVES
            ],
            "direct_contrasts": [
                {"name": name, "policy": policy, "comparator": comparator,
                 "endpoint": endpoint}
                for name, policy, comparator, endpoint
                in module.V4_PRIMARY_CONTRAST_SPECS
            ],
            "policies": policies,
            "paired_endpoints": paired,
        },
        "validity": {
            f"{name}_convergence_valid": True for name in policies
        },
    }


def test_v4_verifier_reconstructs_all_comparator_and_secondary_aggregates(
    tmp_path: Path,
):
    module = load_module()
    bundle = tmp_path / "audit-v4"
    bundle.mkdir()
    static_path = bundle / "estimator_validation/decisions/static_decision.json"
    module._write_json(static_path, {"inputs": [], "valid": True})
    final_path = bundle / "estimator_validation/decisions/final_decision.json"
    module._write_json(final_path, {
        "selection_sha256": module.sha256_file(static_path),
        "selection_path": "estimator_validation/decisions/static_decision.json",
        "objectives": {}, "valid": True,
    })
    final_sha256 = module.sha256_file(final_path)
    records = []
    artifacts = {
        "estimator_validation/decisions/static_decision.json": "estimator_static_decision",
        "estimator_validation/decisions/final_decision.json": "estimator_final_decision",
    }
    for seed in module.V4_ACQUISITION_SEEDS:
        record = _v4_acquisition(module, seed, final_sha256)
        relative = f"acquisition/seed{seed}/eig_seed{seed}.json"
        module._write_json(bundle / relative, record)
        artifacts[relative] = "acquisition_trajectory"
        records.append(record)
    summary = module._headline_from_trajectories(records)
    summary.update(module._v4_aggregates(records))
    module._write_json(bundle / "aggregate/paper_summary.json", {"eig": summary})
    artifacts["aggregate/paper_summary.json"] = "published_aggregate"

    entries = []
    for relative, record_class in artifacts.items():
        path = bundle / relative
        entries.append({
            "path": relative, "record_class": record_class,
            "sha256": module.sha256_file(path), "bytes": path.stat().st_size,
            "source_sha256": "0" * 64,
        })
    checksum_path = bundle / "checksums.sha256"
    checksum_path.write_text(
        "\n".join(f"{item['sha256']}  {item['path']}" for item in entries) + "\n",
        encoding="utf-8",
    )
    checksum_entry = {
        "path": "checksums.sha256", "record_class": "checksum_index",
        "sha256": module.sha256_file(checksum_path), "bytes": checksum_path.stat().st_size,
    }
    counts = {}
    for entry in entries:
        counts[entry["record_class"]] = counts.get(entry["record_class"], 0) + 1
    module._write_json(bundle / "manifest.json", {
        "schema_version": module.BUNDLE_SCHEMA,
        "release_id": "20260812T035654Z_a0703698ace9",
        "scope": {"contains_posterior_samples": False},
        "record_class_counts": counts,
        "files": [*entries, checksum_entry],
    })
    report = module.verify_bundle(bundle)
    assert report["benchmark_version"] == 4
    assert report["acquisition_seed_count"] == 30
    assert report["comparator_aggregate_match"] is True
    assert report["secondary_validation_match"] is True

    reconstructed = module._v4_aggregates(records)
    reconstructed["secondary_validation"]["eig_raw"]["holdout_latent_mean"]["pcv"][
        "mean_latent_ci90_coverage_fraction"
    ] = 0.0
    with pytest.raises(ValueError, match="numeric mismatch"):
        module._assert_equivalent(
            reconstructed,
            module._v4_aggregates(records),
            "eig.v4",
        )
