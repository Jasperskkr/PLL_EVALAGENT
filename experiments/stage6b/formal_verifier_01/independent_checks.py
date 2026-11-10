"""Verifier-only, read-only formal evidence audit. No model/TB execution."""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from pll_allocation.allocation.core import read, write_new
from pll_allocation.physics_mapping.model import fingerprint
from pll_allocation.pipeline_contracts import load_inputs, check_result
from pll_allocation.allocation.multispec_constraints import evaluate_constraints

OUT=Path(__file__).resolve().parent
STUDY=ROOT/'experiments/stage6b/study_01'
config,model,formal_spec,protocol=load_inputs()
checks=[];native_requests=0;native_integration_points=0;children_seen=set()
for name in ('B1_A','B1_B','B1_C','B2_A','B2_B','B2_C'):
    directory=STUDY/'runs'/name
    result=read(directory/'result.json');problem=read(directory/'problem.json')
    events=[json.loads(line) for line in (directory/'allocation_trace.jsonl').read_text(encoding='utf-8').splitlines()]
    previous='0'*64
    for i,event in enumerate(events,1):
        event=dict(event);digest=event.pop('event_sha256')
        assert event['index']==i and event['previous_sha256']==previous and fingerprint(event)==digest
        previous=digest
    assert previous==result['trace_final_sha256']
    submitted={e['candidate_slot']:e['index'] for e in events if e['event']=='SUBMISSION_SAVED_BEFORE_TB'}
    for e in events:
        if e['event'] in ('M2_STARTED','CACHE_HIT'):
            assert submitted[e['candidate_slot']]<e['index']
    local_new=0;local_hits=0;local_native=0
    for attempt in result['attempts']:
        candidate=directory/attempt['directory'];record=read(candidate/'proposal.json')
        assessment=read(candidate/'runner_M1_recheck.json');measured=read(candidate/'BehavioralVerificationResult.json')
        evaluation=evaluate_constraints(model,problem,record['candidate'],assessment,measured)
        assert evaluation==attempt['evaluation']==read(candidate/'joint_evaluation.json')
        reference=read(candidate/'M2_evidence_reference.json');origin=ROOT/reference['child_path']
        proposal=read(origin/'attempt_001/AllocationProposal.json')
        original=read(origin/'attempt_001/BehavioralVerificationResult.json')
        check_result(original,proposal,protocol)
        assert original==measured and fingerprint(record['candidate'])==proposal['parameter_sha256']
        cache=read(ROOT/reference['cache_entry'])
        actual=[{'path':p.relative_to(origin).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
                for p in sorted(origin.rglob('*')) if p.is_file()]
        assert actual==cache['artifacts']
        child_events=[json.loads(line) for line in (origin/'allocation_trace.jsonl').read_text(encoding='utf-8').splitlines()]
        assert next(i for i,e in enumerate(child_events) if e['event']=='SUBMISSION_SAVED') < next(i for i,e in enumerate(child_events) if e['event']=='M2_STARTED')
        if attempt['cache_hit']:
            local_hits+=1;assert attempt['new_M2_cost']=={}
        else:
            local_new+=1;local_native+=attempt['new_M2_cost']['native_completed_runs']
            assert origin not in children_seen
        if origin not in children_seen:
            children_seen.add(origin)
            raw=origin/'raw/attempt_001'
            assert {p.name for p in raw.iterdir() if p.is_dir()}=={'capture','base','amplitude_half','step_half','window_double'}
            capture_requests=list((raw/'capture').rglob('request.json'));assert len(capture_requests)==2
            settings=[read(p)['settings'] for p in capture_requests]
            assert sorted(s['dt_s'] for s in settings)==[.2e-9,.4e-9]
            assert all(s['initial_control_V']==.15 and s['duration_s']==160e-6 for s in settings)
            requests=list(raw.rglob('request.json'));assert len(requests)==106
            for p in requests:
                r=read(p)
                assert r['parameters']==record['candidate'] and r['protocol_sha256']==fingerprint(protocol) and r['protocol_document']==protocol
                summary=read(p.parent/'summary.json')['summary'];native_integration_points+=summary['integration_points']
            native_requests+=len(requests)
        statuses=[r['verification_status'] for r in evaluation['constraints']]
        if evaluation['research_joint_status']=='RESEARCH_JOINT_FEASIBLE':assert all(s=='PASS' for s in statuses)
        assert evaluation['FULL_SYSTEMSPEC_CERTIFIED'] is False
    assert local_new==result['cost']['M2_calls'] and local_hits==result['cost']['cache_hits']
    assert len(result['attempts'])==result['cost']['M2_candidate_slots_used']
    assert local_native==result['cost']['native_completed_runs']
    assert result['cost']['M2_candidate_slots_used']<=6 and result['cost']['M1_calls']<=96 and result['cost']['analytic_calls']<=10000
    checks.append({'run':name,'trace_events':len(events),'candidate_slots':len(result['attempts']),'new_M2':local_new,
                   'cache_hits':local_hits,'native':local_native,'status':result['status'],'stop_reason':result['stop_reason']})
summary=read(ROOT/'experiments/stage6b/summary_01/summary.json')
assert native_requests==summary['native_completed_runs']==1060
assert native_integration_points==sum(c['integration_points'] for c in summary['cost_by_run'].values())
for r in read(ROOT/'experiments/stage6b/frozen_02/plan.json')['sources']:
    assert hashlib.sha256((ROOT/r['path']).read_bytes()).hexdigest()==r['sha256']
write_new(OUT/'independent_checks.json',{'status':'PASS','runs':checks,'native_requests_bound':native_requests,
    'native_integration_points':native_integration_points,'unique_immutable_children':len(children_seen),
    'recomputed_joint_evaluations':sum(r['candidate_slots'] for r in checks),'new_M1_calls':0,'new_M2_calls':0,
    'checked':['frozen source/config hashes','hash-chain and pre-TB persistence order','full current joint re-evaluation',
        'original result contract','full cache subtree SHA/length inventory','106 original requests per unique complete M2',
        'capture .15V/160us and .4/.2ns pair','all native candidate/protocol bindings','new/cache cost separation','full certification false']})
print('PASS: 13 candidate evaluations, 10 immutable full M2 trees, 1060 native requests; zero new simulations')
