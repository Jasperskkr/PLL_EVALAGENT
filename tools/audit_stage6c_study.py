"""Summarize real six-arm pipeline evidence; no re-execution or claim inflation."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from pll_allocation.allocation.core import write_new
from pll_allocation.physics_mapping.model import fingerprint


def audit(study,out):
    study=Path(study).resolve();out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False);rows=[]
    for path in sorted((study/'runs').glob('*/result.json')):
        result=json.loads(path.read_text(encoding='utf-8'));name=path.parent.name
        events=[json.loads(line) for line in (path.parent/'allocation_trace.jsonl').read_text(encoding='utf-8').splitlines()]
        prev='0'*64
        for index,event in enumerate(events,1):
            actual=event['event_sha256'];raw={k:v for k,v in event.items() if k!='event_sha256'}
            if event['index']!=index or event['previous_sha256']!=prev or fingerprint(raw)!=actual:raise ValueError('trace chain mismatch:'+name)
            prev=actual
        if result['trace_final_sha256']!=prev:raise ValueError('result trace mismatch')
        for attempt in result['attempts']:
            folder=path.parent/attempt['directory']
            for rule in attempt['evaluation']['constraints']:
                if not (folder/rule['evidence_path']).is_file():raise ValueError('missing row evidence:'+str(folder/rule['evidence_path']))
        first=result['first_shot'];final=result['final_evaluation'];lastsha=result['final_parameter_sha256']
        last=next((a for a in result['attempts'] if a['parameter_sha256']==lastsha),None)
        def vals(e):
            return {r['metric_name']:dict(value=r['measured_or_predicted_value'],status=r['verification_status'],
                interval=r.get('statistical_interval') if r['metric_name']=='integrated_jitter_s' else r['numerical_envelope'],
                normalized_margin=r['normalized_margin']) for r in e['constraints']} if e else {}
        rows.append(dict(run=name,status=result['status'],first_status=first['evaluation']['research_joint_status'] if first else None,
            final_status=final['research_joint_status'] if final else None,first_parameters=first['parameter_sha256'] if first else None,
            final_parameters=lastsha,first_metrics=vals(first['evaluation']) if first else {},final_metrics=vals(final),
            first_margin=first['evaluation']['minimum_normalized_margin'] if first else None,
            final_margin=final['minimum_normalized_margin'] if final else None,cost=result['cost'],
            first_M1_jitter_s=first.get('M1_noise',{}).get('integrated_jitter_s') if first else None,
            final_M1_jitter_s=last.get('M1_noise',{}).get('integrated_jitter_s') if last else None,
            stop_reason=result['stop_reason'],failure=result['failure'],trace_events=len(events),evidence=str(path)))
    if len(rows)!=6:raise ValueError('incomplete six-arm study')
    counts={k:sum(row['cost'][k] for row in rows) for k in ('M1_calls','analytic_calls','M2_calls','M2_candidate_slots_used','cache_hits','native_completed_runs','native_failed_attempts','integration_points','native_elapsed_s','total_elapsed_s')}
    summary=dict(schema_version='stage6c-sixarm-audit-1.0',rows=rows,total_cost=counts,
        first_feasible=sum(r['first_status']=='RESEARCH_JOINT_FEASIBLE' for r in rows),
        final_feasible=sum(r['final_status']=='RESEARCH_JOINT_FEASIBLE' for r in rows),
        FULL_SYSTEMSPEC_CERTIFIED=False,LLM_calls=0,scope='two predeclared environments; no general success-rate inference')
    write_new(out/'summary.json',summary)
    lines=['# Stage6C six-arm actual study','','|Run|First|Final|minmargin first→final|Jitter ps final|newM2|cache|native|',
        '|---|---|---|---:|---:|---:|---:|---:|']
    for row in rows:
        jitter=row['final_metrics'].get('integrated_jitter_s',{}).get('value')
        lines.append('|{}|{}|{}|{} → {}|{}|{}|{}|{}|'.format(row['run'],row['first_status'],row['final_status'],
            row['first_margin'],row['final_margin'],jitter*1e12 if jitter is not None else None,
            row['cost']['M2_calls'],row['cost']['cache_hits'],row['cost']['native_completed_runs']))
    lines+=['','Actual cost: '+json.dumps(counts),'','Strict periodic PM and original microhertz frequency remain UNKNOWN. Finite recovery and seed CI are conditional.']
    with (out/'summary.md').open('x',encoding='utf-8') as f:f.write('\n'.join(lines)+'\n')
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--study',required=True);p.add_argument('--out',required=True);a=p.parse_args();print(json.dumps(audit(a.study,a.out)['total_cost']))
