"""Experiment driver: frozen inputs -> existing formal CLI, no solver logic.

All allocation/M1/M2 execution is delegated to the project's existing pipeline.
Run by the verifier, sequentially. No automatic retries/resampling of failures.
"""
from copy import deepcopy
import argparse
import csv
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import random
import shutil
import subprocess
import sys
import time

from pll_allocation.exploration.contracts import load_problem, resolve_problem, require
from pll_allocation.exploration.engine import model_identity
from pll_allocation.physics_mapping.model import fingerprint, PARAMETERS
from pll_allocation.verification.continuous import model_identity as m2_identity
from tools.stress_open_domain import scale_context, choose_window, WindowDecisionError

ROOT=Path(__file__).resolve().parents[1]
AXES=('Icp','Rz','C1','C2','f0','Kvco')


def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))


def write(p,data):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf-8') as f:json.dump(data,f,indent=2,ensure_ascii=False,allow_nan=False);f.write('\n')


def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def sources():
    files=[*sorted((ROOT/'pll_allocation').rglob('*.py')),ROOT/'tools/randomized_stress.py',
        ROOT/'tools/stress_open_domain.py',ROOT/'configs/verification/protocol_v1_1.json',
        ROOT/'pll_allocation/verification/kernel.cpp']
    return {p.relative_to(ROOT).as_posix():digest(p) for p in files if '__pycache__' not in p.parts}


def generate(out,seed=2026111209):
    root=Path(out).resolve();root.mkdir(parents=True,exist_ok=False)
    rng=random.Random(seed)
    specs={}
    strata={'A':{'center_kHz':[190,255],'halfwidth_kHz':[45,75],'PM_deg':[46,58],'lock_us':[65,100]},
        'B':{'center_kHz':[255,330],'halfwidth_kHz':[5,13],'PM_deg':[65,74],'lock_us':[30,48]},
        'C':{'center_kHz':[325,430],'halfwidth_kHz':[2,7],'PM_deg':[79,86],'lock_us':[12,25]}}
    for key,s in strata.items():
        c=rng.uniform(*s['center_kHz'])*1000;w=rng.uniform(*s['halfwidth_kHz'])*1000
        specs[key]=[{'metric':'BW_Hz','unit':'Hz','enabled':True,'min':round(c-w,3),'max':round(c+w,3),'evaluation_source':'M1'},
            {'metric':'PM_deg','unit':'deg','enabled':True,'min':round(rng.uniform(*s['PM_deg']),6),'evaluation_source':'M1'},
            {'metric':'lock_time_s','unit':'s','enabled':True,'max':round(rng.uniform(*s['lock_us'])*1e-6,12),'evaluation_source':'M2'},
            {'metric':'jitter_s','unit':'s','enabled':False,'evaluation_source':'UNSUPPORTED'}]
    # Scale scaffolding is predeclared numerical experiment design, not a model
    # capability envelope, not a previous successful candidate/box.
    scaff={'Icp':[8e-6,8e-4],'Rz':[400.,25000.],'C1':[12e-12,450e-12],
        'C2':[.18e-9,8e-9],'f0':[20e6,79.5e6],'Kvco':[3e6,120e6]}
    labels={'D1':'NARROW_RANDOM','D2':'MEDIUM_RANDOM','D3':'WIDE_RANDOM','D4':'BIASED_RANDOM','D5':'COUPLING_CHALLENGE_RANDOM'}
    domains={};generation=[]
    for i,(domain_id,label) in enumerate(labels.items(),1):
        params={}
        for k,(lo,hi) in scaff.items():
            if i in (1,2,3):
                width=rng.uniform(*{1:(.22,.38),2:(.48,.70),3:(.82,.98)}[i]);lower=rng.uniform(0,1-width)
            elif i==4:
                width=rng.uniform(.20,.42);lower=rng.uniform(0,.12) if k in ('Rz','C2','f0','Kvco') else rng.uniform(.55,1-width)
            else:
                width=rng.uniform(.30,.50)
                lower=rng.uniform(.45,1-width) if k in ('C1','Rz') else rng.uniform(0,.12)
            upper=lower+width
            calc=(lambda u:lo+u*(hi-lo)) if k=='f0' else (lambda u:math.exp(math.log(lo)+u*math.log(hi/lo)))
            a,b=calc(lower),calc(upper)
            params[k]={'min':a,'max':b,'default':(a+b)/2 if k=='f0' else math.sqrt(a*b),
                       'unit':PARAMETERS[k][0],'scale':'linear' if k=='f0' else 'log'}
            generation.append({'domain':domain_id,'axis':k,'scaffolding':scaff[k],'normalized_lower':lower,'normalized_width':width})
        domains[domain_id]={'mode':'USER_FINITE','generation_stratum':label,'parameters':params}
    open_config={'mode':'USER_UNBOUNDED','user_parameter_bounds':None,'max_windows':2,
        'window_source':'REAL_LLM using original inverse-derived scale gauge and explicit numeric resource guard',
        'impedance_gauge_Ohm':1000.,'anchor_guard_decades':3,'is_physical_global_bound':False,
        'no_hidden_default_window':True,'no_open_domain_infeasibility_proof':True}
    domains['USER_UNBOUNDED']=open_config
    base=read(ROOT/'configs/problems/nominal.json')
    base['exploration'].update(seed=seed%(2**32),sobol_samples=128,physics_seed_count=0,max_m1_evaluations=128,
        max_analytic_calls=64,region_count=3,sensitivity_representatives=0)
    # Placeholder axes only permit use of existing contract utilities before
    # window construction. They are stripped from LLM state and never searched.
    scaffold_template=deepcopy(base)
    scaffold_template['parameters']={k:{'min':1.,'max':2.,'default':1.5,'unit':PARAMETERS[k][0],
        'scale':'linear' if k=='f0' else 'log'} for k in AXES}
    cfg=read(ROOT/'configs/agent/llm_physics.json')
    cfg['seed']=seed%(2**32)
    feedback=deepcopy(cfg)
    feedback.update(total_m1_budget=128,max_decisions=4,max_llm_calls=6)
    budgets={'initial':cfg,'feedback':{'schema_version':'pll-stage9-feedback-1.0','m1_budget':192,'m2_budget':6,
        'llm_budget':8,'max_reallocations':5,'m2_timeout_s':180,'search':feedback},
        'per_case_hard_limits':{'initial_M1':128,'feedback_M1':192,'initial_API':6,'feedback_API':8,
            'initial_accepted_decisions':4,'M2':6,'max_reallocations':5,'window_planning_API':2},
        'open_window_scheduling':{'first_window_initial_M1':64,'first_window_decisions':2,'first_window_API':3,
            'second_window':'remaining initial128/decisions4/API6; never reset outer feedback192/M2_6/API8',
            'expansion_trigger':'no supported M2 pass after initial window, remaining initial/M2 budget; real LLM may STOP'},
        'total_hard_limits_including_two_pilots':{'M1':6400,'M2':120,'allocation_API':280,'window_API':8,
            'wall_time_s':14400,'minimum_free_disk_GiB':12,'consecutive_provider_failed_cases':3},
        'no_post_result_budget_changes':True}
    provider={'provider':'configured_messages_provider','model_env':'ANTHROPIC_MODEL','base_url_env':'ANTHROPIC_BASE_URL',
        'api_key_env':'ANTHROPIC_AUTH_TOKEN','auth_mode':'bearer','max_tokens':4000,'timeout_s':180,'thinking':{'type':'disabled'}}
    matrix=[]
    for sid in specs:
        for did in domains:
            cid=sid+'_'+did
            p=deepcopy(base if did!='USER_UNBOUNDED' else scaffold_template);p['problem_id']='random_stress_'+cid;p['specs']=deepcopy(specs[sid])
            if did!='USER_UNBOUNDED':p['parameters']=deepcopy(domains[did]['parameters']);resolve_problem(p)
            write(root/'inputs'/f'{cid}.json',p)
            matrix.append({'case_id':cid,'spec_id':sid,'domain_id':did,'input_path':f'inputs/{cid}.json',
                'domain_mode':'USER_UNBOUNDED' if did=='USER_UNBOUNDED' else 'USER_FINITE'})
    write(root/'generated_specs.json',specs);write(root/'generated_domains.json',domains)
    write(root/'USER_UNBOUNDED.json',open_config);write(root/'budget_config.json',budgets);write(root/'provider_config.json',provider)
    write(root/'DOMAIN_GENERATION_DRAWS.json',generation)
    with (root/'case_matrix.csv').open('x',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(matrix[0]));w.writeheader();w.writerows(matrix)
    manifest={'schema_version':'pll-randomized-stress-1.0','seed':seed,'rng':'Python random.Random MT19937',
        'spec_generation_strata':strata,'domain_scale_scaffolding_SI':scaff,
        'case_matrix':matrix,'pilot_cases':['B_D3','B_USER_UNBOUNDED'],
        'difficulty_labels_assigned_before_execution':True,'resampling_allowed':False,
        'M1_model':model_identity(),'M2_model':m2_identity(),
        'provider_model_id':os.environ.get(provider['model_env']),'provider_environment_available':
            {k:bool(os.environ.get(provider[k])) for k in ('model_env','base_url_env','api_key_env')},
        'environment':{'python':sys.version,'platform':platform.platform(),
            'versions':{k:importlib.metadata.version(k) for k in ('numpy','scipy','pytest')}},
        'source_manifest_before_pilot':sources(),'initial_mode':'fresh SMALL_INITIAL_SOBOL_ONLY, not old full Stage7/history',
        'all_problem_templates_pre_registered':True,
        'input_sha256':{p.relative_to(root).as_posix():digest(p) for p in sorted(root.rglob('*')) if p.is_file()}}
    write(root/'experiment_manifest.json',manifest)
    (root/'EXPERIMENT_DESIGN.md').write_text('''# Randomized Stage7–9 Stress — pre-registration

3 stratified random Specs × 5 independently generated continuous six-axis domains + USER_UNBOUNDED =18.
Seed2026111209. Stratification/draws frozen before any allocation; no rejection sampling or handpicked feasible points.
Finite domains are random log intervals (f0 linear), not renamed prior Wide/Narrow. All random draws saved.
Pilot B_D3 and B_USER_UNBOUNDED precede full frozen18, which reruns pilot cases fresh.

Existing initial-allocation CLI creates a new smallSobol Stage7 context(24 formal M1 max) per input/window,
then real unchanged LLM physics-tool planning, original builder/RegionExplorer/M1/SLSQP(if chosen), archive/recheck.
Stage9 accepts only new READY handoffs and original corresponding problem;192 newM1/6M2/8API/5realloc.
All inputs, budgets, source/model/protocol identities and raw provider responses saved. No modified allocation prompt.

USER_UNBOUNDED: user bounds absent, not mathematical infinite search. An explicit arbitrary impedance gauge1000Ohm,
fref and original inverse expose a scale anchor; a real LLM chooses six finite intervals under +/-3decade numerical
resource guards. The guard is NOT physical/user capability. No historical success point or domain supplied.
At most2windows; second must include new space, gets real first-window observations, may STOP. Its bounds create
a new ResearchProblem/context; no stale PASS imported.128 initialM1/4decisions/6API shared across windows;
first64M1/2decisions/3API; Stage9 aggregate192M1/6M2/8API never reset. WindowAPI additional<=2/case.

Global upper bound including2pilots:6400M1/120M2/280allocationAPI/8windowAPI;4h wall;disk>=12GiB;
stop on3consecutive provider-failed cases. Native/Provider failures recorded, never replaced by Mock.
M1 physical certificates may stop without LLM/M2; report actual coverage. Pending/unsupported/unknown stays explicit.
Reports pair M1/M2 from SAME candidate; M2PM remainsUNKNOWN. Finite failure does not prove open-domain impossibility.
''',encoding='utf-8')
    return manifest


def frozen_inputs(root):
    manifest=read(root/'experiment_manifest.json')
    for p,sha in manifest['input_sha256'].items():require(digest(root/p)==sha,'preregistered input changed: '+p)
    return manifest


def command(root,argv,label):
    """Actual formal CLI only; raw output retained, no automatic rerun."""
    write(root/(label+'_command.json'),{'argv':argv,'cwd':str(ROOT),'started_epoch_s':time.time()})
    start=time.perf_counter()
    with (root/(label+'_stdout.log')).open('wb') as out,(root/(label+'_stderr.log')).open('wb') as err:
        p=subprocess.run(argv,cwd=ROOT,stdout=out,stderr=err,shell=False,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    write(root/(label+'_process.json'),{'returncode':p.returncode,'wall_s':time.perf_counter()-start})
    return p.returncode


def all_usage(root):
    """Actual network and formal call artifacts, no shared-cost double count."""
    if (root/'experiment_manifest.json').exists():
        # Test fixtures and source snapshots are not research executions.
        phases=[all_usage(root/p) for p in ('pilots','formal') if (root/p).exists()]
        total={k:sum(x[k] for x in phases) for k in ('M1_calls','M2_verifications','completed_native_runs',
            'native_elapsed_s','integration_points','LLM_requests','LLM_attempts','window_API','allocation_API')}
        total['tokens']={}
        for x in phases:
            for k,v in x['tokens'].items():total['tokens'][k]=total['tokens'].get(k,0)+v
        total['monetary_cost']=None
        return total
    calls=[];m1=0;m2=0;native=0;ns=0.;pts=0
    for p in root.rglob('metadata.json'):
        if 'llm_call' in '/'.join(p.parts):
            x=read(p)
            if 'real_network_call' in x:calls.append((p,x))
    for p in root.rglob('m1_samples.jsonl'):
        # executor raw rows are actual new evaluations; exported calibration
        # copies and archive rows are not charged a second time.
        if p.parent.name=='executor' or p.parent.name.startswith('candidate_audit_'):
            m1+=sum(bool(json.loads(s).get('formal_M1_called')) for s in p.read_text(encoding='utf-8').splitlines() if s.strip())
    m1+=sum(1 for p in root.rglob('posthoc_m1_started.json'))
    for p in root.rglob('verification_*_request.json'):m2+=1
    for p in root.rglob('summary.json'):
        if 'm2_' in '/'.join(p.parts):
            x=read(p)
            if isinstance(x,dict) and 'summary' in x:
                native+=1;ns+=x['summary']['elapsed_s'];pts+=x['summary']['integration_points']
    tokens={}
    for p,x in calls:
        for k,v in (x.get('usage') or {}).items():
            if type(v) is int:tokens[k]=tokens.get(k,0)+v
    window=sum('window_plan_' in '/'.join(p.parts) for p,x in calls if x.get('real_network_call'))
    allocation=sum('window_plan_' not in '/'.join(p.parts) for p,x in calls if x.get('real_network_call'))
    return {'M1_calls':m1,'M2_verifications':m2,'completed_native_runs':native,'native_elapsed_s':ns,'integration_points':pts,
        'LLM_requests':sum(x.get('real_network_call',False) for p,x in calls),'LLM_attempts':len(calls),
        'window_API':window,'allocation_API':allocation,'tokens':tokens,'monetary_cost':None}


def case_status(handoff,stage9,allocation):
    if stage9:
        t=stage9['termination_reason']
        if stage9['supported_M2_status']=='PASS':return 'SUPPORTED_METRICS_PASS'
        if t in ('CONTROLLER_ERROR','COST_LEDGER_MISMATCH'):return 'TOOL_EXECUTION_ERROR'
        if t in ('INVALID_LLM_DECISION','LLM_PROVIDER_FAILED','LLM_CALL_BUDGET_EXHAUSTED'):return 'LLM_DECISION_FAILURE'
        if stage9['supported_M2_status']=='UNKNOWN':return 'M2_UNKNOWN'
        return 'M2_FAIL_BUDGET_EXHAUSTED' if 'BUDGET' in t or t=='MAX_REALLOCATIONS' else 'SEARCH_STAGNATED'
    if allocation and allocation['status'] in ('INVALID_LLM_DECISION','LLM_PROVIDER_FAILED'):return 'LLM_DECISION_FAILURE'
    if allocation and allocation['status']=='PIPELINE_ERROR':return 'TOOL_EXECUTION_ERROR'
    return 'M1_NOT_FOUND'


def run_case(root,case_id,phase):
    manifest=frozen_inputs(root);entry=next(c for c in manifest['case_matrix'] if c['case_id']==case_id)
    if phase=='formal':require(read(root/'FORMAL_SOURCE_FREEZE.json')['sources']==sources(),'formal source changed')
    base=read(root/entry['input_path']);budgets=read(root/'budget_config.json');provider=read(root/'provider_config.json')
    case=root/phase/case_id;case.mkdir(parents=True,exist_ok=False);start=time.perf_counter()
    write(case/'input_user_spec_and_domain.json',{'specs':base['specs'],'domain':read(root/'generated_domains.json')[entry['domain_id']]})
    open_mode=entry['domain_mode']=='USER_UNBOUNDED';previous=None;observation=None;rows=[]
    cfg=deepcopy(budgets['initial']);initial_paid=0;initial_api=0;initial_decisions=0;feedback_paid=0;feedback_api=0;m2paid=0;reallocations=0
    classification='M1_NOT_FOUND';failure=None
    try:
        physics=scale_context(base) if open_mode else None
        if physics:write(case/'open_physics_source.json',physics)
        for window in range(1,3 if open_mode else 2):
            if open_mode:
                if window>1 and (initial_paid>122 or initial_api>=6 or initial_decisions>=4 or m2paid>=6):break
                problem=choose_window(base,case_id,window,physics=physics,previous_window=previous,
                    observation=observation,provider_config=provider,out=case/f'window_plan_{window}')
                if problem is None:classification='SEARCH_STAGNATED';break
            else:problem=base
            wroot=case/f'window_{window}';wroot.mkdir(exist_ok=False)
            write(wroot/'problem.json',problem)
            write(wroot/'domain_provenance.json',{'user_mode':entry['domain_mode'],
                'user_bounds':None if open_mode else problem['parameters'],'computational_window':problem['parameters'],
                'window_source':'REAL_LLM' if open_mode else 'PRE_REGISTERED_RANDOM_USER_DOMAIN',
                'window_is_user_constraint':not open_mode,'previous_window':previous,
                'open_domain_coverage':'FINITE_WINDOWS_ONLY_NO_INFEASIBILITY_PROOF' if open_mode else None})
            initial=deepcopy(cfg)
            initial['total_m1_budget']=min(64 if open_mode and window==1 else 128,128-initial_paid)
            initial['initial_m1_budget']=min(24,initial['total_m1_budget']-3)
            initial['max_decisions']=min(2 if open_mode and window==1 else 4,4-initial_decisions)
            initial['max_llm_calls']=min(3 if open_mode and window==1 else 6,6-initial_api)
            initial['max_decisions']=min(initial['max_decisions'],initial['max_llm_calls'])
            initial['max_round_m1']=min(64,initial['total_m1_budget']-initial['initial_m1_budget']-1)
            write(wroot/'initial_config.json',initial)
            argv=[sys.executable,'-m','pll_allocation','pipeline','--initial-allocation-problem',str(wroot/'problem.json'),
                '--initial-allocation-config',str(wroot/'initial_config.json'),'--llm-config',str(root/'provider_config.json'),
                '--out',str(wroot/'stage8')]
            command(wroot,argv,'stage7_stage8')
            allocation=read(wroot/'stage8/result.json') if (wroot/'stage8/result.json').exists() else None
            handoff=read(wroot/'stage8/stage9_handoff.json') if (wroot/'stage8/stage9_handoff.json').exists() else None
            if allocation:
                initial_paid+=allocation['cost']['M1_calls'];initial_api+=allocation['cost']['LLM_attempts']
                initial_decisions+=allocation['decision_rounds']
            stage9=None
            s9root=wroot/f'stage9_{case_id}_W{window}'
            if handoff and handoff['ready_for_stage9'] and m2paid<6:
                fcfg=deepcopy(budgets['feedback']);fcfg.update(m1_budget=192-feedback_paid,m2_budget=6-m2paid,
                    llm_budget=8-feedback_api,max_reallocations=max(0,5-reallocations))
                write(wroot/'feedback_config.json',fcfg)
                argv=[sys.executable,'-m','pll_allocation','pipeline','--stage9-handoff',str(wroot/'stage8/stage9_handoff.json'),
                    '--stage9-problem',str(wroot/'problem.json'),'--stage9-config',str(wroot/'feedback_config.json'),
                    '--llm-config',str(root/'provider_config.json'),'--out',str(s9root)]
                command(wroot,argv,'stage9')
                stage9=read(s9root/'stage9_final_result.json') if (s9root/'stage9_final_result.json').exists() else None
                if stage9:
                    feedback_paid+=stage9['cost']['M1_calls'];feedback_api+=sum(x['cost']['LLM_attempts'] for x in stage9['searches'])
                    m2paid+=stage9['cost']['M2_verifications'];reallocations+=len(stage9['searches'])
            classification=case_status(handoff,stage9,allocation)
            if allocation is None:classification='TOOL_EXECUTION_ERROR'
            row={'window':window,'path':str(wroot),'problem_sha256':load_problem(wroot/'problem.json')['problem_sha256'],
                'stage9_path':str(s9root) if stage9 else None,
                'initial_status':allocation['status'] if allocation else 'NO_RESULT','handoff_ready':bool(handoff and handoff['ready_for_stage9']),
                'stage9_status':stage9['status'] if stage9 else None,'classification':classification}
            rows.append(row);write(wroot/'window_result.json',row)
            if classification=='SUPPORTED_METRICS_PASS' or not open_mode:break
            observation={'last_window_status':row,'remaining_initial_M1':128-initial_paid,'remaining_initial_API':6-initial_api,
                'remaining_initial_decisions':4-initial_decisions,'remaining_M2':6-m2paid,
                'initial_result':allocation,'stage9_result':stage9}
            previous=problem['parameters']
    except Exception as error:
        failure={'type':type(error).__name__,'reason':str(error)}
        classification='LLM_DECISION_FAILURE' if isinstance(error,WindowDecisionError) or error.__class__.__name__ in ('ProviderError','InvalidResponse') else 'TOOL_EXECUTION_ERROR'
        write(case/'exception.json',failure)
    cost=all_usage(case)
    result={'case_id':case_id,'phase':phase,'domain_mode':entry['domain_mode'],'classification':classification,
        'windows':rows,'cost':cost,'wall_time_s':time.perf_counter()-start,'failure':failure,
        'initial_M1_charged':initial_paid,'feedback_M1_charged':feedback_paid,
        'initial_API_attempts':initial_api,'feedback_API_attempts':feedback_api,'reallocations':reallocations,
        'FULL_SYSTEMSPEC_CERTIFIED':False}
    write(case/'case_result.json',result)
    with (root/'execution_events.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(result,ensure_ascii=False)+'\n')
    print(json.dumps(result,ensure_ascii=False),flush=True)
    return result


def run_phase(root,phase):
    manifest=frozen_inputs(root);limits=read(root/'budget_config.json')['total_hard_limits_including_two_pilots']
    selected=manifest['pilot_cases'] if phase=='pilots' else [c['case_id'] for c in manifest['case_matrix']]
    clock=root/'execution_started.json'
    if not clock.exists():write(clock,{'epoch_s':time.time(),'scope':'all real research phases after marker; previous pilots charged by recorded wall time'})
    prior_pilot_wall=sum(read(p)['wall_time_s'] for p in (root/'pilots').glob('*/case_result.json')) if phase=='formal' else 0
    start=read(clock)['epoch_s'];failed=0
    for case_id in selected:
        # Completed runs can be observed on resume, never overwritten/rerun.
        if (root/phase/case_id/'case_result.json').exists():continue
        cost=all_usage(root)
        remaining=len(selected)-selected.index(case_id)
        exceeded=(cost['M1_calls']+320>limits['M1'] or cost['M2_verifications']+6>limits['M2'] or
            cost['allocation_API']+14>limits['allocation_API'] or cost['window_API']+2>limits['window_API'] or
            shutil.disk_usage(ROOT).free<limits['minimum_free_disk_GiB']*2**30 or
            time.time()-start+prior_pilot_wall>limits['wall_time_s'] or failed>=limits['consecutive_provider_failed_cases'])
        if exceeded:
            write(root/(phase+'_safety_stop.json'),{'next_case':case_id,'unstarted_count':remaining,'cost':cost,
                'reason':'PRE_REGISTERED_GLOBAL_RESOURCE_OR_PROVIDER_GUARD'});break
        result=run_case(root,case_id,phase)
        # Invalid decisions are not Provider outages. Guard only actual provider failures.
        provider_failed=any(read(p).get('status')=='LLM_PROVIDER_FAILED' for p in (root/phase/case_id).rglob('result.json'))
        provider_failed|=any(read(p).get('termination_reason')=='LLM_PROVIDER_FAILED' for p in (root/phase/case_id).rglob('stage9_final_result.json'))
        failed=failed+1 if provider_failed else 0


def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['generate','pilots','freeze','formal','case'])
    p.add_argument('--out',required=True);p.add_argument('--case');p.add_argument('--phase',default='formal')
    args=p.parse_args();root=Path(args.out).resolve()
    if args.mode=='generate':generate(root)
    elif args.mode=='freeze':
        frozen_inputs(root)
        for cid in read(root/'experiment_manifest.json')['pilot_cases']:require((root/'pilots'/cid/'case_result.json').exists(),'both pilots required')
        write(root/'FORMAL_SOURCE_FREEZE.json',{'sources':sources(),'epoch_s':time.time(),'M1_model':model_identity(),
            'M2_model':m2_identity(),'allocation_prompt_modified':False})
        snap=root/'frozen_sources'
        for f in sources():
            dest=snap/f;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/f,dest)
    elif args.mode=='case':run_case(root,args.case,args.phase)
    else:run_phase(root,args.mode)


if __name__=='__main__':main()
