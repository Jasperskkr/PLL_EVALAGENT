from copy import deepcopy
from pathlib import Path
import math
import random
import pytest
from pll_allocation.track_a.core import (
    Meter, assess_m1, fingerprint, load_model, make_candidate, proposal, read,
    validate_proposal, values,
)
from pll_allocation.track_a.physics import (
    cheap_predict, inverse_at_shape, phase_interval, pm_ceiling, propagate,
)
from pll_allocation.track_a.allocate import analytical, optimize, perturbation_check, sensitivity
from pll_allocation.track_a.agent import MockPolicy, run_agent
from pll_allocation.track_a.benchmark import build_targets
from pll_allocation.track_a.runner import run_first
from pll_allocation.track_a.repair import repair

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def model():
    return load_model(ROOT/'configs/BLOCK_SPACE_MODEL_V1.json')


@pytest.fixture
def spec(model):
    return deepcopy(model['experiment']['system_spec'])


def test_phase_bound_and_inverse_interval():
    assert pm_ceiling(50e-12, 2e-9) == pytest.approx(72.247209838, abs=1e-8)
    assert phase_interval(200e-12, .5e-9, 50) is None
    for c1, c2 in [(50e-12, 2e-9), (100e-12, 1e-9)]:
        q = 1+c2/c1
        lo, hi = phase_interval(c1, c2, 50)
        for x in (lo, hi):
            assert math.degrees(math.atan(x)-math.atan(x/q)) == pytest.approx(50)
        assert lo*hi == pytest.approx(q)


def test_infeasibility_certificate_not_optimization_failure(model, spec):
    for item in spec['metrics']:
        if item['metric'] == 'PM_deg':
            item['min'] = 75
    result = propagate(model, spec)
    assert result['status'] == 'PROVEN_INFEASIBLE'
    c, meta = analytical(model, spec, Meter())
    assert c is None and meta['status'] == 'PROVEN_INFEASIBLE'


def test_fixed_frequency_conflict_certificate(model, spec):
    spec['metrics'][0]['min'] = spec['metrics'][0]['max'] = 81e6
    assert propagate(model, spec)['certificates'][0]['kind'] == 'FIXED_FREQUENCY_PLAN'


@pytest.mark.parametrize('seed', [2, 8, 17])
def test_dimensionless_predictor_matches_unchanged_m1(model, spec, seed):
    rng = random.Random(seed)
    c = make_candidate(model, {'Icp': rng.uniform(60e-6, 190e-6), 'Kvco': rng.uniform(15e6, 35e6),
        'Rz': rng.uniform(2100, 7900), 'f0': 72e6, 'C1': rng.choice([50e-12, 100e-12, 200e-12]),
        'C2': rng.choice([.5e-9, 1e-9, 2e-9])})
    meter = Meter()
    fast = cheap_predict(model, c, meter)
    full = assess_m1(model, spec, c, meter)['prediction']['metrics']
    for name in ('UGF_Hz', 'BW_Hz', 'PM_deg'):
        assert fast[name] == pytest.approx(full[name], rel=1e-9)
    assert meter.counts['M1_calls'] == meter.counts['analytic_calls'] == 1


def test_inverse_preserves_target_bw_and_full_candidate(model, spec):
    before = fingerprint(model)
    meter = Meter()
    c, meta = analytical(model, spec, meter)
    assert len(c['values']) == 17
    assert type(c['values']['N']['value']) is int
    result = assess_m1(model, spec, c, meter)
    assert result['judgment']['verdict'] == 'M1_SPEC_PASS'
    assert result['prediction']['metrics']['BW_Hz'] == pytest.approx(225e3)
    assert result['prediction']['metrics']['Vctrl_required_V'] == pytest.approx(.6)
    assert result['verified_joint_block_spec'] is False
    assert fingerprint(model) == before


def test_frequency_scale_identity(model, spec):
    base = make_candidate(model)
    p = values(base)
    a = 1.2
    c = make_candidate(model, {'Rz': p['Rz']/a, 'Icp': p['Icp']*a*a})
    old, new = [cheap_predict(model, item, Meter()) for item in (base, c)]
    assert new['PM_deg'] == pytest.approx(old['PM_deg'])
    for name in ('BW_Hz', 'UGF_Hz'):
        assert new[name] == pytest.approx(a*old[name])


def test_product_invariant_and_tuning_coupling(model):
    c1, c2 = make_candidate(model), make_candidate(model, {'Icp': 80e-6, 'Kvco': 25e6})
    a, b = [cheap_predict(model, c, Meter()) for c in (c1, c2)]
    assert a['BW_Hz'] == pytest.approx(b['BW_Hz'])
    assert a['Vctrl_required_V'] != b['Vctrl_required_V']


def test_sensitivity_detects_gain_degeneracy_and_pm_curvature(model, spec):
    meter = Meter()
    info = sensitivity(model, spec, meter)
    a, b = [info['columns'][k] for k in ('Icp', 'Kvco')]
    assert a['log_elasticity']['BW_Hz'] == pytest.approx(b['log_elasticity']['BW_Hz'], abs=1e-8)
    assert info['columns']['Rz']['PM_curvature_log'] < 0
    assert meter.counts['M1_calls'] == 9


def test_optimization_candidate_independently_passes(model, spec):
    meter = Meter()
    c, meta = optimize(model, spec, meter)
    assert c is not None
    assert meta['coordinates'][0] == 'Icp*Kvco/N'
    assert assess_m1(model, spec, c, meter)['judgment']['verdict'] == 'M1_SPEC_PASS'
    assert meter.counts['M1_calls'] <= 16 and meter.counts['analytic_calls'] <= 2000


def test_out_of_domain_never_passes(model, spec):
    c = make_candidate(model, {'f0': 60e6, 'Kvco': 10e6})
    meter = Meter()
    result = assess_m1(model, spec, c, meter)
    assert result['judgment']['verdict'] == 'UNKNOWN'
    assert result['prediction'] is None and meter.counts['M1_calls'] == 0


def test_budget_counts_failed_calls():
    meter = Meter(1, 1)
    def bad():
        raise ValueError('test failure')
    with pytest.raises(ValueError):
        meter.timed('analytic_calls', bad)
    assert meter.counts['analytic_calls'] == 1
    with pytest.raises(RuntimeError, match='BUDGET_EXHAUSTED'):
        meter.timed('analytic_calls', lambda: 1)


def test_proposal_roundtrip_and_hash_tampering(model, spec):
    c, meta = analytical(model, spec, Meter())
    item = proposal(model, spec, c, 'analytical', assess_m1(model, spec, c, Meter()), meta, 'test')
    assert validate_proposal(model, item) == c
    item['joint_block_spec']['values']['Icp']['value'] *= 1.01
    with pytest.raises(ValueError, match='hash'):
        validate_proposal(model, item)


def test_initial_candidate_saved_before_final_assessment(model, spec, tmp_path, monkeypatch):
    import pll_allocation.track_a.runner as runner
    original = runner.assess_m1
    out = tmp_path/'run'
    def checked(*args):
        assert (out/'initial_joint_block_spec.json').exists()
        assert (out/'first_submission.json').exists()
        return original(*args)
    monkeypatch.setattr(runner, 'assess_m1', checked)
    plan = read(ROOT/'configs/track_a/benchmark_plan.json')
    result = run_first(model, spec, 'analytical', out, plan)
    assert result['status'] == 'M1_SPEC_PASS'
    assert result['cost']['M2_calls'] == 0
    with pytest.raises(FileExistsError):
        run_first(model, spec, 'analytical', out, plan)


def test_agent_uses_tools_and_separate_mock_label(model, spec, tmp_path):
    meter = Meter()
    c, meta = run_agent(model, spec, meter, tmp_path, MockPolicy())
    assert c is not None and meta['mock'] and meta['status'] == 'SUBMITTED'
    text = (tmp_path/'agent_trace.jsonl').read_text(encoding='utf-8')
    assert 'SolveInverseAllocation' in text and 'AnalyzeSensitivity' in text and 'OptimizeCandidate' in text
    assert meter.counts['LLM_calls'] == meter.counts['M2_calls'] == 0


def test_variants_do_not_mutate_official_or_domain(model):
    before = fingerprint(model)
    targets = build_targets(model, read(ROOT/'configs/track_a/benchmark_plan.json'))
    assert targets['official'] == model['experiment']['system_spec']
    assert targets['tight_pm'] != targets['official']
    assert fingerprint(model) == before


@pytest.mark.parametrize('kind,action', [
    ('BW', 'COORDINATED_SCALE_REPAIR'), ('PM', 'RESELECT_LF_RATIO_AND_SHAPE'),
    ('TUNING_UNREACHABLE', 'RECENTER_TUNING'), ('COLD_START_CAPTURE', 'CAPTURE_HYPOTHESIS_REQUIRES_M2'),
    ('MODEL_OUT_OF_DOMAIN', 'REQUEST_MODEL_DIAGNOSIS'), ('UNRELIABLE_MEASUREMENT', 'REQUEST_REMEASUREMENT'),
    ('MULTIPLE', 'COUPLED_REALLOCATION')])
def test_feedback_failure_paths(model, spec, kind, action):
    c = make_candidate(model)
    feedback = {'schema_version': 'allocation-feedback-1.0', 'parameter_sha256': fingerprint(c),
        'source': 'SIMULATED', 'kind': kind, 'verdict': 'UNKNOWN' if kind in ('MODEL_OUT_OF_DOMAIN', 'UNRELIABLE_MEASUREMENT') else 'FAIL',
        'measurements': {'BW_Hz': {'value': 310e3, 'unit': 'Hz', 'reliable': True}}}
    new, meta = repair(model, spec, c, feedback, Meter())
    assert meta['action'] == action
    assert meta['real_repair_success'] == 'NOT_MEASURED'
    if kind == 'BW':
        assert values(new)['Rz'] > values(c)['Rz'] and values(new)['Icp'] < values(c)['Icp']


def test_feedback_binding_rejects_wrong_candidate(model, spec):
    with pytest.raises(ValueError, match='binding'):
        repair(model, spec, make_candidate(model), {'schema_version': 'allocation-feedback-1.0',
            'parameter_sha256': 'bad'}, Meter())


@pytest.mark.parametrize('tamper', ['prediction_hash', 'judgment', 'conditions', 'domain', 'missing_prediction', 'margins', 'protocol'])
def test_proposal_attached_evidence_binding(model, spec, tamper):
    c, meta = analytical(model, spec, Meter())
    item = proposal(model, spec, c, 'analytical', assess_m1(model, spec, c, Meter()), meta, 'test')
    if tamper == 'prediction_hash':
        item['M1']['prediction']['parameter_sha256'] = 'bad'
    elif tamper == 'judgment':
        item['M1']['judgment']['verdict'] = 'PASS'
    elif tamper == 'conditions':
        item['operating_conditions']['N'] = {'value': 9, 'unit': '1'}
    elif tamper == 'domain':
        item['M1']['domain']['model_validity'] = 'BAD'
    elif tamper == 'missing_prediction':
        item['M1']['prediction'] = None
    elif tamper == 'margins':
        item['constraint_margins']['minimum_normalized_margin'] = 1e9
    else:
        item['M1']['prediction']['protocols']['BW_Hz'] = 'wrong'
    with pytest.raises(ValueError):
        validate_proposal(model, item)


def test_post_selection_budget_does_not_erase_formal_pass(model, spec, tmp_path):
    plan = read(ROOT/'configs/track_a/benchmark_plan.json')
    plan['cheap_budget'] = 11
    result = run_first(model, spec, 'analytical', tmp_path/'budget', plan)
    assert result['status'] == 'M1_SPEC_PASS'
    assert read(tmp_path/'budget'/'perturbation_diagnostic.json')['status'] == 'SKIPPED_REMAINING_CHEAP_BUDGET'
    assert result['cost']['analytic_calls'] == 11


@pytest.mark.parametrize('kind', ['PM', 'TUNING_UNREACHABLE', 'COLD_START_CAPTURE'])
def test_repair_does_not_resubmit_unchanged_peak_center_candidate(model, spec, kind):
    c, _ = analytical(model, spec, Meter())
    feedback = {'schema_version': 'allocation-feedback-1.0', 'parameter_sha256': fingerprint(c),
                'source': 'SIMULATED', 'kind': kind, 'verdict': 'FAIL'}
    new, info = repair(model, spec, c, feedback, Meter())
    assert new is None
    assert info['action'] == 'NO_CHANGE_REQUEST_M2_DIAGNOSIS'
    assert info['validation_level'] == 'DIAGNOSIS_REQUIRED'


@pytest.mark.parametrize('kind', ['BW', 'PM', 'MODEL_OUT_OF_DOMAIN', 'UNRELIABLE_MEASUREMENT'])
def test_feedback_agent_tool_route_is_explicitly_mock(model, spec, tmp_path, kind):
    from pll_allocation.track_a.feedback_agent import MockRepairPolicy, run_repair_agent
    candidate = make_candidate(model)
    feedback = {'schema_version': 'allocation-feedback-1.0', 'parameter_sha256': fingerprint(candidate),
        'source': 'SIMULATED', 'kind': kind, 'verdict': 'FAIL',
        'measurements': {'BW_Hz': {'value': 310e3, 'unit': 'Hz', 'reliable': True}}}
    result = run_repair_agent(model, spec, candidate, feedback, Meter(), tmp_path/'feedback', MockRepairPolicy())
    assert result['cost']['LLM_calls'] == result['cost']['M2_calls'] == 0
    assert result['real_repair_success_rate'] is None
    assert result['policy'] == 'MOCK_FEEDBACK_POLICY_NOT_LLM'
    assert result['status'] == ('DIAGNOSIS_REQUIRED' if kind in ('MODEL_OUT_OF_DOMAIN', 'UNRELIABLE_MEASUREMENT') else 'REPAIR_STAGED_NOT_M2_VERIFIED')
