#!/usr/bin/env python3
"""Validate the living manuscript and create explicit paper snapshots."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path


WIKI_ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = WIKI_ROOT / "manuscript.toml"
REQUIRED_PAGES = {
    "README.md",
    "Home.md",
    "Project-Status.md",
    "Full-Manuscript.md",
    "Claims-and-Limits.md",
    "Reproduce-and-Audit.md",
    "References.md",
    "Authoring-and-Snapshots.md",
    "_Sidebar.md",
}
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
}


class WikiError(RuntimeError):
    """A fail-closed manuscript validation error."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest() -> dict:
    with MANIFEST_PATH.open("rb") as stream:
        manifest = tomllib.load(stream)
    if manifest.get("schema_version") != "magnetic-living-manuscript/1.0":
        raise WikiError("unsupported manuscript schema")
    return manifest


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
    missing_pages = sorted(name for name in REQUIRED_PAGES if not (WIKI_ROOT / name).is_file())
    if missing_pages:
        raise WikiError(f"missing wiki pages: {missing_pages}")

    canonical = WIKI_ROOT / manifest["canonical_page"]
    bibliography = WIKI_ROOT / manifest["bibliography"]
    template = WIKI_ROOT / manifest["template"]
    for path in (canonical, bibliography, template):
        if not path.is_file():
            raise WikiError(f"missing declared manuscript input: {path.relative_to(WIKI_ROOT)}")

    texts: dict[Path, str] = {}
    for path in sorted(WIKI_ROOT.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        texts[path] = text
        for label, pattern in BANNED_PUBLIC_PATTERNS.items():
            if pattern.search(text):
                raise WikiError(f"{label} found in {path.name}")
        for target in local_markdown_targets(text):
            resolved = (path.parent / target).resolve()
            if WIKI_ROOT.resolve() not in (resolved, *resolved.parents):
                raise WikiError(f"link escapes wiki root in {path.name}: {target}")
            if not resolved.exists():
                raise WikiError(f"broken local link in {path.name}: {target}")

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
    if not re.fullmatch(r"\d{8}T\d{6}Z_[0-9a-f]{12}", release_id):
        raise WikiError("invalid evidence release ID")
    if not re.fullmatch(r"[0-9a-f]{64}", release_digest):
        raise WikiError("invalid evidence manifest SHA-256")
    for page in ("Full-Manuscript.md", "Project-Status.md"):
        if release_id not in texts[WIKI_ROOT / page] or release_digest not in texts[WIKI_ROOT / page]:
            raise WikiError(f"{page} is not bound to the declared evidence release")

    pandoc = shutil.which("pandoc")
    latexmk = shutil.which("latexmk")
    if pandoc is None or latexmk is None:
        raise WikiError("pandoc and latexmk are required for snapshot capability")
    version = subprocess.run(
        [pandoc, "--version"], check=True, capture_output=True, text=True
    ).stdout.splitlines()[0].removeprefix("pandoc ")
    if version != manifest["pandoc_version"]:
        raise WikiError(f"pandoc version mismatch: expected {manifest['pandoc_version']}, got {version}")

    return {
        "abstract_words": len(abstract.split()),
        "body_words": len(body.split()),
        "citation_count": len(cited),
        "bibliography_count": len(available),
        "evidence_release_id": release_id,
        "wiki_inputs": {
            str(path.relative_to(WIKI_ROOT)): sha256(path)
            for path in sorted(
                [*texts, bibliography, template, MANIFEST_PATH],
                key=lambda item: str(item),
            )
        },
    }


def run_pandoc(source: Path, output: Path) -> None:
    subprocess.run(
        [
            "pandoc",
            str(source),
            "--from=markdown+tex_math_dollars+raw_tex",
            "--to=latex",
            "--natbib",
            "--top-level-division=section",
            "--resource-path",
            str(WIKI_ROOT),
            "--output",
            str(output),
        ],
        check=True,
    )


def snapshot(output: Path) -> Path:
    report = check()
    if output.exists():
        raise WikiError(f"snapshot output already exists: {output}")
    output.mkdir(parents=True)
    try:
        canonical = WIKI_ROOT / load_manifest()["canonical_page"]
        abstract, body = split_manuscript(canonical.read_text(encoding="utf-8"))
        abstract_md = output / "abstract.md"
        body_md = output / "body.md"
        abstract_md.write_text(abstract, encoding="utf-8")
        body_md.write_text(body, encoding="utf-8")
        run_pandoc(abstract_md, output / "abstract.tex")
        run_pandoc(body_md, output / "body.tex")
        shutil.copy2(WIKI_ROOT / "paper-template.tex", output / "main.tex")
        shutil.copy2(WIKI_ROOT / "bibliography" / "references.bib", output / "references.bib")
        shutil.copytree(WIKI_ROOT / "assets", output / "assets")
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
            path.name: sha256(path)
            for path in (output / "main.tex", output / "body.tex", output / "abstract.tex", pdf)
        }
        snapshot_record = {
            "schema_version": "magnetic-paper-snapshot/1.0",
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check", help="validate wiki without generating paper artifacts")
    snapshot_parser = subparsers.add_parser(
        "snapshot", help="explicitly render a staged two-column paper snapshot"
    )
    snapshot_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "check":
            print(json.dumps(check(), indent=2, sort_keys=True))
        else:
            print(snapshot(args.output))
    except (WikiError, OSError, subprocess.CalledProcessError) as exc:
        print(f"wiki build failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
