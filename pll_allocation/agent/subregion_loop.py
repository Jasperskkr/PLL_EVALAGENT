"""Explicit Stage7.5 policy/controller using the existing one M1 executor."""
from copy import deepcopy
import csv
import hashlib
import json
from pathlib import Path
import time

from ..allocation.core import Meter,write_new
from ..block_space.contracts import FREE_IDS
from ..exploration import load_physics_context
from ..exploration.contracts import load_problem,require
from ..physics_mapping.model import fingerprint
from ..region_explorer import RegionExplorer
from .candidates import CandidateArchive
from .region_policy import LLMRegionPolicy,ProviderError
from .subregion_contracts import validate_config,validate_exploration,union_volume
from .subregion_tools import envelope,execute_tool
from .subregion_context import export_context,was_formal_call
from .subregion_prior import build_prior

PROMPT='''You plan EXPLORATION subregions for the current ideal CPPLL from small initial calibration only.
You are not selecting among a completed Stage7 region menu and must not calculate/fabricate M1 results.
Use current SystemSpec, original six-axis domain, actual samples, structured physical evidence and observations.
Return exactly one JSON object with fields:
schema_version="pll-exploration-decision-1.0", decision_id (unique string),
prior_context_sha256 (copy current prior), sampling_seed (copy execution_seed), global_coverage_budget (copy reserved amount), reason, evidence_ids,
regions (prefer2-3, allowed1-6). Each region has exactly:
region_id, normalized_bounds (Icp,Rz,C1,C2,f0,Kvco each[lower,upper] within[0,1], lo<hi),
tools (list of {method,m1_budget,seed_id}), focus_constraints (supported current metric IDs),
evidence_ids, hypothesis, success_condition, failure_modes (nonempty string list).
Methods: SOBOL_IN_REGION, ANALYTICAL_INVERSE, PHYSICS_GUIDED_SEEDS, LOCAL_SENSITIVITY.
Each tool positive integer m1_budget; sum across ALL regions/tools <=budget.round_M1_limit.
Unused budgets are not reassigned. Preserve global reserve; it executes separately after regional rounds.
ANALYTICAL_INVERSE and PHYSICS_GUIDED_SEEDS use the SAME original continuous-cap inverse_at_shape:
target BW midpoint, three peak-phase shapes, legal local gain split; they may yield no in-region point.
SOBOL_IN_REGION supplies actual random local candidates. LOCAL_SENSITIVITY requires seed_id of an actual
formal M1 point INSIDE the box; other methods must use seed_id=null. No other seed list/final BlockSpec.
Consider PM ceiling from C2/C1, loop Icp*Kvco coupling, Rz*C2 shape and f0/Kvco tuning together.
No region can violate a proven necessary condition; no box is certified feasible. Explain explicit testable
success conditions and potential failure modes. Local slopes are not global monotonic laws.
Cite only allowed_evidence_ids. Lock time/jitter/M2 cannot be M1 feasibility criteria.
On round2 read actual history and change geometry/budgets based on observations. If validation_feedback
is present repair that exact error, do not assume a rejected proposal was executed. Never change hard constraints.'''


def source_manifest():
    root=Path(__file__).resolve().parents[2]
    files=[*sorted((root/'pll_allocation/agent').glob('*.py')),*sorted((root/'pll_allocation/region_explorer').glob('*.py')),
           root/'pll_allocation/pipeline.py',root/'pll_allocation/llm_transport.py']
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def execute_multi_region_plan(controller,plan):
    """Physical-intent mode of the existing subregion loop; no new solver.

    Each region constructs and persists its own seeds before its actual search.
    Diagnostic execution is mandatory even after another region's first PASS.
    All calls after that first PASS charge the shared incremental budget.
    """
    for intent in sorted(plan['regions'],key=lambda r:r['priority']):
        folder=controller.root/('region_'+intent['region_id']);folder.mkdir()
        region=controller.build_intent(intent,folder)
        controller.probe(region)
    controller.initial_llm_attempts=len(controller.llm)
    if controller.first is None:
        controller.feedback_rounds()


def prepare_initial(problem_path,out,config):
    """New fixed Sobol calibration; no inverse, hidden sensitivity or full Stage7."""
    cfg=validate_config(config);problem=load_problem(problem_path)
    require(cfg['region_radius']==problem['exploration']['region_radius'],'pilot radius must match ResearchProblemV2 region summary setting')
    root=Path(out);root.mkdir(parents=True,exist_ok=False)
    empty=export_context(problem,[],root/'empty_context',cost={'M1_calls':0},scope='EMPTY_BOOTSTRAP_NO_SEARCH')
    ex=RegionExplorer(empty,root/'executor',m1_budget=cfg['initial_m1_budget'])
    d=envelope(ex,decision_id='INITIAL:SOBOL',region_id='INITIAL_GLOBAL',bounds={k:[0.,1.] for k in FREE_IDS},
        budget=cfg['initial_m1_budget'],seed=cfg['seed'],proposals=cfg['initial_sobol_samples'])
    obs=ex.execute(d)
    ex.close()
    # Prefix inherited IDs so new RegionExplorer sessions cannot collide with
    # their own A8S request IDs. Preserve the exact source evidence mapping.
    samples=deepcopy(ex.rows);ids={r['evidence_id']:'CAL:'+r['evidence_id'] for r in samples}
    for r in samples:
        r['source_evidence_id']=r['evidence_id'];r['evidence_id']=ids[r['evidence_id']]
        if r.get('duplicate_of'):r['duplicate_of']=ids[r['duplicate_of']]
    path=export_context(problem,samples,root/'initial_context',cost=ex.cost(),scope='SMALL_INITIAL_SOBOL_ONLY')
    write_new(root/'initial_manifest.json',{'problem_sha256':problem['problem_sha256'],'context_path':str(path.resolve()),
        'initial_M1_calls':ex.counts['M1_calls'],'formal_cap':cfg['initial_m1_budget'],'sobol_seed':cfg['seed'],
        'sobol_proposals':cfg['initial_sobol_samples'],'source_observation':obs,
        'no_physics_seed_or_sensitivity_before_LLM':True,'LLM_calls':0,'M2_calls':0})
    return path


def deterministic(prior,round_no):
    return {'schema_version':'pll-exploration-decision-1.0','decision_id':f'DETERMINISTIC:{round_no}',
        'prior_context_sha256':prior['prior_context_sha256'],'sampling_seed':prior['execution_seed'],'global_coverage_budget':prior['budget']['global_coverage_reserve_M1'],
        'reason':'Predeclared original physics inverse followed by global Sobol; no LLM data used.',
        'evidence_ids':['REL:shape','REL:phase_ceiling','REL:inverse_gain'],
        'regions':[{'region_id':f'DET_GLOBAL:{round_no}','normalized_bounds':{k:[0.,1.] for k in FREE_IDS},
            'tools':[{'method':'PHYSICS_GUIDED_SEEDS','m1_budget':prior['budget']['round_M1_limit']//2,'seed_id':None},
                     {'method':'SOBOL_IN_REGION','m1_budget':prior['budget']['round_M1_limit']-prior['budget']['round_M1_limit']//2,'seed_id':None}],
            'focus_constraints':[s['metric'] for s in prior['problem']['specs'] if s['enabled'] and s['support_status']=='M1_SUPPORTED'],
            'evidence_ids':['REL:shape','REL:phase_ceiling','REL:inverse_gain'],'hypothesis':'Peak-phase inverse seeds match supported BW target; Sobol preserves broad exploration.',
            'success_condition':'At least one actual M1 feasible point; finite samples do not certify domain.',
            'failure_modes':['No in-domain inverse reconstruction','Finite Sobol misses feasible intersection']} ]}


def run_subregion(problem_path,out,*,config,provider_config=None,initial_context_path=None,policy=None):
    cfg=validate_config(config);problem=load_problem(problem_path);root=Path(out).resolve()
    require(cfg['region_radius']==problem['exploration']['region_radius'],'pilot radius must match ResearchProblemV2 region summary setting')
    root.mkdir(parents=True,exist_ok=False);start=time.perf_counter();sources=source_manifest()
    if initial_context_path is None:initial_context_path=prepare_initial(problem_path,root/'calibration',cfg)
    context=load_physics_context(initial_context_path)
    require(context.get('exploration_source')=='SMALL_INITIAL_SOBOL_ONLY','only declared small initial context is allowed; full Stage7 input rejected')
    require(context['problem']==problem,'shared calibration problem mismatch')
    initial=[json.loads(s) for s in (Path(initial_context_path).parent/'m1_samples.jsonl').read_text(encoding='utf-8').splitlines()]
    initial_calls=sum(was_formal_call(r) for r in initial)
    require(initial_calls<=cfg['initial_m1_budget'] and len(initial)<=cfg['initial_sobol_samples'] and
            all(r['origin'].startswith('LOCAL_SOBOL:') for r in initial),'calibration exceeds small Sobol-only contract')
    ex=RegionExplorer(initial_context_path,root/'executor',m1_budget=cfg['total_m1_budget']-initial_calls)
    archive=CandidateArchive(ex,root/'candidate_archive.jsonl');ex.candidate_archive=archive
    is_llm=cfg['strategy']=='LLM_GUIDED_STAGE7_5'
    planner=policy if policy is not None else LLMRegionPolicy(provider_config or {},prompt=PROMPT) if is_llm else None
    real=isinstance(planner,LLMRegionPolicy)
    meter=Meter(cheap_limit=cfg['analytic_call_limit'],m1_limit=0)
    write_new(root/'run_manifest.json',{'config':cfg,'problem_sha256':problem['problem_sha256'],
        'initial_context_path':str(Path(initial_context_path).resolve()),'initial_context_sha256':context['context_sha256'],
        'initial_formal_M1_calls':initial_calls,'scope':'REAL_LLM_EXPLORATION' if is_llm and real else 'TEST_POLICY_NOT_REAL_LLM' if is_llm else 'DETERMINISTIC_NOT_LLM',
        'source_manifest':sources,'model_fingerprint':context['model']['model_sha256'],'M2_status':'NOT_EVALUATED'})
    history=[];calls=0;seen_ids=set();signatures=set();all_obs=[];failure=None;status='COMPLETED';decisions=[]
    def append(name,data):
        with (root/name).open('a',encoding='utf-8') as f:f.write(json.dumps(data,ensure_ascii=False,allow_nan=False)+'\n')
    for name in ('EXPLORATION_DECISIONS.jsonl','EXPLORATION_BUDGET_TRACE.jsonl'):(root/name).touch(exist_ok=False)
    try:
        for round_no in range(1,cfg['max_decisions']+1):
            folder=root/f'round_{round_no:02d}';folder.mkdir()
            correction=None;accepted=None
            for retry in range(cfg['validation_retries']+1 if is_llm else 1):
                prior=build_prior(ex,cfg,history,round_no,correction)
                write_new(folder/f'prior_{retry:02d}.json',prior)
                if round_no==1 and retry==0:write_new(root/'PHYSICS_PRIOR_CONTEXT.json',prior)
                try:
                    if is_llm:
                        if calls>=cfg['max_llm_calls']:
                            status='LLM_CALL_BUDGET_EXHAUSTED';break
                        calls+=1;raw=planner.decide(deepcopy(prior),folder/f'llm_call_{retry:02d}')
                    else:raw=deterministic(prior,round_no)
                    write_new(folder/f'proposal_{retry:02d}.json',raw)
                    accepted,validation=validate_exploration(raw,problem=problem,
                        allowed_evidence=set(prior['allowed_evidence_ids']),evidence=ex.evidence,
                        max_budget=min(cfg['round_m1_budget'],ex.limit-ex.counts['M1_calls']-cfg['global_m1_budget']),
                        global_reserve=cfg['global_m1_budget'],prior_id=prior['prior_context_sha256'],
                        seen_ids=seen_ids,seen_signatures=signatures)
                    write_new(folder/'validation.json',validation)
                    seen_ids.add(accepted['decision_id']);signatures.add(validation['signature']);decisions.append(accepted)
                    append('EXPLORATION_DECISIONS.jsonl',{'source':'REAL_LLM' if real else 'TEST_POLICY' if is_llm else 'DETERMINISTIC',
                        'decision':accepted,'validation':validation})
                    break
                except (ValueError,KeyError,TypeError) as error:
                    correction={'code':'INVALID_EXPLORATION_DECISION','message':str(error),'retry':retry}
                    write_new(folder/f'validation_error_{retry:02d}.json',correction)
                    accepted=None
            if accepted is None:
                if status=='COMPLETED':status='INVALID_LLM_DECISION' if is_llm else 'INVALID_DETERMINISTIC_DECISION'
                break
            observations=[]
            for ri,r in enumerate(accepted['regions']):
                for ti,t in enumerate(r['tools']):
                    obs=execute_tool(ex,decision_id=f"{accepted['decision_id']}:{ri}:{ti}",region=r,tool=t,
                        seed=accepted['sampling_seed']+ri*4+ti,config=cfg,meter=meter)
                    observations.append(obs);all_obs.append(obs)
                    append('EXPLORATION_BUDGET_TRACE.jsonl',{'round':round_no,'region_id':r['region_id'],
                        'tool':t,'actual_new_M1':obs['cost']['M1_calls'],'initial_M1':initial_calls,
                        'total_strategy_M1':initial_calls+ex.counts['M1_calls'],'hard_limit':cfg['total_m1_budget'],
                        'global_reserve_preserved':cfg['global_m1_budget'],'cache_hits':obs['cost']['cache_hits']})
            archive.sync()
            record={'round':round_no,'decision':accepted,'observations':observations,'best_known':deepcopy(archive.best()),
                    'source':'REAL_LLM' if real else 'TEST' if is_llm else 'DETERMINISTIC'}
            history.append(record);write_new(folder/'observation.json',record)
    except ProviderError as error:
        status='LLM_PROVIDER_FAILED';failure={'type':type(error).__name__,'message':str(error)}
    except Exception as error:
        status='PIPELINE_ERROR';failure={'type':type(error).__name__,'message':str(error)}
    # The same fixed, independent global-reserve stream runs even after an LLM
    # failure. It is explicitly controller coverage, never credited as LLM work.
    global_region={'region_id':'RESERVED_GLOBAL','normalized_bounds':{k:[0.,1.] for k in FREE_IDS}}
    try:
        obs=execute_tool(ex,decision_id='CONTROLLER:GLOBAL_RESERVE',region=global_region,
            tool={'method':'SOBOL_IN_REGION','m1_budget':cfg['global_m1_budget'],'seed_id':None},
            seed=cfg['seed']+1,config=cfg|{'max_tool_proposals':cfg['global_sobol_samples']},meter=meter)
        obs['source']='CONTROLLER_GLOBAL_COVERAGE_NOT_LLM';all_obs.append(obs)
        write_new(root/'global_coverage_observation.json',obs)
    except Exception as error:
        failure={'type':type(error).__name__,'message':'global reserve: '+str(error)};status='PIPELINE_ERROR'
    archive.sync();summary=archive.summary();result_executor=ex.close()
    total=initial_calls+ex.counts['M1_calls']
    formal=[r for r in initial+ex.rows if was_formal_call(r)]
    first=next((i for i,r in enumerate(formal,1) if r['judgment']['m1_feasibility']=='FEASIBLE'),None)
    costs={'M1_calls':total,'initial_shared_M1_calls':initial_calls,'incremental_M1_calls':ex.counts['M1_calls'],
        'M1_limit':cfg['total_m1_budget'],'analytic_calls':meter.counts['analytic_calls'],
        'LLM_calls':sum(c.get('real_network_call',False) for c in getattr(planner,'calls',[])) if real else 0,
        'test_policy_calls':calls if is_llm and not real else 0,'reported_usage':[c.get('usage') for c in getattr(planner,'calls',[])],
        'LLM_elapsed_s':sum(c.get('elapsed_s',0) for c in getattr(planner,'calls',[])),
        'wall_time_s':time.perf_counter()-start,'M2_calls':0,'monetary_cost':None}
    derivatives=[o['sensitivity'] for o in all_obs if o.get('sensitivity')]
    exported=export_context(problem,initial+ex.rows,root/'stage7_context',cost=costs,sensitivities=derivatives,
                            scope=cfg['strategy'],llm_executed=real and costs['LLM_calls']>0)
    with (root/'M1_CANDIDATES.csv').open('xb') as f:f.write((exported.parent/'m1_samples.csv').read_bytes())
    with (root/'SUBREGION_EXECUTION.csv').open('x',encoding='utf-8-sig',newline='') as f:
        fields=['observation_id','decision_id','tool_method','M1_calls','feasible','infeasible','feasible_fraction','best_margin','wall_time_s','allocated_M1','cache_hits','actual_region_equals_requested','normalized_bounds']
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for o in all_obs:w.writerow({'observation_id':o['observation_id'],'decision_id':o['decision_id'],
            'tool_method':o['tool_method'],'M1_calls':o['cost']['M1_calls'],'feasible':len(o['new_positive_evidence_ids']),
            'infeasible':len(o['new_negative_evidence_ids']),'feasible_fraction':o['M1_feasible_fraction'],
            'best_margin':o['latest_minimum_normalized_margin'],'wall_time_s':o['cost']['wall_time_s'],
            'allocated_M1':o['cost']['allocated_M1_budget'],'cache_hits':o['cost']['cache_hits'],
            'actual_region_equals_requested':o['actual_region_equals_requested'],'normalized_bounds':json.dumps(o['normalized_bounds'])})
    boxes=[r['normalized_bounds'] for d in decisions for r in d['regions']]
    # Regions are capped at six per decision: <=12 boxes keeps exact union finite.
    result={'status':status,'strategy':cfg['strategy'],'cost':costs,'failure':failure,'first_M1_feasible_evaluation':first,
        'formal_feasible_points':sum(r['judgment']['m1_feasibility']=='FEASIBLE' for r in formal),
        'best_known':summary['best_known'],'best_feasible':archive.best(feasible_only=True),'candidate_archive_summary':summary,
        'accepted_decisions':len(decisions),'LLM_region_execution_completed':is_llm and real and bool(history),
        'outside_planned_regional_envelopes_fraction':1-union_volume(boxes),
        'volume_scope':'Geometry only, excluding reserved global stream; every unmeasured continuous point remains uncertified',
        'physics_context':str(exported),'initial_context_sha256':context['context_sha256'],
        'M2_status':'NOT_EVALUATED','FULL_SYSTEMSPEC_CERTIFIED':False,'executor_result':result_executor}
    require(source_manifest()==sources,'source changed during pilot')
    require(total<=cfg['total_m1_budget'],'formal M1 hard limit exceeded')
    write_new(root/'cost_summary.json',costs);write_new(root/'result.json',result)
    write_new(root/'output_manifest.json',{p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob('*')) if p.is_file()})
    return result
