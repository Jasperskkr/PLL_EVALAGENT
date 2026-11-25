"""TEST policies, real bounded M1, never recorded as real LLM research."""
from copy import deepcopy
import json
import math
from pathlib import Path

import pytest

from pll_allocation.agent.initial_allocation import run_initial_allocation
from pll_allocation.agent.physics_tool_policy import DeterministicToolPolicy,validate_feedback,validate_config
from pll_allocation.agent.region_policy import ProviderError
from pll_allocation.agent.handoff import validate_handoff
from pll_allocation.agent.subregion_loop import prepare_initial
from pll_allocation.exploration.contracts import load_problem,resolve_problem,check_candidate,coordinate
from pll_allocation.exploration.physics_region_builder import (
    STRATEGIES,build_physics_region,gain_tuning_interval,validate_request,around_seed,
)
from pll_allocation.exploration.engine import model_identity
from pll_allocation.region_explorer.assessment import contains_parameters

ROOT=Path(__file__).resolve().parents[1]
MODEL=model_identity()['model_sha256']
def config():
    c=json.loads((ROOT/'configs/agent/llm_physics.json').read_text(encoding='utf-8'))
    c.update(policy='DETERMINISTIC_PHYSICS_TOOL',total_m1_budget=64,initial_m1_budget=4,initial_sobol_samples=16,max_decisions=3,max_llm_calls=4,max_round_m1=40)
    return c
def problem(name='nominal.json'):
    return load_problem(ROOT/'configs/problems'/name)
def request(p,strategy='HIGH_PM_LF_SHAPE',count=3,attempts=16):
    return {'schema_version':'pll-physics-region-request-1.0','request_id':'TEST',
        'problem_sha256':p['problem_sha256'],'model_fingerprint':MODEL,'strategy':strategy,
        'target_bw_fraction':[.5,.5],'physics_focus':['LF_SHAPE','GAIN_SPLIT'],
        'tuning_preference':'INTERIOR','seed_count':count,'region_width_policy':'BALANCED',
        'budget':{'construction_attempts':attempts,'m1_calls':max(3,count)},'evidence_ids':['REL:shape']}
@pytest.fixture(scope='module')
def initial(tmp_path_factory):
    root=tmp_path_factory.mktemp('initial_physics');p=ROOT/'configs/problems/nominal.json'
    cfg=json.loads((ROOT/'configs/agent/region_planning.json').read_text(encoding='utf-8'));cfg.update(initial_m1_budget=4,initial_sobol_samples=16)
    return p,prepare_initial(p,root/'initial',cfg)

@pytest.mark.parametrize('strategy',sorted(STRATEGIES))
def test_all_strategy_seeds_in_global_domain_and_actual_box(strategy):
    p=problem();r=request(p,strategy);x=build_physics_region(p,r,model_fingerprint=MODEL,random_seed=23)
    assert x['seeds'] and not x['m1_evaluated'] and x['m1_status']=='M1_NOT_EVALUATED'
    for s in x['seeds']:
        assert check_candidate(p,s['parameters'])['status']=='NECESSARY_CONDITIONS_SATISFIED'
        assert contains_parameters(p,s['normalized_bounds'],s['parameters'])
        assert all(0<=lo<hi<=1 for lo,hi in s['normalized_bounds'].values())
    assert x['cost']['inverse_calls']<=x['cost']['construction_attempts']<=r['budget']['construction_attempts']

@pytest.mark.parametrize('product,expected',[(1.,'NO_COMPATIBLE_GAIN_SPLIT'),(1e8,'NO_COMPATIBLE_GAIN_SPLIT'),(2000.,'JOINT_INTERVAL_COMPATIBLE')])
def test_gain_intersections(product,expected):
    assert gain_tuning_interval(problem(),product)['status']==expected

@pytest.mark.parametrize('rails',[(0.,1.2),(-.6,.6),(-1.2,0.)])
def test_tuning_interval_handles_signed_rails(rails):
    p=problem();p['fixed_parameters']['Vctrl_min']['value']=rails[0];p['fixed_parameters']['Vctrl_max']['value']=rails[1]
    if rails[1]<=0:
        assert gain_tuning_interval(p,2000.)['status']=='TUNING_CONFLICT'
    else:
        assert gain_tuning_interval(p,2000.)['status']=='JOINT_INTERVAL_COMPATIBLE'

@pytest.mark.parametrize('axis',('Icp','Rz','C1','C2','f0','Kvco'))
@pytest.mark.parametrize('scale',('linear','log'))
def test_six_axis_units_and_coordinates(axis,scale):
    p=problem();p['parameters'][axis]['scale']=scale
    x=build_physics_region(p,request(p,count=1),model_fingerprint=MODEL,random_seed=13)
    assert x['seeds'];seed=x['seeds'][0]
    value=seed['parameters']['values'][axis]
    assert value['unit']==p['parameters'][axis]['unit']
    u=coordinate(p['parameters'][axis],value['value'])
    assert coordinate(p['parameters'][axis],u,inverse=True)==pytest.approx(value['value'],rel=1e-13)
    assert contains_parameters(p,seed['normalized_bounds'],seed['parameters'])

@pytest.mark.parametrize('pm', (90.,95.,100.))
def test_impossible_pm_certificate_stops_inverse(pm):
    p=problem();next(s for s in p['specs'] if s['metric']=='PM_deg')['min']=pm
    x=build_physics_region(p,request(p),model_fingerprint=MODEL,random_seed=23)
    assert x['global_infeasibility_proven'] and x['cost']['inverse_calls']==0 and not x['seeds']

def test_strategy_failure_is_not_global_infeasibility():
    p=problem();p['parameters']['Rz'].update(min=1e-3,max=1e-2,default=.005)
    x=build_physics_region(p,request(p,attempts=2),model_fingerprint=MODEL,random_seed=23)
    assert not x['seeds'] and not x['global_infeasibility_proven']
    assert x['cost']['construction_attempts']==2
    assert all(a['status']=='GLOBAL_BOUNDS_CONFLICT' for a in x['attempts'])

def test_constructed_gain_and_tuning_diversity():
    p=problem();r=request(p,'GAIN_SPLIT_EXPLORATION',count=6);r['tuning_preference']='DIVERSE'
    x=build_physics_region(p,r,model_fingerprint=MODEL,random_seed=23)
    pairs={(s['parameters']['values']['Icp']['value'],s['parameters']['values']['Kvco']['value']) for s in x['seeds']}
    voltages={s['screening']['derived']['Vctrl_required_V'] for s in x['seeds']}
    assert len(pairs)>=2 and len(voltages)>=3
    products=[s['screening']['derived']['Icp_Kvco_product'] for s in x['seeds']]
    assert max(products)==pytest.approx(min(products),rel=1e-12)

@pytest.mark.parametrize('field,value', [('seed_count',0),('strategy','BO'),('target_bw_fraction',[-.1,.5]),('region_width_policy','ZERO')])
def test_request_validator(field,value):
    p=problem();r=request(p);r[field]=value
    with pytest.raises(ValueError):validate_request(r,p,MODEL,{'REL:shape'},attempts_left=16,m1_left=8)

@pytest.mark.parametrize('request_id',('../escape','a/b','a\\b','.', 'a b'))
def test_request_cannot_escape_output_directory(request_id):
    p=problem();r=request(p);r['request_id']=request_id
    with pytest.raises(ValueError):validate_request(r,p,MODEL,{'REL:shape'},attempts_left=16,m1_left=8)

@pytest.mark.parametrize('bw,pm,factor',[(185000.,52.,.9),(335000.,63.,1.1),(245000.,55.,1.05)])
def test_unseen_specs_domains_reproducible_bounded_construction(bw,pm,factor):
    p=problem()
    for s in p['specs']:
        if s['metric']=='BW_Hz':s.update(min=.95*bw,max=1.05*bw)
        if s['metric']=='PM_deg':s['min']=pm
    for a in ('C1','C2'):
        for k in ('min','max','default'):p['parameters'][a][k]*=factor
    r=request(p,attempts=5);xs=[build_physics_region(p,r,model_fingerprint=MODEL,random_seed=91) for _ in range(2)]
    assert xs[0]['seeds']==xs[1]['seeds'] and xs[0]['attempts']==xs[1]['attempts']
    assert all(x['cost']['construction_attempts']<=5 and x['cost']['M1_calls']==0 for x in xs)
    assert all(contains_parameters(p,s['normalized_bounds'],s['parameters']) for s in xs[0]['seeds'])

@pytest.mark.parametrize('which',('attempts','m1','evidence','model'))
def test_hard_request_limits(which):
    p=problem();r=request(p)
    if which=='attempts':r['budget']['construction_attempts']=17
    if which=='m1':r['budget']['m1_calls']=9
    if which=='evidence':r['evidence_ids']=['UNKNOWN']
    if which=='model':r['model_fingerprint']='wrong'
    with pytest.raises(ValueError):validate_request(r,p,MODEL,{'REL:shape'},attempts_left=16,m1_left=8)

def test_existing_runner_build_optimize_recheck_handoff(initial,tmp_path):
    x=run_initial_allocation(initial[0],tmp_path/'run',config=config(),initial_context=initial[1])
    assert x['status']!='PIPELINE_ERROR' and x['cost']['M1_calls']<=64
    assert x['cost']['LLM_calls']==0 and x['constructed_seed_count']>=1
    root=tmp_path/'run';h=json.loads((root/'verification_handoff.json').read_text(encoding='utf-8'));validate_handoff(h)
    assert h['M2_status']=='NOT_EVALUATED'
    rows=[json.loads(s) for s in (root/'executor/m1_samples.jsonl').read_text(encoding='utf-8').splitlines()]
    assert sum(r['formal_M1_called'] for r in rows)+4==x['cost']['M1_calls']
    assert any(r['independent_final_recheck'] for r in rows)
    decisions=[json.loads(s)['decision'] for s in (root/'executor/search_decisions.jsonl').read_text(encoding='utf-8').splitlines()]
    proposals=json.loads((root/'REGION_CONSTRUCTION_RESULTS.json').read_text(encoding='utf-8'))['proposals']
    boxes={s['region_id']:s['normalized_bounds'] for p in proposals for s in p['seeds']}
    assert any(d['search_method']=='SLSQP' for d in decisions)
    assert all(d['normalized_bounds']==boxes[d['region']['region_id']] for d in decisions if d['search_method']=='SLSQP')
    state=json.loads((root/'round_02/planner_state_00.json').read_text(encoding='utf-8'))
    assert state['sensitivity_status']=='NOT_MEASURED_NO_DERIVATIVE_CLAIM'
    assert all(i in state['allowed_evidence_ids'] for r in state['available_tool_regions'] for i in r['formal_M1_seed_ids'])
    provenance=json.loads((root/'round_01/search_decision.json').read_text(encoding='utf-8'))
    assert provenance['numeric_seed_and_box_proposer']=='PHYSICS_REGION_BUILDER'

class FailAfterBuild(DeterministicToolPolicy):
    def decide(self,state,directory):
        if state['history']:raise ProviderError('TEST provider after known candidates')
        return super().decide(state,directory)

def test_provider_failure_does_not_lose_candidates(initial,tmp_path):
    x=run_initial_allocation(initial[0],tmp_path/'run',config=config(),initial_context=initial[1],policy=FailAfterBuild())
    assert x['status']=='LLM_PROVIDER_FAILED'
    h=json.loads((tmp_path/'run/verification_handoff.json').read_text(encoding='utf-8'));validate_handoff(h)
    assert h['recommended_nominal'] and x['cost']['M1_calls']<=64

def test_future_feedback_is_read_only_provenance(initial,tmp_path):
    from pll_allocation.exploration import load_physics_context
    p=load_physics_context(initial[1])['problem']
    f={'schema_version':'pll-search-feedback-1.0','problem_sha256':p['problem_sha256'],'model_fingerprint':MODEL,
       'observations':[{'evidence_id':'EXT:TEST','candidate_sha256':'0'*64,'model_level':'M2','protocol':'TEST_NOT_REAL_M2',
        'measurements':{'lock_time_s':1e-4},'failed_constraints':['lock_time_s'],'m1_m2_deviation':{}}],
       'preferred_physics_focus':['TUNING'],'historical_failure_ids':['TEST_FAILED']}
    validated=validate_feedback(f,p,MODEL)
    assert validated['scope']=='CALLER_SUPPLIED_EXTERNAL_FEEDBACK_NOT_VERIFIED_BY_THIS_RUN'
    f['model_fingerprint']='wrong'
    with pytest.raises(ValueError):validate_feedback(f,p,MODEL)

def test_unknown_units_rejected_by_original_problem():
    raw=json.loads((ROOT/'configs/problems/nominal.json').read_text(encoding='utf-8'))
    raw['parameters']['C1']['unit']='pF'
    with pytest.raises(ValueError):resolve_problem(raw)

def test_misnested_budget_has_structured_repair_diagnostics():
    p=problem();r=request(p);r['budget']['evidence_ids']=r['evidence_ids']
    with pytest.raises(ValueError) as e:validate_request(r,p,MODEL,{'REL:shape'},attempts_left=16,m1_left=8)
    assert e.value.details['path']=='request.budget'
    assert e.value.details['unexpected_fields']==['evidence_ids']

class MeasureOnce(DeterministicToolPolicy):
    def decide(self,state,directory):
        if state['history'] and not any(h['action']=='PROBE' for h in state['history']):
            r=next(r for r in state['available_tool_regions'] if r['formal_M1_seed_ids'])
            return {'schema_version':'pll-physics-tool-decision-1.0','state_sha256':state['state_sha256'],
                'action':'MEASURE_LOCAL_SENSITIVITY','region_id':r['region_id'],'seed_id':r['formal_M1_seed_ids'][0],
                'm1_budget':12,'reason':'TEST actual local stencil, not a global slope claim',
                'evidence_ids':r['formal_M1_seed_ids']}
        return super().decide(state,directory)

def test_optional_sensitivity_tool_returns_actual_evidence(initial,tmp_path):
    c=config();c.update(max_decisions=4)
    x=run_initial_allocation(initial[0],tmp_path/'run',config=c,initial_context=initial[1],policy=MeasureOnce())
    assert x['cost']['M1_calls']<=64 and x['status']!='PIPELINE_ERROR'
    state=json.loads((tmp_path/'run/round_03/planner_state_00.json').read_text(encoding='utf-8'))
    assert state['local_sensitivity'] and state['sensitivity_status']=='ACTUAL_LOCAL_STENCILS'
    derivative=state['local_sensitivity'][0]
    assert derivative['center_values_SI'] and any(s['evidence_ids'] for s in derivative['stencils'].values())

def test_caller_feedback_seed_is_charged_before_direct_optimization(initial,tmp_path):
    from pll_allocation.exploration import load_physics_context
    p=load_physics_context(initial[1])['problem'];seed=build_physics_region(p,request(p,count=1),model_fingerprint=MODEL,random_seed=23)['seeds'][0]
    f={'schema_version':'pll-search-feedback-1.0','problem_sha256':p['problem_sha256'],'model_fingerprint':MODEL,
        'observations':[{'evidence_id':'EXT:TEST_INPUT','candidate_sha256':seed['parameter_sha256'],
            'parameters':seed['parameters'],'model_level':'M1','protocol':'TEST_CALLER_DATA_NOT_M2',
            'measurements':{},'failed_constraints':[],'m1_m2_deviation':{}}],
        'preferred_physics_focus':['TUNING'],'historical_failure_ids':[]}
    x=run_initial_allocation(initial[0],tmp_path/'run',config=config(),initial_context=initial[1],feedback=f)
    assert x['cost']['feedback_seed_recheck_M1_calls']==1 and x['cost']['M1_calls']<=64
    d=json.loads((tmp_path/'run/round_01/search_decision.json').read_text(encoding='utf-8'))['decision']
    assert d['action']=='OPTIMIZE' and 'f0' in d['active_variables'] and x['constructed_seed_count']==0
    f['observations'][0]['candidate_sha256']='0'*64
    with pytest.raises(ValueError):validate_feedback(f,p,MODEL)
