"""Consolidate preserved original events/evidence; never invent historical realtime."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from pll_allocation.allocation.core import read,write_new
from pll_allocation.physics_mapping.model import fingerprint


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',required=True)
    parser.add_argument('--delivery-receipt');a=parser.parse_args()
    out=Path(a.out).resolve();out.mkdir(parents=True,exist_ok=False)
    chain='0'*64;count=0;real=0;native=0;indexes=0;origins=[]
    stream=(out/'complete_trace.jsonl').open('x',encoding='utf-8')
    def emit(event,**fields):
        nonlocal chain,count
        count+=1
        record={'index':count,'event':event,'index_recorded_at':datetime.now(timezone.utc).isoformat(),
            'previous_sha256':chain,**fields}
        record['event_sha256']=fingerprint(record);chain=record['event_sha256']
        stream.write(json.dumps(record,ensure_ascii=False,allow_nan=False)+'\n')
    emit('TRACE_SCOPE',scope='consolidated preserved real events and immutable artifact index, not new experiments',
        realtime_coverage='method/child runtime original payloads retain their timestamps or local elapsed clock',
        reconstructed_coverage='safe-copy/design/build/test/protection/package receipts indexed with explicit provenance',
        unavailable='no fabricated exact timestamps of every author edit before runtime trace setup')
    files=[p for p in sorted((ROOT/'experiments/stage6b').rglob('*'))
        if p.is_file() and not p.is_relative_to(out) and not set(p.parts)&{'tmp','__pycache__'}
        and 'package_validation_01/reproduced/' not in p.as_posix()]
    for p in files:
        relative=p.relative_to(ROOT).as_posix()
        if p.name=='allocation_trace.jsonl':
            digest=sha(p);lines=p.read_text(encoding='utf-8').splitlines()
            emit('ORIGINAL_TRACE_OPENED',artifact=relative,sha256=digest,original_event_count=len(lines));origins.append(relative)
            for line_number,line in enumerate(lines,1):
                payload=json.loads(line)
                emit('PRESERVED_REALTIME_EVENT',artifact=relative,line=line_number,original_event=payload,
                    provenance='original event; clock belongs to originating run, no global chronological inference')
                real+=1
        elif p.name=='summary.json' and '/raw/' in relative:
            item=read(p)
            if isinstance(item,dict) and 'integration_points' in item.get('summary',{}):
                request=p.parent/'request.json'
                emit('PRESERVED_NATIVE_EVIDENCE',artifact=relative,sha256=sha(p),summary=item['summary'],
                    request=request.relative_to(ROOT).as_posix() if request.is_file() else None,
                    request_sha256=sha(request) if request.is_file() else None,
                    provenance='original native execution evidence; does not create or recount a new call')
                native+=1
        elif p.name in ('receipt.json','plan.json','tests.xml','independent_checks.json','comparison.json',
                         'run_manifest.json','trace_index.json') or p.suffix=='.txt' and p.name in ('stdout.txt','stderr.txt'):
            emit('PRESERVED_ARTIFACT_INDEX',artifact=relative,sha256=sha(p),bytes=p.stat().st_size,
                provenance='post-hoc evidence index; original timing is in artifact')
            indexes+=1
    for p in sorted((ROOT/'docs/stage6b').glob('*')):
        if p.is_file():emit('DESIGN_AND_REPORT_INDEX',artifact=p.relative_to(ROOT).as_posix(),sha256=sha(p))
    if a.delivery_receipt:
        p=Path(a.delivery_receipt).resolve()
        emit('CANDIDATE_PACKAGE_VALIDATED',artifact=p.relative_to(ROOT).as_posix(),sha256=sha(p),receipt=read(p),
            provenance='earlier candidate archive; final archive has external receipt to avoid circular hash')
    emit('TRACE_COMPLETED',preserved_runtime_events=real,native_evidence_records=native,artifact_indexes=indexes)
    stream.close()
    # Independently verify emitted serialization, linkage and record order.
    previous='0'*64
    for index,line in enumerate((out/'complete_trace.jsonl').read_text(encoding='utf-8').splitlines(),1):
        record=json.loads(line);digest=record.pop('event_sha256')
        assert record['index']==index and record['previous_sha256']==previous and fingerprint(record)==digest
        previous=digest
    assert previous==chain
    write_new(out/'receipt.json',{'status':'PASS','events':count,'chain_final_sha256':chain,
        'trace_sha256':sha(out/'complete_trace.jsonl'),'preserved_runtime_events':real,'native_evidence_records':native,
        'artifact_indexes':indexes,'source_traces':origins,'scope':'formal experiment and separate package reproduction indexed distinctly by source path'})


if __name__=='__main__':main()
