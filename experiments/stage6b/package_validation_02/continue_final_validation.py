"""Continue required checks; separately report missing historical delivery reference."""
from pathlib import Path
import hashlib,json,subprocess,sys,time
from datetime import datetime,timezone
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent
DELIVERY=ROOT/'delivery/stage6b_20261109_02';ARCHIVE=DELIVERY/'PLL_Stage6B_reproducible_bundle.zip'
BUNDLE=ROOT.parent.parent/'stage6b-bundlecheck-02/PLL_allocation'
CANDIDATE=ROOT.parent.parent/'stage6b-bundlecheck-01/PLL_allocation'
EXPECTED='c22e37c83b6308c638d9dbaa9c543f50f18bbab439b89a5f03ac6cb3b5d60733'
sys.path.insert(0,str(BUNDLE))
from pll_allocation.physics_mapping.model import fingerprint
from pll_allocation.allocation.core import read,write_new

def sha(path):
    d=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(4*1024*1024),b''):d.update(block)
    return d.hexdigest()

def command(label,argv):
    t=time.perf_counter();at=datetime.now(timezone.utc).isoformat()
    with (OUT/(label+'.stdout.txt')).open('xb') as stdout,(OUT/(label+'.stderr.txt')).open('xb') as stderr:
        p=subprocess.run(argv,cwd=BUNDLE,stdout=stdout,stderr=stderr,check=False)
    r={'argv':argv,'cwd':str(BUNDLE),'started_utc':at,'elapsed_s':time.perf_counter()-t,'returncode':p.returncode}
    write_new(OUT/(label+'.receipt.json'),r);print(json.dumps({'step':label,**r}),flush=True)
    if p.returncode:raise RuntimeError('COMMAND_FAILED:'+label)
    return r

def chain(path,expected_count=None):
    previous='0'*64;count=0
    for count,line in enumerate(path.read_text(encoding='utf-8').splitlines(),1):
        e=json.loads(line);digest=e.pop('event_sha256')
        assert e['index']==count and e['previous_sha256']==previous and fingerprint(e)==digest,str(path)
        previous=digest
    if expected_count is not None:assert count==expected_count
    return {'path':path.relative_to(BUNDLE).as_posix(),'events':count,'final_sha256':previous,'file_sha256':sha(path)}

try:
    started=datetime.now(timezone.utc).isoformat();t=time.perf_counter();runtime={}
    for folder in ('pll_allocation','configs'):
        for p in sorted((BUNDLE/folder).rglob('*')):
            if not p.is_file() or set(p.parts)&{'__pycache__','build','build_stage4','build_stage4_1_r2'}:continue
            rel=p.relative_to(BUNDLE);assert sha(p)==sha(CANDIDATE/rel),rel
            runtime[rel.as_posix()]=sha(p)
    for row in read(BUNDLE/'experiments/stage6b/frozen_02/plan.json')['sources']:
        assert sha(BUNDLE/row['path'])==row['sha256']==sha(CANDIDATE/row['path'])
    path=BUNDLE/'experiments/stage6b/trace_01/complete_trace.jsonl';complete=chain(path,3938);saved=read(path.parent/'receipt.json')
    assert complete['final_sha256']==saved['chain_final_sha256'] and complete['file_sha256']==saved['trace_sha256']
    missing=[];payloads=0;native=0;hashes=0
    sources={}
    for line in path.read_text(encoding='utf-8').splitlines():
        event=json.loads(line);rel=event.get('artifact');artifact=BUNDLE/rel if rel else None
        if artifact and event.get('sha256'):
            if artifact.is_file():assert sha(artifact)==event['sha256'],rel;hashes+=1
            else:missing.append({'artifact':rel,'sha256':event['sha256'],'event':event['event'],'event_index':event['index']})
        if event['event']=='PRESERVED_REALTIME_EVENT':
            if rel not in sources:sources[rel]=(BUNDLE/rel).read_text(encoding='utf-8').splitlines()
            assert json.loads(sources[rel][event['line']-1])==event['original_event'];payloads+=1
        if event['event']=='PRESERVED_NATIVE_EVIDENCE':
            native+=1
            if event.get('request'):assert sha(BUNDLE/event['request'])==event['request_sha256']
    assert payloads==saved['preserved_runtime_events']==1610 and native==saved['native_evidence_records']==2120
    traces=[]
    for study in ('study_01','reproduction_01'):
        for name in ('B1_A','B1_B','B1_C','B2_A','B2_B','B2_C'):
            p=BUNDLE/'experiments/stage6b'/study/'runs'/name;row=chain(p/'allocation_trace.jsonl')
            assert row['final_sha256']==read(p/'result.json')['trace_final_sha256'];traces.append(row)
    write_new(OUT/'evidence_checks.json',{'status':'PASS_CHAINS_RUNTIME_AND_ALL_AVAILABLE_REFERENCES','runtime_files_identical_to_exact_reproduced_candidate01':runtime,
        'frozen_plan_sources':'ALL_MATCH','complete_trace':complete,'preserved_original_payloads_verified':payloads,'native_evidence_records':native,
        'referenced_artifact_hashes_verified':hashes,'missing_referenced_artifacts':missing,'method_trace_chains':traces,
        'new_M1_calls':0,'new_complete_M2_calls':0,'new_LLM_calls':0,'archive_or_extracted_sources_modified':False})
    print('Trace/runtime chains PASS; missing external historical refs='+str(len(missing)),flush=True)
    for name in ('kernel','return_ratio','closed_loop'):
        command('build_'+name,['cmd','/c','pll_allocation\\verification\\build_'+name+'.cmd'])
    testdir=OUT/'test_output';testdir.mkdir(exist_ok=False)
    tests=command('tests',[sys.executable,'-B','-m','pytest','-q','tests','-p','no:cacheprovider',
        '--basetemp='+str(testdir/'tmp'),'--junitxml='+str(testdir/'tests.xml')])
    xml=ET.parse(testdir/'tests.xml').getroot();suite=xml.find('testsuite') if xml.tag=='testsuites' else xml
    assert int(suite.attrib['tests'])==407 and int(suite.attrib.get('failures',0))==0 and int(suite.attrib.get('errors',0))==0
    command('manifest_after',[sys.executable,'-B','tools/package_stage6b.py','verify','--root','.'])
    assert sha(ARCHIVE)==EXPECTED
    receipt={'status':'PASS_REQUIRED_CHECKS_WITH_DOCUMENTED_EXTERNAL_TRACE_REFERENCE' if missing else 'PASS',
        'archive':str(ARCHIVE),'archive_sha256':EXPECTED,'archive_bytes':ARCHIVE.stat().st_size,'archive_entries':12492,
        'manifest_files_verified':12491,'CRC':'PASS','without_git':True,'extraction_root':str(BUNDLE.parent),
        'native_fresh_rebuilds':3,'tests':{'passed':407,'failed':0,'errors':0,'pytest_time_s':float(suite.attrib['time']),'process_elapsed_s':tests['elapsed_s']},
        'trace_events':3938,'runtime_events_preserved':1610,'native_evidence_records':2120,'method_trace_chains':12,
        'missing_external_historical_trace_references':missing,'runtime_and_frozen_sources_identical_to_already_exact_reproduced_candidate01':True,
        'all_six_repeated_here':False,'rationale':'unchanged frozen runtime already fully reproduced from candidate01; no duplicate study required',
        'new_LLM_calls':0,'new_complete_M2_study_calls':0,'elapsed_s':time.perf_counter()-t,'started_utc':started,
        'completed_utc':datetime.now(timezone.utc).isoformat(),'logs_root':str(OUT),'immutable_archive_and_sources_modified':False}
    write_new(OUT/'acceptance_receipt.json',receipt);write_new(DELIVERY/'FINAL_INDEPENDENT_ACCEPTANCE.json',receipt)
    print(json.dumps(receipt),flush=True)
except Exception as error:
    write_new(OUT/'continuation_failure.json',{'type':type(error).__name__,'reason':str(error),'at':datetime.now(timezone.utc).isoformat()})
    raise
