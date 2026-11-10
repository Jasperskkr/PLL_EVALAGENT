"""Independent post-run assertions and protected-history audit; read-only study inputs."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys
from collections import defaultdict

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from pll_allocation.allocation.core import read,write_new
from pll_allocation.scenarios import load_scenario
from pll_allocation.pipeline_contracts import load_inputs,check_result
from pll_allocation.physics_mapping.model import fingerprint


def main():
    p=argparse.ArgumentParser();p.add_argument('--firstshot',type=Path,required=True);p.add_argument('--repair',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--summary',type=Path);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    checks=[]
    def check(name,condition,details=None):checks.append({'name':name,'passed':bool(condition),'details':details})
    cfg,model,_,protocol=load_inputs();plan=read(ROOT/'experiments/stage5/experiment_plan_frozen.json')
    first=read(a.firstshot/'complete.json');repair=read(a.repair/'complete.json')
    check('all25_predeclared_arms_preserved',len(first['jobs'])==25)
    check('phaseA_complete_before_phaseB',first['end_unix']<=read(a.repair/'manifest.json')['start_unix'])
    costs=defaultdict(int);hashes=defaultdict(set)
    for phase,jobs in [('FIRST_SHOT',first['jobs']),('REPAIR',repair['jobs'])]:
        for job in jobs:
            folder=Path(job['directory']);result=read(folder/'result.json');manifest=read(folder/'run_manifest.json')
            binding=result['scenario_binding'];sid=binding['scenario_id'];scene,spec,actual=load_scenario(ROOT/f'experiments/stage5/scenarios/{sid}.json',cfg,load_inputs()[2])
            check(job['arm']+phase+'_binding',binding==actual and manifest['scenario_binding']==actual)
            check(job['arm']+phase+'_no_pipeline_error',result['status']!='PIPELINE_ERROR',result.get('failure'))
            costs[job['arm']]+=result['cost']['M2_calls']
            if sid=='S4':
                check(job['arm']+'_infeasible_no_sim_or_LLM',result['status']=='INFEASIBLE_UNDER_M1_ASSUMPTIONS' and result['cost']['M2_calls']==result['cost']['LLM_calls']==0)
            for attempt in result['attempts']:
                path=folder/attempt['directory'];item=read(path/'AllocationProposal.json')
                check(job['arm']+phase+'_persisted_candidate',read(path/'submitted_joint_block_spec.json')==item['joint_block_spec'])
                check(job['arm']+phase+'_effective_spec',item['system_spec']==spec and item['M1']['scenario_binding']==binding)
                hashes[(job['arm'],phase)].add(item['parameter_sha256'])
                if (path/'BehavioralVerificationResult.json').exists():
                    measured=read(path/'BehavioralVerificationResult.json');check_result(measured,item,protocol)
                    check(job['arm']+phase+'_no_full_pass',not measured['verified_joint_block_spec'] and measured['overall_status']!='PASS')
                    bw=next(c for c in measured['constraints'] if c['metric']=='BW_Hz')
                    check(job['arm']+phase+'_hard_fail_dominates_unknown',bw['status']!='FAIL' or measured['overall_status']=='FAIL')
                    if phase=='FIRST_SHOT':check(job['arm']+'_stage_is_firstshot',attempt['stage']=='FIRST_SHOT')
                    else:check(job['arm']+'_stage_is_repair',attempt['stage']=='FEEDBACK_REPAIR' and result['first_shot'] is None)
                    # Revalidate recorded original raw measurement against the projection.
                    from pll_allocation.verification.scenario import measurement_proposal
                    projected,_=measurement_proposal(item)
                    original=read(folder/'raw'/attempt['directory']/'frozen_measurement/result.json')
                    check_result(original,projected,protocol)
                    check(job['arm']+phase+'_actual_independent_BW_not_replaced',measured['metrics']==original['metrics'])
    check('all_arm_M2_budgets_le3',all(v<=3 for v in costs.values()),dict(costs))
    for seed in plan['random_seeds']:
        keys=[hashes[(f'{sid}__random__{seed}','FIRST_SHOT')] for sid in ('S0','S1','S2','S3')]
        check('paired_random_seed_'+str(seed),all(k==keys[0] for k in keys))
    allowed={'docs/DECISIONS.md','docs/PROJECT_STATUS.md','pll_allocation/pipeline.py','pll_allocation/pipeline_contracts.py'}
    before=read(ROOT/'experiments/stage5/resume_audit_01/tracked_before.json')
    changes=[r['path'] for r in before if not (ROOT/r['path']).is_file() or hashlib.sha256((ROOT/r['path']).read_bytes()).hexdigest()!=r['sha256']]
    unexpected=[path for path in changes if path not in allowed]
    check('protected_tracked_history_unchanged_except_authorized_adapters_docs',not unexpected,{'checked':len(before),'changed':changes,'unexpected':unexpected})
    check('original_scenario_plan_hashes_unchanged',all(read(ROOT/f'experiments/stage5/scenarios/{s["id"]}.json')['scenario_sha256']==s['sha256'] for s in plan['scenarios']))
    if a.summary:
        import csv
        with (a.summary/'scenario_results.csv').open(encoding='utf-8-sig') as stream:rows=list(csv.DictReader(stream))
        for row in rows:
            if row.get('strategy')=='random' and row.get('parameter_sha256'):
                check(row['arm']+row['phase']+'_reported_seed_matches_lineage',int(row['seed'])==int(row['arm'].rsplit('__',1)[1]))
    report={'passed':all(c['passed'] for c in checks),'checks':checks,'check_count':len(checks),
        'HEAD':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip(),
        'source_version':'HEAD plus manifest byte hashes; Stage5 changes not yet committed',
        'protected_scope':'existing tracked files plus explicit bindings; ignored binary raw not rehashed'}
    write_new(a.out/'audit.json',report)
    print(json.dumps({'passed':report['passed'],'checks':len(checks),'failed':[c for c in checks if not c['passed']]},indent=2))
    raise SystemExit(0 if report['passed'] else 1)


if __name__=='__main__':main()
