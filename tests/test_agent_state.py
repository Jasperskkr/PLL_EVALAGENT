"""Historical replay plus generated invariants; TEST policies are never real LLM."""
from copy import deepcopy
import json
import random
from pathlib import Path
from types import SimpleNamespace

import pytest

from pll_allocation.agent.candidates import CandidateArchive, material_change, rank
from pll_allocation.agent.decision_adapter import adapt_decision, DecisionValidationError
from pll_allocation.agent.planner_state import build_state, sensitivity, sensitivity_conflicts
from pll_allocation.agent.region_policy import ProviderError
from pll_allocation.agent.search_loop import AgentSearchLoop, validate_config
from pll_allocation.agent.run_state import run_state
from pll_allocation.agent.calibration import raw_problem
from pll_allocation.exploration import run_exploration, load_physics_context
from pll_allocation.exploration.contracts import judge, make_parameters, resolve_problem
from pll_allocation.physics_mapping.model import evaluate, fingerprint
from pll_allocation.region_explorer import RegionExplorer
from pll_allocation.region_explorer.explorer import slsqp_cost_model
from pll_allocation.region_explorer.contracts import validate_decision

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def histories():
    path = ROOT/'docs/stage8b_stabilization/historical_regression_inputs.json'
    if not path.is_file():
        pytest.skip('Optional historical replay archive is not included in the source release')
    return json.loads(path.read_text(encoding='utf-8'))


@pytest.fixture(scope='module')
def context(tmp_path_factory):
    folder = tmp_path_factory.mktemp('stabilization_calibration')
    raw = json.loads((ROOT/'configs/problems/nominal.json').read_text())
    raw['exploration'].update(sobol_samples=8, physics_seed_count=8, max_m1_evaluations=48,
                              sensitivity_representatives=1)
    path=folder/'problem.json'; path.write_text(json.dumps(raw))
    run_exploration(path, folder/'context')
    return folder/'context/physics_context.json'


def cfg(**changes):
    c=json.loads((ROOT/'configs/agent/region_search.json').read_text())
    c.update(schema_version='pll-llm-region-loop-1.1', total_m1_budget=40, max_round_m1=20,
             calibration_budget=8, seed_probe_budget=4, seed_probe_samples=4,
             quality_target=100., min_decisions_before_quality_stop=1,
             mode='INITIAL_ALLOCATION')
    c.update(changes)
    return c


def proposal(s, *, n=2):
    point=s['best_known'] or next(r for r in s['calibration']['displayed_samples'] if r['seed_eligible'])
    radius=.04 if not s['history'] else .03
    return {'action':'OPTIMIZE','region_origin':'LLM_PROPOSED',
        'normalized_bounds':{k:[max(0.,u-radius),min(1.,u+radius)] for k,u in point['normalized'].items()},
        'active_variables':list(point['normalized'])[:n], 'seed_ids':[point['evidence_id']],
        'm1_budget':min(16,s['budget']['max_this_decision_M1_calls']),
        'reason':'TEST policy; no real LLM','evidence_ids':[point['evidence_id']]}


class Policy:
    def __init__(self, fail_at=None, stop_at=None):
        self.states=[];self.fail_at=fail_at;self.stop_at=stop_at;self.calls=[]
    def decide(self,s,directory):
        self.states.append(deepcopy(s))
        if self.fail_at==len(self.states):raise ProviderError('TEST injected provider fault')
        if self.stop_at==len(self.states):
            return {'action':'STOP','stop_basis':'SPEC_SATISFIED','reason':'TEST best known adequate',
                    'evidence_ids':[s['best_known']['evidence_id']]}
        return proposal(s)


def make_loop(context,tmp_path,policy=None,**changes):
    return AgentSearchLoop(context,tmp_path/'run',config=cfg(**changes),provider_config={},policy=policy or Policy())


def read_allocation(x):
    return json.loads((x.root/'m1_allocation.json').read_text())


@pytest.mark.parametrize('fail_at',[1,2,3])
def test_provider_failure_never_loses_best_and_rechecks(context,tmp_path,fail_at):
    x=make_loop(context,tmp_path,Policy(fail_at=fail_at))
    r=x.run(); a=read_allocation(x)
    assert r['termination_reason']=='LLM_PROVIDER_FAILED'
    assert r['m1_allocation_status']=='KNOWN_M1_FEASIBLE_RECHECKED'
    assert a['recommended_nominal']['judgment']['minimum_normalized_margin'] >= a['best_calibration_candidate']['judgment']['minimum_normalized_margin']
    assert a['recommendation_recheck']['row']['formal_M1_called']
    assert a['recommendation_recheck']['row']['origin']=='RECOMMENDATION:FINAL_RECHECK'
    assert r['cost']['M1_calls']<=40 and r['cost']['LLM_calls']==0
    assert len((x.root/'candidate_archive.jsonl').read_text().splitlines())==len(x.archive.entries)


def test_historical_low_bw_chooses_better_calibration(histories,tmp_path):
    h=histories['low_bw_baseline']; c=h['context']; old=h['allocation']['calibration_baseline']; worse=h['allocation']['new_allocation']
    x=SimpleNamespace(problem=c['problem'],context=c,calibration_samples=h['calibration_samples'],rows=[])
    archive=CandidateArchive(x,tmp_path/'archive.jsonl')
    assert archive.best()['judgment']['minimum_normalized_margin'] > worse['judgment']['minimum_normalized_margin']
    assert archive.best()['parameter_sha256']==old['parameter_sha256']
    x.rows.append({**deepcopy(next(r for r in h['calibration_samples'] if r['evidence_id']==old['evidence_id'])),
                   'evidence_id':'TEST_REPEAT', 'origin':'SLSQP:TEST:TRIAL'})
    archive.sync()
    assert archive.best()['parameter_sha256']==old['parameter_sha256']


def test_historical_global_negligible_second_round_is_stall(histories):
    h=histories['global_stagnation']; rounds=h['rounds']
    a=rounds[0]['observation']['observations'][0]['latest_minimum_normalized_margin']
    b=rounds[1]['observation']['observations'][0]['latest_minimum_normalized_margin']
    assert b>a and not material_change(a,b)['material']


def test_historical_tight_conflicts_bound_to_working_points(histories):
    derivatives=sensitivity(histories['tight_conflict']['context'])
    conflicts=sensitivity_conflicts(derivatives)
    item=next(r for r in conflicts if r['metric']=='PM_deg' and r['variable']=='Icp')
    assert {r['center_evidence_id'] for r in item['working_points']}=={'S000004','S000015'}
    assert any(r['derivative']<0 for r in item['working_points']) and any(r['derivative']>0 for r in item['working_points'])


def test_historical_tight_exhaustion_keeps_solver_and_feasibility_independent(histories,tmp_path):
    h=histories['tight_call_exhaustion'];c=h['context']
    x=SimpleNamespace(problem=c['problem'],context=c,calibration_samples=h['calibration_samples'],rows=[])
    archive=CandidateArchive(x,tmp_path/'archive.jsonl')
    history=[r['observation'] for r in h['rounds'] if r['observation']]
    assert h['result']['status']=='INVALID_LLM_DECISION'
    assert h['result']['cost']['LLM_calls']==3 and len(history)==2
    result=run_state('LLM_CALL_BUDGET_EXHAUSTED',history,archive,{'passed':False})
    assert result['termination_reason']=='LLM_CALL_BUDGET_EXHAUSTED'
    assert result['solver_execution_status']['counts']=={'BUDGET_EXHAUSTED':1,'CONVERGED':1}
    assert result['feedback_reoptimization_count']==1
    assert result['m1_allocation_status']=='KNOWN_M1_FEASIBLE_RECHECK_FAILED_OR_UNAVAILABLE'
    assert archive.best(feasible_only=True) is not None


def test_historical_global_bad_box_structured_error_no_execution(histories):
    h=histories['global_out_of_bounds']; c=h['context']; rows={r['evidence_id']:r for r in h['calibration_samples']}
    state=h['rounds'][1]['states'][0]; raw=h['rounds'][1]['proposals'][0]
    rows.update({r['evidence_id']:r for r in state['physics_knowledge']+state['sensitivity']})
    x=SimpleNamespace(context=c,problem=c['problem'],evidence=rows)
    x.validate=lambda d:validate_decision(d,context=c,evidence=rows,regions={},remaining_budget=120)
    with pytest.raises(DecisionValidationError) as error:
        adapt_decision(raw,x,state,validate_config(cfg()),round_number=2,first=False)
    assert error.value.details['code']=='SEED_OUTSIDE_REGION'
    violation=error.value.details['seed_boundary_violations'][0]
    assert violation['seed_id']=='S000235' and 'Icp' in violation['violations']


def test_call_budget_orthogonal_and_feedback_stop_differs(context,tmp_path):
    x=make_loop(context,tmp_path/'exhaust',max_decisions=3,max_llm_calls=3)
    # One repair spends a request but does not advance the numerical round.
    p=Policy(); original=p.decide
    def once_bad(s,directory):
        raw=original(s,directory)
        if len(p.states)==1:raw['evidence_ids']=['INVALID_TEST']
        return raw
    p.decide=once_bad;x.policy=p
    r=x.run()
    assert r['termination_reason']=='LLM_CALL_BUDGET_EXHAUSTED'
    assert r['feedback_loop_status']=='FEEDBACK_REOPTIMIZED'
    assert r['feedback_reoptimization_count']==1
    y=make_loop(context,tmp_path/'stop',Policy(stop_at=2));q=y.run()
    assert q['feedback_loop_status']=='FEEDBACK_READ_AND_STOPPED'
    assert not q['feedback_reoptimization_completed']


def test_budget_exhausted_while_waiting_for_decision_repair(context,tmp_path):
    class Invalid(Policy):
        def decide(self,s,directory):
            d=super().decide(s,directory);d['evidence_ids']=['TEST_INVALID'];return d
    x=make_loop(context,tmp_path,Invalid(),max_decisions=1,max_llm_calls=2,validation_retries=2)
    r=x.run()
    assert r['termination_reason']=='LLM_CALL_BUDGET_EXHAUSTED'
    assert r['cost']['test_policy_calls']==2 and not x.history
    assert r['m1_allocation_status']=='KNOWN_M1_FEASIBLE_RECHECKED'
    assert len(list((x.root/'round_01').glob('validation_error_*.json')))==2


def test_probe_without_solver_is_not_feedback_reoptimization():
    archive=SimpleNamespace(best=lambda **kwargs:None)
    record={'decision':{'action':'OPTIMIZE'},'observations':[
        {'solver_runs':[{'solver':'SOBOL','status':'COMPLETED'}]}]}
    state=run_state('TEST_NO_SEED',[deepcopy(record),record],archive,{'passed':False})
    assert state['feedback_loop_status']=='FEEDBACK_ACTION_ACCEPTED_NO_OPTIMIZATION_EXECUTED'
    assert state['feedback_reoptimization_count']==state['optimization_execution_count']==0
    assert state['feedback_optimization_proposal_count']==1


def test_rebound_sensitivity_keeps_explicit_center_without_candidate_region(context,tmp_path):
    x=make_loop(context,tmp_path)
    # Current Spec can remove all former region representatives; the measured
    # center evidence still binds each local derivative to its actual point.
    c=deepcopy(x.explorer.context);c['candidate_regions']=[]
    rows=sensitivity(c,x.explorer.evidence)
    assert rows and all(r['center_values_SI'] is not None for r in rows)
    for row in rows:
        point=x.explorer.evidence[row['center_evidence_id']]['parameters']
        assert row['center_values_SI']=={k:v['value'] for k,v in point['values'].items() if k in c['problem']['parameters']}
    x.status='TEST_FINISHED';x.finish()


@pytest.mark.parametrize('dimensions',[1,2,3,4,5,6])
@pytest.mark.parametrize('budget',[3,8,17])
def test_active_dimension_budget_and_final_reserve(context,tmp_path,dimensions,budget):
    x=make_loop(context,tmp_path)
    s=build_state(x.explorer,x.config,[],round_number=1,calls_remaining=3,calibration=x.calibration)
    raw=proposal(s,n=dimensions);raw['m1_budget']=budget
    d=adapt_decision(raw,x.explorer,s,x.config,round_number=1,first=True)
    obs=x.explorer.execute(d)
    assert obs['cost']['M1_calls']<=budget
    assert obs['final_recheck_status']=='OK'
    if budget < slsqp_cost_model(dimensions)['minimum_action_budget']:
        assert all(r['status']=='SKIPPED_BUDGET' for r in obs['solver_runs'])
        assert obs['cost']['M1_calls']==1  # Audit of known best, no numerical start.
    x.status='TEST_FINISHED';r=x.finish()
    a=read_allocation(x)
    assert a['recommendation_recheck']['passed'] and r['cost']['M1_calls']<=40


def test_scheduling_skips_extra_seeds_without_changing_box(context,tmp_path):
    x=make_loop(context,tmp_path)
    s=build_state(x.explorer,x.config,[],round_number=1,calls_remaining=3,calibration=x.calibration)
    raw=proposal(s,n=6);raw.update(normalized_bounds={k:[0.,1.] for k in raw['normalized_bounds']},m1_budget=8)
    raw['seed_ids']=[p['evidence_id'] for p in s['calibration']['displayed_samples'] if p['seed_eligible']][:3]
    d=adapt_decision(raw,x.explorer,s,x.config,round_number=1,first=True)
    o=x.explorer.execute(d)
    assert o['normalized_bounds']==raw['normalized_bounds']
    assert sum(r['status']=='SKIPPED_BUDGET' for r in o['solver_runs'])==len(d['seed_ids'])
    assert all(r['M1_calls']==0 for r in o['solver_runs'] if r['status']=='SKIPPED_BUDGET')
    x.status='TEST_FINISHED';x.finish()


@pytest.mark.parametrize('seed',range(8))
def test_generated_specs_domains_ranking_and_persistence(context,tmp_path,seed):
    rng=random.Random(seed); c=load_physics_context(context)
    row=next(r for r in map(json.loads,(context.parent/'m1_samples.jsonl').read_text().splitlines())
             if r.get('formal_M1_result') and r['judgment']['m1_feasibility']=='FEASIBLE')
    raw=raw_problem(c['problem']);raw['problem_id']='GENERATED_TEST_'+str(seed)
    for k,axis in raw['parameters'].items():
        value=row['parameters']['values'][k]['value']
        axis.update(min=value/rng.uniform(1.05,1.5),max=value*rng.uniform(1.05,1.5),default=value)
    bw=row['metrics']['BW_Hz'];pm=row['metrics']['PM_deg']
    raw['specs'][0].update(min=bw*rng.uniform(.6,.9),max=bw*rng.uniform(1.1,1.5))
    raw['specs'][1]['min']=pm*rng.uniform(.5,.9)
    p=resolve_problem(raw)
    transformed=deepcopy(row);transformed['parameters']=make_parameters(p,{k:v['value'] for k,v in row['parameters']['values'].items()})
    transformed['parameter_sha256']=fingerprint(transformed['parameters'])
    # Only domain/spec changed, fixed numerical input and original formal result stay identical.
    assert transformed['parameter_sha256']==row['parameter_sha256']
    transformed['problem_sha256']=p['problem_sha256']
    x=SimpleNamespace(problem=p,context=c,calibration_samples=[transformed],rows=[])
    archive=CandidateArchive(x,tmp_path/'archive.jsonl')
    assert archive.best()['judgment']['m1_feasibility']=='FEASIBLE'
    expected=archive.best()['parameter_sha256']
    for i in range(10):
        wrong=deepcopy(transformed);wrong['evidence_id']='TEST_BAD_'+str(i)
        wrong['problem_sha256']='wrong';x.rows.append(wrong)
        archive.sync()
        assert archive.best()['parameter_sha256']==expected
    assert len(archive.entries)==1 and len(archive.rejected)==10


@pytest.mark.parametrize('base',[0.,.1,10.,1e4])
def test_material_improvement_property_thresholds(base):
    rng=random.Random(18)
    for _ in range(40):
        step=rng.uniform(-1,1)*1e-8
        assert not material_change(base,base+step)['material']
    assert material_change(base,base+max(1e-3,abs(base)*1e-3))['material']


@pytest.mark.parametrize('test_seed',range(8))
def test_generated_axis_seed_regions_reject_all_outliers(context,tmp_path,test_seed):
    x=make_loop(context,tmp_path)
    s=build_state(x.explorer,x.config,[],round_number=1,calls_remaining=3,calibration=x.calibration)
    rng=random.Random(test_seed); raw=proposal(s,n=rng.randrange(1,7))
    axis=rng.choice(list(raw['normalized_bounds']))
    u=x.explorer.evidence[raw['seed_ids'][0]]['parameters']['values'][axis]['value']
    point=next(r for r in s['calibration']['displayed_samples'] if r['evidence_id']==raw['seed_ids'][0])['normalized'][axis]
    raw['normalized_bounds'][axis]=[.8,.9] if point<.8 else [.05,.15]
    with pytest.raises(DecisionValidationError) as err:
        adapt_decision(raw,x.explorer,s,x.config,round_number=1,first=True)
    assert axis in err.value.details['seed_boundary_violations'][0]['violations']
    assert x.explorer.cost()['M1_calls']==0
    x.status='TEST_REJECTED';x.finish()


@pytest.mark.parametrize('mode',['INITIAL_ALLOCATION','FEEDBACK_REOPTIMIZATION_ACCEPTANCE'])
def test_mode_and_quality_stop_requirements(context,tmp_path,mode):
    c=cfg();c.update(mode=mode,quality_target=-1.,min_decisions_before_quality_stop=1)
    x=AgentSearchLoop(context,tmp_path/'run',config=c,provider_config={},policy=Policy())
    r=x.run()
    assert r['decision_rounds']==(1 if mode=='INITIAL_ALLOCATION' else 2)
    assert r['termination_reason']=='M1_QUALITY_TARGET_REACHED'
    assert r['feedback_reoptimization_completed']==(mode!='INITIAL_ALLOCATION')


def test_origin_accounting_separates_local_stencils(context,tmp_path):
    x=make_loop(context,tmp_path)
    s=build_state(x.explorer,x.config,[],round_number=1,calls_remaining=3,calibration=x.calibration)
    counts=s['calibration']['origins_separately_counted']
    assert counts['SOBOL_GLOBAL']==8 and counts['SENSITIVITY_PROBE']>0 and counts['PHYSICS_SEED']>0
    assert sum(counts.values())==s['calibration']['unique_calibration_points']
    assert s['best_known']['normalized'] and s['current_tightest_constraint']
    x.status='TEST_FINISHED';x.finish()


def test_unfounded_stop_basis_is_rejected(context,tmp_path):
    x=make_loop(context,tmp_path)
    s=build_state(x.explorer,x.config,[],round_number=2,calls_remaining=3,calibration=x.calibration)
    for basis,match in [('BUDGET','actual limited'),('STALLED','measured stalled')]:
        raw={'action':'STOP','stop_basis':basis,'reason':'TEST unsupported claim','evidence_ids':[s['best_known']['evidence_id']]}
        with pytest.raises(ValueError,match=match):
            adapt_decision(raw,x.explorer,s,x.config,round_number=2,first=False)
    x.status='TEST_FINISHED';x.finish()


def test_no_known_feasible_is_not_infeasibility_proof(context,tmp_path):
    raw=raw_problem(load_physics_context(context)['problem'])
    # A lawful yet extremely weak gain domain: necessary screen is not a nonexistence proof.
    raw['parameters']['Icp'].update(min=5e-301,max=2e-300,default=1e-300)
    raw['exploration'].update(sobol_samples=0,physics_seed_count=1,sensitivity_representatives=0)
    file=tmp_path/'unresolved.json';file.write_text(json.dumps(raw))
    x=AgentSearchLoop(context,tmp_path/'run',config=cfg(),provider_config={},problem_path=file,policy=Policy(fail_at=1))
    r=x.run();a=read_allocation(x)
    assert r['m1_allocation_status']=='NO_KNOWN_M1_FEASIBLE_CANDIDATE'
    assert a['recommended_nominal'] is None and r['termination_reason']=='LLM_PROVIDER_FAILED'
    assert a['recommendation_recheck']['status']=='NO_KNOWN_FEASIBLE_CANDIDATE'


def test_final_recheck_exception_preserves_recommendation(context,tmp_path,monkeypatch):
    x=make_loop(context,tmp_path,Policy(fail_at=1))
    def broken(*args):raise ArithmeticError('TEST evaluator failure on final audit')
    monkeypatch.setattr('pll_allocation.region_explorer.explorer.evaluate',broken)
    r=x.run();a=read_allocation(x)
    assert r['termination_reason']=='LLM_PROVIDER_FAILED'
    assert r['m1_allocation_status']=='KNOWN_M1_FEASIBLE_RECHECK_FAILED_OR_UNAVAILABLE'
    assert a['recommended_nominal'] and not a['recommendation_recheck']['passed']
    assert r['cost']['M1_calls']==1 and r['cost']['executor']['M1_failures']==1


def test_accepted_decision_reproducible_trace(context,tmp_path):
    digests=[]
    for name in ['a','b']:
        x=make_loop(context,tmp_path/name,Policy(stop_at=2));r=x.run()
        a=read_allocation(x)
        digests.append((a['recommended_nominal']['parameters'],a['recommendation_recheck']['row']['metrics'],
                        [{k:v for k,v in row.items() if k!='cost'} for row in x.explorer.rows]))
    assert digests[0]==digests[1]


def test_production_contains_no_case_specific_constants():
    forbidden=['S000004','S000015','S000235','global_repeat','tight_repeat','203611.977','294711.693']
    sources='\n'.join(p.read_text(encoding='utf-8') for d in ['agent','region_explorer']
                      for p in (ROOT/'pll_allocation'/d).glob('*.py'))
    assert not any(s in sources for s in forbidden)
