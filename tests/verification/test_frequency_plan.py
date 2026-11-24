"""Integer-N metadata, independent measurements, and standard M2 request binding."""
from copy import deepcopy
import json
import math
from pathlib import Path

import numpy as np
import pytest

from pll_allocation.agent.spec_allocation import run_spec_allocation
from pll_allocation.physics_mapping.model import fingerprint
from pll_allocation.verification import continuous, run_suite
from pll_allocation.verification.experiments import candidate, protocol
from pll_allocation.verification.measure import capture_metrics
from pll_allocation.verification.simulator import simulate, validate_frequency_plan

ROOT = Path(__file__).resolve().parents[2]


def parameters(n=10):
    p = deepcopy(candidate())
    # Equal divided-frequency dynamics across N; all parameters remain positive.
    for name, value in {'N': n, 'f0': 72e6*n/8, 'Kvco': 20e6*n/8}.items():
        p['values'][name]['value'] = value
    return p


@pytest.mark.parametrize('n', [1, 4, 8, 10, 16])
def test_capture_phase_slope_uses_observed_divider(n):
    fref, ppm = 10e6, 20.
    t = np.linspace(0, 30e-6, 1501)
    slope = 2*math.pi*fref*ppm*1e-6*t
    trace = np.column_stack([t, slope, np.zeros(len(t)), np.full(len(t), .4),
                             np.full(len(t), .4), np.zeros(len(t))])
    plan = {'f_ref_Hz': fref, 'N': n, 'output_frequency_Hz': n*fref}
    run = {'trace': trace, 'settings': {'frequency_plan': plan},
           'summary': {'actual_clamp_events': 0}}
    result = capture_metrics(run, protocol())
    assert result['status'] == 'CAPTURED_WITHIN_WINDOW'
    assert result['output_frequency_Hz'] == pytest.approx(n*fref*(1+ppm*1e-6))
    assert result['frequency_plan'] == plan
    assert result['frequency_plan_source'] == 'SIMULATION_SETTINGS'
    run['settings']['frequency_plan']['output_frequency_Hz'] += 1
    with pytest.raises(ValueError, match='frequency plan'):
        capture_metrics(run, protocol())


def test_capture_convergence_ppm_uses_target_frequency(tmp_path, monkeypatch):
    p = parameters(10)
    measured = iter([100e6, 100e6+90.])

    def saved(*args, **kwargs):
        return {'output_frequency_Hz': next(measured), 'steady_control_V': .4,
                'lock_time_s': 20e-6, 'status': 'CAPTURED_WITHIN_WINDOW'}

    monkeypatch.setattr(run_suite, 'save_run', saved)
    result = run_suite.capture_pair(tmp_path/'capture', p, .15, 160e-6)
    assert result['step_comparison']['frequency_difference_ppm'] == pytest.approx(.9)
    assert result['numerical_converged']


def test_frequency_sweep_is_not_skipped_above_old_80mhz_intercept(tmp_path, monkeypatch):
    p = parameters(10)
    p['values']['f0']['value'] = 90e6
    calls, posthoc = [], []
    monkeypatch.setattr(continuous, 'capture_pair', lambda *a, **k: {})
    monkeypatch.setattr(continuous, 'response_sweep', lambda *a, **k: calls.append(k) or {})
    monkeypatch.setattr(continuous, 'comparison_after_measurement', lambda *a, **k: {'checked': True})
    _, _, result = continuous.measurement_suite(p, tmp_path, protocol(),
        before_posthoc_m1=lambda: posthoc.append(True))
    assert len(calls) == 4 and len(posthoc) == 1
    assert result == {'checked': True}


@pytest.mark.parametrize('n', [0, -1, 8.5, True])
def test_invalid_divider_still_rejected(n):
    p = candidate()
    p['values']['N']['value'] = n
    with pytest.raises(ValueError, match='N:'):
        validate_frequency_plan(p)


def test_reference_and_rail_scope_remains_explicit():
    p = parameters(10)
    p['values']['f_ref']['value'] = 20e6
    with pytest.raises(ValueError, match='10MHz reference'):
        validate_frequency_plan(p)


@pytest.fixture(scope='module')
def n10_handoff(tmp_path_factory):
    folder = tmp_path_factory.mktemp('integer_n_handoff')
    p = json.loads((ROOT/'configs/problems/nominal.json').read_text(encoding='utf-8'))
    p['fixed_parameters']['N']['value'] = 10
    path = folder/'problem.json'
    path.write_text(json.dumps(p), encoding='utf-8')
    cfg = json.loads((ROOT/'configs/agent/spec_allocation.json').read_text(encoding='utf-8'))
    cfg.update(target_count=1, m2_target_count=1, m1_budget=16, initial_search_m1_budget=8,
               m2_budget=0, llm_budget=0)
    run_spec_allocation(path, folder/'run', config=cfg)
    return json.loads((folder/'run/initial/verification_handoff.json').read_text(encoding='utf-8'))


def test_n10_request_uses_spec_and_versioned_bound_protocol(n10_handoff):
    req = continuous.verification_request(n10_handoff, run_id='TEST', observation_id='TEST:N10', timeout_s=30)
    assert continuous.validate_request(req) == n10_handoff['recommended_nominal']['parameters']
    assert req['protocol_id'] == 'integer_n_metrics_1.0'
    assert req['protocol']['base_protocol_id'] == 'track_b_metrics_1.1'
    assert req['protocol']['frequency_plan'] == {'f_ref_Hz': 10e6, 'N': 10, 'output_frequency_Hz': 100e6}
    assert req['specs'] == n10_handoff['system_spec']
    req['protocol']['frequency_plan']['N'] = 8
    req['protocol_sha256'] = fingerprint(req['protocol'])
    req['request_sha256'] = fingerprint({k: v for k, v in req.items() if k != 'request_sha256'})
    with pytest.raises(ValueError, match='binding mismatch'):
        continuous.validate_request(req)


@pytest.mark.parametrize('n', [4, 8, 10, 16])
def test_native_integer_n_observation_tracks_actual_output(n):
    run = simulate(parameters(n), duration_s=30e-6, onset_s=30e-6, initial_control_V=.4)
    measured = capture_metrics(run, protocol())
    assert run['settings']['frequency_plan']['N'] == n
    assert measured['status'] == 'CAPTURED_WITHIN_WINDOW'
    assert measured['output_frequency_Hz'] == pytest.approx(n*10e6, rel=1e-8)
    assert run['summary']['tail_frequency_Hz'] == pytest.approx(n*10e6, rel=1e-8)
