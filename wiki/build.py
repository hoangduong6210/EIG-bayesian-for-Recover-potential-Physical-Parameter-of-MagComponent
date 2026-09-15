#!/usr/bin/env python3
"""Validate the scientific manuscript and create named paper releases."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Callable
from pathlib import Path


WIKI_ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = WIKI_ROOT / "manuscript.toml"
FRONT_MATTER = re.compile(r"\A---\n(?P<body>.*?)\n---\n", re.DOTALL)
MARKDOWN_LINK = re.compile(
    r"(?P<prefix>!?\[[^\]]*\]\()(?P<target>[^)]+)(?P<suffix>\))"
)
README_NOTICE = (
    "<!-- Source: wiki/Home.md; update with `python wiki/build.py write-readme`. -->\n\n"
)
BANNED_PUBLIC_PATTERNS = {
    "credential": re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    "machine path": re.compile(r"/(?:users|home|scratch|tmp)/[A-Za-z0-9_.-]+/"),
    "automated-authoring provenance": re.compile(
        r"\b(?:Chat" + r"GPT|Open" + r"AI|Gr" + r"ok|Clau" + r"de|Code" +
        r"x|A" + r"I[- ]assisted)\b",
        re.IGNORECASE,
    ),
    "internal presentation note": re.compile(
        r"\b(?:Current Presen" + r"tation|no running hea" + r"der|reviewer res" + r"ponse)\b",
        re.IGNORECASE,
    ),
    "editorial process narration": re.compile(
        r"\b(?:current manuscript preser" + r"ves|one-way mir" + r"ror|"
        r"this wiki is the liv" + r"ing|may lag this (?:page|wiki)|"
        r"wiki is ne" + r"wer than|explicit snap" + r"shot is approved)\b",
        re.IGNORECASE,
    ),
}
DOCUMENT_RELEASE_TYPES = {"conference", "journal"}
DOCUMENT_RELEASE_NAME = re.compile(r"^(conference|journal)-[a-z0-9][a-z0-9.-]{2,63}$")


class WikiError(RuntimeError):
    """A fail-closed manuscript validation error."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_mm3_readiness(manifest: dict) -> dict:
    """Bind the campaign protocol and its separate production integration record."""
    root = WIKI_ROOT.parent.resolve()
    report = {}
    for section, key, field in (
        ("diagnostics", "production_integration", "record"),
        ("campaigns", "model_mismatch_v3", "config"),
    ):
        contract = manifest.get(section, {}).get(key)
        if contract is None:
            continue
        relative = contract.get(field)
        if not isinstance(relative, str) or Path(relative).is_absolute():
            raise WikiError("MM-3 evidence path must be repository-relative")
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file() \
                or sha256(path) != contract.get(field + "_sha256"):
            raise WikiError("MM-3 evidence checksum or path mismatch")
        if field == "record":
            record = json.loads(path.read_text(encoding="utf-8"))
            rows = record.get("states", [])
            if record.get("record_class") != "endpoint_free_production_sampler_integration_check" \
                    or record.get("all_checks_passed") is not True \
                    or record.get("scientific_endpoints_included") is not False \
                    or record.get("new_mismatch_campaign_admitted") is not False \
                    or len(rows) != 2 or {r.get("target_id") for r in rows} != {"n3", "n4"} \
                    or any(r.get("diagnostics", {}).get("valid") is not True for r in rows):
                raise WikiError("MM-3 integration evidence is not a complete endpoint-free pass")
        else:
            with path.open("rb") as stream:
                config = tomllib.load(stream)
            qualification = manifest.get("diagnostics", {}).get("sparse_mixing_v2", {})
            if config.get("campaign_id") != "MM-3" \
                    or config.get("status") != "preregistered_before_confirmatory_outcomes" \
                    or config.get("seeds") != list(range(10100, 10130)) \
                    or config.get("sampler_qualification_manifest_sha256") != qualification.get("manifest_sha256") \
                    or config.get("sampler_qualification_config_sha256") != qualification.get("config_sha256"):
                raise WikiError("MM-3 campaign identity or qualification binding differs")
            if "registration" in contract:
                relative_registration = contract["registration"]
                if not isinstance(relative_registration, str) or Path(relative_registration).is_absolute():
                    raise WikiError("MM-3 registration path is invalid")
                registration_path = (root / relative_registration).resolve()
                if not registration_path.is_relative_to(root) or not registration_path.is_file() \
                        or sha256(registration_path) != contract.get("registration_sha256"):
                    raise WikiError("MM-3 registration checksum or path mismatch")
                registered = json.loads(registration_path.read_text(encoding="utf-8"))
                if registered.get("campaign_id") != "MM-3" \
                        or registered.get("record_class") != "submission_record_not_a_completion_result" \
                        or registered.get("config_sha256") != contract["config_sha256"] \
                        or registered.get("expected_task_count") != 120 \
                        or registered.get("scientific_endpoints_included") is not False \
                        or registered.get("campaign_admission_decided") is not False:
                    raise WikiError("MM-3 registration is inconsistent with the protocol")
                report["model_mismatch_v3_registration_sha256"] = contract["registration_sha256"]
        report[key + "_sha256"] = contract[field + "_sha256"]
    return report


def check_mm3_result_contract(contract: dict) -> dict:
    """Validate the admitted MM-3 aggregate and its public audit binding."""

    if not isinstance(contract, dict):
        raise WikiError("MM-3 result contract must be a table")
    root = WIKI_ROOT.parent.resolve()
    records = {}
    for label in ("aggregate", "audit_manifest", "admission", "asset_descriptor"):
        relative, digest = contract.get(label), contract.get(f"{label}_sha256")
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
            raise WikiError(f"invalid MM-3 {label} path")
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise WikiError(f"missing or unsafe MM-3 {label}")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise WikiError(f"invalid MM-3 {label} SHA-256")
        if sha256(path) != digest:
            raise WikiError(f"MM-3 {label} SHA-256 mismatch")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, UnicodeError) as exc:
            raise WikiError(f"invalid MM-3 {label} JSON") from exc
        if not isinstance(value, dict):
            raise WikiError(f"MM-3 {label} must contain an object")
        records[label] = value

    aggregate = records["aggregate"]
    expected_scenarios = {
        "matched_control",
        "permeability_two_pole",
        "core_loss_temperature_curvature",
        "combined_mismatch",
    }
    expected_policies = {
        "eig_raw",
        "eig_per_cost",
        "fixed_channel_balanced",
        "random_channel_balanced",
        "predictive_variance_raw",
        "predictive_variance_per_cost",
        "laplace_d_opt_raw",
        "laplace_d_opt_per_cost",
    }
    expected_contrasts = {
        "eig_raw_vs_predictive_variance_raw",
        "eig_raw_vs_laplace_d_opt_raw",
        "eig_per_cost_vs_predictive_variance_per_cost",
        "eig_per_cost_vs_laplace_d_opt_per_cost",
    }
    if aggregate.get("schema_version") != "magcore-model-mismatch-aggregate/1.0" \
            or aggregate.get("campaign_id") != "MM-3" \
            or aggregate.get("config_sha256") != contract.get("config_sha256") \
            or aggregate.get("estimator_decision_sha256") \
            != "eb334ae2c188f12e7f544be71b6f0c40be15913ceec0df60e5bf9a9258ed82b6" \
            or aggregate.get("source_result_count") != 120 \
            or aggregate.get("scenario_count") != 4 \
            or aggregate.get("seed_count_per_scenario") != 30 \
            or aggregate.get("policy_count") != 8:
        raise WikiError("MM-3 aggregate identity or matrix differs")
    scenarios = aggregate.get("scenarios")
    if not isinstance(scenarios, dict) or set(scenarios) != expected_scenarios:
        raise WikiError("MM-3 aggregate scenario registry differs")
    source_files = aggregate.get("source_files")
    if not isinstance(source_files, list) or len(source_files) != 120:
        raise WikiError("MM-3 aggregate source inventory is incomplete")
    source_keys = set()
    for row in source_files:
        if not isinstance(row, dict) or row.get("scenario") not in expected_scenarios \
                or type(row.get("seed")) is not int \
                or row["seed"] not in range(10100, 10130) \
                or not re.fullmatch(r"[0-9a-f]{64}", str(row.get("sha256", ""))):
            raise WikiError("MM-3 aggregate source entry is malformed")
        source_keys.add((row["scenario"], row["seed"]))
    if len(source_keys) != 120:
        raise WikiError("MM-3 aggregate source identities are not unique and complete")
    for scenario in scenarios.values():
        policies = scenario.get("policies")
        contrasts = scenario.get("paired_strong_comparator_contrasts")
        if not isinstance(policies, dict) or set(policies) != expected_policies:
            raise WikiError("MM-3 policy registry differs")
        if not isinstance(contrasts, dict) or set(contrasts) != expected_contrasts:
            raise WikiError("MM-3 contrast registry differs")
        for policy in policies.values():
            reached, failed = policy.get("reached_gate_count"), policy.get("failure_to_gate_count")
            if policy.get("n_seeds") != 30 or type(reached) is not int \
                    or type(failed) is not int or reached + failed != 30:
                raise WikiError("MM-3 policy denominator differs")
        for contrast in contrasts.values():
            wins, ties, losses = (
                contrast.get("policy_wins"), contrast.get("ties"), contrast.get("policy_losses")
            )
            complete, excluded = (
                contrast.get("complete_pair_count"),
                contrast.get("excluded_pair_count_due_to_gate_failure"),
            )
            if any(type(value) is not int for value in (wins, ties, losses, complete, excluded)) \
                    or wins + ties + losses != complete or complete + excluded != 30:
                raise WikiError("MM-3 paired contrast accounting differs")

    audit = records["audit_manifest"]
    if audit.get("schema_version") != "magcore-model-mismatch-public-audit/1.0" \
            or audit.get("campaign_id") != "MM-3" \
            or audit.get("config_sha256") != contract.get("config_sha256") \
            or audit.get("matrix") != {
                "scenario_count": 4,
                "seed_count_per_scenario": 30,
                "policy_count": 8,
                "task_record_count": 120,
            }:
        raise WikiError("MM-3 audit manifest identity or matrix differs")
    task_records = audit.get("task_records")
    if not isinstance(task_records, list) or len(task_records) != 120:
        raise WikiError("MM-3 audit task inventory is incomplete")
    audit_sources = {
        (row.get("scenario"), row.get("seed")): row.get("source_sha256")
        for row in task_records if isinstance(row, dict)
    }
    aggregate_sources = {
        (row["scenario"], row["seed"]): row["sha256"] for row in source_files
    }
    if audit_sources != aggregate_sources or any(
        not re.fullmatch(r"[0-9a-f]{64}", str(row.get("sha256", "")))
        for row in task_records
    ):
        raise WikiError("MM-3 public task hashes do not bind the aggregate sources")
    scope = audit.get("scope", {})
    if scope.get("contains_scientific_endpoints") is not True \
            or scope.get("contains_acquisition_trajectories") is not True \
            or scope.get("contains_sampler_checkpoint_histories") is not True \
            or scope.get("contains_full_walker_iteration_chains") is not False \
            or scope.get("supports_independent_full_chain_diagnostic_recomputation") is not False:
        raise WikiError("MM-3 public audit scope differs")

    admission, asset = records["admission"], records["asset_descriptor"]
    if admission.get("schema_version") != "magcore-model-mismatch-admission/1.0" \
            or admission.get("campaign_id") != "MM-3" \
            or admission.get("decision") != "admitted" \
            or admission.get("aggregate_sha256") != contract["aggregate_sha256"] \
            or admission.get("audit_manifest_sha256") != contract["audit_manifest_sha256"] \
            or admission.get("basis", {}).get("validated_task_record_count") != 120 \
            or admission.get("basis", {}).get("raw_to_aggregate_scientific_match") is not True:
        raise WikiError("MM-3 admission record differs")
    declared_asset = asset.get("asset", {})
    if asset.get("schema_version") != "magcore-model-mismatch-audit-assets/1.0" \
            or asset.get("campaign_id") != "MM-3" \
            or asset.get("aggregate_sha256") != contract["aggregate_sha256"] \
            or asset.get("audit_manifest_sha256") != contract["audit_manifest_sha256"] \
            or declared_asset.get("task_record_count") != 120 \
            or not re.fullmatch(r"[0-9a-f]{64}", str(declared_asset.get("sha256", ""))) \
            or not str(declared_asset.get("url", "")).startswith("https://github.com/"):
        raise WikiError("MM-3 public asset descriptor differs")
    return {
        "model_mismatch_v3_aggregate_sha256": contract["aggregate_sha256"],
        "model_mismatch_v3_audit_manifest_sha256": contract["audit_manifest_sha256"],
        "model_mismatch_v3_admission_sha256": contract["admission_sha256"],
        "model_mismatch_v3_asset_descriptor_sha256": contract["asset_descriptor_sha256"],
    }


def check_sparse_pilot_contract(contract: dict) -> dict:
    """Validate optional pilot evidence before allowing Wiki claims to use it."""
    if not isinstance(contract, dict):
        raise WikiError("sparse-pilot diagnostic contract must be a table")
    root = WIKI_ROOT.parent.resolve()
    records = {}
    for label in ("manifest", "decision"):
        relative, digest = contract.get(label), contract.get(f"{label}_sha256")
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
            raise WikiError(f"invalid sparse-pilot {label} path")
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise WikiError(f"missing or unsafe sparse-pilot {label}")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise WikiError(f"invalid sparse-pilot {label} SHA-256")
        if sha256(path) != digest:
            raise WikiError(f"sparse-pilot {label} SHA-256 mismatch")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, UnicodeError) as exc:
            raise WikiError(f"invalid sparse-pilot {label} JSON") from exc
        if not isinstance(value, dict):
            raise WikiError(f"sparse-pilot {label} must contain an object")
        records[label] = value
    pilot, decision = records["manifest"], records["decision"]
    if pilot.get("schema_version") != "magcore-sparse-mixing-pilot-manifest/1.0" \
            or pilot.get("record_class") != "endpoint_free_sampler_pilot_manifest" \
            or pilot.get("protocol_id") != "SparseMix-Pilot-1":
        raise WikiError("unsupported sparse-pilot manifest identity")
    if pilot.get("matrix") != {"expected_task_count": 24, "validated_task_count": 24,
                               "artifact_count": 72}:
        raise WikiError("sparse-pilot matrix is not complete")
    disclosure = pilot.get("disclosure", {})
    if any(disclosure.get(key) is not False for key in (
        "scientific_endpoints_included", "automatic_admission", "claim_bearing_result",
        "retroactive_mm2_admission_allowed", "confirmatory_sampler_validation",
    )):
        raise WikiError("sparse-pilot disclosure boundary differs")
    if decision.get("schema_version") != "magcore-sparse-pilot-selection/1.0":
        raise WikiError("unsupported sparse-pilot decision schema")
    if decision.get("complete_matrix") is not True \
            or decision.get("pilot_manifest") != contract["manifest"] \
            or decision.get("pilot_manifest_sha256") != contract["manifest_sha256"]:
        raise WikiError("sparse-pilot decision source binding differs")
    arm = decision.get("selected_arm")
    if arm not in {"stretch", "de_snooker", "logit_stretch"}:
        raise WikiError("unsupported sparse-pilot selected arm")
    for target in ("n3", "n4"):
        summary = pilot.get("method_summaries", {}).get(target, {}).get(arm)
        if not isinstance(summary, dict) or summary.get("independent_ensemble_count") != 4:
            raise WikiError("sparse-pilot selected arm lacks both state summaries")
    return {"sparse_pilot_manifest_sha256": contract["manifest_sha256"],
            "sparse_pilot_decision_sha256": contract["decision_sha256"]}


def check_sparse_mixing_v2_contract(contract: dict) -> dict:
    """Bind the confirmatory diagnostic result to its prospective configuration."""
    if not isinstance(contract, dict):
        raise WikiError("SparseMix-2 diagnostic contract must be a table")
    root = WIKI_ROOT.parent.resolve()
    records = {}
    for label in ("manifest", "config"):
        relative, digest = contract.get(label), contract.get(f"{label}_sha256")
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
            raise WikiError(f"invalid SparseMix-2 {label} path")
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise WikiError(f"missing or unsafe SparseMix-2 {label}")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise WikiError(f"invalid SparseMix-2 {label} SHA-256")
        if sha256(path) != digest:
            raise WikiError(f"SparseMix-2 {label} SHA-256 mismatch")
        try:
            contents = path.read_text(encoding="utf-8")
            value = json.loads(contents) if label == "manifest" else tomllib.loads(contents)
        except (ValueError, UnicodeError) as exc:
            raise WikiError(f"invalid SparseMix-2 {label}") from exc
        if not isinstance(value, dict):
            raise WikiError(f"SparseMix-2 {label} must contain an object")
        records[label] = value
    result, config = records["manifest"], records["config"]
    if result.get("schema_version") != "magcore-sparse-mixing-v2-manifest/1.0" \
            or result.get("record_class") != "endpoint_free_confirmatory_sampler_validation_manifest" \
            or result.get("protocol_id") != "SparseMix-2" \
            or config.get("schema_version") != "magcore-sparse-mixing-v2/1.0" \
            or config.get("protocol_id") != "SparseMix-2":
        raise WikiError("unsupported SparseMix-2 evidence identity")
    if config.get("status") != "preregistered_before_confirmatory_chains" \
            or config.get("diagnostic_only") is not True \
            or config.get("retroactive_mm2_admission_allowed") is not False:
        raise WikiError("SparseMix-2 configuration disclosure differs")
    if result.get("config_sha256") != contract["config_sha256"] \
            or result.get("parent_config_sha256") != config.get("parent_config_sha256") \
            or result.get("pilot_decision_sha256") != config.get("pilot_decision_sha256") \
            or not isinstance(config.get("diagnostics"), dict) \
            or result.get("registered_criteria") != config["diagnostics"]:
        raise WikiError("SparseMix-2 configuration binding differs")
    if result.get("matrix") != {"expected_task_count": 16, "validated_task_count": 16,
                                "artifact_count": 48}:
        raise WikiError("SparseMix-2 matrix is not complete")
    tasks, artifacts = result.get("tasks"), result.get("artifacts")
    if not isinstance(tasks, list) or not isinstance(artifacts, list) \
            or len(tasks) != 16 or len(artifacts) != 16 \
            or any(not isinstance(row, dict) or not isinstance(row.get("task_id"), str)
                   for row in tasks + artifacts):
        raise WikiError("SparseMix-2 task records are incomplete")
    identities = {row["task_id"] for row in tasks}
    if len(identities) != 16 or {row["task_id"] for row in artifacts} != identities \
            or any(sum(row.get("target_id") == state for row in tasks) != 8 for state in ("n3", "n4")):
        raise WikiError("SparseMix-2 independent ensemble matrix differs")
    disclosure = result.get("disclosure", {})
    if any(disclosure.get(key) is not False for key in (
        "scientific_endpoints_included", "retroactive_mm2_admission_allowed", "model_mismatch_campaign_admitted",
    )) or disclosure.get("confirmatory_sampler_validation") is not True:
        raise WikiError("SparseMix-2 disclosure boundary differs")
    classifications = result.get("classifications")
    if not isinstance(classifications, dict) or set(classifications) != {"n3", "n4"}:
        raise WikiError("SparseMix-2 classifications must cover both locked states")
    passes = []
    for row in classifications.values():
        if not isinstance(row, dict) or row.get("independent_ensemble_count") != 8 \
                or type(row.get("criteria_passed")) is not bool \
                or not isinstance(row.get("reason_codes"), list):
            raise WikiError("SparseMix-2 classification is malformed")
        passed = row["criteria_passed"]
        if row.get("classification") != ("mixing_supported" if passed else "mixing_not_supported") \
                or passed != (len(row["reason_codes"]) == 0):
            raise WikiError("SparseMix-2 classification contradicts its criteria")
        passes.append(passed)
    if type(result.get("both_states_pass")) is not bool or result["both_states_pass"] != all(passes):
        raise WikiError("SparseMix-2 both-state claim contradicts classifications")
    return {"sparse_mixing_v2_manifest_sha256": contract["manifest_sha256"],
            "sparse_mixing_v2_config_sha256": contract["config_sha256"],
            "sparse_mixing_v2_both_states_pass": result["both_states_pass"]}


def aggregate_digest(entries: dict[str, str]) -> str:
    """Hash a path-to-digest map without depending on filesystem traversal order."""
    digest = hashlib.sha256()
    for relative, value in sorted(entries.items()):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(value.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def load_manifest() -> dict:
    with MANIFEST_PATH.open("rb") as stream:
        manifest = tomllib.load(stream)
    if manifest.get("schema_version") != "magnetic-living-manuscript/1.0":
        raise WikiError("unsupported manuscript schema")
    return manifest


def declared_public_pages(manifest: dict) -> tuple[str, ...]:
    """Return the ordered, unique allowlist used by checks and publication."""
    pages = tuple(manifest.get("wiki", {}).get("public_pages", ()))
    if not pages or len(set(pages)) != len(pages):
        raise WikiError("wiki public-page allowlist is empty or contains duplicates")
    roles = {
        manifest.get("wiki", {}).get("home"),
        manifest.get("wiki", {}).get("index"),
        manifest.get("wiki", {}).get("sidebar"),
        manifest.get("canonical_page"),
    }
    if None in roles or not roles <= set(pages):
        raise WikiError("wiki role pages must be present in the public-page allowlist")
    slugs = [Path(page).name for page in pages]
    if len(set(slugs)) != len(slugs):
        raise WikiError("public Wiki page filenames must be unique after flattening")
    return pages


def strip_front_matter(text: str) -> str:
    match = FRONT_MATTER.match(text)
    if match is None:
        raise WikiError("cannot render a page without YAML front matter")
    return text[match.end() :].lstrip()


def split_local_target(raw: str) -> tuple[str, str] | None:
    """Split a local Markdown target into path and optional fragment."""
    target = raw.strip()
    if not target or target.startswith("#"):
        return None
    if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.IGNORECASE):
        return None
    path, marker, fragment = target.partition("#")
    return path, ("#" + fragment if marker else "")


def rewrite_markdown_links(
    text: str, source: Path, resolve_target: Callable[[Path, str], str]
) -> str:
    """Rewrite local Markdown targets while leaving external links unchanged."""

    def replace(match: re.Match[str]) -> str:
        split = split_local_target(match.group("target"))
        if split is None:
            return match.group(0)
        path, fragment = split
        rewritten = resolve_target(source, path)
        return (
            match.group("prefix")
            + rewritten
            + fragment
            + match.group("suffix")
        )

    return MARKDOWN_LINK.sub(replace, text)


def render_repository_readme(manifest: dict | None = None) -> str:
    """Render the repository landing page from the canonical Wiki home."""
    manifest = manifest or load_manifest()
    source = WIKI_ROOT / manifest["readme"]["source"]
    repository = WIKI_ROOT.parent.resolve()

    def resolve_target(page: Path, raw_path: str) -> str:
        target = (page.parent / raw_path).resolve()
        try:
            relative = target.relative_to(repository)
        except ValueError as exc:
            raise WikiError(f"README link escapes repository: {raw_path}") from exc
        return relative.as_posix()

    body = strip_front_matter(source.read_text(encoding="utf-8"))
    return README_NOTICE + rewrite_markdown_links(body, source, resolve_target)


def write_repository_readme() -> Path:
    """Atomically refresh README.md from the canonical Wiki home."""
    manifest = load_manifest()
    output = (WIKI_ROOT / manifest["readme"]["output"]).resolve()
    if output != WIKI_ROOT.parent / "README.md":
        raise WikiError("README output must be the repository landing page")
    temporary = output.with_name(output.name + ".tmp")
    temporary.write_text(render_repository_readme(manifest), encoding="utf-8")
    temporary.replace(output)
    return output


def bibliography_keys(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    return set(re.findall(r"(?m)^@\w+\s*\{\s*([^,\s]+)\s*,", text))


def citation_keys(text: str) -> set[str]:
    return set(re.findall(r"(?<!\w)@([A-Za-z0-9_.:-]+)", text))


def local_markdown_targets(text: str) -> set[str]:
    targets: set[str] = set()
    for raw in re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", text):
        target = raw.strip().split("#", 1)[0]
        if not target or re.match(r"^[a-z][a-z0-9+.-]*:", target, re.IGNORECASE):
            continue
        targets.add(target)
    return targets


def markdown_anchors(text: str) -> set[str]:
    """Return explicit and GitHub-style heading anchors for a Markdown page."""
    anchors = set(re.findall(r'<a\s+id=["\']([^"\']+)["\']\s*></a>', text))
    for heading in re.findall(r"(?m)^#{1,6}\s+(.+?)\s*#*\s*$", text):
        label = re.sub(r"!?\[([^\]]+)\]\([^)]+\)", r"\1", heading)
        label = re.sub(r"[`*_{}\\]", "", label).lower()
        label = "".join(
            character
            for character in label
            if character.isalnum() or character in {" ", "-"}
        )
        anchors.add(re.sub(r"-+", "-", re.sub(r"\s+", "-", label)).strip("-"))
    return anchors


def split_manuscript(text: str) -> tuple[str, str]:
    abstract_marker = "## Abstract\n"
    keywords_marker = "\n*Keywords:*"
    body_marker = "\n# Introduction\n"
    if abstract_marker not in text or keywords_marker not in text or body_marker not in text:
        raise WikiError("canonical manuscript lacks abstract, keywords, or introduction")
    abstract_start = text.index(abstract_marker) + len(abstract_marker)
    abstract_end = text.index(keywords_marker, abstract_start)
    body_start = text.index(body_marker, abstract_end) + 1
    abstract = text[abstract_start:abstract_end].strip()
    body = text[body_start:].strip() + "\n"
    if len(abstract.split()) < 120 or len(body.split()) < 3500:
        raise WikiError("manuscript content is unexpectedly incomplete")
    return abstract + "\n", body


def check() -> dict:
    manifest = load_manifest()
    public_pages = declared_public_pages(manifest)
    snapshot_policy = manifest.get("snapshot", {})
    if snapshot_policy.get("source_direction") != "wiki_to_document":
        raise WikiError("paper export must declare wiki_to_document source direction")
    if set(snapshot_policy.get("document_release_types", [])) != DOCUMENT_RELEASE_TYPES:
        raise WikiError("document release types must be conference and journal")
    if snapshot_policy.get("paper_output_is_explicit") is not True:
        raise WikiError("paper output must remain an explicit operation")
    missing_pages = sorted(name for name in public_pages if not (WIKI_ROOT / name).is_file())
    if missing_pages:
        raise WikiError(f"missing wiki pages: {missing_pages}")
    declared_markdown = set(public_pages) | {"README.md"}
    actual_markdown = {
        str(path.relative_to(WIKI_ROOT)) for path in WIKI_ROOT.rglob("*.md")
    }
    if actual_markdown != declared_markdown:
        missing = sorted(declared_markdown - actual_markdown)
        undeclared = sorted(actual_markdown - declared_markdown)
        raise WikiError(
            f"wiki page inventory mismatch; missing={missing}, undeclared={undeclared}"
        )

    for relative in manifest["wiki"].get("public_assets", []):
        if not (WIKI_ROOT / relative).is_file():
            raise WikiError(f"missing public Wiki asset: {relative}")

    canonical = WIKI_ROOT / manifest["canonical_page"]
    bibliography = WIKI_ROOT / manifest["bibliography"]
    template = WIKI_ROOT / manifest["template"]
    for path in (canonical, bibliography, template):
        if not path.is_file():
            raise WikiError(f"missing declared manuscript input: {path.relative_to(WIKI_ROOT)}")

    texts: dict[Path, str] = {}
    public_text_suffixes = {".md", ".json", ".toml", ".py", ".tex", ".bib", ".lua"}
    paper_sources: list[str] = []
    for path in sorted(
        item
        for item in WIKI_ROOT.rglob("*")
        if item.is_file() and item.suffix.lower() in public_text_suffixes
    ):
        text = path.read_text(encoding="utf-8")
        texts[path] = text
        for label, pattern in BANNED_PUBLIC_PATTERNS.items():
            if pattern.search(text):
                raise WikiError(f"{label} found in {path.relative_to(WIKI_ROOT)}")
        if path.suffix.lower() == ".md":
            front = FRONT_MATTER.match(text)
            if front is None:
                raise WikiError(
                    f"missing YAML front matter in {path.relative_to(WIKI_ROOT)}"
                )
            fields = {
                line.split(":", 1)[0].strip()
                for line in front.group("body").splitlines()
                if ":" in line
            }
            required_fields = {"title", "status", "paper_source"}
            if not required_fields <= fields or not ({"last_updated", "date"} & fields):
                raise WikiError(
                    f"incomplete YAML front matter in {path.relative_to(WIKI_ROOT)}"
                )
            if re.search(r"(?m)^paper_source:\s*true\s*$", front.group("body")):
                paper_sources.append(str(path.relative_to(WIKI_ROOT)))
            for target in local_markdown_targets(text):
                resolved = (path.parent / target).resolve()
                if WIKI_ROOT.resolve() not in (resolved, *resolved.parents):
                    raise WikiError(
                        f"link escapes wiki root in {path.relative_to(WIKI_ROOT)}: {target}"
                    )
                if not resolved.exists():
                    raise WikiError(
                        f"broken local link in {path.relative_to(WIKI_ROOT)}: {target}"
                    )

    if paper_sources != [manifest["canonical_page"]]:
        raise WikiError(
            "paper_source must identify only the canonical full-manuscript page"
        )

    for path, text in texts.items():
        if path.suffix.lower() != ".md":
            continue
        for match in MARKDOWN_LINK.finditer(text):
            raw = match.group("target").strip()
            if raw.startswith("#"):
                target_path = path
                fragment = raw[1:]
            else:
                split = split_local_target(raw)
                if split is None:
                    continue
                raw_path, marker = split
                if not marker:
                    continue
                target_path = (path.parent / raw_path).resolve()
                fragment = marker[1:]
            if target_path.suffix.lower() != ".md":
                continue
            if fragment not in markdown_anchors(texts[target_path]):
                raise WikiError(
                    f"broken anchor in {path.relative_to(WIKI_ROOT)}: {raw}"
                )

    landing_page = WIKI_ROOT.parent / "README.md"
    landing_text = landing_page.read_text(encoding="utf-8")
    for label, pattern in BANNED_PUBLIC_PATTERNS.items():
        if pattern.search(landing_text):
            raise WikiError(f"{label} found in repository README.md")
    expected_readme = render_repository_readme(manifest)
    if landing_text != expected_readme:
        raise WikiError(
            "repository README.md is stale; run `python wiki/build.py write-readme`"
        )

    canonical_text = texts[canonical]
    abstract, body = split_manuscript(canonical_text)
    cited = citation_keys(canonical_text)
    available = bibliography_keys(bibliography)
    unresolved = sorted(cited - available)
    if unresolved:
        raise WikiError(f"unresolved citation keys: {unresolved}")
    minimum_bibliography = int(manifest["snapshot"]["minimum_bibliography_items"])
    if len(available) < minimum_bibliography:
        raise WikiError("bibliography is smaller than the declared minimum")

    release_id = manifest["evidence"]["release_id"]
    release_digest = manifest["evidence"]["manifest_sha256"]
    projection_path = WIKI_ROOT / manifest["evidence"]["projection"]
    projection_digest = manifest["evidence"]["projection_sha256"]
    overlap_path = WIKI_ROOT.parent / manifest["evidence"]["selection_overlap"]
    overlap_digest = manifest["evidence"]["selection_overlap_sha256"]
    if not re.fullmatch(r"\d{8}T\d{6}Z_[0-9a-f]{12}", release_id):
        raise WikiError("invalid evidence release ID")
    if not re.fullmatch(r"[0-9a-f]{64}", release_digest):
        raise WikiError("invalid evidence manifest SHA-256")
    if not projection_path.is_file():
        raise WikiError("missing disclosure-safe evidence projection")
    if not re.fullmatch(r"[0-9a-f]{64}", projection_digest):
        raise WikiError("invalid evidence projection SHA-256")
    if sha256(projection_path) != projection_digest:
        raise WikiError("evidence projection SHA-256 mismatch")
    if not overlap_path.is_file():
        raise WikiError("missing selection-overlap diagnostic")
    if not re.fullmatch(r"[0-9a-f]{64}", overlap_digest):
        raise WikiError("invalid selection-overlap SHA-256")
    if sha256(overlap_path) != overlap_digest:
        raise WikiError("selection-overlap SHA-256 mismatch")
    overlap = json.loads(overlap_path.read_text(encoding="utf-8"))
    if overlap.get("schema") != "magcore-selection-overlap/1.0":
        raise WikiError("unsupported selection-overlap schema")
    if overlap.get("seed_count") != 30:
        raise WikiError("unexpected selection-overlap seed count")
    if overlap.get("source", {}).get("release_id") != release_id:
        raise WikiError("selection-overlap release ID mismatch")
    if overlap.get("source", {}).get("release_manifest_sha256") != release_digest:
        raise WikiError("selection-overlap release manifest mismatch")

    pilot_report = {}
    if "sparse_pilot" in manifest.get("diagnostics", {}):
        pilot_report = check_sparse_pilot_contract(manifest["diagnostics"]["sparse_pilot"])
    sparse_v2_report = {}
    if "sparse_mixing_v2" in manifest.get("diagnostics", {}):
        sparse_v2_report = check_sparse_mixing_v2_contract(manifest["diagnostics"]["sparse_mixing_v2"])
    mm3_result_report = {}
    if "model_mismatch_v3" in manifest.get("campaigns", {}):
        mm3_result_report = check_mm3_result_contract(
            manifest["campaigns"]["model_mismatch_v3"]
        )
    sparse_contract = manifest.get("diagnostics", {}).get("sparse_mixing", {})
    if sparse_contract.get("protocol_id") != "SparseMix-1":
        raise WikiError("unexpected sparse-mixing protocol identity")
    sparse_run_id = sparse_contract.get("run_id", "")
    if not re.fullmatch(r"\d{8}T\d{6}Z_[0-9a-f]{12}", sparse_run_id):
        raise WikiError("invalid sparse-mixing run ID")
    sparse_manifest_path = WIKI_ROOT.parent / sparse_contract.get("manifest", "")
    sparse_descriptor_path = (
        WIKI_ROOT.parent / sparse_contract.get("asset_descriptor", "")
    )
    for path, digest, label in (
        (sparse_manifest_path, sparse_contract.get("manifest_sha256", ""),
         "sparse-mixing manifest"),
        (sparse_descriptor_path,
         sparse_contract.get("asset_descriptor_sha256", ""),
         "sparse-mixing asset descriptor"),
    ):
        if not path.is_file():
            raise WikiError(f"missing {label}")
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise WikiError(f"invalid {label} SHA-256")
        if sha256(path) != digest:
            raise WikiError(f"{label} SHA-256 mismatch")
    sparse_result = json.loads(sparse_manifest_path.read_text(encoding="utf-8"))
    if sparse_result.get("schema_version") != "magcore-sparse-mixing-manifest/1.0":
        raise WikiError("unsupported sparse-mixing manifest schema")
    if sparse_result.get("protocol_id") != sparse_contract["protocol_id"]:
        raise WikiError("sparse-mixing manifest protocol mismatch")
    if sparse_result.get("matrix") != {
        "artifact_count": 36,
        "expected_task_count": 18,
        "validated_task_count": 18,
    }:
        raise WikiError("sparse-mixing matrix is not complete")
    if sparse_result.get("disclosure") != {
        "claim_bearing_result": False,
        "mm2_admission_changed": False,
        "scientific_endpoints_included": False,
    }:
        raise WikiError("sparse-mixing disclosure boundary differs")
    sparse_classes = sparse_result.get("classifications", {})
    if sparse_classes.get("n3", {}).get("classification") != "mixing_supported" \
            or sparse_classes.get("n4", {}).get("classification") \
            != "mixing_not_supported":
        raise WikiError("unexpected sparse-mixing classifications")
    sparse_descriptor = json.loads(
        sparse_descriptor_path.read_text(encoding="utf-8")
    )
    if sparse_descriptor.get("schema_version") \
            != "magnetic-sparse-mixing-audit-assets/1.0":
        raise WikiError("unsupported sparse-mixing asset descriptor schema")
    if sparse_descriptor.get("run_id") != sparse_run_id \
            or sparse_descriptor.get("source_validator_manifest_sha256") \
            != sparse_contract["manifest_sha256"]:
        raise WikiError("sparse-mixing descriptor source binding differs")
    if sparse_descriptor.get("protocol_id") != sparse_contract["protocol_id"] \
            or sparse_descriptor.get("preregistration_config_sha256") \
            != sparse_result.get("config_sha256"):
        raise WikiError("sparse-mixing descriptor protocol binding differs")
    expected_sparse_classes = {
        target: record["classification"]
        for target, record in sparse_classes.items()
    }
    if sparse_descriptor.get("classifications") != expected_sparse_classes:
        raise WikiError("sparse-mixing descriptor classifications differ")
    if sparse_descriptor.get("validation") != {
        "all_artifact_hashes_match": True,
        "artifact_count": 36,
        "exact_replay_task_count": 2,
        "expected_task_count": 18,
        "source_validator_exact_replay_match": True,
        "validated_task_count": 18,
    }:
        raise WikiError("sparse-mixing descriptor validation differs")
    if sparse_descriptor.get("scope") != {
        "changes_mm2_admission": False,
        "contains_deterministic_thinned_chains": True,
        "contains_full_walker_iteration_chains": False,
        "contains_scientific_endpoints": False,
        "full_chain_diagnostics_recomputable_from_asset": False,
    }:
        raise WikiError("sparse-mixing descriptor scope differs")
    sparse_asset = sparse_descriptor.get("asset", {})
    if sparse_asset.get("task_record_count") != 18 \
            or sparse_asset.get("deterministic_thinned_chain_count") != 18 \
            or sparse_asset.get("payload_file_count") != 37 \
            or not re.fullmatch(r"[0-9a-f]{64}", sparse_asset.get("sha256", "")) \
            or not re.fullmatch(
                r"[0-9a-f]{64}", sparse_asset.get("bundle_manifest_sha256", "")
            ):
        raise WikiError("sparse-mixing public asset declaration differs")
    projection = json.loads(projection_path.read_text(encoding="utf-8"))
    if projection.get("schema_version") != "magnetic-wiki-evidence/1.0":
        raise WikiError("unsupported evidence projection schema")
    if projection["release"]["id"] != release_id:
        raise WikiError("evidence projection release ID mismatch")
    if projection["release"]["manifest_sha256"] != release_digest:
        raise WikiError("evidence projection manifest SHA-256 mismatch")
    jobs = projection["scientific_jobs"]
    declared_artifacts = projection["campaign"]["result_artifact_count"]
    if sum(job["artifacts"] for job in jobs) != declared_artifacts:
        raise WikiError("scientific job registry does not cover every artifact")
    if declared_artifacts != 222:
        raise WikiError("unexpected result-artifact count")
    record_set = projection["sources"]["acquisition_record_set"]
    if record_set["record_count"] != 30:
        raise WikiError("unexpected paired acquisition-record count")
    figure_manifest_path = WIKI_ROOT / "assets" / "acquisition-diagnostics.json"
    figure_manifest = json.loads(figure_manifest_path.read_text(encoding="utf-8"))
    if figure_manifest["evidence_projection_sha256"] != projection_digest:
        raise WikiError("acquisition figure is not bound to current evidence")
    figure_path = WIKI_ROOT / "assets" / figure_manifest["figure"]
    if sha256(figure_path) != figure_manifest["figure_sha256"]:
        raise WikiError("acquisition figure SHA-256 mismatch")
    if figure_manifest["evidence_sources"] != ["E4", "E5"]:
        raise WikiError("acquisition figure has unexpected evidence sources")
    source_page_path = WIKI_ROOT / "evidence" / "Evidence-Sources.md"
    source_page = texts[source_page_path]
    for source_id in range(1, 17):
        anchor = f'<a id="e{source_id}"></a>'
        if anchor not in source_page:
            raise WikiError(f"missing evidence source anchor E{source_id}")
    for page in (
        "Home.md",
        "status/Project-Status.md",
        "manuscript/Full-Manuscript.md",
        "claims/Claims-and-Limits.md",
        "results/Scientific-Job-Results.md",
    ):
        if "Evidence-Sources.md#e" not in texts[WIKI_ROOT / page]:
            raise WikiError(f"{page} has no source-bound quantitative result")
    index_path = WIKI_ROOT / manifest["wiki"]["index"]
    index_targets = {
        str((index_path.parent / target).resolve().relative_to(WIKI_ROOT))
        for target in local_markdown_targets(texts[index_path])
        if (index_path.parent / target).resolve().suffix == ".md"
    }
    indexed_pages = set(public_pages) - {
        manifest["wiki"]["index"],
        manifest["wiki"]["sidebar"],
    }
    omitted = sorted(indexed_pages - index_targets)
    if omitted:
        raise WikiError(f"Wiki index omits canonical pages: {omitted}")
    for page in ("manuscript/Full-Manuscript.md", "status/Project-Status.md"):
        if release_id not in texts[WIKI_ROOT / page] or release_digest not in texts[WIKI_ROOT / page]:
            raise WikiError(f"{page} is not bound to the declared evidence release")

    return {
        **pilot_report,
        **sparse_v2_report,
        **mm3_result_report,
        **check_mm3_readiness(manifest),
        "abstract_words": len(abstract.split()),
        "body_words": len(body.split()),
        "citation_count": len(cited),
        "bibliography_count": len(available),
        "evidence_release_id": release_id,
        "evidence_projection_sha256": projection_digest,
        "selection_overlap_sha256": overlap_digest,
        "sparse_mixing_manifest_sha256": sparse_contract["manifest_sha256"],
        "sparse_mixing_asset_descriptor_sha256": (
            sparse_contract["asset_descriptor_sha256"]
        ),
        "scientific_job_count": len(jobs),
        "result_artifact_count": declared_artifacts,
        "acquisition_figure_sha256": figure_manifest["figure_sha256"],
        "repository_readme_sha256": sha256(landing_page),
        "wiki_inputs": {
            str(path.relative_to(WIKI_ROOT)): sha256(path)
            for path in sorted(
                {
                    *texts, bibliography, template, MANIFEST_PATH,
                    WIKI_ROOT / "bibliography" / "IEEEtran.bst",
                    *(WIKI_ROOT / name for name in manifest["wiki"]["public_assets"]),
                },
                key=lambda item: str(item),
            )
        },
    }


def render_public_wiki_page(
    relative: str, manifest: dict, source_revision: str
) -> str:
    """Render one organized source page into the flat hosted-Wiki namespace."""
    source = WIKI_ROOT / relative
    pages = declared_public_pages(manifest)
    slugs = {page: Path(page).name for page in pages}
    public_assets = set(manifest["wiki"].get("public_assets", []))
    repository_url = manifest["publication"]["repository_url"].rstrip("/")

    def resolve_target(page: Path, raw_path: str) -> str:
        target = (page.parent / raw_path).resolve()
        try:
            target_relative = target.relative_to(WIKI_ROOT).as_posix()
        except ValueError as exc:
            raise WikiError(
                f"public Wiki link escapes source tree: {relative}: {raw_path}"
            ) from exc
        if target_relative in slugs:
            return slugs[target_relative]
        if target_relative in public_assets:
            return target_relative
        if not target.exists():
            raise WikiError(f"public Wiki link target does not exist: {target_relative}")
        return f"{repository_url}/blob/{source_revision}/wiki/{target_relative}"

    body = strip_front_matter(source.read_text(encoding="utf-8"))
    return rewrite_markdown_links(body, source, resolve_target)


def validate_public_wiki_tree(output: Path) -> None:
    """Reject broken local links and anchors in a staged hosted-Wiki tree."""
    markdown = {
        path.resolve(): path.read_text(encoding="utf-8")
        for path in output.glob("*.md")
    }
    for path, text in markdown.items():
        for match in MARKDOWN_LINK.finditer(text):
            raw = match.group("target").strip()
            if raw.startswith("#"):
                target = path
                fragment = raw[1:]
            else:
                split = split_local_target(raw)
                if split is None:
                    continue
                raw_path, marker = split
                target = (path.parent / raw_path).resolve()
                fragment = marker[1:] if marker else ""
            if not target.exists():
                raise WikiError(
                    f"broken staged Wiki link in {path.name}: {raw}"
                )
            if fragment and target.suffix.lower() == ".md":
                target_text = markdown.get(target)
                if target_text is None or fragment not in markdown_anchors(target_text):
                    raise WikiError(
                        f"broken staged Wiki anchor in {path.name}: {raw}"
                    )


def stage_public_wiki(output: Path) -> Path:
    """Create an allowlisted, flat hosted-Wiki projection outside the repo."""
    resolved_output = output.resolve()
    repository = WIKI_ROOT.parent.resolve()
    if output.exists():
        raise WikiError(f"Wiki staging output already exists: {output}")
    if resolved_output == repository or repository in resolved_output.parents:
        raise WikiError("public Wiki staging output must be outside the repository")

    manifest = load_manifest()
    report = check()
    source_revision = committed_wiki_revision()
    output.mkdir(parents=True)
    try:
        rendered: dict[str, str] = {}
        for relative in declared_public_pages(manifest):
            slug = Path(relative).name
            target = output / slug
            target.write_text(
                render_public_wiki_page(relative, manifest, source_revision),
                encoding="utf-8",
            )
            rendered[slug] = sha256(target)

        for relative in manifest["wiki"].get("public_assets", []):
            source = WIKI_ROOT / relative
            target = output / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            rendered[relative] = sha256(target)

        validate_public_wiki_tree(output)

        record = {
            "schema_version": "magnetic-public-wiki/1.0",
            "source_revision": source_revision,
            "source_tree_sha256": aggregate_digest(report["wiki_inputs"]),
            "evidence_release_id": report["evidence_release_id"],
            "evidence_projection_sha256": report["evidence_projection_sha256"],
            "files": dict(sorted(rendered.items())),
        }
        record_path = output / "publish-manifest.json"
        record_path.write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return record_path
    except Exception:
        (output / "WIKI_STAGING_FAILED").write_text(
            "public Wiki staging failed\n", encoding="utf-8"
        )
        raise


def require_snapshot_tools() -> tuple[str, str]:
    """Resolve and verify the optional document toolchain for paper export."""
    pandoc = shutil.which("pandoc")
    latexmk = shutil.which("latexmk")
    if pandoc is None or latexmk is None:
        raise WikiError("pandoc and latexmk are required for snapshot capability")
    version = subprocess.run(
        [pandoc, "--version"], check=True, capture_output=True, text=True
    ).stdout.splitlines()[0].removeprefix("pandoc ")
    expected = load_manifest()["pandoc_version"]
    if version != expected:
        raise WikiError(f"pandoc version mismatch: expected {expected}, got {version}")
    return pandoc, latexmk


def validate_document_release(document_kind: str, release_name: str) -> None:
    """Validate immutable document-release identity before creating output."""
    if document_kind not in DOCUMENT_RELEASE_TYPES:
        raise WikiError(f"unsupported document kind: {document_kind}")
    if not DOCUMENT_RELEASE_NAME.fullmatch(release_name):
        raise WikiError(
            "release name must start with conference- or journal- and use "
            "lowercase letters, digits, dots, or hyphens"
        )
    if not release_name.startswith(document_kind + "-"):
        raise WikiError("release name prefix does not match document kind")


def committed_wiki_revision() -> str:
    """Return the exact committed wiki source and reject uncommitted wiki input."""
    repository = WIKI_ROOT.parent
    status = subprocess.run(
        ["git", "status", "--porcelain", "--", "wiki", "README.md"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if status:
        raise WikiError("commit the Wiki and README projection before publishing")
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise WikiError("could not resolve a full source wiki commit")
    return revision


def render_document_markdown(text: str, wiki_commit: str) -> str:
    """Bind PDF evidence links to the reviewed commit and prefer vector figures."""
    manifest = load_manifest()
    source = WIKI_ROOT / manifest["canonical_page"]
    repository_url = manifest["publication"]["repository_url"].rstrip("/")

    def resolve_target(page: Path, raw_path: str) -> str:
        target = (page.parent / raw_path).resolve()
        if target.is_relative_to((WIKI_ROOT / "assets").resolve()):
            vector = target.with_suffix(".pdf")
            asset = vector if vector.is_file() else target
            return asset.relative_to(WIKI_ROOT).as_posix()
        relative = target.relative_to(WIKI_ROOT.parent).as_posix()
        return f"{repository_url}/blob/{wiki_commit}/{relative}"

    return rewrite_markdown_links(text, source, resolve_target)


def render_document_bibliography(text: str) -> str:
    """Expose source DOI fields through IEEEtran's supported note field.

    The unmodified upstream style predates DOI-field support. Preserve the
    canonical DOI and add its linked display only in the document projection.
    """
    entries = re.split(r"(?m)(?=^@)", text)
    for index, entry in enumerate(entries):
        doi_match = re.search(r"\bdoi\s*=\s*\{([^{}]+)\}", entry, re.IGNORECASE)
        if doi_match is None:
            continue
        if re.search(r"\bnote\s*=", entry, re.IGNORECASE):
            raise WikiError("DOI-bearing bibliography entry already has a note; review its display")
        doi = doi_match.group(1)
        if not re.fullmatch(r"10\.[0-9]{4,9}/[^\s{}\\]+", doi):
            raise WikiError("invalid DOI in document bibliography")
        end = entry.rfind("}")
        note = r"note={doi: \href{https://doi.org/" + doi + r"}{\nolinkurl{" + doi + "}}}"
        entries[index] = entry[:end].rstrip().rstrip(",") + ",\n  " + note + entry[end:]
    return "".join(entries)


def layout_document_latex(text: str) -> str:
    """Adapt pinned Pandoc longtables and figures to bounded two-column floats."""
    def table_float(match: re.Match[str]) -> str:
        table = match.group(0)
        caption_match = re.search(r"\\caption\{.*?\\tabularnewline", table, re.DOTALL)
        caption = ""
        if caption_match:
            caption = caption_match.group(0).removesuffix(r"\tabularnewline")
            table = table[:caption_match.start()] + table[caption_match.end():]
        table = re.sub(r"\\endfirsthead.*?\\endhead", "", table, flags=re.DOTALL)
        table = table.replace(r"\endhead", "")
        table = table.replace(r"\begin{longtable}[]", r"\begin{tabular}")
        table = table.replace(r"\end{longtable}", r"\end{tabular}")
        table = table.replace(r"\columnwidth", r"\textwidth")
        return (
            "\\begin{table*}[t]\n\\centering\n\\small\n" + caption + "\n"
            "\\setlength{\\tabcolsep}{4pt}\n" + table + "\n\\end{table*}"
        )

    text = re.sub(r"\\begin\{longtable\}.*?\\end\{longtable\}", table_float, text, flags=re.DOTALL)
    text = text.replace(r"\begin{figure}", r"\begin{figure*}[t]")
    text = text.replace(r"\end{figure}", r"\end{figure*}")
    text = text.replace(
        r"\includegraphics{",
        r"\includegraphics[width=\textwidth,height=0.38\textheight,keepaspectratio]{",
    )
    text = re.sub(
        r"\\texttt\{([0-9a-f]{64})\}",
        lambda match: r"\texttt{" + r"\allowbreak{}".join(
            match.group(1)[index:index + 8] for index in range(0, 64, 8)
        ) + "}",
        text,
    )
    return text


def run_pandoc(source: Path, output: Path) -> None:
    canonical_parent = (WIKI_ROOT / load_manifest()["canonical_page"]).parent
    subprocess.run(
        [
            "pandoc",
            str(source),
            "--from=markdown+tex_math_dollars+raw_tex",
            "--to=latex",
            "--natbib",
            "--lua-filter",
            str(WIKI_ROOT / "paper-layout.lua"),
            "--top-level-division=section",
            "--resource-path",
            os.pathsep.join((str(canonical_parent), str(WIKI_ROOT))),
            "--output",
            str(output),
        ],
        check=True,
    )
    output.write_text(layout_document_latex(output.read_text(encoding="utf-8")), encoding="utf-8")


def snapshot(output: Path, document_kind: str, release_name: str) -> Path:
    validate_document_release(document_kind, release_name)
    if output.exists():
        raise WikiError(f"snapshot output already exists: {output}")
    resolved_output = output.resolve()
    repository = WIKI_ROOT.parent.resolve()
    if resolved_output == repository or repository in resolved_output.parents:
        raise WikiError("snapshot output must be staged outside the repository")
    require_snapshot_tools()
    report = check()
    wiki_commit = committed_wiki_revision()
    output.mkdir(parents=True)
    try:
        canonical = WIKI_ROOT / load_manifest()["canonical_page"]
        abstract, body = split_manuscript(canonical.read_text(encoding="utf-8"))
        abstract = render_document_markdown(abstract, wiki_commit)
        body = render_document_markdown(body, wiki_commit)
        abstract_md = output / "abstract.md"
        body_md = output / "body.md"
        abstract_md.write_text(abstract, encoding="utf-8")
        body_md.write_text(body, encoding="utf-8")
        run_pandoc(abstract_md, output / "abstract.tex")
        run_pandoc(body_md, output / "body.tex")
        shutil.copy2(WIKI_ROOT / "paper-template.tex", output / "main.tex")
        (output / "references.bib").write_text(
            render_document_bibliography((WIKI_ROOT / "bibliography" / "references.bib").read_text(encoding="utf-8")),
            encoding="utf-8",
        )
        shutil.copy2(WIKI_ROOT / "bibliography" / "IEEEtran.bst", output / "IEEEtran.bst")
        (output / "assets").mkdir()
        for name in load_manifest()["wiki"]["public_assets"]:
            if name.startswith("assets/"):
                shutil.copy2(WIKI_ROOT / name, output / name)
        subprocess.run(
            [
                "latexmk",
                "-pdf",
                "-interaction=nonstopmode",
                "-halt-on-error",
                "-outdir=" + str(output),
                str(output / "main.tex"),
            ],
            check=True,
            cwd=output,
        )
        pdf = output / "main.pdf"
        bbl = output / "main.bbl"
        if not pdf.is_file() or not bbl.is_file():
            raise WikiError("snapshot build did not produce PDF and bibliography")
        if bbl.read_text(encoding="utf-8", errors="replace").count("\\bibitem") < 45:
            raise WikiError("snapshot bibliography is incomplete")
        generated = {
            path.relative_to(output).as_posix(): sha256(path)
            for path in sorted(output.rglob("*"))
            if path.is_file() and path.suffix in {".tex", ".pdf", ".png", ".bib", ".bst", ".bbl", ".json", ".md"}
        }
        snapshot_record = {
            "schema_version": "magnetic-paper-snapshot/1.0",
            "document_release": {
                "kind": document_kind,
                "name": release_name,
                "source_direction": "wiki_to_document",
            },
            "source": {
                "wiki_commit": wiki_commit,
                "wiki_tree_sha256": aggregate_digest(report["wiki_inputs"]),
            },
            **report,
            "generated": generated,
        }
        (output / "snapshot.json").write_text(
            json.dumps(snapshot_record, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return pdf
    except Exception:
        (output / "SNAPSHOT_FAILED").write_text("snapshot build failed\n", encoding="utf-8")
        raise


def verify_snapshot(directory: Path) -> dict:
    """Verify an archived document independently of the mutable Wiki state."""
    root = directory.resolve()
    record = json.loads((root / "snapshot.json").read_text(encoding="utf-8"))
    if record.get("schema_version") != "magnetic-paper-snapshot/1.0":
        raise WikiError("unsupported document snapshot schema")
    release = record.get("document_release", {})
    validate_document_release(release.get("kind", ""), release.get("name", ""))
    if release.get("source_direction") != "wiki_to_document":
        raise WikiError("snapshot is not sourced from Wiki")
    source = record.get("source", {})
    if not re.fullmatch(r"[a-f0-9]{40}", source.get("wiki_commit", "")):
        raise WikiError("snapshot lacks exact Wiki revision")
    inputs = record.get("wiki_inputs", {})
    if not inputs or source.get("wiki_tree_sha256") != aggregate_digest(inputs):
        raise WikiError("snapshot Wiki input manifest digest mismatch")
    generated = record.get("generated", {})
    required = {"main.pdf", "main.tex", "body.tex", "abstract.tex", "references.bib", "IEEEtran.bst", "main.bbl"}
    if not required <= generated.keys():
        raise WikiError("snapshot omits a required document artifact")
    for name, digest in generated.items():
        path = (root / name).resolve()
        if Path(name).is_absolute() or not path.is_relative_to(root):
            raise WikiError("snapshot artifact path escapes its directory")
        if not path.is_file() or not re.fullmatch(r"[a-f0-9]{64}", digest) or sha256(path) != digest:
            raise WikiError(f"snapshot artifact missing or changed: {name}")
    return {"release": release["name"], "source_commit": source["wiki_commit"], "verified_files": len(generated)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check", help="validate wiki without generating paper artifacts")
    subparsers.add_parser(
        "write-readme", help="refresh the repository README from Wiki Home"
    )
    wiki_parser = subparsers.add_parser(
        "stage-wiki", help="create a flat hosted-Wiki projection outside the repository"
    )
    wiki_parser.add_argument("--output", type=Path, required=True)
    snapshot_parser = subparsers.add_parser(
        "snapshot", help="explicitly render a staged conference or journal snapshot"
    )
    snapshot_parser.add_argument("--output", type=Path, required=True)
    snapshot_parser.add_argument(
        "--document-kind", choices=sorted(DOCUMENT_RELEASE_TYPES), required=True
    )
    snapshot_parser.add_argument("--release-name", required=True)
    verify_parser = subparsers.add_parser("verify-snapshot", help="verify a stored document without rebuilding it")
    verify_parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "check":
            print(json.dumps(check(), indent=2, sort_keys=True))
        elif args.command == "write-readme":
            print(write_repository_readme())
        elif args.command == "stage-wiki":
            print(stage_public_wiki(args.output))
        elif args.command == "verify-snapshot":
            print(json.dumps(verify_snapshot(args.directory), indent=2, sort_keys=True))
        else:
            print(snapshot(args.output, args.document_kind, args.release_name))
    except (WikiError, OSError, subprocess.CalledProcessError) as exc:
        print(f"wiki build failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
