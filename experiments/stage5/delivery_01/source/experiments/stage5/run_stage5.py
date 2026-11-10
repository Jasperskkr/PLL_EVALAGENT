"""Finite study orchestration. Every allocation and full M2 uses formal pipeline CLI."""
from pathlib import Path
import argparse
import json
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pll_allocation.allocation.core import read, write_new
from pll_allocation.physics_mapping.model import fingerprint
from pll_allocation.pipeline import source_identity


def invoke(folder, command):
    folder.mkdir(parents=True, exist_ok=False)
    start = time.perf_counter()
    write_new(folder/'command.json', {'argv':command,'cwd':str(ROOT),'start_unix':time.time()})
    with (folder/'stdout.log').open('x',encoding='utf-8') as out, (folder/'stderr.log').open('x',encoding='utf-8') as err:
        process=subprocess.run(command,cwd=ROOT,stdout=out,stderr=err,timeout=900,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
    receipt={'argv':command,'returncode':process.returncode,'process_wall_s':time.perf_counter()-start}
    write_new(folder/'execution.json',receipt)
    return receipt


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--phase',choices=['firstshot','repair','local'],required=True)
    parser.add_argument('--out',required=True);parser.add_argument('--firstshot');parser.add_argument('--repair')
    parser.add_argument('--resume-local',help='Read-only reference to completed S0 evidence after bookkeeping failure; never rerun it')
    args=parser.parse_args(); root=Path(args.out).resolve(); root.mkdir(parents=True,exist_ok=False)
    start=time.perf_counter(); sources=source_identity(); plan=read(ROOT/'experiments/stage5/experiment_plan_frozen.json')
    write_new(root/'manifest.json',{'phase':args.phase,'plan_sha256':fingerprint(plan),'source_identity':sources,
        'HEAD':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip(),
        'branch':subprocess.check_output(['git','branch','--show-current'],cwd=ROOT).decode().strip(),
        'start_unix':time.time(),'plan':plan})
    jobs=[]
    if args.phase=='firstshot':
        for scene in plan['scenarios']:
            path=ROOT/f'experiments/stage5/scenarios/{scene["id"]}.json'
            if read(path)['scenario_sha256']!=scene['sha256']:raise ValueError('frozen scenario changed')
            for strategy,seed in [('analytical',None),*[('random',seed) for seed in plan['random_seeds']],('llm_agent',None)]:
                name=scene['id']+'__'+strategy+(f'__{seed}' if seed is not None else '')
                out=root/'runs'/name
                cmd=[sys.executable,'-B','-m','pll_allocation','pipeline','--strategy',strategy,'--scenario',str(path),
                    '--m2-budget','1','--repair-budget','0','--out',str(out)]
                if seed is not None:cmd+=['--seed',str(seed)]
                receipt=invoke(root/'receipts'/name,cmd)
                result=read(out/'result.json') if (out/'result.json').exists() else None
                jobs.append({'arm':name,'directory':str(out),'receipt':receipt,'status':result['status'] if result else 'PROCESS_FAILED'})
                print(name,jobs[-1]['status'],flush=True)
                write_new(root/f'progress_{len(jobs):03d}.json',jobs[-1])
    elif args.phase=='repair':
        first=Path(args.firstshot); complete=read(first/'complete.json')
        for job in complete['jobs']:
            original=Path(job['directory']); result=read(original/'result.json')
            if not result['attempts']:continue
            last=original/result['attempts'][-1]['directory']
            if not (last/'structured_feedback.json').exists():continue
            fb=read(last/'structured_feedback.json')
            if fb['verdict']!='FAIL' or fb['kind']!='BW':continue
            sid=result['scenario_binding']['scenario_id']; name=job['arm']; out=root/'runs'/name
            cmd=[sys.executable,'-B','-m','pll_allocation','pipeline','--strategy','analytical',
                '--scenario',str(ROOT/f'experiments/stage5/scenarios/{sid}.json'),
                '--feedback-from',str(last),'--m2-budget','2','--repair-budget','1','--out',str(out)]
            receipt=invoke(root/'receipts'/name,cmd)
            repaired=read(out/'result.json')
            jobs.append({'arm':name,'original_strategy':result['strategy'],'directory':str(out),
                'parent':str(original),'repair_kind':'EXISTING_DETERMINISTIC_NOT_LLM','receipt':receipt,'status':repaired['status']})
            print(name,repaired['status'],flush=True)
    else:
        first=Path(args.firstshot); sys.path.insert(0,str(ROOT/'tools'))
        from run_stage41 import frequency_variants, steps
        from run_stage4 import measurement_gate
        from pll_allocation.verification.return_ratio import protocol,sweep
        for sid in ('S0','S3'):
            source=first/'runs'/f'{sid}__analytical'/'attempt_001'/'AllocationProposal.json'
            item=read(source)
            if sid=='S0' and args.resume_local:
                case=Path(args.resume_local).resolve()/sid
                if read(case/'AllocationProposal.json')!=item or not (case/'steps/result.json').is_file():
                    raise ValueError('completed S0 evidence binding mismatch')
                previous=read(case/'frequency'/'raw/base/plan.json')
                if previous['protocol']!=protocol():raise ValueError('reused S0 protocol mismatch')
                summaries=[read(p)['summary'] for p in case.rglob('*.json') if p.name.startswith(('summary','pilot_summary'))]
                cost={'native_runs':len(summaries),'native_s':sum(s.get('elapsed_s',s.get('native_elapsed_s',0)) for s in summaries)}
                jobs.append({'scenario':sid,'directory':str(case),'cost':cost,'new_native_runs_this_continuation':0,
                    'origin':'REUSE_COMPLETED_EVIDENCE_NOT_NEW_SIMULATION','scope':'LOCAL_ENGINEERING_EVIDENCE_NOT_PERIODIC_PM_CERTIFICATION'})
                write_new(root/'S0_evidence_reference.json',jobs[-1])
                continue
            case=root/sid;case.mkdir()
            write_new(case/'AllocationProposal.json',item)
            measurements={}; doc=protocol()
            for name,mode,amp,dt,cycles,grid in frequency_variants(doc):
                measurements[name]=sweep(case/'frequency'/'raw'/name,item['joint_block_spec'],mode=mode,
                    amplitude=amp,dt=dt,cycles=cycles,grid=grid,doc=doc)
                print(sid,name,measurements[name]['crossing']['status'],flush=True)
            write_new(case/'frequency_result.json',measurements)
            write_new(case/'frequency_gate.json',measurement_gate(measurements,doc))
            steps(case/'steps',item['joint_block_spec'])
            summaries=[read(p)['summary'] for p in case.rglob('*.json')
                if p.name.startswith(('summary','pilot_summary'))]
            cost={'native_runs':len(summaries),'native_s':sum(s.get('elapsed_s',s.get('native_elapsed_s',0)) for s in summaries)}
            jobs.append({'scenario':sid,'directory':str(case),'cost':cost,'scope':'LOCAL_ENGINEERING_EVIDENCE_NOT_PERIODIC_PM_CERTIFICATION'})
            if sum(j['cost']['native_runs'] for j in jobs)>800:raise RuntimeError('predeclared local native budget exceeded')
    if source_identity()!=sources:raise RuntimeError('study source changed during execution')
    write_new(root/'complete.json',{'phase':args.phase,'jobs':jobs,'process_wall_s':time.perf_counter()-start,
        'end_unix':time.time(),'source_unchanged':True})


if __name__=='__main__':main()
