"""Stage7 continuous-domain acceptance; numerical tests use the real formal M1."""
from copy import deepcopy
import json
import math
from pathlib import Path

import pytest

from pll_allocation.exploration import (
    check_candidate, load_physics_context, load_problem, make_parameters, resolve_problem, run_exploration,
)
from pll_allocation.exploration.contracts import coordinate, judge, screen_problem
from pll_allocation.physics_mapping.model import evaluate, fingerprint
from pll_allocation.physics_mapping.validation import HISTORICAL_ANCHOR
from pll_allocation.pipeline_contracts import load_inputs
from pll_allocation.block_space.contracts import check_parameters

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT/'configs/stage7/continuous_global_v2.json'


def raw():
    return json.loads(CONFIG.read_text(encoding='utf-8'))


def small():
    p = raw()
    p['exploration'].update(sobol_samples=16, physics_seed_count=6, region_count=2,
                            sensitivity_representatives=1, max_m1_evaluations=48)
    return p


def run(tmp_path, p=None, folder='run', **kwargs):
    path = tmp_path/(folder+'_problem.json')
    path.write_text(json.dumps(p or small()), encoding='utf-8')
    result = run_exploration(path, tmp_path/folder, **kwargs)
    assert result['failure'] is None
    return result, tmp_path/folder


def records(folder):
    return [json.loads(line) for line in (folder/'m1_samples.jsonl').read_text(encoding='utf-8').splitlines()]


def test_nominal_unchanged_and_continuous_nonchoices_supported():
    p = load_problem(CONFIG)
    c = make_parameters(p)
    nominal = evaluate(c)
    assert nominal.status.value == 'OK'
    for metric, value in HISTORICAL_ANCHOR.items():
        assert nominal.metrics[metric] == pytest.approx(value, rel=1e-11)
    continuous = make_parameters(p, {'C1': 73e-12, 'C2': 1.37e-9})
    assert check_candidate(p, continuous)['status'] == 'NECESSARY_CONDITIONS_SATISFIED'
    assert evaluate(continuous).status.value == 'OK'
    _, frozen, _, _ = load_inputs()
    assert check_parameters(frozen, continuous)['declared_domain'] == 'OUT_OF_DECLARED_DOMAIN'


def test_spec_changes_toggle_and_pending_are_respected():
    p = load_problem(CONFIG)
    c = make_parameters(p)
    result = evaluate(c)
    first = judge(p, c, result)
    assert first['m1_feasibility'] == 'FEASIBLE'
    assert first['constraints'][0]['bound_margins']['min'] == pytest.approx(result.metrics['BW_Hz']-150000)
    assert first['constraints'][0]['bound_margins']['max'] == pytest.approx(300000-result.metrics['BW_Hz'])
    assert first['all_enabled_specs_status'] == 'UNKNOWN'
    assert [s['status'] for s in first['constraints'][2:]] == ['UNKNOWN', 'UNKNOWN']
    modified = raw()
    modified['specs'][0].update(min=200000, max=210000)
    modified['specs'][1]['min'] = 70
    updated = judge(resolve_problem(modified), c, result)
    assert updated['m1_feasibility'] == 'INFEASIBLE'
    assert all(s['status'] == 'VIOLATED' for s in updated['constraints'][:2])
    modified['specs'][0]['enabled'] = modified['specs'][1]['enabled'] = False
    disabled = judge(resolve_problem(modified), c, result)
    assert disabled['m1_feasibility'] == 'NOT_REQUESTED'
    assert disabled['all_enabled_specs_status'] == 'UNKNOWN'
    assert not disabled['verified_joint_block_spec']


def test_configurable_fixed_plan_uses_existing_model():
    p = raw()
    p['fixed_parameters']['N']['value'] = 9
    p['fixed_parameters']['f_ref']['value'] = 9e6
    p = resolve_problem(p)
    c = make_parameters(p)
    assert check_candidate(p, c)['status'] == 'NECESSARY_CONDITIONS_SATISFIED'
    assert evaluate(c).metrics['output_frequency_Hz'] == 81e6


def test_pm_necessary_condition_and_global_certificate():
    p = raw()
    p['parameters']['C1'].update(min=99e-12, max=101e-12)
    p['parameters']['C2'].update(min=.99e-9, max=1.01e-9)
    p['specs'][1]['min'] = 70
    p = resolve_problem(p)
    screening = screen_problem(p)
    expected = math.degrees(math.asin(1.01e-9/(2*99e-12+1.01e-9)))
    assert screening['global_PM_ceiling_deg'] == pytest.approx(expected)
    assert screening['status'] == 'PROVEN_M1_INFEASIBLE'
    assert check_candidate(p, make_parameters(p))['status'] == 'NECESSARY_CONDITION_FAIL'


@pytest.mark.parametrize('name,value', [('Icp', 0), ('Rz', -1), ('C1', float('nan')),
                                      ('C2', float('inf')), ('f0', 1), ('Kvco', -1)])
def test_invalid_candidate_never_passes(name, value):
    p = load_problem(CONFIG)
    c = make_parameters(p)
    c['values'][name]['value'] = value
    assert check_candidate(p, c)['status'] == 'INVALID_CANDIDATE'


def test_units_fixed_inputs_and_tuning_gate():
    p = load_problem(CONFIG)
    c = make_parameters(p)
    c['values']['C1']['unit'] = 'pF'
    assert check_candidate(p, c)['status'] == 'INVALID_CANDIDATE'
    c = make_parameters(p, {'f0': 40e6, 'Kvco': 5e6})
    assert check_candidate(p, c)['status'] == 'INVALID_CANDIDATE'
    c = make_parameters(p)
    c['values']['N']['value'] = 9
    assert check_candidate(p, c)['status'] == 'INVALID_CANDIDATE'


@pytest.mark.parametrize('change', [
    lambda p: p['parameters']['C1'].update(min=0),
    lambda p: p['parameters']['C2'].update(scale='choices'),
    lambda p: p['parameters']['Icp'].update(default=1),
    lambda p: p['specs'][0].update(min=4e5, max=1e5),
    lambda p: p['specs'][1].update(enabled=1),
    lambda p: p['specs'][1].update(normalization_scale=0),
    lambda p: p['fixed_parameters']['N'].update(value=8.),
    lambda p: p['fixed_parameters']['q0'].update(value=1e-14),
    lambda p: p['exploration'].update(max_m1_evaluations=0),
    lambda p: p['exploration'].update(seed=True),
])
def test_bad_config_rejected(change):
    p = raw()
    change(p)
    with pytest.raises(ValueError):
        resolve_problem(p)


def test_feasible_exploration_has_regions_stencils_and_context(tmp_path):
    result, folder = run(tmp_path)
    assert result['status'] == 'M1_FEASIBLE_SAMPLES_FOUND'
    assert result['cost']['M1_calls'] <= 48
    assert result['cost']['M2_calls'] == result['cost']['LLM_calls'] == 0
    assert result['cost']['candidate_generations'] == result['cost']['proposals']
    context = load_physics_context(folder/'physics_context.json')
    evidence = {r['evidence_id']: r for r in records(folder)}
    for region in context['candidate_regions']:
        assert region['representative_evidence_id'] in evidence
        assert not region['whole_region_M1_certified']
        assert region['support_evidence_ids']
        for name, bound in region['bounds'].items():
            axis = context['problem']['parameters'][name]
            assert axis['min'] <= bound['min'] <= bound['max'] <= axis['max']
    columns = context['sensitivity']['representatives'][0]['columns']
    assert set(columns) == {'Icp', 'Rz', 'C1', 'C2', 'f0', 'Kvco'}
    assert all(c['status'] == 'OK' for c in columns.values())
    assert columns['Icp']['log_elasticity']['BW_Hz'] == pytest.approx(columns['Kvco']['log_elasticity']['BW_Hz'], rel=3e-3)
    assert not context['capability_boundary']['M2_executed']
    assert result['unsupported_or_pending_enabled_specs'] == ['lock_time_s', 'jitter_s']
    assert all(evidence[e]['M1_status'] == 'OK' for c in columns.values() for e in c['evidence_ids'])
    for name in ('problem_resolved.json', 'physics_screening.json', 'm1_samples.csv', 'candidate_regions.json',
                 'sensitivity.json', 'stage7_report.md', 'run_events.jsonl'):
        assert (folder/name).is_file()


def test_infeasible_proof_and_not_found_are_distinct(tmp_path):
    p = small()
    p['specs'][1]['min'] = 95
    impossible, folder = run(tmp_path, p, 'impossible')
    assert impossible['status'] == 'PROVEN_M1_INFEASIBLE'
    assert impossible['cost']['M1_calls'] == 0
    assert records(folder) == []
    p = small()
    p['specs'][0].update(min=1e9, max=2e9)
    not_found, folder = run(tmp_path, p, 'not_found')
    assert not_found['status'] == 'NO_M1_FEASIBLE_SAMPLE_FOUND'
    assert not_found['cost']['M1_calls'] > 0


def test_reproducible_sampling_and_science_digest(tmp_path):
    first, a = run(tmp_path, folder='a')
    second, b = run(tmp_path, folder='b')
    assert first['scientific_sha256'] == second['scientific_sha256']
    assert (a/'m1_samples.jsonl').read_bytes() == (b/'m1_samples.jsonl').read_bytes()
    changed, _ = run(tmp_path, folder='changed', seed=19)
    assert changed['scientific_sha256'] != first['scientific_sha256']


def test_exact_dedup_without_rounding_or_extra_m1(tmp_path, monkeypatch):
    import numpy as np
    from scipy.stats import qmc
    class RepeatedDraws:
        def __init__(self, **kwargs): pass
        def random_base2(self, m):
            rows = np.full((4, 6), .5)
            rows[2:, 0] += 1e-13
            return rows
    monkeypatch.setattr(qmc, 'Sobol', RepeatedDraws)
    p = small()
    p['exploration'].update(sobol_samples=3, physics_seed_count=0, sensitivity_representatives=0)
    result, folder = run(tmp_path, p)
    rows = records(folder)
    assert result['cost']['duplicates'] == 1
    assert result['cost']['M1_calls'] == 2
    assert rows[0]['parameter_sha256'] != rows[2]['parameter_sha256']
    assert rows[1]['duplicate_of'] == rows[0]['evidence_id']


def test_budget_exhaustion_retains_unevaluated_rows(tmp_path):
    result, folder = run(tmp_path, budget=1, seed=0)
    assert result['cost']['M1_calls'] == 1
    assert result['cost']['M1_budget_skips'] > 0
    assert result['M1_budget_exhausted']
    assert any(r['M1_status'] == 'NOT_EVALUATED_M1_BUDGET_EXHAUSTED' for r in records(folder))
    assert any(c['status'] == 'DOMAIN_OR_BUDGET_LIMITED' for d in
               json.loads((folder/'sensitivity.json').read_text())['representatives'] for c in d['columns'].values())


def test_numerical_failure_keeps_reason_and_cannot_use_cheap_as_pass(tmp_path):
    p = small()
    p['parameters']['Icp'].update(min=5e-301, max=2e-300, default=1e-300)
    p['exploration'].update(sobol_samples=0, physics_seed_count=1, sensitivity_representatives=0)
    result, folder = run(tmp_path, p)
    row = records(folder)[0]
    assert row['M1_status'] == 'NUMERICAL_FAILURE'
    assert row['formal_M1_result']['reason']
    assert row['judgment']['m1_feasibility'] == 'UNKNOWN'
    assert result['cost']['M1_failures'] == 1
    assert result['exploration_feasible_samples'] == 0


def test_context_tampering_and_existing_output_are_rejected(tmp_path):
    _, folder = run(tmp_path)
    with pytest.raises(FileExistsError):
        run_exploration(tmp_path/'run_problem.json', folder)
    (folder/'candidate_regions.json').write_text('{}')
    with pytest.raises(ValueError, match='evidence binding'):
        load_physics_context(folder/'physics_context.json')


def test_cli_is_formal_pipeline_route_and_mixed_mode_rejected(tmp_path):
    from pll_allocation.pipeline import main
    p = small()
    p['exploration'].update(sobol_samples=1, physics_seed_count=1, sensitivity_representatives=0)
    path = tmp_path/'input.json'
    path.write_text(json.dumps(p))
    assert main(['--explore-problem', str(path), '--out', str(tmp_path/'cli'), '--seed', '0', '--exploration-budget', '1']) == 0
    assert (tmp_path/'cli/physics_context.json').is_file()
    assert main(['--explore-problem', str(path), '--out', str(tmp_path/'bad'), '--m2-budget', '0']) == 2
    assert not (tmp_path/'bad').exists()


def test_log_and_linear_scales():
    p = load_problem(CONFIG)
    axis = p['parameters']['Icp']
    assert coordinate(axis, .5, inverse=True) == pytest.approx(math.sqrt(axis['min']*axis['max']))
    axis = p['parameters']['f0']
    assert coordinate(axis, .5, inverse=True) == pytest.approx((axis['min']+axis['max'])/2)


def test_global_tuning_contradiction_is_m1_only():
    p = raw()
    p['parameters']['f0'].update(min=40e6, max=50e6, default=45e6)
    p['parameters']['Kvco'].update(min=5e6, max=10e6, default=8e6)
    screen = screen_problem(resolve_problem(p))
    assert screen['status'] == 'PROVEN_M1_INFEASIBLE'
    assert screen['certificates'][0]['kind'] == 'GLOBAL_TUNING_UNREACHABLE'


def test_no_m1_constraints_never_yields_vacuous_feasible_regions(tmp_path):
    p = small()
    p['specs'][0]['enabled'] = p['specs'][1]['enabled'] = False
    p['exploration'].update(sobol_samples=2, physics_seed_count=1)
    result, folder = run(tmp_path, p)
    assert result['status'] == 'M1_NOT_REQUESTED'
    assert result['region_count'] == 0
    assert all(r['judgment']['all_enabled_specs_status'] == 'UNKNOWN' for r in records(folder))


def test_capability_cannot_be_upgraded_by_requesting_m1_jitter():
    p = raw()
    p['specs'][3]['evaluation_source'] = 'M1'
    p = resolve_problem(p)
    c = make_parameters(p)
    result = judge(p, c, evaluate(c))
    assert result['constraints'][3]['support_status'] == 'UNSUPPORTED'
    assert result['constraints'][3]['status'] == 'UNKNOWN'


def test_default_int_and_float_are_one_exact_numeric_proposal():
    p = load_problem(CONFIG)
    a = make_parameters(p, {'Rz': 3820})
    b = make_parameters(p, {'Rz': 3820.})
    c = make_parameters(p, {'Rz': math.nextafter(3820., math.inf)})
    assert fingerprint(a) == fingerprint(b)
    assert fingerprint(a) != fingerprint(c)


def test_unsupported_evaluation_reason_is_traceable_and_no_overwrite(tmp_path):
    p = small()
    p['exploration'].update(sobol_samples=0, physics_seed_count=1, max_analytic_calls=0, sensitivity_representatives=0)
    result, folder = run(tmp_path, p)
    assert result['cost']['analytic_calls'] == 0
    assert result['cost']['M1_calls'] == 1
    events = [json.loads(line) for line in (folder/'run_events.jsonl').read_text().splitlines()]
    proposed = next(i for i, e in enumerate(events) if e['event'] == 'CANDIDATE_PROPOSED')
    evaluated = next(i for i, e in enumerate(events) if e['event'] == 'CANDIDATE_RECORDED')
    assert proposed < evaluated
    assert len(events[proposed]['parameters']['values']) == 17
