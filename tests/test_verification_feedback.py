"""TEST-only M2/Policy fault injection. Never real LLM or M2 research evidence."""
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch
import subprocess

import pytest

from pll_allocation.agent.initial_allocation import run_initial_allocation
from pll_allocation.agent.physics_tool_policy import DeterministicToolPolicy
from pll_allocation.agent.region_policy import ProviderError
from pll_allocation.agent.feedback import (run_stage9_feedback, load_handoff, applicable,
    feedback_summary, search_feedback)
from pll_allocation.agent.handoff import validate_handoff
from pll_allocation.agent.subregion_loop import prepare_initial
from pll_allocation.physics_mapping.model import fingerprint
from pll_allocation.verification.continuous import (verification_request, validate_request,
    judge_measurements, execute_request)
from pll_allocation.verification.verify import validate_proposal, example_proposal

ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture(scope='module')
def saved(tmp_path_factory):
    root=tmp_path_factory.mktemp('stage9_input')
    p=ROOT/'configs/problems/nominal.json'
    pilot=json.loads((ROOT/'configs/agent/region_planning.json').read_text(encoding='utf-8'))
    pilot.update(initial_m1_budget=4,initial_sobol_samples=16)
    context=prepare_initial(p,root/'calibration',pilot)
    cfg=json.loads((ROOT/'configs/agent/llm_physics.json').read_text(encoding='utf-8'))
    cfg.update(policy='DETERMINISTIC_PHYSICS_TOOL',total_m1_budget=48,initial_m1_budget=4,
        initial_sobol_samples=16,max_decisions=2,max_llm_calls=3,max_round_m1=30)
    run_initial_allocation(p,root/'initial',config=cfg,initial_context=context)
    path=root/'initial/stage9_handoff.json'
    h=json.loads(path.read_text(encoding='utf-8')); validate_handoff(h)
    cfg['policy']='LLM_PHYSICS_TOOL'
    return path,p,h,cfg

def config(saved,**updates):
    x={'schema_version':'pll-stage9-feedback-1.0','m1_budget':90,'m2_budget':2,'llm_budget':4,
       'max_reallocations':1,'m2_timeout_s':30,'search':saved[3]}
    return x|updates

def request(saved):
    return verification_request(saved[2],run_id='TEST',observation_id='TEST:1',timeout_s=30)

def synthetic(req,*,bw=225000,lock=20e-6,captured=True,converged=True):
    capture={'numerical_converged':converged,
        'reliable_capture_status':'CAPTURED_WITHIN_WINDOW' if captured else 'NOT_CAPTURED_WITHIN_WINDOW',
        'fine':{'lock_time_s':lock},'step_comparison':{'lock_time_difference_s':0}}
    compare={'numerical_converged':converged,'M2_BW_measurement':{'BW_Hz':bw},
        'BW_numerical_envelope_Hz':[bw-10,bw+10]}
    return judge_measurements(req,capture,compare)

def fake_m2(**values):
    def run(req,out):
        x=synthetic(req,**values)
        x.update(candidate_sha256=req['candidate_sha256'],request_sha256=req['request_sha256'],
            problem_sha256=req['problem_sha256'],protocol_sha256=req['protocol_sha256'],
            M2_model_fingerprint=fingerprint(req['M2_model']),evidence_id='TEST_M2:'+req['observation_id'],
            observation_id=req['observation_id'],execution_status='COMPLETED',raw_evidence_path='TEST_NO_WAVEFORM',
            cost={'posthoc_M1_calls':0,'completed_native_runs':0,'integration_points':0,'native_elapsed_s':0})
        return x
    return run

@pytest.mark.parametrize('field',('candidate_sha256','parameters','protocol_sha256','M2_model','budget'))
def test_request_tamper_rejected(saved,field):
    req=request(saved)
    if field=='parameters':req[field]['values']['C1']['value']*=1.01
    elif field=='budget':req[field]['posthoc_M1_reserve']=0
    else:req[field]='wrong'
    with pytest.raises(ValueError):validate_request(req)
    req['request_sha256']=fingerprint({k:v for k,v in req.items() if k!='request_sha256'})
    with pytest.raises(ValueError):validate_request(req)

@pytest.mark.parametrize('key',('block_spec_SI','handoff_sha256','ready_for_stage9'))
def test_handoff_tamper_rejected(saved,key):
    h=deepcopy(saved[2]);h[key]=False
    with pytest.raises((ValueError,TypeError)):verification_request(h,run_id='TEST',observation_id='TEST',timeout_s=1)

def test_original_frozen_gate_still_rejects_continuous_contract(saved):
    p=example_proposal(saved[2]['recommended_nominal']['parameters'])
    with pytest.raises(ValueError):validate_proposal(p)
    validate_request(request(saved))

@pytest.mark.parametrize('bw,expected',[(225000,'PASS'),(400000,'FAIL'),(150000,'UNKNOWN')])
def test_bw_envelope_boundary(saved,bw,expected):
    x=synthetic(request(saved),bw=bw)
    assert next(c['status'] for c in x['constraints'] if c['metric']=='BW_Hz')==expected
    assert x['metrics']['PM_deg']['value'] is None
    assert not x['FULL_SYSTEMSPEC_CERTIFIED']

@pytest.mark.parametrize('captured,converged',[(False,True),(True,False),(False,False)])
def test_unknown_is_not_physical_fail(saved,captured,converged):
    x=synthetic(request(saved),captured=captured,converged=converged)
    assert next(c['status'] for c in x['constraints'] if c['metric']=='lock_time_s')=='UNKNOWN'
    assert x['overall_status']=='UNKNOWN'

@pytest.mark.parametrize('budget', (0,1))
def test_zero_budgets_no_uncontrolled_execution(saved,tmp_path,budget):
    called=[]
    def backend(*a):called.append(a);return fake_m2()(*a)
    result=run_stage9_feedback(saved[0],tmp_path/'run',problem_config=saved[1],
        stage9_config=config(saved,m2_budget=budget,m1_budget=0),m2_executor=backend)
    assert not called and result['cost']['M1_calls']==0 and result['cost']['M2_verifications']==0
    assert result['best_known_M1']['parameter_sha256']==saved[2]['recommended_nominal']['parameter_sha256']

def test_test_backend_label_and_m2_partial_pass(saved,tmp_path):
    r=run_stage9_feedback(saved[0],tmp_path/'run',problem_config=saved[1],
        stage9_config=config(saved),m2_executor=fake_m2())
    assert r['mode']=='TEST_INJECTED_NOT_RESEARCH'
    assert r['supported_M2_status']=='PASS' and r['M2_status']=='UNKNOWN'
    assert r['recommended_M2_supported'] and not r['real_fail_reverification_completed']
    root = tmp_path/'run'
    assert json.loads((root/'verification_result.json').read_text(encoding='utf-8')) == json.loads(json.dumps(r))
    assert (root/'verification_result.json').read_bytes() == (root/'stage9_final_result.json').read_bytes()
    assert (root/'cost_summary.json').read_bytes() == (root/'stage9_cost_summary.json').read_bytes()

class Broken(DeterministicToolPolicy):
    def decide(self,state,directory):raise ProviderError('TEST unavailable')

def test_provider_failure_keeps_m1_and_m2_fail(saved,tmp_path):
    r=run_stage9_feedback(saved[0],tmp_path/'run',problem_config=saved[1],stage9_config=config(saved),
        m2_executor=fake_m2(bw=400000),policy=Broken())
    assert r['termination_reason']=='LLM_PROVIDER_FAILED', r['failure']
    assert r['M2_status']=='FAIL' and r['m1_allocation_status']=='KNOWN_FEASIBLE_PRESERVED'
    assert r['best_known_M1'] and r['cost']['M1_calls']<=90

def test_feedback_distinct_candidate_reverification_test_only(saved,tmp_path):
    r=run_stage9_feedback(saved[0],tmp_path/'run',problem_config=saved[1],stage9_config=config(saved),
        m2_executor=fake_m2(bw=400000),policy=DeterministicToolPolicy())
    assert len(r['verified_history'])==2,r['failure']
    assert len({h['candidate_sha256'] for h in r['verified_history']})==2
    assert not r['real_fail_reverification_completed'] and r['cost']['M1_calls']<=90
    assert r['M2_status']=='FAIL' and r['best_known_M1']
    records=[json.loads(s) for s in (tmp_path/'run/reallocation_candidates.jsonl').read_text().splitlines()]
    assert records[0]['recheck']['passed'] and records[0]['feedback_evidence_id'].startswith('TEST_M2:')

def test_deadline_and_worker_crash_keep_unknown_and_cost(saved,tmp_path):
    req=request(saved)
    for i,exc in enumerate((subprocess.TimeoutExpired('TEST',.01),None)):
        output=tmp_path/str(i)
        with patch('pll_allocation.verification.continuous.subprocess.run') as p:
            if exc:p.side_effect=exc
            else:p.return_value=subprocess.CompletedProcess('TEST',9,b'',b'TEST crash')
            x=execute_request(req,output)
        assert x['overall_status']=='UNKNOWN'
        assert x['execution_status'] in ('TIMEOUT','WORKER_FAILED')
        assert x['cost']['posthoc_M1_calls']==0 and (output/'execution_result.json').exists()

def test_current_spec_and_feedback_provenance(saved):
    req=request(saved);obs=fake_m2(bw=400000)(req,None)
    s=feedback_summary(req,obs,{'M1_calls':12},[]);f=search_feedback(req,s)
    assert f['observations'][0]['failed_constraints']==['BW_Hz']
    assert f['observations'][0]['measurements']['remaining_budgets']['M1_calls']==12
    assert s['m1_m2_deviation']['BW_Hz']['definitions_identical'] is False
    row=deepcopy(saved[2]['recommended_nominal']);assert applicable(row,saved[2])
    row['problem_sha256']='old';assert not applicable(row,saved[2])

class ReverifyPolicy(DeterministicToolPolicy):
    def decide(self,state,directory):
        return {'schema_version':'pll-physics-tool-decision-1.0','state_sha256':state['state_sha256'],
            'action':'REVERIFY','reason':'TEST unchanged protocol retry after unresolved numerical measurement',
            'evidence_ids':[state['external_feedback']['observations'][0]['evidence_id']]}

def test_unknown_reverify_requires_real_cited_feedback_and_budget(saved,tmp_path):
    cfg=config(saved)
    r=run_stage9_feedback(saved[0],tmp_path/'run',problem_config=saved[1],stage9_config=cfg,
        m2_executor=fake_m2(converged=False),policy=ReverifyPolicy())
    assert len(r['verified_history'])==2,r['failure']
    assert len({h['candidate_sha256'] for h in r['verified_history']})==1
    assert r['cost']['M2_verifications']==2 and not r['real_fail_reverification_completed']
    assert r['M2_status']=='UNKNOWN' and r['feedback_loop_status']=='SAME_CANDIDATE_REVERIFIED'

def test_known_physical_fail_cannot_reverify_without_changed_measurement(saved,tmp_path):
    r=run_stage9_feedback(saved[0],tmp_path/'run',problem_config=saved[1],stage9_config=config(saved),
        m2_executor=fake_m2(bw=400000),policy=ReverifyPolicy())
    assert len(r['verified_history'])==1 and r['termination_reason']=='INVALID_LLM_DECISION'
    assert r['best_known_M1'] and r['M2_status']=='FAIL'

def test_partial_capture_survives_timeout(saved,tmp_path):
    req=request(saved);out=tmp_path/'partial'
    def timedout(*args,**kwargs):
        (out/'capture').mkdir(parents=True)
        capture={'numerical_converged':True,'reliable_capture_status':'CAPTURED_WITHIN_WINDOW',
            'fine':{'lock_time_s':20e-6},'step_comparison':{'lock_time_difference_s':0}}
        (out/'capture/comparison.json').write_text(json.dumps(capture),encoding='utf-8')
        raise subprocess.TimeoutExpired('TEST',.01)
    with patch('pll_allocation.verification.continuous.subprocess.run',side_effect=timedout):
        x=execute_request(req,out)
    checks={c['metric']:c['status'] for c in x['constraints']}
    assert checks['lock_time_s']=='PASS' and checks['BW_Hz']=='UNKNOWN' and x['execution_status']=='TIMEOUT'

@pytest.mark.parametrize('limit', (6,12,25))
def test_varied_m1_budget_preserves_candidate_and_hard_limit(saved,tmp_path,limit):
    r=run_stage9_feedback(saved[0],tmp_path/'run',problem_config=saved[1],stage9_config=config(saved,m1_budget=limit),
        m2_executor=fake_m2(bw=400000),policy=DeterministicToolPolicy())
    assert r['cost']['M1_calls']<=limit and r['best_known_M1']
    assert r['M2_status']=='FAIL' and not r['FULL_SYSTEMSPEC_CERTIFIED']

def test_wrong_current_problem_rejected_before_output(saved,tmp_path):
    with pytest.raises(ValueError):
        run_stage9_feedback(saved[0],tmp_path/'must_not_exist',problem_config=ROOT/'configs/problems/tight.json',
            stage9_config=config(saved),m2_executor=fake_m2())
    assert not (tmp_path/'must_not_exist').exists()

def test_finalization_failure_retains_paid_call_costs_and_initial_archive(saved,tmp_path):
    def broken(problem,path,**kwargs):
        folder=Path(path)/'executor';folder.mkdir(parents=True)
        (folder/'m1_samples.jsonl').write_text(json.dumps({'formal_M1_called':True})+'\n',encoding='utf-8')
        raise RuntimeError('TEST after real-call artifact was persisted')
    with patch('pll_allocation.agent.feedback.run_initial_allocation',side_effect=broken):
        r=run_stage9_feedback(saved[0],tmp_path/'run',problem_config=saved[1],stage9_config=config(saved),
            m2_executor=fake_m2(bw=400000))
    assert r['status']=='CONTROLLER_ERROR' and r['cost']['M1_calls']==1
    assert r['cost']['recorded_formal_M1_calls']==1 and r['best_known_M1']
    assert r['M2_status']=='FAIL' and r['failure']['reason'].startswith('TEST')

def test_rejected_proposals_are_not_marked_accepted(saved,tmp_path):
    class InvalidThenStop(DeterministicToolPolicy):
        def __init__(self):self.n=0
        def decide(self,state,directory):
            self.n+=1
            common={'schema_version':'pll-physics-tool-decision-1.0','state_sha256':state['state_sha256'],
                'action':'STOP','stop_basis':'SPEC_SATISFIED','reason':'TEST stop, M1 only',
                'evidence_ids':[state['best_known']['evidence_id']]}
            if self.n==1:common['evidence_ids']=['TEST_NONEXISTENT']
            return common
    r=run_stage9_feedback(saved[0],tmp_path/'run',problem_config=saved[1],stage9_config=config(saved),
        m2_executor=fake_m2(bw=400000),policy=InvalidThenStop())
    rows=[json.loads(s) for s in (tmp_path/'run/agent_decisions.jsonl').read_text(encoding='utf-8').splitlines()]
    assert rows[0]['validation_status']=='REJECTED' and rows[0]['accepted_decision'] is None
    assert rows[1]['validation_status']=='ACCEPTED' and rows[1]['accepted_decision']
    assert r['M2_status']=='FAIL' and r['best_known_M1']
