"""Read-only evidence aggregation; never executes a policy or simulator."""
from pathlib import Path
import argparse
import csv
import json
import sys
from collections import Counter

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from pll_allocation.allocation.core import read,write_new
from pll_allocation.pipeline_contracts import check_result,load_inputs
from pll_allocation.physics_mapping.model import fingerprint


def export_csv(path,rows):
    keys=list(dict.fromkeys(k for row in rows for k in row))
    with path.open('x',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=keys);writer.writeheader();writer.writerows(rows)


def collect(first,repair,local,out):
    out.mkdir(parents=True,exist_ok=False);(out/'metric_evaluations').mkdir()
    rows=[];costs=[];traces=[];arm_summaries=[];first_summaries={}
    all_jobs=[('FIRST_SHOT',job) for job in read(first/'complete.json')['jobs']]
    all_jobs += [('FEEDBACK_REPAIR',job) for job in read(repair/'complete.json')['jobs']]
    for phase,job in all_jobs:
        folder=Path(job['directory']);result=read(folder/'result.json');manifest=read(folder/'run_manifest.json')
        binding=result['scenario_binding'];arm=job['arm']; scene=binding['scenario_id']
        runner_events=[json.loads(line) for line in (folder/'allocation_trace.jsonl').read_text(encoding='utf-8').splitlines()]
        strategy=job.get('original_strategy',result['strategy'])
        lineage_manifest=read(Path(job['parent'])/'run_manifest.json') if phase=='FEEDBACK_REPAIR' else manifest
        seed=lineage_manifest['seed'] if strategy=='random' else None
        run_cost={**result['cost'],'arm':arm,'phase':phase,'scenario_id':scene,'strategy':strategy,
            'process_wall_s':job['receipt']['process_wall_s'],'result_path':str(folder/'result.json')}
        events=read(folder/'cost_events.json')
        run_cost['numerical_inverse_root_calls']=sum(e['kind']=='analytic_calls' and isinstance(e.get('input'),list)
            and len(e['input'])==2 and all(type(x) in (int,float) for x in e['input']) for e in events)
        solver_runs=[]
        def solver_records(obj):
            if isinstance(obj,dict):
                for key,value in obj.items():
                    if key=='solver_runs' and isinstance(value,list):solver_runs.extend(x for x in value if 'iterations' in x)
                    else:solver_records(value)
            elif isinstance(obj,list):
                for value in obj:solver_records(value)
        for path in sorted(folder.glob('attempt_*/allocation_metadata.json')):solver_records(read(path))
        # The same metadata may be nested twice; exact records identify one actual solve.
        run_cost['SLSQP_invocations']=len({fingerprint(record) for record in solver_runs})
        costs.append(run_cost)
        summary={'arm':arm,'scenario':scene,'phase':phase,'strategy':strategy,'seed':seed,'status':result['status'],
            'M1_first_feasible':None,'BW_first_status':'NOT_EVALUATED','supported_metrics':[],
            'M2_calls_to_first_BW_subset_pass':None,'LLM_status':result.get('LLM_allocation_status','NOT_APPLICABLE')}
        if not result['attempts']:
            rows.append({'arm':arm,'phase':phase,'scenario_id':scene,'scenario_sha256':binding['scenario_sha256'],
                'strategy':strategy,'seed':seed,'candidate_index':0,'run_status':result['status'],
                'm1_status':'NOT_EVALUATED','m2_status':'NOT_EVALUATED','full_systemspec':'NOT_VERIFIED',
                'evidence':str(folder/'result.json')})
        for index,attempt in enumerate(result['attempts'],1):
            p=folder/attempt['directory'];item=read(p/'AllocationProposal.json');assessment=read(p/'M1_prediction.json')
            prediction=(assessment.get('prediction') or {}).get('metrics',{})
            domain=read(p/'constraint_checks.json');measured=read(p/'BehavioralVerificationResult.json') if (p/'BehavioralVerificationResult.json').exists() else None
            if measured:check_result(measured,item,load_inputs()[3])
            checks={c['metric']:c for c in measured.get('constraints',[])} if measured else {}
            metrics=measured.get('metrics',{}) if measured else {};bw=metrics.get('BW_Hz',{})
            bwstatus=checks.get('BW_Hz',{}).get('status','NOT_EVALUATED')
            m1ok=assessment['judgment']['verdict']=='M1_SPEC_PASS'
            supported=['BW_Hz'] if bw.get('status')=='MEASURED_CONVERGED' else []
            subset='M2_MEASURED_SUBSET_PASS' if supported and bwstatus=='PASS' else 'M2_MEASURED_SUBSET_FAIL' if bwstatus=='FAIL' else 'M2_MEASURED_SUBSET_UNKNOWN'
            if summary['M2_calls_to_first_BW_subset_pass'] is None and bwstatus=='PASS':
                summary['M2_calls_to_first_BW_subset_pass']=index+(1 if phase=='FEEDBACK_REPAIR' else 0)
            if index==1:
                summary.update(M1_first_feasible=m1ok,BW_first_status=bwstatus,supported_metrics=supported,
                    parameter_sha256=item['parameter_sha256'])
            params={k:v['value'] for k,v in item['joint_block_spec']['values'].items()}
            bwvalue=bw.get('value');m1bw=prediction.get('BW_Hz')
            row={'arm':arm,'phase':phase,'scenario_id':scene,'scenario_sha256':binding['scenario_sha256'],
                'effective_spec_sha256':binding['effective_system_spec_sha256'],'strategy':strategy,'seed':seed,
                'candidate_index':index,'parameter_sha256':item['parameter_sha256'],
                **{k:params[k] for k in ('Icp','Rz','C1','C2','f0','Kvco')},
                'declared_domain':domain['declared_domain'],'model_validity':domain['model_validity'],
                'Vctrl_required_V':domain['derived'].get('Vctrl_required_V'),
                'BW_requirement_min_Hz':next(x['min'] for x in item['system_spec']['metrics'] if x['metric']=='BW_Hz'),
                'BW_requirement_max_Hz':next(x['max'] for x in item['system_spec']['metrics'] if x['metric']=='BW_Hz'),
                'PM_requirement_min_deg':next(x['min'] for x in item['system_spec']['metrics'] if x['metric']=='PM_deg'),
                'm1_status':assessment['judgment']['verdict'],'M1_feasibility_label':'M1_PREDICTED_FEASIBLE' if m1ok else 'M1_NOT_PREDICTED_FEASIBLE',
                'BW_M1_Hz':m1bw,'UGF_M1_Hz':prediction.get('UGF_Hz'),'PM_M1_deg':prediction.get('PM_deg'),
                'output_frequency_M1_Hz':prediction.get('output_frequency_Hz'),
                'M1_normalized_margins':json.dumps(item.get('constraint_margins'),separators=(',',':')),
                'BW_M2_Hz':bwvalue,'BW_M2_interval_Hz':json.dumps(bw.get('numerical_envelope')),
                'BW_measurement_validity':bw.get('status','NOT_MEASURED'),'BW_spec_status':bwstatus,
                'BW_error_Hz':bwvalue-m1bw if bwvalue is not None and m1bw else None,
                'BW_error_percent':100*(bwvalue/m1bw-1) if bwvalue is not None and m1bw else None,
                'capture':metrics.get('capture',{}).get('value'),
                'output_frequency_M2_Hz':metrics.get('output_frequency_Hz',{}).get('value'),
                'output_frequency_spec_status':checks.get('output_frequency_Hz',{}).get('status','NOT_EVALUATED'),
                'PM_M2_deg':metrics.get('PM_deg',{}).get('value'),'PM_spec_status':checks.get('PM_deg',{}).get('status','NOT_EVALUATED'),
                'measured_hard_metric_subset':json.dumps(supported),'M2_subset_label':subset,
                'full_systemspec':measured.get('overall_status') if measured else 'NOT_VERIFIED',
                'local_mapping_evidence':'NEW_PREDECLARED_SUITE' if phase=='FIRST_SHOT' and strategy=='analytical' and scene in ('S0','S3') else 'NOT_MEASURED_THIS_ROUND',
                'generation_elapsed_s':next((e['generation_elapsed_s'] for e in runner_events if e['event']=='SUBMISSION_SAVED' and e.get('parameter_sha256')==item['parameter_sha256']),None),
                'first_shot_kind':attempt.get('first_shot_kind'),
                'submission_formal_M1_calls':int(assessment.get('prediction') is not None),
                'M2_complete_verification_calls':int(measured is not None),
                'run_M1_search_and_submission_calls':result['cost']['M1_calls'],
                'run_M1_posthoc_calls':result['cost']['M1_posthoc_calls'],
                'run_LLM_calls':result['cost']['LLM_calls'],
                'evidence':str(p/'BehavioralVerificationResult.json' if measured else p/'constraint_checks.json')}
            rows.append(row)
            per_metric=[]
            for req in item['system_spec']['metrics']:
                name=req['metric'];observed=metrics.get(name,{})
                per_metric.append({'requirement':req,'M1_prediction':prediction.get(name),
                    'M2_measurement':observed,'measurement_validity':observed.get('status','NOT_MEASURED'),
                    'status':checks.get(name,{}).get('status','UNKNOWN'),'error':measured.get('prediction_errors',{}).get(name) if measured else None,
                    'evidence':row['evidence'],'scenario_binding':binding})
            write_new(out/'metric_evaluations'/f'{arm}__{phase}__{index}.json',per_metric)
        for filename,kind in [('allocation_trace.jsonl','RUNNER_EVENT')]:
            for line in (folder/filename).read_text(encoding='utf-8').splitlines():
                traces.append({'arm':arm,'phase':phase,'kind':kind,'scenario_binding':binding,'source':str(folder/filename),'data':json.loads(line)})
        for path in sorted(folder.glob('attempt_*/agent_trace.jsonl')):
            for line in path.read_text(encoding='utf-8').splitlines():
                traces.append({'arm':arm,'phase':phase,'kind':'AGENT_TOOL','scenario_binding':binding,'source':str(path),'data':json.loads(line)})
        for event in events:
            traces.append({'arm':arm,'phase':phase,'kind':'COST_EVENT','scenario_binding':binding,'data':event})
        for path in sorted(folder.glob('attempt_*/llm_calls/call_*/metadata.json')):
            traces.append({'arm':arm,'phase':phase,'kind':'LLM_API','scenario_binding':binding,'source':str(path),'data':read(path)})
        arm_summaries.append(summary)
        if phase=='FIRST_SHOT':first_summaries[arm]=summary
    export_csv(out/'scenario_results.csv',rows);export_csv(out/'run_costs.csv',costs)
    with (out/'candidate_trace.jsonl').open('x',encoding='utf-8') as f:
        for trace in traces:f.write(json.dumps(trace,ensure_ascii=False,allow_nan=False)+'\n')
    local_summary=[]
    local_complete=read(local/'complete.json')
    for job in local_complete['jobs']:
        sid=job['scenario'];case=Path(job['directory']);runs=read(case/'frequency_result.json');gate=read(case/'frequency_gate.json');step=read(case/'steps/result.json')
        local_summary.append({'scenario':sid,'parameter_sha256':read(case/'AllocationProposal.json')['parameter_sha256'],
            'series':runs['base']['crossing'],'clamp':runs['independent_clamp']['crossing'],
            'frequency_gate':gate,'step_status':step['status'],'step_base':step.get('results',{}).get('plus'),
            'convergence':step.get('convergence'),'formal_PM':'UNKNOWN','evidence':str(case)})
    totals={k:sum(c.get(k,0) for c in costs) for k in ('M2_calls','M1_calls','M1_posthoc_calls','analytic_calls','LLM_calls',
        'candidate_generations','numerical_inverse_root_calls','SLSQP_invocations','native_completed_runs','native_failed_attempts','integration_points','native_elapsed_s','total_elapsed_s','process_wall_s')}
    llm=[]
    for trace in traces:
        if trace['kind']=='LLM_API':llm.append(trace['data'])
    usage=Counter()
    for call in llm:
        for k,v in (call.get('usage') or {}).items():
            if type(v) in (int,float):usage[k]+=v
    summary={'arm_summaries':arm_summaries,'local_evidence':local_summary,'totals':totals,
        'local_phase_cost':local_complete,'firstshot_phase_wall_s':read(first/'complete.json')['process_wall_s'],
        'repair_phase_wall_s':read(repair/'complete.json')['process_wall_s'],
        'LLM_usage':dict(usage),'LLM_API_statuses':dict(Counter(c.get('status') for c in llm)),
        'candidate_rows':len(rows),'trace_events':len(traces),'unique_candidate_hashes':len({r['parameter_sha256'] for r in rows if r.get('parameter_sha256')}),
        'full_verified_pass_count':sum(r.get('full_systemspec')=='PASS' for r in rows),
        'missing_local_suite':'explicit NOT_MEASURED_THIS_ROUND on other rows; not periodic PM certification',
        'monetary_cost':None,'monetary_cost_reason':'No configured audited per-token price; token/time counts retained'}
    failed_local=ROOT/'experiments/stage5/local_receipt_01/execution.json'
    if failed_local.exists():summary['local_prior_bookkeeping_failure_execution']=read(failed_local)
    write_new(out/'summary.json',summary)
    print(json.dumps({'totals':totals,'rows':len(rows),'unique_candidates':summary['unique_candidate_hashes']},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--firstshot',required=True,type=Path);p.add_argument('--repair',required=True,type=Path)
    p.add_argument('--local',required=True,type=Path);p.add_argument('--out',required=True,type=Path);a=p.parse_args()
    collect(a.firstshot,a.repair,a.local,a.out)
