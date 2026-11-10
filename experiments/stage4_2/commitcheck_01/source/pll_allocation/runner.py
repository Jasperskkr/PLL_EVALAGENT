"""Deterministic safety/acceptance sequence with injected proposal policy and TB."""
from __future__ import annotations
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import platform
import time
from .contracts import build_problem, check_candidate, digest, canonical
from .behavioral import PythonBehavioralBackend, MetricVerifier, screen, write_json, PHYSICS
from .policies import ServiceUnavailable

def diagnosis(p,attempt):
    judgement=attempt.get('judgement',{})
    return {'violations':[c for c in judgement.get('checks',[]) if c['status']!='PASS'],
            'satisfied':[c for c in judgement.get('checks',[]) if c['status']=='PASS'],
            'model_issues':judgement.get('issues',[]), 'constraint_errors':attempt['constraint_check']['errors'],
            'physical_relations':PHYSICS,'sensitivity_evidence':'ANALYTIC_RELATIONS_ONLY; no uncharged finite-difference TB calls',
            'repair_decision_owner':'allocation_policy'}

def source_snapshot():
    root=Path(__file__).resolve().parent
    return {str(f.relative_to(root)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(root.rglob('*.py'))}

def run(problem,policy,out,*,budget=30,max_attempts=None,backend=None,verifier=None):
    p=build_problem(problem)
    if type(budget) is not int or not 1<=budget<=10000: raise ValueError('bounded positive evaluation budget required')
    max_attempts=budget if max_attempts is None else max_attempts
    if type(max_attempts) is not int or not 1<=max_attempts<=10000: raise ValueError('bounded positive attempt budget required')
    output=Path(out).resolve()
    # Reject even empty existing directories: the caller owns one unique run directory.
    output.mkdir(parents=True,exist_ok=False)
    backend=backend or PythonBehavioralBackend(); verifier=verifier or MetricVerifier()
    write_json(output/'input_system_spec.json',p)
    write_json(output/'block_space_snapshot.json',p['block_space'])
    write_json(output/'topology_snapshot.json',p['topology'])
    capabilities=backend.capabilities()
    write_json(output/'backend_capabilities.json',capabilities)
    unsupported=[s['metric'] for s in p['system_spec'] if capabilities.get('metrics',{}).get(s['metric']) !=
                 {'unit':s['unit'],'measurement':s['measurement']}]
    fingerprint=digest(p); sources=source_snapshot(); start=time.perf_counter()
    history=[]; evaluations=0; final=None; status='BUDGET_EXHAUSTED'; reason=None
    policy_time=0.; previous='0'*64
    for sequence in range(1,max_attempts+1):
        if evaluations>=budget: break
        remaining={'behavioral_evaluations':budget-evaluations,'proposal_attempts':max_attempts-sequence+1}
        before=time.perf_counter()
        try:
            proposal=policy.propose(deepcopy(p),deepcopy(history),remaining)
        except ServiceUnavailable as error:
            status='POLICY_UNAVAILABLE'; reason=str(error); break
        finally:
            policy_time+=time.perf_counter()-before
        if proposal is None:
            status='POLICY_STOPPED'; break
        candidate=proposal['candidate']
        attempt_dir=output/'attempts'/f'{sequence:03d}'; attempt_dir.mkdir(parents=True,exist_ok=False)
        # Write the actual first proposal before any screening or TB invocation.
        write_json(attempt_dir/'proposal.json',proposal)
        if sequence==1: write_json(output/'initial_joint_block_spec.json',candidate)
        check=check_candidate(p,candidate)
        attempt={'schema_version':'allocation-attempt-1.0','sequence':sequence,'candidate':candidate,
                 'candidate_sha256':digest(candidate),'proposal_source':policy.policy_id,
                 'rationale':proposal.get('rationale',''),'constraint_check':check,
                 'evaluation_index':None,'prediction':None,'judgement':None,'metric_prediction_error':None,
                 'cost':{'behavioral_evaluations':0},'artifacts':str(attempt_dir.relative_to(output))}
        if check['status']=='VALID':
            attempt['prediction']=screen(p,candidate)
            write_json(attempt_dir/'prediction.json',attempt['prediction'])
            evaluations+=1; attempt['evaluation_index']=evaluations
            tb_start=time.perf_counter()
            try:
                measured=backend.run(deepcopy(p),deepcopy(candidate),attempt_dir)
                if measured.get('backend_id') != backend.backend_id:
                    raise ValueError('backend identity mismatch')
                judgement=verifier.judge(p,candidate,measured)
                if unsupported:
                    judgement['verdict']='UNKNOWN'
                    judgement.setdefault('issues',[]).append('UNSUPPORTED_BY_BACKEND:'+','.join(unsupported))
                    for item in judgement.get('checks',[]):
                        if item['metric'] in unsupported: item['status']='UNSUPPORTED'
            except Exception as error:
                measured={'schema_version':'behavioral-evaluation-1.0','backend_id':backend.backend_id,
                          'completed':False,'metrics':{},'error_type':type(error).__name__,'cost':{'behavioral_evaluations':1}}
                judgement={'verdict':'UNKNOWN','checks':[],'issues':['TB_EXCEPTION:'+type(error).__name__],
                           'minimum_normalized_margin':None,'constraint_violation':None}
            attempt['judgement']=judgement
            attempt['cost']={'behavioral_evaluations':1,'elapsed_s':time.perf_counter()-tb_start}
            attempt['cost']['external_calls']=measured.get('cost',{}).get('external_calls',capabilities.get('external_calls_per_evaluation'))
            attempt['measured_metrics']=measured.get('metrics',{})
            errors={}
            for name,predicted in attempt['prediction']['metrics'].items():
                actual=measured.get('metrics',{}).get(name)
                if type(actual) in (int,float): errors[name]=actual-predicted
            attempt['metric_prediction_error']=errors
            write_json(attempt_dir/'behavioral_result.json',measured)
        else:
            attempt['judgement']={'verdict':'INVALID','checks':[],'issues':check['errors'],
                                  'minimum_normalized_margin':None,'constraint_violation':None}
        attempt['diagnosis']=diagnosis(p,attempt)
        history.append(attempt)
        event={'sequence':sequence,'attempt':attempt,'previous_sha256':previous}
        previous=digest(event); event['event_sha256']=previous
        with (output/'allocation_trace.jsonl').open('a',encoding='utf-8') as f:
            f.write(canonical(event)+'\n')
        write_json(attempt_dir/'attempt.json',attempt)
        if digest(p)!=fingerprint or source_snapshot()!=sources:
            raise RuntimeError('frozen input or source changed during run')
        if attempt['judgement']['verdict']=='PASS':
            final=attempt; status='VERIFIED_BEHAVIORAL_PASS'; break
        if unsupported and attempt['evaluation_index'] is not None:
            status='UNSUPPORTED_SYSTEM_SPEC'; reason='Unsupported measurements: '+','.join(unsupported); break
    first=history[0] if history else None
    # Selection remains diagnostic on failure; no failed candidate is called verified.
    selected=final or next((a for a in reversed(history) if a['evaluation_index'] is not None),None)
    if selected: write_json(output/'final_joint_block_spec.json',selected['candidate'])
    write_json(output/'constraint_checks.json',[a['constraint_check'] for a in history])
    write_json(output/'behavioral_tb_results.json',[{'sequence':a['sequence'],'verdict':a['judgement'],
               'measured_metrics':a.get('measured_metrics',{}),'artifacts':a['artifacts']} for a in history])
    metrics={'first_pass_feasible':bool(first and first['judgement']['verdict']=='PASS'),
             'evaluations_to_first_feasible':final['evaluation_index'] if final else None,
             'success_within_budget':final is not None,'behavioral_evaluations':evaluations,'proposal_attempts':len(history),
             'minimum_normalized_margin':selected['judgement']['minimum_normalized_margin'] if selected else None,
             'constraint_violation':selected['judgement']['constraint_violation'] if selected else None,
             'predicted_vs_verified_metric_error':selected['metric_prediction_error'] if selected else None,
             'strategy_runtime_s':policy_time,'evaluation_runtime_s':sum(a['cost'].get('elapsed_s',0) for a in history),
             'llm_calls':len(getattr(policy,'calls',[])), 'scope':'DECLARED_BEHAVIORAL_MODEL_ONLY'}
    write_json(output/'system_metrics.json',metrics)
    manifest={'schema_version':'allocation-result-1.0','status':status,'reason':reason,'task_id':p['task_id'],
              'policy_id':policy.policy_id,'backend_id':backend.backend_id,'input_sha256':fingerprint,
              'source_sha256':sources,'trace_head_sha256':previous,
              'decision_sha256':digest([{'candidate':a['candidate'],'judgement':a['judgement'],
                                        'measured_metrics':a.get('measured_metrics',{})} for a in history]),
              'evaluation_budget':budget,'attempt_budget':max_attempts,
              'final_candidate_sha256':selected['candidate_sha256'] if selected else None,
              'final_candidate_verified':final is not None,'environment':{'python':platform.python_version(),'platform':platform.platform()},
              'created_at':datetime.now().astimezone().isoformat(),'runtime_s':time.perf_counter()-start,
              'llm_calls':getattr(policy,'calls',[]),
              'external_calls':{name:sum(a['cost'].get('external_calls',{}).get(name,0) for a in history)
                                if all(a['cost'].get('external_calls') is not None for a in history if a['evaluation_index'] is not None)
                                else 'UNKNOWN' for name in ('MATLAB','ngspice')},
              'independent_physical_qualification':'UNKNOWN','metrics':metrics}
    write_json(output/'run_manifest.json',manifest)
    lines=[f'# {p["task_id"]}',f'状态：{status}。范围：声明行为模型。独立物理资格：UNKNOWN。',
           f'策略：{policy.policy_id}；TB：{backend.backend_id}。',
           f'首次通过：{metrics["first_pass_feasible"]}；实际完整行为评价：{evaluations}/{budget}；提议：{len(history)}。',
           f'首次可行评价序号：{metrics["evaluations_to_first_feasible"]}；真实LLM请求：{metrics["llm_calls"]}。',
           '最终规格见 final_joint_block_spec.json；首次规格见 initial_joint_block_spec.json；逐轮理由、违例和修复见 allocation_trace.jsonl。']
    if selected:
        lines.extend(['','|指标|TB测量|目标|判决|','|---|---|---|---|'])
        lines.extend(f'|{c["metric"]}|{c["actual"]}|{c["operator"]} {c["target"]} {c["unit"]}|{c["status"]}|' for c in selected['judgement']['checks'])
    if reason: lines.append('原因：'+reason)
    (output/'report.md').write_text('\n\n'.join(lines)+'\n',encoding='utf-8')
    return manifest
