"""Read-only result, preservation, plan and judgment audit. No M2/LLM calls."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'experiments/stage6a'))
from study import read,write_new,load_inputs,fingerprint,check_parameters
from pll_allocation.physics_mapping.registry import load_registry
from pll_allocation.pipeline_contracts import check_result


def audit(out,summary):
    out=Path(out);out.mkdir(parents=True,exist_ok=False);checks=[]
    def check(name,condition,**evidence):
        checks.append({'name':name,'passed':bool(condition),**evidence})
    root=ROOT/'experiments/stage6a';plan=read(root/'frozen_01/experiment_plan.json')
    check('plan_digest',fingerprint({k:v for k,v in plan.items() if k!='plan_sha256'})==plan['plan_sha256'])
    for name,h in plan['source_identity'].items():check('frozen_source:'+name,hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==h)
    cfg,model,_,protocol=load_inputs();load_registry(ROOT/'docs/stage4_2/PHYSICS_MAPPING_REGISTRY.json',root=ROOT)
    check('Registry_binding',True)
    rows=list(csv.DictReader((summary/'candidate_results.csv').open(encoding='utf-8')))
    check('complete_M2_budget',len(rows)<=plan['max_complete_M2'])
    native=0;elapsed=0.;costs=[]
    for row in rows:
        n=row['candidate'];base=ROOT/row['evidence_directory'];item=read(base/'attempt_001/AllocationProposal.json')
        result=read(base/'attempt_001/BehavioralVerificationResult.json');run=read(base/'result.json');detail=read(summary/(n+'.json'))
        check_result(result,item,protocol);check(n+':formal_result_binding',True)
        check(n+':candidate_hash',fingerprint(item['joint_block_spec'])==detail['parameter_sha256']==result['parameter_sha256'])
        d=check_parameters(model,item['joint_block_spec']);check(n+':original_domain',d['declared_domain']=='IN_DECLARED_DOMAIN' and d['model_validity']=='VALID')
        check(n+':not_full_certification',not result['verified_joint_block_spec'] and not detail['judgment']['FULL_SYSTEMSPEC_CERTIFIED'])
        check(n+':strict_PM_unknown',result['metrics']['PM_deg']['value'] is None and result['metrics']['PM_deg']['status']=='PM_M2_UNKNOWN')
        check(n+':real_M2',run['cost']['M2_calls']==1 and run['cost']['native_completed_runs']>2 and run['cost']['LLM_calls']==0)
        if n in plan['candidate_bindings']:
            check(n+':prewritten_candidate_binding',item['parameter_sha256']==plan['candidate_bindings'][n]['parameter_sha256'])
        cap=read(base/'raw/attempt_001/capture/comparison.json')
        check(n+':fixed_initial_condition',cap['initial_control_V']==.15 and cap['duration_s']==160e-6)
        check(n+':two_capture_steps',all((base/'raw/attempt_001/capture'/key/'summary.json').is_file() for key in ['coarse','fine']))
        parts=[]
        for p in (base/'raw').rglob('summary.json'):
            s=read(p)['summary'];parts.append(s)
        check(n+':native_count',len(parts)==run['cost']['native_completed_runs'])
        check(n+':native_elapsed',abs(sum(s['elapsed_s'] for s in parts)-run['cost']['native_elapsed_s'])<1e-9)
        native+=len(parts);elapsed+=sum(s['elapsed_s'] for s in parts)
        check(n+':submission_before_M2_trace',[(e['event']) for e in [json.loads(x) for x in (base/'allocation_trace.jsonl').read_text().splitlines()]].index('SUBMISSION_SAVED') < [(e['event']) for e in [json.loads(x) for x in (base/'allocation_trace.jsonl').read_text().splitlines()]].index('M2_STARTED'))
    s=read(summary/'summary.json');check('aggregate_native_runs',s['native_runs']==native);check('aggregate_native_seconds',abs(s['native_elapsed_s']-elapsed)<1e-9)
    h=read(summary/'Stage5_S3_random11_regression.json')['judgment']
    check('Stage5_counterexample_preserved',h['BW_status']=='PASS' and not h['M1_PREDICTED_FEASIBLE'] and h['research_joint_status']=='FAIL')
    check('E1_boundary_reliable_fail',read(summary/'E1_upper_shape.json')['judgment']['BW_status']=='FAIL')
    check('baseline_semantics',read(root/'m2_01/E0_baseline_comparison.json')['all_passed'])
    before=read(root/'safety_01/baseline_files.json');safety=read(root/'safety_01/safety_receipt.json');original=Path(safety['source_root'])
    original_changed=[];isolated_changed=[]
    allowed={'docs/DECISIONS.md','docs/PROJECT_STATUS.md'}
    for name,v in before.items():
        for base,changes in [(original,original_changed),(ROOT,isolated_changed)]:
            p=base/name
            if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=v['sha256']:changes.append(name)
    check('original_14709_files_unchanged',not original_changed,changes=original_changed)
    check('isolated_inherited_files_only_authorized_status_appends',set(isolated_changed)<=allowed,changes=isolated_changed)
    for n in safety['missing_tracked_preserved']:check('original_missing_preserved:'+n,not (original/n).exists())
    command=['git','-c','core.quotepath=false','status','--short']
    status=subprocess.run(command,cwd=original,capture_output=True,check=True).stdout.decode('utf-8')
    check('original_git_status_unchanged',status==safety['source_status'])
    head=subprocess.run(['git','rev-parse','HEAD'],cwd=original,capture_output=True,check=True).stdout.decode().strip()
    check('master_untouched',head==safety['HEAD'])
    branch=subprocess.run(['git','branch','--show-current'],cwd=ROOT,capture_output=True,check=True).stdout.decode().strip()
    check('isolated_research_branch',branch=='codex/stage6a-multispec-feasibility')
    result={'status':'PASS' if all(c['passed'] for c in checks) else 'FAIL','checks':len(checks),'failed':[c for c in checks if not c['passed']],
        'original_files_checked':len(before),'original_changes':original_changed,'isolated_inherited_changes':isolated_changed,
        'complete_M2':len(rows),'native_runs':native,'native_elapsed_s':elapsed,'new_M2_or_LLM_calls':0,'details':checks}
    write_new(out/'audit.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='details'},indent=2))
    if result['status']!='PASS':raise SystemExit(1)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path);p.add_argument('--summary',required=True,type=Path);a=p.parse_args();audit(a.out,a.summary)
