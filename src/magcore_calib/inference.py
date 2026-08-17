"""Six-dimensional posterior inference with prior-center initialization."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .diagnostics import diagnostic_report
from .forward import MU0
from .models import Channel, Geometry, MagneticParams, Observation
from .prior import DatasheetPrior, log_prior_active, prior_center_vector


@dataclass(frozen=True)
class PreparedLikelihood:
    channel: np.ndarray
    frequency_hz: np.ndarray
    flux_t: np.ndarray
    values: np.ndarray
    sigma: np.ndarray
    geometry: Geometry | None


def prepare_likelihood(observations: list[Observation],
                       geometry: Geometry | None = None) -> PreparedLikelihood:
    if not observations:
        raise ValueError("posterior likelihood requires at least one observation")
    temperatures = np.array([o.design.temperature_c for o in observations])
    if np.ptp(temperatures) > 2.0:
        raise ValueError("likelihood cannot mix temperature cohorts")
    channel_codes = {channel: index for index, channel in enumerate(Channel)}
    return PreparedLikelihood(
        channel=np.array([channel_codes[o.design.channel] for o in observations], dtype=np.int8),
        frequency_hz=np.array([o.design.f_hz for o in observations]),
        flux_t=np.array([o.design.b_pk_t for o in observations]),
        values=np.array([o.value for o in observations]),
        sigma=np.array([o.sigma for o in observations]),
        geometry=geometry,
    )


def log_likelihood_prepared(x: np.ndarray, data: PreparedLikelihood) -> float:
    params = MagneticParams.from_active(np.asarray(x))
    prediction = np.empty_like(data.values)
    channel_codes = {channel: index for index, channel in enumerate(Channel)}
    pcv = data.channel == channel_codes[Channel.PCV]
    prediction[pcv] = (params.k * data.frequency_hz[pcv] ** params.alpha
                       * data.flux_t[pcv] ** params.beta)
    permeability = ~pcv
    if np.any(permeability):
        frequency = data.frequency_hz[permeability]
        exponent = 1.0 - params.alpha_cc
        magnitude = (frequency / params.f_rel_hz) ** exponent
        angle = exponent * math.pi / 2.0
        den_real = 1.0 + magnitude * math.cos(angle)
        den_imag = magnitude * math.sin(angle)
        denominator = den_real ** 2 + den_imag ** 2
        mu_real = 1.0 + (params.mu_s - 1.0) * den_real / denominator
        mu_imag = (params.mu_s - 1.0) * den_imag / denominator
        subchannels = data.channel[permeability]
        values = np.empty_like(frequency)
        values[subchannels == channel_codes[Channel.MU_REAL]] = mu_real[subchannels == channel_codes[Channel.MU_REAL]]
        values[subchannels == channel_codes[Channel.MU_IMAG]] = mu_imag[subchannels == channel_codes[Channel.MU_IMAG]]
        lm = subchannels == channel_codes[Channel.LM]
        if np.any(lm):
            if data.geometry is None:
                raise ValueError("Geometry is required for the Lm channel")
            scale = MU0 * data.geometry.turns ** 2 * data.geometry.area_m2 / data.geometry.path_m
            values[lm] = mu_real[lm] * scale
        prediction[permeability] = values
    residual = (data.values - prediction) / data.sigma
    return float(np.sum(-0.5 * residual ** 2 - np.log(data.sigma) - 0.5 * math.log(2.0 * math.pi)))


def log_likelihood_active(x: np.ndarray, observations: list[Observation],
                          geometry: Geometry | None = None) -> float:
    return log_likelihood_prepared(x, prepare_likelihood(observations, geometry))


def log_posterior_active(x: np.ndarray, observations: list[Observation],
                         spec: DatasheetPrior, geometry: Geometry | None = None) -> float:
    prior = log_prior_active(x, spec)
    if not math.isfinite(prior):
        return -math.inf
    return prior + log_likelihood_active(x, observations, geometry)


def _log_posterior_prepared(x: np.ndarray, data: PreparedLikelihood,
                            spec: DatasheetPrior) -> float:
    prior = log_prior_active(x, spec)
    return -math.inf if not math.isfinite(prior) else prior + log_likelihood_prepared(x, data)


@dataclass
class PosteriorResult:
    chain: np.ndarray
    samples: np.ndarray
    log_probabilities: np.ndarray
    diagnostics: dict


def sample_emcee(observations: list[Observation], spec: DatasheetPrior,
                 geometry: Geometry | None = None, *, n_walkers: int = 48,
                 n_steps: int = 5000, burn: int = 1000, seed: int = 0,
                 pool=None, max_steps: int | None = None,
                 check_interval: int | None = None) -> PosteriorResult:
    """Heavy sampler. Entrypoints, not this reusable function, enforce SLURM."""
    import emcee

    if n_walkers < 12:
        raise ValueError("six-dimensional affine-invariant sampling needs at least 12 walkers")
    max_steps = n_steps if max_steps is None else max_steps
    check_interval = n_steps if check_interval is None else check_interval
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 1
           for value in (n_steps, max_steps, check_interval)):
        raise ValueError("sampler step counts must be positive integers")
    if isinstance(burn, bool) or not isinstance(burn, int) or burn < 0:
        raise ValueError("sampler burn must be a nonnegative integer")
    if max_steps < n_steps:
        raise ValueError("adaptive sampler max_steps cannot be below n_steps")
    rng = np.random.default_rng(seed)
    center = prior_center_vector(spec)
    scales = np.array([0.05, 0.02, 0.02, 0.05, 0.05, 0.02])
    initial = center + rng.normal(size=(n_walkers, 6)) * scales
    prepared = prepare_likelihood(observations, geometry)
    sampler = emcee.EnsembleSampler(
        n_walkers, 6, _log_posterior_prepared, args=(prepared, spec), pool=pool,
    )
    # emcee maintains its own legacy RandomState for proposals.  Seeding only
    # NumPy's Generator above makes initialization repeatable but leaves the
    # Markov transition sequence nondeterministic across SLURM runs.
    proposal_rng = np.random.RandomState(seed)
    sampler.random_state = proposal_rng.get_state()
    sampler.run_mcmc(initial, burn + n_steps, progress=False)

    def current_result() -> tuple[np.ndarray, np.ndarray, dict]:
        chain_now = sampler.get_chain(discard=burn, flat=False)
        log_prob_now = sampler.get_log_prob(discard=burn, flat=True)
        try:
            tau_now = np.asarray(
                sampler.get_autocorr_time(discard=burn, tol=0), dtype=float
            )
        except Exception:
            tau_now = np.full(6, np.nan)
        report = diagnostic_report(
            chain_now, sampler.acceptance_fraction, tau_now
        )
        report["finite_log_probability_fraction"] = float(
            np.mean(np.isfinite(log_prob_now))
        )
        report["valid"] = bool(
            report["valid"]
            and report["finite_log_probability_fraction"] == 1.0
        )
        return chain_now, log_prob_now, report

    chain, log_prob, diagnostics = current_result()
    extension_count = 0
    while not diagnostics["valid"] and chain.shape[0] < max_steps:
        extension = min(check_interval, max_steps - chain.shape[0])
        sampler.run_mcmc(None, extension, progress=False)
        extension_count += 1
        chain, log_prob, diagnostics = current_result()
    diagnostics["adaptive_sampling"] = {
        "minimum_retained_steps": n_steps,
        "maximum_retained_steps": max_steps,
        "check_interval_steps": check_interval,
        "actual_retained_steps": int(chain.shape[0]),
        "extension_count": extension_count,
        "stopped_reason": "converged" if diagnostics["valid"] else "maximum_steps",
    }
    flat = chain.reshape((-1, 6))
    return PosteriorResult(chain, flat, log_prob, diagnostics)
