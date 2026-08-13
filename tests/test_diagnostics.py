import numpy as np

from magcore_calib.diagnostics import diagnostic_report, posterior_summary


def test_summary_always_reports_six_parameters_and_alpha_boundary():
    rng = np.random.default_rng(2)
    samples = np.column_stack([
        rng.normal(-16, 0.1, 1000), rng.normal(1.5, 0.02, 1000),
        rng.normal(2.5, 0.02, 1000), rng.normal(7.7, 0.05, 1000),
        rng.normal(13.8, 0.05, 1000), rng.normal(0.845, 0.002, 1000),
    ])
    summary = posterior_summary(samples)
    assert set(summary) == {"k", "alpha", "beta", "mu_s", "f_rel_hz", "alpha_cc"}
    assert summary["alpha_cc"]["boundary_flag"] is True
    assert "ci90_half_width_pct" not in summary["alpha_cc"]


def test_injected_diagnostics_apply_declared_gates():
    chain = np.zeros((1000, 20, 6))
    report = diagnostic_report(chain, np.full(20, 0.4), np.full(6, 10.0))
    assert report["valid"] is True
    assert all(value == 2000.0 for value in report["ess"].values())
