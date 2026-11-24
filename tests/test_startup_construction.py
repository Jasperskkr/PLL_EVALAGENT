"""Startup-offset construction keeps the six-axis domain and original request."""
from copy import deepcopy
import pytest

from pll_allocation.agent.spec_allocation import validate_config
from pll_allocation.exploration.conditional_physics import allocation_options
from pll_allocation.exploration.contracts import load_problem, check_candidate
from pll_allocation.exploration.physics_region_builder import build_physics_region, validate_request
from pll_allocation.physics_mapping.model import parse_parameters


def request(problem):
    return {'schema_version': 'pll-physics-region-request-1.0', 'request_id': 'STARTUP:TEST',
        'problem_sha256': problem['problem_sha256'], 'model_fingerprint': 'TEST_MODEL',
        'strategy': 'DIVERSITY_EXPLORATION', 'target_bw_fraction': [.5, .5],
        'physics_focus': ['LF_SHAPE', 'TUNING'], 'tuning_preference': 'DIVERSE',
        'seed_count': 5, 'region_width_policy': 'BALANCED',
        'budget': {'construction_attempts': 16, 'm1_calls': 5}, 'evidence_ids': ['REL:shape']}


@pytest.mark.parametrize('name', ['nominal', 'tight'])
def test_startup_clipping_and_diverse_implementation_preferences(name):
    problem = load_problem('configs/problems/'+name+'.json'); r = request(problem)
    cfg = validate_config({'schema_version': 'pll-spec-allocation-1.0', 'initial_state_aware_enabled': True})
    validate_request(r, problem, 'TEST_MODEL', ['REL:shape'], attempts_left=16, m1_left=5)
    result = build_physics_region(problem, r, model_fingerprint='TEST_MODEL', random_seed=23,
        physics_options=allocation_options(cfg), minimum_distance=.05)
    assert len(result['seeds']) == 5
    assert len({s['selection_preference'] for s in result['seeds']}) >= 4
    errors = []
    for seed in result['seeds']:
        p = parse_parameters(seed['parameters'])
        assert problem['parameters']['f0']['min'] <= p['f0'] <= problem['parameters']['f0']['max']
        assert check_candidate(problem, seed['parameters'])['status'] == 'NECESSARY_CONDITIONS_SATISFIED'
        v = (p['N']*p['f_ref']-p['f0'])/p['Kvco']
        assert .02-1e-14 <= v <= 1.18+1e-14
        errors.append(abs(seed['analytic_features']['initial_frequency_error_Hz']))
    assert min(errors) < max(errors)
    assert result['cost']['M1_calls'] == 0


def test_all_flags_off_preserve_exact_seeds_and_attempts():
    p = load_problem('configs/problems/nominal.json'); r = request(p)
    a = build_physics_region(p, r, model_fingerprint='TEST_MODEL', random_seed=23)
    c = validate_config({'schema_version': 'pll-spec-allocation-1.0'})
    b = build_physics_region(p, r, model_fingerprint='TEST_MODEL', random_seed=23,
        physics_options=allocation_options(c))
    assert a['seeds'] == b['seeds'] and a['attempts'] == b['attempts']
