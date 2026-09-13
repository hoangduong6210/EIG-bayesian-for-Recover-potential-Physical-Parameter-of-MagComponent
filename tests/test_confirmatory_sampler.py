"""Deterministic DE production checks using synthetic arrays and sampler doubles."""

from __future__ import annotations

import emcee
import numpy as np
import pytest

from magcore_calib import inference
from magcore_calib.models import Channel, DesignPoint, Observation
from magcore_calib.prior import DatasheetPrior, prior_center_vector


def _report(tau=100.0, previous=100.0, changes=1, *, acceptance=0.1,
            steps=20000, log_probability=None):
    chain = np.broadcast_to(np.zeros(6), (steps, 48, 6))
    return inference._de_checkpoint_report(
        chain, np.array([acceptance]), np.full(6, tau),
        np.zeros(10) if log_probability is None else log_probability,
        None if previous is None else np.full(6, previous), changes,
    )


def test_first_checkpoint_and_single_stable_change_cannot_stop():
    first, changes = _report(previous=None, changes=0)
    assert not first["valid"] and changes == 0
    second, changes = _report(changes=changes)
    assert not second["valid"] and changes == 1
    third, changes = _report(changes=changes)
    assert third["valid"] and changes == 2


def test_relative_tau_uses_current_denominator_and_resets_streak():
    passing, count = _report(tau=110, previous=100)
    assert passing["valid"] and count == 2
    failing, count = _report(tau=100, previous=111, changes=count)
    assert not failing["valid"] and count == 0
    assert failing["tau_stability"]["relative_change"]["ln_k"] == 0.11


@pytest.mark.parametrize("tau", [np.nan, np.inf, -1, 0])
def test_invalid_autocorrelation_never_admits(tau):
    with np.errstate(divide="ignore", invalid="ignore"):
        report, count = _report(tau=tau, changes=5)
    assert not report["valid"] and count == 0


@pytest.mark.parametrize("acceptance,expected", [(0.049, False), (0.05, True),
                                                  (0.1, True), (0.8, True), (0.801, False)])
def test_qualified_acceptance_sanity_replaces_legacy_range(acceptance, expected):
    report, _ = _report(acceptance=acceptance)
    assert report["valid"] is expected


def test_short_tau_ratio_and_nonfinite_probability_fail():
    report, _ = _report(tau=401, previous=401)
    assert not report["valid"]
    report, _ = _report(log_probability=np.array([0.0, -np.inf]))
    assert not report["valid"]


class SamplerDouble:
    instances = []

    def __init__(self, nwalkers, ndim, density, **kwargs):
        self.nwalkers, self.ndim = nwalkers, ndim
        self.density, self.kwargs = density, kwargs
        self.steps = 0
        self.calls = []
        self.reset_count = 0
        self.acceptance_fraction = np.full(nwalkers, 0.1)
        type(self).instances.append(self)

    def run_mcmc(self, initial, steps, progress=False):
        self.calls.append(steps)
        self.steps += steps
        return object()

    def reset(self):
        self.steps = 0
        self.reset_count += 1

    def get_chain(self, discard=0, flat=False):
        result = np.broadcast_to(prior_center_vector(DatasheetPrior()),
                                 (self.steps - discard, self.nwalkers, 6))
        return result.reshape(-1, 6) if flat else result

    def get_log_prob(self, discard=0, flat=False):
        shape = ((self.steps - discard) * self.nwalkers,) if flat else (self.steps - discard, self.nwalkers)
        return np.broadcast_to(np.array(0.0), shape)

    def get_autocorr_time(self, **kwargs):
        return np.full(6, 100.0)


def _observations():
    return [Observation(DesignPoint(Channel.PCV, 1e5, 0.1), 1.0, 0.1)]


def _de_arguments():
    return dict(n_walkers=48, n_steps=20000, burn=80000, max_steps=800000,
                check_interval=20000, sampler_method="de_snooker", seed=9317)


def test_mocked_production_run_resets_burn_and_stops_at_third_checkpoint(monkeypatch):
    SamplerDouble.instances.clear()
    monkeypatch.setattr(emcee, "EnsembleSampler", SamplerDouble)
    monkeypatch.setattr(emcee, "__version__", "3.1.6")
    result = inference.sample_emcee(_observations(), DatasheetPrior(), **_de_arguments())
    sampler = SamplerDouble.instances[-1]
    assert sampler.calls == [80000, 20000, 20000, 20000]
    assert sampler.reset_count == 1
    assert result.chain.shape == (60000, 48, 6)
    report = result.diagnostics
    assert report["valid"]
    assert report["adaptive_sampling"]["extension_count"] == 2
    assert len(report["adaptive_sampling"]["checkpoint_history"]) == 3
    assert report["sampler"]["acceptance_window"] == "retained_only"
    assert report["sampler"]["version"] == "3.1.6"
    assert sampler.kwargs["vectorize"] is True
    de, snooker = sampler.kwargs["moves"]
    assert de[1] == 0.8 and snooker[1] == 0.2
    assert de[0].sigma == 1e-5 and de[0].gamma0 == 2.38 / np.sqrt(12)
    assert snooker[0].gammas == 1.7
    assert de[0].nsplits == 2 and snooker[0].nsplits == 4


def test_legacy_default_path_has_no_reset_or_new_diagnostics(monkeypatch):
    monkeypatch.setattr(emcee, "EnsembleSampler", SamplerDouble)
    for options in ({}, {"sampler_method": "stretch"}):
        result = inference.sample_emcee(_observations(), DatasheetPrior(),
                                        n_steps=30, burn=10, **options)
        sampler = SamplerDouble.instances[-1]
        assert sampler.calls == [40]
        assert sampler.reset_count == 0
        assert sampler.density is inference._log_posterior_prepared
        assert "vectorize" not in sampler.kwargs
        assert "sampler" not in result.diagnostics
        assert "tau_stability" not in result.diagnostics


@pytest.mark.parametrize("key,value", [("n_steps", 10000), ("burn", 4000),
                                       ("max_steps", 320000), ("check_interval", 40000),
                                       ("n_walkers", 24), ("pool", object())])
def test_de_contract_rejected_before_observation_load(monkeypatch, key, value):
    monkeypatch.setattr(emcee, "__version__", "3.1.6")
    monkeypatch.setattr(inference, "prepare_likelihood", lambda *_: pytest.fail("data loaded"))
    args = _de_arguments()
    args[key] = value
    with pytest.raises(ValueError):
        inference.sample_emcee([], DatasheetPrior(), **args)


def test_de_version_rejected_before_observation_load(monkeypatch):
    monkeypatch.setattr(emcee, "__version__", "3.2.0")
    monkeypatch.setattr(inference, "prepare_likelihood", lambda *_: pytest.fail("data loaded"))
    with pytest.raises(ValueError, match="version"):
        inference.sample_emcee([], DatasheetPrior(), **_de_arguments())
