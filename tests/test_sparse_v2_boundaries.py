"""Independent deterministic checks at the confirmatory sampler boundary."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import emcee
import numpy as np
import pytest

from magcore_calib.sparse_mixing import load_frozen_modules
from magcore_calib.sparse_transport import VectorizedPosterior


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def runner():
    spec = importlib.util.spec_from_file_location(
        "confirmatory_boundary_test", ROOT / "experiments/sparse_mixing_v2.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ConstructorReached(Exception):
    """Terminate the test before any proposal or chain can be allocated."""


@pytest.mark.parametrize("arm", ["stretch", "logit_stretch", "de_snooker"])
def test_actual_sampler_moves_match_pinned_record_without_running_chain(runner, monkeypatch, tmp_path, arm):
    modules = load_frozen_modules(ROOT)
    spec = modules.prior.DatasheetPrior()
    geometry = modules.models.Geometry()
    observation = modules.models.Observation(
        modules.models.DesignPoint(modules.models.Channel.MU_REAL, 1e5, 0.0),
        2000.0, 50.0,
    )
    target = SimpleNamespace(target_id="n3")
    state = SimpleNamespace(
        modules=modules, observations=(observation,), spec=spec, geometry=geometry,
    )
    initial = np.tile(modules.prior.prior_center_vector(spec), (48, 1))
    task = {
        "index": 0, "task_id": "boundary", "target_id": "n3", "arm": arm,
        "initialization": "local_prior_center", "replicate": 0,
        "initial_seed": 17, "sampler_seed": 19,
    }
    config = {
        "emcee_version": emcee.__version__, "_parent_path": "unused",
        "warmup": 80000, "retained": 800000, "checkpoints": [800000],
    }
    monkeypatch.setattr(runner, "require_slurm", lambda: None)
    monkeypatch.setattr(runner, "tasks", lambda _: [task])
    monkeypatch.setattr(runner, "load_sparse_mixing_plan", lambda _: SimpleNamespace(targets=[target]))
    monkeypatch.setattr(runner, "reconstruct_state", lambda *args: state)
    monkeypatch.setattr(runner, "initial_ensemble", lambda *args, **kwargs: initial)

    def capture(n_walkers, ndim, log_probability, *, moves, vectorize):
        assert (n_walkers, ndim, vectorize) == (48, 6, True)
        if arm == "logit_stretch":
            assert log_probability.__func__ is VectorizedPosterior.transformed
        else:
            assert isinstance(log_probability, VectorizedPosterior)
        objects = moves if isinstance(moves, list) else [(moves, 1.0)]
        declared = runner.move_parameters(arm)
        assert {type(move).__name__ for move, _ in objects} == set(declared)
        for move, weight in objects:
            fields = declared[type(move).__name__]
            assert weight == fields["weight"]
            for name, value in fields.items():
                if name != "weight":
                    assert getattr(move, name) == value
        raise ConstructorReached

    monkeypatch.setattr(emcee, "EnsembleSampler", capture)
    with pytest.raises(ConstructorReached):
        runner.run_task(config, task, mm2_source=tmp_path, mm2_config=tmp_path, out_dir=tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_existing_output_aborts_before_reconstruction(runner, monkeypatch, tmp_path):
    task = {"task_id": "already_exists"}
    config = {"emcee_version": emcee.__version__}
    marker = tmp_path / "already_exists.SUCCESS.json"
    marker.write_text("{}")
    monkeypatch.setattr(runner, "require_slurm", lambda: None)
    monkeypatch.setattr(runner, "tasks", lambda _: [task])
    monkeypatch.setattr(runner, "reconstruct_state", lambda *args: pytest.fail("loaded state before output collision check"))
    with pytest.raises(FileExistsError):
        runner.run_task(config, task, mm2_source=tmp_path, mm2_config=tmp_path, out_dir=tmp_path)
    assert marker.read_text() == "{}"
