"""Tests for the full current-paper source contract."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_current_manuscript.py"
SPEC = importlib.util.spec_from_file_location("check_current_manuscript", SCRIPT)
assert SPEC and SPEC.loader
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


def test_current_manuscript_contract_passes() -> None:
    paper = ROOT / "paper" / "current_state" / "source"
    result = CHECKER.audit(paper / "main.tex", paper / "refs.bib")
    assert result["valid"] is True
    assert result["reference_count"] >= 45
    assert result["full_figure_count"] == 4


def test_full_paper_figure_manifest_matches_frozen_summary() -> None:
    script = ROOT / "scripts" / "generate_current_paper_figures.py"
    spec = importlib.util.spec_from_file_location("generate_current_paper_figures", script)
    assert spec and spec.loader
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    release_id = (ROOT / "results" / "CURRENT").read_text(encoding="utf-8").strip()
    summary = ROOT / "results" / "frozen" / release_id / "tables" / "paper_summary.json"
    figures = ROOT / "paper" / "current_state" / "source" / "figures"
    result = generator.verify(summary, figures)
    assert result["verified_figure_count"] == 4


def test_v4_acquisition_figure_requires_all_preregistered_contrasts() -> None:
    script = ROOT / "scripts" / "generate_current_paper_figures.py"
    spec = importlib.util.spec_from_file_location("generate_current_paper_figures_v4", script)
    assert spec and spec.loader
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    summary = {"eig": {"primary_contrasts": {}}}
    assert generator.acquisition_figure_mode(summary) == "legacy"
    summary["eig"]["primary_contrasts"] = {
        key: {} for key in generator.V4_PRIMARY_CONTRASTS
    }
    assert generator.acquisition_figure_mode(summary) == "v4_direct"
    summary["eig"]["primary_contrasts"].pop(generator.V4_PRIMARY_CONTRASTS[-1])
    with pytest.raises(ValueError, match="incomplete v4 primary contrasts"):
        generator.acquisition_figure_mode(summary)


def test_v4_summary_regenerates_and_verifies_all_four_full_figures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = ROOT / "scripts" / "generate_current_paper_figures.py"
    spec = importlib.util.spec_from_file_location("generate_current_paper_figures_render", script)
    assert spec and spec.loader
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    release_id = (ROOT / "results" / "CURRENT").read_text(encoding="utf-8").strip()
    source_summary = (
        ROOT / "results" / "frozen" / release_id / "tables" / "paper_summary.json"
    )
    summary = json.loads(source_summary.read_text(encoding="utf-8"))
    eig = summary["eig"]
    count_values = [float(value) + 1.0 for value in eig["raw_counts"]]
    cost_values = [float(value) + 10.0 for value in eig["per_cost_modeled_costs"]]
    eig["strong_comparators"] = {
        "predictive_variance_raw": {"counts": count_values},
        "laplace_d_opt_raw": {"counts": count_values},
        "predictive_variance_per_cost": {"modeled_costs": cost_values},
        "laplace_d_opt_per_cost": {"modeled_costs": cost_values},
    }
    pair_count = len(eig["seeds"])
    eig["primary_contrasts"] = {
        key: {
            "wins": pair_count, "ties": 0, "losses": 0,
            "complete_pair_count": pair_count, "total_pair_count": pair_count,
        }
        for key in generator.V4_PRIMARY_CONTRASTS
    }
    summary_path = tmp_path / "paper_summary.json"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    output_dir = tmp_path / "figures"
    monkeypatch.setattr(generator, "require_slurm", lambda: None)
    manifest = generator.generate(summary_path, output_dir)
    assert {entry["path"] for entry in manifest["outputs"]} == set(
        generator.FIGURE_NAMES
    )
    verified = generator.verify(summary_path, output_dir)
    assert verified["verified_figure_count"] == 4


def test_full_figure_verification_rejects_stale_release_mix(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "generate_current_paper_figures.py"
    spec = importlib.util.spec_from_file_location("generate_current_paper_figures_stale", script)
    assert spec and spec.loader
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    release_id = (ROOT / "results" / "CURRENT").read_text(encoding="utf-8").strip()
    source_summary = (
        ROOT / "results" / "frozen" / release_id / "tables" / "paper_summary.json"
    )
    stale_summary = json.loads(source_summary.read_text(encoding="utf-8"))
    stale_summary["release_id"] = "stale-release-sentinel"
    stale_path = tmp_path / "paper_summary.json"
    stale_path.write_text(json.dumps(stale_summary), encoding="utf-8")
    figures = ROOT / "paper" / "current_state" / "source" / "figures"
    with pytest.raises(ValueError, match="figure/release mismatch"):
        generator.verify(stale_path, figures)


def test_checker_rejects_uncited_entry(tmp_path: Path) -> None:
    paper = ROOT / "paper" / "current_state" / "source"
    source = tmp_path / "main.tex"
    bibliography = tmp_path / "refs.bib"
    source.write_text((paper / "main.tex").read_text(encoding="utf-8"), encoding="utf-8")
    bibliography.write_text(
        (paper / "refs.bib").read_text(encoding="utf-8")
        + "\n@misc{uncited_sentinel, title={Sentinel}, year={2026}}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="uncited bibliography"):
        CHECKER.audit(source, bibliography)


def test_checker_rejects_format_regression(tmp_path: Path) -> None:
    paper = ROOT / "paper" / "current_state" / "source"
    source = tmp_path / "main.tex"
    bibliography = tmp_path / "refs.bib"
    source.write_text(
        (paper / "main.tex").read_text(encoding="utf-8").replace(
            "10pt,a4paper,twocolumn", "10pt,a4paper"
        ),
        encoding="utf-8",
    )
    bibliography.write_text((paper / "refs.bib").read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(ValueError, match="two-column"):
        CHECKER.audit(source, bibliography)
