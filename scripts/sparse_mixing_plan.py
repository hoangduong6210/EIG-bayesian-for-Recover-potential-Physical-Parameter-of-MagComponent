#!/usr/bin/env python3
"""Inspect the immutable SparseMix-1 task registry."""

from __future__ import annotations

import argparse
import json
import shlex
from pathlib import Path

from magcore_calib.sparse_mixing import load_sparse_mixing_plan


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("plan", "task"))
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--task-id", type=int)
    parser.add_argument("--format", choices=("json", "shell"), default="json")
    args = parser.parse_args()
    plan = load_sparse_mixing_plan(args.config)
    if args.command == "plan":
        payload = {
            "protocol_id": plan.protocol_id,
            "config_sha256": plan.config_sha256,
            "task_count": plan.task_count,
            "tasks": [task.task_id for task in plan.tasks()],
        }
    else:
        if args.task_id is None:
            parser.error("task requires --task-id")
        task = plan.task(args.task_id)
        payload = {
            "TASK_ID": task.task_id,
            "TARGET_ID": task.target.target_id,
            "INITIALIZATION": task.initialization,
            "REPLICATE": task.replicate,
            "SEED": task.seed,
        }
    if args.format == "json":
        print(json.dumps(payload, sort_keys=True))
    else:
        for key, value in payload.items():
            print(f"{key}={shlex.quote(str(value))}")


if __name__ == "__main__":
    main()
