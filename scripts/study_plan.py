#!/usr/bin/env python3
"""Emit deterministic study-plan task mappings for SLURM array jobs."""

from __future__ import annotations

import argparse
import json
import shlex
from pathlib import Path
from typing import Any

from magcore_calib.study_plan import load_study_plan


def _shell(values: dict[str, Any]) -> str:
    return "\n".join(
        f"{key.upper()}={shlex.quote(str(value))}" for key, value in values.items()
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("plan", "state", "grid", "reference", "audit", "downstream", "acquisition"))
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--task-id", type=int)
    parser.add_argument("--format", choices=("json", "shell"), default="json")
    args = parser.parse_args()
    plan = load_study_plan(args.config)

    if args.command == "plan":
        values = plan.as_dict()
    else:
        if args.task_id is None:
            parser.error(f"{args.command} requires --task-id")
        if args.command == "state":
            values = plan.validation_state_task(args.task_id).as_dict()
        elif args.command == "grid":
            values = plan.validation_grid_task(args.task_id).as_dict()
        elif args.command == "reference":
            values = plan.validation_reference_task(args.task_id).as_dict()
        elif args.command == "audit":
            values = plan.validation_audit_task(args.task_id).as_dict()
        elif args.command == "downstream":
            values = plan.downstream_validation_task(args.task_id).as_dict()
        else:
            seed = plan.acquisition_seed(args.task_id)
            values = {"seed": seed, "task_id": f"seed{seed}"}

    if args.format == "shell":
        if any(isinstance(value, (dict, list)) for value in values.values()):
            parser.error("shell output is available only for individual task mappings")
        print(_shell(values))
    else:
        print(json.dumps(values, sort_keys=True))


if __name__ == "__main__":
    main()
