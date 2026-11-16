"""Package completed ablation evidence. No solver, provider, or M1 invocation."""
from datetime import datetime, timezone
from pathlib import Path
import difflib
import hashlib
import json
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'experiments/spec_allocation_ablation'
sys.path.insert(0,str(ROOT))


def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,data):
    with p.open('x',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False,indent=2,allow_nan=False)
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)
def deleted(raw):return sorted(r[3:] for r in raw.split(b'\0') if r[:2].strip()==b'D')


def main():
    from pll_allocation.agent.spec_allocation_ablation import check_freeze
    check_freeze(OUT)
    for task in ('TASK0_INDEPENDENT','TASK1','TASK2','TASK3'):
        assert read(OUT/(task+'_GATE.json'))['accepted'],task
    assert read(OUT/'verifier/FINAL_VERIFIER_FINDINGS.json')['accepted']
    protected=read(OUT/'PROTECTED_HISTORY.json')
    changed=[name for name,digest in protected.items() if not (ROOT/name).is_file() or sha(ROOT/name)!=digest]
    assert not changed,changed
    baseline=read(OUT/'GIT_BASELINE.json')
    assert git('rev-parse','HEAD').decode().strip()==baseline['head']
    assert git('branch','--show-current').decode().strip()==baseline['branch']
    assert not git('diff','--cached','--name-only')
    assert deleted(git('status','--porcelain=v1','-z'))==deleted((OUT/'GIT_STATUS_BEFORE.bin').read_bytes())
    original=['pll_allocation/pipeline.py','tools/stress_open_domain.py']
    added=['pll_allocation/agent/spec_allocation_ablation.py','pll_allocation/agent/spec_allocation_ablation_report.py',
        'tests/test_spec_allocation_ablation.py','tools/analyze_spec_allocation_ablation.py',
        'tools/audit_ablation_clock.py','tools/package_spec_allocation_ablation.py']
    manifest={}
    with (OUT/'CODE_CHANGES.patch').open('x',encoding='utf-8',newline='\n') as handle:
        for name in original+added:
            before=OUT/'before'/name;after=ROOT/name
            a=before.read_text(encoding='utf-8-sig').splitlines(True) if before.exists() else []
            b=after.read_text(encoding='utf-8-sig').splitlines(True)
            handle.writelines(difflib.unified_diff(a,b,fromfile='a/'+name if before.exists() else '/dev/null',tofile='b/'+name))
            manifest[name]={'before_sha256':sha(before) if before.exists() else None,'after_sha256':sha(after)}
    put(OUT/'CODE_CHANGE_MANIFEST.json',manifest)
    s=read(OUT/'SUMMARY.json')
    put(OUT/'FINAL_STATUS.json',{'status':'COMPLETED_AND_STOPPED','finalized_utc':datetime.now(timezone.utc).isoformat(),
        'completed_tasks':[0,1,2,3],'not_implemented_tasks':[4,5],'main_runs':s['run_count'],
        'main_M1':s['M1'],'main_API':s['API'],'main_M2':s['M2'],
        'history_files_checked':len(protected),'history_changed':changed,'frozen_source_unchanged':True,
        'head':baseline['head'],'branch':baseline['branch'],'staging_empty':True,
        'preexisting_deleted_count':len(deleted((OUT/'GIT_STATUS_BEFORE.bin').read_bytes())),
        'new_branch_worktree_commit_push':False,'new_API_M1_M2_from_packaging':0,
        'cost_ledger':'verifier/FINAL_VERIFIER_FINDINGS.json',
        'no_broader_model_certification':True})
    exclude={'ARTIFACT_INDEX.json','FINAL_DELIVERY_RECEIPT.json'}
    files={p.relative_to(OUT).as_posix():{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(OUT.rglob('*'))
        if p.is_file() and p.relative_to(OUT).as_posix() not in exclude}
    docs={name:sha(ROOT/name) for name in ('docs/DECISIONS.md','docs/PROJECT_STATUS.md','SPEC_ALLOCATION_ABLATION_HANDOFF.md')}
    put(OUT/'ARTIFACT_INDEX.json',{'files':files,'source_code':manifest,'external_docs_sha256':docs,
        'excluded_self_reference':sorted(exclude)})
    put(OUT/'FINAL_DELIVERY_RECEIPT.json',{'status':'COMPLETED_AND_STOPPED','files_indexed':len(files),
        'index_sha256':sha(OUT/'ARTIFACT_INDEX.json'),'code_patch_sha256':sha(OUT/'CODE_CHANGES.patch'),
        'status_sha256':sha(OUT/'FINAL_STATUS.json'),'source_frozen_unchanged':True,
        'history_files_unchanged':len(protected),'new_API_M1_M2':0})
    print(json.dumps({'status':'COMPLETED_AND_STOPPED','files':len(files),'protected_files':len(protected),
        'main_runs':s['run_count'],'M1':s['M1'],'API':s['API'],'M2':s['M2']},ensure_ascii=False))


if __name__=='__main__':main()
