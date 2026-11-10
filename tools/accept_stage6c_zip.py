"""Independent-readable full ZIP CRC/content/path/trace acceptance; no extraction."""
import argparse
import hashlib
import json
from pathlib import Path,PurePosixPath
import time
import zipfile


def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()


def accept(archive,out):
    archive=Path(archive);out=Path(out);out.mkdir(parents=True,exist_ok=False);start=time.perf_counter();bad=[];refs=0;chains=0
    h=hashlib.sha256()
    with archive.open('rb') as stream:
        for b in iter(lambda:stream.read(1024*1024),b''):h.update(b)
    with zipfile.ZipFile(archive) as z:
        names=z.namelist();s=set(names)
        if len(s)!=len(names):raise ValueError('duplicate ZIP names')
        if any(PurePosixPath(n).is_absolute() or '..' in PurePosixPath(n).parts for n in names):raise ValueError('unsafe ZIP path')
        manifest=json.loads(z.read('MANIFEST.json'));expected={row['path'] for row in manifest['files']}|{'MANIFEST.json','README.txt'}
        if expected!=s:raise ValueError('ZIP manifest set mismatch')
        total=0
        for row in manifest['files']:
            digest=hashlib.sha256();size=0
            with z.open(row['path']) as stream:
                for b in iter(lambda:stream.read(1024*1024),b''):digest.update(b);size+=len(b)
            if digest.hexdigest()!=row['sha256'] or size!=row['bytes']:bad.append(row['path'])
            total+=size # reading each stream fully also verifies CRC
        for name in names:
            if name.endswith('allocation_trace.jsonl') or name.endswith('artifact_trace.jsonl'):
                events=[json.loads(line) for line in z.read(name).decode('utf-8').splitlines()]
                if not events or 'event_sha256' not in events[0]:continue # old plain trace retained as such
                previous='0'*64
                for index,event in enumerate(events,1):
                    raw={k:v for k,v in event.items() if k!='event_sha256'}
                    encoded=(json.dumps(raw,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
                        if name.endswith('allocation_trace.jsonl') else canonical(raw))
                    if event.get('previous_sha256')!=previous or event.get('index')!=index or hashlib.sha256(encoded).hexdigest()!=event['event_sha256']:
                        raise ValueError('trace chain mismatch:'+name)
                    previous=event['event_sha256']
                    if event.get('bundle_path'):
                        refs+=1
                        if event['bundle_path'] not in s:raise ValueError('trace artifact missing:'+event['bundle_path'])
                chains+=1
        # Every final study constraint row resolves inside its own candidate directory.
        for name in names:
            if name.startswith('study/runs/') and name.endswith('/joint_evaluation.json'):
                value=json.loads(z.read(name));base=PurePosixPath(name).parent
                for rule in value['constraints']:
                    target=(base/rule['evidence_path']).as_posix();refs+=1
                    if target not in s:raise ValueError('joint constraint evidence absent:'+target)
        result=dict(status='PASS' if not bad else 'FAIL',archive=str(archive),archive_sha256=h.hexdigest(),
            manifest_files=len(manifest['files']),source_bytes=total,hash_mismatch=bad,
            all_stream_CRCS_verified=True,valid_hash_chains=chains,checked_artifact_references=refs,
            elapsed_s=time.perf_counter()-start,scope='all ZIP entries/manifest hashes and saved trace/evidence paths; no new simulation')
    with (out/'receipt.json').open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--archive',required=True);p.add_argument('--out',required=True);a=p.parse_args();print(json.dumps(accept(a.archive,a.out)))
