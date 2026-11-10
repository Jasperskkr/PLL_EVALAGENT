"""Independent fresh-extraction reproduction. All generated files stay in new paths."""
from pathlib import Path
import hashlib
import json
import math
import shutil
import subprocess
import sys
import time
from datetime import datetime,timezone
import zipfile

ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
ARCHIVE=ROOT/'delivery/stage6b_20261109_01/stage6b_candidate_01.zip'
EXTRACT=ROOT.parent.parent/'stage6b-bundlecheck-01'
EXPECTED='9933ccd0db323149fdb34b1fb4bd1b878cd926776ab1860af1f174a8ba612215'

def write(name,obj):
    with (OUT/name).open('x',encoding='utf-8') as f:json.dump(obj,f,indent=2,ensure_ascii=False)

def sha(path):
    d=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(4*1024*1024),b''):d.update(block)
    return d.hexdigest()

def command(name,argv,cwd):
    t=time.perf_counter();at=datetime.now(timezone.utc).isoformat()
    with (OUT/(name+'.stdout.txt')).open('xb') as stdout,(OUT/(name+'.stderr.txt')).open('xb') as stderr:
        p=subprocess.run(argv,cwd=cwd,stdout=stdout,stderr=stderr,check=False)
    r={'argv':argv,'cwd':str(cwd),'started_utc':at,'elapsed_s':time.perf_counter()-t,'returncode':p.returncode}
    write(name+'.receipt.json',r);print(json.dumps({'step':name,**r}),flush=True)
    if p.returncode:raise RuntimeError('COMMAND_FAILED:'+name)
    return r

try:
    t=time.perf_counter();at=datetime.now(timezone.utc).isoformat()
    assert sha(ARCHIVE)==EXPECTED,'archive SHA256 mismatch'
    EXTRACT.mkdir(exist_ok=False)
    with zipfile.ZipFile(ARCHIVE) as archive:
        assert archive.testzip() is None,'archive CRC failure'
        for row in archive.infolist():
            target=(EXTRACT/row.filename).resolve()
            assert target.is_relative_to(EXTRACT.resolve()),row.filename
        archive.extractall(EXTRACT)
        entries=len(archive.infolist())
    bundle=EXTRACT/'PLL_allocation'
    write('extraction.receipt.json',{'archive':str(ARCHIVE),'sha256':EXPECTED,'CRC':'PASS','entries':entries,'extraction_root':str(EXTRACT),
                                    'started_utc':at,'elapsed_s':time.perf_counter()-t})
    print('Extracted verified archive',entries,flush=True)
    command('manifest_before',[sys.executable,'-B','tools/package_stage6b.py','verify','--root','.'],bundle)
    for label in ('kernel','return_ratio','closed_loop'):
        command('build_'+label,['cmd','/c','pll_allocation\\verification\\build_'+label+'.cmd'],bundle)
    test_output=OUT/'test_output';test_output.mkdir(exist_ok=False)
    command('tests',[sys.executable,'-B','-m','pytest','-q','tests','-p','no:cacheprovider',
        '--basetemp='+str(test_output/'tmp'),'--junitxml='+str(test_output/'tests.xml')],bundle)
    command('reproduction',[sys.executable,'-B','tools/run_stage6b.py','--frozen','experiments/stage6b/frozen_02',
        '--out','experiments/stage6b/reproduction_01'],bundle)
    command('reproduction_audit',[sys.executable,'-B','tools/audit_stage6b.py','--study','experiments/stage6b/reproduction_01',
        '--out','experiments/stage6b/reproduction_summary_01'],bundle)
    command('manifest_after',[sys.executable,'-B','tools/package_stage6b.py','verify','--root','.'],bundle)
    sys.path.insert(0,str(ROOT))
    from pll_allocation.allocation.core import read
    from pll_allocation.physics_mapping.model import fingerprint
    rows=[];exact=True
    count_keys=('analytic_calls','M1_calls','candidate_generations','M2_calls','LLM_calls','M2_candidate_slots_used',
                'cache_hits','native_completed_runs','native_failed_attempts','integration_points')
    numeric=[]
    def compare_number(label,a,b,abs_tol):
        global exact
        if a is None or b is None:assert a==b,label;return
        diff=abs(a-b);same=(a==b);exact=exact and same
        assert math.isclose(a,b,rel_tol=1e-10,abs_tol=abs_tol),(label,a,b,diff)
        numeric.append({'metric':label,'original':a,'reproduced':b,'absolute_difference':diff,'exact':same,'absolute_tolerance':abs_tol,'relative_tolerance':1e-10})
    for name in ('B1_A','B1_B','B1_C','B2_A','B2_B','B2_C'):
        original=read(ROOT/'experiments/stage6b/study_01/runs'/name/'result.json')
        reproduced=read(bundle/'experiments/stage6b/reproduction_01/runs'/name/'result.json')
        assert original['status']==reproduced['status'] and original['stop_reason']==reproduced['stop_reason'],name
        assert original['final_parameter_sha256']==reproduced['final_parameter_sha256'],name
        assert original['FULL_SYSTEMSPEC_CERTIFIED']==reproduced['FULL_SYSTEMSPEC_CERTIFIED']==False
        assert {k:original['cost'][k] for k in count_keys}=={k:reproduced['cost'][k] for k in count_keys},name
        a,b=original['attempts'],reproduced['attempts'];assert len(a)==len(b),name
        for x,y in zip(a,b):
            assert (x['parameter_sha256'],x['reason'],x['cache_hit'])==(y['parameter_sha256'],y['reason'],y['cache_hit']),name
            assert x['evaluation']['research_joint_status']==y['evaluation']['research_joint_status'],name
            bx={r['metric_name']:r for r in x['evaluation']['constraints']};by={r['metric_name']:r for r in y['evaluation']['constraints']}
            assert set(bx)==set(by)
            for metric in bx:
                u,v=bx[metric],by[metric];assert u['verification_status']==v['verification_status'],(name,metric)
                tol=1e-12 if metric in ('lock_time_s','Vctrl_required_V') else 1e-7
                label=f'{name}/slot{x["candidate_slot"]}/{metric}'
                compare_number(label+'/value',u['measured_or_predicted_value'],v['measured_or_predicted_value'],tol)
                assert (u['numerical_envelope'] is None)==(v['numerical_envelope'] is None)
                for i,(p,q) in enumerate(zip(u['numerical_envelope'] or [],v['numerical_envelope'] or [])):
                    compare_number(label+'/envelope'+str(i),p,q,tol)
        rows.append({'run':name,'candidate_order_sha256':[r['parameter_sha256'] for r in a],
                     'final_selected_sha256':original['final_parameter_sha256'],'status':original['status'],
                     'cost_counts':{k:original['cost'][k] for k in count_keys},'status_candidate_order_final_and_counts':'IDENTICAL'})
    write('comparison.json',{'status':'PASS','all_compared_numeric_values_exact':exact,'runs':rows,'numeric_comparisons':numeric,
        'ignored':['timings','absolute paths','compiler binary identities','trace event hashes that include timings'],
        'tolerances':'relative1e-10; absolute1e-7 for Hz/deg,1e-12 for seconds/volts; actual differences recorded',
        'cost_scope':'additional package reproduction, separate from original formal study'})
    reproduced_root=OUT/'reproduced';reproduced_root.mkdir(exist_ok=False)
    for name in ('reproduction_01','reproduction_summary_01'):
        shutil.copytree(bundle/'experiments/stage6b'/name,reproduced_root/name)
    copied={}
    for p in reproduced_root.rglob('*'):
        if p.is_file():copied[p.relative_to(reproduced_root).as_posix()]={'sha256':sha(p),'bytes':p.stat().st_size}
    write('reproduced_manifest.json',{'files':copied,'source_root':str(bundle/'experiments/stage6b'),
        'destination_root':str(reproduced_root),'reference_mapping':'preserved relative artifact references experiments/stage6b/reproduction_01 map to this reproduced/reproduction_01 directory for packaged review',
        'excluded':'extracted source, DLL/build outputs; tests temp is outside reproduced'})
    for rel,row in copied.items():
        assert sha(bundle/'experiments/stage6b'/rel)==row['sha256'],rel
    write('receipt.json',{'status':'PASS','archive':str(ARCHIVE),'archive_sha256':EXPECTED,'extraction_root':str(EXTRACT),
        'comparison':'comparison.json','copied_reproduction_files':len(copied),'copied_reproduction_bytes':sum(v['bytes'] for v in copied.values()),
        'all_compared_numbers_exact':exact,'new_LLM_calls':0,'new_study':'independent additional full six-arm reproduction',
        'new_reproduction_cost':read(bundle/'experiments/stage6b/reproduction_summary_01/summary.json')})
    print('PASS: fresh source rebuild/tests/all-six reproduction/comparison and raw-evidence copy',flush=True)
except Exception as error:
    write('failure.json',{'type':type(error).__name__,'reason':str(error),'at':datetime.now(timezone.utc).isoformat()})
    raise
