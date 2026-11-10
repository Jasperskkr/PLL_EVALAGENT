"""Create self-contained source/results ZIP on a spacious volume; never mutate evidence."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import zipfile
ROOT=Path(__file__).resolve().parents[1]


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def extra_roots(values):
    result={}
    for value in values or []:
        name,sep,path=value.partition('=')
        if not sep or not name or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789_-' for c in name):
            raise ValueError('extra must be a simple-name=existing-directory')
        root=Path(path).resolve()
        if name in result or not root.is_dir():raise ValueError('duplicate or missing extra directory')
        result[name]=root
    return result


def package(study,delivery,extra=None):
    study=Path(study).resolve();delivery=Path(delivery).resolve();delivery.mkdir(parents=True,exist_ok=False)
    files={};include=['pll_allocation','configs','tests','tools','docs','data','baseline','examples','learn']
    skip={'__pycache__','.pytest_cache','.git','build','build_stage4','build_stage4_1_r2','build_stage6c','build_stage6c_v2','build_stage6c_v3'}
    for directory in include:
        for p in (ROOT/directory).rglob('*'):
            if p.is_file() and not any(x in skip for x in p.parts) and p.suffix.lower() not in ('.dll','.obj','.lib','.exp','.pyc','.zip'):
                files['repo/'+p.relative_to(ROOT).as_posix()]=p
    for p in ROOT.iterdir():
        if p.is_file() and (p.suffix.lower() in ('.md','.py','.toml','.txt','.yml','.yaml','.json') or p.name in ('.gitattributes','.gitignore')):
            if p.name in ('bootstrap_stage7.py',):continue
            files['repo/'+p.name]=p
    # Complete original407test inputs plus allcurrentnew/failedexperiments.
    for dirname in ['stage5','stage6a','stage6b','stage6c','stage7']:
        base=ROOT/'experiments'/dirname
        for p in base.rglob('*'):
            if not p.is_file():continue
            # Copied identity JSONs are evidence, even when their parent keeps
            # the original build directory name. Native binary suffixes below
            # are still excluded; this exception admits only the JSON receipt.
            identity_evidence=p.name=='identity.json' and 'rebuilt_identity' in p.relative_to(ROOT).parts
            if any(x in skip or x=='tmp' for x in p.parts) and not identity_evidence:continue
            if p.suffix.lower() in ('.dll','.obj','.lib','.exp','.pyc','.zip'):continue
            if dirname=='stage7' and not any(x in p.parts for x in ('safety_02','pretests_01')):continue
            files['repo/'+p.relative_to(ROOT).as_posix()]=p
    # Legacy regression tests also use these explicitly inherited Stage4.2 inputs.
    for name in ('summary.json','coupling_and_sensitivity.json'):
        p=ROOT/'experiments/stage4_2/readiness_05'/name
        if p.is_file():files['repo/'+p.relative_to(ROOT).as_posix()]=p
    for p in study.rglob('*'):
        if p.is_file() and not any(x in skip for x in p.parts):files['study/'+p.relative_to(study).as_posix()]=p
    for name,base in (extra or {}).items():
        if delivery.is_relative_to(base):raise ValueError('delivery cannot be inside an included evidence tree')
        for p in base.rglob('*'):
            if p.is_file() and not any(x in skip or x=='tmp' for x in p.parts) and p.suffix.lower() not in ('.dll','.obj','.lib','.exp','.pyc','.zip'):
                files['extra/'+name+'/'+p.relative_to(base).as_posix()]=p
    archive=delivery/'PLL_Stage6C_reproducible_bundle.zip';manifest=[]
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
        for name,p in sorted(files.items()):
            row=dict(path=name,bytes=p.stat().st_size,sha256=sha(p));manifest.append(row)
            # NPZ is already a compressed ZIP. Re-deflating multi-gigabyte noise
            # trajectories costs minutes without improving reproducibility.
            compression=zipfile.ZIP_STORED if p.suffix.lower() in ('.npz','.gz','.png','.jpg','.jpeg','.pdf') else zipfile.ZIP_DEFLATED
            z.write(p,name,compress_type=compression)
        metadata=dict(schema_version='pll-stage6c-bundle-1.0',created_utc=datetime.now(timezone.utc).isoformat(),files=manifest,
            native_binaries='excluded; fresh MSVC rebuild required; historical binary hashes remain evidence',
            compression_policy='already-compressed arrays/images/PDF stored; other files deflated; all payload hashes verified',
            original_study_path=str(study),extra_evidence_roots={k:str(v) for k,v in (extra or {}).items()},
            notes='saved runtime absolute paths are provenance; repo/, study/ and extra/ include their artifact trees')
        z.writestr('MANIFEST.json',json.dumps(metadata,ensure_ascii=False,indent=2))
        z.writestr('README.txt','See repo/docs/stage6c/REPRODUCE.md, FINAL_RESEARCH_REPORT.md and FINAL_DELIVERY_ACCEPTANCE.md (when present). Earlier trace-bound document revisions remain as historical records; the final acceptance addendum records observed export outcomes. All official executions use python -m pll_allocation pipeline. Historical failures are included; zero sources never upgrade strict PM or frequency precision. No secrets or native binaries are intentionally included.\n')
    receipt=dict(path=str(archive),sha256=sha(archive),bytes=archive.stat().st_size,files=len(manifest),source_bytes=sum(x['bytes'] for x in manifest))
    with (delivery/'PACKAGING_RECEIPT.json').open('x',encoding='utf-8') as f:json.dump(receipt,f,indent=2)
    return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--study',required=True);p.add_argument('--out',required=True)
    p.add_argument('--extra',action='append',default=[],help='include auxiliary evidence as name=directory')
    a=p.parse_args();print(json.dumps(package(a.study,a.out,extra_roots(a.extra))))
