"""Formal M1 integration and explicitly offline policy/M2 interface tests."""
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from pll_allocation.agent.candidate_pool import distance
from pll_allocation.agent.pool_search import PoolDeterministicPolicy
from pll_allocation.agent.spec_allocation import run_spec_allocation, rows
from pll_allocation.physics_mapping.model import fingerprint
from pll_allocation.verification.continuous import judge_measurements

ROOT = Path(__file__).resolve().parents[1]
NOMINAL = ROOT/'configs/problems/nominal.json'


def config(**updates):
    return {'schema_version': 'pll-spec-allocation-1.0', 'target_count': 3,
            'm2_budget': 0, 'm1_budget': 40, 'initial_search_m1_budget': 16} | updates


@pytest.mark.parametrize('problem', ['nominal', 'tight'])
def test_cold_inverse_builds_distinct_formal_pool_with_few_calls(tmp_path, problem):
    r = run_spec_allocation(ROOT/f'configs/problems/{problem}.json', tmp_path/'run', config=config(target_count=5))
    assert r['M1_quality_count'] >= 5 and r['pool_target_reached']
    assert r['cost']['M1_calls'] <= 9 and r['cost']['LLM_calls'] == 0
    assert r['recommended_M2_supported'] is None and r['M2_status'] == 'NOT_EVALUATED'
    p = json.loads((tmp_path/'run/problem_resolved.json').read_text(encoding='utf-8'))
    for i, a in enumerate(r['candidates']):
        assert a['formal_M1_result']['status'] == 'OK' and a['M1_feasibility'] == 'FEASIBLE'
        assert all(distance(p, a, b) >= .05 for b in r['candidates'][:i])
    h = json.loads((tmp_path/'run/initial/verification_handoff.json').read_text(encoding='utf-8'))
    assert h['ready_for_stage9'] and h['recommendation_recheck']['passed']
    assert 'EMPTY_BOOTSTRAP' in Path(h['source_context_binding']['path']).read_text(encoding='utf-8')


def test_quality_cannot_be_bypassed_by_one_feasible_point(tmp_path):
    r = run_spec_allocation(NOMINAL, tmp_path/'run',
        config=config(target_count=1, minimum_margin=100, m1_budget=12, initial_search_m1_budget=12))
    assert not r['pool_target_reached'] and r['M1_quality_count'] == 0
    assert r['recommended'] is None and r['cost']['M1_calls'] <= 12
    assert r['initial_termination'] != 'M1_POOL_TARGET_REACHED'


def test_small_budget_stops_with_partial_pool_not_infeasibility(tmp_path):
    r = run_spec_allocation(NOMINAL, tmp_path/'run', config=config(target_count=20, m1_budget=4))
    assert not r['pool_target_reached'] and r['cost']['M1_calls'] <= 4
    assert 'INFEASIBLE' not in r['status']


def test_auto_sufficient_pool_never_enters_llm_branch(tmp_path):
    with patch('pll_allocation.agent.region_policy.subprocess.run', side_effect=AssertionError('NETWORK FORBIDDEN')):
        r = run_spec_allocation(NOMINAL, tmp_path/'run', config=config(mode='AUTO_HYBRID'))
    result = json.loads((tmp_path/'run/initial/result.json').read_text(encoding='utf-8'))
    assert r['pool_target_reached'] and r['cost']['LLM_calls'] == 0
    assert set(result['policy_branches']) == {'DETERMINISTIC'}


class OfflinePhysicsPolicy:
    def __init__(self):
        self.states = []

    def decide(self, state, directory):
        self.states.append(deepcopy(state))
        return PoolDeterministicPolicy().decide(state, directory)


@pytest.mark.parametrize('mode', ['LLM_PHYSICS_GUIDED', 'AUTO_HYBRID'])
def test_offline_llm_interface_observes_physics_and_m1_feedback(tmp_path, mode):
    policy = OfflinePhysicsPolicy()
    with patch('pll_allocation.agent.region_policy.subprocess.run', side_effect=AssertionError('NETWORK FORBIDDEN')):
        r = run_spec_allocation(NOMINAL, tmp_path/'run', config=config(mode=mode, target_count=10,
            deterministic_rounds=1, llm_budget=5), policy=policy)
    assert policy.states and policy.states[0]['relations']
    if mode == 'AUTO_HYBRID':
        assert policy.states[0]['history'] and policy.states[0]['samples']
    assert r['cost']['LLM_calls'] == 0 and r['LLM_validation'] == 'OFFLINE_INTERFACE_ONLY'


@pytest.mark.parametrize('mode', ['LLM_PHYSICS_GUIDED', 'AUTO_HYBRID'])
def test_real_llm_not_authorized_fails_closed_and_retains_m1(tmp_path, mode):
    with patch('pll_allocation.agent.region_policy.subprocess.run', side_effect=AssertionError('NETWORK FORBIDDEN')):
        r = run_spec_allocation(NOMINAL, tmp_path/'run', config=config(mode=mode, target_count=30,
            deterministic_rounds=1, initial_search_m1_budget=30))
    assert r['cost']['LLM_calls'] == 0 and 'NOT_AUTHORIZED' in r['failure']['reason']
    if mode == 'AUTO_HYBRID':
        assert r['M1_distinct_feasible_count'] > 0


def test_offline_m2_pool_failure_then_alternative_and_no_fake_native_pass(tmp_path):
    invoked = []
    def backend(request, out):
        invoked.append(request['candidate_sha256'])
        capture = {'numerical_converged': True, 'reliable_capture_status': 'CAPTURED_WITHIN_WINDOW',
            'fine': {'lock_time_s': 54e-6 if len(invoked) == 1 else 20e-6},
            'step_comparison': {'lock_time_difference_s': 0}}
        comparison = {'numerical_converged': True, 'M2_BW_measurement': {'BW_Hz': 225000},
                      'BW_numerical_envelope_Hz': [224990, 225010]}
        result = judge_measurements(request, capture, comparison)
        return result | {'candidate_sha256': request['candidate_sha256'], 'request_sha256': request['request_sha256'],
            'problem_sha256': request['problem_sha256'], 'protocol_sha256': request['protocol_sha256'],
            'M2_model_fingerprint': fingerprint(request['M2_model']), 'evidence_id': 'TEST:'+request['observation_id'],
            'observation_id': request['observation_id'], 'execution_status': 'COMPLETED',
            'raw_evidence_path': 'TEST_NO_NATIVE_EVIDENCE',
            'cost': {'posthoc_M1_calls': 0, 'completed_native_runs': 0, 'integration_points': 0, 'native_elapsed_s': 0.}}
    r = run_spec_allocation(NOMINAL, tmp_path/'run', config=config(m2_budget=2), m2_executor=backend)
    assert len(set(invoked)) == 2
    assert r['M2_supported_pass_count'] == 0 and r['recommended_M2_supported'] is None
    assert r['TEST_M2_injected'] and r['verification_termination'] == 'SUPPORTED_M2_METRICS_PASS'
    assert not (tmp_path/'run/verification/reallocation_01').exists()
    assert any(c['M2_supported_status'] == 'FAIL' for c in r['candidates'])
    for item in rows(tmp_path/'run/verification/m2_verifications.jsonl'):
        assert item['observation']['metrics']['PM_deg']['value'] is None


def test_output_cannot_overwrite_prior_run(tmp_path):
    run_spec_allocation(NOMINAL, tmp_path/'run', config=config())
    with pytest.raises(FileExistsError):
        run_spec_allocation(NOMINAL, tmp_path/'run', config=config())


@pytest.mark.parametrize('mode', ['DETERMINISTIC', 'LLM_PHYSICS_GUIDED', 'AUTO_HYBRID'])
def test_cold_feedback_reallocation_uses_same_tools_and_actual_feedback(tmp_path, mode):
    from test_verification_feedback import fake_m2
    calls = []
    def backend(req, out):
        calls.append(req['candidate_sha256'])
        return fake_m2(lock=54e-6 if len(calls) == 1 else 20e-6)(req, out)
    policy = OfflinePhysicsPolicy() if mode != 'DETERMINISTIC' else None
    r = run_spec_allocation(NOMINAL, tmp_path/'run', config=config(mode=mode, target_count=1,
        m2_budget=2, llm_budget=5), policy=policy, m2_executor=backend)
    assert len(set(calls)) == 2 and r['verification_termination'] == 'SUPPORTED_M2_METRICS_PASS'
    f = json.loads((tmp_path/'run/verification/reallocation_01/external_feedback.json').read_text(encoding='utf-8'))
    assert f['observations'][0]['measurements']['failed_constraints'] == ['lock_time_s']
    decisions = rows(tmp_path/'run/verification/reallocation_01/SEARCH_DECISION_TRACE.jsonl')
    assert decisions[0]['decision']['request']['tuning_preference'] == 'LOW_VOLTAGE'
    assert r['cost']['M1_calls'] <= 40 and r['M2_supported_pass_count'] == 0
    if mode == 'LLM_PHYSICS_GUIDED':
        assert any(s['external_feedback'] for s in policy.states)


def test_auto_m2_failure_escalates_after_deterministic_repair(tmp_path):
    from test_verification_feedback import fake_m2
    calls = []
    def backend(req, out):
        calls.append(req['candidate_sha256'])
        return fake_m2(lock=54e-6 if len(calls) < 3 else 20e-6)(req, out)
    policy = OfflinePhysicsPolicy()
    r = run_spec_allocation(NOMINAL, tmp_path/'run', config=config(mode='AUTO_HYBRID', target_count=1,
        m2_budget=3, llm_budget=5), policy=policy, m2_executor=backend)
    assert len(set(calls)) == 3 and r['cost']['LLM_calls'] == 0
    assert r['verification_termination'] == 'SUPPORTED_M2_METRICS_PASS'
    assert any(s['external_feedback']['observations'][0]['measurements']['previous_searches']
               for s in policy.states if s['external_feedback'])
    assert r['cost']['offline_llm_decisions'] > 0 and r['M2_supported_pass_count'] == 0
