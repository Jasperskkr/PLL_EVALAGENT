"""Compare Stage6B byte snapshot and Stage6C optional changes, no state mutation."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args();out=Path(a.out);out.mkdir(parents=True,exist_ok=False)
    baseline=json.loads((ROOT/'experiments/stage7/safety_02/current_source_manifest.json').read_text(encoding='utf-8'))
    allowed={'pll_allocation/verification/experiments.py','pll_allocation/pipeline.py','pll_allocation/pipeline_contracts.py',
        'pll_allocation/allocation/multispec_constraints.py','pll_allocation/allocation/multispec_search.py'}
    changed=[];unchanged=[]
    for row in baseline:
        path=ROOT/row['path'];actual=hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        record={**row,'actual_sha256':actual}
        if actual!=row['sha256']:changed.append(record)
        else:unchanged.append(record)
    unexpected=[r for r in changed if r['path'] not in allowed]
    current=[]
    for dirname in ('pll_allocation','configs/stage6c','tests','tools','docs/stage6c'):
        for path in sorted((ROOT/dirname).rglob('*')):
            if (path.is_file() and '__pycache__' not in path.parts and path.suffix.lower() not in ('.dll','.obj','.lib','.exp','.pyc')
                and not any(part.startswith('build') for part in path.relative_to(ROOT).parts)):
                current.append({'path':path.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size})
    cmd=['git','diff','--no-ext-diff','--','pll_allocation','configs/stage6c','tests','tools']
    diff=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace')
    with (out/'git_tracked_diff.patch').open('x',encoding='utf-8') as f:f.write(diff.stdout)
    with (out/'current_manifest.json').open('x',encoding='utf-8') as f:json.dump(current,f,indent=2)
    result=dict(status='PASS' if not unexpected else 'FAIL',baseline_files=len(baseline),unchanged_files=len(unchanged),
        explicit_optional_modified=changed,unexpected=unexpected,allowed=sorted(allowed),
        unchanged_core=['ideal model/registry/contracts/kernel/simulator/measure/verify/protocol/allocate byte preserved'],
        diff_scope='Git HEAD older than fullStage6B; tracked diff includes inherited changes. Use baseline manifest for this stage attribution.')
    with (out/'receipt.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
    print(json.dumps({k:result[k] for k in ('status','baseline_files','unchanged_files')}))
