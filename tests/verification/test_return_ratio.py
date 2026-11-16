"""Independent return-ratio tests; original protocols/fixtures remain unchanged."""
from copy import deepcopy
import json
from pathlib import Path
import numpy as np
import pytest
from pll_allocation.verification.return_ratio import phasor_fit, crossings, extract_pair, protocol
from pll_allocation.verification.return_ratio_native import simulate_port
from pll_allocation.verification.experiments import candidate
from pll_allocation.verification.simulator import simulate


@pytest.mark.parametrize('overrides', [{}, {'Icp': 120e-6}, {'C1': 50e-12, 'Rz': 4500},
    {'Rz': 2482.02812479}, {'Icp': 104.404300186e-6, 'Rz': 3048.124920669, 'C1': 50e-12,
                          'C2': 2e-9, 'f0': 63.761604100e6, 'Kvco': 27.063993167e6}])
def test_zero_injection_preserves_original_event_path_exactly(overrides):
    p = candidate(overrides)
    kwargs = {'frequency_Hz': 160000, 'amplitude_rad': 0., 'duration_s': 30e-6, 'onset_s': 20e-6}
    new = simulate_port(p, **kwargs)
    original = simulate_port(p, original_export=True, **kwargs)
    old = simulate(p, duration_s=30e-6, onset_s=20e-6, initial_control_V=new['settings']['initial_control_V'], record_interval_s=10e-9)
    assert np.array_equal(new['trace'][:, :6], original['trace'])
    assert np.array_equal(new['trace'][:, :6], old['trace'])
    assert np.array_equal(new['div_edges'], old['div_edges'])
    assert np.array_equal(new['ref_edges'], old['ref_edges'])


def test_complex_fit_retains_phase_sign_and_dc_trend():
    t = np.arange(0, 120e-6, 10e-9); f = 100000
    expected = np.array([.01*np.exp(-1.2j), .02*np.exp(.3j)])
    signals = np.real(np.exp(2j*np.pi*f*t[:, None])*expected)+.1+100*t[:, None]
    got, residual, _ = phasor_fit(t, signals, f)
    assert np.allclose(got[0], expected, atol=1e-12)
    assert np.max(residual) < 1e-12


def test_crossings_do_not_use_bw_or_bridge_unknown_points():
    points = [{'frequency_Hz': f, 'magnitude': m, 'phase_deg': p, 'status': s}
        for f, m, p, s in [(100000, 2, -120, 'MEASURED'), (150000, 1.1, -125, 'UNKNOWN'), (200000, .5, -130, 'MEASURED')]]
    assert crossings(points)['status'] == 'UNKNOWN'
    points[1]['status'] = 'MEASURED'
    out = crossings(points)
    assert out['status'] == 'MEASURED_BRACKETED'
    assert 150000 < out['UGF_Hz'] < 200000 and 50 < out['PM_deg'] < 55


def test_multiple_downward_crossings_remain_unknown():
    points = [{'frequency_Hz': f, 'magnitude': m, 'phase_deg': -120, 'status': 'MEASURED'}
        for f, m in zip((1, 2, 3, 4), (2, .5, 2, .5))]
    assert crossings(points)['status'] == 'UNKNOWN'
    assert crossings(points[:3])['status'] == 'UNKNOWN'  # one down + one up is also ambiguous


@pytest.mark.parametrize('mode,initial,freq', [('bad', None, 1e5), ('series', .4, 1e5), ('series', None, 1e9)])
def test_invalid_port_domain_is_rejected(mode, initial, freq):
    with pytest.raises(ValueError):
        simulate_port(candidate(), mode=mode, initial_control_V=initial, frequency_Hz=freq)


def test_actual_injection_changes_pfd_edges_and_returns_negative_feedback():
    p = candidate()
    settings = {'frequency_Hz': 160000, 'duration_s': 145e-6, 'onset_s': 20e-6}
    a = simulate_port(p, amplitude_rad=.01, **settings)
    b = simulate_port(p, amplitude_rad=-.01, **settings)
    zero = simulate_port(p, amplitude_rad=0., **settings)
    assert not np.array_equal(a['div_edges'], zero['div_edges'])
    m = extract_pair(a, b, protocol())
    assert m['status'] == 'MEASURED' and -150 < m['phase_deg'] < -90
    assert m['quality']['clamp_events'] == 0
    assert not m['M1_used_for_measurement']


@pytest.mark.parametrize('field', ['parameter_sha256', 'protocol_sha256', 'PM_deg'])
def test_extension_rejects_wrong_binding_or_false_certification(tmp_path, field):
    import hashlib
    from pll_allocation.verification.return_ratio_validity import load_extension
    from pll_allocation.verification import return_ratio_validity as module
    from pll_allocation.physics_mapping.model import fingerprint
    root = Path(__file__).resolve().parents[2]
    item = json.loads((root/'tests/fixtures/verification/analytical_proposal_stage3a.json').read_text(encoding='utf-8'))
    evidence = {'schema_version': 'pll-stage4-measurement-extension-1.0',
        **{k: item[k] for k in ('parameter_sha256', 'block_space_sha256', 'system_spec_sha256')},
        'proposal_versions': item['versions'], 'protocol_id': protocol()['protocol_id'],
        'protocol_sha256': fingerprint(protocol()), 'verified_joint_block_spec': False,
        'source_hashes': {name: hashlib.sha256((Path(module.__file__).parent/name).read_bytes()).hexdigest()
            for name in ('kernel.cpp', 'return_ratio_kernel.cpp', 'return_ratio_native.py', 'return_ratio.py', 'return_ratio_validity.py')},
        'metrics': {k: {'value': None, 'status': 'UNKNOWN'} for k in ('PM_deg', 'UGF_Hz')}}
    good = tmp_path/'good.json'; good.write_text(json.dumps(evidence), encoding='utf-8')
    assert load_extension(good, item)['verified_joint_block_spec'] is False
    if field == 'PM_deg':
        evidence['metrics'][field] = {'value': 70, 'status': 'PASS'}
    else:
        evidence[field] = 'wrong'
    bad = tmp_path/'bad.json'; bad.write_text(json.dumps(evidence), encoding='utf-8')
    with pytest.raises(ValueError):
        load_extension(bad, item)


def test_existing_measurement_evidence_cannot_leak_into_first_shot(tmp_path):
    from pll_allocation.pipeline import run_pipeline
    with pytest.raises(ValueError, match='first shot'):
        run_pipeline(tmp_path/'new', measurement_extension='unread')
    assert not (tmp_path/'new').exists()


def test_feedback_categories_compose_without_converting_unreliable_to_failure():
    from pll_allocation.verification.return_ratio_validity import classify_feedback
    metrics = {'PM_deg': {'value': 40, 'status': 'MEASURED_CONVERGED'}}
    predictions = {'PM_deg': 60}
    checks = [{'metric': 'PM_deg', 'status': 'FAIL'}]
    tags = classify_feedback(metrics, predictions, checks)
    assert {x['category'] for x in tags} == {'SPEC_VIOLATION', 'MODEL_DISAGREEMENT'}
    tags = classify_feedback(metrics, predictions, checks, unsupported=['PM_deg'], numerical_ok=False)
    assert {x['category'] for x in tags} == {'UNSUPPORTED_METRIC', 'MEASUREMENT_UNRELIABLE'}
    assert classify_feedback(metrics, predictions, checks, validity='OUT_OF_DOMAIN')[0]['category'] == 'OUT_OF_DOMAIN'
