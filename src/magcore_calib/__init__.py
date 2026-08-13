"""Magnetic-core Bayesian calibration research pipeline."""

__version__ = "1.0.0"

from .models import (
    ACTIVE_NAMES,
    Channel,
    DesignPoint,
    Geometry,
    MagneticParams,
    Observation,
)
from .prior import DatasheetPrior, log_prior_active, prior_center_vector

__all__ = [
    "ACTIVE_NAMES",
    "Channel",
    "DatasheetPrior",
    "DesignPoint",
    "Geometry",
    "MagneticParams",
    "Observation",
    "log_prior_active",
    "prior_center_vector",
]
