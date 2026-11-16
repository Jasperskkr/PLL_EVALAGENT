"""Unit policies are labelled tests; actual acceptance uses the real API separately."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess

import pytest

from pll_allocation.agent.calibration import prepare_context, raw_problem
from pll_allocation.agent.decision_adapter import adapt_decision
from pll_allocation.agent.planner_state import build_state
from pll_allocation.agent.region_policy import LLMRegionPolicy, ProviderError, strict_json, validate_provider
from pll_allocation.agent.search_loop import AgentSearchLoop, validate_config
from pll_allocation.exploration import load_physics_context, run_exploration
from pll_allocation.exploration.contracts import judge
from pll_allocation.physics_mapping.model import evaluate

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def contexts(tmp_path_factory):
    folder = tmp_path_factory.mktemp('stage8b_calibration')
    paths = {}
    for case, config in [('global', 'nominal'), ('tight', 'tight'),
                         ('impossible', 'infeasible_pm')]:
        raw = json.loads((ROOT/f'configs/problems/{config}.json').read_text())
        raw['exploration'].update(sobol_samples=8, physics_seed_count=16, max_m1_evaluations=64,
                                  sensitivity_representatives=1)
        source = folder/(case+'.json')
        source.write_text(json.dumps(raw))
        run_exploration(source, folder/case)
        paths[case] = folder/case/'physics_context.json'
    return paths


def config():
    raw = json.loads((ROOT/'configs/agent/region_search.json').read_text())
    raw.update(total_m1_budget=32, max_round_m1=16, calibration_budget=8, seed_probe_budget=4,
               seed_probe_samples=4, max_decisions=2, min_decisions_before_quality_stop=2, quality_target=100.)
    return raw


def propose(state, *, stop=False, seedless=False):
    if stop:
        return {'action': 'STOP', 'reason': 'Test policy sees real observation',
                'evidence_ids': [state['best_known']['evidence_id']]}
    row = next(r for r in state['calibration']['displayed_samples'] if r['seed_eligible'])
    radius = .04 if not state['history'] else .03
    return {'action': 'OPTIMIZE', 'region_origin': 'LLM_PROPOSED',
            'normalized_bounds': {k: [max(0., v-radius), min(1., v+radius)] for k,v in row['normalized'].items()},
            'active_variables': list(row['normalized']), 'seed_ids': [] if seedless else [row['evidence_id']],
            'm1_budget': min(16, state['budget']['max_this_decision_M1_calls']),
            'reason': 'UNIT TEST geometry only; real M1 is still called by the executor.',
            'evidence_ids': [row['evidence_id'], 'E_PM', 'SENS8B:01']}


class TestPolicy:
    __test__ = False
    def __init__(self, invalid=False, seedless=False, provider_fail=False, second_stop=True):
        self.states = []
        self.invalid, self.seedless, self.provider_fail, self.second_stop = invalid, seedless, provider_fail, second_stop
        self.calls = []
    def decide(self, state, directory):
        self.states.append(deepcopy(state))
        if self.provider_fail:
            raise ProviderError('Injected provider error; no real API call')
        proposal = propose(state, stop=bool(state['history']) and self.second_stop, seedless=self.seedless)
        if self.invalid and len(self.states) == 1:
            proposal['normalized_bounds']['C1'][0] = -.01
        return proposal


def loop(contexts, tmp_path, policy=None, case='global', **kwargs):
    return AgentSearchLoop(contexts[case], tmp_path/'run', config=config(), provider_config={},
                           policy=policy or TestPolicy(), **kwargs)


def state(loop):
    return build_state(loop.explorer, loop.config, loop.history, round_number=1, calls_remaining=3,
                       calibration=loop.calibration)


def test_first_state_has_no_region_menu_and_full_six_axis_sensitivity(contexts, tmp_path):
    x = loop(contexts, tmp_path)
    s = state(x)
    text = json.dumps(s)
    assert all(k not in text for k in ('candidate_regions', 'R001', 'R002', 'R003', 'normalized_bounds'))
    assert len(s['problem']['parameters']) == 6 and not s['history']
    assert s['execution_and_stop']['quality_target_minimum_normalized_margin']==x.config['quality_target']
    for rep in s['sensitivity']:
        assert len(rep['normalized_matrix']['BW_Hz']) == len(rep['normalized_matrix']['PM_deg']) == 6
        assert len(rep['stencils']) == 6
        assert rep['normalized_bound_margin_jacobian']['BW_Hz:max']
    assert {'HARD_CONSTRAINT','PHYSICS_PRIOR','HEURISTIC'} <= {r['kind'] for r in s['physics_knowledge']}
    x.explorer.close()


@pytest.mark.parametrize('case', ['global', 'tight'])
def test_real_m1_enters_feedback_and_second_decision(contexts, tmp_path, case):
    p = TestPolicy()
    x = loop(contexts, tmp_path, p, case)
    result = x.run()
    assert result['status'] == 'STOPPED_BY_LLM'
    assert result['feedback_decision_completed'] and result['cost']['M1_calls'] <= 32
    assert result['cost']['LLM_calls'] == 0 and result['cost']['test_policy_calls'] == 2
    assert p.states[1]['history'][0]['observations'][0]['solver_runs']
    assert p.states[1]['history'][0]['observations'][0]['cost']['M1_calls'] > 0
    assert any(r['evidence_id'].startswith('A8S') for r in p.states[1]['calibration']['displayed_samples'])
    allocation = json.loads((tmp_path/'run/m1_allocation.json').read_text())
    row = allocation['new_allocation']
    assert row is not None
    independent = evaluate(row['parameters'])
    assert independent.metrics == row['metrics']
    assert judge(x.explorer.problem, row['parameters'], independent) == row['judgment']


def test_feedback_can_change_region_and_optimize_again(contexts, tmp_path):
    p = TestPolicy(second_stop=False)
    x = loop(contexts, tmp_path, p)
    r = x.run()
    assert len(x.history) == 2
    assert x.history[0]['decision']['normalized_bounds'] != x.history[1]['decision']['normalized_bounds']
    assert r['cost']['M1_calls'] <= 32


def test_invalid_output_repaired_with_precise_error_before_solver(contexts, tmp_path):
    p = TestPolicy(invalid=True)
    x = loop(contexts, tmp_path, p)
    r = x.run()
    assert r['feedback_decision_completed']
    assert 'inside original domain' in p.states[1]['validation_feedback']['message']
    assert p.states[1]['budget']['executor_M1_calls'] == 0
    assert (tmp_path/'run/round_01/validation_error_00.json').is_file()


def test_seedless_region_probe_uses_same_box_and_is_charged(contexts, tmp_path):
    x = loop(contexts, tmp_path, TestPolicy(seedless=True))
    r = x.run()
    execution = x.history[0]['execution_decisions']
    assert execution[0]['action'] == 'PROBE'
    assert all(d['normalized_bounds'] == x.history[0]['decision']['normalized_bounds'] for d in execution)
    assert sum(o['cost']['M1_calls'] for o in x.history[0]['observations']) <= 16
    assert r['cost']['M1_calls'] <= 32


def test_missing_probe_seed_reports_observation_not_fallback(contexts, tmp_path, monkeypatch):
    x = loop(contexts, tmp_path, TestPolicy(seedless=True))
    original = x.explorer.execute
    def reject_all(d):
        obs = original(d)
        if d['action'] == 'PROBE':
            for r in x.explorer.rows:
                r['M1_status'] = 'NUMERICAL_FAILURE'
        return obs
    monkeypatch.setattr(x.explorer,'execute',reject_all)
    result = x.run()
    assert x.history[0]['outcome'] == 'NO_EVALUABLE_SEED_IN_LLM_REGION'
    assert len(x.history[0]['execution_decisions']) == 1
    assert result['feedback_decision_completed']


@pytest.mark.parametrize('mutate,match', [
    (lambda d: d['normalized_bounds']['C1'].__setitem__(0,-.1), 'inside original domain'),
    (lambda d: d['evidence_ids'].append('fake'), 'Evidence ID'),
    (lambda d: d['seed_ids'].__setitem__(0,'fake'), 'exposed'),
    (lambda d: d.update(m1_budget=1000), 'budget'),
    (lambda d: d.update(region_origin='PRESET'), 'LLM_PROPOSED'),
    (lambda d: d.update(metrics={'PM_deg':90}), 'strict proposal'),
    (lambda d: d.update(active_variables=['C3']), 'Active Variables'),
])
def test_adapter_rejects_without_m1(contexts, tmp_path, mutate, match):
    x = loop(contexts, tmp_path)
    s = state(x)
    d = propose(s)
    mutate(d)
    with pytest.raises(ValueError,match=match):
        adapt_decision(d,x.explorer,s,x.config,round_number=1,first=True)
    assert x.explorer.cost()['M1_calls'] == 0
    x.explorer.close()


def test_strict_region_necessary_certificate_rejected(contexts, tmp_path):
    x = loop(contexts,tmp_path,case='tight')
    s = state(x)
    d = propose(s,seedless=True)
    d['normalized_bounds']['C1']=[.9,1.]
    d['normalized_bounds']['C2']=[0.,.05]
    with pytest.raises(ValueError,match='contradiction'):
        adapt_decision(d,x.explorer,s,x.config,round_number=1,first=True)
    x.explorer.close()


def test_seed_error_includes_exact_axis_and_coordinate(contexts,tmp_path):
    x=loop(contexts,tmp_path)
    s=state(x);d=propose(s)
    point=s['calibration']['displayed_samples'][0]['normalized']
    axis='f0'
    d['normalized_bounds'][axis]=[.99,1.] if point[axis]<.99 else [0.,.01]
    with pytest.raises(ValueError,match='seed_boundary_violations') as error:
        adapt_decision(d,x.explorer,s,x.config,round_number=1,first=True)
    assert 'seed_normalized_coordinate' in str(error.value) and 'f0' in str(error.value)
    x.explorer.close()


def test_physics_contradiction_stops_before_policy(contexts,tmp_path):
    p=TestPolicy()
    r=loop(contexts,tmp_path,p,'impossible').run()
    assert r['status']=='PROVEN_M1_INFEASIBLE' and not p.states
    assert r['cost']['M1_calls']==r['cost']['LLM_calls']==0


def test_compatible_new_spec_rejudges_existing_numbers(contexts,tmp_path):
    old=load_physics_context(contexts['global'])
    raw=raw_problem(old['problem'])
    raw['specs'][0].update(min=290000,max=300000)
    raw['specs'][1]['min']=70
    file=tmp_path/'current.json'; file.write_text(json.dumps(raw))
    path,cost=prepare_context(contexts['global'],file,tmp_path/'rebound',calibration_budget=8)
    new=load_physics_context(path)
    rows=list(map(json.loads,(path.parent/'m1_samples.jsonl').read_text().splitlines()))
    prior={r['evidence_id']:r for r in map(json.loads,(contexts['global'].parent/'m1_samples.jsonl').read_text().splitlines())}
    assert cost['new_M1_calls']==0 and cost['rejudged_for_new_spec']
    assert new['problem']['specs'][1]['min']==70
    assert any(r['judgment']!=prior[r['evidence_id']]['judgment'] for r in rows)
    assert all(r['metrics']==prior[r['evidence_id']]['metrics'] for r in rows)


def test_incompatible_coordinate_domain_explicit_stage7_budget(contexts,tmp_path):
    old=load_physics_context(contexts['global'])
    raw=raw_problem(old['problem'])
    raw['parameters']['C1']['min']*=.9
    raw['exploration'].update(sobol_samples=2,physics_seed_count=1,sensitivity_representatives=0)
    file=tmp_path/'domain.json'; file.write_text(json.dumps(raw))
    path,cost=prepare_context(contexts['global'],file,tmp_path/'fresh',calibration_budget=2)
    assert cost['mode']=='EXPLICIT_NEW_STAGE7_CALIBRATION_INCOMPATIBLE_COORDINATES'
    assert cost['new_M1_calls']<=2
    assert load_physics_context(path)['problem']['parameters']['C1']['min']==raw['parameters']['C1']['min']


def test_provider_failure_not_mock_success(contexts,tmp_path):
    x=loop(contexts,tmp_path,TestPolicy(provider_fail=True))
    result=x.run()
    assert result['status']=='LLM_PROVIDER_FAILED'
    assert not result['new_M1_feasible_allocation']


@pytest.mark.parametrize('text', ['{"action":NaN}', '{"a":1,"a":2}', '{"a":1e999}', '[] trailing'])
def test_strict_json_rejects_ambiguous_or_nonfinite(text):
    with pytest.raises(ValueError):
        strict_json(text)


def test_real_policy_missing_environment_no_network_or_secret(tmp_path,monkeypatch):
    for name in ('UNIT_REGION_MODEL','UNIT_REGION_URL','UNIT_REGION_KEY'):
        monkeypatch.delenv(name,raising=False)
    p=LLMRegionPolicy({'model_env':'UNIT_REGION_MODEL','base_url_env':'UNIT_REGION_URL','api_key_env':'UNIT_REGION_KEY'})
    with pytest.raises(ProviderError,match='ENVIRONMENT_UNAVAILABLE'):
        p.decide({},tmp_path/'call')
    assert not p.calls[0]['real_network_call']


def test_real_policy_worker_response_and_usage_saved_without_secret(tmp_path,monkeypatch):
    for k,v in [('UNIT_REGION_MODEL','model'),('UNIT_REGION_URL','https://unused.invalid'),('UNIT_REGION_KEY','unit-secret-credential')]:
        monkeypatch.setenv(k,v)
    def reply(command,**kwargs):
        output=Path(command[command.index('--response')+1]); status=Path(command[command.index('--status')+1])
        output.write_text(json.dumps({'model':'model','usage':{'input_tokens':1,'output_tokens':2},
            'content':[{'type':'text','text':'{"action":"STOP","reason":"done","evidence_ids":["x"]}'}]}))
        status.write_text(json.dumps({'status':'RESPONDED','real_network_call':True,'http_status':200}))
        return subprocess.CompletedProcess(command,0)
    monkeypatch.setattr('pll_allocation.agent.region_policy.subprocess.run',reply)
    p=LLMRegionPolicy({'model_env':'UNIT_REGION_MODEL','base_url_env':'UNIT_REGION_URL','api_key_env':'UNIT_REGION_KEY'})
    assert p.decide({},tmp_path/'call')['action']=='STOP'
    assert p.calls[0]['usage']['output_tokens']==2
    assert all(b'unit-secret-credential' not in f.read_bytes() for f in tmp_path.rglob('*') if f.is_file())


@pytest.mark.parametrize('updates', [{'max_llm_calls':0},{'total_m1_budget':1},{'seed_probe_budget':100}])
def test_invalid_configuration_rejected(updates):
    cfg=config(); cfg.update(updates)
    with pytest.raises(ValueError): validate_config(cfg)


def test_provider_config_rejects_embedded_key():
    with pytest.raises(ValueError): validate_provider({'api_key':'not-a-config-field'})


def test_no_supported_enabled_specs_stop_without_llm(contexts,tmp_path):
    old=load_physics_context(contexts['global'])
    raw=raw_problem(old['problem'])
    for s in raw['specs']:
        if s['evaluation_source']=='M1':
            s['enabled']=False
    file=tmp_path/'unsupported.json';file.write_text(json.dumps(raw))
    p=TestPolicy()
    x=loop(contexts,tmp_path,p,problem_path=file)
    r=x.run()
    assert r['status']=='M1_CAPABILITY_INSUFFICIENT'
    assert not p.states and not r['new_M1_feasible_allocation']


def test_repeated_invalid_decisions_stop_without_optimizer(contexts,tmp_path):
    class AlwaysInvalid(TestPolicy):
        def decide(self,s,directory):
            raw=propose(s);raw['evidence_ids']=['invented'];return raw
    x=loop(contexts,tmp_path,AlwaysInvalid())
    r=x.run()
    assert r['status']=='INVALID_LLM_DECISION'
    # Invalid proposals do not search; the retained calibration recommendation
    # still gets its reserved formal audit call under the stabilization contract.
    assert r['cost']['M1_calls']==1 and not x.history
    assert r['m1_allocation_status'] == 'KNOWN_M1_FEASIBLE_RECHECKED'
    assert not x.explorer.observations


def test_stage8b_cli_rejects_mixed_m2_mode(contexts,tmp_path):
    from pll_allocation.pipeline import main
    assert main(['--out',str(tmp_path/'bad'),'--llm-region-context',str(contexts['global']),
                 '--planner-config','configs/agent/region_search.json','--m2-budget','1'])==2
    assert not (tmp_path/'bad').exists()
