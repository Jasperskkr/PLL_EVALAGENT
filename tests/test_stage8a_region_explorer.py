"""Real-M1 acceptance for the decision-controlled six-axis explorer."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from pll_allocation.block_space.contracts import FREE_IDS
from pll_allocation.exploration import run_exploration
from pll_allocation.exploration.contracts import coordinate, judge
from pll_allocation.physics_mapping.model import evaluate
from pll_allocation.region_explorer import RegionExplorer, run_region_exploration
from pll_allocation.region_explorer.assessment import contains_parameters, normalized_point, physical_coordinate
from pll_allocation.region_explorer.contracts import OBJECTIVE, SCHEMA

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def contexts(tmp_path_factory):
    folder = tmp_path_factory.mktemp('stage8a_contexts')
    result = {}
    for name, config in [('global', 'continuous_global_v2'), ('tight', 'continuous_tight_v2'),
                         ('impossible', 'pm_infeasible_v2'), ('continuous', 'continuous_global_v2')]:
        raw = json.loads((ROOT/f'configs/stage7/{config}.json').read_text())
        raw['exploration'].update(sobol_samples=8, physics_seed_count=16, sensitivity_representatives=1,
                                  max_m1_evaluations=64)
        if name == 'continuous':
            raw['parameters']['C1']['default'] = 73e-12
            raw['parameters']['C2']['default'] = 1.37e-9
            raw['exploration'].update(sobol_samples=0, physics_seed_count=1)
        source = folder/(name+'.json')
        source.write_text(json.dumps(raw), encoding='utf-8')
        out = folder/name
        run_exploration(source, out)
        result[name] = out/'physics_context.json'
    return result


def decision(explorer, *, method='SOBOL', budget=16, active=None, region_index=0):
    region = explorer.context['candidate_regions'][region_index]
    sid = region['representative_evidence_id']
    return {'schema_version': SCHEMA, 'decision_id': 'D01', 'context_sha256': explorer.context['context_sha256'],
        'action': 'PROBE' if method == 'SOBOL' else 'OPTIMIZE',
        'region': {'region_id': region['region_id'], 'parent_region_id': None},
        'normalized_bounds': deepcopy(region['normalized_bounds']), 'active_variables': list(active or FREE_IDS),
        'seed_ids': [sid], 'm1_budget': budget, 'objective': OBJECTIVE, 'reason': 'Explicit test decision; no LLM',
        'evidence_ids': [sid], 'random_seed': 20261110, 'search_method': method,
        'settings': {'sample_count': 8} if method == 'SOBOL' else {'maxiter': 30, 'finite_difference_step': 1e-5}}


def explorer(contexts, tmp_path, case='global', budget=96):
    return RegionExplorer(contexts[case], tmp_path/'run', m1_budget=budget)


def test_readonly_assessment_does_not_run_m1(contexts, tmp_path, monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError('read-only loading must not evaluate')
    monkeypatch.setattr('pll_allocation.region_explorer.explorer.evaluate', forbidden)
    x = explorer(contexts, tmp_path)
    assert x.counts['M1_calls'] == 0
    assert x.assessment['unknown_space']['normalized_design_domain'] == {k: [0., 1.] for k in FREE_IDS}
    for r in x.assessment['regions']:
        assert not r['whole_region_M1_certified']
        assert r['support_count'] == sum(len(ids) for ids in r['sample_groups'].values())
        assert r['representative']['representative_evidence_id'] in r['evidence_ids']
    x.close()


@pytest.mark.parametrize('case', ['global', 'tight', 'continuous'])
def test_probe_and_real_continuous_slsqp(contexts, tmp_path, case):
    x = explorer(contexts, tmp_path, case, 110)
    d = decision(x, budget=12, region_index=min(1, len(x.context['candidate_regions'])-1))
    first = x.execute(d)
    d.update(decision_id='D02', action='OPTIMIZE', search_method='SLSQP', m1_budget=90,
             settings={'maxiter': 30, 'finite_difference_step': 1e-5})
    obs = x.execute(d)
    assert obs['final_recheck_status'] == 'OK'
    assert all(r['status'] != 'SOLVER_EXCEPTION' for r in obs['solver_runs'])
    assert obs['cost']['M1_calls'] <= 90
    assert obs['latest_minimum_normalized_margin'] >= obs['original_minimum_normalized_margin']
    final = x.evidence[obs['final_recheck_evidence_id']]
    assert obs['best_candidate']['parameters']
    independent = evaluate(final['parameters'])
    assert independent.metrics == final['metrics']
    assert judge(x.problem, final['parameters'], independent) == final['judgment']
    for row in x.rows:
        assert contains_parameters(x.problem, d['normalized_bounds'], row['parameters'])
        assert row['decision_id'] in {'D01', 'D02'}
    assert len({r['parameters']['values']['C1']['value'] for r in x.rows}) > 2
    assert len({r['parameters']['values']['C2']['value'] for r in x.rows}) > 2
    assert first['cost']['M1_calls'] <= 12
    result = x.close()
    assert result['cost']['M1_calls'] <= 110 and result['M2_calls'] == result['LLM_calls'] == 0


def test_impossible_probes_are_necessary_rejections_not_pass(contexts, tmp_path):
    x = explorer(contexts, tmp_path, 'impossible', 8)
    assert not x.assessment['regions']
    d = {'schema_version': SCHEMA, 'decision_id': 'impossible', 'context_sha256': x.context['context_sha256'],
        'action': 'PROBE', 'region': {'region_id': 'NEW_FULL', 'parent_region_id': None},
        'normalized_bounds': {k: [0., 1.] for k in FREE_IDS}, 'active_variables': list(FREE_IDS),
        'seed_ids': [], 'm1_budget': 8, 'objective': OBJECTIVE, 'reason': 'Probe proven PM contradiction',
        'evidence_ids': [], 'random_seed': 4, 'search_method': 'SOBOL', 'settings': {'sample_count': 8}}
    o = x.execute(d)
    assert o['status'] == 'NO_M1_FEASIBLE_OBSERVED'
    assert x.counts['M1_calls'] == 0 and len(o['failures_and_unknowns']) == 8
    assert all(r['judgment']['m1_feasibility'] == 'UNKNOWN' for r in x.rows)
    x.close()


@pytest.mark.parametrize('mutation,match', [
    (lambda d: d['normalized_bounds']['C1'].__setitem__(0, -.01), 'inside original domain'),
    (lambda d: d['active_variables'].append('C3'), 'active variables'),
    (lambda d: d['seed_ids'].__setitem__(0, 'fake'), 'seed_ids'),
    (lambda d: d['evidence_ids'].append('fake'), 'evidence_ids'),
    (lambda d: d.update(m1_budget=1000), 'remaining M1 budget'),
    (lambda d: d.update(m1_budget=True), 'remaining M1 budget'),
    (lambda d: d.update(context_sha256='fake'), 'binding'),
    (lambda d: d.update(objective='BW_ONLY'), 'hard constraints'),
    (lambda d: d.update(model='fake'), 'unknown fields'),
    (lambda d: d['normalized_bounds']['C2'].__setitem__(0, float('nan')), 'finite'),
    (lambda d: d['region'].update(parent_region_id='fake'), 'parent'),
    (lambda d: d.update(search_method='SLSQP'), 'PROBE uses'),
])
def test_invalid_decisions_have_no_calls(contexts, tmp_path, mutation, match):
    x = explorer(contexts, tmp_path)
    d = decision(x)
    mutation(d)
    with pytest.raises(ValueError, match=match):
        x.execute(d)
    assert x.counts['M1_calls'] == 0 and not x.observations
    x.close()


def test_out_of_region_seed_and_illegal_fixed_seed(contexts, tmp_path):
    x = explorer(contexts, tmp_path)
    d = decision(x, active=['C1'])
    d['region']['region_id'] = 'new'
    d['normalized_bounds']['C1'] = [.9, 1.]
    with pytest.raises(ValueError, match='seed outside'):
        x.execute(d)
    d = decision(x, active=['C1'])
    sid = d['seed_ids'][0]
    x.evidence[sid] = deepcopy(x.evidence[sid])
    x.evidence[sid]['parameters']['values']['N']['value'] = 9
    with pytest.raises(ValueError, match='illegal seed/fixed'):
        x.execute(d)
    x.close()


def test_subset_freezes_other_values_exactly(contexts, tmp_path):
    x = explorer(contexts, tmp_path, 'continuous', 50)
    d = decision(x, method='SLSQP', budget=40, active=['C1', 'C2'])
    x.execute(d)
    base = x.evidence[d['seed_ids'][0]]['parameters']['values']
    for r in x.rows:
        assert all(r['parameters']['values'][k] == base[k] for k in FREE_IDS if k not in ('C1', 'C2'))
    x.close()


def test_two_seed_multistart_uses_decision_bounds(contexts, tmp_path):
    x = explorer(contexts, tmp_path, budget=90)
    d = decision(x, method='SLSQP', budget=80)
    d['normalized_bounds'] = {k: [0., 1.] for k in FREE_IDS}
    d['region']['region_id'] = 'multi'
    d['seed_ids'] = [r['representative_evidence_id'] for r in x.context['candidate_regions'][:2]]
    d['settings']['maxiter'] = 1
    o = x.execute(d)
    assert len(o['solver_runs']) == len(d['seed_ids'])
    assert all(set(run['bounds']) == set(FREE_IDS) for run in o['solver_runs'])
    x.close()


def test_tiny_budget_counts_differences_and_recheck(contexts, tmp_path):
    x = explorer(contexts, tmp_path, budget=2)
    o = x.execute(decision(x, method='SLSQP', budget=2))
    assert x.counts['M1_calls'] == 2
    assert o['budget_exhausted']
    final = x.evidence[o['final_recheck_evidence_id']]
    assert final['formal_M1_called'] and final['independent_final_recheck']
    x.close()


def test_failures_charged_and_unknown(contexts, tmp_path, monkeypatch):
    x = explorer(contexts, tmp_path, budget=3)
    def broken(*args, **kwargs):
        raise ArithmeticError('injected numeric failure')
    monkeypatch.setattr('pll_allocation.region_explorer.explorer.evaluate', broken)
    d = decision(x, budget=3)
    d['settings']['sample_count'] = 16
    o = x.execute(d)
    assert x.counts['M1_calls'] == x.counts['M1_failures'] == 3
    assert o['budget_exhausted']
    assert any('injected numeric' in r['reason'] for r in x.rows if r['M1_status'] == 'EVALUATOR_EXCEPTION')
    assert all(r['judgment']['m1_feasibility'] == 'UNKNOWN' for r in x.rows)
    x.close()


def test_solver_exception_reported(contexts, tmp_path, monkeypatch):
    x = explorer(contexts, tmp_path)
    def broken(*a, **k):
        raise RuntimeError('injected solver failure')
    monkeypatch.setattr('scipy.optimize.minimize', broken)
    o = x.execute(decision(x, method='SLSQP', budget=10))
    assert o['solver_runs'][0]['status'] == 'SOLVER_EXCEPTION'
    assert o['final_recheck_status'] == 'OK'
    assert o['cost']['M1_calls'] == 1
    x.close()


def test_duplicate_and_stop_enforced(contexts, tmp_path):
    x = explorer(contexts, tmp_path)
    d = decision(x)
    x.execute(d)
    with pytest.raises(ValueError, match='duplicate decision_id'):
        x.execute(d)
    d['decision_id'] = 'renamed'
    d['reason'] = 'different reason'
    d['region']['region_id'] = 'renamed'
    with pytest.raises(ValueError, match='duplicate effective'):
        x.execute(d)
    d.update(action='STOP', m1_budget=0, active_variables=[], seed_ids=[], settings={}, search_method='NONE')
    assert x.execute(d)['status'] == 'STOPPED'
    d['decision_id'] = 'after_stop'
    with pytest.raises(ValueError, match='STOPPED'):
        x.execute(d)
    x.close()


def test_refine_expand_switch_and_new_unknown_region(contexts, tmp_path):
    x = explorer(contexts, tmp_path)
    d = decision(x, budget=8)
    rid = d['region']['region_id']
    bounds = deepcopy(d['normalized_bounds'])
    point = normalized_point(x.problem, x.evidence[d['seed_ids'][0]]['parameters'])
    d.update(action='REFINE')
    d['region'] = {'region_id': 'smaller', 'parent_region_id': rid}
    d['normalized_bounds'] = {k: [(lo+point[k])/2, (hi+point[k])/2] for k, (lo, hi) in bounds.items()}
    x.execute(d)
    d.update(decision_id='expand', action='EXPAND')
    d['region'] = {'region_id': 'larger', 'parent_region_id': 'smaller'}
    d['normalized_bounds'] = bounds
    x.execute(d)
    d.update(decision_id='switch', action='SWITCH', random_seed=3)
    d['region'] = {'region_id': 'unknown_full', 'parent_region_id': None}
    d['normalized_bounds'] = {k: [0., 1.] for k in FREE_IDS}
    x.execute(d)
    assert 'unknown_full' in x.regions
    d.update(decision_id='bad_switch')
    with pytest.raises(ValueError, match='different region'):
        x.execute(d)
    x.close()


def test_identical_seed_and_input_reproduce_scientific_digest(contexts, tmp_path):
    results, samples = [], []
    for name in ('a', 'b'):
        x = RegionExplorer(contexts['continuous'], tmp_path/name, m1_budget=50)
        x.execute(decision(x, budget=8))
        d = decision(x, method='SLSQP', budget=40)
        d['decision_id'] = 'opt'
        x.execute(d)
        results.append(x.close())
        samples.append([{k: v for k, v in r.items() if k != 'cost'} for r in x.rows])
    assert samples[0] == samples[1]
    assert results[0]['scientific_sha256'] == results[1]['scientific_sha256']


def test_saved_stage7_hash_and_output_protection(contexts, tmp_path):
    x = explorer(contexts, tmp_path)
    with pytest.raises(FileExistsError):
        RegionExplorer(contexts['global'], tmp_path/'run', m1_budget=10)
    x.problem['parameters']['C1']['min'] *= 2
    with pytest.raises(ValueError, match='mutated'):
        x.validate(decision(x))


def test_batch_shared_interface(contexts, tmp_path):
    x = RegionExplorer(contexts['global'], tmp_path/'draft', m1_budget=16)
    d = decision(x)
    x.close()
    source = tmp_path/'decisions.json'
    source.write_text(json.dumps([d]), encoding='utf-8')
    r = run_region_exploration(contexts['global'], source, tmp_path/'batch', m1_budget=16)
    assert r['status'] == 'COMPLETED'
    assert (tmp_path/'batch/region_assessment.json').is_file()


def test_cache_deduplicates_exact_points_without_quantization(contexts, tmp_path, monkeypatch):
    import numpy as np
    x = explorer(contexts, tmp_path, 'continuous', 8)
    class Repeated:
        def __init__(self, **kw):
            pass
        def random_base2(self, power):
            a = [.5]*6
            b = a.copy()
            b[2] += 1e-12
            return np.array([a, a, b, b])
    monkeypatch.setattr('scipy.stats.qmc.Sobol', Repeated)
    d = decision(x, budget=8)
    d['settings']['sample_count'] = 3
    x.execute(d)
    assert x.counts['M1_calls'] == 2 and x.counts['cache_hits'] == 1
    assert x.rows[1]['duplicate_of'] == x.rows[0]['evidence_id']
    assert x.rows[2]['parameter_sha256'] != x.rows[0]['parameter_sha256']
    x.close()


def test_true_model_numerical_failure_counted_not_pass(tmp_path):
    raw = json.loads((ROOT/'configs/stage7/continuous_global_v2.json').read_text())
    raw['parameters']['Icp'].update(min=5e-301, max=2e-300, default=1e-300)
    raw['exploration'].update(sobol_samples=0, physics_seed_count=1, sensitivity_representatives=0)
    src = tmp_path/'underflow.json'
    src.write_text(json.dumps(raw))
    run_exploration(src, tmp_path/'stage7_numeric')
    x = RegionExplorer(tmp_path/'stage7_numeric/physics_context.json', tmp_path/'stage8a_numeric', m1_budget=4)
    # Narrow the other coordinates around the legal default, so tuning and the
    # ideal PM ceiling pass, leaving the real M1 underflow as the failure source.
    from pll_allocation.exploration.contracts import make_parameters
    point = normalized_point(x.problem, make_parameters(x.problem))
    bounds = {k: [max(0., u-.001), min(1., u+.001)] for k, u in point.items()}
    d = {'schema_version': SCHEMA, 'decision_id': 'numeric', 'context_sha256': x.context['context_sha256'],
        'action': 'PROBE', 'region': {'region_id': 'numeric', 'parent_region_id': None},
        'normalized_bounds': bounds, 'active_variables': list(FREE_IDS), 'seed_ids': [], 'm1_budget': 4,
        'objective': OBJECTIVE, 'reason': 'Real underflow test', 'evidence_ids': [], 'random_seed': 1,
        'search_method': 'SOBOL', 'settings': {'sample_count': 3}}
    x.execute(d)
    assert x.counts['M1_failures'] == x.counts['M1_calls'] == 3
    assert all(r['M1_status'] == 'NUMERICAL_FAILURE' and r['reason'] for r in x.rows)
    assert all(r['judgment']['m1_feasibility'] == 'UNKNOWN' for r in x.rows)
    x.close()


def test_exact_region_endpoints_are_not_rejected_by_log_roundtrip(contexts, tmp_path, monkeypatch):
    import numpy as np
    x = explorer(contexts, tmp_path, 'continuous', 4)
    class Corners:
        def __init__(self, **kw):
            pass
        def random_base2(self, power):
            return np.array([[0.]*6, [1.]*6])
    monkeypatch.setattr('scipy.stats.qmc.Sobol', Corners)
    d = decision(x, budget=4)
    d['settings']['sample_count'] = 2
    x.execute(d)
    assert all(r['M1_status'] != 'NOT_EVALUATED_OUTSIDE_DECISION_REGION' for r in x.rows)
    x.close()


def test_tiny_positive_log_coordinate_cannot_round_below_user_minimum(contexts, tmp_path):
    x = explorer(contexts, tmp_path, 'tight')
    axis = x.problem['parameters']['C1']
    assert coordinate(axis, 1e-18, inverse=True) < axis['min']  # real Stage7 inverse roundoff
    assert physical_coordinate(axis, 1e-18) == axis['min']
    d = decision(x, method='SLSQP', budget=8)
    d['region']['region_id'] = 'NUMERIC_ENDPOINT_TEST'
    d['normalized_bounds'] = {k: [0., 1.] for k in FREE_IDS}
    x.validate(d)
    active = list(FREE_IDS)
    u = normalized_point(x.problem, x.evidence[d['seed_ids'][0]]['parameters'])
    u['C1'] = 1e-18
    candidate = x._decode(d, x.evidence[d['seed_ids'][0]]['parameters'], active, [u[k] for k in active])
    assert candidate['values']['C1']['value'] == axis['min']
    assert x.counts['coordinate_endpoint_corrections'] == 1
    with pytest.raises(ValueError, match='outside decision bounds'):
        x._decode(d, x.evidence[d['seed_ids'][0]]['parameters'], ['C1'], [-1e-18])
    x.close()


@pytest.mark.parametrize('flag,value', [('--m2-budget', '1'), ('--seed', '3'), ('--explore-problem', 'x')])
def test_cli_refuses_mixed_modes(contexts, tmp_path, flag, value):
    from pll_allocation.pipeline import main
    assert main(['--out', str(tmp_path/'bad'), '--region-context', str(contexts['global']),
                 '--search-decisions', 'unused.json', '--region-m1-budget', '10', flag, value]) == 2
    assert not (tmp_path/'bad').exists()


def test_cli_routes_to_shared_explorer(contexts, tmp_path):
    from pll_allocation.pipeline import main
    x = RegionExplorer(contexts['continuous'], tmp_path/'draft', m1_budget=8)
    d = decision(x, budget=8)
    x.close()
    file = tmp_path/'decisions.json'
    file.write_text(json.dumps([d]))
    assert main(['--out', str(tmp_path/'cli'), '--region-context', str(contexts['continuous']),
                 '--search-decisions', str(file), '--region-m1-budget', '8']) == 0
    assert (tmp_path/'cli/planner_state.json').is_file()
