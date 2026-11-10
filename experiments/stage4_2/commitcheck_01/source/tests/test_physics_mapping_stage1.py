"""Physical/numerical properties and domain gates for isolated M1."""
from copy import deepcopy
from dataclasses import replace
import json
import math
from pathlib import Path
import pytest
from pll_allocation.physics_mapping import (
    FrequencyScan, MetricRequest, M1Evaluator, Status, UnavailableEvaluator, evaluate,
)
from pll_allocation.physics_mapping.experiment import (
    judge_experiment, load_experiment, parameters_from_experiment, validate_experiment,
)
from pll_allocation.physics_mapping.validation import HISTORICAL_ANCHOR, polynomial_reference, run_stage1

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT/'configs/physics_mapping_stage1_v2.json'


@pytest.fixture
def exp():
    return load_experiment(CONFIG)


@pytest.fixture
def parameters(exp):
    return parameters_from_experiment(exp)


def changed(parameters, name, value=None, unit=None):
    p = deepcopy(parameters)
    if value is not None:
        p['values'][name]['value'] = value
    if unit is not None:
        p['values'][name]['unit'] = unit
    return p


def test_historical_python_anchor_and_scoped_verdict(exp, parameters):
    result = evaluate(parameters)
    assert result.status == Status.OK
    for name in ('UGF_Hz', 'BW_Hz'):
        assert abs(result.metrics[name]/HISTORICAL_ANCHOR[name]-1) <= .005
    assert abs(result.metrics['PM_deg']-HISTORICAL_ANCHOR['PM_deg']) <= .2
    assert abs(result.metrics['Vctrl_required_V']-.4) <= 1e-6
    assert result.metrics['output_frequency_Hz'] == 80e6
    assert result.metrics['Kvco_local_Hz_per_V'] == 20e6
    judgment = judge_experiment(exp, parameters, result)
    assert judgment['verdict'] == 'M1_SPEC_PASS'
    assert judgment['verified_joint_block_spec'] is False
    assert result.diagnostics['MATLAB_runtime_calls'] == 0
    assert result.diagnostics['behavioral_TB_calls'] == 0


@pytest.mark.parametrize('changes', [{'Icp': 120e-6}, {'Rz': 4500}, {'Kvco': 25e6},
                                     {'C1': 50e-12, 'C2': 2e-9},
                                     {'Icp': 140e-6, 'Kvco': 20e6/1.4}])
def test_perturbations_against_independent_magnitude_polynomials(exp, changes):
    p = parameters_from_experiment(exp, changes)
    result = evaluate(p)
    assert result.status == Status.OK
    for k, v in polynomial_reference(p).items():
        assert result.metrics[k] == pytest.approx(v, rel=1e-9, abs=1e-9)


def test_lf_transfer_matches_independent_two_node_kcl(parameters):
    fs = (1e2, 1e4, 1e5, 1e6, 1e8)
    result = evaluate(parameters, response_frequencies_Hz=fs)
    assert result.status == Status.OK
    p = {k: v['value'] for k, v in parameters['values'].items()}
    g = 1/p['Rz']
    for f, row in zip(fs, result.response):
        s = 2j*math.pi*f
        y11, y22 = s*p['C1']+g, s*p['C2']+g
        z_kcl = y22/(y11*y22-g*g)
        assert complex(*row['Zlf_Ohm']) == pytest.approx(z_kcl, rel=1e-11)
        l = complex(*row['L'])
        assert l == pytest.approx(p['Icp']*p['Kvco']/p['N']*z_kcl/s, rel=1e-11)
        assert complex(*row['T']) == pytest.approx(l/(1+l), rel=1e-12)


def test_coupled_gain_invariance_changes_tuning_but_not_loop(exp, parameters):
    base = evaluate(parameters)
    p = parameters_from_experiment(exp, {'Icp': 140e-6, 'Kvco': 20e6/1.4})
    other = evaluate(p)
    for k in ('UGF_Hz', 'BW_Hz', 'PM_deg'):
        assert other.metrics[k] == pytest.approx(base.metrics[k], rel=1e-11)
    assert other.metrics['Vctrl_required_V'] == pytest.approx(.56)


@pytest.mark.parametrize('name,value', [
    ('Icp', 0), ('Rz', -1), ('C1', 0), ('C2', -1e-9), ('Kvco', -20e6),
    ('f_ref', 0), ('N', 0), ('N', 8.0), ('N', True),
    ('Vctrl_min', 1.2), ('f0', -1), ('PFD_reset_delay', -1e-9),
    ('PFD_reset_delay', 1e-7), ('Cload', -1e-15), ('Gload', -1e-9),
    ('CP_mismatch', 2), ('Icp', float('nan')), ('Rz', float('inf')),
])
def test_invalid_signs_types_and_nonfinite_never_pass(exp, parameters, name, value):
    p = changed(parameters, name, value)
    r = evaluate(p)
    assert r.status == Status.OUT_OF_DOMAIN
    assert r.metrics == {}
    assert judge_experiment(exp, p, r)['verdict'] == 'UNKNOWN'
    json.dumps(r.as_dict(), allow_nan=False)


@pytest.mark.parametrize('name,unit', [('Kvco', 'rad/s/V'), ('Icp', 'uA'),
                                     ('Rz', 'kOhm'), ('C1', 'pF')])
def test_explicit_wrong_units_rejected(parameters, name, unit):
    r = evaluate(changed(parameters, name, unit=unit))
    assert r.status == Status.OUT_OF_DOMAIN
    assert not r.metrics


@pytest.mark.parametrize('name,value', [('Kvco2', 1e6), ('CP_mismatch', .01),
    ('CP_leakage', 1e-9), ('CP_leakage', -1e-9), ('q0', -1e-15),
    ('PFD_reset_delay', 1e-12), ('Cload', 5e-14), ('Gload', 1e-9)])
def test_nonideal_linearization_is_explicitly_unsupported(exp, parameters, name, value):
    p = changed(parameters, name, value)
    result = evaluate(p)
    assert result.status == Status.UNSUPPORTED
    assert name in result.reason
    assert not result.metrics
    assert judge_experiment(exp, p, result)['verdict'] == 'UNKNOWN'


@pytest.mark.parametrize('f0,feasible', [(40e6, False), (80e6, True), (56e6, True)])
def test_outside_or_rail_tuning_not_valid_m1(parameters, f0, feasible):
    result = evaluate(changed(parameters, 'f0', f0))
    assert result.status == Status.OUT_OF_DOMAIN
    assert result.factors['F_TUNING']['feasible'] is feasible
    assert not result.metrics


@pytest.mark.parametrize('scan,reason', [
    (FrequencyScan(1e6, 1e7, 64), 'UGF'),
    (FrequencyScan(1e3, 180e3, 256), 'BW'),
])
def test_missing_crossings_never_generate_reliable_metrics(exp, parameters, scan, reason):
    r = evaluate(parameters, scan=scan)
    assert r.status == Status.NUMERICAL_FAILURE and reason in r.reason
    assert not r.metrics
    assert judge_experiment(exp, parameters, r)['verdict'] == 'UNKNOWN'


def test_crossing_residuals_and_scan_resolution_converge(parameters):
    base = evaluate(parameters)
    coarse = evaluate(parameters, scan=FrequencyScan(points=128))
    assert coarse.metrics == pytest.approx(base.metrics, rel=1e-10)
    fs = (base.metrics['UGF_Hz'], base.metrics['BW_Hz'])
    response = evaluate(parameters, response_frequencies_Hz=fs).response
    assert abs(complex(*response[0]['L'])) == pytest.approx(1, abs=1e-11)
    assert abs(complex(*response[1]['T'])) == pytest.approx(2**-.5, abs=1e-11)


@pytest.mark.parametrize('scan', [FrequencyScan(0, 1e8), FrequencyScan(1e8, 1),
                                 FrequencyScan(points=2), FrequencyScan(points=100001)])
def test_invalid_scan(parameters, scan):
    assert evaluate(parameters, scan=scan).status == Status.OUT_OF_DOMAIN


@pytest.mark.parametrize('level', ['M0', 'M2'])
def test_reserved_fidelity_cannot_impersonate_an_evaluator(parameters, level):
    result = UnavailableEvaluator(level).evaluate(MetricRequest(parameters))
    assert result.status == Status.UNSUPPORTED and result.model_level == level
    assert not result.metrics


def test_metric_request_and_partial_result(parameters):
    request = MetricRequest(parameters, metrics=('BW_Hz',))
    assert set(M1Evaluator().evaluate(request).metrics) == {'BW_Hz'}
    assert M1Evaluator().evaluate(replace(request, metrics=('jitter_s',))).status == Status.UNSUPPORTED
    assert M1Evaluator().evaluate(replace(request, metrics=())).status == Status.UNSUPPORTED


@pytest.mark.parametrize('mutation,expected', [
    (lambda request: None, Status.OUT_OF_DOMAIN),
    (lambda request: replace(request, scan=None), Status.OUT_OF_DOMAIN),
    (lambda request: replace(request, metrics=None), Status.UNSUPPORTED),
    (lambda request: replace(request, metrics=(1,)), Status.UNSUPPORTED),
    (lambda request: replace(request, response_frequencies_Hz=None), Status.OUT_OF_DOMAIN),
    (lambda request: replace(request, response_frequencies_Hz=(0,)), Status.OUT_OF_DOMAIN),
])
def test_malformed_public_requests_return_status(parameters, mutation, expected):
    result = M1Evaluator().evaluate(mutation(MetricRequest(parameters)))
    assert result.status == expected and not result.metrics


def test_unknown_semantics_and_missing_values_are_not_inferred(parameters):
    p = deepcopy(parameters)
    p['conventions']['vco_f0'] = 'frequency_at_V0'
    assert evaluate(p).status == Status.UNSUPPORTED
    p = deepcopy(parameters)
    del p['values']['CP_leakage']
    assert evaluate(p).status == Status.OUT_OF_DOMAIN


@pytest.mark.parametrize('mutation', [
    lambda e: e['block_space']['variables']['Icp'].update(unit='uA'),
    lambda e: e['block_space']['variables']['Icp'].update(fixed=1e-4),
    lambda e: e['block_space']['variables']['C1'].update(choices=[]),
    lambda e: e['block_space']['variables']['Rz'].update(range={'min': 0, 'max': 8000}),
    lambda e: e['block_space']['variables']['Kvco'].update(default=1),
    lambda e: e['system_spec'].update(draft=False),
    lambda e: e['system_spec']['metrics'][1].update(protocol='UGF_as_BW'),
    lambda e: e['system_spec']['metrics'][1].update(min=400000),
])
def test_invalid_v2_experiment(exp, mutation):
    mutation(exp)
    with pytest.raises(ValueError):
        validate_experiment(exp)


def test_all_axis_modes_are_consumed_and_membership_checked(exp):
    p = parameters_from_experiment(exp, {'Icp': 120e-6, 'C1': 50e-12, 'N': 8})
    assert p['values']['Icp']['value'] == 120e-6
    for bad in ({'Icp': 1}, {'C1': 75e-12}, {'N': 9}, {'unknown': 1}):
        with pytest.raises(ValueError):
            parameters_from_experiment(exp, bad)


def test_model_ok_can_fail_draft_spec_and_result_binding(exp, parameters):
    r = evaluate(parameters)
    exp['system_spec']['metrics'][2]['min'] = 60
    assert judge_experiment(exp, parameters, r)['verdict'] == 'M1_SPEC_FAIL'
    assert judge_experiment(exp, changed(parameters, 'Icp', 120e-6), r)['verdict'] == 'UNKNOWN'
    r.protocols['BW_Hz'] = 'other_definition'
    assert judge_experiment(exp, parameters, r)['verdict'] == 'UNKNOWN'


def test_reproducible_run_saves_candidates_refuses_overwrite_and_records_failures(tmp_path):
    out = tmp_path/'run'
    manifest = run_stage1(CONFIG, out)
    assert manifest['numerical_acceptance'] == 'PASS'
    assert manifest['cost']['MATLAB_runtime_calls'] == 0
    assert manifest['cost']['M2_behavioral_TB_calls'] == 0
    candidates = json.loads((out/'candidate_snapshots.json').read_text(encoding='utf-8'))
    assert len(candidates) == 5
    failures = json.loads((out/'failure_cases.json').read_text(encoding='utf-8'))
    assert all(row['satisfied'] for row in failures.values())
    with pytest.raises(FileExistsError):
        run_stage1(CONFIG, out)
