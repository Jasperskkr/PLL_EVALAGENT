"""Build an artifact-derived audit trace after experiments; never invent tool calls."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()


def create(out,study=None,extra=None):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    roots=[ROOT/'experiments/stage7/safety_02',ROOT/'experiments/stage7/pretests_01',ROOT/'experiments/stage6c',ROOT/'configs/stage6c',ROOT/'docs/stage6c']
    if study:roots.append(Path(study).resolve())
    if extra:roots.extend(extra.values())
    files=[]
    for base in roots:
        for p in sorted(base.rglob('*')):
            if p.is_file() and not p.is_relative_to(out) and not any(x in p.parts for x in ('__pycache__','tmp')):
                if p.suffix.lower() not in ('.dll','.obj','.lib','.exp','.pyc','.zip'):files.append(p)
    records=[];previous='0'*64
    # Trace is reconstructed from saved evidence; filesystem mtime is a retrieval ordering,
    # not a substitute for actual timestamps in command/native/run receipts.
    for p in sorted(set(files),key=lambda p:(p.stat().st_mtime_ns,p.as_posix())):
        rel=p.relative_to(ROOT).as_posix() if p.is_relative_to(ROOT) else p.as_posix();typ='ARTIFACT'
        if p.name.endswith('.command.json') or p.name in ('receipt.json','command.json'):typ='ACTUAL_COMMAND_OR_RECEIPT'
        elif p.name.endswith('failure.json'):typ='RECORDED_FAILURE'
        elif p.name.endswith('events.jsonl') or p.name=='allocation_trace.jsonl':typ='ACTUAL_RUN_EVENTS'
        elif p.name in ('first_candidate.json','initial_joint_block_spec.json','proposal.json'):typ='PERSISTED_PROPOSAL'
        event=dict(index=len(records)+1,event=typ,path=rel,sha256=sha(p),bytes=p.stat().st_size,previous_sha256=previous)
        extra_match=next(((name,base) for name,base in (extra or {}).items() if p.is_relative_to(base)),None)
        if study and p.is_relative_to(Path(study).resolve()):event['bundle_path']='study/'+p.relative_to(Path(study).resolve()).as_posix()
        elif extra_match:event['bundle_path']='extra/'+extra_match[0]+'/'+p.relative_to(extra_match[1]).as_posix()
        else:event['bundle_path']='repo/'+rel
        event['event_sha256']=hashlib.sha256(canonical(event)).hexdigest();previous=event['event_sha256'];records.append(event)
        if typ=='ACTUAL_RUN_EVENTS':
            for number,line in enumerate(p.read_text(encoding='utf-8').splitlines(),1):
                try:payload=json.loads(line)
                except json.JSONDecodeError:continue
                child=dict(index=len(records)+1,event='EMBEDDED_ACTUAL_EVENT',path=rel,line=number,
                    original_event=payload,previous_sha256=previous,
                    timestamp_policy='original payload timestamp/cost retained; outer order is artifact retrieval')
                child['event_sha256']=hashlib.sha256(canonical(child)).hexdigest();previous=child['event_sha256'];records.append(child)
    with (out/'artifact_trace.jsonl').open('x',encoding='utf-8') as f:
        for row in records:f.write(json.dumps(row,ensure_ascii=False)+'\n')
    summary=dict(schema_version='pll-stage6c-artifact-audit-1.0',created_utc=datetime.now(timezone.utc).isoformat(),
        files=len(files),trace_events=len(records),trace_final_sha256=previous,scope='artifact-derived execution evidence, includes retained failures and embedded actual events',
        limitations='does not pretend to reconstruct unrecorded interactive tool conversations; actual calls/costs remain in linked receipts',
        native_event_files=[r['path'] for r in records if r['event']=='ACTUAL_RUN_EVENTS'])
    with (out/'receipt.json').open('x',encoding='utf-8') as f:json.dump(summary,f,indent=2,ensure_ascii=False)
    return summary


if __name__=='__main__':
    from package_stage6c import extra_roots
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--study')
    p.add_argument('--extra',action='append',default=[])
    a=p.parse_args();print(json.dumps(create(a.out,a.study,extra_roots(a.extra))))
