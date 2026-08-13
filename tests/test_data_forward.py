import csv

import numpy as np
import pytest

from magcore_calib.data import common_random_outcomes, default_library, load_material_csv
from magcore_calib.forward import predict
from magcore_calib.models import Channel, DesignPoint, Geometry, MagneticParams
from magcore_calib.inference import log_likelihood_active, log_likelihood_prepared, prepare_likelihood
from magcore_calib.models import Observation


def params():
    return MagneticParams(1e-7, 1.5, 2.5, 2200.0, 1e6, 0.25)


def test_default_library_is_isothermal_and_magnetic_only():
    library = default_library()
    assert {point.temperature_c for point in library} == {25.0}
    assert {point.channel for point in library} == {
        Channel.PCV, Channel.MU_REAL, Channel.MU_IMAG, Channel.LM,
    }


def test_forward_rejects_mixed_temperature():
    points = [DesignPoint(Channel.PCV, 1e5, 0.1, 25.0),
              DesignPoint(Channel.PCV, 1e5, 0.1, 60.0)]
    with pytest.raises(ValueError, match="temperature-independent"):
        predict(params(), points)


def test_loader_filters_temperature_cohort(tmp_path):
    path = tmp_path / "mu.csv"
    path.write_text(
        "f,T,b,mu_real,mu_imag\n100000,25.1,0,2000,100\n100000,60,0,1500,200\n",
        encoding="utf-8",
    )
    observations = load_material_csv(str(path), target_temperature_c=25.0, tolerance_c=0.5)
    assert len(observations) == 2
    assert all(abs(o.design.temperature_c - 25.0) <= 0.5 for o in observations)


def test_pcv_loader_normalizes_explicit_millitesla_encoding(tmp_path):
    path = tmp_path / "pcv.csv"
    path.write_text("f,p_v,T,b\n100000,12,25,25\n100000,15,25,0.1\n", encoding="utf-8")
    report = {}
    observations = load_material_csv(
        str(path), target_temperature_c=25.0, channels=(Channel.PCV,), b_max_t=0.5,
        normalize_flux_above_1_as_millitesla=True, report=report,
    )
    assert [o.design.b_pk_t for o in observations] == [0.025, 0.1]
    assert report["rows_flux_normalized_millitesla_to_tesla"] == 1
    assert report["observations_emitted"] == 2


def test_common_random_outcomes_are_reproducible():
    library = default_library()[:4]
    first = common_random_outcomes(params(), library, seed=8, geometry=Geometry())
    second = common_random_outcomes(params(), library, seed=8, geometry=Geometry())
    assert first == second
    assert set(first) == {point.key() for point in library}


def test_inference_accepts_a_non_25c_isothermal_cohort():
    design = DesignPoint(Channel.MU_REAL, 1e5, 0.0, 30.2)
    value = predict(params(), [design], target_c=30.0, tolerance_c=0.5)[0]
    likelihood = log_likelihood_active(params().to_active(), [Observation(design, value, 1.0)])
    assert np.isfinite(likelihood)


def test_vectorized_likelihood_matches_forward_for_all_channels():
    geometry = Geometry()
    observations = []
    for design in default_library()[:6] + [
        DesignPoint(Channel.PCV, 1e5, 0.1), DesignPoint(Channel.LM, 1e5, 0.0)
    ]:
        value = predict(params(), [design], geometry)[0]
        observations.append(Observation(design, value, max(abs(value) * 0.02, 1e-9)))
    actual = log_likelihood_prepared(params().to_active(), prepare_likelihood(observations, geometry))
    expected = sum(-np.log(o.sigma) - 0.5 * np.log(2.0 * np.pi) for o in observations)
    assert np.isclose(actual, expected)
