"""Offline LLM decision interface drives real original M1 tools, never paid API."""
from copy import deepcopy
import json

import pytest

from pll_allocation.agent.spec_allocation import run_spec_allocation, validate_config, pool_config, rows
from pll_allocation.agent.physics_tool_policy import PROMPT, prompt_for_options
from pll_allocation.agent.pool_search import PoolLLMPolicy
from pll_allocation.exploration.conditional_physics import allocation_options
from pll_allocation.exploration.contracts import load_problem
from pll_allocation.exploration.physics_region_builder import build_physics_region, validate_request, OBJECTIVE_REQUEST_SCHEMA
from pll_allocation.physics_mapping.model import fingerprint

BASE = {'schema_version': 'pll-spec-allocation-1.0', 'mode': 'LLM_PHYSICS_GUIDED',
    'target_count': 12, 'm1_budget': 96, 'initial_search_m1_budget': 88, 'm2_budget': 0,
    'max_decisions': 6, 'max_round_m1': 24, 'llm_budget': 8,
    'max_build_attempts': 8, 'construction_attempt_budget': 64,
    'analytic_features_enabled': True, 'noise_allocation_enabled': True,
    'initial_state_aware_enabled': True, 'physics_ranking_enabled': True}


def request(problem, options, goals, *, count=1, attempts=8):
    return {'schema_version': OBJECTIVE_REQUEST_SCHEMA, 'request_id': 'MOCK:BUILD',
        'problem_sha256': problem['problem_sha256'], 'model_fingerprint': 'TEST_MODEL',
        'strategy': 'HIGH_PM_LF_SHAPE', 'target_bw_fraction': [.5, .5],
        'physics_focus': ['LF_SHAPE', 'GAIN_SPLIT', 'TUNING'], 'tuning_preference': 'DIVERSE',
        'seed_count': count, 'region_width_policy': 'BALANCED',
        'budget': {'construction_attempts': attempts, 'm1_calls': count}, 'evidence_ids': ['REL:shape'],
        'physical_objectives': goals, 'tool_options_sha256': fingerprint(options)}


class ObservingMockPolicy:
    """Independent requests, deliberately does not call a deterministic policy."""
    def __init__(self):
        self.states = []

    def decide(self, state, directory):
        self.states.append(deepcopy(state)); index = len(self.states)-1
        capabilities = state['conditional_physics']
        diagnostics = capabilities['candidates']
        evidence = [diagnostics[0]['evidence_id']] if diagnostics else ['REL:shape']
        common = {'schema_version': 'pll-physics-tool-decision-1.0', 'state_sha256': state['state_sha256'],
            'reason': 'TEST choose enabled physical goals from bound conditional observations, never declare PASS',
            'evidence_ids': evidence}
        if index in (0, 1, 5):
            goals = ['NOISE_AWARE'] if index == 0 else ['FAST_LOCK', 'NOISE_AWARE'] if index == 1 else ['INITIAL_STATE_AWARE']
            if index == 1:
                # Consume the preceding tools' actual conditional diagnostics.
                assert any(d['noise']['jitter_margin_s'] < 0 for d in diagnostics)
                assert any(abs(d['dynamics']['initial_frequency_error_Hz']) > 0 for d in diagnostics)
                goals = ['FAST_LOCK', 'NOISE_AWARE']
            if index == 5:
                assert any(d['dynamics']['prediction_validity']['status'] == 'CONDITIONAL_IDEAL_LINEAR'
                           for d in diagnostics)
                goals = ['INITIAL_STATE_AWARE']
            opt = state['candidate_pool']['config']['physics_options']
            req = request(state['problem'], opt, goals, count=2)
            req.update(request_id='MOCK:'+str(state['round']), model_fingerprint=state['model']['model_sha256'],
                evidence_ids=evidence, target_bw_fraction=[.5+.04*index, .5+.04*index])
            return common | {'action': 'BUILD_PHYSICS_REGION', 'request': req}
        region = next(r for r in state['available_tool_regions'] if r['formal_M1_seed_ids'])
        if index == 2:
            return common | {'action': 'PROBE_REGION', 'region_id': region['region_id'], 'sample_count': 2, 'm1_budget': 2}
        if index == 3:
            return common | {'action': 'MEASURE_LOCAL_SENSITIVITY', 'region_id': region['region_id'],
                'seed_id': region['formal_M1_seed_ids'][0], 'm1_budget': 12}
        return common | {'action': 'OPTIMIZE_LOCAL', 'region_id': region['region_id'],
            'seed_ids': region['formal_M1_seed_ids'][:1], 'active_variables': ['Icp', 'Rz'], 'm1_budget': 24}


@pytest.mark.parametrize('mode', ['LLM_PHYSICS_GUIDED', 'AUTO_HYBRID'])
def test_mock_observes_selects_and_executes_real_tools(tmp_path, monkeypatch, mode):
    def forbidden(*args, **kwargs):
        raise AssertionError('No paid or transport calls authorized')
    monkeypatch.setattr('pll_allocation.agent.region_policy.subprocess.run', forbidden)
    policy = ObservingMockPolicy()
    config = BASE | {'mode': mode, 'deterministic_rounds': 1,
                     'max_decisions': 7 if mode == 'AUTO_HYBRID' else 6}
    result = run_spec_allocation('configs/problems/nominal.json', tmp_path/'run', config=config, policy=policy)
    assert len(policy.states) == 6, result['failure']
    observed = [s for s in policy.states if s['conditional_physics']['candidates']]
    assert observed
    for state in observed:
        for item in state['conditional_physics']['candidates']:
            assert item['evidence_id'] in state['allowed_evidence_ids']
            assert item['candidate_sha256'] and item['source_evidence_id']
            assert item['problem_sha256'] == state['problem']['problem_sha256']
            assert item['model_fingerprint'] == state['model']['model_sha256']
            assert item['prediction_sha256'] == fingerprint({k: v for k, v in item.items()
                                                            if k not in ('evidence_id', 'prediction_sha256')})
            noise, dynamics = item['noise'], item['dynamics']
            assert noise['predicted_jitter_s'] is not None and noise['dominant_noise_source']
            assert noise['jitter_margin_s'] < 0 and noise['noise_profile_identity']['sha256']
            assert noise['prediction_validity'] == 'CONDITIONAL_INDEPENDENT_SMALL_SIGNAL'
            assert dynamics['omega_n_rad_s'] and dynamics['zeta_approx']
            assert dynamics['initial_frequency_error_Hz'] is not None
            assert dynamics['slip_risk'] in ('LOW', 'MEDIUM', 'HIGH', 'UNKNOWN')
            assert dynamics['predicted_lock_time_s'] is None and not item['capture_certified']
            assert item['formal_M2_status'] == 'UNKNOWN'
    trace = rows(tmp_path/'run/initial/SEARCH_DECISION_TRACE.jsonl')
    builds = [r for r in trace if r['decision'].get('request', {}).get('schema_version') == OBJECTIVE_REQUEST_SCHEMA]
    assert len(builds) == 3
    assert [r['actual']['objective_selection']['physical_objectives'][0] for r in builds] == [
        'NOISE_AWARE', 'FAST_LOCK', 'INITIAL_STATE_AWARE']
    assert all(sum(o['M1_calls'] for o in b['actual']['observations']) > 0 for b in builds)
    assert {'PROBE', 'OPTIMIZE'} <= {r['decision']['action'] for r in trace}
    assert any(s['local_sensitivity'] for s in policy.states)
    assert any(r['formal_M1_called'] and r['M1_status'] == 'OK' for r in rows(tmp_path/'run/initial/executor/m1_samples.jsonl'))
    assert result['cost']['M1_calls'] <= config['m1_budget'] and result['cost']['LLM_calls'] == 0
    assert result['cost']['M2_verifications'] == 0 and result['LLM_validation'] == 'OFFLINE_INTERFACE_ONLY'
    assert not result['failure'] and not result['FULL_SYSTEMSPEC_CERTIFIED']


def test_goals_change_actual_builder_order_with_same_input():
    problem = load_problem('configs/problems/nominal.json'); opt = allocation_options(validate_config(BASE))
    results = []
    for goals in (['NOISE_AWARE'], ['FAST_LOCK'], ['INITIAL_STATE_AWARE']):
        req = request(problem, opt, goals)
        validate_request(req, problem, 'TEST_MODEL', ['REL:shape'], attempts_left=8, m1_left=2, physics_options=opt)
        results.append(build_physics_region(problem, req, model_fingerprint='TEST_MODEL', random_seed=23, physics_options=opt))
    assert all(r['seeds'] for r in results)
    assert len({r['seeds'][0]['parameter_sha256'] for r in results}) >= 2
    assert [r['seeds'][0]['selection_preference'] for r in results] == [
        'NOISE_FAVORABLE', 'FAST_LOCK_PROXY', 'INITIAL_STATE_AWARE']


@pytest.mark.parametrize('mutation', ['disabled', 'noise_disabled', 'stale', 'duplicate', 'unknown', 'parameters', 'limit', 'old_extra', 'budget'])
def test_versioned_request_rejects_unavailable_or_unsafe_fields(mutation):
    problem = load_problem('configs/problems/nominal.json'); opt = allocation_options(validate_config(BASE))
    req = request(problem, opt, ['NOISE_AWARE'])
    if mutation == 'disabled': opt = None
    if mutation == 'noise_disabled':
        opt = allocation_options(validate_config(BASE | {'noise_allocation_enabled': False}))
        req['tool_options_sha256'] = fingerprint(opt)
    if mutation == 'stale': req['tool_options_sha256'] = '0'*64
    if mutation == 'duplicate': req['physical_objectives'] *= 2
    if mutation == 'unknown': req['physical_objectives'] = ['CERTIFY_M2']
    if mutation == 'parameters': req['parameters'] = {'Icp': 1e-4}
    if mutation == 'limit': req['jitter_limit_s'] = 1e-9
    if mutation == 'old_extra': req['schema_version'] = 'pll-physics-region-request-1.0'
    if mutation == 'budget': req['budget']['m1_calls'] = 100
    with pytest.raises(ValueError):
        validate_request(req, problem, 'TEST_MODEL', ['REL:shape'], attempts_left=8, m1_left=2, physics_options=opt)


def test_disabled_capabilities_and_prompt_are_absent(tmp_path):
    assert prompt_for_options() == PROMPT
    old = pool_config(validate_config({'schema_version': 'pll-spec-allocation-1.0'}))
    enabled = pool_config(validate_config(BASE))
    assert 'physical_objectives' not in PoolLLMPolicy({}, old).prompt
    assert OBJECTIVE_REQUEST_SCHEMA in PoolLLMPolicy({}, enabled).prompt
    class LegacyMock:
        def __init__(self): self.states = []
        def decide(self, state, directory):
            from pll_allocation.agent.pool_search import PoolDeterministicPolicy
            self.states.append(deepcopy(state))
            return PoolDeterministicPolicy().decide(state, directory)
    policy = LegacyMock()
    result = run_spec_allocation('configs/problems/nominal.json', tmp_path/'old', config={
        'schema_version': 'pll-spec-allocation-1.0', 'mode': 'LLM_PHYSICS_GUIDED', 'target_count': 2,
        'm1_budget': 20, 'initial_search_m1_budget': 16, 'm2_budget': 0}, policy=policy)
    assert policy.states and all('conditional_physics' not in s for s in policy.states)
    assert result['pool_target_reached'] and result['cost']['LLM_calls'] == 0


@pytest.mark.parametrize('flag,goals,noise,dynamics', [
    ('noise_allocation_enabled', ['NOISE_AWARE'], True, False),
    ('initial_state_aware_enabled', ['INITIAL_STATE_AWARE', 'FAST_LOCK'], False, True),
    ('analytic_features_enabled', [], False, True),
    ('physics_ranking_enabled', [], False, True)])
def test_individual_capability_gating_and_unknown_prediction(flag, goals, noise, dynamics):
    from types import SimpleNamespace
    from pll_allocation.agent.conditional_observation import conditional_observation
    from pll_allocation.exploration.conditional_physics import ConditionalPhysics
    from pll_allocation.exploration.contracts import make_parameters
    problem = load_problem('configs/problems/nominal.json')
    options = allocation_options(validate_config({'schema_version': 'pll-spec-allocation-1.0', flag: True}))
    # Deliberately unsupported nonlinearity must remain an explicit UNKNOWN.
    params = make_parameters(problem)
    params['values']['Kvco2']['value'] = 1
    ex = SimpleNamespace(conditional_physics=ConditionalPhysics(problem, options), problem=problem,
        context={'model': {'model_sha256': 'TEST_MODEL'}}, evidence={})
    row = {'parameter_sha256': fingerprint(params), 'parameters': params,
           'evidence_id': 'TEST:UNSUPPORTED', 'M1_status': 'INVALID'}
    state = conditional_observation(ex, [row]*30)
    assert state['allowed_physical_objectives'] == goals
    assert (OBJECTIVE_REQUEST_SCHEMA in state['request_schema_versions']) == bool(goals)
    assert len(state['candidates']) == 1
    item = state['candidates'][0]
    assert ('noise' in item) == noise and ('dynamics' in item) == dynamics
    assert item['formal_M2_status'] == 'UNKNOWN' and not item['capture_certified']
    if noise:
        assert item['noise']['predicted_jitter_s'] is None
        assert item['noise']['conditional_noise_status'] == 'UNKNOWN'
        assert item['noise']['reason']
    if dynamics:
        assert item['dynamics']['slip_risk'] == 'UNKNOWN'
        assert item['dynamics']['prediction_validity']['status'] == 'UNKNOWN'
    assert ex.evidence[item['evidence_id']] == item
