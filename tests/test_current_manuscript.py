"""Tests for the full current-paper source contract."""

from __future__ import annotations

import importlib.util
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
    summary = (
        ROOT / "results" / "frozen" / "20260812T035654Z_a0703698ace9"
        / "tables" / "paper_summary.json"
    )
    figures = ROOT / "paper" / "current_state" / "source" / "figures"
    result = generator.verify(summary, figures)
    assert result["verified_figure_count"] == 4


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
