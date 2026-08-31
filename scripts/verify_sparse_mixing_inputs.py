#!/usr/bin/env python3
"""Verify every copied SparseMix-1 input and the extracted MM-2 source tree."""

from __future__ import annotations

import argparse
import hashlib
import tarfile
from pathlib import Path

from magcore_calib.sparse_mixing import load_sparse_mixing_plan, sha256_file


def _digest_stream(stream) -> str:
    digest = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(block)
    return digest.hexdigest()


def verify_inputs(config: Path, root: Path) -> None:
    plan = load_sparse_mixing_plan(config)
    parent = plan.raw["parent"]
    declared = {
        "mm2_source.tar.gz": parent["source_archive_sha256"],
        "mm2_config.toml": parent["config_sha256"],
        "mm2_rejection.json": parent["rejection_sha256"],
        "mm2_failed_marker.json": parent["failed_marker_sha256"],
        "mm2_closeout.json": parent["closeout_sha256"],
    }
    for relative, expected in declared.items():
        path = root / relative
        if not path.is_file() or sha256_file(path) != expected:
            raise ValueError(f"SparseMix-1 locked input digest mismatch: {relative}")

    source = root / "mm2_source"
    if not source.is_dir():
        raise FileNotFoundError("SparseMix-1 extracted MM-2 source is missing")
    archive_entries: dict[str, str] = {}
    with tarfile.open(root / "mm2_source.tar.gz", "r:gz") as archive:
        for member in archive.getmembers():
            if member.isdir():
                continue
            if not member.isfile():
                raise ValueError("SparseMix-1 source archive contains a non-file entry")
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError("SparseMix-1 source archive member is unreadable")
            archive_entries[member.name] = _digest_stream(stream)
    source_entries = {
        path.relative_to(source).as_posix(): sha256_file(path)
        for path in source.rglob("*") if path.is_file()
    }
    if archive_entries != source_entries:
        raise ValueError("extracted MM-2 source differs from the locked archive")
    if sha256_file(source / "configs/model_mismatch_v2.toml") \
            != parent["config_sha256"]:
        raise ValueError("MM-2 source configuration differs from the locked input")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--input-root", required=True, type=Path)
    args = parser.parse_args()
    verify_inputs(args.config.resolve(), args.input_root.resolve())


if __name__ == "__main__":
    main()
