"""The MM-3 figure must remain bound to the admitted aggregate."""

import hashlib
import json
from pathlib import Path


WIKI = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_mm3_figure_manifest_matches_source_and_image():
    manifest = json.loads((WIKI / "assets/model-mismatch-v3.json").read_text())
    source = WIKI.parent / manifest["source"]
    figure = WIKI / "assets" / manifest["figure"]
    assert manifest["schema_version"] == "magcore-model-mismatch-figure/1.0"
    assert manifest["campaign_id"] == "MM-3"
    assert manifest["source_sha256"] == sha256(source)
    assert manifest["figure_sha256"] == sha256(figure)
    assert manifest["difference_definition"] == "comparator_minus_eig"
