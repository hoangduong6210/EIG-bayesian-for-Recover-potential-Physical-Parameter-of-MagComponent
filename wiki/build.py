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
    public_text_suffixes = {".md", ".json", ".toml", ".py", ".tex", ".bib"}
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
    for source_id in range(1, 10):
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
        "abstract_words": len(abstract.split()),
        "body_words": len(body.split()),
        "citation_count": len(cited),
        "bibliography_count": len(available),
        "evidence_release_id": release_id,
        "evidence_projection_sha256": projection_digest,
        "selection_overlap_sha256": overlap_digest,
        "scientific_job_count": len(jobs),
        "result_artifact_count": declared_artifacts,
        "acquisition_figure_sha256": figure_manifest["figure_sha256"],
        "repository_readme_sha256": sha256(landing_page),
        "wiki_inputs": {
            str(path.relative_to(WIKI_ROOT)): sha256(path)
            for path in sorted(
                [*texts, bibliography, template, MANIFEST_PATH],
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


def run_pandoc(source: Path, output: Path) -> None:
    canonical_parent = (WIKI_ROOT / load_manifest()["canonical_page"]).parent
    subprocess.run(
        [
            "pandoc",
            str(source),
            "--from=markdown+tex_math_dollars+raw_tex",
            "--to=latex",
            "--natbib",
            "--top-level-division=section",
            "--resource-path",
            os.pathsep.join((str(canonical_parent), str(WIKI_ROOT))),
            "--output",
            str(output),
        ],
        check=True,
    )


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
    args = parser.parse_args()
    try:
        if args.command == "check":
            print(json.dumps(check(), indent=2, sort_keys=True))
        elif args.command == "write-readme":
            print(write_repository_readme())
        elif args.command == "stage-wiki":
            print(stage_public_wiki(args.output))
        else:
            print(snapshot(args.output, args.document_kind, args.release_name))
    except (WikiError, OSError, subprocess.CalledProcessError) as exc:
        print(f"wiki build failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
