#!/usr/bin/env python3
"""Map immutable SLURM task indices to MM-1 scenario/seed pairs."""

from __future__ import annotations

import argparse
import json
import shlex
from pathlib import Path

from magcore_calib.model_mismatch import load_model_mismatch_plan


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("plan", "task"))
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--task-id", type=int)
    parser.add_argument("--format", choices=("json", "shell"), default="json")
    args = parser.parse_args()
    plan = load_model_mismatch_plan(args.config)
    if args.command == "plan":
        values = plan.as_dict()
        values["task_count"] = plan.task_count
    else:
        if args.task_id is None:
            parser.error("task requires --task-id")
        scenario, seed = plan.task(args.task_id)
        values = {
            "scenario": scenario.name, "seed": seed,
            "task_id": f"{scenario.name}_seed{seed}",
        }
    if args.format == "shell":
        if any(isinstance(value, (dict, list)) for value in values.values()):
            parser.error("shell format is available only for one task")
        print("\n".join(
            f"{key.upper()}={shlex.quote(str(value))}"
            for key, value in values.items()
        ))
    else:
        print(json.dumps(values, sort_keys=True))


if __name__ == "__main__":
    main()
