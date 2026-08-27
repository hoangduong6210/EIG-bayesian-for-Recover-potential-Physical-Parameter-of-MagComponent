#!/usr/bin/env python3
"""Explain acquisition-policy overlap from frozen benchmark-v4 records.

The analysis is descriptive.  It separates three questions that have distinct
comparability requirements:

* selected-design overlap compares policies at the same acquisition index;
* score-ranking correlation additionally requires the exact same posterior
  state and candidate universe;
* gate-distance change compares the recorded state immediately before and
  after one selected acquisition on that policy's own trajectory.

Outputs are deterministic JSON/CSV files suitable for evidence review.  No
claim of causal superiority is inferred from overlap or correlation alone.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any, Iterable, Sequence


ANALYSIS_SCHEMA = "magcore-selection-overlap/1.0"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _write_csv(path: Path, rows: Sequence[dict[str, Any]], fields: Sequence[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def _finite_number(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
    )


def _mean(values: Sequence[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _median(values: Sequence[float]) -> float | None:
    return statistics.median(values) if values else None


def _summary(values: Sequence[float]) -> dict[str, Any]:
    return {
        "count": len(values),
        "mean": _mean(values),
        "median": _median(values),
        "minimum": min(values) if values else None,
        "maximum": max(values) if values else None,
    }


def _average_ranks(values: Sequence[float]) -> list[float]:
    """Return one-based average ranks with ascending values ranked first."""

    order = sorted(range(len(values)), key=lambda index: (values[index], index))
    ranks = [0.0] * len(values)
    position = 0
    while position < len(order):
        end = position + 1
        value = values[order[position]]
        while end < len(order) and values[order[end]] == value:
            end += 1
        average = ((position + 1) + end) / 2.0
        for sorted_index in range(position, end):
            ranks[order[sorted_index]] = average
        position = end
    return ranks


def spearman_correlation(left: Sequence[float], right: Sequence[float]) -> float | None:
    """Compute Spearman's rho with average ranks; return None for constants."""

    if len(left) != len(right) or len(left) < 2:
        return None
    if not all(_finite_number(value) for value in (*left, *right)):
        raise ValueError("ranking scores must be finite")
    left_ranks, right_ranks = _average_ranks(left), _average_ranks(right)
    left_mean, right_mean = statistics.fmean(left_ranks), statistics.fmean(right_ranks)
    numerator = sum(
        (left_value - left_mean) * (right_value - right_mean)
        for left_value, right_value in zip(left_ranks, right_ranks)
    )
    left_ss = sum((value - left_mean) ** 2 for value in left_ranks)
    right_ss = sum((value - right_mean) ** 2 for value in right_ranks)
    if left_ss == 0.0 or right_ss == 0.0:
        return None
    return numerator / math.sqrt(left_ss * right_ss)


def _longest_common_subsequence_length(left: Sequence[str], right: Sequence[str]) -> int:
    previous = [0] * (len(right) + 1)
    for left_value in left:
        current = [0]
        for index, right_value in enumerate(right, start=1):
            current.append(
                previous[index - 1] + 1
                if left_value == right_value
                else max(previous[index], current[-1])
            )
        previous = current
    return previous[-1]


def _path_metrics(left: Sequence[str], right: Sequence[str]) -> dict[str, Any]:
    common_prefix = 0
    for left_value, right_value in zip(left, right):
        if left_value != right_value:
            break
        common_prefix += 1
    minimum_length = min(len(left), len(right))
    maximum_length = max(len(left), len(right))
    positional_matches = sum(a == b for a, b in zip(left, right))
    union = set(left) | set(right)
    intersection = set(left) & set(right)
    lcs = _longest_common_subsequence_length(left, right)
    return {
        "left_path_length": len(left),
        "right_path_length": len(right),
        "exact_path_match": left == right,
        "common_prefix_length": common_prefix,
        "positional_match_count": positional_matches,
        "positional_match_rate": (
            positional_matches / minimum_length if minimum_length else None
        ),
        "selected_set_jaccard": len(intersection) / len(union) if union else 1.0,
        "lcs_length": lcs,
        "lcs_rate_max_length": lcs / maximum_length if maximum_length else 1.0,
    }


def _score_value(candidate: dict[str, Any]) -> tuple[str, float]:
    if "utility_mean" in candidate:
        field = "utility_mean"
    elif "utility" in candidate:
        field = "utility"
    else:
        raise ValueError("candidate ranking lacks its decision utility")
    value = candidate.get(field)
    if not _finite_number(value):
        raise ValueError("candidate ranking utility must be finite")
    return field, float(value)


@dataclass(frozen=True)
class Decision:
    seed: int
    policy: str
    objective: str
    decision_step: int
    n_measurements_before: int
    selected_key: str
    selected_identity: str
    selected_channel: str
    state_identity_sha256: str
    candidate_scores: tuple[dict[str, Any], ...]
    pcv_before: float
    lm_before: float
    pcv_after: float
    lm_after: float


def _gate_metrics(pcv: float, lm: float, pcv_gate: float, lm_gate: float) -> dict[str, float]:
    pcv_ratio, lm_ratio = pcv / pcv_gate, lm / lm_gate
    max_ratio = max(pcv_ratio, lm_ratio)
    return {
        "pcv_gate_ratio": pcv_ratio,
        "lm_gate_ratio": lm_ratio,
        "max_gate_ratio": max_ratio,
        "positive_gate_excess": max(0.0, max_ratio - 1.0),
    }


def _record_decisions(record: dict[str, Any]) -> tuple[list[str], list[Decision]]:
    seed = record.get("provenance", {}).get("seed")
    policies = record.get("design", {}).get("policies")
    gate = record.get("design", {}).get("gate_contract")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("record provenance seed is missing")
    if not isinstance(policies, dict) or not policies:
        raise ValueError("record has no acquisition policies")
    if not isinstance(gate, dict):
        raise ValueError("record gate contract is missing")
    pcv_gate, lm_gate = gate.get("pcv_ci_half_width_pct"), gate.get("lm_ci_half_width_pct")
    if not _finite_number(pcv_gate) or not _finite_number(lm_gate):
        raise ValueError("record gate thresholds must be finite")

    registry = record.get("design", {}).get("comparator_registry", [])
    policy_order = [entry.get("policy") for entry in registry if isinstance(entry, dict)]
    if set(policy_order) != set(policies) or len(policy_order) != len(policies):
        raise ValueError("comparator registry and policy records disagree")

    decisions: list[Decision] = []
    for policy_name in policy_order:
        policy = policies[policy_name]
        trajectory = policy.get("trajectory")
        if not isinstance(trajectory, list) or not trajectory:
            raise ValueError(f"policy {policy_name} has no trajectory")
        for index, row in enumerate(trajectory[:-1]):
            following = trajectory[index + 1]
            acquisition = row.get("acquisition")
            if not isinstance(acquisition, dict):
                raise ValueError(f"policy {policy_name} has a missing nonterminal acquisition")
            identity = acquisition.get("selected_identity")
            selected_key = acquisition.get("selected_key")
            if not isinstance(identity, str) or not isinstance(selected_key, str):
                raise ValueError("selected candidate identity/key is malformed")
            channel = identity.split("|", 1)[0]
            state = row.get("decision_state", {}).get("state_identity_sha256")
            scores = acquisition.get("candidate_scores", [])
            if not isinstance(state, str) or not state:
                raise ValueError("decision state identity is missing")
            if not isinstance(scores, list):
                raise ValueError("candidate_scores must be a list when present")
            widths = (
                row.get("pcv_latent_mean_ci90_half_width_pct"),
                row.get("lm_latent_mean_ci90_half_width_pct"),
                following.get("pcv_latent_mean_ci90_half_width_pct"),
                following.get("lm_latent_mean_ci90_half_width_pct"),
            )
            if not all(_finite_number(value) for value in widths):
                raise ValueError("trajectory gate widths must be finite")
            decisions.append(Decision(
                seed=seed,
                policy=policy_name,
                objective=str(acquisition.get("objective")),
                decision_step=index + 1,
                n_measurements_before=int(row["n_measurements"]),
                selected_key=selected_key,
                selected_identity=identity,
                selected_channel=channel,
                state_identity_sha256=state,
                candidate_scores=tuple(scores),
                pcv_before=float(widths[0]),
                lm_before=float(widths[1]),
                pcv_after=float(widths[2]),
                lm_after=float(widths[3]),
            ))
    return policy_order, decisions


def _load_records(release_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    paths = sorted((release_dir / "metrics" / "eig").glob("seed*/eig_seed*.json"))
    if not paths:
        raise ValueError(f"no benchmark records found under {release_dir}")
    records, sources = [], []
    for path in paths:
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("design", {}).get("benchmark_version") != 4:
            raise ValueError(f"{path} is not a benchmark-v4 record")
        records.append(record)
        sources.append({
            "path": path.relative_to(release_dir).as_posix(),
            "sha256": _sha256(path),
        })
    seeds = [record.get("provenance", {}).get("seed") for record in records]
    if len(seeds) != len(set(seeds)):
        raise ValueError("benchmark records contain duplicate seeds")
    return records, sources


def analyze_records(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Return deterministic overlap diagnostics for benchmark-v4 records."""

    if not records:
        raise ValueError("at least one benchmark record is required")
    all_decisions: list[Decision] = []
    policy_order: list[str] | None = None
    gate_contract: dict[str, Any] | None = None
    for record in records:
        order, decisions = _record_decisions(record)
        if policy_order is None:
            policy_order = order
            gate_contract = record["design"]["gate_contract"]
        elif order != policy_order or record["design"]["gate_contract"] != gate_contract:
            raise ValueError("policy registry or gate contract differs between seeds")
        all_decisions.extend(decisions)
    assert policy_order is not None and gate_contract is not None

    by_seed_policy: dict[tuple[int, str], list[Decision]] = defaultdict(list)
    by_seed_policy_step: dict[tuple[int, str, int], Decision] = {}
    seeds = sorted({decision.seed for decision in all_decisions})
    for decision in all_decisions:
        by_seed_policy[(decision.seed, decision.policy)].append(decision)
        key = (decision.seed, decision.policy, decision.decision_step)
        if key in by_seed_policy_step:
            raise ValueError("duplicate policy decision step")
        by_seed_policy_step[key] = decision
    for decisions in by_seed_policy.values():
        decisions.sort(key=lambda item: item.decision_step)

    selection_frequency_rows: list[dict[str, Any]] = []
    selection_groups: dict[tuple[str, int, str, str, str], list[Decision]] = defaultdict(list)
    selection_step_counts: dict[tuple[str, int], int] = defaultdict(int)
    for decision in all_decisions:
        selection_groups[(
            decision.policy,
            decision.decision_step,
            decision.selected_key,
            decision.selected_identity,
            decision.selected_channel,
        )].append(decision)
        selection_step_counts[(decision.policy, decision.decision_step)] += 1
    for (policy, step, key, identity, channel), decisions in sorted(
        selection_groups.items(),
        key=lambda item: (
            policy_order.index(item[0][0]), item[0][1], item[0][2]
        ),
    ):
        denominator = selection_step_counts[(policy, step)]
        selection_frequency_rows.append({
            "policy": policy,
            "decision_step": step,
            "eligible_seed_count": denominator,
            "selected_key": key,
            "selected_identity": identity,
            "selected_channel": channel,
            "selection_count": len(decisions),
            "selection_rate": len(decisions) / denominator,
        })

    pairwise_step_rows: list[dict[str, Any]] = []
    pairwise_overall_rows: list[dict[str, Any]] = []
    for left_policy, right_policy in combinations(policy_order, 2):
        step_values = sorted({
            decision.decision_step
            for decision in all_decisions
            if decision.policy in (left_policy, right_policy)
        })
        overall_pairs: list[tuple[Decision, Decision]] = []
        for step in step_values:
            paired = [
                (by_seed_policy_step[(seed, left_policy, step)],
                 by_seed_policy_step[(seed, right_policy, step)])
                for seed in seeds
                if (seed, left_policy, step) in by_seed_policy_step
                and (seed, right_policy, step) in by_seed_policy_step
            ]
            if not paired:
                continue
            overall_pairs.extend(paired)
            same_candidate = sum(left.selected_identity == right.selected_identity for left, right in paired)
            same_channel = sum(left.selected_channel == right.selected_channel for left, right in paired)
            same_state = sum(left.state_identity_sha256 == right.state_identity_sha256 for left, right in paired)
            pairwise_step_rows.append({
                "left_policy": left_policy,
                "right_policy": right_policy,
                "decision_step": step,
                "eligible_seed_count": len(paired),
                "same_candidate_count": same_candidate,
                "same_candidate_rate": same_candidate / len(paired),
                "same_channel_count": same_channel,
                "same_channel_rate": same_channel / len(paired),
                "same_state_count": same_state,
                "same_state_rate": same_state / len(paired),
            })
        same_candidate = sum(left.selected_identity == right.selected_identity for left, right in overall_pairs)
        same_channel = sum(left.selected_channel == right.selected_channel for left, right in overall_pairs)
        same_state = sum(left.state_identity_sha256 == right.state_identity_sha256 for left, right in overall_pairs)
        pairwise_overall_rows.append({
            "left_policy": left_policy,
            "right_policy": right_policy,
            "eligible_seed_step_count": len(overall_pairs),
            "same_candidate_count": same_candidate,
            "same_candidate_rate": same_candidate / len(overall_pairs) if overall_pairs else None,
            "same_channel_count": same_channel,
            "same_channel_rate": same_channel / len(overall_pairs) if overall_pairs else None,
            "same_state_count": same_state,
            "same_state_rate": same_state / len(overall_pairs) if overall_pairs else None,
        })

    path_rows: list[dict[str, Any]] = []
    for seed in seeds:
        for left_policy, right_policy in combinations(policy_order, 2):
            left_path = [item.selected_identity for item in by_seed_policy[(seed, left_policy)]]
            right_path = [item.selected_identity for item in by_seed_policy[(seed, right_policy)]]
            path_rows.append({
                "seed": seed,
                "left_policy": left_policy,
                "right_policy": right_policy,
                **_path_metrics(left_path, right_path),
            })

    path_aggregate: list[dict[str, Any]] = []
    for left_policy, right_policy in combinations(policy_order, 2):
        rows = [
            row for row in path_rows
            if row["left_policy"] == left_policy and row["right_policy"] == right_policy
        ]
        path_aggregate.append({
            "left_policy": left_policy,
            "right_policy": right_policy,
            "seed_count": len(rows),
            "exact_path_match_count": sum(bool(row["exact_path_match"]) for row in rows),
            "exact_path_match_rate": _mean([float(row["exact_path_match"]) for row in rows]),
            "common_prefix_length": _summary([float(row["common_prefix_length"]) for row in rows]),
            "positional_match_rate": _summary([
                float(row["positional_match_rate"])
                for row in rows if row["positional_match_rate"] is not None
            ]),
            "selected_set_jaccard": _summary([
                float(row["selected_set_jaccard"]) for row in rows
            ]),
            "lcs_rate_max_length": _summary([
                float(row["lcs_rate_max_length"]) for row in rows
            ]),
        })

    ranking_rows: list[dict[str, Any]] = []
    decisions_by_state: dict[tuple[int, str], list[Decision]] = defaultdict(list)
    for decision in all_decisions:
        if decision.candidate_scores:
            decisions_by_state[(decision.seed, decision.state_identity_sha256)].append(decision)
    for (seed, state_identity), decisions in sorted(decisions_by_state.items()):
        decisions.sort(key=lambda item: policy_order.index(item.policy))
        for left, right in combinations(decisions, 2):
            left_scores = {score.get("design_identity"): score for score in left.candidate_scores}
            right_scores = {score.get("design_identity"): score for score in right.candidate_scores}
            if None in left_scores or None in right_scores or set(left_scores) != set(right_scores):
                continue
            identities = sorted(left_scores)
            left_field, _ = _score_value(left_scores[identities[0]])
            right_field, _ = _score_value(right_scores[identities[0]])
            left_values = [_score_value(left_scores[identity])[1] for identity in identities]
            right_values = [_score_value(right_scores[identity])[1] for identity in identities]
            rho = spearman_correlation(left_values, right_values)
            ranking_rows.append({
                "seed": seed,
                "n_measurements_before": left.n_measurements_before,
                "state_identity_sha256": state_identity,
                "left_policy": left.policy,
                "right_policy": right.policy,
                "left_objective": left.objective,
                "right_objective": right.objective,
                "left_score_field": left_field,
                "right_score_field": right_field,
                "candidate_count": len(identities),
                "spearman_rho": rho,
                "same_selected_candidate": left.selected_identity == right.selected_identity,
            })

    ranking_aggregate: list[dict[str, Any]] = []
    for left_policy, right_policy in combinations(policy_order, 2):
        rows = [
            row for row in ranking_rows
            if row["left_policy"] == left_policy and row["right_policy"] == right_policy
        ]
        if not rows:
            continue
        correlations = [
            float(row["spearman_rho"])
            for row in rows if row["spearman_rho"] is not None
        ]
        ranking_aggregate.append({
            "left_policy": left_policy,
            "right_policy": right_policy,
            "comparable_state_count": len(rows),
            "defined_correlation_count": len(correlations),
            "same_selected_candidate_count": sum(
                bool(row["same_selected_candidate"]) for row in rows
            ),
            "same_selected_candidate_rate": _mean([
                float(row["same_selected_candidate"]) for row in rows
            ]),
            "spearman_rho": _summary(correlations),
        })

    ranking_by_measurement_count: list[dict[str, Any]] = []
    ranking_groups: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in ranking_rows:
        ranking_groups[(
            str(row["left_policy"]),
            str(row["right_policy"]),
            int(row["n_measurements_before"]),
        )].append(row)
    for (left_policy, right_policy, n_measurements), rows in sorted(
        ranking_groups.items(),
        key=lambda item: (
            policy_order.index(item[0][0]),
            policy_order.index(item[0][1]),
            item[0][2],
        ),
    ):
        correlations = [
            float(row["spearman_rho"])
            for row in rows if row["spearman_rho"] is not None
        ]
        ranking_by_measurement_count.append({
            "left_policy": left_policy,
            "right_policy": right_policy,
            "n_measurements_before": n_measurements,
            "comparable_state_count": len(rows),
            "same_selected_candidate_count": sum(
                bool(row["same_selected_candidate"]) for row in rows
            ),
            "same_selected_candidate_rate": _mean([
                float(row["same_selected_candidate"]) for row in rows
            ]),
            "spearman_rho": _summary(correlations),
        })

    pcv_gate = float(gate_contract["pcv_ci_half_width_pct"])
    lm_gate = float(gate_contract["lm_ci_half_width_pct"])
    gate_rows: list[dict[str, Any]] = []
    for decision in sorted(
        all_decisions,
        key=lambda item: (item.seed, policy_order.index(item.policy), item.decision_step),
    ):
        before = _gate_metrics(decision.pcv_before, decision.lm_before, pcv_gate, lm_gate)
        after = _gate_metrics(decision.pcv_after, decision.lm_after, pcv_gate, lm_gate)
        gate_rows.append({
            "seed": decision.seed,
            "policy": decision.policy,
            "decision_step": decision.decision_step,
            "n_measurements_before": decision.n_measurements_before,
            "selected_key": decision.selected_key,
            "selected_identity": decision.selected_identity,
            "selected_channel": decision.selected_channel,
            "pcv_width_before_pct": decision.pcv_before,
            "pcv_width_after_pct": decision.pcv_after,
            "pcv_gate_ratio_before": before["pcv_gate_ratio"],
            "pcv_gate_ratio_after": after["pcv_gate_ratio"],
            "lm_width_before_pct": decision.lm_before,
            "lm_width_after_pct": decision.lm_after,
            "lm_gate_ratio_before": before["lm_gate_ratio"],
            "lm_gate_ratio_after": after["lm_gate_ratio"],
            "max_gate_ratio_before": before["max_gate_ratio"],
            "max_gate_ratio_after": after["max_gate_ratio"],
            "max_gate_ratio_improvement": before["max_gate_ratio"] - after["max_gate_ratio"],
            "positive_gate_excess_before": before["positive_gate_excess"],
            "positive_gate_excess_after": after["positive_gate_excess"],
            "positive_gate_excess_improvement": (
                before["positive_gate_excess"] - after["positive_gate_excess"]
            ),
            "both_gate_widths_met_after": (
                after["pcv_gate_ratio"] <= 1.0 and after["lm_gate_ratio"] <= 1.0
            ),
        })

    gate_aggregate: list[dict[str, Any]] = []
    for policy in policy_order:
        for step in sorted({
            int(row["decision_step"]) for row in gate_rows if row["policy"] == policy
        }):
            rows = [
                row for row in gate_rows
                if row["policy"] == policy and row["decision_step"] == step
            ]
            improvements = [float(row["max_gate_ratio_improvement"]) for row in rows]
            gate_aggregate.append({
                "policy": policy,
                "decision_step": step,
                "eligible_seed_count": len(rows),
                "max_gate_ratio_improvement": _summary(improvements),
                "improved_count": sum(value > 0.0 for value in improvements),
                "improved_rate": sum(value > 0.0 for value in improvements) / len(rows),
                "reached_gate_after_count": sum(
                    bool(row["both_gate_widths_met_after"]) for row in rows
                ),
            })

    return {
        "schema": ANALYSIS_SCHEMA,
        "benchmark_version": 4,
        "seed_count": len(seeds),
        "seeds": seeds,
        "policy_order": policy_order,
        "gate_contract": gate_contract,
        "metric_definitions": {
            "selection_step": "one-based acquisition index after the shared initial design",
            "same_candidate": "exact equality of stable design_identity",
            "score_comparable": (
                "same seed, exact posterior-state hash, and identical remaining-candidate universe"
            ),
            "ranking_score": "the utility used by each policy to choose its candidate",
            "positive_gate_excess": (
                "max(0, max(pcv_width/pcv_gate, lm_width/lm_gate) - 1)"
            ),
            "gate_improvement": "value before acquisition minus value after acquisition",
            "path_lcs_rate": "longest-common-subsequence length divided by longer path length",
        },
        "selection_frequency_by_step": selection_frequency_rows,
        "pairwise_same_candidate_by_step": pairwise_step_rows,
        "pairwise_same_candidate_overall": pairwise_overall_rows,
        "path_overlap_by_seed": path_rows,
        "path_overlap_aggregate": path_aggregate,
        "ranking_correlation_comparable_states": ranking_rows,
        "ranking_correlation_aggregate": ranking_aggregate,
        "ranking_correlation_by_measurement_count": ranking_by_measurement_count,
        "gate_distance_change_by_decision": gate_rows,
        "gate_distance_change_aggregate": gate_aggregate,
        "interpretation_limits": [
            "Overlap and rank correlation are descriptive and do not establish policy equivalence.",
            "Same-step overlap after paths diverge compares selected designs, not common posterior states.",
            "Ranking correlation is emitted only for exact shared states and candidate universes.",
            "Later-step overlap uses only seeds where both policies still require an acquisition.",
            "Gate changes are realized one-step changes on each policy trajectory, not counterfactual effects.",
            "All findings remain conditional on the matched Steinmetz plus one-pole Cole-Cole model.",
            "This analysis hashes its 30 input records but does not verify the release-wide checksum tree.",
        ],
    }


CSV_SPECS = {
    "selection_frequency_by_step.csv": (
        "selection_frequency_by_step",
        ("policy", "decision_step", "eligible_seed_count", "selected_key",
         "selected_identity", "selected_channel", "selection_count", "selection_rate"),
    ),
    "pairwise_step_overlap.csv": (
        "pairwise_same_candidate_by_step",
        ("left_policy", "right_policy", "decision_step", "eligible_seed_count",
         "same_candidate_count", "same_candidate_rate", "same_channel_count",
         "same_channel_rate", "same_state_count", "same_state_rate"),
    ),
    "path_overlap_by_seed.csv": (
        "path_overlap_by_seed",
        ("seed", "left_policy", "right_policy", "left_path_length", "right_path_length",
         "exact_path_match", "common_prefix_length", "positional_match_count",
         "positional_match_rate", "selected_set_jaccard", "lcs_length",
         "lcs_rate_max_length"),
    ),
    "ranking_correlation.csv": (
        "ranking_correlation_comparable_states",
        ("seed", "n_measurements_before", "state_identity_sha256", "left_policy",
         "right_policy", "left_objective", "right_objective", "left_score_field",
         "right_score_field", "candidate_count", "spearman_rho",
         "same_selected_candidate"),
    ),
    "gate_distance_change.csv": (
        "gate_distance_change_by_decision",
        ("seed", "policy", "decision_step", "n_measurements_before", "selected_key",
         "selected_identity", "selected_channel", "pcv_width_before_pct",
         "pcv_width_after_pct", "pcv_gate_ratio_before", "pcv_gate_ratio_after",
         "lm_width_before_pct", "lm_width_after_pct", "lm_gate_ratio_before",
         "lm_gate_ratio_after", "max_gate_ratio_before", "max_gate_ratio_after",
         "max_gate_ratio_improvement", "positive_gate_excess_before",
         "positive_gate_excess_after", "positive_gate_excess_improvement",
         "both_gate_widths_met_after"),
    ),
}


def write_analysis(
    release_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    release_dir = release_dir.resolve()
    output_dir = output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    records, sources = _load_records(release_dir)
    analysis = analyze_records(records)
    manifest_path = release_dir / "manifest.json"
    analysis["source"] = {
        "release_id": release_dir.name,
        "release_manifest_sha256": _sha256(manifest_path) if manifest_path.is_file() else None,
        "acquisition_records": sources,
    }
    _write_json(output_dir / "summary.json", analysis)
    aggregate = {
        "schema": analysis["schema"],
        "benchmark_version": analysis["benchmark_version"],
        "source": analysis["source"],
        "seed_count": analysis["seed_count"],
        "seeds": analysis["seeds"],
        "policy_order": analysis["policy_order"],
        "gate_contract": analysis["gate_contract"],
        "metric_definitions": analysis["metric_definitions"],
        "selection_frequency_by_step": analysis["selection_frequency_by_step"],
        "pairwise_same_candidate_overall": analysis[
            "pairwise_same_candidate_overall"
        ],
        "path_overlap_aggregate": analysis["path_overlap_aggregate"],
        "ranking_correlation_aggregate": analysis[
            "ranking_correlation_aggregate"
        ],
        "ranking_correlation_by_measurement_count": analysis[
            "ranking_correlation_by_measurement_count"
        ],
        "gate_distance_change_aggregate": analysis[
            "gate_distance_change_aggregate"
        ],
        "interpretation_limits": analysis["interpretation_limits"],
    }
    _write_json(output_dir / "aggregate_summary.json", aggregate)
    for filename, (section, fields) in CSV_SPECS.items():
        _write_csv(output_dir / filename, analysis[section], fields)
    output_names = ("summary.json", "aggregate_summary.json", *CSV_SPECS)
    output_hashes = {name: _sha256(output_dir / name) for name in output_names}
    _write_json(output_dir / "checksums.json", {
        "schema": ANALYSIS_SCHEMA,
        "files": output_hashes,
    })
    return analysis


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    analysis = write_analysis(args.release_dir, args.output_dir)
    print(json.dumps({
        "schema": analysis["schema"],
        "release_id": analysis["source"]["release_id"],
        "seed_count": analysis["seed_count"],
        "policy_count": len(analysis["policy_order"]),
        "output_dir": str(args.output_dir.resolve()),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
