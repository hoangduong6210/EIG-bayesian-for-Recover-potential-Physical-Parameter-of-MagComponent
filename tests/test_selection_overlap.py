from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.analyze_selection_overlap import (
    ANALYSIS_SCHEMA,
    analyze_records,
    spearman_correlation,
    write_analysis,
)


IDENTITIES = {
    "a": "lm|0x1.0p+10|0x0.0p+0|0x1.9p+4",
    "b": "pcv|0x1.0p+11|0x1.0p-3|0x1.9p+4",
    "c": "mu_real|0x1.0p+12|0x0.0p+0|0x1.9p+4",
}


def _scores(order: list[str], utilities: list[float], field: str) -> list[dict]:
    return [
        {
            "design_identity": IDENTITIES[key],
            "design_key": key,
            field: utility,
        }
        for key, utility in zip(order, utilities)
    ]


def _row(
    n: int,
    state: str,
    pcv: float,
    lm: float,
    selected: str | None,
    scores: list[dict] | None,
    objective: str,
) -> dict:
    return {
        "n_measurements": n,
        "pcv_latent_mean_ci90_half_width_pct": pcv,
        "lm_latent_mean_ci90_half_width_pct": lm,
        "reached": pcv <= 8.0 and lm <= 5.0,
        "decision_state": {"state_identity_sha256": state},
        "acquisition": None if selected is None else {
            "objective": objective,
            "selected_key": selected,
            "selected_identity": IDENTITIES[selected],
            "candidate_scores": scores,
        },
    }


def _record(seed: int) -> dict:
    eig = {
        "trajectory": [
            _row(2, f"{seed}-initial", 16.0, 10.0, "a",
                 _scores(["a", "b", "c"], [3.0, 2.0, 1.0], "utility_mean"), "raw"),
            _row(3, f"{seed}-after-a", 8.0, 7.5, "b",
                 _scores(["b", "c"], [2.0, 1.0], "utility_mean"), "raw"),
            _row(4, f"{seed}-eig-final", 6.0, 4.0, None, None, "raw"),
        ],
    }
    predictive_variance = {
        "trajectory": [
            _row(2, f"{seed}-initial", 16.0, 10.0, "a",
                 _scores(["a", "b", "c"], [30.0, 20.0, 10.0], "utility"), "raw"),
            _row(3, f"{seed}-after-a", 8.0, 7.5, "c",
                 _scores(["b", "c"], [1.0, 2.0], "utility"), "raw"),
            _row(4, f"{seed}-pv-final", 9.0, 4.0, None, None, "raw"),
        ],
    }
    return {
        "provenance": {"seed": seed},
        "design": {
            "benchmark_version": 4,
            "gate_contract": {
                "pcv_ci_half_width_pct": 8.0,
                "lm_ci_half_width_pct": 5.0,
            },
            "comparator_registry": [
                {"policy": "eig_raw"},
                {"policy": "predictive_variance_raw"},
            ],
            "policies": {
                "eig_raw": eig,
                "predictive_variance_raw": predictive_variance,
            },
        },
    }


def test_spearman_correlation_supports_ties_and_constants():
    assert spearman_correlation([1, 2, 3], [10, 20, 30]) == pytest.approx(1.0)
    assert spearman_correlation([1, 2, 3], [30, 20, 10]) == pytest.approx(-1.0)
    assert spearman_correlation([1, 1, 2], [10, 10, 20]) == pytest.approx(1.0)
    assert spearman_correlation([1, 1, 1], [10, 20, 30]) is None


def test_analysis_separates_selection_overlap_from_score_comparability():
    result = analyze_records([_record(101), _record(102)])

    assert result["schema"] == ANALYSIS_SCHEMA
    assert result["seed_count"] == 2
    steps = result["pairwise_same_candidate_by_step"]
    assert [row["same_candidate_rate"] for row in steps] == [1.0, 0.0]
    assert all(row["same_state_rate"] == 1.0 for row in steps)
    assert result["pairwise_same_candidate_overall"][0]["same_candidate_rate"] == 0.5
    frequencies = result["selection_frequency_by_step"]
    eig_first = next(
        row for row in frequencies
        if row["policy"] == "eig_raw" and row["decision_step"] == 1
    )
    assert eig_first["selected_key"] == "a"
    assert eig_first["selection_count"] == 2
    assert eig_first["selection_rate"] == 1.0

    paths = result["path_overlap_by_seed"]
    assert len(paths) == 2
    assert all(row["common_prefix_length"] == 1 for row in paths)
    assert all(row["positional_match_rate"] == 0.5 for row in paths)
    assert all(row["selected_set_jaccard"] == pytest.approx(1 / 3) for row in paths)
    assert all(row["lcs_rate_max_length"] == 0.5 for row in paths)

    rankings = result["ranking_correlation_comparable_states"]
    assert len(rankings) == 4
    assert sorted(row["spearman_rho"] for row in rankings) == [-1.0, -1.0, 1.0, 1.0]
    aggregate = result["ranking_correlation_aggregate"][0]
    assert aggregate["comparable_state_count"] == 4
    assert aggregate["spearman_rho"]["mean"] == pytest.approx(0.0)

    gate_rows = result["gate_distance_change_by_decision"]
    eig_first = next(
        row for row in gate_rows
        if row["seed"] == 101 and row["policy"] == "eig_raw" and row["decision_step"] == 1
    )
    assert eig_first["max_gate_ratio_before"] == 2.0
    assert eig_first["max_gate_ratio_after"] == 1.5
    assert eig_first["max_gate_ratio_improvement"] == 0.5


def test_write_analysis_emits_hashed_machine_readable_outputs(tmp_path: Path):
    release = tmp_path / "20260817T000000Z_abcdef123456"
    record_dir = release / "metrics" / "eig" / "seed101"
    record_dir.mkdir(parents=True)
    (release / "manifest.json").write_text("{}\n", encoding="utf-8")
    (record_dir / "eig_seed101.json").write_text(
        json.dumps(_record(101)), encoding="utf-8"
    )
    output = tmp_path / "analysis"

    result = write_analysis(release, output)

    assert result["source"]["release_id"] == release.name
    assert (output / "summary.json").is_file()
    assert (output / "aggregate_summary.json").is_file()
    assert (output / "selection_frequency_by_step.csv").is_file()
    assert (output / "pairwise_step_overlap.csv").is_file()
    assert (output / "path_overlap_by_seed.csv").is_file()
    assert (output / "ranking_correlation.csv").is_file()
    assert (output / "gate_distance_change.csv").is_file()
    checksums = json.loads((output / "checksums.json").read_text(encoding="utf-8"))
    assert checksums["schema"] == ANALYSIS_SCHEMA
    assert "summary.json" in checksums["files"]
    assert "aggregate_summary.json" in checksums["files"]
    with pytest.raises(FileExistsError):
        write_analysis(release, output)
