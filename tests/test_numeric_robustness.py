"""Numerical robustness without changing CPPLL equations or verdict semantics."""
from copy import deepcopy
import math
from pathlib import Path

import pytest

from pll_allocation.allocation.physics import bandwidth_ratio, raw_prediction
from pll_allocation.numerics import NumericalError, positive_root, polynomial_log_sign, snap_closed_bound
from pll_allocation.physics_mapping.model import FrequencyScan, evaluate, _crossing, ModelError, _loop_crossings
from pll_allocation.exploration.contracts import load_problem, make_parameters


@pytest.mark.parametrize('logroot', [-200., -40., 0.3, 40., 200.])
def test_adaptive_positive_root_is_bounded_and_accurate(logroot):
    diagnostics = {}
    root = positive_root(lambda y: y-math.exp(logroot), diagnostics=diagnostics)
    assert root == pytest.approx(math.exp(logroot), rel=2e-13)
    assert diagnostics['expansions'] > 0 if abs(logroot) > 14 else diagnostics['expansions'] == 0
    assert diagnostics['function_evaluations'] <= 180
    assert diagnostics['iterations'] == 80


def test_scaled_polynomial_overflow_and_nonfinite_failure():
    diagnostics = {}
    # Same polynomial y^3 - exp(600), with a representable root exp(200).
    root = positive_root(lambda y: y**3-math.exp(600),
                         log_function=lambda z: polynomial_log_sign((1., 0., 0., -math.exp(600)), z),
                         diagnostics=diagnostics)
    assert math.log(root) == pytest.approx(200, abs=1e-12)
    assert diagnostics['log_sign_evaluations'] > 0
    with pytest.raises(NumericalError) as caught:
        positive_root(lambda y: float('nan'))
    assert caught.value.reason_code == 'ROOT_NONFINITE_FUNCTION'
    with pytest.raises(NumericalError) as caught:
        positive_root(lambda y: -1.)
    assert caught.value.reason_code in ('ROOT_UNREPRESENTABLE', 'ROOT_NOT_BRACKETED')
    assert caught.value.diagnostics['expansions'] <= 32


def test_root_underflow_is_not_a_success():
    with pytest.raises(NumericalError, match='ROOT_ENDPOINT_UNRESOLVED'):
        positive_root(lambda y: 0.)
    with pytest.raises(NumericalError, match='COEFFICIENT_NONFINITE'):
        polynomial_log_sign((1., float('inf')), 0.)


def base_parameters():
    return dict(Icp=100e-6, Rz=3820., C1=1e-10, C2=1e-9, f0=72e6,
                Kvco=20e6, N=8, f_ref=10e6)


def test_single_current_counterexample_recovers():
    p = base_parameters()
    p['Icp'] = 1e-12
    diag = {}
    result = raw_prediction(p, diagnostics=diag)
    assert result['UGF_Hz'] == pytest.approx(7.587414268969754, rel=1e-6)
    assert result['BW_Hz'] == pytest.approx(11.789126820497918, rel=1e-6)
    assert diag['UGF']['expansions'] > 0


def test_nominal_root_and_bw_ratio_keep_physical_meaning():
    p = base_parameters()
    result = raw_prediction(p)
    q = 1+p['C2']/p['C1']
    x = 2*math.pi*result['UGF_Hz']*p['Rz']*p['C2']
    assert bandwidth_ratio(q, x) == pytest.approx(result['BW_Hz']/result['UGF_Hz'], rel=1e-12)


def test_unrepresentable_coefficients_report_numeric_failure():
    p = base_parameters()
    p['Icp'] = 1e-200
    with pytest.raises(NumericalError, match='COEFFICIENT_RANGE'):
        raw_prediction(p)


def parameters():
    problem = load_problem(Path(__file__).resolve().parents[1]/'configs/problems/nominal.json')
    return make_parameters(problem)


def test_default_scan_recovers_low_gain_and_respects_explicit_limits():
    p = parameters()
    p['values']['Icp']['value'] = 1e-18
    automatic = evaluate(p)
    assert automatic.status.value == 'OK'
    scan = automatic.diagnostics['scan']
    assert scan['expansions'] > 0
    assert scan['minimum_Hz'] < scan['initial_window_Hz'][0]
    assert scan['response_evaluations'] <= 400000
    assert abs(scan['crossings']['UGF']['residual']) < 1e-9
    explicit = evaluate(p, scan=FrequencyScan(1., 1e9, 128))
    assert explicit.status.value == 'NUMERICAL_FAILURE'
    assert explicit.diagnostics['reason_code'] == 'SCAN_EXPLICIT_BOUNDARY'
    assert explicit.diagnostics['scan']['expansions'] == 0


def test_default_scan_nominal_fast_path_unchanged():
    p = parameters()
    default = evaluate(p)
    info = default.diagnostics['scan']
    assert info['expansions'] == 0
    explicit = evaluate(p, scan=FrequencyScan(*info['initial_window_Hz']))
    assert explicit.metrics == default.metrics


def test_scan_nonfinite_or_multiple_crossings_do_not_expand():
    with pytest.raises(ModelError) as caught:
        _crossing([1., 2., 3., 4.], lambda f: {1.: 1., 2.: -1., 3.: 1., 4.: -1.}[f], 'UGF')
    assert caught.value.reason_code == 'SCAN_CROSSING_UNRELIABLE'
    with pytest.raises(ModelError) as caught:
        _crossing([1., 2.], lambda f: float('nan'), 'BW')
    assert caught.value.reason_code == 'SCAN_NONFINITE'


def test_scan_expansion_budget_and_nonfinite_fail_without_certificate(monkeypatch):
    from pll_allocation.physics_mapping import model
    monkeypatch.setattr(model, '_response', lambda p, f: (1., .5, .25))
    diag = {}
    with pytest.raises(ModelError) as caught:
        _loop_crossings(dict(C1=1., C2=1., f_ref=1.), FrequencyScan(points=32), 1., 2., 1., diag)
    assert caught.value.reason_code == 'SCAN_EXPANSION_BUDGET'
    assert diag['scan']['expansions'] == 8


@pytest.mark.parametrize('edge,direction', [(500., -math.inf), (15000., math.inf)])
def test_closed_bound_snap_is_limited_to_eight_ULPs(edge, direction):
    low, high = 500., 15000.
    assert snap_closed_bound(edge, low, high) == (edge, None)
    value = edge
    for i in range(1, 10):
        value = math.nextafter(value, direction)
        corrected, info = snap_closed_bound(value, low, high)
        if i <= 8:
            assert corrected == edge and info['ulp_steps'] == i
            assert info['raw_value'] == value
        else:
            assert corrected == value and info is None
    assert snap_closed_bound(499.999, low, high) == (499.999, None)
    assert snap_closed_bound(float('nan'), low, high)[1] is None


def test_inverse_boundary_restored_then_full_contract_and_formal_m1():
    from pll_allocation.allocation.physics import inverse_at_shape
    from pll_allocation.allocation.core import Meter
    from pll_allocation.exploration.contracts import axes, check_candidate
    problem = load_problem(Path(__file__).resolve().parents[1]/'configs/problems/nominal.json')
    # Fixed reproduction at the declared closed Rz boundary; no local archive.
    p = base_parameters() | {'Rz': 500.}
    target_bw, shape = 119544.62756704011, 0.24174520983096773
    meter = Meter()
    raw = inverse_at_shape(axes(problem), p['C1'], p['C2'], target_bw, shape, meter)
    assert raw['Rz'] == 500.
    correction = meter.events[-1]['boundary_corrections'][0]
    assert correction['raw_value'] < 500. and correction['corrected_value'] == 500.
    candidate = make_parameters(problem, raw)  # all six exact declared bounds
    assert check_candidate(problem, candidate)['status'] != 'INVALID_CANDIDATE'
    assert evaluate(candidate).status.value == 'OK'
    # External inputs and open rails are NOT granted ULP slack.
    with pytest.raises(ValueError):
        make_parameters(problem, {'Rz': math.nextafter(500., -math.inf)})
    rail = parameters()
    rail['values']['f0']['value'] = 56e6
    assert evaluate(rail).status.value == 'OUT_OF_DOMAIN'


def test_precision_warning_is_not_an_infeasibility_verdict():
    p = parameters()
    # A nearly cancelling closed-loop response with representable coefficients.
    for name, value in {'Icp': 1.5791382833109854e-21, 'Rz': 1.5915494310498847e18,
                        'C1': 1e-18, 'C2': 9.999999999177335e-25}.items():
        p['values'][name]['value'] = value
    result = evaluate(p)
    assert result.status.value == 'OK'
    assert any(w['reason_code'] == 'CLOSED_LOOP_CANCELLATION' for w in result.diagnostics['precision_warnings'])
    assert result.diagnostics['physical_infeasibility_proven'] is False


def test_failed_candidate_and_numerical_states_keep_distinct_reasons():
    from pll_allocation.exploration.contracts import check_candidate, screen_problem
    problem = load_problem(Path(__file__).resolve().parents[1]/'configs/problems/nominal.json')
    bad = parameters()
    bad['values']['Rz']['value'] = 499.999
    rejection = check_candidate(problem, bad)
    assert rejection['reason_code'] == 'PARAMETER_BOUNDS'
    assert rejection['status'] == 'INVALID_CANDIDATE'
    assert rejection['global_infeasibility_proven'] is False
    assert screen_problem(problem)['certificates'] == []
    bad['values']['Icp']['value'] = 1e-320
    result = evaluate(bad)
    assert result.status.value == 'NUMERICAL_FAILURE'
    assert result.diagnostics['reason_code'] == 'COEFFICIENT_RANGE'
    assert not result.diagnostics['physical_infeasibility_proven']


def test_unknown_numerical_failure_cannot_issue_global_certificate(monkeypatch):
    import json
    from pll_allocation.exploration import physics_region_builder as builder
    from pll_allocation.physics_mapping.model import fingerprint
    problem = load_problem(Path(__file__).resolve().parents[1]/'configs/problems/nominal.json')
    # Request validation belongs to the caller; use one explicit construction.
    request = dict(request_id='numeric-failure', budget={'construction_attempts': 1}, seed_count=1,
                   evidence_ids=[], strategy='HIGH_PM_LF_SHAPE', target_bw_fraction=[0., 1.],
                   tuning_preference='CENTER', width_policy='NARROW')
    def failure(*args, **kwargs):
        raise NumericalError('ROOT_NOT_BRACKETED', 'injected numerical failure')
    monkeypatch.setattr(builder, 'inverse_at_shape', failure)
    result = builder.build_physics_region(problem, request, model_fingerprint='test-only', random_seed=17)
    assert result['global_infeasibility_proven'] is False
    assert result['attempts'][0]['reason_code'] == 'ROOT_NOT_BRACKETED'
    assert not result['seeds']


def test_instrumented_and_fast_roots_match():
    for logarithm in (-200., -20., 0., 20., 200.):
        target = math.exp(logarithm)
        diag = {}
        plain = positive_root(lambda y: y-target)
        measured = positive_root(lambda y: y-target, diagnostics=diag)
        assert plain == measured
        assert diag['function_evaluations'] <= 180


def test_partially_explicit_frequency_window_only_moves_unspecified_side():
    p = parameters()
    p['values']['Icp']['value'] = 1e-18
    result = evaluate(p, scan=FrequencyScan(maximum_Hz=1e7, points=128))
    assert result.status.value == 'OK'
    info = result.diagnostics['scan']
    assert info['maximum_Hz'] == 1e7 and info['expansions'] > 0
    assert info['minimum_Hz'] < info['initial_window_Hz'][0]


def test_physical_equations_and_sobol_sampling_ast_are_unchanged():
    import ast
    import hashlib
    root = Path(__file__).resolve().parents[1]
    # Formula-only AST hashes from remote main f2f0874, not a local source archive.
    expected = {
        "pm_ceiling": "c9a64558fb4a639804583dbc066b77d2a674487e2329d6dc8d875856a385e0b2",
        "phase_interval": "50af7807bd63015a66a81fad4caf8a1ccfaf242c25992032d08eb2f4b7485a06",
        "bandwidth_ratio": "19036682c41c1fb7ef6706649b43a5ecadcba56d8281c294a5b9e89d5d768419",
        "raw_prediction": "35421276915ad4861589dbbae5a42ca2880e6ca3ce66ef6ff6e8a3a80feb78f2",
        "inverse_parameters": "9ee0664abacad20e72156fefcd8a691b3546d81ff691e91840f75c6644a1b909",
        "response_s": "9ecf28181ab5b39c9810b4f08cbe38a06e638c99b4f482194cc2b9196c184672",
        "response_z": "47e82d1e1a47604f1eb5a817210f055f5fc84d20bb881419a20a4a7f5b1cb61c",
        "response_l": "44b462ff4e87dd4fa73f1f936e8b7eab26449cbd22cc6b4ea50a83ec8aa39c66",
        "response_t": "5db80017181819a5823de3607831e6eb35a210cae9390cb90c672206f486b7bc",
        "sobol_draws": "e009b8cbb248eb14fbeb5519586fddc0209b30834ed41a33e326dd468dedf665"
}
    def parsed(name):
        return ast.parse((root/name).read_text(encoding='utf-8'))
    def function(tree, name):
        return next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)
    def digest(value):
        # Python 3.12 adds empty FunctionDef.type_params; formulas are identical.
        return hashlib.sha256(value.replace(', type_params=[]', '').encode()).hexdigest()
    physics = parsed('pll_allocation/allocation/physics.py')
    actual = {name: digest(ast.dump(function(physics, name))) for name in ('pm_ceiling', 'phase_interval')}
    for name in ('bandwidth_ratio', 'raw_prediction'):
        value = '\n'.join(ast.dump(n.args[0].body) for n in ast.walk(function(physics, name))
                          if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == '_bisect_positive')
        actual[name] = digest(value)
    inverse = next(n.value for n in ast.walk(function(physics, 'inverse_at_shape')) if isinstance(n, ast.Assign) and
                   any(isinstance(t, ast.Name) and t.id == 'result' for t in n.targets))
    actual['inverse_parameters'] = digest(ast.dump(inverse))
    model = parsed('pll_allocation/physics_mapping/model.py')
    for name in ('s', 'z', 'l', 't'):
        value = next(ast.dump(n.value) for n in ast.walk(function(model, '_response')) if isinstance(n, ast.Assign) and
                     any(isinstance(t, ast.Name) and t.id == name for t in n.targets))
        actual['response_'+name] = digest(value)
    builder = parsed('pll_allocation/exploration/physics_region_builder.py')
    value = '\n'.join(ast.dump(n) for n in ast.walk(builder) if isinstance(n, ast.Assign) and
                      any(isinstance(t, ast.Name) and t.id == 'draws' for t in n.targets))
    actual['sobol_draws'] = digest(value)
    assert actual == expected
