"""Density preservation checks for sparse-posterior transport.

These tests evaluate densities and coordinate maps without running chains.
"""

from __future__ import annotations

from dataclasses import replace
import hashlib
import importlib.util
from pathlib import Path
import sys

import numpy as np
import pytest

from magcore_calib.sparse_mixing import load_frozen_modules
from magcore_calib.sparse_transport import (
    VectorizedPosterior,
    log_abs_det_jacobian,
    to_original,
    to_unconstrained,
)


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def pilot_module():
    spec = importlib.util.spec_from_file_location(
        "sparse_pilot_test", ROOT / "experiments/sparse_mixing_pilot.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def pilot_config_path(tmp_path):
    folder = tmp_path / "configs"
    folder.mkdir()
    parent = (ROOT / "configs/sparse_mixing_v1.toml").read_bytes()
    (folder / "sparse_mixing_v1.toml").write_bytes(parent)
    path = folder / "pilot.toml"
    path.write_text(
        'schema_version = "magcore-sparse-mixing-pilot/1.0"\n'
        'protocol_id = "SparseMix-Pilot-1"\n'
        'record_class = "endpoint_free_technical_pilot"\n'
        'diagnostic_only = true\nretroactive_mm2_admission_allowed = false\n'
        'n_walkers = 48\n'
        'arms = ["stretch", "de_snooker", "logit_stretch"]\n'
        'families = ["local_prior_center", "overdispersed_prior_lhs"]\n'
        'replicates = 2\nwarmup = 10000\nretained = 80000\n'
        'checkpoints = [20000, 40000, 60000, 80000]\n'
        'parent_config = "configs/sparse_mixing_v1.toml"\n'
        f'parent_config_sha256 = "{hashlib.sha256(parent).hexdigest()}"\n'
        '[selection]\nrequire_complete_matrix = true\n'
        'confirmatory_seeds_must_be_new = true\nscientific_endpoints_allowed = false\n',
        encoding="utf-8",
    )
    return path


@pytest.fixture
def target():
    modules = load_frozen_modules(ROOT)
    models = modules.models
    observations = [
        models.Observation(models.DesignPoint(models.Channel.PCV, 1.0e5, 0.1), 0.08, 0.01),
        models.Observation(models.DesignPoint(models.Channel.PCV, 3.0e5, 0.2), 0.5, 0.08),
        models.Observation(models.DesignPoint(models.Channel.MU_REAL, 1.0e5, 0.0), 2000.0, 50.0),
        models.Observation(models.DesignPoint(models.Channel.MU_IMAG, 4.0e5, 0.0), 400.0, 30.0),
        models.Observation(models.DesignPoint(models.Channel.LM, 1.0e5, 0.0), 3.0e-4, 1.0e-5),
    ]
    spec = modules.prior.DatasheetPrior()
    data = modules.inference.prepare_likelihood(observations, models.Geometry())
    return modules, spec, data, VectorizedPosterior(data, spec, modules)


def test_vectorized_density_matches_frozen_scalar_for_mixed_channels(target):
    modules, spec, data, posterior = target
    center = modules.prior.prior_center_vector(spec)
    rng = np.random.default_rng(78453)
    points = center + rng.normal(size=(64, 6)) * np.array([0.3, 0.1, 0.1, 0.15, 0.2, 0.08])
    expected = np.array([
        modules.inference._log_posterior_prepared(row, data, spec)
        for row in points
    ])
    np.testing.assert_allclose(posterior(points), expected, rtol=2e-12, atol=2e-9)
    np.testing.assert_array_equal(posterior(points), posterior(points))


@pytest.mark.parametrize("coordinate,bound", [(1, 1.0), (1, 3.0), (2, 2.0), (2, 4.0), (3, 0.0), (4, np.log(1000.0)), (5, 0.0), (5, 0.85)])
def test_original_density_preserves_inclusive_prior_bounds(target, coordinate, bound):
    modules, spec, data, posterior = target
    point = modules.prior.prior_center_vector(spec)
    point[coordinate] = bound
    expected = modules.inference._log_posterior_prepared(point, data, spec)
    assert np.isfinite(expected)
    np.testing.assert_allclose(posterior(point[None, :])[0], expected, rtol=2e-12, atol=2e-9)


@pytest.mark.parametrize("coordinate,value", [(1, 0.999), (1, 3.001), (2, 1.999), (2, 4.001), (3, -0.01), (4, np.log(999.0)), (5, -0.001), (5, 0.851), (0, np.nan), (0, np.inf), (0, -np.inf)])
def test_vectorized_density_rejects_invalid_points(target, coordinate, value):
    modules, spec, _, posterior = target
    valid = modules.prior.prior_center_vector(spec)
    invalid = valid.copy()
    invalid[coordinate] = value
    actual = posterior(np.stack([valid, invalid]))
    assert np.isfinite(actual[0])
    assert actual[1] == -np.inf


def test_invalid_prior_scale_does_not_create_finite_density(target):
    modules, spec, data, _ = target
    for sd in (0.0, -0.1, np.inf, np.nan):
        invalid_spec = replace(spec, alpha_sd=sd)
        with pytest.raises(ValueError, match="prior scales"):
            VectorizedPosterior(data, invalid_spec, modules)


def test_batch_order_and_partition_do_not_change_density(target):
    modules, spec, _, posterior = target
    rng = np.random.default_rng(888)
    points = modules.prior.prior_center_vector(spec) + rng.normal(size=(12, 6)) * 0.02
    order = rng.permutation(len(points))
    np.testing.assert_array_equal(posterior(points[order]), posterior(points)[order])
    np.testing.assert_array_equal(
        np.concatenate([posterior(points[:5]), posterior(points[5:])]),
        posterior(points),
    )


@pytest.mark.parametrize("channel_index", [0, 1, 2, 3])
def test_single_channel_density_respects_supplied_prior(target, channel_index):
    modules, spec, data, _ = target
    spec = replace(spec, log10_k_nom=-7.2, log10_k_sd=0.3, ln_mu_s_sd=0.45, alpha_cc_nom=0.4)
    mask = data.channel == channel_index
    subset = replace(data, **{
        field: getattr(data, field)[mask]
        for field in ("channel", "frequency_hz", "flux_t", "values", "sigma")
    })
    posterior = VectorizedPosterior(subset, spec, modules)
    x = modules.prior.prior_center_vector(spec)
    expected = modules.inference._log_posterior_prepared(x, subset, spec)
    np.testing.assert_allclose(posterior(x[None, :])[0], expected, rtol=2e-12, atol=2e-9)


def test_transport_roundtrip_preserves_all_six_coordinates():
    x = np.array([
        [-17.0, 1.4, 2.5, 7.5, 13.0, 0.001],
        [-18.0, 2.4, 3.5, 8.5, 14.0, 0.425],
        [-16.0, 1.8, 2.7, 6.5, 12.0, 0.849],
    ])
    z = to_unconstrained(x)
    np.testing.assert_array_equal(z[:, :5], x[:, :5])
    np.testing.assert_allclose(to_original(z), x, rtol=1e-13, atol=1e-13)
    np.testing.assert_allclose(to_original(to_unconstrained(x[0])), x[0], rtol=1e-13)
    np.testing.assert_allclose(to_unconstrained(to_original(z)), z, rtol=1e-12, atol=1e-12)


@pytest.mark.parametrize("logit", [-10.0, -3.0, 0.0, 2.0, 10.0])
def test_transport_jacobian_matches_finite_difference(logit):
    z = np.array([-17.0, 1.5, 2.5, 7.5, 13.0, logit])
    step = 1.0e-5
    identity = np.eye(6)
    jacobian = np.column_stack([
        (to_original(z + step * direction) - to_original(z - step * direction)) / (2 * step)
        for direction in identity
    ])
    sign, logdet = np.linalg.slogdet(jacobian)
    assert sign == 1.0
    np.testing.assert_allclose(log_abs_det_jacobian(z), logdet, rtol=1e-7, atol=1e-7)


def test_transformed_density_adds_inverse_map_jacobian(target):
    modules, spec, data, posterior = target
    x = np.tile(modules.prior.prior_center_vector(spec), (5, 1))
    x[:, 5] = [0.001, 0.1, 0.425, 0.7, 0.849]
    z = to_unconstrained(x)
    scalar = np.array([
        modules.inference._log_posterior_prepared(row, data, spec)
        for row in x
    ])
    # d(alpha_cc)/dz = alpha_cc * (1-alpha_cc/0.85).
    expected = scalar + np.log(x[:, 5] * (1.0 - x[:, 5] / 0.85))
    np.testing.assert_allclose(posterior.transformed(z), expected, rtol=2e-12, atol=2e-9)


def test_jacobian_stays_finite_at_extreme_finite_logits():
    z = np.zeros((3, 6))
    z[:, 5] = [-1000.0, 0.0, 1000.0]
    actual = log_abs_det_jacobian(z)
    assert np.all(np.isfinite(actual))
    np.testing.assert_allclose(actual[[0, 2]], np.log(0.85) - 1000.0)


@pytest.mark.parametrize("alpha_cc", [-0.01, 0.0, 0.85, 0.9, np.nan, np.inf])
def test_forward_transport_rejects_noninterior_inputs(alpha_cc):
    x = np.zeros(6)
    x[5] = alpha_cc
    with pytest.raises(ValueError, match="finite interior"):
        to_unconstrained(x)


@pytest.mark.parametrize("shape", [(), (5,), (2, 7)])
def test_transport_rejects_malformed_shapes(shape):
    x = np.zeros(shape)
    for function in (to_unconstrained, to_original, log_abs_det_jacobian):
        with pytest.raises(ValueError, match="dimension six"):
            function(x)


def test_batched_density_rejects_unbatched_shape(target):
    modules, spec, _, posterior = target
    with pytest.raises(ValueError, match="shape"):
        posterior(modules.prior.prior_center_vector(spec))
    assert posterior(np.empty((0, 6))).shape == (0,)


def test_transformed_density_rejects_saturated_or_nonfinite_coordinates(target):
    modules, spec, _, posterior = target
    z = np.tile(to_unconstrained(modules.prior.prior_center_vector(spec)), (6, 1))
    z[:, 5] = [-1000.0, 1000.0, -np.inf, np.inf, np.nan, 0.0]
    result = posterior.transformed(z)
    assert np.all(result[:5] == -np.inf)
    assert np.isfinite(result[5])


def test_lm_likelihood_requires_geometry(target):
    modules, spec, data, _ = target
    posterior = VectorizedPosterior(replace(data, geometry=None), spec, modules)
    with pytest.raises(ValueError, match="Geometry"):
        posterior(modules.prior.prior_center_vector(spec)[None, :])


def test_pilot_task_seeds_pair_initialization_and_preserve_identity(pilot_module, pilot_config_path):
    config = pilot_module.load_config(pilot_config_path)
    assert config["_config_sha256"] == hashlib.sha256(pilot_config_path.read_bytes()).hexdigest()
    tasks = pilot_module.tasks(config)
    assert len(tasks) == 24
    assert len({row["task_id"] for row in tasks}) == 24
    assert len({row["sampler_seed"] for row in tasks}) == 24
    groups = {}
    for task in tasks:
        key = (task["target_id"], task["initialization"], task["replicate"])
        groups.setdefault(key, []).append(task)
    assert len(groups) == 8
    assert all(len({row["initial_seed"] for row in group}) == 1 for group in groups.values())
    reordered = pilot_module.tasks({**config, "arms": list(reversed(config["arms"]))})
    keyed = lambda rows: {
        row["task_id"]: {key: value for key, value in row.items() if key != "index"}
        for row in rows
    }
    assert keyed(tasks) == keyed(reordered)


@pytest.mark.parametrize("old,new", [('retained = 80000', 'retained = 80001'), ('replicates = 2', 'replicates = true'), ('"de_snooker"', '"unknown"'), ('20000, 40000, 60000, 80000', '20000, 40000, 80000')])
def test_pilot_parser_rejects_schedule_or_arm_drift(pilot_module, pilot_config_path, old, new):
    pilot_config_path.write_text(pilot_config_path.read_text().replace(old, new))
    with pytest.raises(ValueError):
        pilot_module.load_config(pilot_config_path)


def test_pilot_parser_rejects_mutated_parent(pilot_module, pilot_config_path):
    parent = pilot_config_path.parent / "sparse_mixing_v1.toml"
    parent.write_bytes(parent.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="checksum"):
        pilot_module.load_config(pilot_config_path)


@pytest.mark.parametrize("present_env", [None, "SLURM_JOB_ID", "SLURM_JOB_NODELIST"])
def test_pilot_rejects_login_before_config_or_state_loading(pilot_module, monkeypatch, tmp_path, present_env):
    for key in ("SLURM_JOB_ID", "SLURM_JOB_NODELIST"):
        monkeypatch.delenv(key, raising=False)
    if present_env is not None:
        monkeypatch.setenv(present_env, "test-only")

    def must_not_load(*args, **kwargs):
        pytest.fail("configuration or state loaded before the scheduler guard")

    monkeypatch.setattr(pilot_module, "load_config", must_not_load)
    monkeypatch.setattr(pilot_module, "tasks", must_not_load)
    monkeypatch.setattr(pilot_module, "reconstruct_state", must_not_load)
    with pytest.raises(RuntimeError, match="SLURM"):
        pilot_module.run_task({}, {}, mm2_source=tmp_path, mm2_config=tmp_path, out_dir=tmp_path)
    monkeypatch.setattr(sys, "argv", [
        "pilot", "--config", str(tmp_path / "absent.toml"), "--task-id", "0",
        "--mm2-source", str(tmp_path), "--mm2-config", str(tmp_path),
        "--out-dir", str(tmp_path / "out"),
    ])
    with pytest.raises(RuntimeError, match="SLURM"):
        pilot_module.main()
    assert not (tmp_path / "out").exists()
