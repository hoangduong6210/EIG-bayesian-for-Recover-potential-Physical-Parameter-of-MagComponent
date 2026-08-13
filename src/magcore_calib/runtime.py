"""Compute policy guards and reproducible runtime metadata."""

from __future__ import annotations

import os
from contextlib import contextmanager
from multiprocessing import Pool


def require_slurm() -> None:
    if not os.environ.get("SLURM_JOB_ID") or not os.environ.get("SLURM_JOB_NODELIST"):
        raise RuntimeError("heavy magnetic calibration must be submitted through SLURM")


def slurm_metadata() -> dict[str, str | None]:
    return {
        "job_id": os.environ.get("SLURM_JOB_ID"),
        "array_job_id": os.environ.get("SLURM_ARRAY_JOB_ID"),
        "array_task_id": os.environ.get("SLURM_ARRAY_TASK_ID"),
        "node_list": os.environ.get("SLURM_JOB_NODELIST"),
        "partition": os.environ.get("SLURM_JOB_PARTITION"),
    }


@contextmanager
def sampling_pool(workers: int):
    """Bound worker lifetime to one heavy experiment process."""
    if workers <= 1:
        yield None
        return
    pool = Pool(processes=workers)
    try:
        yield pool
    finally:
        pool.close()
        pool.join()
