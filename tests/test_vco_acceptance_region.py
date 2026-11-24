"""Discrete budgets/domain gates/evidence tiers for opt-in VCO probes."""
from copy import deepcopy
from pathlib import Path

import pytest

from pll_allocation.agent.spec_allocation import run_spec_allocation
from pll_allocation.exploration.contracts import load_problem
from pll_allocation.vco_sizing.region import analyze_vco_acceptance_region

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def source(tmp_path_factory):
    r = run_spec_allocation(ROOT/'configs/problems/nominal.json', tmp_path_factory.mktemp('region_source')/'run',
        config={'schema_version': 'pll-spec-allocation-1.0', 'target_count': 3, 'm1_budget': 20,
                'initial_search_m1_budget': 16, 'm2_budget': 0})
    return r['candidates'][0], load_problem(ROOT/'configs/problems/nominal.json')


def probe(source, out, **kwargs):
    candidate, problem = source
    return analyze_vco_acceptance_region(candidate, problem=problem, out=out, experiment_id='TEST:VCO-region', **kwargs)


def test_discrete_m1_budget_leaves_unexecuted_m2_unknown(source, tmp_path):
    c, _ = source; kv = c['parameters']['values']['Kvco']['value']
    before = deepcopy(c)
    r = probe(source, tmp_path/'probe', kvco_values=[kv*.6, kv, kv*2], vlock_values=[.3, .6, .9],
              m1_budget=2, sample_budget=5)
    assert r['budget']['M1_calls'] == 2 and r['budget']['M2_calls'] == 0
    assert len(r['points']) == 9 and len(r['unverified_points']) == 9
    assert r['M2_passed_points'] == r['M2_failed_points'] == []
    assert any(p['sampling_status'] == 'NOT_EVALUATED_BUDGET' for p in r['points'])
    assert 'NO_CONTINUOUS' in r['unverified_region'] and c == before
    for point in r['points']:
        if 'constraint_margins' in point:
            lock = next(x for x in point['constraint_margins'] if x['metric'] == 'lock_time_s')
            assert lock['status'] == 'UNKNOWN' and lock['support_status'] == 'PENDING_M2'


def test_m1_fail_is_separate_from_domain_rejection_and_unrun_m2(source, tmp_path):
    c, _ = source; kv = c['parameters']['values']['Kvco']['value']
    r = probe(source, tmp_path/'probe', kvco_values=[5e6, kv, 85e6], vlock_values=[.1, .6, 1.3], sample_budget=9)
    assert r['M1_feasible_points'] and r['M1_failed_points'] and r['domain_rejected_points']
    assert r['M2_failed_points'] == []
    assert all(p['M1_status'] == 'NOT_EVALUATED' for p in r['points'] if p['point_id'] in r['domain_rejected_points'])
    assert not r['FULL_SYSTEMSPEC_CERTIFIED']


@pytest.mark.parametrize('options', [{'m2_budget': 5}, {'m2_budget': -1}, {'m2_budget': True},
    {'m1_budget': 2, 'm2_budget': 1}, {'sample_budget': 257}, {'vlock_values': [float('nan')]},
    {'kvco_values': [True]}, {'kvco_values': [0]}, {'kvco_values': [1e308], 'vlock_values': [1e308]}])
def test_invalid_budgets_or_samples_rejected_before_any_output(source, tmp_path, options):
    with pytest.raises(ValueError): probe(source, tmp_path/'probe', **options)
    assert not (tmp_path/'probe').exists()


def test_explicit_new_domain_preserves_systemspec(source, tmp_path):
    import json
    c, p = source; raw = json.loads((ROOT/'configs/problems/nominal.json').read_text(encoding='utf-8'))
    raw['problem_id'] = 'TEST:expanded-vco-domain'; raw['parameters']['Kvco']['max'] = 90e6
    r = probe(source, tmp_path/'probe', revalidation_problem=raw, kvco_values=[85e6], vlock_values=[.3])
    point = r['points'][0]
    assert point['original_search_domain_status'] == 'OUTSIDE_ORIGINAL_SEARCH_DOMAIN'
    assert point['sampling_status'] == 'M1_EVALUATED' and r['problem']['specs'] == p['specs']
    raw['specs'][0]['max'] *= 2
    with pytest.raises(ValueError, match='SystemSpec'):
        probe(source, tmp_path/'bad', revalidation_problem=raw)


def test_native_m2_budget_and_sparse_point_evidence(source, tmp_path):
    from pll_allocation.verification.build_identity import check_build
    try:
        check_build()
    except (FileNotFoundError, RuntimeError) as error:
        pytest.skip('native build unavailable: '+str(error))
    c, _ = source; kv = c['parameters']['values']['Kvco']['value']
    r = probe(source, tmp_path/'native', kvco_values=[kv], vlock_values=[.3, .5, .7],
              sample_budget=3, m1_budget=5, m2_budget=1)
    assert r['budget']['M2_calls'] == 1 and r['budget']['M1_calls'] <= 5
    measured = [p for p in r['points'] if 'M2_observation' in p]
    assert len(measured) == 1 and len(r['unverified_points']) == 2
    assert len(r['M2_passed_points']+r['M2_failed_points']+r['M2_unknown_points']) == 1
    p = measured[0]; obs = p['M2_observation']
    assert p['M2_status'] == obs['supported_metrics_status']
    assert obs['cost']['completed_native_runs'] > 0 and obs['metrics']['PM_deg']['value'] is None
    assert not r['FULL_SYSTEMSPEC_CERTIFIED']


def test_native_timeout_consumes_budget_and_remains_unknown(source, tmp_path):
    from pll_allocation.verification.build_identity import check_build
    try:
        check_build()
    except (FileNotFoundError, RuntimeError) as error:
        pytest.skip('native build unavailable: '+str(error))
    c, _ = source; kv = c['parameters']['values']['Kvco']['value']
    r = probe(source, tmp_path/'timeout', kvco_values=[kv], vlock_values=[.5],
              sample_budget=1, m1_budget=3, m2_budget=1, m2_timeout_s=.001)
    assert r['budget']['M2_calls'] == 1 and r['budget']['M1_calls'] <= 3
    assert r['M2_unknown_points'] == ['VCO0001'] and r['M2_failed_points'] == []
    assert r['points'][0]['M2_observation']['execution_status'] == 'TIMEOUT'
