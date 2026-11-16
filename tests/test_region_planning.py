"""TEST policies and actual bounded M1; these tests never claim real LLM results."""
from copy import deepcopy
import json
from pathlib import Path
import pytest

from pll_allocation.agent.subregion_contracts import validate_config,validate_exploration,union_volume
from pll_allocation.agent.subregion_loop import prepare_initial,run_subregion,deterministic
from pll_allocation.agent.subregion_prior import build_prior
from pll_allocation.agent.subregion_tools import execute_tool
from pll_allocation.agent.candidates import CandidateArchive
from pll_allocation.agent.handoff import build_handoff,validate_handoff
from pll_allocation.agent.region_policy import ProviderError,LLMRegionPolicy,PROMPT
from pll_allocation.allocation.core import Meter
from pll_allocation.exploration import load_physics_context
from pll_allocation.physics_mapping.model import evaluate
from pll_allocation.region_explorer import RegionExplorer
from pll_allocation.region_explorer.assessment import contains_parameters

ROOT=Path(__file__).resolve().parents[1]
def config():
    c=json.loads((ROOT/'configs/agent/region_planning.json').read_text())
    c.update(total_m1_budget=32,initial_m1_budget=4,global_m1_budget=4,round_m1_budget=12,
             max_decisions=2,max_tool_proposals=16,initial_sobol_samples=16,global_sobol_samples=16)
    return c

@pytest.fixture(scope='module')
def initial(tmp_path_factory):
    root=tmp_path_factory.mktemp('p75')
    p=json.loads((ROOT/'configs/problems/nominal.json').read_text())
    p['exploration'].update(max_m1_evaluations=32,sobol_samples=16,physics_seed_count=0,sensitivity_representatives=0)
    source=root/'problem.json';source.write_text(json.dumps(p))
    ctx=prepare_initial(source,root/'initial',config())
    return source,ctx

class Policy:
    def __init__(self,fail=False,invalid=False):self.calls=[];self.states=[];self.fail=fail;self.invalid=invalid
    def decide(self,state,directory):
        self.states.append(deepcopy(state))
        if self.fail:raise ProviderError('TEST provider failure')
        d=deterministic(state,state['round']);d['decision_id']='TEST:'+str(len(self.states))
        if self.invalid:d['regions'][0]['normalized_bounds']['C1']=[-.1,.5]
        return d

def explorer(initial,tmp_path):return RegionExplorer(initial[1],tmp_path/'executor',m1_budget=28)

def test_initial_small_no_physics_menu(initial):
    ctx=load_physics_context(initial[1]);assert ctx['exploration_source']=='SMALL_INITIAL_SOBOL_ONLY'
    samples=[json.loads(s) for s in (initial[1].parent/'m1_samples.jsonl').read_text().splitlines()]
    assert sum(bool(r['formal_M1_result']) for r in samples)<=4
    assert all(r['origin'].startswith('LOCAL_SOBOL') and r['evidence_id'].startswith('CAL:') for r in samples)

def test_prior_current_evidence_no_fixed_region_menu(initial,tmp_path):
    ex=explorer(initial,tmp_path);p=build_prior(ex,config(),[],1)
    assert 'candidate_regions' not in json.dumps(p) and 'normalized_bounds' not in json.dumps(p)
    assert len(p['problem']['parameters'])==6
    assert {'NECESSARY','ANALYTICAL_RELATION','HEURISTIC'}<={r['category'] for r in p['relations']}
    assert p['capability_boundary']['lock_time_s']=='PENDING_M2'
    assert all(r['source'] and r['variables'] and r['metrics'] for r in p['relations'])
    assert not p['local_sensitivity']

@pytest.mark.parametrize('mutation',('outside','inverted','missing_axis','budget','unknown_evidence','reserve','unsupported_tool','duplicate','unsupported_metric'))
def test_invalid_decisions_rejected(initial,tmp_path,mutation):
    ex=explorer(initial,tmp_path);p=build_prior(ex,config(),[],1);d=deterministic(p,1);r=d['regions'][0]
    if mutation=='outside':r['normalized_bounds']['Icp'][0]=-.1
    elif mutation=='inverted':r['normalized_bounds']['C2']=[.8,.3]
    elif mutation=='missing_axis':del r['normalized_bounds']['Kvco']
    elif mutation=='budget':r['tools'][0]['m1_budget']=100
    elif mutation=='unknown_evidence':r['evidence_ids']=['HISTORICAL:NOT_LOADED']
    elif mutation=='reserve':d['global_coverage_budget']=0
    elif mutation=='unsupported_tool':r['tools'][0]['method']='BOUNDARY_PROBING'
    elif mutation=='duplicate':d['regions'].append(deepcopy(r))
    elif mutation=='unsupported_metric':r['focus_constraints']=['lock_time_s']
    with pytest.raises(ValueError):validate_exploration(d,problem=ex.problem,allowed_evidence=set(p['allowed_evidence_ids']),
        evidence=ex.evidence,max_budget=12,global_reserve=4,prior_id=p['prior_context_sha256'])

def test_overlap_and_tiny_diagnostics(initial,tmp_path):
    ex=explorer(initial,tmp_path);p=build_prior(ex,config(),[],1);d=deterministic(p,1)
    r=deepcopy(d['regions'][0]);r['region_id']='SECOND';r['normalized_bounds']['Icp']=[.001,1.]
    for x in d['regions'][0]['tools']+r['tools']:x['m1_budget']=2
    d['regions'].append(r)
    _,v=validate_exploration(d,problem=ex.problem,allowed_evidence=set(p['allowed_evidence_ids']),
        evidence=ex.evidence,max_budget=12,global_reserve=4,prior_id=p['prior_context_sha256'])
    assert any(x['code']=='LARGE_OVERLAP' for x in v['diagnostics'])
    assert union_volume([x['normalized_bounds'] for x in d['regions']])==pytest.approx(1.)

def test_full_test_loop_budget_persistence_export(initial,tmp_path):
    policy=Policy()
    result=run_subregion(initial[0],tmp_path/'loop',config=config(),initial_context_path=initial[1],policy=policy)
    assert result['failure'] is None and result['cost']['M1_calls']<=32
    assert result['cost']['LLM_calls']==0 and result['cost']['test_policy_calls']==2
    assert len(policy.states[1]['history'])==1
    ctx=load_physics_context(result['physics_context'])
    assert not ctx['capability_boundary']['LLM_executed']
    samples=[json.loads(s) for s in (Path(result['physics_context']).parent/'m1_samples.jsonl').read_text().splitlines()]
    assert len({s['evidence_id'] for s in samples})==len(samples)
    assert all(s['evidence_id'].startswith('P75:') for s in samples)
    downstream=RegionExplorer(result['physics_context'],tmp_path/'downstream',m1_budget=10)
    assert all(contains_parameters(downstream.problem,{k:[0.,1.] for k in downstream.problem['parameters']},s['parameters']) for s in samples)

@pytest.mark.parametrize('failure',('provider','invalid'))
def test_failure_preserves_calibration_and_global_path(initial,tmp_path,failure):
    policy=Policy(fail=failure=='provider',invalid=failure=='invalid')
    result=run_subregion(initial[0],tmp_path/'loop',config=config(),initial_context_path=initial[1],policy=policy)
    assert result['status']==('LLM_PROVIDER_FAILED' if failure=='provider' else 'INVALID_LLM_DECISION')
    assert result['cost']['M1_calls']<=32
    assert (tmp_path/'loop/global_coverage_observation.json').exists()
    assert result['cost']['LLM_calls']==0

def test_provider_default_prompt_unchanged():
    assert LLMRegionPolicy({}).prompt==PROMPT
    assert LLMRegionPolicy({},prompt='TEST other decision contract').prompt.startswith('TEST')

@pytest.mark.parametrize('axis',('Icp','Rz','C1','C2','f0','Kvco'))
def test_continuous_box_and_budget(initial,tmp_path,axis):
    ex=explorer(initial,tmp_path)
    region={'region_id':'TEST_BOX','normalized_bounds':{k:[.15,.85] for k in ex.problem['parameters']}}
    region['normalized_bounds'][axis]=[.31,.63]
    obs=execute_tool(ex,decision_id='TEST',region=region,tool={'method':'SOBOL_IN_REGION','m1_budget':2,'seed_id':None},
        seed=31,config=config(),meter=Meter())
    assert obs['actual_region_equals_requested'] and ex.counts['M1_calls']<=2
    assert all(contains_parameters(ex.problem,region['normalized_bounds'],r['parameters']) for r in ex.rows)

def test_duplicate_candidates_cached_and_formal_failure_charged(initial,tmp_path,monkeypatch):
    ex=explorer(initial,tmp_path)
    seed=next(s for s in ex.calibration_samples if s['M1_status']=='OK')
    from pll_allocation.agent.subregion_tools import envelope
    d=envelope(ex,decision_id='CACHE',region_id='CACHE',bounds={k:[0.,1.] for k in ex.problem['parameters']},budget=3,seed=23,proposals=2)
    o=ex.execute(d,candidate_stream=iter([seed['parameters'],seed['parameters']]),tool_name='PHYSICS_GUIDED_SEEDS')
    assert o['cost']['M1_calls']==0 and o['cost']['cache_hits']==2

def test_frozen_full_stage7_cannot_be_initial(initial,tmp_path):
    from pll_allocation.agent.subregion_context import export_context
    p=load_physics_context(initial[1])['problem']
    full=export_context(p,[],tmp_path/'wrong',cost={},scope='STAGE7_COMPLETE')
    with pytest.raises(ValueError,match='small initial'):run_subregion(initial[0],tmp_path/'run',config=config(),initial_context_path=full,policy=Policy())

def test_config_hard_cap():
    c=config();c['total_m1_budget']=10
    with pytest.raises(ValueError):validate_config(c)


def test_true_sensitivity_stencil_is_reused(initial,tmp_path):
    ex=explorer(initial,tmp_path)
    s=next(r for r in ex.calibration_samples if r['M1_status']=='OK')
    region={'region_id':'SLOPE','normalized_bounds':{k:[0.,1.] for k in ex.problem['parameters']}}
    obs=execute_tool(ex,decision_id='SLOPE',region=region,
        tool={'method':'LOCAL_SENSITIVITY','m1_budget':12,'seed_id':s['evidence_id']},seed=32,config=config(),meter=Meter())
    assert obs['sensitivity']['representatives'][0]['center_evidence_id']==s['evidence_id']
    assert ex.counts['M1_calls']<=12
    prior=build_prior(ex,config(),[{'observations':[obs]}],2)
    assert prior['local_sensitivity'][0]['category']=='LOCAL_SENSITIVITY'
    assert prior['local_sensitivity'][0]['center_parameters']==s['parameters']


def test_evaluator_exception_charged_once_then_cached(initial,tmp_path,monkeypatch):
    from pll_allocation.agent.subregion_tools import envelope
    from pll_allocation.exploration.contracts import make_parameters
    ex=explorer(initial,tmp_path)
    point=make_parameters(ex.problem) # legal actual nominal, distinct from Sobol
    def broken(_):raise ArithmeticError('TEST deliberate numerical failure')
    monkeypatch.setattr('pll_allocation.region_explorer.explorer.evaluate',broken)
    d=envelope(ex,decision_id='FAILURE',region_id='FAILURE',bounds={k:[0.,1.] for k in ex.problem['parameters']},budget=3,seed=23,proposals=2)
    obs=ex.execute(d,candidate_stream=iter([point,point]),tool_name='ANALYTICAL_INVERSE')
    assert obs['cost']['M1_calls']==1 and obs['cost']['M1_failures']==1 and obs['cost']['cache_hits']==1
    assert not obs['new_positive_evidence_ids']


@pytest.mark.parametrize('pm', (90.,95.,100.))
def test_necessary_condition_rejects_whole_impossible_region(initial,tmp_path,pm):
    ex=explorer(initial,tmp_path);p=build_prior(ex,config(),[],1)
    problem=deepcopy(ex.problem)
    next(s for s in problem['specs'] if s['metric']=='PM_deg')['min']=pm
    d=deterministic(p,1)
    with pytest.raises(ValueError,match='necessary condition'):
        validate_exploration(d,problem=problem,allowed_evidence=set(p['allowed_evidence_ids']),
            evidence=ex.evidence,max_budget=12,global_reserve=4,prior_id=p['prior_context_sha256'])


def test_no_known_feasible_handoff_blocked(initial,tmp_path):
    ex=explorer(initial,tmp_path)
    archive=CandidateArchive(ex,tmp_path/'archive.jsonl')
    h=build_handoff(ex,archive,None,{'passed':False},{'termination_reason':'TEST_NO_CANDIDATE'},ex.cost())
    assert h['gate_status']=='BLOCKED' and not h['ready_for_stage9']
    with pytest.raises(ValueError):validate_handoff(h)


@pytest.mark.parametrize('row,expected',[
    ({'formal_M1_called':True,'formal_M1_result':None},True),
    ({'formal_M1_called':False,'formal_M1_result':None},False),
    ({'formal_M1_result':{'status':'OK'}},True),
    ({'formal_M1_result':None},False),
])
def test_formal_call_flag_and_legacy_evidence(row,expected):
    from pll_allocation.agent.subregion_context import was_formal_call
    assert was_formal_call(row) is expected


def test_initial_evaluator_exceptions_still_consume_session_budget(initial,tmp_path,monkeypatch):
    import csv
    source=initial[0];cfg=config()
    with monkeypatch.context() as patch:
        def fail(_):raise ArithmeticError('TEST initial calibration exception')
        patch.setattr('pll_allocation.region_explorer.explorer.evaluate',fail)
        ctxpath=prepare_initial(source,tmp_path/'failed_initial',cfg)
    ctx=load_physics_context(ctxpath)
    assert ctx['summary']['formal_M1_calls']==4
    samples=[json.loads(s) for s in (ctxpath.parent/'m1_samples.jsonl').read_text().splitlines()]
    assert sum(r['formal_M1_called'] for r in samples)==4
    assert not any(r['formal_M1_result'] for r in samples)
    with (ctxpath.parent/'m1_samples.csv').open(encoding='utf-8-sig',newline='') as f:
        assert sum(r['formal_M1_called']=='True' for r in csv.DictReader(f))==4
    policy=Policy()
    result=run_subregion(source,tmp_path/'run',config=cfg,initial_context_path=ctxpath,policy=policy)
    assert result['cost']['initial_shared_M1_calls']==4
    assert all(s['budget']['initial_actual_M1']==4 for s in policy.states)
    new=[json.loads(s) for s in (tmp_path/'run/executor/m1_samples.jsonl').read_text().splitlines()]
    formal=[r for r in samples+new if r['formal_M1_called']]
    assert result['cost']['M1_calls']==len(formal)<=32
    first=next((i for i,r in enumerate(formal,1) if r['judgment']['m1_feasibility']=='FEASIBLE'),None)
    assert result['first_M1_feasible_evaluation']==first
    assert first is None or first>4


def test_failed_initial_calls_cannot_bypass_calibration_cap(initial,tmp_path,monkeypatch):
    with monkeypatch.context() as patch:
        def fail(_):raise ArithmeticError('TEST rejected over-cap initial')
        patch.setattr('pll_allocation.region_explorer.explorer.evaluate',fail)
        ctxpath=prepare_initial(initial[0],tmp_path/'failed_initial',config())
    smaller=config();smaller['initial_m1_budget']=3
    with pytest.raises(ValueError,match='small Sobol-only'):
        run_subregion(initial[0],tmp_path/'run',config=smaller,initial_context_path=ctxpath,policy=Policy())
