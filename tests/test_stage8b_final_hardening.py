"""Budget/stop/handoff invariants. All policies are explicitly TEST, not LLM."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from pll_allocation.agent.decision_adapter import adapt_decision
from pll_allocation.agent.handoff import validate_handoff
from pll_allocation.agent.planner_state import build_state
from pll_allocation.agent.run_state import quality_state
from pll_allocation.agent.search_loop import AgentSearchLoop
from pll_allocation.agent.region_policy import ProviderError
from pll_allocation.exploration import run_exploration,load_physics_context
from pll_allocation.agent.calibration import raw_problem
from pll_allocation.physics_mapping.model import fingerprint,MappingResult,Status
from pll_allocation.region_explorer.explorer import slsqp_cost_model
from pll_allocation.region_explorer import RegionExplorer
from pll_allocation.agent.candidates import CandidateArchive
from pll_allocation.agent.planner_state import knowledge,sensitivity

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def context(tmp_path_factory):
    root=tmp_path_factory.mktemp('hardening_context')
    raw=json.loads((ROOT/'configs/stage7/continuous_tight_v2.json').read_text(encoding='utf-8'))
    raw['exploration'].update(sobol_samples=8,physics_seed_count=8,max_m1_evaluations=64,sensitivity_representatives=1)
    file=root/'problem.json';file.write_text(json.dumps(raw),encoding='utf-8')
    run_exploration(file,root/'stage7')
    return root/'stage7/physics_context.json'


def config(**changes):
    c=json.loads((ROOT/'configs/stage8b/pilot.json').read_text(encoding='utf-8'))
    c.update(total_m1_budget=64,max_round_m1=30,calibration_budget=16,max_decisions=2,max_llm_calls=3,
             quality_target=100.,min_decisions_before_quality_stop=2,seed_probe_budget=4,seed_probe_samples=4)
    c.update(changes);return c


class Policy:
    def __init__(self,basis='SPEC_SATISFIED',budget=25,dimensions=4,fail=False):
        self.basis=basis;self.budget=budget;self.dimensions=dimensions;self.fail=fail;self.calls=[]
    def decide(self,s,directory):
        if self.fail:raise ProviderError('TEST provider failure')
        if s['history']:
            d={'action':'STOP','reason':'TEST saved evidence stop','evidence_ids':[s['best_known']['evidence_id']]}
            if self.basis:d['stop_basis']=self.basis
            return d
        return {'action':'OPTIMIZE','region_origin':'LLM_PROPOSED',
            'normalized_bounds':{k:[0.,1.] for k in s['problem']['parameters']},
            'active_variables':list(s['problem']['parameters'])[:self.dimensions],
            'seed_ids':[r['evidence_id'] for r in s['calibration']['displayed_samples'] if r['seed_eligible']][:4],
            'm1_budget':min(self.budget,s['budget']['max_this_decision_M1_calls']),
            'reason':'TEST only, real numerical execution','evidence_ids':[s['best_known']['evidence_id']]}


def loop(context,tmp_path,policy=None,**changes):
    return AgentSearchLoop(context,tmp_path/'run',config=config(**changes),provider_config={},policy=policy or Policy())


def load(x,name):return json.loads((x.root/name).read_text(encoding='utf-8'))


@pytest.mark.parametrize('dimension',[1,2,4,6])
@pytest.mark.parametrize('seed_count',[1,2,4])
def test_iteration_aware_starts_and_hard_budget(context,tmp_path,dimension,seed_count):
    x=loop(context,tmp_path);s=build_state(x.explorer,x.config,[],round_number=1,calls_remaining=3,calibration=x.calibration)
    raw=Policy(dimensions=dimension).decide(s,None);raw['seed_ids']=raw['seed_ids'][:seed_count]
    d=adapt_decision(raw,x.explorer,s,x.config,round_number=1,first=True)
    obs=x.explorer.execute(d)
    assert obs['cost']['M1_calls']<=25
    runs=obs['solver_runs'];assert len(runs)==len(raw['seed_ids'])
    for r in runs:
        if r['status']=='SKIPPED_BUDGET':assert r['M1_calls']==r['iterations']==0 and not r['started']
        else:
            assert r['M1_calls']<=r['allocated_M1_budget']
            assert r['cost_model']['estimated_iteration_cost']>dimension+1
            assert r['iterations']>=0 and r['callback_iterations']==len(r['iteration_trace'])
    assert obs['normalized_bounds']==d['normalized_bounds']
    x.status='TEST_END';x.finish()
    assert load(x,'stage9_handoff.json')['ready_for_stage9']
    assert x.explorer.cost()['M1_calls']<=64


def test_insufficient_iteration_budget_is_execution_outcome_not_invalid_decision(context,tmp_path):
    x=loop(context,tmp_path,Policy(budget=7,dimensions=6))
    result=x.run()
    assert result['termination_reason']=='STOPPED_BY_LLM'
    assert result['solver_execution_status']['started']==0
    assert result['solver_execution_status']['skipped_budget']>0
    assert result['m1_allocation_status']=='KNOWN_M1_FEASIBLE_RECHECKED'
    assert not result['feedback_reoptimization_completed']


@pytest.mark.parametrize('budget',[3,4,8])
def test_seedless_tiny_budget_keeps_valid_optimizer_envelope(context,tmp_path,budget):
    class Seedless(Policy):
        def decide(self,s,directory):
            d=super().decide(s,directory)
            if d['action']=='OPTIMIZE':d['seed_ids']=[]
            return d
    x=loop(context,tmp_path,Seedless(budget=budget,dimensions=6))
    result=x.run()
    assert result['termination_reason'] not in ('PIPELINE_ERROR','INVALID_LLM_DECISION')
    assert result['cost']['M1_calls']<=64
    for record in x.history:
        assert sum(o['cost']['M1_calls'] for o in record['observations'])<=record['decision']['m1_budget']
    assert result['m1_allocation_status']=='KNOWN_M1_FEASIBLE_RECHECKED'


def test_fixed_historical_four_seeds_twentyfive_calls(tmp_path):
    saved=ROOT/'docs/stage8b_stabilization/evidence/unseen_real_01'
    d=json.loads((saved/'round_01/search_decision.json').read_text(encoding='utf-8'))['decision']
    x=RegionExplorer(saved/'calibration_current/physics_context.json',tmp_path/'executor',
        m1_budget=26,reserved_final_calls=1,budget_scheduling=True)
    archive=CandidateArchive(x,tmp_path/'archive.jsonl')
    for item in knowledge(x.context)+sensitivity(x.context,x.evidence):x.evidence[item['evidence_id']]=item
    obs=x.execute(d);archive.sync()
    runs=obs['solver_runs'];started=[r for r in runs if r['started']]
    assert len(d['seed_ids'])==4 and d['m1_budget']==25 and len(started)==1
    assert started[0]['callback_iterations']>=2
    assert sum(r['status']=='SKIPPED_BUDGET' for r in runs)==3
    assert obs['normalized_bounds']==d['normalized_bounds']
    check=x.recheck_recommendation(archive.best(feasible_only=True))
    assert check['passed'] and x.cost()['M1_calls']<=26
    x.close()


@pytest.mark.parametrize('basis',[None,'SPEC_SATISFIED'])
def test_spec_only_stop_and_legacy_stop_are_not_quality(context,tmp_path,basis):
    x=loop(context,tmp_path,Policy(basis=basis));r=x.run()
    assert r['termination_reason']=='STOPPED_BY_LLM' and r['llm_stop_basis']=='SPEC_SATISFIED'
    assert r['quality_target_status']['status']=='NOT_REACHED'
    handoff=load(x,'stage9_handoff.json')
    assert handoff['ready_for_stage9'] and validate_handoff(handoff)==load(x,'m1_allocation.json')['recommended_nominal']['parameters']
    assert handoff['M2_status']=='NOT_EVALUATED' and not handoff['FULL_SYSTEMSPEC_CERTIFIED']


def test_false_quality_stop_rejected_without_losing_recommendation(context,tmp_path):
    x=loop(context,tmp_path,Policy(basis='BEST_KNOWN_SUFFICIENT'));r=x.run()
    assert r['termination_reason']=='INVALID_LLM_DECISION'
    assert r['m1_allocation_status']=='KNOWN_M1_FEASIBLE_RECHECKED'
    assert r['quality_target_status']['status']=='NOT_REACHED'
    assert 'quality STOP' in load(x,'round_02/validation_error_00.json')['message']
    assert load(x,'stage9_handoff.json')['ready_for_stage9']


def test_quality_reached_separate_from_feasibility(context,tmp_path):
    x=loop(context,tmp_path,quality_target=0.,min_decisions_before_quality_stop=1)
    r=x.run();assert r['termination_reason']=='M1_QUALITY_TARGET_REACHED'
    assert r['quality_target_status']['status']=='REACHED'
    assert r['m1_allocation_status']=='KNOWN_M1_FEASIBLE_RECHECKED'
    assert load(x,'stage9_handoff.json')['ready_for_stage9']


def test_provider_failure_preserves_rechecked_stage7_and_handoff(context,tmp_path):
    x=loop(context,tmp_path,Policy(fail=True));r=x.run();a=load(x,'m1_allocation.json')
    assert r['termination_reason']=='LLM_PROVIDER_FAILED'
    assert a['recommended_nominal']['parameter_sha256']==a['best_stage7_calibration']['parameter_sha256']
    assert r['quality_target_status']['status']=='NOT_REACHED'
    assert load(x,'stage9_handoff.json')['ready_for_stage9']


def test_budget_exhaustion_and_legacy_output_never_override_recommendation(context,tmp_path):
    x=loop(context,tmp_path,Policy(),max_decisions=1,max_llm_calls=1,min_decisions_before_quality_stop=1)
    r=x.run();a=load(x,'m1_allocation.json')
    assert r['termination_reason']=='DECISION_BUDGET_EXHAUSTED'
    assert r['quality_target_status']['status']=='NOT_REACHED'
    assert a['recommended_nominal']['judgment']['minimum_normalized_margin']>=a['best_stage7_calibration']['judgment']['minimum_normalized_margin']
    assert 'new_allocation' in a['legacy_non_authoritative_fields']
    assert validate_handoff(load(x,'stage9_handoff.json'))==a['recommended_nominal']['parameters']


@pytest.mark.parametrize('failure',['EXCEPTION','NUMERICAL_FAILURE'])
def test_numerical_failures_charged_and_best_retained(context,tmp_path,monkeypatch,failure):
    x=loop(context,tmp_path)
    def broken(*args):
        if failure=='EXCEPTION':raise ArithmeticError('TEST numeric failure')
        return MappingResult(status=Status.NUMERICAL_FAILURE,reason='TEST numeric failure')
    monkeypatch.setattr('pll_allocation.region_explorer.explorer.evaluate',broken)
    r=x.run();a=load(x,'m1_allocation.json');h=load(x,'stage9_handoff.json')
    assert a['recommended_nominal'] and r['cost']['M1_calls']<=64
    assert r['m1_allocation_status']=='KNOWN_M1_FEASIBLE_RECHECK_FAILED_OR_UNAVAILABLE'
    assert r['quality_target_status']['status']=='UNVERIFIED_RECHECK_FAILED'
    assert not h['ready_for_stage9']
    with pytest.raises(ValueError,match='blocked'):validate_handoff(h)
    assert r['cost']['executor']['M1_failures']>0


def test_no_feasible_candidate_blocks_handoff(context,tmp_path):
    p=raw_problem(load_physics_context(context)['problem']);p['specs'][1]['min']=95
    file=tmp_path/'impossible.json';file.write_text(json.dumps(p),encoding='utf-8')
    x=AgentSearchLoop(context,tmp_path/'run',config=config(),provider_config={},problem_path=file,policy=Policy())
    r=x.run();h=load(x,'stage9_handoff.json')
    assert r['termination_reason']=='PROVEN_M1_INFEASIBLE'
    assert not h['ready_for_stage9'] and h['recommended_nominal'] is None
    with pytest.raises(ValueError):validate_handoff(h)


@pytest.mark.parametrize('field',['block_spec_SI','system_spec','model_fingerprint','recommendation_recheck','ready_for_stage9'])
def test_tampered_handoff_rejected_even_after_fingerprint_reseal(context,tmp_path,field):
    x=loop(context,tmp_path,Policy(fail=True));x.run();h=load(x,'stage9_handoff.json')
    if field=='block_spec_SI':h[field]['C1']['value']*=2
    elif field=='system_spec':h[field][0]['max']*=2
    elif field=='model_fingerprint':h[field]='wrong'
    elif field=='recommendation_recheck':h[field]['passed']=False
    else:h[field]=False
    h['handoff_sha256']=fingerprint({k:v for k,v in h.items() if k!='handoff_sha256'})
    with pytest.raises(ValueError):validate_handoff(h)


def test_scheduler_reuses_leftover_budget_for_another_seed(context,tmp_path,monkeypatch):
    import scipy.optimize
    from types import SimpleNamespace
    starts=[]
    def early(fun,u,**kwargs):
        starts.append(list(u))
        kwargs['constraints'][0]['fun'](u)
        kwargs['constraints'][0]['fun'](u)  # Exact repeated numerical request exercises cache.
        kwargs['callback'](u)
        return SimpleNamespace(x=u,success=True,status=0,message='TEST early convergence',nit=1)
    monkeypatch.setattr(scipy.optimize,'minimize',early)
    x=loop(context,tmp_path,Policy(dimensions=2));x.run()
    assert len(starts)>1
    assert x.explorer.cost()['cache_hits']>0 and x.explorer.cost()['M1_calls']<=64


def test_solver_exception_keeps_best_and_formal_recheck(context,tmp_path,monkeypatch):
    def broken(*args,**kwargs):raise RuntimeError('TEST solver failure')
    monkeypatch.setattr('scipy.optimize.minimize',broken)
    x=loop(context,tmp_path);r=x.run()
    assert r['solver_execution_status']['exceptions']>0
    assert r['m1_allocation_status']=='KNOWN_M1_FEASIBLE_RECHECKED'
    assert load(x,'stage9_handoff.json')['ready_for_stage9']
