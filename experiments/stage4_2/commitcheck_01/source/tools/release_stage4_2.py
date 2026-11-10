"""Stage4.2 explicit review export/staging, preserving all unrelated working-tree edits."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parents[1]
BASE='47afcb72011636e838b03d81cf91bcec49744a77'
EXCLUDE={'__pycache__','.pytest_cache','tmp','source','commitcheck_01'}
FILES=['pll_allocation/physics_mapping/registry.py','tests/test_mapping_registry_stage4_2.py',
       'tools/audit_stage4_2.py','tools/run_stage4_2.py','tools/release_stage4_2.py']


def git(*args,input=None):
    return subprocess.check_output(['git',*args],cwd=ROOT,input=input)


def selected():
    files=[ROOT/name for name in FILES]
    for folder in ('docs/stage4_2','experiments/stage4_2'):
        files.extend(p for p in (ROOT/folder).rglob('*') if p.is_file() and not set(p.relative_to(ROOT/folder).parts)&EXCLUDE)
    appends=json.loads((ROOT/'docs/stage4_2/stage_log_appends.json').read_text(encoding='utf-8'))
    blobs={p.relative_to(ROOT).as_posix():p.read_bytes() for p in sorted(set(files))}
    for name,text in appends.items():
        blobs[name]=git('show',BASE+':'+name)+text.encode('utf-8')
    secret_values=[v.encode() for k,v in os.environ.items() if len(v)>=12 and any(x in k.upper() for x in ('TOKEN','API_KEY','SECRET','PASSWORD'))]
    hits=[name for name,content in blobs.items() if any(value in content for value in secret_values)]
    if hits:raise ValueError('credential value detected; paths='+str(hits))
    return blobs


def export(out):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    source=out/'source';source.mkdir()
    archive=zipfile.ZipFile(io.BytesIO(git('archive','--format=zip',BASE)))
    for info in archive.infolist():
        if info.is_dir():continue
        path=source/info.filename
        if not path.resolve().is_relative_to(source):raise ValueError('unsafe archive path')
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(archive.read(info))
    blobs=selected()
    for name,content in blobs.items():
        path=source/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(content)
    with (out/'export_manifest.json').open('x',encoding='utf-8') as stream:
        json.dump({'baseline_commit':BASE,'overlay_sha256':{k:hashlib.sha256(v).hexdigest() for k,v in blobs.items()},
                   'overlay_files':len(blobs),'contains_stage4_runtime':False,'has_nested_git':False,
                   'scope':'ephemeral regression fixture, no new project'},stream,ensure_ascii=False,indent=2)
    print(json.dumps({'source':str(source),'overlay_files':len(blobs)}))


def stage():
    if git('rev-parse','HEAD').decode().strip()!=BASE:raise ValueError('unexpected parent commit')
    if git('diff','--cached','--name-only').strip():raise ValueError('index already contains work; will not replace it')
    blobs=selected()
    for name,content in blobs.items():
        oid=git('hash-object','-w','--stdin',input=content).decode().strip()
        git('update-index','--add','--cacheinfo','100644',oid,name)
    names=set(git('diff','--cached','--name-only').decode('utf-8').splitlines())
    # Git may quote non-ASCII paths, but every staged path here is ASCII.
    if names!=set(blobs):raise ValueError('staged scope mismatch')
    for name,content in blobs.items():
        if git('show',':'+name)!=content:raise ValueError('staged byte mismatch: '+name)
    print(json.dumps({'staged_files':len(names),'secret_scan':'PASS','unrelated_dirty_work_not_staged':True}))


if __name__=='__main__':
    p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--export',type=Path);g.add_argument('--stage',action='store_true');a=p.parse_args()
    export(a.export) if a.export else stage()
