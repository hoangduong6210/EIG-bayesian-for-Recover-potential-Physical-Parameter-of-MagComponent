#!/usr/bin/env python3
"""Export a disclosure-safe, source-bound result projection for the wiki."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from statistics import mean


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def artifact_count(artifacts: list[dict], prefix: str) -> int:
    return sum(entry["path"].startswith(prefix) for entry in artifacts)


def selected_sequence(policy: dict) -> tuple[str, ...]:
    return tuple(
        state["acquisition"]["selected_key"]
        for state in policy["trajectory"]
        if state.get("acquisition", {}).get("selected_key")
    )


def acquisition_analysis(records: list[dict]) -> dict:
    rows = []
    for record in records:
        policies = record["design"]["policies"]
        sequences = {name: selected_sequence(value) for name, value in policies.items()}
        rows.append((record["provenance"]["seed"], policies, sequences))

    raw_policies = ("eig_raw", "predictive_variance_raw", "laplace_d_opt_raw")
    all_three_same_set = sum(
        len({frozenset(sequences[name]) for name in raw_policies}) == 1
        for _, _, sequences in rows
    )
    pairwise = {}
    for left, right in (
        ("eig_raw", "predictive_variance_raw"),
        ("eig_raw", "laplace_d_opt_raw"),
        ("eig_per_cost", "predictive_variance_per_cost"),
        ("eig_per_cost", "laplace_d_opt_per_cost"),
    ):
        pairwise[f"{left}_vs_{right}"] = {
            "exact_sequence_count": sum(
                sequences[left] == sequences[right] for _, _, sequences in rows
            ),
            "same_selected_set_count": sum(
                set(sequences[left]) == set(sequences[right])
                for _, _, sequences in rows
            ),
        }

    blockers_at_four = {}
    for name in raw_policies:
        counter: Counter[str] = Counter()
        for _, policies, _ in rows:
            state = next(
                item for item in policies[name]["trajectory"] if item["n_measurements"] == 4
            )
            pcv_fails = state["pcv_latent_mean_ci90_half_width_pct"] > 8.0
            lm_fails = state["lm_latent_mean_ci90_half_width_pct"] > 5.0
            label = (
                "both"
                if pcv_fails and lm_fails
                else "pcv"
                if pcv_fails
                else "lm"
                if lm_fails
                else "neither"
            )
            counter[label] += 1
        blockers_at_four[name] = dict(sorted(counter.items()))

    third_selection = {}
    for name in ("eig_per_cost", "predictive_variance_per_cost"):
        third_selection[name] = dict(
            sorted(Counter(sequences[name][2] for _, _, sequences in rows).items())
        )

    eig_cost_blocker_at_five: Counter[str] = Counter()
    cost_differences = []
    for _, policies, _ in rows:
        state = next(
            item
            for item in policies["eig_per_cost"]["trajectory"]
            if item["n_measurements"] == 5
        )
        pcv_fails = state["pcv_latent_mean_ci90_half_width_pct"] > 8.0
        lm_fails = state["lm_latent_mean_ci90_half_width_pct"] > 5.0
        label = (
            "both"
            if pcv_fails and lm_fails
            else "pcv"
            if pcv_fails
            else "lm"
            if lm_fails
            else "neither"
        )
        eig_cost_blocker_at_five[label] += 1
        cost_differences.append(
            policies["eig_per_cost"]["modeled_cost_to_gate"]
            - policies["predictive_variance_per_cost"]["modeled_cost_to_gate"]
        )

    sequence_frequencies = {}
    for name in (
        "eig_raw",
        "predictive_variance_raw",
        "laplace_d_opt_raw",
        "eig_per_cost",
        "predictive_variance_per_cost",
        "laplace_d_opt_per_cost",
    ):
        counts = Counter(" -> ".join(sequences[name]) for _, _, sequences in rows)
        sequence_frequencies[name] = [
            {"sequence": sequence, "seed_count": count}
            for sequence, count in counts.most_common()
        ]

    gate_trajectories = {}
    for name, measurement_counts in {
        "eig_raw": (4, 5),
        "predictive_variance_raw": (4, 5),
        "laplace_d_opt_raw": (4, 5),
        "eig_per_cost": (4, 5, 6),
        "predictive_variance_per_cost": (4, 5),
        "laplace_d_opt_per_cost": (4, 5, 6),
    }.items():
        gate_trajectories[name] = {}
        for n_measurements in measurement_counts:
            states = [
                next(
                    state
                    for state in policies[name]["trajectory"]
                    if state["n_measurements"] == n_measurements
                )
                for _, policies, _ in rows
            ]
            pcv_pass = [
                state["pcv_latent_mean_ci90_half_width_pct"] <= 8.0
                for state in states
            ]
            lm_pass = [
                state["lm_latent_mean_ci90_half_width_pct"] <= 5.0
                for state in states
            ]
            gate_trajectories[name][str(n_measurements)] = {
                "pcv_pass_count": sum(pcv_pass),
                "lm_pass_count": sum(lm_pass),
                "both_pass_count": sum(
                    pcv and lm for pcv, lm in zip(pcv_pass, lm_pass, strict=True)
                ),
                "mean_pcv_ci90_half_width_pct": mean(
                    state["pcv_latent_mean_ci90_half_width_pct"] for state in states
                ),
                "mean_lm_ci90_half_width_pct": mean(
                    state["lm_latent_mean_ci90_half_width_pct"] for state in states
                ),
            }

    shared_state_scores = []
    candidate_cost = {"pcv": 60.0, "lm": 15.0, "mu_real": 20.0, "mu_imag": 20.0}
    pcv_key = "pcv|500000|0.2|25"
    lm_key = "lm|10000|0|25"
    for seed, policies, sequences in rows:
        if sequences["eig_per_cost"][:2] != sequences[
            "predictive_variance_per_cost"
        ][:2]:
            continue
        eig_state = next(
            state
            for state in policies["eig_per_cost"]["trajectory"]
            if state["n_measurements"] == 4
        )
        pv_state = next(
            state
            for state in policies["predictive_variance_per_cost"]["trajectory"]
            if state["n_measurements"] == 4
        )
        eig_scores = {
            item["design_key"]: item["eig_mean_nats"]
            / candidate_cost[item["channel"]]
            for item in eig_state["acquisition"]["candidate_scores"]
        }
        pv_scores = {
            item["design_key"]: item["utility"]
            for item in pv_state["acquisition"]["candidate_scores"]
        }
        shared_state_scores.append(
            {
                "seed": seed,
                "pcv_width": eig_state["pcv_latent_mean_ci90_half_width_pct"],
                "lm_width": eig_state["lm_latent_mean_ci90_half_width_pct"],
                "eig_pcv_utility": eig_scores[pcv_key],
                "eig_lm_utility": eig_scores[lm_key],
                "eig_lm_rank": 1
                + sum(value > eig_scores[lm_key] for value in eig_scores.values()),
                "pv_pcv_utility": pv_scores[pcv_key],
                "pv_lm_utility": pv_scores[lm_key],
                "pv_pcv_rank": 1
                + sum(value > pv_scores[pcv_key] for value in pv_scores.values()),
                "pv_lm_rank": 1
                + sum(value > pv_scores[lm_key] for value in pv_scores.values()),
            }
        )

    def summarize(values: list[float]) -> dict:
        return {"mean": mean(values), "minimum": min(values), "maximum": max(values)}

    shared_score_summary = {
        "state_count": len(shared_state_scores),
        "pcv_ci90_half_width_pct": summarize(
            [row["pcv_width"] for row in shared_state_scores]
        ),
        "lm_ci90_half_width_pct": summarize(
            [row["lm_width"] for row in shared_state_scores]
        ),
        "eig_per_cost": {
            "pcv_utility": summarize(
                [row["eig_pcv_utility"] for row in shared_state_scores]
            ),
            "lm_10khz_utility": summarize(
                [row["eig_lm_utility"] for row in shared_state_scores]
            ),
            "lm_10khz_rank_one_count": sum(
                row["eig_lm_rank"] == 1 for row in shared_state_scores
            ),
        },
        "predictive_variance_per_cost": {
            "pcv_utility": summarize(
                [row["pv_pcv_utility"] for row in shared_state_scores]
            ),
            "lm_10khz_utility": summarize(
                [row["pv_lm_utility"] for row in shared_state_scores]
            ),
            "pcv_rank_one_count": sum(
                row["pv_pcv_rank"] == 1 for row in shared_state_scores
            ),
            "lm_10khz_rank_frequency": dict(
                sorted(
                    Counter(str(row["pv_lm_rank"]) for row in shared_state_scores).items()
                )
            ),
        },
    }

    return {
        "paired_seed_count": len(rows),
        "raw_all_three_same_selected_set_count": all_three_same_set,
        "pairwise_sequence_overlap": pairwise,
        "raw_gate_blocker_after_four_measurements": blockers_at_four,
        "per_cost_third_selected_design": third_selection,
        "eig_per_cost_gate_blocker_after_five_measurements": dict(
            sorted(eig_cost_blocker_at_five.items())
        ),
        "eig_minus_predictive_variance_cost_difference_frequency": dict(
            sorted(Counter(str(value) for value in cost_differences).items())
        ),
        "gate_trajectories": gate_trajectories,
        "shared_n4_eig_vs_predictive_variance_per_cost": shared_score_summary,
        "sequence_frequencies": sequence_frequencies,
    }


def policy_endpoint(summary: dict, policy: str) -> dict:
    eig = summary["eig"]
    if policy == "eig_raw":
        counts = eig["raw_counts"]
        costs = None
        failures = eig["raw_eig_failure_count"]
    elif policy == "eig_per_cost":
        counts = eig["per_cost_counts"]
        costs = eig["per_cost_modeled_costs"]
        failures = eig["per_cost_eig_failure_count"]
    elif policy == "fixed_channel_balanced":
        counts = eig["fixed_counts"]
        costs = eig["fixed_modeled_costs"]
        failures = eig["fixed_failure_count"]
    else:
        record = eig["strong_comparators"][policy]
        counts = record["counts"]
        costs = record["modeled_costs"]
        failures = record["gate_failure_count"]
    result = {
        "measurement_count": {
            "mean": sum(counts) / len(counts),
            "minimum": min(counts),
            "maximum": max(counts),
        },
        "gate_failure_count": failures,
    }
    if costs is not None:
        result["modeled_cost"] = {
            "mean": sum(costs) / len(costs),
            "minimum": min(costs),
            "maximum": max(costs),
        }
    return result


def compact_estimator_validation(decision: dict) -> dict:
    """Retain scientific decisions without copying local provenance paths."""

    return {
        "selected_setting": decision["selected_setting"],
        "selection_mode": decision["selection_mode"],
        "reference_setting": decision["reference_setting"],
        "raw_endpoint": decision["objectives"]["raw"]["endpoint"],
        "raw_all_seeds_stable": decision["objectives"]["raw"][
            "all_seeds_stable"
        ],
        "per_cost_endpoint": decision["objectives"]["per_cost"]["endpoint"],
        "per_cost_all_seeds_stable": decision["objectives"]["per_cost"][
            "all_seeds_stable"
        ],
        "raw_claim_gate_passed": decision["raw_claim_gate_passed"],
        "per_cost_claim_gate_passed": decision["per_cost_claim_gate_passed"],
        "reference_audit_passed": decision["reference_audit_passed"],
        "reference_downstream_passed": decision["reference_downstream_passed"],
        "downstream_candidate_passed": decision["downstream_candidate_passed"],
        "valid": decision["valid"],
    }


def compact_secondary_validation(secondary: dict) -> dict:
    """Project aggregate holdout metrics; omit per-seed arrays."""

    projected = {}
    for policy, record in secondary.items():
        projected[policy] = {
            "mean_parameter_truth_in_ci90_count": record[
                "mean_parameter_truth_in_ci90_count"
            ],
            "holdout_latent_mean": {
                channel: {
                    "mean_latent_ci90_coverage_fraction": metrics[
                        "mean_latent_ci90_coverage_fraction"
                    ],
                    "relative_rmse_pct_summary": metrics[
                        "relative_rmse_pct_summary"
                    ],
                }
                for channel, metrics in record["holdout_latent_mean"].items()
            },
        }
    return projected


def export(release_dir: Path) -> dict:
    release_dir = release_dir.resolve()
    release_id = release_dir.name
    manifest_path = release_dir / "manifest.json"
    result_manifest_path = release_dir / "tables" / "result_manifest.json"
    summary_path = release_dir / "tables" / "paper_summary.json"
    manifest = load_json(manifest_path)
    result_manifest = load_json(result_manifest_path)
    summary = load_json(summary_path)
    if summary["release_id"] != release_id:
        raise ValueError("summary/release ID mismatch")

    artifacts = result_manifest["artifacts"]
    acquisition_entries = [
        entry
        for entry in artifacts
        if entry["record_class"] == "canonical_synthetic"
        and entry["path"].startswith("results/eig/")
    ]
    acquisition_records = [
        load_json(release_dir / entry["path"].replace("results/", "metrics/", 1))
        for entry in acquisition_entries
    ]
    acquisition_input_digest = hashlib.sha256(
        json.dumps(
            [{"path": entry["path"], "sha256": entry["sha256"]} for entry in acquisition_entries],
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    jobs = [
        {
            "id": "matched_model_recovery",
            "artifacts": artifact_count(artifacts, "results/posterior/"),
            "status": "claim_input",
            "result": "five prior-predictive recovery records; 28 of 30 interval inclusions",
        },
        {
            "id": "prior_offset_sensitivity",
            "artifacts": artifact_count(artifacts, "results/robustness/prior_offset"),
            "status": "diagnostic_only",
            "result": "records retained; no general robustness claim",
        },
        {
            "id": "synthetic_lot_sensitivity",
            "artifacts": artifact_count(artifacts, "results/robustness/lot_"),
            "status": "diagnostic_only",
            "result": "synthetic target-valid records; no physical lot claim",
        },
        {
            "id": "local_identifiability",
            "artifacts": artifact_count(artifacts, "results/identifiability/"),
            "status": "claim_input",
            "result": "rank-six local Fisher spectrum",
        },
        {
            "id": "estimator_posterior_states",
            "artifacts": artifact_count(artifacts, "results/eig_validation_states/")
            - result_manifest["record_class_counts"]["supporting_artifact"],
            "status": "claim_input",
            "result": "twelve declared posterior states",
        },
        {
            "id": "estimator_score_campaign",
            "artifacts": result_manifest["record_class_counts"]["eig_validation_score"],
            "status": "claim_input",
            "result": "grid, reference, and doubled-budget score records",
        },
        {
            "id": "estimator_downstream_validation",
            "artifacts": result_manifest["record_class_counts"]["eig_validation_downstream"],
            "status": "claim_input",
            "result": "both endpoints reproduced the reference",
        },
        {
            "id": "paired_acquisition_benchmark",
            "artifacts": len(acquisition_entries),
            "status": "claim_input",
            "result": "eight policies, four direct contrasts, all gates reached",
        },
        {
            "id": "measured_core_loss",
            "artifacts": artifact_count(artifacts, "results/measured_pcv/"),
            "status": "claim_input",
            "result": "four accepted in-sample adequacy records",
        },
        {
            "id": "measured_permeability_accepted",
            "artifacts": sum(
                entry["record_class"] == "canonical_measured"
                and entry["path"].startswith("results/measured_mu/")
                for entry in artifacts
            ),
            "status": "claim_input",
            "result": "two accepted in-sample adequacy records",
        },
        {
            "id": "measured_permeability_excluded",
            "artifacts": result_manifest["record_class_counts"][
                "canonical_measured_excluded"
            ],
            "status": "excluded_diagnostic",
            "result": "two convergence-invalid or boundary-flagged records",
        },
        {
            "id": "measured_acquisition_suggestions",
            "artifacts": artifact_count(artifacts, "results/measured_eig/"),
            "status": "diagnostic_only",
            "result": "model-conditional suggestions; stable ranking not claimed",
        },
        {
            "id": "estimator_sample_matrices",
            "artifacts": result_manifest["record_class_counts"]["supporting_artifact"],
            "status": "supporting",
            "result": "flattened posterior sample matrices",
        },
    ]
    if sum(job["artifacts"] for job in jobs) != result_manifest["expected_result_artifact_count"]:
        raise ValueError("scientific job registry does not cover every result artifact")

    policies = [
        "eig_raw",
        "predictive_variance_raw",
        "laplace_d_opt_raw",
        "eig_per_cost",
        "predictive_variance_per_cost",
        "laplace_d_opt_per_cost",
        "fixed_channel_balanced",
        "random_channel_balanced",
    ]
    return {
        "schema_version": "magnetic-wiki-evidence/1.0",
        "release": {
            "id": release_id,
            "manifest_sha256": file_sha256(manifest_path),
            "git_revision": manifest["git_revision"],
        },
        "sources": {
            "release_manifest": {
                "path": "manifest.json",
                "sha256": file_sha256(manifest_path),
            },
            "result_manifest": {
                "path": "tables/result_manifest.json",
                "sha256": file_sha256(result_manifest_path),
            },
            "paper_summary": {
                "path": "tables/paper_summary.json",
                "sha256": file_sha256(summary_path),
            },
            "acquisition_record_set": {
                "path_pattern": "metrics/eig/seed*/eig_seed*.json",
                "record_count": len(acquisition_entries),
                "path_sha256_digest": acquisition_input_digest,
            },
        },
        "campaign": {
            "expected_task_count": result_manifest["expected_task_count"],
            "result_artifact_count": result_manifest["expected_result_artifact_count"],
            "record_class_counts": result_manifest["record_class_counts"],
            "tasks_without_result_artifacts": result_manifest[
                "tasks_without_result_artifacts"
            ],
            "acquisition_audit": result_manifest["acquisition_benchmark_audit"],
        },
        "scientific_jobs": jobs,
        "results": {
            "fisher": summary["fisher"],
            "recovery": summary["recovery"],
            "recovery_interval_inclusion_total": summary[
                "recovery_interval_inclusion_total"
            ],
            "estimator_validation": compact_estimator_validation(
                summary["eig"]["estimator_validation_decision"]
            ),
            "policy_endpoints": {
                name: policy_endpoint(summary, name) for name in policies
            },
            "primary_contrasts": summary["eig"]["primary_contrasts"],
            "secondary_validation": compact_secondary_validation(
                summary["eig"]["secondary_validation"]
            ),
            "measured_core_loss": summary["measured_pcv"],
            "measured_permeability": summary["measured_permeability"],
            "excluded_measured_permeability": summary[
                "excluded_measured_permeability"
            ],
            "trajectory_analysis": acquisition_analysis(acquisition_records),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = export(args.release_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
