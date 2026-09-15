"""Evidence binding and reproducible exports for the journal summary figure."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "journal_mismatch_figure", ROOT / "scripts" / "plot_model_mismatch_v3.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
AGGREGATE = ROOT / "results/diagnostics/model_mismatch/MM-3/20260913T065150Z_a75d737c9d50/aggregate.json"


def test_mismatch_figure_binds_intervals_and_vector_output(tmp_path):
    output = tmp_path / "figure.png"
    manifest_path = tmp_path / "figure.json"
    result = MODULE.render(AGGREGATE, output, manifest_path)
    assert "95% paired-bootstrap" in result["interval"]
    assert "not multiplicity-adjusted" in result["interval"]
    assert result["source_sha256"] == hashlib.sha256(AGGREGATE.read_bytes()).hexdigest()
    assert result["figure_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert result["vector_figure_sha256"] == hashlib.sha256(output.with_suffix(".pdf").read_bytes()).hexdigest()
    assert json.loads(manifest_path.read_text()) == result
    assert MODULE.render(AGGREGATE, output, manifest_path) == result


@pytest.mark.parametrize("field,value", [("campaign_id", "MM-2"), ("source_result_count", 119)])
def test_mismatch_figure_rejects_other_or_incomplete_campaign(tmp_path, field, value):
    record = json.loads(AGGREGATE.read_text())
    record[field] = value
    source = tmp_path / "aggregate.json"
    source.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="admitted MM-3"):
        MODULE.render(source, tmp_path / "figure.png", tmp_path / "figure.json")
