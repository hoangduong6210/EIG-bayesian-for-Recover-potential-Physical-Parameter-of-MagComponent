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
                 check_interval: int | None = None,
                 sampler_method: str = "stretch") -> PosteriorResult:
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
    if sampler_method not in {"stretch", "de_snooker"}:
        raise ValueError("unsupported posterior sampler method")
    if sampler_method == "de_snooker":
        return _sample_de_snooker(
            observations, spec, geometry, n_walkers=n_walkers, n_steps=n_steps,
            burn=burn, seed=seed, pool=pool, max_steps=max_steps,
            check_interval=check_interval,
        )
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


def _de_checkpoint_report(chain: np.ndarray, acceptance: np.ndarray,
                          tau: np.ndarray, log_probability: np.ndarray,
                          previous_tau: np.ndarray | None,
                          stable_changes: int) -> tuple[dict, int]:
    """Apply production diagnostics; two consecutive stable changes are required."""
    from .models import ACTIVE_NAMES

    tau = np.asarray(tau, dtype=float)
    report = diagnostic_report(chain, acceptance, tau)
    finite = float(np.mean(np.isfinite(log_probability)))
    positive_tau = bool(np.all(np.isfinite(tau)) and np.all(tau > 0))
    comparable = previous_tau is not None and positive_tau and bool(
        np.all(np.isfinite(previous_tau)) and np.all(previous_tau > 0)
    )
    relative = np.abs(tau - previous_tau) / tau if comparable else None
    stable = comparable and bool(np.all(relative <= 0.10))
    stable_changes = stable_changes + 1 if stable else 0
    report["thresholds"] = {
        "min_ess": 400.0, "min_steps_per_tau": 50.0,
        "acceptance_range": [0.05, 0.80],
        "maximum_relative_tau_change": 0.10,
        "required_consecutive_stable_changes": 2,
        "minimum_finite_log_probability_fraction": 1.0,
    }
    report["finite_log_probability_fraction"] = finite
    report["retained_steps"] = int(chain.shape[0])
    report["tau_stability"] = {
        "comparison_available": comparable,
        "relative_change": {name: float(relative[i]) if comparable else None
                            for i, name in enumerate(ACTIVE_NAMES)},
        "denominator": "current_checkpoint_tau",
        "consecutive_stable_changes": stable_changes,
        "eligible": stable_changes >= 2,
    }
    report["valid"] = bool(
        positive_tau and finite == 1.0
        and all(value is not None and value >= 400.0 for value in report["ess"].values())
        and all(value is not None and value >= 50.0 for value in report["steps_per_tau"].values())
        and 0.05 <= report["acceptance_fraction"] <= 0.80
        and stable_changes >= 2
    )
    return report, stable_changes


def _sample_de_snooker(observations: list[Observation], spec: DatasheetPrior,
                       geometry: Geometry | None, *, n_walkers: int,
                       n_steps: int, burn: int, seed: int, pool,
                       max_steps: int, check_interval: int) -> PosteriorResult:
    """Qualified move family with prospective production convergence checks."""
    import sys
    from types import SimpleNamespace

    import emcee

    from . import models as models_module
    from . import prior as prior_module
    from .sparse_transport import VectorizedPosterior

    if emcee.__version__ != "3.1.6":
        raise ValueError("DE+snooker requires the qualified emcee version 3.1.6")
    if (n_walkers, n_steps, burn, max_steps, check_interval) != (48, 20000, 80000, 800000, 20000):
        raise ValueError("DE+snooker requires 48 walkers, 80k warmup and 20k/800k/20k retained schedule")
    if pool is not None:
        raise ValueError("DE+snooker uses vectorized evaluation and does not accept a process pool")
    initial = prior_center_vector(spec) + np.random.default_rng(seed).normal(
        size=(n_walkers, 6)
    ) * np.array([0.05, 0.02, 0.02, 0.05, 0.05, 0.02])
    prepared = prepare_likelihood(observations, geometry)
    modules = SimpleNamespace(prior=prior_module, models=models_module,
                              inference=sys.modules[__name__])
    posterior = VectorizedPosterior(prepared, spec, modules)
    initial_parity = posterior.check_scalar_parity(initial)
    gamma = float(2.38 / np.sqrt(12))
    moves = [
        (emcee.moves.DEMove(sigma=1e-5, gamma0=gamma, nsplits=2, randomize_split=True), 0.8),
        (emcee.moves.DESnookerMove(gammas=1.7, randomize_split=True), 0.2),
    ]
    sampler = emcee.EnsembleSampler(n_walkers, 6, posterior, moves=moves, vectorize=True)
    sampler.random_state = np.random.RandomState(seed).get_state()
    state = sampler.run_mcmc(initial, burn, progress=False)
    sampler.reset()
    previous_tau = None
    stable_changes = 0
    history = []
    retained = 0
    while retained < max_steps:
        state = sampler.run_mcmc(state, min(check_interval, max_steps - retained), progress=False)
        retained = min(retained + check_interval, max_steps)
        chain = sampler.get_chain(flat=False)
        log_probability = sampler.get_log_prob(flat=True)
        try:
            tau = np.asarray(sampler.get_autocorr_time(tol=0), dtype=float)
        except Exception:
            tau = np.full(6, np.nan)
        report, stable_changes = _de_checkpoint_report(
            chain, sampler.acceptance_fraction, tau, log_probability,
            previous_tau, stable_changes,
        )
        history.append(report)
        previous_tau = tau.copy()
        if report["valid"] or retained == max_steps:
            break
        del chain, log_probability
    final_parity = posterior.check_scalar_parity(chain[-1])
    diagnostics = dict(report)
    diagnostics["adaptive_sampling"] = {
        "minimum_retained_steps": n_steps, "maximum_retained_steps": max_steps,
        "check_interval_steps": check_interval, "actual_retained_steps": retained,
        "extension_count": len(history) - 1,
        "stopped_reason": "converged" if report["valid"] else "maximum_steps",
        "checkpoint_history": history,
    }
    diagnostics["sampler"] = {
        "method": "de_snooker", "implementation": "emcee.EnsembleSampler",
        "version": emcee.__version__, "vectorize": True,
        "acceptance_window": "retained_only", "warmup_steps": burn,
        "move_parameters": {
            "DEMove": {"weight": 0.8, "sigma": 1e-5, "gamma0": gamma,
                       "nsplits": 2, "randomize_split": True},
            "DESnookerMove": {"weight": 0.2, "gammas": 1.7,
                              "nsplits": 4, "randomize_split": True},
        },
        "density_parity": {"initial": initial_parity, "final": final_parity},
        "qualification_scope": "SparseMix-2 evaluated eight independent ensembles per locked n3/n4 state. Production checks evaluate one adaptive ensemble per posterior state and do not establish the same cross-ensemble agreement.",
    }
    return PosteriorResult(chain, chain.reshape((-1, 6)), log_probability, diagnostics)
