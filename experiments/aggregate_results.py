#!/usr/bin/env python3
"""Lightweight aggregation of schema-valid, convergence-valid run results."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from magcore_calib.results import SCHEMA_VERSION, validate_result
from magcore_calib.runtime import require_slurm


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    require_slurm()
    accepted, rejected = [], []
    for path in sorted(Path(args.run_dir).glob("results/**/*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            validate_result(record)
            validity = record.get("validity", {})
            convergence_values = [value for key, value in validity.items() if "convergence_valid" in key]
            if convergence_values and not all(convergence_values):
                raise ValueError("convergence gate failed")
            accepted.append({"path": str(path), "run_id": record["run_id"]})
        except (ValueError, json.JSONDecodeError) as error:
            rejected.append({"path": str(path), "reason": str(error)})
    manifest = {"schema_version": SCHEMA_VERSION, "accepted": accepted, "rejected": rejected}
    destination = Path(args.out)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
