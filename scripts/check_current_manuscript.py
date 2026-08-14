#!/usr/bin/env python3
"""Fail-closed source audit for the unrestricted current manuscript."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


MIN_REFERENCES = 45
REQUIRED_DOCUMENT_CLASS = r"\documentclass[10pt,a4paper,twocolumn]{article}"
REQUIRED_FIGURES = {
    "study_workflow_full.pdf",
    "synthetic_diagnostics_full.pdf",
    "acquisition_diagnostics_full.pdf",
    "measured_adequacy_full.pdf",
}
FORBIDDEN_SOURCE_PATTERNS = {
    "running-header package": r"\\usepackage(?:\[[^]]*\])?\{fancyhdr\}",
    "copyright footer": r"(?i)copyright|\\copyright",
}


def bibliography_keys(text: str) -> list[str]:
    """Return BibTeX entry keys in declaration order."""

    return re.findall(r"(?m)^@\w+\{([^,\s]+),", text)


def citation_keys(text: str) -> set[str]:
    """Return citation keys used by ordinary LaTeX citation commands."""

    return {
        key.strip()
        for group in re.findall(r"\\cite\{([^}]+)\}", text)
        for key in group.split(",")
        if key.strip()
    }


def doi_values(text: str) -> list[str]:
    """Return normalized DOI fields while ignoring entries without a DOI."""

    return [
        value.strip().lower()
        for value in re.findall(r"(?i)\bdoi\s*=\s*\{([^}]+)\}", text)
    ]


def duplicate_values(values: list[str]) -> list[str]:
    """Return sorted values occurring more than once."""

    return sorted({value for value in values if values.count(value) > 1})


def audit(source_path: Path, bibliography_path: Path) -> dict[str, object]:
    """Validate the current paper's format, citation graph, and public wording."""

    source = source_path.read_text(encoding="utf-8")
    bibliography = bibliography_path.read_text(encoding="utf-8")
    errors: list[str] = []

    if REQUIRED_DOCUMENT_CLASS not in source:
        errors.append("current paper must remain A4, 10 pt, and two-column")
    if r"\pagestyle{plain}" not in source:
        errors.append("current paper must use the plain page-number-only style")
    if r"\appendix" not in source:
        errors.append("unrestricted current paper must contain its evidence appendices")
    for label, pattern in FORBIDDEN_SOURCE_PATTERNS.items():
        if re.search(pattern, source):
            errors.append(f"forbidden {label} detected")

    declared = bibliography_keys(bibliography)
    cited = citation_keys(source)
    if len(declared) < MIN_REFERENCES:
        errors.append(
            f"current paper requires at least {MIN_REFERENCES} references; found {len(declared)}"
        )
    duplicate_keys = duplicate_values(declared)
    if duplicate_keys:
        errors.append(f"duplicate bibliography keys: {', '.join(duplicate_keys)}")
    missing = sorted(cited - set(declared))
    uncited = sorted(set(declared) - cited)
    if missing:
        errors.append(f"citations missing from bibliography: {', '.join(missing)}")
    if uncited:
        errors.append(f"uncited bibliography entries: {', '.join(uncited)}")
    duplicate_dois = duplicate_values(doi_values(bibliography))
    if duplicate_dois:
        errors.append(f"duplicate DOI fields: {', '.join(duplicate_dois)}")

    included_figures = set(re.findall(r"\\includegraphics(?:\[[^]]*\])?\{([^}]+)\}", source))
    missing_figures = sorted(REQUIRED_FIGURES - included_figures)
    if missing_figures:
        errors.append(f"missing full-paper figures: {', '.join(missing_figures)}")

    result: dict[str, object] = {
        "valid": not errors,
        "reference_count": len(declared),
        "citation_count": len(cited),
        "full_figure_count": len(REQUIRED_FIGURES & included_figures),
        "format": "A4 10pt two-column; plain page-number-only footer",
        "errors": errors,
    }
    if errors:
        raise ValueError("; ".join(errors))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--bibliography", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.source, args.bibliography), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
