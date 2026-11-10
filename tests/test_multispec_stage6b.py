"""Stage6B boundary tests. Synthetic M2 fixtures are never study evidence."""
from copy import deepcopy
from pathlib import Path
import json
import math
import pytest
from pll_allocation import pipeline
from pll_allocation.pipeline_contracts import load_inputs
from pll_allocation.allocation.core import Meter,assess_m1,read,write_new,proposal,values
from pll_allocation.allocation.allocate import analytical
from pll_allocation.allocation.multispec_constraints import validate_problem,evaluate_constraints,objective_key
from pll_allocation.allocation.multispec_search import SearchController
from pll_allocation.block_space.contracts import make_candidate
from pll_allocation.physics_mapping.model import fingerprint

ROOT=Path(__file__).resolve().parents[1]


def problem(name='B1'):
    return read(ROOT/'experiments/stage6b/frozen_01'/(name+'.json'))


def initial(name='B1'):
    _,model,_,_=load_inputs();p=problem(name);meter=Meter(10000,96)
    candidate,_=analytical(model,p['research_system_spec'],meter)
    assessment=assess_m1(model,p['research_system_spec'],candidate,meter)
    return model,p,candidate,assessment


def synthetic_measurement(candidate,assessment):
    """Contract-bound synthetic test fixture, no numerical TB run."""
    bw=assessment['prediction']['metrics']['BW_Hz']
    return {'parameter_sha256':fingerprint(candidate),'overall_status':'UNKNOWN',
        'metrics':{'BW_Hz':{'value':bw,'status':'MEASURED_CONVERGED','numerical_envelope':[bw-10,bw+10]},
            'capture':{'value':'CAPTURED_WITHIN_WINDOW','initial_control_V':.15,'duration_s':160e-6},
            'lock_time_s':{'value':33e-6,'step_difference_s':0.,'resolution_s':1e-6,'status':'MEASURED_WINDOW_CONDITIONAL'}},
        'reliability':{'BW_converged':True,'capture_step_converged':True}}


@pytest.mark.parametrize('name',['B1','B2'])
def test_versioned_problem_and_mixed_evidence_success(name):
    cfg,model,frozen,proto=load_inputs();p=problem(name)
    assert validate_problem(p,cfg,model,frozen,proto)==p
    model,p,c,a=initial(name);m=synthetic_measurement(c,a);e=evaluate_constraints(model,p,c,a,m)
    assert e['research_joint_status']=='RESEARCH_JOINT_FEASIBLE'
    assert not e['FULL_SYSTEMSPEC_CERTIFIED'] and e['strict_periodic_PM_status']=='UNKNOWN'
    assert {r['measurement_source'] for r in e['constraints']}=={'M1','M2'}


@pytest.mark.parametrize('mutation',[
    lambda p:p['constraints'][0].update(measurement_source='M1'),
    lambda p:p['constraints'][3].update(upper_bound=50e-6),
    lambda p:p['research_system_spec']['metrics'][0].update(min=81e6,max=81e6),
    lambda p:p['budgets'].update(M2_candidate_slots=7),
    lambda p:p['constraints'][0].update(normalization_scale=0),
    lambda p:p['constraints'][2].update(strict=False),
    lambda p:p['search'].update(poll_order=['region_switch'])])
def test_unsafe_or_unfrozen_contract_rejected(mutation):
    cfg,model,spec,proto=load_inputs();p=problem();mutation(p)
    p['problem_sha256']=fingerprint({k:v for k,v in p.items() if k!='problem_sha256'})
    with pytest.raises(ValueError):validate_problem(p,cfg,model,spec,proto)


def test_stage5_bw_pass_pm_fail_never_joint_success():
    cfg,model,_,_=load_inputs();p=problem()
    folder=ROOT/'experiments/stage5/repair_01/runs/S3__random__11/attempt_001'
    c=read(folder/'AllocationProposal.json')['joint_block_spec'];m=read(folder/'BehavioralVerificationResult.json')
    a=assess_m1(model,p['research_system_spec'],c,Meter())
    e=evaluate_constraints(model,p,c,a,m);rows={r['metric_name']:r for r in e['constraints']}
    assert rows['BW_Hz']['verification_status']=='PASS'
    assert rows['PM_deg']['verification_status']=='FAIL'
    assert e['research_joint_status']=='FAIL'


@pytest.mark.parametrize('mutation,status',[
    (lambda m:m['metrics']['capture'].update(value='NOT_CAPTURED_WITHIN_WINDOW'),'FAIL'),
    (lambda m:m['metrics']['capture'].update(value='LOST_LOCK_WITHIN_WINDOW'),'FAIL'),
    (lambda m:m['reliability'].update(capture_step_converged=False),'UNKNOWN'),
    (lambda m:m['metrics']['lock_time_s'].update(value=40e-6),'UNKNOWN'),
    (lambda m:m['metrics']['lock_time_s'].update(value=43e-6),'FAIL'),
    (lambda m:m['metrics']['lock_time_s'].update(value=float('nan')),'UNKNOWN'),
    (lambda m:m['metrics']['lock_time_s'].update(step_difference_s=-1),'UNKNOWN'),
    (lambda m:m['metrics']['lock_time_s'].update(step_difference_s=3e-6),'UNKNOWN'),
    (lambda m:m['metrics']['BW_Hz'].update(numerical_envelope=[300e3,100e3]),'UNKNOWN'),
    (lambda m:m['metrics']['BW_Hz'].update(status='UNSUPPORTED'),'UNKNOWN')])
def test_failed_unknown_malformed_evidence_never_pass(mutation,status):
    model,p,c,a=initial();m=synthetic_measurement(c,a);mutation(m)
    assert evaluate_constraints(model,p,c,a,m)['research_joint_status']==status


def test_measurement_parameter_binding_and_unknown_order():
    model,p,c,a=initial();m=synthetic_measurement(c,a);m['parameter_sha256']='wrong'
    with pytest.raises(ValueError,match='binding'):evaluate_constraints(model,p,c,a,m)
    e=evaluate_constraints(model,p,c,{'prediction':None})
    assert all(math.isfinite(v) for v in objective_key(e,p['objective']))


def controller(name='B1',method='C'):
    _,model,_,_=load_inputs();p=problem(name);events=[]
    ctl=SearchController(model,p,method,Meter(10000,96),lambda event,**kw:events.append({'event':event,**kw}))
    return ctl,events


def test_local_polls_reconstruct_gain_and_tuning_recheck_all():
    ctl,events=controller();r=ctl.initialize();p=values(r['candidate'])
    for label,delta in [('Vreq',-.02),('Kvco',.02)]:
        c=ctl._coordinate_candidate(r,label,delta);s=values(c)
        assert s['Icp']*s['Kvco']==pytest.approx(p['Icp']*p['Kvco'])
        checked=ctl.checked(c,'TEST');assert checked is not None
        e=evaluate_constraints(ctl.model,ctl.problem,c,checked['assessment'])
        assert e['unresolved_constraints']==2 and e['M1_predicted_feasible']
    assert ctl._coordinate_candidate(r,'Vreq',100) is None
    assert any(e['event']=='COORDINATE_OUT_OF_DOMAIN' for e in events)


def test_pair_fixed_anchor_step_nonsmooth_trend_and_contraction():
    ctl,events=controller();r=ctl.initialize()
    e=evaluate_constraints(ctl.model,ctl.problem,r['candidate'],r['assessment'],synthetic_measurement(r['candidate'],r['assessment']))
    ctl.observe(r,e);minus=ctl.next();step=ctl.pair_step
    ctl.observe(minus,e);ctl.vstep*=.5;plus=ctl.next()
    assert ctl.pair_step==step
    v0=(80e6-values(r['candidate'])['f0'])/values(r['candidate'])['Kvco']
    vm=(80e6-values(minus['candidate'])['f0'])/values(minus['candidate'])['Kvco']
    vp=(80e6-values(plus['candidate'])['f0'])/values(plus['candidate'])['Kvco']
    assert vm+vp==pytest.approx(2*v0)
    ctl.observe(plus,e)
    assert any(x['event']=='TRUST_RADIUS_CONTRACTED' for x in events)
    assert any(x.get('classification')=='RESOLUTION_OVERLAP_NO_EXACT_GRADIENT' for x in events)


def test_bw_fail_activates_sensitivity_screen_and_degeneracy():
    ctl,events=controller('B2');r=ctl.initialize();m=synthetic_measurement(r['candidate'],r['assessment'])
    m['metrics']['BW_Hz'].update(value=302000,numerical_envelope=[301900,302100])
    e=evaluate_constraints(ctl.model,ctl.problem,r['candidate'],r['assessment'],m);ctl.observe(r,e)
    trial=ctl.next()
    assert trial and 'M2_BW_RESIDUAL' in trial['reason']
    assert any(x['event']=='FEEDBACK_PATTERN_SCREEN' for x in events)
    ctl.sens['columns']['Icp']['status']='DOMAIN_LIMITED';ctl.sens['columns']['Rz']['status']='DOMAIN_LIMITED'
    assert ctl._bw_feedback_poll() is None
    assert any(x['event']=='SENSITIVITY_DEGENERATE' for x in events)


def test_discrete_region_switch_and_unresolved_stop():
    ctl,events=controller();r=ctl.initialize()
    e=evaluate_constraints(ctl.model,ctl.problem,r['candidate'],r['assessment'],synthetic_measurement(r['candidate'],r['assessment']))
    ctl.observe(r,e);ctl.poll_number=4;trial=ctl.next()
    old,new=values(r['candidate']),values(trial['candidate'])
    assert (old['C1'],old['C2'])!=(new['C1'],new['C2'])
    assert trial['assessment']['judgment']['verdict']=='M1_SPEC_PASS'
    ctl.observe(trial,evaluate_constraints(ctl.model,ctl.problem,trial['candidate'],trial['assessment']))
    assert ctl.next() is None and ctl.stop_reason=='UNRESOLVED_MEASUREMENT_DIAGNOSIS_REQUIRED'


def synthetic_child(monkeypatch):
    calls=[]
    def run(out,strategy,**kwargs):
        root=Path(out);folder=root/'attempt_001';folder.mkdir(parents=True)
        _,model,spec,proto=load_inputs();c,_=kwargs['policy'].propose(model,spec,None,None,[])
        assert (root.parent/'proposal.json').is_file()
        a=assess_m1(model,spec,c,Meter());item=proposal(model,spec,c,'analytical',a,{},'SYNTHETIC_TEST')
        m=synthetic_measurement(c,a);write_new(folder/'AllocationProposal.json',item)
        write_new(folder/'BehavioralVerificationResult.json',m);calls.append(c)
        return {'status':'M2_PARTIAL_PASS','failure':None,'cost':{'M1_calls':1,'M1_posthoc_calls':1,'M2_calls':1,
            'native_completed_runs':0,'native_failed_attempts':0,'integration_points':0,'native_elapsed_s':0,'native_failure_elapsed_s':0}}
    monkeypatch.setattr(pipeline,'run_pipeline',run)
    monkeypatch.setattr(pipeline,'check_result',lambda *a:None)
    return calls


def assert_chain(path):
    previous='0'*64
    for line in path.read_text(encoding='utf-8').splitlines():
        event=json.loads(line);digest=event.pop('event_sha256')
        assert event['previous_sha256']==previous and fingerprint(event)==digest
        previous=digest
    return previous


def test_runner_cache_budget_trace_and_tampering(tmp_path,monkeypatch):
    calls=synthetic_child(monkeypatch);cache=tmp_path/'cache';path=ROOT/'experiments/stage6b/frozen_01/B1.json'
    a=pipeline.run_multispec(tmp_path/'a',path,'A',cache_path=cache)
    b=pipeline.run_multispec(tmp_path/'b',path,'A',cache_path=cache)
    assert len(calls)==1 and a['cost']['M2_calls']==1 and b['cost']['M2_calls']==0
    assert b['cost']['cache_hits']==1 and b['cost']['M2_candidate_slots_used']==1
    assert assert_chain(tmp_path/'a/allocation_trace.jsonl')==a['trace_final_sha256']
    (tmp_path/'a/candidate_001/full_pipeline/attempt_001/BehavioralVerificationResult.json').write_text('{}',encoding='utf-8')
    bad=pipeline.run_multispec(tmp_path/'bad',path,'A',cache_path=cache)
    assert bad['status']=='PIPELINE_ERROR' and bad['cost']['M2_calls']==0
    with pytest.raises(FileExistsError):pipeline.run_multispec(tmp_path/'a',path,'A')


def test_small_budgets_stop_and_feasibility_precedes_secondary(tmp_path,monkeypatch):
    synthetic_child(monkeypatch);p=problem();p['budgets'].update(M2_candidate_slots=1)
    p['problem_sha256']=fingerprint({k:v for k,v in p.items() if k!='problem_sha256'});path=tmp_path/'p.json';write_new(path,p)
    result=pipeline.run_multispec(tmp_path/'run',path,'C')
    assert result['cost']['M2_candidate_slots_used']==1 and result['stop_reason']=='M2_CANDIDATE_SLOT_BUDGET_EXHAUSTED'
    p['budgets']['M1_calls']=1;p['problem_sha256']=fingerprint({k:v for k,v in p.items() if k!='problem_sha256'})
    path2=tmp_path/'p2.json';write_new(path2,p)
    stopped=pipeline.run_multispec(tmp_path/'budget',path2,'C')
    assert stopped['cost']['M2_calls']==0 and stopped['stop_reason']=='BUDGET_EXHAUSTED'
    model,p,c,a=initial();m=synthetic_measurement(c,a);good=evaluate_constraints(model,p,c,a,m)
    m['metrics']['BW_Hz'].update(value=301000,numerical_envelope=[300900,301100]);m['metrics']['lock_time_s']['value']=1e-6
    bad=evaluate_constraints(model,p,c,a,m)
    assert objective_key(good,p['objective'])<objective_key(bad,p['objective'])


def test_stage6a_historical_boundary_and_feasible_compatibility():
    _,model,_,_=load_inputs()
    for name,scenario,expected in [('E0_analytical','B1','RESEARCH_JOINT_FEASIBLE'),
                                    ('E1_upper_shape','B2','FAIL')]:
        folder=ROOT/'experiments/stage6a/m2_01/runs'/name/'attempt_001'
        item=read(folder/'AllocationProposal.json');m=read(folder/'BehavioralVerificationResult.json');p=problem(scenario)
        a=assess_m1(model,p['research_system_spec'],item['joint_block_spec'],Meter())
        assert evaluate_constraints(model,p,item['joint_block_spec'],a,m)['research_joint_status']==expected
