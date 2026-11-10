"""Independent final ZIP streaming audit; reuses tested02 only after exact source match."""
from pathlib import Path,PurePosixPath
import hashlib,json,sys,time,zipfile,zlib
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent
DELIVERY=ROOT/'delivery/stage6b_20261109_03';ARCHIVE=DELIVERY/'PLL_Stage6B_reproducible_bundle.zip'
ZIP02=ROOT/'delivery/stage6b_20261109_02/PLL_Stage6B_reproducible_bundle.zip'
EXPECTED='9b1f47b4cadc2b26b97e4bf10f5a80dc487bc4f60c78cc1eb35fa59dbeb927db'
PREFIX='PLL_allocation/'
sys.path.insert(0,str(ROOT))
from pll_allocation.physics_mapping.model import fingerprint
from pll_allocation.allocation.core import read,write_new

def sha(path):
    d=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(4*1024*1024),b''):d.update(block)
    return d.hexdigest()

def decode(archive,relative):return json.loads(archive.read(PREFIX+relative).decode('utf-8'))

def chain(lines,label,expected_count=None):
    previous='0'*64;count=0
    for count,line in enumerate(lines,1):
        event=json.loads(line);digest=event.pop('event_sha256')
        assert event['index']==count and event['previous_sha256']==previous and fingerprint(event)==digest,label
        previous=digest
    if expected_count is not None:assert count==expected_count,(label,count)
    return {'path':label,'events':count,'final_sha256':previous}

try:
    start=time.perf_counter();at=datetime.now(timezone.utc).isoformat()
    assert ARCHIVE.stat().st_size==909378428 and sha(ARCHIVE)==EXPECTED,'archive identity mismatch'
    with zipfile.ZipFile(ARCHIVE) as archive,zipfile.ZipFile(ZIP02) as prior:
        infos=archive.infolist();assert len(infos)==12518
        assert len({i.filename for i in infos})==len(infos),'duplicate member path'
        actual={}
        for number,info in enumerate(infos,1):
            assert info.filename.startswith(PREFIX) and '..' not in PurePosixPath(info.filename).parts and not info.is_dir(),info.filename
            d=hashlib.sha256();crc=0;size=0
            with archive.open(info) as stream:
                for block in iter(lambda:stream.read(4*1024*1024),b''):
                    d.update(block);crc=zlib.crc32(block,crc);size+=len(block)
            assert crc==info.CRC and size==info.file_size,'CRC/SIZE:'+info.filename
            actual[info.filename[len(PREFIX):]]={'sha256':d.hexdigest(),'bytes':size}
            if number%3000==0:print('streamed members',number,flush=True)
        manifest=decode(archive,'BUNDLE_MANIFEST.json');assert len(manifest['files'])==12517
        declared={r['path']:{'sha256':r['sha256'],'bytes':r['bytes']} for r in manifest['files']}
        assert len(declared)==12517 and set(actual)==set(declared)|{'BUNDLE_MANIFEST.json'}
        for rel,row in declared.items():assert actual[rel]==row,rel
        old_manifest=decode(prior,'BUNDLE_MANIFEST.json');old={r['path']:{'sha256':r['sha256'],'bytes':r['bytes']} for r in old_manifest['files']}
        removed=sorted(set(old)-set(declared));added=sorted(set(declared)-set(old));changed=sorted(p for p in set(old)&set(declared) if old[p]!=declared[p])
        assert not removed
        assert changed==['tools/package_stage6b.py'],changed
        expected_receipt='delivery/stage6b_20261109_01/stage6b_candidate_01.zip.receipt.json'
        assert len(added)==26 and expected_receipt in added
        validation_added=[p for p in added if p.startswith('experiments/stage6b/package_validation_02/')]
        assert len(validation_added)==25 and set(added)==set(validation_added)|{expected_receipt},added
        runtime=[p for p in old if p.startswith(('pll_allocation/','configs/','tests/'))]
        assert all(old[p]==declared[p] for p in runtime)
        other_sources=[p for p in old if p.startswith(('tools/','docs/')) and p!='tools/package_stage6b.py']
        assert all(old[p]==declared[p] for p in other_sources)
        # Every added validation record must equal the completed original receipt/log bytes.
        for p in validation_added:assert sha(ROOT/p)==actual[p]['sha256'],p
        assert actual[expected_receipt]['sha256']=='53712e04e6d4e02553be63aee9022c7931328b9c09d72662cd44455a5470e7f6'
        # Sole source change selects the missing receipt into future exports.
        old_helper=prior.read(PREFIX+'tools/package_stage6b.py').decode('utf-8')
        new_helper=archive.read(PREFIX+'tools/package_stage6b.py').decode('utf-8')
        import difflib
        diff=''.join(difflib.unified_diff(old_helper.splitlines(True),new_helper.splitlines(True),fromfile='tested02',tofile='final03'))
        (OUT/'packaging_helper.diff').open('x',encoding='utf-8').write(diff)
        assert 'stage6b_candidate_01.zip.receipt.json' in diff
        frozen=decode(archive,'experiments/stage6b/frozen_02/plan.json')
        for row in frozen['sources']:assert actual[row['path']]['sha256']==row['sha256'],row['path']
        full_path='experiments/stage6b/trace_01/complete_trace.jsonl'
        lines=archive.read(PREFIX+full_path).decode('utf-8').splitlines();full=chain(lines,full_path,3938)
        trace_receipt=decode(archive,'experiments/stage6b/trace_01/receipt.json')
        assert full['final_sha256']==trace_receipt['chain_final_sha256'] and actual[full_path]['sha256']==trace_receipt['trace_sha256']
        refs=0;native=0;runtime_events=0;payloads={}
        for line in lines:
            event=json.loads(line);artifact=event.get('artifact')
            if artifact and event.get('sha256'):
                assert artifact in actual and actual[artifact]['sha256']==event['sha256'],artifact;refs+=1
            if event['event']=='PRESERVED_REALTIME_EVENT':
                if artifact not in payloads:payloads[artifact]=archive.read(PREFIX+artifact).decode('utf-8').splitlines()
                assert json.loads(payloads[artifact][event['line']-1])==event['original_event'],artifact
                refs+=1;runtime_events+=1
            if event['event']=='PRESERVED_NATIVE_EVIDENCE':
                native+=1
                if event.get('request'):
                    assert event['request'] in actual and actual[event['request']]['sha256']==event['request_sha256'],event['request'];refs+=1
        assert refs==6056 and runtime_events==1610 and native==2120,(refs,runtime_events,native)
        traces=[]
        for study in ('study_01','reproduction_01'):
            for name in ('B1_A','B1_B','B1_C','B2_A','B2_B','B2_C'):
                directory='experiments/stage6b/'+study+'/runs/'+name
                trace=chain(archive.read(PREFIX+directory+'/allocation_trace.jsonl').decode('utf-8').splitlines(),directory+'/allocation_trace.jsonl')
                assert trace['final_sha256']==decode(archive,directory+'/result.json')['trace_final_sha256'];traces.append(trace)
        tested02=decode(archive,'experiments/stage6b/package_validation_02/acceptance_receipt.json')
        assert tested02['tests']['passed']==407 and tested02['native_fresh_rebuilds']==3
        assert tested02['archive_sha256']=='c22e37c83b6308c638d9dbaa9c543f50f18bbab439b89a5f03ac6cb3b5d60733'
        exact01=decode(archive,'experiments/stage6b/package_validation_01/comparison.json')
        assert exact01['status']=='PASS' and exact01['all_compared_numeric_values_exact'] and len(exact01['numeric_comparisons'])==156
        write_new(OUT/'audit_details.json',{'status':'PASS','streamed_members':len(infos),'streamed_uncompressed_bytes':sum(v['bytes'] for v in actual.values()),
            'manifest_files':len(declared),'removed':removed,'added':added,'changed':changed,'runtime_config_test_files_unchanged':len(runtime),
            'other_tools_docs_unchanged':len(other_sources),'packaging_helper_change':'only export file selection; diff recorded, no runtime/test behavior change',
            'frozen_plan_sources_verified':len(frozen['sources']),'complete_trace':full,'artifact_request_payload_refs_verified':refs,
            'runtime_events_preserved':runtime_events,'native_evidence_records':native,'method_trace_chains':traces,
            'source02_acceptance':tested02,'candidate01_exact_reproduction_comparison_sha256':actual['experiments/stage6b/package_validation_01/comparison.json']['sha256']})
    assert sha(ARCHIVE)==EXPECTED,'archive changed during validation'
    receipt={'status':'PASS','archive':str(ARCHIVE),'archive_sha256':EXPECTED,'archive_bytes':909378428,'archive_entries':12518,
        'CRC':'PASS_ALL_MEMBERS_STREAMED','manifest_files_verified':12517,'full_trace_events':3938,'artifact_request_payload_refs_verified':6056,
        'runtime_events_preserved':1610,'native_evidence_records':2120,'method_trace_chains_verified':12,'missing_references':0,
        'source_test_basis':{'archive02_sha256':tested02['archive_sha256'],'fresh_native_rebuilds':3,'tests_passed':407,
            'tests_failed':0,'without_git':True,'source_runtime_config_tests_and_all_other_tools_docs':'BYTE_IDENTICAL',
            'sole_source_difference':'tools/package_stage6b.py export selection adds historical receipt; no runtime effect'},
        'six_arm_reproduction_basis':{'candidate01_sha256':'9933ccd0db323149fdb34b1fb4bd1b878cd926776ab1860af1f174a8ba612215',
            'comparison':'all6candidate order/final/constraints/costs identical;156numeric values exact','runtime_source':'BYTE_IDENTICAL'},
        'new_LLM_calls':0,'new_M2_study_calls':0,'new_test_runs':0,'archive_or_sources_modified':False,
        'started_utc':at,'completed_utc':datetime.now(timezone.utc).isoformat(),'elapsed_s':time.perf_counter()-start,'audit_root':str(OUT),
        'prior02_failure':'preserved, single missing historical delivery receipt fixed by adding exact original bytes'}
    write_new(OUT/'acceptance_receipt.json',receipt);write_new(DELIVERY/'FINAL_INDEPENDENT_ACCEPTANCE.json',receipt)
    print(json.dumps(receipt),flush=True)
except Exception as error:
    write_new(OUT/'failure.json',{'type':type(error).__name__,'reason':str(error),'at':datetime.now(timezone.utc).isoformat()})
    raise
