"""Opt-in noise participates in proposals, stopping and the existing optimizer."""
from copy import deepcopy
import json
from pathlib import Path
import pytest

from pll_allocation.agent.spec_allocation import run_spec_allocation, validate_config, pool_config
from pll_allocation.exploration.conditional_physics import allocation_options, ConditionalPhysics
from pll_allocation.exploration.contracts import load_problem, make_parameters
from pll_allocation.physics_mapping.model import fingerprint


BASE = {'schema_version': 'pll-spec-allocation-1.0', 'target_count': 2, 'm1_budget': 16,
        'm2_budget': 0, 'initial_search_m1_budget': 16, 'max_decisions': 2}


def test_optional_flags_validate_and_default_to_original_path():
    c = validate_config(BASE)
    assert allocation_options(c) is None and 'physics_options' not in pool_config(c)
    with pytest.raises(ValueError):
        validate_config(BASE | {'noise_allocation_enabled': 1})
    with pytest.raises(ValueError):
        validate_config(BASE | {'physics_options': {'noise_band_Hz': [1e6, 1e4]}})


def test_noise_changes_six_axis_allocation_and_stopping(tmp_path):
    original = run_spec_allocation('configs/problems/nominal.json', tmp_path/'old', config=BASE)
    enhanced = run_spec_allocation('configs/problems/nominal.json', tmp_path/'new',
        config=BASE | {'noise_allocation_enabled': True})
    assert original['pool_target_reached']
    assert not enhanced['pool_target_reached']
    assert {r['parameter_sha256'] for r in original['candidates']} != {r['parameter_sha256'] for r in enhanced['candidates']}
    physics = ConditionalPhysics(load_problem('configs/problems/nominal.json'),
        allocation_options(validate_config(BASE | {'noise_allocation_enabled': True})))
    old = min(physics.describe(r['parameters'])['predicted_jitter_s'] for r in original['candidates'])
    assert enhanced['conditional_noise_summary']['best_predicted_jitter_s'] < old
    assert enhanced['conditional_noise_summary']['formal_M2_jitter_status'] == 'UNKNOWN'
    assert enhanced['cost']['M1_calls'] <= BASE['m1_budget']
    proposals = list((tmp_path/'new/initial').glob('physics_tools/*/proposal_before_M1.json'))
    assert any(json.loads(p.read_text())['conditional_search']['noise_integrations'] > 1 for p in proposals)


def test_limit_is_read_from_problem_and_unknown_is_not_certified():
    problem = load_problem('configs/problems/nominal.json')
    opt = allocation_options(validate_config(BASE | {'noise_allocation_enabled': True}))
    physics = ConditionalPhysics(problem, opt); c = make_parameters(problem)
    value = physics.describe(c)['predicted_jitter_s']
    changed = deepcopy(problem)
    next(s for s in changed['specs'] if s['metric'] == 'jitter_s')['max'] = value*2
    other = ConditionalPhysics(changed, opt)
    assert not physics.qualified({'parameters': c}) and other.qualified({'parameters': c})
    assert physics.extra_margin({'parameters': c})[0] < 0 < other.extra_margin({'parameters': c})[0]
    c['values']['Kvco2']['value'] = 1
    assert not other.qualified({'parameters': c})


def test_existing_regional_slsqp_executes_noise_margin(tmp_path, monkeypatch):
    calls = []
    original = ConditionalPhysics.extra_margin
    def tracked(self, row):
        value = original(self, row)
        calls.append((fingerprint(row['parameters']), value))
        return value
    monkeypatch.setattr(ConditionalPhysics, 'extra_margin', tracked)
    r = run_spec_allocation('configs/problems/nominal.json', tmp_path/'run', config=BASE | {
        'noise_allocation_enabled': True, 'm1_budget': 40, 'initial_search_m1_budget': 40})
    observations = [json.loads(line) for line in
        (tmp_path/'run/initial/executor/region_observations.jsonl').read_text().splitlines()]
    solver_runs = [s for o in observations for s in o['solver_runs']]
    assert any(s.get('started') and s.get('conditional_noise_constraint', {}).get('enabled') for s in solver_runs)
    assert len({key for key, value in calls if value}) > 1
    assert r['cost']['M1_calls'] <= 40


def test_feasible_conditional_target_is_counted_without_changing_formal_support(tmp_path):
    raw = json.loads(Path('configs/problems/nominal.json').read_text())
    next(s for s in raw['specs'] if s['metric'] == 'jitter_s')['max'] = 100e-12
    problem_path = tmp_path/'loose_problem.json'
    problem_path.write_text(json.dumps(raw), encoding='utf-8')
    result = run_spec_allocation(problem_path, tmp_path/'loose', config=BASE | {'noise_allocation_enabled': True})
    assert result['conditional_noise_summary']['status'] == 'CONDITIONAL_TARGET_REACHED'
    assert result['pool_target_reached']
    assert all(r['M2_status'] == 'NOT_EVALUATED' for r in result['candidates'])
    assert not result['FULL_SYSTEMSPEC_CERTIFIED']
