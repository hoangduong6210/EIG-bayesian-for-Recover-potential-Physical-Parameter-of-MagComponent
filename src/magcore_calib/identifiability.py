"""Fisher-information diagnostics in the canonical six-dimensional space."""

from __future__ import annotations

import numpy as np

from .forward import predict
from .models import ACTIVE_NAMES, Geometry, MagneticParams, Observation


def jacobian(params: MagneticParams, observations: list[Observation],
             geometry: Geometry | None = None, step: float = 1e-5) -> np.ndarray:
    center = params.to_active()
    matrix = np.empty((len(observations), 6))
    designs = [o.design for o in observations]
    for index in range(6):
        plus, minus = center.copy(), center.copy()
        plus[index] += step
        minus[index] -= step
        matrix[:, index] = (
            predict(MagneticParams.from_active(plus), designs, geometry)
            - predict(MagneticParams.from_active(minus), designs, geometry)
        ) / (2.0 * step)
    return matrix


def fisher_spectrum(params: MagneticParams, observations: list[Observation],
                    geometry: Geometry | None = None) -> dict:
    jac = jacobian(params, observations, geometry)
    sigma = np.array([o.sigma for o in observations])
    fisher = (jac / sigma[:, None]).T @ (jac / sigma[:, None])
    fisher = (fisher + fisher.T) / 2.0
    values, vectors = np.linalg.eigh(fisher)
    values = np.clip(values, 0.0, None)
    positive = values[values > np.finfo(float).eps * max(values.max(), 1.0)]
    condition = float(values.max() / positive.min()) if len(positive) else None
    return {
        "parameter_names": list(ACTIVE_NAMES),
        "eigenvalues_ascending": values.tolist(),
        "eigenvectors_columns": vectors.tolist(),
        "condition_number_resolved_subspace": condition,
        "rank": int(np.linalg.matrix_rank(fisher)),
        "n_observations": len(observations),
    }
