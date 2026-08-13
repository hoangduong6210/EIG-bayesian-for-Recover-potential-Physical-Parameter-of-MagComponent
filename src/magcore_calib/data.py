"""Isothermal candidate libraries, observations, and CSV ingestion."""

from __future__ import annotations

import csv
import os
from collections.abc import Iterable
from pathlib import Path

import numpy as np

from .forward import predict_one
from .models import Channel, DesignPoint, Geometry, MagneticParams, Observation

NOISE_FRACTION = {
    Channel.PCV: 0.03,
    Channel.MU_REAL: 0.02,
    Channel.MU_IMAG: 0.05,
    Channel.LM: 0.01,
}


def material_database_root() -> Path:
    """Resolve the staged upstream dataset for this standalone repository."""
    configured = os.environ.get("MAGCORE_DATA_ROOT")
    if configured:
        root = Path(configured).resolve()
        if not root.is_dir():
            raise FileNotFoundError(f"configured material database not found: {root}")
        return root
    repository_root = Path(__file__).resolve().parents[2]
    root = repository_root / "data" / "external" / "materialdatabase" / "data"
    if not root.is_dir():
        raise FileNotFoundError(
            "staged material database not found; set MAGCORE_DATA_ROOT or stage it at "
            f"{root}"
        )
    return root


def complex_mu_path(material: str, source: str) -> Path:
    path = material_database_root() / "complex_permeability" / source / f"{material}.csv"
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def pcv_paths(material: str) -> list[Path]:
    base = material_database_root() / "datasheet_curves" / material
    paths = [base / "p_v_over_f_at_b_T.csv", base / "p_v_over_b_at_f_T.csv"]
    found = [path for path in paths if path.is_file()]
    if not found:
        raise FileNotFoundError(f"no core-loss curves for {material} under {base}")
    return found


def default_library(temperature_c: float = 25.0) -> list[DesignPoint]:
    points: list[DesignPoint] = []
    for f_hz in (1e4, 3e4, 1e5, 3e5, 5e5, 1e6, 2e6, 3e6):
        points.extend([
            DesignPoint(Channel.MU_REAL, f_hz, 0.0, temperature_c),
            DesignPoint(Channel.MU_IMAG, f_hz, 0.0, temperature_c),
        ])
    for f_hz in (3e4, 5e4, 1e5, 2e5, 3e5, 5e5):
        for b_pk_t in (0.05, 0.10, 0.20):
            points.append(DesignPoint(Channel.PCV, f_hz, b_pk_t, temperature_c))
    for f_hz in (1e4, 1e5, 1e6):
        points.append(DesignPoint(Channel.LM, f_hz, 0.0, temperature_c))
    return points


def observation_for(params: MagneticParams, design: DesignPoint, rng: np.random.Generator,
                    geometry: Geometry | None = None) -> Observation:
    mean = predict_one(params, design, geometry)
    sigma = max(1e-9, NOISE_FRACTION[design.channel] * abs(mean))
    return Observation(design, float(mean + rng.normal(0.0, sigma)), sigma)


def common_random_outcomes(params: MagneticParams, library: Iterable[DesignPoint], *, seed: int,
                           geometry: Geometry | None = None) -> dict[str, Observation]:
    """One immutable outcome per candidate, shared by all acquisition policies."""
    rng = np.random.default_rng(seed)
    return {d.key(): observation_for(params, d, rng, geometry) for d in library}


def load_material_csv(path: str, *, target_temperature_c: float = 25.0,
                      tolerance_c: float = 0.5, noise_fraction: float = 0.03,
                      channels: tuple[Channel, ...] = (Channel.MU_REAL, Channel.MU_IMAG),
                      b_max_t: float | None = None,
                      normalize_flux_above_1_as_millitesla: bool = False,
                      report: dict | None = None) -> list[Observation]:
    """Load unified ferrite CSV columns without mixing temperature cohorts."""
    observations: list[Observation] = []
    stats = {
        "path": str(Path(path).resolve()), "rows_read": 0, "rows_in_temperature_cohort": 0,
        "rows_flux_normalized_millitesla_to_tesla": 0, "observations_emitted": 0,
        "flux_normalization_rule": (
            "abs(b)>1 interpreted as mT and multiplied by 1e-3"
            if normalize_flux_above_1_as_millitesla else "none"
        ),
    }
    with open(path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            stats["rows_read"] += 1
            try:
                temperature = float(row["T"])
                frequency = float(row["f"])
                flux = float(row.get("b", 0.0) or 0.0)
            except (KeyError, TypeError, ValueError):
                continue
            if abs(temperature - target_temperature_c) > tolerance_c:
                continue
            stats["rows_in_temperature_cohort"] += 1
            if normalize_flux_above_1_as_millitesla and abs(flux) > 1.0:
                flux *= 1.0e-3
                stats["rows_flux_normalized_millitesla_to_tesla"] += 1
            if b_max_t is not None and flux > b_max_t:
                continue
            values = {
                Channel.MU_REAL: row.get("mu_real"),
                Channel.MU_IMAG: row.get("mu_imag"),
                Channel.PCV: row.get("p_v"),
            }
            for channel in channels:
                raw = values.get(channel)
                try:
                    value = float(raw) if raw is not None else None
                except (TypeError, ValueError):
                    continue
                if value is None or not np.isfinite(value):
                    continue
                design = DesignPoint(channel, frequency, flux, temperature)
                observations.append(Observation(
                    design, value, max(1e-9, noise_fraction * abs(value))
                ))
                stats["observations_emitted"] += 1
    if report is not None:
        report.update(stats)
    if not observations:
        raise ValueError(
            f"no usable observations in {target_temperature_c:g}+/-{tolerance_c:g} C cohort"
        )
    return observations
