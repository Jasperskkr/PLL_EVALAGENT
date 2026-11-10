"""Read-only evidence checks and new summary output; never executes a TB."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from pll_allocation.allocation.core import read,write_new,values
from pll_allocation.physics_mapping.model import fingerprint


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def check_chain(path):
    previous='0'*64;count=0
    for line in path.read_text(encoding='utf-8').splitlines():
        event=json.loads(line);digest=event.pop('event_sha256');count+=1
        if event['previous_sha256']!=previous or fingerprint(event)!=digest or event['index']!=count:
            raise ValueError('TRACE_CHAIN_BROKEN:'+str(path))
        previous=digest
    return {'path':path.relative_to(ROOT).as_posix(),'events':count,'final_sha256':previous,'sha256':sha(path)}


def audit(study,out):
    out.mkdir(parents=True,exist_ok=False);rows=[];traces=[];native=[];cache_entries=[]
    for scenario in ('B1','B2'):
        for method in ('A','B','C'):
            folder=study/'runs'/(scenario+'_'+method);result=read(folder/'result.json')
            trace=check_chain(folder/'allocation_trace.jsonl');traces.append(trace)
            assert trace['final_sha256']==result['trace_final_sha256']
            assert result['cost']['M2_candidate_slots_used']<=6 and result['cost']['M1_calls']<=96 and result['cost']['analytic_calls']<=10000
            assert result['status']!='PIPELINE_ERROR' and not result['FULL_SYSTEMSPEC_CERTIFIED'] and result['LLM_calls']==0
            for attempt in result['attempts']:
                candidate=folder/attempt['directory'];record=read(candidate/'proposal.json');v=values(record['candidate'])
                e=attempt['evaluation'];by={r['metric_name']:r for r in e['constraints']};m1=attempt['M1_metrics'];m2=attempt['M2_metrics']
                ref=read(candidate/'M2_evidence_reference.json');origin=ROOT/ref['child_path']
                entry=read(ROOT/ref['cache_entry'])
                assert entry['cache_key']==ref['cache_key']
                for artifact in entry['artifacts']:
                    p=origin/artifact['path'];assert p.is_file() and sha(p)==artifact['sha256']
                cache_entries.append(ref['cache_entry'])
                assert e['parameter_sha256']==fingerprint(record['candidate'])
                assert e['research_joint_status']!='RESEARCH_JOINT_FEASIBLE' or all(r['verification_status']=='PASS' for r in e['constraints'])
                rows.append({'scenario':scenario,'method':method,'candidate_slot':attempt['candidate_slot'],
                    'candidate_sha256':attempt['parameter_sha256'],'reason':attempt['reason'],'cache_hit':attempt['cache_hit'],
                    'final_selected':attempt['parameter_sha256']==result['final_parameter_sha256'],
                    **{k:v[k] for k in ('Icp','Rz','C1','C2','f0','Kvco')},
                    'M1_BW_Hz':m1['BW_Hz'],'M1_PM_deg':m1['PM_deg'],'M1_UGF_Hz':m1['UGF_Hz'],
                    'Vreq_V':m1['Vctrl_required_V'],'M2_BW_Hz':m2['BW_Hz']['value'],
                    'BW_prediction_error_pct':100*(m2['BW_Hz']['value']/m1['BW_Hz']-1) if m2['BW_Hz']['value'] else None,
                    'BW_envelope_Hz':by['BW_Hz']['numerical_envelope'],
                    'capture_time_s':m2['lock_time_s']['value'],'capture_envelope_s':by['lock_time_s']['numerical_envelope'],
                    'minimum_normalized_margin':e['minimum_normalized_margin'],'PM_margin_deg':by['PM_deg']['margin'],
                    'constraint_status':{k:r['verification_status'] for k,r in by.items()},
                    'joint_status':e['research_joint_status'],'original_M2_status':e['original_M2_status']})
            for p in folder.rglob('summary.json'):
                item=read(p)
                if 'summary' in item and 'integration_points' in item['summary']:native.append(item['summary'])
    costs={s+'_'+m:read(study/'runs'/(s+'_'+m)/'result.json')['cost'] for s in ('B1','B2') for m in ('A','B','C')}
    summary={'research_scope':'M1 PM/tuning + independent M2 BW/conditional capture; no full certification',
        'candidate_slots':sum(c['M2_candidate_slots_used'] for c in costs.values()),
        'new_complete_M2_calls':sum(c['M2_calls'] for c in costs.values()),
        'cache_hits':sum(c['cache_hits'] for c in costs.values()),'M1_calls':sum(c['M1_calls'] for c in costs.values()),
        'cheap_calls':sum(c['analytic_calls'] for c in costs.values()),
        'native_completed_runs':sum(c['native_completed_runs'] for c in costs.values()),
        'native_failed_attempts':sum(c['native_failed_attempts'] for c in costs.values()),
        'native_elapsed_s':sum(c['native_elapsed_s'] for c in costs.values()),
        'total_method_wall_s':sum(c['total_elapsed_s'] for c in costs.values()),'LLM_calls':0,
        'research_feasible_slots':sum(r['joint_status']=='RESEARCH_JOINT_FEASIBLE' for r in rows),
        'cost_by_run':costs,'trace_checks':traces,'cache_entries_verified':len(set(cache_entries))}
    assert len(native)==summary['native_completed_runs']
    write_new(out/'candidates.json',rows);write_new(out/'summary.json',summary)
    import csv
    with (out/'candidates.csv').open('x',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader()
        writer.writerows({k:json.dumps(v) if isinstance(v,(dict,list)) else v for k,v in row.items()} for row in rows)
    # Consolidated index is constructed from preserved receipts, not retroactive realtime events.
    chain='0'*64;events=[]
    for path in sorted((ROOT/'experiments/stage6b').rglob('*')):
        if not path.is_file() or path.is_relative_to(out) or 'tmp' in path.parts:continue
        if path.name not in ('receipt.json','plan.json','tests.xml','allocation_trace.jsonl','run_manifest.json','result.json'):continue
        event={'index':len(events)+1,'event':'PRESERVED_ARTIFACT_INDEXED','recorded_at':datetime.now(timezone.utc).isoformat(),
            'provenance':'CONSOLIDATED_INDEX; original timestamp/event preserved in artifact',
            'artifact':path.relative_to(ROOT).as_posix(),'sha256':sha(path),'bytes':path.stat().st_size,'previous_sha256':chain}
        event['event_sha256']=fingerprint(event);chain=event['event_sha256'];events.append(event)
    with (out/'full_process_trace.jsonl').open('x',encoding='utf-8') as stream:
        for event in events:stream.write(json.dumps(event,ensure_ascii=False)+'\n')
    write_new(out/'trace_index.json',{'provenance':'reconstructed artifact index + original real-time search/native traces',
        'index_events':len(events),'index_final_sha256':chain,'method_traces':traces,
        'coverage':['safe snapshot','design','build/compiler failures and success','pretests and failed devtests',
            'frozen plan','all M1/cheap costs','pre-TB submissions','M2 raw/native requests and measured summaries',
            'cache origin','feedback/search/incumbent/stops','source protection','packaging separately in release receipt'],
        'not_recorded':'wall-clock timestamps of every author edit/tool invocation before trace setup; no fabricated historical events'})
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--study',required=True);parser.add_argument('--out',required=True)
    a=parser.parse_args();print(json.dumps(audit(Path(a.study).resolve(),Path(a.out).resolve()),ensure_ascii=False,indent=2))
