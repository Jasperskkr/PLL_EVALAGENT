"""Stage4.1 true event-loop compatibility and non-fabricated metric safeguards."""
from copy import deepcopy
from pathlib import Path
import runpy
import numpy as np
import pytest
from pll_allocation.verification.closed_loop_native import simulate_step
from pll_allocation.verification.closed_loop import cycle_average, decay_fit, protocol, analyze
from pll_allocation.verification.experiments import candidate
from pll_allocation.verification.simulator import simulate


@pytest.mark.parametrize('overrides', [{}, {'Icp': 160e-6, 'Kvco': 12.5e6},
    {'C1': 50e-12, 'C2': 2e-9, 'Rz': 3048.124920669113}, {'Rz': 2482.028124785117}])
def test_zero_step_original_three_paths_are_identical(overrides):
    p = candidate(overrides)
    settings = dict(amplitude_rad=0., onset_s=20e-6, duration_s=30e-6)
    extended = simulate_step(p, **settings); original = simulate_step(p, original_export=True, **settings)
    old = simulate(p, duration_s=30e-6, onset_s=20e-6,
                   initial_control_V=extended['settings']['initial_control_V'], record_interval_s=10e-9)
    assert np.array_equal(extended['trace'][:, :6], original['trace'])
    assert np.array_equal(extended['trace'][:, :6], old['trace'])
    assert np.array_equal(extended['ref_edges'], old['ref_edges'])
    assert np.array_equal(extended['div_edges'], old['div_edges'])
    assert np.isfinite(extended['trace']).all()
    assert extended['summary']['slips'] == 0


def test_generated_extension_preserves_frozen_update_source():
    root = Path(__file__).resolve().parents[2]
    generator = runpy.run_path(str(root/'tools/generate_stage41_kernel.py'))
    assert generator['source']().replace('\r\n', '\n') == (root/'pll_allocation/verification/closed_loop_kernel.cpp').read_text(encoding='utf-8')


def test_reference_step_changes_actual_edges_charge_and_voltage():
    p = candidate(); a = simulate_step(p); z = simulate_step(p, amplitude_rad=0.)
    assert not np.array_equal(a['ref_edges'], z['ref_edges'])
    assert not np.array_equal(a['div_edges'], z['div_edges'])
    assert np.ptp(a['trace'][:, 8]) > 1e-14
    assert np.ptp(a['trace'][:, 3]) > 1e-5
    assert np.allclose(a['trace'][:, 9]-a['trace'][:, 10], a['trace'][:, 11], atol=1e-12)
    assert np.allclose(a['trace'][:, 12], 72e6+20e6*a['trace'][:, 3])
    result, curve = analyze(p, a, z, protocol())
    assert result['status'] == 'MEASURED'
    assert result['M2']['settling_s'] is not None
    assert curve.shape[1] == 4
    assert result['comparison']['normalized_RMSE'] < .05


def test_average_preserves_constant_and_linear_signal():
    t = np.linspace(0, 1, 101); edges = np.linspace(.103, .903, 9)
    means = cycle_average(t, np.column_stack([np.ones(len(t)), 2*t]), edges)
    assert np.allclose(means[:, 0], 1)
    assert np.allclose(means[:, 1], edges[:-1]+edges[1:])


def test_decay_unknown_without_sufficient_ringing_and_recovers_known_envelope():
    t = np.arange(0, 100e-6, .1e-6)
    assert decay_fit(t, 1-np.exp(-1e6*t), protocol()['limits'])['rate_per_s'] is None
    got = decay_fit(t, 1+.2*np.exp(-1e5*t)*np.cos(2*np.pi*2e5*t), protocol()['limits'])
    assert got['status'] == 'MEASURED' and abs(got['rate_per_s']/1e5-1) < .02


@pytest.mark.parametrize('settings', [{'amplitude_rad': .03}, {'rise_s': 0}, {'dt_s': 1e-9},
                                      {'amplitude_rad': float('nan')}])
def test_invalid_step_domain_rejected(settings):
    with pytest.raises(ValueError):
        simulate_step(candidate(), **settings)


def test_bad_working_point_does_not_produce_response_metrics():
    p = candidate(); z = simulate_step(p, amplitude_rad=0.); a = deepcopy(z)
    a['trace'][:, 11] += 1
    result, curve = analyze(p, a, z, protocol())
    assert result['status'] == 'UNKNOWN' and curve is None
    assert 'M2' not in result


def test_protocol_cannot_silently_change_certification_or_version(monkeypatch):
    import pll_allocation.verification.closed_loop as module
    item = protocol(); item['formal_UGF_PM_certification'] = True
    monkeypatch.setattr(module, 'read', lambda _: item)
    with pytest.raises(ValueError, match='version/certification'):
        module.protocol()


def test_holdout_rejects_wrong_source_lock_before_simulation(tmp_path, monkeypatch):
    import argparse
    import json
    import tools.run_stage41 as module
    lock = tmp_path/'wrong.json'
    lock.write_text(json.dumps({'source_bindings': {}, 'development_complete': True}), encoding='utf-8')
    monkeypatch.setattr(module, 'run_case', lambda *a, **k: pytest.fail('M2 must not run'))
    args = argparse.Namespace(mode='holdout', out=str(tmp_path/'new'), lock=str(lock))
    with pytest.raises(ValueError, match='lock mismatch'):
        module.main(args)
