"""M2 verification/feedback controller over the existing physics-tool Agent loop.

Policy, inverse construction, SLSQP, formal M1 and archive remain their existing
implementations. This module owns measurement provenance and cross-stage budgets.
"""
from copy import deepcopy
import json
from pathlib import Path
import time

from ..allocation.core import write_new
from ..io_contracts import read_json
from ..exploration import load_physics_context
from ..exploration.contracts import load_problem, require, judge, check_candidate
from ..physics_mapping.model import MappingResult, Status, fingerprint
from ..region_explorer import RegionExplorer
from ..verification.continuous import execute_request, verification_request
from .candidates import CandidateArchive, rank
from .handoff import validate_handoff, build_handoff
from .initial_allocation import run_initial_allocation
from .physics_tool_policy import validate_config as search_config


def read(path):
    return read_json(path)


def validate_config(raw):
    fields={'schema_version','m1_budget','m2_budget','llm_budget','max_reallocations','m2_timeout_s','search'}
    require(isinstance(raw,dict) and fields <= set(raw) <= fields | {'m2_target_count'} and raw['schema_version']=='pll-stage9-feedback-1.0',
            'complete verification feedback configuration required')
    c=deepcopy(raw); c.setdefault('m2_target_count', 1); c['search']=search_config(c['search'])
    require(type(c['m2_target_count']) is int and 1 <= c['m2_target_count'] <= 100,
            'm2_target_count must be 1..100')
    require(c['m2_target_count'] == 1 or c['search'].get('candidate_pool'),
            'multiple M2 targets require the continuous candidate pool')
    for k in ('m1_budget','m2_budget','llm_budget','max_reallocations'):
        require(type(c[k]) is int and c[k]>=0,k+': nonnegative hard limit required')
    require(c['max_reallocations']<=10 and c['m2_budget']<=32 and c['llm_budget']<=40,'bounded verification feedback run required')
    require(type(c['m2_timeout_s']) in (int,float) and 0<c['m2_timeout_s']<=3600,'bounded M2 timeout required')
    return c


def load_handoff(path, problem_config):
    item=read(path); validate_handoff(item)
    problem=load_problem(problem_config)
    require(item['problem']==problem,'handoff differs from current problem configuration')
    binding=item['source_context_binding']
    if 'relative_path' in binding:
        require(isinstance(binding['relative_path'],str) and binding['relative_path'] and
                not Path(binding['relative_path']).is_absolute(), 'relative context path required')
        context=(Path(path).resolve().parent/binding['relative_path']).resolve()
    else:
        context=Path(binding['path'])
    loaded=load_physics_context(context)
    require(loaded['context_sha256']==item['context_sha256'] and loaded['problem']==problem,
            'saved source context differs or is unavailable')
    return item,context


def feedback_summary(request, observation, remaining, history):
    failures=[c for c in observation['constraints'] if c['status']=='FAIL']
    metrics=observation['metrics']; m1=request['M1_metrics']
    bw=metrics['BW_Hz']; valid=bw['valid'] and m1.get('BW_Hz') is not None
    deviation={'BW_Hz': {'M1_prediction':m1.get('BW_Hz'),'M2_measurement':bw['value'],
        'absolute_difference_Hz':bw['value']-m1['BW_Hz'] if valid else None,
        'relative_difference':bw['value']/m1['BW_Hz']-1 if valid else None,
        'comparison_scope':'continuous ideal M1 vs sampled native warm-start divided-phase -3dB; diagnostic cross-model deviation, not numerical error',
        'definitions_identical':False}, 'lock_time_s':{'comparable':False,'reason':'M1 has no reliable lock-time mapping'}}
    return {'schema_version':'pll-m2-feedback-summary-1.0','evidence_id':observation['evidence_id'],
        'run_id':request['run_id'],'observation_id':observation['observation_id'],
        'candidate_id':request['candidate_id'],'candidate_sha256':request['candidate_sha256'],
        'problem_sha256':request['problem_sha256'],'model_fingerprint':request['handoff']['model_fingerprint'],
        'M1':m1,'M2':metrics,'constraints':observation['constraints'],
        'failed_constraints':[c['metric'] for c in failures],
        'most_severe_failure':min(failures,key=lambda c:c['margin']/c['spec']['normalization_scale'],default=None),
        'm1_m2_deviation':deviation,'M2_status':observation['overall_status'],
        'supported_metrics_status':observation['supported_metrics_status'],
        'execution_status':observation['execution_status'],
        'protocol_id':request['protocol_id'],'protocol_sha256':request['protocol_sha256'],
        'M2_model_fingerprint':observation['M2_model_fingerprint'],
        'raw_evidence_path':observation['raw_evidence_path'], 'remaining_budgets':remaining,
        'verification_history':history, 'measurement_validity':{k:v['valid'] for k,v in metrics.items()},
        'capability_boundary':observation['capability_boundary']}


def search_feedback(request, summary):
    """Use the existing provenance-bound external-feedback contract unchanged."""
    return {'schema_version':'pll-search-feedback-1.0','problem_sha256':request['problem_sha256'],
        'model_fingerprint':request['handoff']['model_fingerprint'],
        'observations':[{'evidence_id':'EXT:'+summary['evidence_id'],
            'candidate_sha256':request['candidate_sha256'],'model_level':'M2',
            'protocol':request['protocol_id']+':'+request['protocol_sha256'],
            'parameters':deepcopy(request['parameters']), 'measurements':deepcopy(summary),
            'failed_constraints':summary['failed_constraints'], 'm1_m2_deviation':summary['m1_m2_deviation']}],
        'preferred_physics_focus':[], 'historical_failure_ids':[x['observation_id'] for x in summary['verification_history']
            if x['M2_status']=='FAIL']}


def applicable(row, handoff):
    try:
        require(row['model_fingerprint']==handoff['model_fingerprint'] and row['problem_sha256']==handoff['problem_sha256'] and
                row['parameter_sha256']==fingerprint(row['parameters']),'incompatible candidate')
        result=MappingResult(**(row['formal_M1_result']|{'status':Status(row['formal_M1_result']['status'])}))
        require(result.status==Status.OK and result.parameter_sha256==row['parameter_sha256'] and
                result.metrics==row['metrics'],'invalid formal M1 evidence')
        require(check_candidate(handoff['problem'],row['parameters'])['status']=='NECESSARY_CONDITIONS_SATISFIED', 'illegal candidate')
        require(judge(handoff['problem'],row['parameters'],result)==row['judgment'] and
                row['judgment']['m1_feasibility']=='FEASIBLE','current Spec not satisfied')
        return True
    except (ValueError,KeyError,TypeError):
        return False


def run_feedback(handoff_path, out, *, problem_config, feedback_config, provider_config=None,
                        policy=None, m2_executor=None):
    """Real execution by default. Injected TEST policies/backends are labeled.

    M1 best-known and M2-verified recommendations are independent. A failed M2
    candidate remains M1-feasible in the append-only ledger but cannot overwrite
    a candidate with passing supported M2 measurements.
    """
    cfg=validate_config(feedback_config)
    initial,context_path=load_handoff(handoff_path,problem_config)
    root=Path(out).resolve(); root.mkdir(parents=True,exist_ok=False)
    start=time.perf_counter(); run_id=root.name
    write_new(root/'verification_problem_resolved.json',initial['problem'])
    write_new(root/'stage9_problem_resolved.json',initial['problem'])
    write_new(root/'initial_handoff.json',initial); write_new(root/'verification_config.json',cfg)
    write_new(root/'stage9_config.json',cfg)
    paths={name:root/(name+'.jsonl') for name in ('m2_verifications','feedback_summaries','agent_decisions',
        'reallocation_candidates','stage9_run_events','candidate_archive')}
    for p in paths.values():p.touch(exist_ok=False)
    def append(name,item):
        with paths[name].open('a',encoding='utf-8') as f:f.write(json.dumps(item,ensure_ascii=False,allow_nan=False)+'\n')
    def event(kind,**data):append('stage9_run_events',{'event':kind,'run_id':run_id,**data})
    counts={'M1_calls':0,'M2_verifications':0,'LLM_calls':0,'M2_cache_hits':0,'completed_native_runs':0,
        'integration_points':0,'native_elapsed_s':0.,'tokens':{},'monetary_cost':None}
    def remaining():return {k:cfg[c]-counts[k] for k,c in
        (('M1_calls','m1_budget'),('M2_verifications','m2_budget'),('LLM_calls','llm_budget'))}
    ledger=[deepcopy(initial['recommended_nominal'])|{'stage9_source_run':str(Path(handoff_path).resolve().parent)}]
    append('candidate_archive',ledger[0])
    prior_archive=Path(handoff_path).resolve().parent/'candidate_archive.jsonl'
    if prior_archive.exists():
        for line in prior_archive.read_text(encoding='utf-8').splitlines():
            row=json.loads(line)
            if applicable(row,initial):
                item=deepcopy(row)|{'stage9_source_run':str(prior_archive.parent)}
                ledger.append(item); append('candidate_archive',item)
    history=[]; searches=[]; cache={}; verified={}; reverify_reasons=set(); reverify=None
    pool = cfg['search'].get('candidate_pool')
    current=initial; termination='MAX_REALLOCATIONS'; failure=None
    mode=('TEST_INJECTED_NOT_RESEARCH' if policy is not None or m2_executor is not None else
          'REAL_M2_'+pool['mode'] if pool else 'REAL_M2_DETERMINISTIC' if
          cfg['search']['policy']=='DETERMINISTIC_PHYSICS_TOOL' else 'REAL_M2_REAL_LLM')
    event('RUN_STARTED',mode=mode,initial_handoff_sha256=initial['handoff_sha256'])

    def passing_candidates():
        passing = {k for k, v in verified.items() if v['observation']['supported_metrics_status'] == 'PASS'}
        if pool:
            from .candidate_pool import joint_candidates
            return joint_candidates(ledger, initial['problem'], pool, passing)
        return [v['handoff']['recommended_nominal'] for k, v in verified.items() if k in passing]

    def audited_handoff(selected, suffix):
        """Reuse the original independent selected-point audit and gate."""
        ex=RegionExplorer(context_path,root/('candidate_audit_'+suffix),m1_budget=2,reserved_final_calls=1)
        archive=CandidateArchive(ex,ex.root/'candidate_archive.jsonl')
        recheck=ex.recheck_recommendation(selected)
        counts['M1_calls']+=ex.counts['M1_calls']; ex.close()
        handoff=build_handoff(ex,archive,selected,recheck,{'termination_reason':'M1_POOL_CANDIDATE_SELECTION'},ex.cost(), handoff_dir=root)
        write_new(root/('pool_handoff_'+suffix+'.json'),handoff)
        return handoff

    try:
        for cycle in range(cfg['m2_budget'] if pool else cfg['max_reallocations']+1):
            if remaining()['M2_verifications']<1:
                termination='M2_BUDGET_EXHAUSTED'; break
            if remaining()['M1_calls']<1:
                termination='M1_BUDGET_EXHAUSTED_BEFORE_POSTHOC'; break
            oid=run_id+':V'+str(cycle+1)
            request=verification_request(current,run_id=run_id,observation_id=oid,timeout_s=cfg['m2_timeout_s'])
            key=fingerprint({k:request[k] for k in ('candidate_sha256','problem_sha256','protocol_sha256','M2_model')})
            if key in cache and reverify is None:
                # No duplicate native work; explicit protocol/model/current-Spec cache applicability.
                counts['M2_cache_hits']+=1; event('DUPLICATE_VERIFICATION_SKIPPED',cache_key=key)
                termination='UNCHANGED_CANDIDATE_ALREADY_VERIFIED'; break
            if reverify is not None:
                event('EXPLICIT_UNKNOWN_REVERIFICATION',decision=reverify,cache_key=key)
                reverify=None
            write_new(root/f'verification_{cycle+1:02d}_request.json',request)
            counts['M2_verifications']+=1
            measured=(m2_executor or execute_request)(request,root/f'm2_{cycle+1:02d}')
            require(measured['candidate_sha256']==request['candidate_sha256'] and
                measured['request_sha256']==request['request_sha256'] and measured['problem_sha256']==request['problem_sha256'] and
                measured['protocol_sha256']==request['protocol_sha256'] and
                measured['M2_model_fingerprint']==fingerprint(request['M2_model']),'M2 result provenance mismatch')
            for k in ('completed_native_runs','integration_points','native_elapsed_s'):counts[k]+=measured['cost'][k]
            counts['M1_calls']+=measured['cost']['posthoc_M1_calls']
            require(counts['M1_calls']<=cfg['m1_budget'],'M1 hard budget exceeded')
            cache[key]=measured; verified[request['candidate_sha256']]={'handoff':current,'observation':measured}
            append('m2_verifications',{'request':request,'observation':measured,'cache_key':key})
            history.append({'observation_id':oid,'candidate_sha256':request['candidate_sha256'],
                'M2_status':measured['overall_status'],'supported_metrics_status':measured['supported_metrics_status'],
                'execution_status':measured['execution_status'],'evidence_id':measured['evidence_id']})
            if 'selection_evidence' in current:
                event('PHYSICS_M2_SELECTION', candidate_sha256=request['candidate_sha256'],
                      selection=current['selection_evidence'])
            summary=feedback_summary(request,measured,remaining(),history)
            summary['previous_searches']=deepcopy(searches)
            passed = passing_candidates()
            history[-1].update(elapsed_s=time.perf_counter()-start, joint_pass_count=len(passed))
            summary['joint_target_count'] = cfg['m2_target_count']
            summary['joint_pass_count'] = len(passed)
            summary['joint_pass_candidates'] = deepcopy(passed)
            summary['search_purpose'] = ('REPLENISH_JOINT_POOL' if measured['supported_metrics_status'] == 'PASS'
                                       else 'REPAIR_OR_REPLACE_FAILED_CANDIDATE')
            summary['best_known_M1']=deepcopy(min(ledger,key=rank))
            unseen={r['parameter_sha256']:r for r in ledger if r['parameter_sha256'] not in verified}
            summary['unverified_M1_candidates']=[{'candidate_sha256':r['parameter_sha256'],
                'evidence_id':r['evidence_id'],'parameters':r['parameters'],'metrics':r['metrics'],
                'judgment':r['judgment'],'source_run':r.get('stage9_source_run')}
                for r in sorted(unseen.values(),key=rank)[:12]]
            append('feedback_summaries',summary); event('M2_COMPLETED',observation_id=oid,
                M2_status=measured['overall_status'],supported_metrics_status=measured['supported_metrics_status'])
            if len(passed) >= cfg['m2_target_count']:
                termination=('SUPPORTED_M2_METRICS_PASS' if cfg['m2_target_count'] == 1
                             else 'JOINT_M1_M2_TARGET_REACHED'); break
            if not pool and cycle==cfg['max_reallocations']:termination='MAX_REALLOCATIONS'; break
            if remaining()['M2_verifications']<1:termination='M2_BUDGET_EXHAUSTED'; break
            if pool:
                from .candidate_pool import select_m2
                tested=[x['handoff']['recommended_nominal'] for x in verified.values()]
                selected=select_m2(ledger,initial['problem'],pool,tested,passed)
                if selected is not None:
                    if remaining()['M1_calls']<2:termination='M1_BUDGET_EXHAUSTED_BEFORE_POOL_AUDIT'; break
                    current=audited_handoff(selected,f'pool_{cycle+1:02d}')
                    event('EXISTING_M1_POOL_CANDIDATE_SELECTED',candidate_sha256=selected['parameter_sha256'],
                          selection_rule=selected.get('physics_selection', {}).get('reason',
                              'quality gate, distance from tested candidates, M1 margin'),
                          **({'physics_selection': selected['physics_selection']} if 'physics_selection' in selected else {}))
                    if not current['ready_for_stage9']:termination='NEW_CANDIDATE_RECHECK_FAILED'; break
                    continue
                if len(searches)>=cfg['max_reallocations']:termination='MAX_REALLOCATIONS'; break
            needs_llm = cfg['search']['policy']=='LLM_PHYSICS_TOOL' and not pool
            if needs_llm and remaining()['LLM_calls']<1:termination='LLM_BUDGET_EXHAUSTED'; break
            # Reserve a new candidate audit call plus the next M2 posthoc M1.
            if remaining()['M1_calls']<6:termination='M1_BUDGET_EXHAUSTED_BEFORE_REALLOCATION'; break
            child=deepcopy(cfg['search'])
            # Shared calibration costs were paid in M1 exploration, not called again.
            from .subregion_context import was_formal_call
            shared=sum(was_formal_call(readrow) for readrow in
                [json.loads(s) for s in (context_path.parent/'m1_samples.jsonl').read_text(encoding='utf-8').splitlines()])
            child['total_m1_budget']=min(child['total_m1_budget'],remaining()['M1_calls']-2+shared)
            child['initial_m1_budget']=max(child['initial_m1_budget'],shared)
            if child['total_m1_budget']<=child['initial_m1_budget']+1:
                termination='M1_BUDGET_EXHAUSTED_BEFORE_REALLOCATION'; break
            child['max_round_m1']=min(child['max_round_m1'],child['total_m1_budget']-shared-1)
            if pool:
                child['candidate_pool']['llm_call_limit']=min(pool['llm_call_limit'],remaining()['LLM_calls'])
                child['candidate_pool']['excluded_hashes']=list(verified)
                # A repair seeks a new untested point, not K copies of the
                # candidate that already failed M2. The global pool stays intact.
                child['candidate_pool']['target_count']=1
            elif needs_llm:
                child['max_llm_calls']=min(child['max_llm_calls'],remaining()['LLM_calls'])
                child['max_decisions']=min(child['max_decisions'],child['max_llm_calls'])
            search_dir=root/f'reallocation_{cycle+1:02d}'
            feedback=search_feedback(request,summary)
            event('AGENT_REPLANNING_STARTED',feedback_evidence_id=summary['evidence_id'],search_config=child)
            try:
                result=run_initial_allocation(problem_config,search_dir,config=child,provider_config=provider_config,
                    initial_context=context_path,feedback=feedback,policy=policy)
            except Exception:
                # Initialization/finalization can fail outside the inherited
                # runner's own error boundary. Already paid calls survive.
                samples=search_dir/'executor/m1_samples.jsonl'
                if samples.exists():
                    counts['M1_calls']+=sum(bool(json.loads(s).get('formal_M1_called')) for s in
                        samples.read_text(encoding='utf-8').splitlines() if s.strip())
                for meta in search_dir.glob('round_*/llm_call_*/metadata.json'):
                    counts['LLM_calls']+=bool(read(meta).get('real_network_call'))
                    for k,v in (read(meta).get('usage') or {}).items():
                        if type(v) is int:counts['tokens'][k]=counts['tokens'].get(k,0)+v
                raise
            cost=result['cost']; counts['M1_calls']+=cost['incremental_M1_calls']; counts['LLM_calls']+=cost['LLM_calls']
            if pool:
                for k in ('test_policy_calls','policy_decisions','offline_llm_decisions','deterministic_decisions'):
                    counts[k]=counts.get(k,0)+cost.get(k,0)
                for k in ('conditional_prediction_calls', 'conditional_noise_trial_integrations'):
                    if k in cost:
                        counts[k] = counts.get(k, 0)+cost[k]
            for usage in cost.get('reported_usage',[]):
                for k,v in (usage or {}).items():
                    if type(v) is int:counts['tokens'][k]=counts['tokens'].get(k,0)+v
            searches.append({'path':str(search_dir),'status':result['status'],
                'search_purpose':summary['search_purpose'],
                'failure':result.get('failure'),
                'solver_execution_status':result['solver_execution_status'],
                'cost':cost,'feedback_evidence_id':summary['evidence_id'],
                'accepted_actions':[read(p)['decision'] for p in sorted(search_dir.glob('round_*/search_decision.json'))]})
            require(counts['M1_calls']<=cfg['m1_budget'] and counts['LLM_calls']<=cfg['llm_budget'],'cross-stage hard limit exceeded')
            # Preserve accepted AND rejected proposals with paths to raw provider evidence.
            for p in sorted(search_dir.glob('round_*/proposal_*.json')):
                rejected=p.parent/('validation_error_'+p.stem.split('_')[-1]+'.json')
                append('agent_decisions',{'run_id':run_id,'feedback_evidence_id':summary['evidence_id'],
                    'path':str(p),'raw_decision':read(p),'controller_validation_path':str(p.parent),
                    'validation_status':'REJECTED' if rejected.exists() else 'ACCEPTED',
                    'validation_error':read(rejected) if rejected.exists() else None,
                    'accepted_decision':read(p.parent/'search_decision.json') if not rejected.exists() and
                        (p.parent/'search_decision.json').exists() else None})
            candidates=[]
            for line in (search_dir/'candidate_archive.jsonl').read_text(encoding='utf-8').splitlines():
                row=json.loads(line)
                if applicable(row,initial):
                    row=deepcopy(row)|{'stage9_source_run':str(search_dir),'parent_M2_feedback':summary['evidence_id']}
                    ledger.append(row); append('candidate_archive',row)
                    if row['parameter_sha256'] not in verified and row['source']=='STAGE8B_SEARCH':candidates.append(row)
            requested=result.get('m2_reverification_request')
            if requested:
                sig=fingerprint({'candidate':request['candidate_sha256'],'reason':requested['reason']})
                if sig in reverify_reasons:termination='REPEATED_REVERIFICATION_WITHOUT_NEW_REASON'; break
                reverify_reasons.add(sig); reverify=requested
                continue
            if not candidates:
                termination=result['termination_reason'] if result.get('termination_reason') in (
                    'LLM_PROVIDER_FAILED','INVALID_LLM_DECISION','LLM_CALL_BUDGET_EXHAUSTED') else 'NO_DISTINCT_M1_FEASIBLE_REALLOCATION'
                if pool and result.get('failure'):
                    failure=deepcopy(result['failure'])
                break
            if pool:
                selected=select_m2(candidates,initial['problem'],pool,tested,passed)
                if selected is None:termination='NO_QUALITY_QUALIFIED_REALLOCATION'; break
            else:
                selected=min(candidates,key=rank)
            # Reuse the same budgeted M1 executor for independent selected-point audit.
            ex=RegionExplorer(context_path,root/f'candidate_audit_{cycle+1:02d}',m1_budget=2,reserved_final_calls=1)
            archive=CandidateArchive(ex,ex.root/'candidate_archive.jsonl')
            recheck=ex.recheck_recommendation(selected); counts['M1_calls']+=ex.counts['M1_calls']; ex.close()
            next_handoff=build_handoff(ex,archive,selected,recheck,{'termination_reason':'STAGE9_DISTINCT_CANDIDATE_SELECTION'},ex.cost(), handoff_dir=root)
            write_new(root/f'new_handoff_{cycle+1:02d}.json',next_handoff)
            append('reallocation_candidates',{'run_id':run_id,'parent_candidate_sha256':request['candidate_sha256'],
                'feedback_evidence_id':summary['evidence_id'],'candidate':selected,'recheck':recheck,
                'decision_trace_path':str(search_dir/'SEARCH_DECISION_TRACE.jsonl'),
                'selection_rule':'quality gate and diversity from tested points' if pool else 'best M1 rank among distinct unverified new formal feasible candidates',
                'handoff_sha256':next_handoff['handoff_sha256']})
            if not next_handoff['ready_for_stage9']:termination='NEW_CANDIDATE_RECHECK_FAILED'; break
            current=next_handoff
    except Exception as error:
        termination='CONTROLLER_ERROR'; failure={'type':type(error).__name__,'reason':str(error)}
        event('CONTROLLER_ERROR',failure=failure)
    # Reconcile actual call artifacts even when a finalization step failed.
    disk_m1=sum((p/'posthoc_m1_started.json').exists() for p in root.glob('m2_*') if p.is_dir())
    for pattern in ('reallocation_*/executor/m1_samples.jsonl','candidate_audit_*/m1_samples.jsonl'):
        for path in root.glob(pattern):
            disk_m1+=sum(bool(json.loads(s).get('formal_M1_called')) for s in path.read_text(encoding='utf-8').splitlines() if s.strip())
    counts['recorded_formal_M1_calls']=disk_m1
    if m2_executor is None and disk_m1!=counts['M1_calls']:
        termination='COST_LEDGER_MISMATCH'
        failure={'type':'CostReconciliationError','reason':'M1 ledger differs from persisted formal call evidence'}
    best_m1=min(ledger,key=rank)
    delivered = passing_candidates()
    delivered_keys = {r['parameter_sha256'] for r in delivered}
    eligible=[x for k,x in verified.items() if k in delivered_keys]
    best_m2=min(eligible,key=lambda x:rank(x['handoff']['recommended_nominal']),default=None)
    counts.update(wall_time_s=time.perf_counter()-start,shared_Stage7_M1_cost='historical, no repeated calibration',
                  M1_limit=cfg['m1_budget'],M2_limit=cfg['m2_budget'],LLM_limit=cfg['llm_budget'])
    changed=any(a['candidate_sha256']!=b['candidate_sha256'] for a,b in zip(history,history[1:]))
    result={'schema_version':'pll-stage9-result-1.0','status':termination,'strategy':'stage9_existing_physics_tool_feedback',
        'execution_route':'CONTINUOUS_VERIFICATION',
        'actual_execution':{'M2_executor':'TEST_INJECTED' if m2_executor is not None else 'NATIVE',
            'M2_executed':counts['M2_verifications']>0, 'real_LLM_calls':counts['LLM_calls'],
            'policy_injected':policy is not None, 'configured_mode':pool['mode'] if pool else cfg['search']['policy']},
        'run_id':run_id,'problem_sha256':initial['problem_sha256'],'M1_model_fingerprint':initial['model_fingerprint'],
        'initial_handoff_sha256':initial['handoff_sha256'],
        'termination_reason':termination,'mode':mode,'m1_allocation_status':'KNOWN_FEASIBLE_PRESERVED',
        'M2_status':best_m2['observation']['overall_status'] if best_m2 else history[-1]['M2_status'] if history else 'NOT_EVALUATED',
        'supported_M2_status':'PASS' if best_m2 else history[-1]['supported_metrics_status'] if history else 'NOT_EVALUATED',
        'feedback_loop_status':'REALLOCATION_REVERIFIED' if changed else 'SAME_CANDIDATE_REVERIFIED' if len(history)>1 else
            'FEEDBACK_SEARCH_ATTEMPTED' if searches else 'NOT_REPLANNED',
        'real_fail_reverification_completed':len(history)>1 and history[0]['M2_status']=='FAIL' and
            history[0]['candidate_sha256']!=history[1]['candidate_sha256'] and mode!='TEST_INJECTED_NOT_RESEARCH' and bool(searches),
        'solver_execution_status':[x['solver_execution_status'] for x in searches],
        'best_known_M1':best_m1,'recommended_M2_supported':best_m2['handoff']['recommended_nominal'] if best_m2 else None,
        'm2_target_count':cfg['m2_target_count'], 'joint_pass_count':len(delivered),
        'joint_target_reached':len(delivered) >= cfg['m2_target_count'],
        'time_to_first_joint_s':next((x['elapsed_s'] for x in history if x['joint_pass_count']), None),
        'time_to_joint_target_s':next((x['elapsed_s'] for x in history
                                      if x['joint_pass_count'] >= cfg['m2_target_count']), None),
        'verified_history':history,'searches':searches,'cost':counts,'failure':failure,'FULL_SYSTEMSPEC_CERTIFIED':False}
    write_new(root/'stage9_cost_summary.json',counts); write_new(root/'stage9_final_result.json',result)
    write_new(root/'cost_summary.json',counts)
    write_new(root/'verification_result.json',result)
    report=['# Behavioral verification and feedback',f'Mode: {mode}',f'Termination: {termination}',
        f'M1: {result["m1_allocation_status"]}; M2 supported subset: {result["supported_M2_status"]}; full M2: {result["M2_status"]}',
        f'Real FAIL -> reallocation -> reverification: {result["real_fail_reverification_completed"]}',
        'M2 PM/Jitter remain UNKNOWN. M1 feasibility does not overwrite M2 FAIL.',
        '```json',json.dumps(history,ensure_ascii=False,indent=2),'```','## Costs','```json',json.dumps(counts,indent=2),'```']
    (root/'stage9_report.md').write_text('\n\n'.join(report)+'\n',encoding='utf-8')
    (root/'feedback_report.md').write_text('\n\n'.join(report)+'\n',encoding='utf-8')
    event('RUN_COMPLETED',termination_reason=termination,cost=counts)
    (root/'verification_run_events.jsonl').write_bytes(paths['stage9_run_events'].read_bytes())
    return result


def run_stage9_feedback(handoff_path, out, *, problem_config, stage9_config,
                        provider_config=None, policy=None, m2_executor=None):
    """Compatibility call for existing clients; use run_feedback in new code."""
    return run_feedback(handoff_path, out, problem_config=problem_config,
        feedback_config=stage9_config, provider_config=provider_config,
        policy=policy, m2_executor=m2_executor)
