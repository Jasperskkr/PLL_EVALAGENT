"""Final immutable ZIP validation. No allocation experiment is repeated."""
from pathlib import Path
import hashlib,json,subprocess,sys,time,zipfile
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
DELIVERY=ROOT/'delivery/stage6b_20261109_02'
ARCHIVE=DELIVERY/'PLL_Stage6B_reproducible_bundle.zip'
EXTRACT=ROOT.parent.parent/'stage6b-bundlecheck-02'
CANDIDATE=ROOT.parent.parent/'stage6b-bundlecheck-01/PLL_allocation'
EXPECTED='c22e37c83b6308c638d9dbaa9c543f50f18bbab439b89a5f03ac6cb3b5d60733'

def write(path,obj):
    with path.open('x',encoding='utf-8') as f:json.dump(obj,f,indent=2,ensure_ascii=False)

def sha(path):
    d=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(4*1024*1024),b''):d.update(block)
    return d.hexdigest()

def command(label,argv,cwd):
    start=time.perf_counter();at=datetime.now(timezone.utc).isoformat()
    with (OUT/(label+'.stdout.txt')).open('xb') as stdout,(OUT/(label+'.stderr.txt')).open('xb') as stderr:
        p=subprocess.run(argv,cwd=cwd,stdout=stdout,stderr=stderr,check=False)
    record={'argv':argv,'cwd':str(cwd),'started_utc':at,'elapsed_s':time.perf_counter()-start,'returncode':p.returncode}
    write(OUT/(label+'.receipt.json'),record);print(json.dumps({'step':label,**record}),flush=True)
    if p.returncode:raise RuntimeError('COMMAND_FAILED:'+label)
    return record

try:
    started=datetime.now(timezone.utc).isoformat();t=time.perf_counter()
    assert ARCHIVE.stat().st_size==909348223
    assert sha(ARCHIVE)==EXPECTED,'archive SHA256 mismatch'
    EXTRACT.mkdir(exist_ok=False)
    with zipfile.ZipFile(ARCHIVE) as archive:
        assert len(archive.infolist())==12492
        assert archive.testzip() is None,'CRC failure'
        for entry in archive.infolist():
            assert (EXTRACT/entry.filename).resolve().is_relative_to(EXTRACT.resolve()),entry.filename
        archive.extractall(EXTRACT)
    bundle=EXTRACT/'PLL_allocation'
    assert not (bundle/'.git').exists()
    write(OUT/'extraction.receipt.json',{'archive':str(ARCHIVE),'sha256':EXPECTED,'CRC':'PASS','archive_bytes':ARCHIVE.stat().st_size,
        'entries':12492,'extraction_root':str(EXTRACT),'without_git':True,'started_utc':started,'elapsed_s':time.perf_counter()-t})
    print('Verified final archive SHA/CRC; extracted12492entries',flush=True)
    command('manifest_before',[sys.executable,'-B','tools/package_stage6b.py','verify','--root','.'],bundle)
    runtime={}
    for folder in ('pll_allocation','configs'):
        for p in sorted((bundle/folder).rglob('*')):
            if not p.is_file() or set(p.parts)&{'__pycache__','build','build_stage4','build_stage4_1_r2'}:continue
            rel=p.relative_to(bundle);old=CANDIDATE/rel
            assert old.is_file() and sha(p)==sha(old),'RUNTIME_DIFFERENCE:'+rel.as_posix()
            runtime[rel.as_posix()]=sha(p)
    # The freeze also binds test and study-driver version, separately from runnable package.
    for row in json.loads((bundle/'experiments/stage6b/frozen_02/plan.json').read_text(encoding='utf-8'))['sources']:
        assert sha(bundle/row['path'])==row['sha256'],row['path']
        assert sha(bundle/row['path'])==sha(CANDIDATE/row['path']),row['path']
    sys.path.insert(0,str(bundle))
    from pll_allocation.physics_mapping.model import fingerprint
    from pll_allocation.allocation.core import read
    def chain(path,expected_count=None):
        previous='0'*64;count=0
        for count,line in enumerate(path.read_text(encoding='utf-8').splitlines(),1):
            event=json.loads(line);digest=event.pop('event_sha256')
            assert event['index']==count and event['previous_sha256']==previous and fingerprint(event)==digest,str(path)
            previous=digest
        if expected_count is not None:assert count==expected_count,(path,count)
        return {'path':path.relative_to(bundle).as_posix(),'events':count,'final_sha256':previous,'file_sha256':sha(path)}
    complete_path=bundle/'experiments/stage6b/trace_01/complete_trace.jsonl'
    full=chain(complete_path,3938);full_receipt=read(complete_path.parent/'receipt.json')
    assert full['final_sha256']==full_receipt['chain_final_sha256'] and full['file_sha256']==full_receipt['trace_sha256']
    preserved=0;native=0;artifact_hashes=0;payloads=0
    for line in complete_path.read_text(encoding='utf-8').splitlines():
        event=json.loads(line);artifact=event.get('artifact')
        if artifact and event.get('sha256'):
            assert sha(bundle/artifact)==event['sha256'],artifact;artifact_hashes+=1
        if event['event']=='PRESERVED_REALTIME_EVENT':
            preserved+=1
            source_line=(bundle/artifact).read_text(encoding='utf-8').splitlines()[event['line']-1]
            assert json.loads(source_line)==event['original_event'],artifact;payloads+=1
        if event['event']=='PRESERVED_NATIVE_EVIDENCE':
            native+=1
            if event.get('request'):assert sha(bundle/event['request'])==event['request_sha256']
    assert preserved==full_receipt['preserved_runtime_events']==1610
    assert native==full_receipt['native_evidence_records']==2120
    traces=[]
    for study in ('study_01','reproduction_01'):
        for name in ('B1_A','B1_B','B1_C','B2_A','B2_B','B2_C'):
            directory=bundle/'experiments/stage6b'/study/'runs'/name
            row=chain(directory/'allocation_trace.jsonl')
            assert row['final_sha256']==read(directory/'result.json')['trace_final_sha256']
            traces.append(row)
    write(OUT/'evidence_checks.json',{'status':'PASS','runtime_files_identical_to_exact_reproduced_candidate01':runtime,
        'frozen_plan_sources':'ALL_MATCH','complete_trace':full,'complete_trace_preserved_events':preserved,
        'complete_trace_native_records':native,'referenced_artifact_hashes_verified':artifact_hashes,'preserved_original_payloads_verified':payloads,
        'method_trace_chains':traces,'new_M1_calls':0,'new_complete_M2_calls':0,'new_LLM_calls':0,
        'reproduction_basis':'all runtime/config and frozen source bytes match candidate01, whose all-six outputs were numerically exact; no study rerun'})
    print('Trace/frozen/runtime checks PASS',flush=True)
    builds=[]
    for name in ('kernel','return_ratio','closed_loop'):
        builds.append(command('build_'+name,['cmd','/c','pll_allocation\\verification\\build_'+name+'.cmd'],bundle))
    testdir=OUT/'test_output';testdir.mkdir(exist_ok=False)
    tests=command('tests',[sys.executable,'-B','-m','pytest','-q','tests','-p','no:cacheprovider',
        '--basetemp='+str(testdir/'tmp'),'--junitxml='+str(testdir/'tests.xml')],bundle)
    import xml.etree.ElementTree as ET
    xml=ET.parse(testdir/'tests.xml').getroot();suite=xml.find('testsuite') if xml.tag=='testsuites' else xml
    assert int(suite.attrib['tests'])==407 and int(suite.attrib.get('failures',0))==0 and int(suite.attrib.get('errors',0))==0
    command('manifest_after',[sys.executable,'-B','tools/package_stage6b.py','verify','--root','.'],bundle)
    receipt={'status':'PASS','archive':str(ARCHIVE),'archive_sha256':EXPECTED,'archive_bytes':ARCHIVE.stat().st_size,
        'archive_entries':12492,'manifest_files_verified':12491,'CRC':'PASS','without_git':True,'extraction_root':str(EXTRACT),
        'native_fresh_rebuilds':3,'tests':{'passed':407,'failed':0,'errors':0,'pytest_time_s':float(suite.attrib['time']),'process_elapsed_s':tests['elapsed_s']},
        'trace_events':3938,'runtime_events_preserved':1610,'native_evidence_records':2120,'method_trace_chains':12,
        'runtime_and_frozen_sources_identical_to_already_exact_reproduced_candidate01':True,
        'all_six_repeated_here':False,'rationale':'unchanged frozen runtime already fully reproduced from candidate01; no duplicate study required',
        'new_LLM_calls':0,'new_complete_M2_study_calls':0,'elapsed_s':time.perf_counter()-t,'completed_utc':datetime.now(timezone.utc).isoformat(),
        'logs_root':str(OUT),'immutable_archive_and_sources_modified':False}
    write(OUT/'acceptance_receipt.json',receipt)
    write(DELIVERY/'FINAL_INDEPENDENT_ACCEPTANCE.json',receipt)
    assert sha(ARCHIVE)==EXPECTED
    print(json.dumps(receipt),flush=True)
except Exception as error:
    write(OUT/'failure.json',{'type':type(error).__name__,'reason':str(error),'at':datetime.now(timezone.utc).isoformat()})
    raise
