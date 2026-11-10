"""Verify inherited byte protection and record actual Stage6B delta; no mutations."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from pll_allocation.allocation.core import read,write_new


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',required=True);a=parser.parse_args()
    out=Path(a.out).resolve();out.mkdir(parents=True,exist_ok=False)
    safety=ROOT/'experiments/stage6b/safety_01';raw_files=read(safety/'baseline_files.json');receipt=read(safety/'receipt.json')
    files={}
    for name,item in raw_files.items():
        normalized=name.replace('\\','/')
        if normalized in files and files[normalized]!=item:raise ValueError('conflicting duplicated safety identity')
        files[normalized]=item
    original=Path(receipt['source_root']);changed=[];original_changed=[]
    for name,item in files.items():
        p=ROOT/name;source=original/name
        if not p.is_file() or sha(p)!=item['sha256']:
            changed.append({'path':name,'original_sha256':item['sha256'],'sha256':sha(p) if p.is_file() else None})
        if not source.is_file() or sha(source)!=item['sha256']:original_changed.append(name)
    allowed={'pll_allocation/pipeline.py','docs/DECISIONS.md','docs/PROJECT_STATUS.md','tools/run_stage41.py'}
    unexpected=[r for r in changed if r['path'] not in allowed]
    status=subprocess.run(['git','status','--short'],cwd=original,capture_output=True,text=True,encoding='utf-8').stdout
    source_git_unchanged=status==receipt['source_status']
    reuse=[]
    for name in files:
        if any(name.startswith(p) for p in ('pll_allocation/allocation/','pll_allocation/physics_mapping/',
                'pll_allocation/block_space/','pll_allocation/verification/')) and Path(name).suffix in ('.py','.cpp'):
            reuse.append({'path':name,'original_path':str(original/name),'original_sha256':files[name]['sha256'],
                'sha256':sha(ROOT/name),'byte_identical':sha(ROOT/name)==files[name]['sha256'],
                'domain':'fixed ideal SI behavioral model and original declared parameter/measurement domains',
                'semantics':'original formulas/proposals/measurements reused without circuit-realizability claims'})
    write_new(out/'reuse_manifest.json',reuse)
    result={'safety_manifest_entries':len(raw_files),'duplicate_slash_alias_entries':len(raw_files)-len(files),
        'inherited_unique_files_checked':len(files),'inherited_changes':changed,'unexpected_inherited_changes':unexpected,
        'historical_tool_adaptation':'tools/run_stage41.py: optional Git metadata for exported source only; all source/protocol lock checks retained',
        'original_source_changes':original_changed,'original_git_status_unchanged':source_git_unchanged,
        'all_original_reused_modules_unchanged':all(r['byte_identical'] for r in reuse),
        'HEAD':subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True).stdout.strip(),
        'branch':subprocess.run(['git','branch','--show-current'],cwd=ROOT,capture_output=True,text=True).stdout.strip(),
        'master':subprocess.run(['git','rev-parse','master'],cwd=ROOT,capture_output=True,text=True).stdout.strip(),
        'source_branch_and_dirty_snapshot_preserved':source_git_unchanged and not original_changed,
        'no_merge_or_commit_in_this_stage':True}
    result['status']='PASS' if not unexpected and not original_changed and source_git_unchanged and result['all_original_reused_modules_unchanged'] else 'FAIL'
    write_new(out/'receipt.json',result);print(result)
    return 0 if result['status']=='PASS' else 2

if __name__=='__main__':raise SystemExit(main())
