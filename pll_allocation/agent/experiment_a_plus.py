"""A+ experimental scheduling adapter; all M1/optimization uses RegionExplorer."""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import random
import sys
import time
import numpy as np
from ..allocation.core import Meter, write_new
from ..block_space.contracts import FREE_IDS
from ..exploration.contracts import load_problem, resolve_problem, coordinate, make_parameters, require
from ..exploration.engine import model_identity
from ..exploration.physics_region_builder import build_physics_region, validate_request
from ..physics_mapping.model import PARAMETERS, fingerprint
from ..region_explorer.assessment import normalized_point, physical_coordinate
from ..region_explorer.explorer import RegionExplorer, margin_vector
from .region_policy import LLMRegionPolicy, ProviderError, InvalidResponse
from .window_contract import normalize_window, contract_decision
from .subregion_context import export_context
from .subregion_tools import envelope, execute_tool, inverse_proposals

ROOT=Path(__file__).resolve().parents[2]
SEEDS=(1301,2603,3907)
SPECS={'SW':(180000.,410000.,50.),'SN':(260000.,330000.,60.),'ST':(290000.,300000.,70.)}
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def utc():return datetime.now(timezone.utc).isoformat()
def append(p,x):
    with Path(p).open('a',encoding='utf-8') as f:f.write(json.dumps(x,ensure_ascii=False,allow_nan=False)+'\n')
def sources():
    return {p.relative_to(ROOT).as_posix():sha(p) for p in [*ROOT.joinpath('pll_allocation').rglob('*.py'),ROOT/'tools/stress_open_domain.py']}

def freeze(out):
    root=Path(out).resolve(); f=root/'frozen'; f.mkdir(exist_ok=False)
    base=read(ROOT/'configs/stage7/continuous_global_v2.json'); fixed=base['fixed_parameters']
    fr=fixed['f_ref']['value']; target=fr*fixed['N']['value']; span=1.2; z=1000.
    scales={'C1':1/(2*math.pi*fr*z),'C2':1/(2*math.pi*fr*z),'Rz':z,'Icp':span/(2*math.pi*z),'Kvco':target/span}
    guard={k:{'min':target*1e-4 if k=='f0' else scales[k]*1e-3,
        'max':target*(1-1e-6) if k=='f0' else scales[k]*1e3,
        'default':target*.5 if k=='f0' else scales[k], 'unit':PARAMETERS[k][0],
        'scale':'linear' if k=='f0' else 'log'} for k in FREE_IDS}
    base['parameters']=guard
    base['exploration'].update(sobol_samples=128,physics_seed_count=0,max_m1_evaluations=256,
        max_analytic_calls=192,region_count=3,sensitivity_representatives=0)
    for name,(lo,hi,pm) in SPECS.items():
        p=deepcopy(base); p['problem_id']='A_PLUS:'+name
        p['specs']=[{'metric':'BW_Hz','unit':'Hz','enabled':True,'min':lo,'max':hi,'evaluation_source':'M1'},
            {'metric':'PM_deg','unit':'deg','enabled':True,'min':pm,'evaluation_source':'M1'},
            {'metric':'lock_time_s','unit':'s','enabled':False,'evaluation_source':'M2'},
            {'metric':'jitter_s','unit':'s','enabled':False,'evaluation_source':'UNSUPPORTED'}]
        resolve_problem(p); write_new(f/(name+'.json'),p)
    matrix=[{'run_id':f'{s}_{p}_{seed}','spec':s,'policy':p,'seed':seed} for seed in SEEDS for s in SPECS for p in ('P1','P2')]
    random.Random(2026111301).shuffle(matrix)
    cfg={'schema_version':'pll-a-plus-1.0','seeds':list(SEEDS),'run_order':matrix,'domain_mode':'USER_UNBOUNDED',
        'user_parameter_bounds':None,'hard_numerical_resource_guard':guard,'guard_is_physical_capability':False,
        'guard_origin':'topology numerical scales, arbitrary 1000Ohm gauge, +/-3 decades; same for all Specs',
        'model_hard_conditions':['positive finite SI','N=8,fref=10MHz','ideal fixed topology','interior tuning within0..1.2V'],
        'phase1_M1_limit':128,'phase2_M1_limit':128,'max_regions':3,'region_caps':[43,43,42],
        'initial_Stage7_M1':0,'bootstrap':'Explicit EMPTY_BOOTSTRAP, no prepare_initial; original default remains unchanged',
        'phase1_schedule':['shared scale_context analytical prior','numeric planner window','HIGH_PM_LF_SHAPE builder3seeds',
            'Sobol8M1','original SLSQP remaining regional budget'],
        'phase2_schedule':['SLSQP32','Sensitivity12','DIVERSITY_EXPLORATION inverse8','two SLSQP24 starts',
            'Analytical Inverse residual then Sobol','three interior connection samples per selected edge'],
        'construction_attempt_limit_per_request':64,'connectivity_reserve':21,'top_n':8,
        'minimum_normalized_margin':.01,'minimum_tuning_margin_V':.01,'diversity_rms_threshold':.02,
        'diversity_normalization':'six COMMON frozen guard coordinates, log except f0 linear; RMS Euclidean',
        'selection':'chronological greedy; core Top8 completion requires first PASS included and all8 margin eligible; no connectivity points added',
        'sensitivity_guidance':'After actual stencil, subsequent SLSQP uses up to3 largest finite absolute derivatives of the measured tightest constraint; fallback six axes',
        'slsqp':{'maxiter':40,'finite_difference_step':1e-5},
        'rule_window':'shared inverse anchor /10..*10, x3/x10 on later rounds; f0 .1.. .95 of output',
        'shared_information':'Both see existing scale_context, including its one unvalidated inverse-derived gauge. No reference witness supplied.',
        'LLM_authority':'Existing open-domain adapter submits actual six numeric intervals; no different search-tool decisions',
        'LLM_retries':0,'LLM_calls_per_window':1,'LLM_seed_note':'fresh states/API; no provider sampling seed supported',
        'provider':read(ROOT/'configs/stage8b/messages_pilot.json'),'provider_model':os.environ.get('ANTHROPIC_MODEL'),
        'reference_isolation':'reference_only never loaded by planners/Trial; status gate only',
        'frozen_utc':utc(),'python':sys.version,'M2_calls':0}
    write_new(f/'config.json',cfg); write_new(f/'source_manifest.json',sources())
    write_new(f/'input_manifest.json',{p.name:sha(p) for p in f.iterdir() if p.is_file()})
    write_new(root/'EXPERIMENT_DESIGN.json',cfg)
    return response('FROZEN',{'M1_calls':0})

def response(status,cost):return {'status':status,'strategy':'experiment_a_plus','cost':cost,'failure':None}
def check_freeze(root):
    f=root/'frozen'; require(sources()==read(f/'source_manifest.json'),'source changed after freeze')
    for n,h in read(f/'input_manifest.json').items():require(sha(f/n)==h,'frozen input changed: '+n)
    return read(f/'config.json')
def request(p,ident,count=3,strategy='HIGH_PM_LF_SHAPE'):
    return {'schema_version':'pll-physics-region-request-1.0','request_id':ident,'problem_sha256':p['problem_sha256'],
        'model_fingerprint':model_identity()['model_sha256'],'strategy':strategy,'target_bw_fraction':[.5,.5],
        'physics_focus':['LF_SHAPE','GAIN_SPLIT'],'tuning_preference':'INTERIOR','seed_count':count,
        'region_width_policy':'BROAD','budget':{'construction_attempts':64,'m1_calls':count},'evidence_ids':['REL:shape','REL:inverse_gain']}

def reference(out):
    root=Path(out).resolve(); check_freeze(root); f=root/'reference_only'; f.mkdir(exist_ok=False); rows=[]; start=time.perf_counter()
    for name in SPECS:
        p=load_problem(root/'frozen'/(name+'.json')); sub=f/name; sub.mkdir()
        context=export_context(p,[],sub/'context',cost={'M1_calls':0},scope='EMPTY_BOOTSTRAP_NO_SEARCH')
        ex=RegionExplorer(context,sub/'executor',m1_budget=8,stop_when=lambda r:r['judgment']['m1_feasibility']=='FEASIBLE')
        prop=build_physics_region(p,request(p,'REF:'+name,8),model_fingerprint=model_identity()['model_sha256'],random_seed=880013)
        write_new(sub/'proposal_before_M1.json',prop)
        for i,s in enumerate(prop['seeds']):
            d=envelope(ex,decision_id=f'REF:{i}',region_id=f'REF:{i}',bounds={k:[0.,1.] for k in FREE_IDS},budget=1,seed=880013+i,proposals=1)
            ex.execute(d,candidate_stream=iter([s['parameters']]),tool_name='PHYSICS_GUIDED_SEEDS')
            if any(r['judgment']['m1_feasibility']=='FEASIBLE' for r in ex.rows):break
        ex.close(); rows.append({'spec':name,'feasible':any(r['judgment']['m1_feasibility']=='FEASIBLE' for r in ex.rows),
            'M1_calls':ex.counts['M1_calls'],'inverse_calls':prop['cost']['inverse_calls']})
    write_new(f/'summary.json',{'rows':rows,'wall_s':time.perf_counter()-start,'not_shared_with_planners':True})
    require(all(r['feasible'] for r in rows),'model reference witness not found for every Spec')
    write_new(root/'REFERENCE_GATE.json',{'all_three_model_feasible':True,'reference_data_shared':False})
    return response('REFERENCE_COMPLETE',{'M1_calls':sum(r['M1_calls'] for r in rows)})

def rule_window(state):
    a=state['physics']['scale_anchors_SI']; g=state['physics']['numerical_resource_guard']; n=state['round']; factor=10*(1,3,10)[n-1]
    target=state['template']['fixed_parameters']['N']['value']*state['template']['fixed_parameters']['f_ref']['value']
    params={k:{'min':max(g[k]['min'],target*.1/n if k=='f0' else a[k]/factor),
        'max':min(g[k]['max'],target*(.95+.015*(n-1)) if k=='f0' else a[k]*factor),
        'unit':PARAMETERS[k][0],'scale':'linear' if k=='f0' else 'log'} for k in FREE_IDS}
    return {'schema_version':'pll-computational-window-decision-1.0','state_sha256':state['state_sha256'],
        'action':'OPEN_WINDOW' if n==1 else 'EXPAND_OR_SWITCH','parameters':params,
        'reason':'Predeclared symmetric interval around shared unvalidated inverse gauge; expand on measured miss.',
        'evidence_ids':['OPEN:SCALE_GAUGE','REL:shape','REL:inverse_gain']}

class Trial:
    def __init__(self,root,entry,cfg):
        self.root=root; self.entry=entry; self.cfg=cfg; root.mkdir(parents=True,exist_ok=False)
        self.start=time.perf_counter(); self.started_utc=utc(); self.phase='PHASE1'; self.first=None; self.eighth=None
        self.explorers=[]; self.candidates=[]; self.selected=[]; self.actions=[]; self.timings=[]; self.plans=[]; self.llm=[]; self.constructions=[]
        self.current_region=0; self.first_region=None; self.failure=None; self.stop_reason=None; self.connectivity=[]
        self.raw=read(root.parents[1]/'frozen'/(entry['spec']+'.json')); self.guard=cfg['hard_numerical_resource_guard']
        write_new(root/'submission.json',{'entry':entry,'specs':self.raw['specs'],'domain_mode':'USER_UNBOUNDED',
            'user_bounds':None,'submitted_utc':self.started_utc,'perf_counter':self.start})

    def calls(self):return sum(e.counts['M1_calls'] for e in self.explorers)
    def distance(self,a,b):
        return math.sqrt(sum((coordinate(self.guard[k],a['values'][k]['value'])-coordinate(self.guard[k],b['values'][k]['value']))**2 for k in FREE_IDS)/6)
    def log(self,r):
        ident=f'W{self.current_region}:{r["evidence_id"]}'
        if any(c['id']==ident for c in self.candidates):return
        timing=r['cost'].get('evaluation_timing',{})
        origin=r['origin']; source='SLSQP' if origin.startswith('SLSQP') else 'Sobol' if origin.startswith('LOCAL_SOBOL') else 'Connectivity' if origin.startswith('LOCAL_CONNECTIVITY') else 'Sensitivity' if origin.startswith('LOCAL_SENSITIVITY') else 'Physics Inverse'
        c={'id':ident,'window':self.current_region,'phase':self.phase,'source':source,'origin':origin,
            'formal_M1_called':r['formal_M1_called'],'M1_call_index':self.calls(),'parameters':deepcopy(r['parameters']),
            'parameter_sha256':r['parameter_sha256'],'M1_status':r['M1_status'],'metrics':deepcopy(r['metrics']),
            'judgment':deepcopy(r['judgment']),'elapsed_s':time.perf_counter()-self.start,
            'M1_return_elapsed_s':timing.get('perf_counter_finished',time.perf_counter())-self.start,
            'M1_wall_s':timing.get('wall_time_s'),'executor_evidence_id':r['evidence_id'],
            'tuning_margin_V':r['screening'].get('derived',{}).get('tuning_margin_V')}
        self.candidates.append(c); append(self.root/'all_candidates.jsonl',c)
        if (c['formal_M1_called'] and self.phase!='CONNECTIVITY' and c['judgment']['m1_feasibility']=='FEASIBLE' and
            c['judgment']['minimum_normalized_margin']>=self.cfg['minimum_normalized_margin'] and
            r['screening'].get('derived',{}).get('tuning_margin_V',-1)>=self.cfg['minimum_tuning_margin_V'] and
            all(self.distance(c['parameters'],x['parameters'])>=self.cfg['diversity_rms_threshold'] for x in self.selected) and len(self.selected)<8):
            self.selected.append(c); append(self.root/'top8_selection.jsonl',c)
            if len(self.selected)==8:self.eighth=c
    def target(self,r):
        self.log(r)
        if self.phase=='PHASE1' and r['judgment']['m1_feasibility']=='FEASIBLE':
            self.first=self.candidates[-1]; self.first_region=self.current_region; return True
        return self.phase=='PHASE2_SEARCH' and len(self.selected)==8
    def timed(self,kind,name,func):
        start=time.perf_counter(); before=self.calls()
        try:return func()
        finally:
            rec={'phase':self.phase,'category':kind,'name':name,'start_s':start-self.start,
                'end_s':time.perf_counter()-self.start,'inclusive_wall_s':time.perf_counter()-start,'M1_calls':self.calls()-before}
            self.timings.append(rec); append(self.root/'timing_events.jsonl',rec)
    def new_ex(self,p,f,limit):
        context=export_context(p,[],f/'empty_context',cost={'M1_calls':0},scope='EMPTY_BOOTSTRAP_NO_SEARCH')
        ex=RegionExplorer(context,f/'executor',m1_budget=limit,budget_scheduling=True,stop_when=self.target)
        self.explorers.append(ex); return ex
    def perform(self,ex,d,stream=None,tool=None):
        before=len(ex.rows)
        obs=self.timed('optimizer' if d['search_method']=='SLSQP' else 'search_tool',d['decision_id'],
            lambda:ex.execute(d,candidate_stream=stream,tool_name=tool))
        for r in ex.rows[before:]:self.log(r)
        a={'phase':self.phase,'window':self.current_region,'decision':d,'observation':obs}
        self.actions.append(a); append(self.root/'actions.jsonl',a); return obs
    def point(self,ex,p,ident,tool='PHYSICS_GUIDED_SEEDS'):
        d=envelope(ex,decision_id=ident,region_id=ident,bounds={k:[0.,1.] for k in FREE_IDS},budget=1,
            seed=self.entry['seed']+len(self.actions),proposals=1)
        return self.perform(ex,d,iter([p]),tool)
    def optimize(self,ex,sid,b,ident,active=None):
        d=envelope(ex,decision_id=ident,region_id=ident,bounds={k:[0.,1.] for k in FREE_IDS},budget=b,
            seed=self.entry['seed']+len(self.actions),proposals=1)
        d.update(action='OPTIMIZE',search_method='SLSQP',seed_ids=[sid],settings=deepcopy(self.cfg['slsqp']))
        if active:
            d['active_variables']=active
            d['reason']='Existing subset SLSQP; axes ranked by actual local sensitivity of tightest constraint.'
        return self.perform(ex,d)
    def best(self,ex):
        rows={r['parameter_sha256']:r for r in ex.rows if r['M1_status']=='OK' and margin_vector(ex.problem,r)}
        return sorted(rows.values(),key=lambda r:-r['judgment']['minimum_normalized_margin'])
    def build(self,ex,f,ident,count=3,strategy='HIGH_PM_LF_SHAPE'):
        req=request(ex.problem,ident,count,strategy)
        validate_request(req,ex.problem,model_identity()['model_sha256'],set(req['evidence_ids']),attempts_left=64,m1_left=count)
        write_new(f/(ident+'_request.json'),req)
        prop=self.timed('physics',ident,lambda:build_physics_region(ex.problem,req,model_fingerprint=model_identity()['model_sha256'],
            random_seed=self.entry['seed']+len(self.constructions),history=[c['parameters'] for c in self.candidates if c['formal_M1_called']],
            excluded={c['parameter_sha256'] for c in self.candidates if c['formal_M1_called']}))
        self.constructions.append(prop); write_new(f/(ident+'_before_M1.json'),prop); return prop

    def phase1(self):
        from tools.stress_open_domain import scale_context,validate_window,PROMPT
        physics=self.timed('physics','SHARED_SCALE_PRIOR',lambda:scale_context(self.raw))
        physics['numerical_resource_guard']={k:{'min':a['min'],'max':a['max']} for k,a in self.guard.items()}
        physics['M2_applicability']={'status':'NOT_EVALUATED_IN_A_PLUS'}
        write_new(self.root/'shared_physics_prior.json',physics); previous=None; observation=None
        for n in range(1,4):
            self.current_region=n; f=self.root/f'window_{n:02d}'; f.mkdir()
            state={'schema_version':'pll-open-input-state-1.0','case_id':self.entry['run_id'],'round':n,
                'user_domain':{'mode':'USER_UNBOUNDED','six_axis_user_min_max':None},'template':deepcopy(self.raw),
                'physics':deepcopy(physics),'previous_window':previous,'actual_observation':observation,
                'budget':{'remaining_M1':128-self.calls(),'remaining_regions':4-n},'controller_seed':self.entry['seed']}
            state['template']['parameters']={}; state['state_sha256']=fingerprint(state); write_new(f/'PlannerState.json',state)
            try:
                if self.entry['policy']=='P2':
                    planner=LLMRegionPolicy(self.cfg['provider'],prompt=PROMPT)
                    def validate_current(raw,current):
                        bound=deepcopy(current);bound['template']=deepcopy(self.raw)
                        return validate_window(raw,bound)
                    try:p=self.timed('llm','WINDOW_'+str(n),lambda:contract_decision(planner,state,f,
                        existing_directory=True,raw_alias='RegionIntent.json',normalize=normalize_window,validate=validate_current))
                    finally:self.llm.extend(planner.calls)
                else:
                    raw=self.timed('planner','RULE_WINDOW_'+str(n),lambda:rule_window(state))
                    write_new(f/'RegionIntent.json',raw)
                    normalized,trace=normalize_window(raw,state);write_new(f/'normalization.json',trace)
                    validation=deepcopy(state);validation['template']=deepcopy(self.raw)
                    p=validate_window(normalized,validation)
            except ValueError as error:
                write_new(f/'validation.json',{'accepted':False,'reason':str(error),'fallback_used':False}); raise
            write_new(f/'validation.json',{'accepted':True,'numeric_bounds_source':self.entry['policy'],'whole_window_certified':False})
            if p is None:self.stop_reason='PLANNER_STOP_WITHOUT_PASS'; break
            problem=resolve_problem(p); ratios={k:coordinate(self.guard[k],a['max'])-coordinate(self.guard[k],a['min']) for k,a in problem['parameters'].items()}
            plan={'window':n,'parameters':problem['parameters'],'guard_axis_width_ratios':ratios,'guard_hypervolume_fraction':math.prod(ratios.values())}
            self.plans.append(plan); write_new(f/'actual_subspace.json',plan)
            cap=self.cfg['region_caps'][n-1]; ex=self.timed('setup','CONTEXT',lambda:self.new_ex(problem,f,cap+128)); before=self.calls()
            prop=self.build(ex,f,'BUILD')
            for i,s in enumerate(prop['seeds']):
                self.point(ex,s['parameters'],f'W{n}:INVERSE:{i}')
                if self.first:break
            if not self.first:
                b=min(8,cap-(self.calls()-before)); d=envelope(ex,decision_id=f'W{n}:SOBOL',region_id=f'W{n}:SOBOL',
                    bounds={k:[0.,1.] for k in FREE_IDS},budget=b,seed=self.entry['seed']+n,proposals=64); self.perform(ex,d)
            rows=self.best(ex)
            if not self.first and rows and cap-(self.calls()-before)>=23:self.optimize(ex,rows[0]['evidence_id'],cap-(self.calls()-before),f'W{n}:SLSQP')
            if self.first:return ex
            observation={'M1_calls':self.calls()-before,'stop_reason':'REGION_NOT_FOUND','actual_evidence':self.candidates[-12:]}
            write_new(f/'observed_failure.json',observation); previous=problem['parameters']
        self.stop_reason=self.stop_reason or ('PHASE1_BUDGET_EXHAUSTED' if self.calls()>=128 else 'NOT_FOUND_WITHIN_THREE_REGIONS')
        return None

    def phase2(self,ex):
        self.phase='PHASE2_SEARCH'; self.p2start=time.perf_counter(); self.p2calls=self.calls(); f=self.root/'expansion'; f.mkdir()
        cutoff=self.calls()+107
        def left():return max(0,cutoff-self.calls())
        def done():return len(self.selected)==8 or left()==0
        if not done() and left()>=23:self.optimize(ex,self.first['executor_evidence_id'],min(32,left()),'EXPAND:SLSQP:1')
        rows=self.best(ex); sensitive_axes=None
        if not done() and rows and left()>=12:
            before=len(ex.rows)
            obs=self.timed('sensitivity','EXPAND:SENSITIVITY',lambda:execute_tool(ex,decision_id='EXPAND:SENSITIVITY',
                region={'region_id':'EXPAND:SENSITIVITY','normalized_bounds':{k:[0.,1.] for k in FREE_IDS}},
                tool={'method':'LOCAL_SENSITIVITY','seed_id':rows[0]['evidence_id'],'m1_budget':min(12,left())},seed=self.entry['seed'],
                config={'max_tool_proposals':12},meter=Meter(cheap_limit=0,m1_limit=0)))
            for r in ex.rows[before:]:self.log(r)
            write_new(f/'sensitivity.json',obs)
            reps=obs['sensitivity']['representatives']
            if reps:
                center=ex.evidence[reps[0]['center_evidence_id']]
                tight=min((c for c in center['judgment']['constraints'] if c['enabled'] and c['normalized_margin'] is not None),key=lambda c:c['normalized_margin'])
                column=reps[0]['normalized_matrix'].get(tight['metric'],{})
                ranked=sorted((k for k,v in column.items() if v is not None and abs(v)>1e-10),key=lambda k:-abs(column[k]))
                sensitive_axes=ranked[:3] or None
                write_new(f/'sensitivity_guidance.json',{'center_evidence_id':center['evidence_id'],'tightest_metric':tight['metric'],
                    'actual_normalized_derivatives':column,'subsequent_SLSQP_axes':sensitive_axes,'scope':'Local evidence only'})
        if not done():
            prop=self.build(ex,f,'EXPAND_DIVERSITY',8,'DIVERSITY_EXPLORATION')
            for i,s in enumerate(prop['seeds']):
                if done():break
                self.point(ex,s['parameters'],f'EXPAND:COUPLED_INVERSE:{i}')
        starts=[]
        for r in self.best(ex):
            if all(self.distance(r['parameters'],x['parameters'])>=.01 for x in starts):starts.append(r)
            if len(starts)==2:break
        for i,r in enumerate(starts):
            if done() or left()<23:break
            self.optimize(ex,r['evidence_id'],min(24,left()),f'EXPAND:SLSQP:{i+2}',sensitive_axes)
        if not done():
            meter=Meter(cheap_limit=64,m1_limit=0); b=left()
            d=envelope(ex,decision_id='EXPAND:ANALYTICAL',region_id='EXPAND:ANALYTICAL',bounds={k:[0.,1.] for k in FREE_IDS},
                budget=b,seed=self.entry['seed']+19,proposals=64)
            def measured_inverse():
                proposals=inverse_proposals(ex,d,meter,'ANALYTICAL_INVERSE')
                while True:
                    try:proposal=self.timed('physics','ANALYTICAL_PROPOSAL',lambda:next(proposals))
                    except StopIteration:return
                    yield proposal
            self.perform(ex,d,measured_inverse(),'ANALYTICAL_INVERSE')
            write_new(f/'analytical_cost.json',{'counts':meter.counts,'events':meter.events})
        if not done():
            b=left(); d=envelope(ex,decision_id='EXPAND:SOBOL',region_id='EXPAND:SOBOL',bounds={k:[0.,1.] for k in FREE_IDS},
                budget=b,seed=self.entry['seed']+23,proposals=max(64,b*8)); self.perform(ex,d)
        self.phase='CONNECTIVITY'
        if len(self.selected)>1:
            center=self.selected[0]; u=normalized_point(ex.problem,center['parameters'])
            for i,other in enumerate(self.selected[1:],1):
                evidence=[]; v=normalized_point(ex.problem,other['parameters'])
                for fraction in (.25,.5,.75):
                    if self.calls()-self.p2calls>=128:break
                    candidate=make_parameters(ex.problem,{k:physical_coordinate(ex.problem['parameters'][k],u[k]+fraction*(v[k]-u[k])) for k in FREE_IDS})
                    self.point(ex,candidate,f'CONNECT:{i}:{fraction}','LOCAL_CONNECTIVITY'); r=ex.rows[-1]
                    evidence.append({'fraction':fraction,'executor_evidence_id':r['evidence_id'],'formal_M1_called':r['formal_M1_called'],
                        'M1_status':r['M1_status'],'feasibility':r['judgment']['m1_feasibility'],'minimum_normalized_margin':r['judgment']['minimum_normalized_margin']})
                self.connectivity.append({'from':center['id'],'to':other['id'],'samples':evidence,
                    'sampled_connection_pass':len(evidence)==3 and all(e['M1_status']=='OK' and e['feasibility']=='FEASIBLE' for e in evidence),
                    'continuous_segment_certified':False})
        write_new(f/'local_connectivity.json',self.connectivity)
        write_new(f/'top8_points.json',{'points':self.selected,'diversity_rms_threshold':.02,'minimum_normalized_margin':.01,'whole_region_certified':False})
        included=any(s['id']==self.first['id'] for s in self.selected)
        self.stop_reason='TOP8_COMPLETED' if len(self.selected)==8 and included else 'FIRST_PASS_MARGIN_INSUFFICIENT' if not included else 'PHASE2_SEARCH_BUDGET_EXHAUSTED' if self.calls()-self.p2calls>=107 else 'PHASE2_NOT_FOUND'

    def run(self):
        try:
            ex=self.phase1()
            if ex is not None:self.phase2(ex)
        except Exception as error:
            self.failure={'type':type(error).__name__,'reason':str(error)}
            self.stop_reason='PROVIDER_FAILURE' if isinstance(error,ProviderError) else 'PLANNER_INVALID_RESPONSE' if isinstance(error,InvalidResponse) else 'EXECUTION_FAILURE'
        finally:
            for ex in self.explorers:
                if not ex.closed:
                    try:ex.close()
                    except Exception as error:self.failure=self.failure or {'type':type(error).__name__,'reason':str(error)}
        formal=[c for c in self.candidates if c['formal_M1_called']]; latency=[c['M1_wall_s'] for c in formal if c['M1_wall_s'] is not None]
        distances=[self.distance(a['parameters'],b['parameters']) for i,a in enumerate(self.selected) for b in self.selected[i+1:]]
        prior=read(self.root/'shared_physics_prior.json') if (self.root/'shared_physics_prior.json').exists() else {}
        inverse=sum(p['cost']['inverse_calls'] for p in self.constructions)+prior.get('analytic_calls',0)
        for p in self.root.glob('expansion/analytical_cost.json'):inverse+=read(p)['counts']['analytic_calls']
        timing={k:sum(t['inclusive_wall_s'] for t in self.timings if t['category']==k) for k in ('llm','physics','optimizer','sensitivity','search_tool','planner','setup')}
        timing.update(M1=sum(latency),optimizer_exclusive=max(0,timing['optimizer']-sum(c['M1_wall_s'] or 0 for c in formal if c['source']=='SLSQP')),
            wall=time.perf_counter()-self.start,note='optimizer/search/sensitivity inclusive times contain M1; do not add overlapping categories')
        p1=self.first['M1_call_index'] if self.first else self.calls()
        included=bool(self.first and any(s['id']==self.first['id'] for s in self.selected))
        complete=len(self.selected)==8 and included
        result={**self.entry,'status':'EXECUTION_FAILED' if self.failure else 'NOT_FOUND' if not self.first else 'TOP8_COMPLETE' if complete else 'FIRST_PASS_PARTIAL_TOP8',
            'failure':self.failure,'stop_reason':self.stop_reason,'first_region_hit':self.first_region==1,'first_region_index':self.first_region,
            'first_candidate_M1_pass':formal[0]['judgment']['m1_feasibility']=='FEASIBLE' if formal else None,
            'time_to_first_pass_s':self.first['elapsed_s'] if self.first else None,'M1_to_first_pass':self.first['M1_call_index'] if self.first else None,
            'first_pass':self.first,'first_pass_in_top8':included,'top8_complete':complete,
            'time_to_eight_s':self.eighth['elapsed_s'] if self.eighth and complete else None,
            'incremental_expansion_to_eight_s':self.eighth['elapsed_s']-self.first['elapsed_s'] if self.eighth and self.first and complete else None,
            'incremental_expansion_wall_s':time.perf_counter()-getattr(self,'p2start',time.perf_counter()),
            'phase1_M1_calls':p1,'phase2_M1_calls':self.calls()-p1,'total_M1_calls':self.calls(),
            'LLM_API_calls':sum(bool(c.get('real_network_call')) for c in self.llm),'LLM_attempts':len(self.llm),
            'LLM_API_latency_s':[c['elapsed_s'] for c in self.llm],'LLM_metadata':self.llm,
            'physics_inverse_attempts':inverse,'construction_attempts':sum(p['cost']['construction_attempts'] for p in self.constructions),
            'slsqp_actions':sum(a['decision']['search_method']=='SLSQP' for a in self.actions),
            'slsqp_calls':sum(bool(s.get('started')) for a in self.actions for s in a['observation']['solver_runs']),
            'M1_evaluation_p50_s':float(np.percentile(latency,50)) if latency else None,
            'M1_evaluation_p95_s':float(np.percentile(latency,95)) if latency else None,
            'top8_count':len(self.selected),'top8_points':self.selected,'point_diversity_min_rms':min(distances,default=None),
            'point_diversity_max_rms':max(distances,default=None),'pairwise_distances':distances,
            'local_connectivity':self.connectivity,'actual_windows':self.plans,'timing':timing,
            'initial_Stage7_calibration_M1_calls':0,'started_utc':self.started_utc,'completed_utc':utc(),
            'M2_calls':0,'FULL_SYSTEMSPEC_CERTIFIED':False}
        require(self.calls()==len(formal),'formal call ledger mismatch')
        require(p1<=128 and self.calls()-p1<=128,'phase budget exceeded')
        write_new(self.root/'result.json',result); return result

def run(out):
    root=Path(out).resolve(); cfg=check_freeze(root)
    require(read(root/'REFERENCE_GATE.json')['all_three_model_feasible'],'model reference gate missing')
    f=root/'runs'; f.mkdir(exist_ok=False); start=time.perf_counter(); rows=[]
    for entry in cfg['run_order']:
        check_freeze(root); r=Trial(f/entry['run_id'],entry,cfg).run(); rows.append(r)
        compact={k:r[k] for k in ('run_id','status','stop_reason','top8_count','total_M1_calls','time_to_first_pass_s','time_to_eight_s')}
        append(root/'run_completion.jsonl',compact); print(json.dumps(compact),flush=True)
    summary={'run_count':len(rows),'main_M1_calls':sum(r['total_M1_calls'] for r in rows),'main_LLM_API_calls':sum(r['LLM_API_calls'] for r in rows),
        'run_wall_s':time.perf_counter()-start,'execution_failures':sum(r['status']=='EXECUTION_FAILED' for r in rows),'completed_utc':utc()}
    write_new(root/'execution_summary.json',summary); return response('EXPERIMENT_COMPLETE',summary)

def dispatch(mode,out):return {'freeze':freeze,'reference':reference,'run':run}[mode](out)
