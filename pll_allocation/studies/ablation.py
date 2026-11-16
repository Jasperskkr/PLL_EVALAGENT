"""Opt-in M1 ablations. Original evaluator, judgment and RegionExplorer SLSQP.

This module only schedules existing tools and records their provenance. It does
not implement an evaluator, optimizer, or new physical reconstruction formula.
"""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter
import csv
import hashlib
import json
import math
import random
import subprocess
import time

from scipy.stats import qmc
from ..allocation.core import Meter, write_new
from ..allocation.physics import inverse_at_shape, phase_interval, pm_ceiling, RELATIONS
from ..block_space.contracts import FREE_IDS
from ..exploration.contracts import axes, resolve_problem, make_parameters, check_candidate, coordinate, require
from ..exploration.engine import model_identity
from ..exploration.physics_region_builder import gain_tuning_interval, around_seed
from ..physics_mapping.model import fingerprint, PARAMETERS
from ..region_explorer.assessment import physical_coordinate, normalized_point
from ..region_explorer.explorer import RegionExplorer, margin_vector
from .initial_allocation import SEEDS, SPECS, read, sha, sources, rule_window, append
from .multi_region import deterministic_plan
from ..agent.region_policy import LLMRegionPolicy, ProviderError
from ..agent.subregion_context import export_context
from ..agent.subregion_contracts import intent_problem, normalize_multi, validate_multi_plan
from ..agent.subregion_tools import envelope
from ..agent.window_contract import contract_decision

ROOT = Path(__file__).resolve().parents[2]
ALL = {k: [0., 1.] for k in FREE_IDS}
PROMPT = '''Choose exactly THREE distinct initial physical search hypotheses for the supplied ideal CPPLL.
Return JSON only: {"schema_version":"pll-multi-region-plan-1.0","action":"MULTI_REGION_PLAN",
"reason":"...","regions":[three objects]}. Do not invent M1 measurements or use reference witnesses.
Each object has EXACT fields: region_id (safe unique letters/digits/_/- <=40), hypothesis,
evidence_ids (supplied physics.allowed_evidence_ids only), priority (unique1,2,3),
target_bw_fraction [lo,hi] (position inside the BW specification), reserved_bw_margin_fraction,
c1_scale_decades [lo,hi] relative to scale_anchors_SI.C1, c2_c1_ratio [lo,hi],
kvco_scale_decades [lo,hi] relative to scale_anchors_SI.Kvco,
f0_target_fraction [lo,hi] relative to N*fref, strategy, tuning_preference,
search_tools, m1_budget, expected_improvements (string list), failure_modes (string list).
Fixed executor fields: m1_budget is43 for priorities1/2 and42 for priority3;
search_tools is ["PHYSICS_GUIDED_SEEDS","SOBOL_IN_REGION","SLSQP"].
The SAME frozen inverse/Sobol/SLSQP schedule is applied to P0/P1/P2. You only choose
physical geometry, BW target preference, priority and tuning preference. There is no feedback/replanning.
Strategies: HIGH_PM_LF_SHAPE,BW_TARGETED_INVERSE,GAIN_SPLIT_EXPLORATION,VCO_TUNING_EXPLORATION,DIVERSITY_EXPLORATION.
Tuning: INTERIOR,LOW_VOLTAGE,HIGH_VOLTAGE,DIVERSE. The executor uses one tuning
fraction per seed (.5/.2/.8/.5 respectively), avoiding different candidate counts.
No M2, jitter or lock-time judgment. Coordinates/units are Controller metadata.
All five interval fields are finite ordered pairs. BW fractions must satisfy
.01<=reserved_bw_margin_fraction<.5, margin<=lo<hi<=1-margin.
0<f0lo<f0hi<1 and global f0 guard must hold. Kvco/f0 must jointly permit
0<Vreq=(N*fref-f0)/Kvco<1.2V. C1 and Kvco envelopes MUST stay inside fixed global guard.
Ratio upper endpoint must support PM; phase ceiling and necessary_ratio_min are supplied.
Controller compiles a contained C1 slice and corresponding C2 corner-safe interval
inside your coupled ratio envelope. All contraction is logged as Controller output.
Rz/Icp stay in the global guard for original inverse reconstruction.
Choose genuinely different LF ratio/scale, gain/tuning or BW hypotheses based on the
same supplied physics that the deterministic rule sees. Whole regions are uncertified.
The gauge1000Ohm is an arbitrary dimensional anchor, not a circuit capability.
If validation_feedback appears, repair that structural error once. Physical violations
are terminal. Never claim a numerical compiler window is a measured feasible region.'''


def utc():
    return datetime.now(timezone.utc).isoformat()


def raw_problem(problem):
    return {k: deepcopy(v) for k, v in problem.items() if k not in ('problem_sha256', 'screening')}


def subdomain(template, bounds):
    result = deepcopy(template)
    for k, (lo, hi) in bounds.items():
        a = template['parameters'][k]
        low, high = physical_coordinate(a, lo), physical_coordinate(a, hi)
        result['parameters'][k].update(min=low, max=high,
            default=(low+high)/2 if k == 'f0' else math.sqrt(low*high))
    return result


def physics_context(template, gauge):
    from pll_allocation.agent.computational_window import scale_context
    context = scale_context(template, z_gauge=gauge)
    context['heuristic_gauge_guard_NOT_EXECUTED'] = context['numerical_resource_guard']
    context['numerical_resource_guard'] = {k: {x: a[x] for x in ('min', 'max')}
                                          for k, a in template['parameters'].items()}
    context['M2_applicability'] = {'status': 'NOT_RUN_IN_THIS_STUDY'}
    context['necessary_ratio_min'] = (1+math.sin(math.radians(SPECS[template['_spec']][2]))) / (
        1-math.sin(math.radians(SPECS[template['_spec']][2])))-1 if '_spec' in template else None
    return context


def response(status, cost=None):
    return {'status': status, 'strategy': 'spec_allocation_ablation', 'cost': cost or {}, 'failure': None}


def freeze(out):
    root = Path(out).resolve(); frozen = root/'frozen'; frozen.mkdir(parents=True, exist_ok=False)
    baseline = ROOT/'experiments/initial_allocation_a_plus/frozen'
    domains = {}
    for spec in SPECS:
        p = read(baseline/(spec+'.json'))
        p['problem_id'] = 'SPEC_ALLOCATION_ABLATION:'+spec
        p['exploration'].update(max_m1_evaluations=128, physics_seed_count=0, sobol_samples=128)
        resolve_problem(p); write_new(frozen/(spec+'.json'), p); domains[spec] = p['parameters']
    require(all(d == domains['SW'] for d in domains.values()), 'same global guard required')
    task_defs = {
        'task1': {'specs': list(SPECS), 'arms': ['S0','S1','S2'],
                  'factor': 'inverse construction / priority corner only',
                  'fixed_region_normalized': {k: [.1,.9] for k in FREE_IDS},
                  'prior_scale_inverse_calls': 0},
        'task2': {'specs': ['SN','ST'], 'arms': ['G1','G2','G3','G4'],
                  'factor': 'initial scale reference and presence of scale-relative window',
                  'gauge_Ohm': {'G1':100., 'G2':1000., 'G3':10000., 'G4':None},
                  'solver': 'S2', 'note': 'G4 global differs in window presence as explicitly requested; not pure gauge contrast'},
        'task3': {'specs': list(SPECS), 'arms': ['P0','P1','P2'],
                  'factor': 'single-global / rule3 / real-LLM3 initial geometry',
                  'gauge_Ohm':1000., 'solver':'S2', 'multi_region_caps':[43,43,42],
                  'exact_regions': {'P0':1,'P1':3,'P2':3}, 'LLM_calls': 'one plus at most one structural correction',
                  'no_feedback': True, 'LLM_geometry_only': True}}
    matrices = {}
    for index, (task, definition) in enumerate(task_defs.items(), 1):
        rows = [{'run_id': f'{spec}_{arm}_{seed}', 'spec':spec, 'arm':arm, 'seed':seed}
                for spec in definition['specs'] for seed in SEEDS for arm in definition['arms']]
        random.Random(2026111400+index).shuffle(rows); matrices[task] = rows
    cfg = {'schema_version':'pll-spec-allocation-ablation-1.0', 'frozen_utc':utc(),
        'SystemSpec':SPECS, 'seeds':SEEDS, 'domain_mode':'USER_UNBOUNDED', 'user_bounds':None,
        'global_domain':domains['SW'], 'global_guard_origin':
        'A+ topology scales from arbitrary1000Ohm, +/-3decades; finite computational resources, not physical capability',
        'global_guard_fixed_for_all_tasks_and_gauges':True,
        'M1_limit_per_run':128, 'M2_calls':0, 'formal_M1_frequency_grid_points':8000,
        'model':model_identity(), 'task_definitions':task_defs, 'matrices':matrices,
        'shared_solver': {'single_region': {'inverse_seed_slots':9,'Sobol_initial_formal_target':24,'SLSQP_calls':3},
            'three_regions_each': {'inverse_seed_slots':3,'Sobol_initial_formal_target':8,'SLSQP_calls':1},
            'inverse_construction_attempts_per_run':63, 'inverse_proposal_limit':9,
            'SLSQP_budget_per_start':31, 'SLSQP_settings':{'maxiter':40,'finite_difference_step':1e-5},
            'Sobol_max_raw_proposals_per_action':4096,
            'S0_seed_slots': 'same count of Sobol initialized candidates, no inverse anywhere in Task1 S0',
            'remainder': 'Sobol fills unused formal budget, bounded4096 proposals per fill',
            'no_stop_at_first_PASS': True, 'why': 'first-hit plus full-budget yield/diversity measured; no Top8 task',
            'no_inverse_defined_local_box_execution': True,
            'S1_vs_S2':'same low-discrepancy sequence after first index; S2 replaces first LF/x with corner and peak. No HIGH_PM half-box bias elsewhere.',
            'LF_sampling':'Sobol logC1/logC2/BW fraction/x in legal phase interval; ceiling skips logged',
            'gain_tuning':'original inverse_at_shape + original gain_tuning_interval; geometric gain split and interior/requested tuning'},
        'scale_equivalence': {'signature':['C2/C1','Rz*C2','Icp*Kvco/(N*(C1+C2))'],
            'matching':'componentwise absolute log ratio <=1e-6; transfer-function equivalence only, f0 tuning reported separately',
            'gauge_transform':'C1,C2 -> a*C; Rz -> Rz/a; Icp -> a*Icp (Kvco fixed)',
            'never_count_parameter_distance_as_distinct_physical_family': True},
        'reporting': {'first_pass_not_found': 'null time + right-censored at run wall and evaluated M1 count',
            'failed_submission': 'kept in full denominator; zeroM1 physical/planner failures separate from NOT_FOUND',
            'wall_scope':'submission before scale/planning; per-action inclusive times overlap M1; outer CLI separately',
            'all_failures_retained':True, 'compile_changes_owner':'Controller'},
        'provider': read(ROOT/'configs/providers/messages.json'), 'LLM_prompt':PROMPT,
        'no_history_witnesses':True, 'no_post_result_prompt_algorithm_changes':True}
    write_new(frozen/'config.json', cfg); write_new(frozen/'source_manifest.json', sources())
    write_new(frozen/'input_manifest.json', {p.name:sha(p) for p in frozen.iterdir() if p.is_file()})
    snapshot = root/'source_snapshot'; snapshot.mkdir()
    for name in sources():
        dest=snapshot/name; dest.parent.mkdir(parents=True,exist_ok=True); dest.write_bytes((ROOT/name).read_bytes())
    write_new(root/'EXPERIMENT_DESIGN.json',cfg)
    write_new(root/'GIT_BASELINE.json', {'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip(),
        'branch':subprocess.check_output(['git','branch','--show-current'],cwd=ROOT).decode().strip()})
    (root/'GIT_STATUS_BEFORE.bin').write_bytes(subprocess.check_output(['git','status','--porcelain=v1','-z'],cwd=ROOT))
    protection={p.relative_to(ROOT).as_posix():sha(p)
        for folder in ('initial_allocation_a_plus','stage7_8_multiregion_20261113_01','stage7_8_multiregion_20261113_02')
        for p in (ROOT/'experiments'/folder).rglob('*') if p.is_file()}
    write_new(root/'PROTECTED_HISTORY.json',protection)
    return response('ABLATION_FROZEN',{'M1':0,'API':0})


def check_freeze(root):
    f=root/'frozen'; require(sources()==read(f/'source_manifest.json'),'source changed after preregistration')
    for name,digest in read(f/'input_manifest.json').items():
        require(sha(f/name)==digest, 'input changed: '+name)
    return read(f/'config.json')


def loop_signature(parameters):
    v={k:parameters['values'][k]['value'] for k in FREE_IDS}
    n=parameters['values']['N']['value']
    return [v['C2']/v['C1'], v['Rz']*v['C2'], v['Icp']*v['Kvco']/(n*(v['C1']+v['C2']))]


def equivalent_signature(a,b):
    return all(abs(math.log(x/y))<=1e-6 for x,y in zip(a,b))


def inverse_stream(problem, *, seed, mode, attempts, max_seeds, target_fraction, tuning):
    """Construction policy adapter to the original inverse and joint precheck.

S1/S2 share every draw except the first shape. No PM/BW result is fabricated.
The stream yields trace records as well as original-tool candidate parameters.
"""
    meter=Meter(cheap_limit=attempts,m1_limit=0)
    draws=qmc.Sobol(d=4,scramble=True,seed=seed).random_base2((attempts-1).bit_length())
    axes_=problem['parameters']; fixed=problem['fixed_parameters']; count=0
    bw=next(s for s in problem['specs'] if s['metric']=='BW_Hz')
    pm=next(s for s in problem['specs'] if s['metric']=='PM_deg')['min']
    for index,u in enumerate(draws[:attempts]):
        if count>=max_seeds:break
        start=time.perf_counter()
        c1=physical_coordinate(axes_['C1'],float(u[0]));c2=physical_coordinate(axes_['C2'],float(u[1]))
        if mode=='S2' and index==0:c1,c2=axes_['C1']['min'],axes_['C2']['max']
        interval=phase_interval(c1,c2,pm)
        record={'attempt':index+1,'C1_F':c1,'C2_F':c2,'PM_ceiling_deg':pm_ceiling(c1,c2),
            'corner_priority':mode=='S2' and index==0,'inverse_called':False,'parameters':None}
        try:
            if interval is None:
                record['status']='LF_PHASE_CEILING_REJECTED';continue
            x=math.exp(math.log(interval[0])+float(u[3])*math.log(interval[1]/interval[0]))
            if mode=='S2' and index==0:x=math.sqrt(1+c2/c1)
            fraction=target_fraction[0]+float(u[2])*(target_fraction[1]-target_fraction[0])
            target=bw['min']+fraction*(bw['max']-bw['min'])
            record.update(shape_x=x,target_BW_Hz=target,inverse_called=True)
            raw=inverse_at_shape(axes(problem),c1,c2,target,x,meter)
            if raw is None:record['status']='INVERSE_GAIN_CONFLICT';continue
            if not axes_['Rz']['min']<=raw['Rz']<=axes_['Rz']['max']:
                record.update(status='INVERSE_RZ_OUTSIDE_REGION',Rz_Ohm=raw['Rz']);continue
            product=raw['Icp']*raw['Kvco'];joint=gain_tuning_interval(problem,product)
            record['gain_tuning_precheck']=joint
            if joint['status']!='JOINT_INTERVAL_COMPATIBLE':record['status']=joint['status'];continue
            klo,khi=joint['tuning_compatible_Kvco_interval'];kv=math.sqrt(klo*khi)
            target_f=fixed['N']['value']*fixed['f_ref']['value']
            vlo=max(fixed['Vctrl_min']['value'],(target_f-axes_['f0']['max'])/kv)
            vhi=min(fixed['Vctrl_max']['value'],(target_f-axes_['f0']['min'])/kv)
            fraction={'INTERIOR':.5,'LOW_VOLTAGE':.2,'HIGH_VOLTAGE':.8,'DIVERSE':.5}[tuning]
            raw.update(Kvco=kv,Icp=product/kv,f0=target_f-kv*(vlo+fraction*(vhi-vlo)))
            candidate=make_parameters(problem,raw)
            screen=check_candidate(problem,candidate);record['screening']=screen
            if screen['status']!='NECESSARY_CONDITIONS_SATISFIED':
                record['status']='SEED_SCREEN_REJECTED';continue
            count+=1;record.update(status='SEED_CONSTRUCTED',parameters=candidate,
                parameter_sha256=fingerprint(candidate),seed_local_box_NOT_EXECUTED=around_seed(problem,candidate,'BALANCED'))
        except (ValueError,ArithmeticError,RuntimeError) as error:
            record.update(status='INVERSE_EXCEPTION',error=type(error).__name__+': '+str(error))
        finally:
            record['wall_s']=time.perf_counter()-start
            record['cumulative_inverse_calls']=meter.counts['analytic_calls']
            yield record


class AblationTrial:
    def __init__(self,root,task,entry,cfg,*,limit=128):
        self.root=root;self.root.mkdir(parents=True,exist_ok=False)
        self.task=task;self.entry=entry;self.cfg=cfg;self.limit=limit
        self.raw=read(root.parents[1]/'frozen'/(entry['spec']+'.json')) if task!='smoke' else None
        self.started=time.perf_counter();self.explorers=[];self.rows=[];self.seen=set()
        self.first=None;self.timings=[];self.llm=[];self.constructions=[];self.regions=[];self.current=None
        self.error=None;self.legal=None;self.proposed=None;self.planner_calls=0
        write_new(root/'submission.json',{'task':task,'entry':entry,'submitted_utc':utc(),
            'M1_limit':limit,'M2_calls':0,'no_history_candidate_loaded':True})

    def elapsed(self):return time.perf_counter()-self.started

    def calls(self):return sum(e.counts['M1_calls'] for e in self.explorers)

    def timed(self,category,name,func):
        start=self.elapsed();before=self.calls()
        try:return func()
        finally:
            record={'category':category,'name':name,'started_s':start,'ended_s':self.elapsed(),
                'inclusive_wall_s':self.elapsed()-start,'M1_calls':self.calls()-before}
            self.timings.append(record);append(self.root/'timing_events.jsonl',record)

    def collect(self,row):
        key=(len(self.explorers),row['evidence_id'])
        if key in self.seen:return False
        self.seen.add(key)
        formal=row['formal_M1_called']
        record=deepcopy(row)|{'region_id':self.current,'observed_elapsed_s':self.elapsed(),
            'global_M1_call_index':self.calls() if formal else None,
            'pipeline_stage':'m1_result','source':row['origin']}
        if formal:
            record['M1_return_elapsed_s']=row['cost']['evaluation_timing']['perf_counter_finished']-self.started
            record['loop_signature']=loop_signature(row['parameters'])
        self.rows.append(record);append(self.root/'all_candidates.jsonl',record)
        if formal and row['judgment']['m1_feasibility']=='FEASIBLE' and self.first is None:
            self.first=deepcopy(record);write_new(self.root/'first_PASS.json',self.first)
        return False

    def execute(self,ex,decision,stream=None):
        before=len(ex.rows)
        obs=self.timed('optimizer' if decision['search_method']=='SLSQP' else 'search',decision['decision_id'],
            lambda:ex.execute(decision,candidate_stream=stream,tool_name='PHYSICS_GUIDED_SEEDS' if stream is not None else None))
        for row in ex.rows[before:]:self.collect(row)
        append(self.root/'actions.jsonl',obs)
        require(obs['failure'] is None,'original executor ACTION_ERROR: '+str(obs['failure']))
        return obs

    def sobol(self,ex,ident,budget):
        if budget<1:return
        stage=1 if ident.endswith(':SHARED_SOBOL') else 2 if ident.endswith(':REMAINDER') else 0
        d=envelope(ex,decision_id=ident,region_id=ident,bounds=ALL,budget=budget,
            seed=self.entry['seed']+len(self.explorers)*10000+stage*1000,proposals=4096)
        return self.execute(ex,d)

    def region(self,raw,ident,budget,mode,*,slots,attempts,probe,opt_starts,target_fraction=(.5,.5),tuning='INTERIOR'):
        self.current=ident;folder=self.root/('region_'+ident);folder.mkdir()
        p=resolve_problem(raw)
        info={'pipeline_stage':'executed_region','region_id':ident,'compiled_region':raw['parameters'],
            'executed_region':p['parameters'],'global_normalized_bounds':{k:[coordinate(self.raw['parameters'][k],a[x])
                for x in ('min','max')] for k,a in p['parameters'].items()},
            'budget':budget,'mode':mode,'source_of_bounds':'pre-inverse compiled domain; no seed-defined shrink',
            'inverse_seed_local_boxes_executed':False}
        self.regions.append(info);write_new(folder/'region_contract.json',info)
        context=self.timed('setup',ident,lambda:export_context(p,[],folder/'empty_context',cost={'M1_calls':0},scope='EMPTY_BOOTSTRAP_NO_SEARCH'))
        ex=RegionExplorer(context,folder/'executor',m1_budget=budget,budget_scheduling=True,stop_when=self.collect)
        self.explorers.append(ex)
        if mode!='S0':
            def construct():
                result=[]
                for attempt in inverse_stream(p,seed=self.entry['seed'],mode=mode,attempts=attempts,
                        max_seeds=slots,target_fraction=target_fraction,tuning=tuning):
                    self.constructions.append(attempt);append(folder/'inverse_attempts.jsonl',attempt)
                    if attempt['parameters'] is not None:result.append(attempt['parameters'])
                return result
            candidates=self.timed('physics',ident+':INVERSE',construct)
            write_new(folder/'inverse_seeds_BEFORE_M1.json',{'pipeline_stage':'inverse_seed','candidates':candidates})
            if candidates:
                d=envelope(ex,decision_id=ident+':INVERSE',region_id=ident+':INVERSE',bounds=ALL,
                    budget=min(slots,budget),seed=self.entry['seed'],proposals=len(candidates))
                self.execute(ex,d,iter(candidates))
            deficit=slots-ex.counts['M1_calls']
            if deficit>0:self.sobol(ex,ident+':SLOT_FILL',min(deficit,budget-ex.counts['M1_calls']))
        else:self.sobol(ex,ident+':NO_INVERSE_INIT',min(slots,budget))
        self.sobol(ex,ident+':SHARED_SOBOL',min(probe,budget-ex.counts['M1_calls']))
        used_seeds=set()
        for i in range(opt_starts):
            remaining=budget-ex.counts['M1_calls']
            usable={r['parameter_sha256']:r for r in ex.rows if margin_vector(p,r) and r['parameter_sha256'] not in used_seeds}
            ranked=sorted(usable.values(),key=lambda r:-r['judgment']['minimum_normalized_margin'])
            if remaining<23 or not ranked:break
            row=ranked[0];used_seeds.add(row['parameter_sha256'])
            d=envelope(ex,decision_id=ident+':SLSQP:'+str(i),region_id=ident+':SLSQP:'+str(i),
                bounds=ALL,budget=min(31,remaining),seed=self.entry['seed'],proposals=1)
            d.update(action='OPTIMIZE',search_method='SLSQP',seed_ids=[row['evidence_id']],
                settings=deepcopy(self.cfg['shared_solver']['SLSQP_settings']))
            self.execute(ex,d)
        if budget>ex.counts['M1_calls']:self.sobol(ex,ident+':REMAINDER',budget-ex.counts['M1_calls'])
        ex.close()
        write_new(folder/'region_result.json',{'M1_calls':ex.counts['M1_calls'],
            'feasible_formal':sum(r['formal_M1_called'] and r['judgment']['m1_feasibility']=='FEASIBLE' for r in ex.rows),
            'stop':'FORMAL_BUDGET_EXHAUSTED' if ex.counts['M1_calls']==budget else 'BOUNDED_PROPOSALS_EXHAUSTED'})

    def get_physics(self,gauge):
        value=self.timed('physics','SCALE_CONTEXT',lambda:physics_context(self.raw,gauge))
        pm=SPECS[self.entry['spec']][2];s=math.sin(math.radians(pm))
        value['necessary_ratio_min']=(1+s)/(1-s)-1
        write_new(self.root/'physics_context.json',value);return value

    def plan_three(self,physics):
        state={'schema_version':'pll-spec-allocation-ablation-planner-1.0','case_id':self.entry['run_id'],
            'specs':self.raw['specs'],'fixed_parameters':self.raw['fixed_parameters'],'physics':physics,
            'domain_mode':'USER_UNBOUNDED','user_parameter_bounds':None,'global_domain':self.raw['parameters'],
            'budget':{'total_formal_M1':128,'region_caps_by_priority':[43,43,42]},
            'planner_authority':'three physical intents and priority; solver/tool/budget fixed',
            'seed':self.entry['seed'],'no_history_or_M1_observation':True}
        state['state_sha256']=fingerprint(state);write_new(self.root/'PlannerState.json',state)
        def validate(plan,current):
            validate_multi_plan(plan,template=self.raw,physics=physics,min_regions=3,max_regions=3)
            for r in plan['regions']:
                require(r['m1_budget']==(43,43,42)[r['priority']-1], 'frozen budget by priority required')
                require(set(r['search_tools'])=={'PHYSICS_GUIDED_SEEDS','SOBOL_IN_REGION','SLSQP'},'same frozen solver pool required')
            return plan
        if self.entry['arm']=='P2':
            policy=LLMRegionPolicy(self.cfg['provider'],prompt=self.cfg['LLM_prompt'])
            try:
                value=self.timed('llm','INITIAL_THREE_REGIONS',lambda:contract_decision(policy,state,self.root/'planner',
                    normalize=normalize_multi,validate=validate,raw_alias='LLM_original_proposal.json'))
            finally:self.llm=deepcopy(policy.calls)
        else:
            value=self.timed('planner','RULE_THREE_REGIONS',lambda:deterministic_plan(self.raw,physics))
            for r in value['regions']:
                r['search_tools']=['PHYSICS_GUIDED_SEEDS','SOBOL_IN_REGION','SLSQP']
            write_new(self.root/'rule_original_proposal.json',value);validate(value,state)
        self.proposed=value;return value

    def run(self):
        write_new(self.root/'global_domain.json',{'pipeline_stage':'global_domain','parameters':self.raw['parameters'],
            'model':self.cfg['model'],'specs':self.raw['specs'],'user_bounds':None})
        try:
            arm=self.entry['arm'];mode='S2'
            if self.task=='task1':
                mode=arm;raw=subdomain(self.raw,self.cfg['task_definitions']['task1']['fixed_region_normalized'])
                write_new(self.root/'proposed_region.json',{'pipeline_stage':'proposed_region','parameters':raw['parameters'],
                    'ownership':'frozen pre-inverse normalized[.1,.9]','scale_context_calls':0})
                self.legal=True;self.region(raw,'REGION',self.limit,mode,slots=9,attempts=63,probe=24,opt_starts=3)
            elif self.task=='task2':
                gauge=self.cfg['task_definitions']['task2']['gauge_Ohm'][arm]
                if gauge is None:raw=deepcopy(self.raw)
                else:
                    physics=self.get_physics(gauge)
                    proposal=rule_window({'physics':physics,'round':1,'template':self.raw,'state_sha256':'NO_LLM'})
                    write_new(self.root/'raw_scale_window.json',proposal)
                    raw=deepcopy(self.raw)
                    for k,a in proposal['parameters'].items():
                        raw['parameters'][k]=a|{'default':(a['min']+a['max'])/2 if k=='f0' else math.sqrt(a['min']*a['max'])}
                write_new(self.root/'proposed_region.json',{'pipeline_stage':'proposed_region','parameters':raw['parameters'],
                    'gauge_Ohm':gauge,'global_guard_changed':False})
                self.legal=True;self.region(raw,'REGION',128,'S2',slots=9,attempts=63,probe=24,opt_starts=3)
            else:
                physics=self.get_physics(1000.)
                if arm=='P0':
                    write_new(self.root/'proposed_region.json',{'pipeline_stage':'proposed_region','parameters':self.raw['parameters'],'source':'P0_GLOBAL'})
                    self.legal=True;self.region(self.raw,'GLOBAL',128,'S2',slots=9,attempts=63,probe=24,opt_starts=3)
                else:
                    plan=self.plan_three(physics);self.legal=True
                    for intent in sorted(plan['regions'],key=lambda r:r['priority']):
                        raw,compiled=intent_problem(self.raw,intent,physics['scale_anchors_SI'])
                        write_new(self.root/(intent['region_id']+'_compiled.json'),{'pipeline_stage':'compiled_region',
                            'proposed_region':intent,'compiled_region':raw['parameters'],'owner':'Controller',
                            'requested_C1_F':[physics['scale_anchors_SI']['C1']*10**x for x in intent['c1_scale_decades']],
                            'no_seed_used_for_compilation':True})
                        self.region(raw,intent['region_id'],intent['m1_budget'],'S2',slots=3,attempts=21,
                            probe=8,opt_starts=1,target_fraction=intent['target_bw_fraction'],tuning=intent['tuning_preference'])
        except (ValueError,ProviderError,KeyError,TypeError) as error:
            self.legal=False if not self.explorers else self.legal
            self.error={'type':type(error).__name__,'reason':str(error),'executed_regions':len(self.explorers)}
            write_new(self.root/'failure.json',self.error)
        finally:
            for ex in self.explorers:
                if not ex.closed:ex.close()
        return self.finish()

    def finish(self):
        formal=[r for r in self.rows if r['formal_M1_called']]
        require(len(formal)==self.calls()<=self.limit,'formal accounting mismatch')
        passed=[r for r in formal if r['judgment']['m1_feasibility']=='FEASIBLE']
        families=[]
        for r in passed:
            if not any(equivalent_signature(r['loop_signature'],s) for s in families):families.append(r['loop_signature'])
        wall=self.elapsed();m1times=[r['cost']['evaluation_timing']['wall_time_s'] for r in formal]
        scale_calls=1 if (self.root/'physics_context.json').exists() else 0
        result={'task':self.task,**self.entry,'status': 'EXECUTION_FAILURE' if self.error else 'PASS_FOUND' if passed else 'NOT_FOUND',
            'failure':self.error,'proposal_legal':self.legal,'actual_regions':len(self.regions),'M1_calls':self.calls(),
            'formal_budget_exhausted':self.calls()==self.limit,'M1_limit':self.limit,'M2_calls':0,
            'first_PASS':self.first is not None,'first_candidate_PASS':bool(formal and formal[0]['judgment']['m1_feasibility']=='FEASIBLE'),
            'M1_to_first_PASS':self.first['global_M1_call_index'] if self.first else None,
            'time_to_first_PASS_s':self.first['M1_return_elapsed_s'] if self.first else None,
            'time_censored':self.first is None,'censor_at_wall_s':wall,'censor_at_M1_calls':self.calls(),
            'total_wall_s':wall,'feasible_formal_calls':len(passed),'unique_feasible_candidates':len({r['parameter_sha256'] for r in passed}),
            'response_families_at_log_tolerance_1e_6':len(families),
            'best_margin':max((r['judgment']['minimum_normalized_margin'] for r in passed),default=None),
            'first_margin':self.first['judgment']['minimum_normalized_margin'] if self.first else None,
            'construction_attempts':len(self.constructions),'inverse_calls':sum(r['inverse_called'] for r in self.constructions),
            'scale_prior_inverse_calls':scale_calls,'invalid_inverse_attempts':sum(r['status']!='SEED_CONSTRUCTED' for r in self.constructions),
            'invalid_inverse_called_fraction':(sum(r['inverse_called'] and r['status']!='SEED_CONSTRUCTED' for r in self.constructions)/
                sum(r['inverse_called'] for r in self.constructions)) if any(r['inverse_called'] for r in self.constructions) else None,
            'SLSQP_starts':sum(s.get('started',False) for ex in self.explorers for ob in ex.observations for s in ob['solver_runs']),
            'SLSQP_actions':sum(ob['action']=='OPTIMIZE' for ex in self.explorers for ob in ex.observations),
            'solver_failures':[deepcopy(s) for ex in self.explorers for ob in ex.observations
                for s in ob['solver_runs'] if s.get('status') in ('SOLVER_EXCEPTION','NOT_CONVERGED')],
            'solver_failure_policy':'Numerical SLSQP failures retained as optimizer outcomes; executor ACTION_ERROR is major and stops batch',
            'API_calls':len(self.llm),'API_latency_s':sum(x['elapsed_s'] for x in self.llm),
            'LLM_calls':self.llm,'M1_total_wall_s':sum(m1times),
            'timings':self.timings,'actual_region_contracts':self.regions,
            'unknown_certification':'M1 model only; no independent physical or M2 certification'}
        write_new(self.root/'result.json',result);return result


def smoke(root):
    cfg=check_freeze(root);folder=root/'task0_smoke';folder.mkdir(exist_ok=False)
    rows=[]
    for arm in ('S0','S1','S2'):
        entry={'run_id':'SN_'+arm+'_SMOKE','spec':'SN','arm':arm,'seed':9173}
        trial=AblationTrial(folder/entry['run_id'],'smoke',entry,cfg,limit=64)
        trial.raw=read(root/'frozen/SN.json');trial.task='task1'
        rows.append(trial.run())
    require(all(r['M1_calls']<=64 and r['failure'] is None for r in rows),'smoke execution invalid')
    require(rows[0]['inverse_calls']==0 and rows[0]['scale_prior_inverse_calls']==0,'S0 inverse leak')
    write_new(root/'TASK0_GATE.json',{'accepted':True,'smoke_runs':3,'M1_calls':sum(r['M1_calls'] for r in rows),
        'API_calls':0,'no_model_or_judgment_changed':True,'rows':rows})
    return response('TASK0_SMOKE_COMPLETE',{'M1':sum(r['M1_calls'] for r in rows),'API':0})


def run_task(root,task):
    cfg=check_freeze(root)
    gate={'task1':'TASK0_GATE.json','task2':'TASK1_GATE.json','task3':'TASK2_GATE.json'}[task]
    require(read(root/gate)['accepted'],'previous task gate not accepted')
    require(read(root/(task.upper()+'_TEST_GATE.json'))['accepted'],'stage tests required before running')
    folder=root/task;folder.mkdir(exist_ok=False);start=time.perf_counter();rows=[]
    for entry in cfg['matrices'][task]:
        trial=AblationTrial(folder/entry['run_id'],task,entry,cfg)
        rows.append(trial.run());append(root/(task+'_completion.jsonl'),rows[-1])
        if rows[-1]['failure'] and not (task=='task3' and entry['arm']=='P2' and not trial.explorers):
            write_new(root/(task+'_MAJOR_CONTRACT_STOP.json'),{'run_id':entry['run_id'],
                'failure':rows[-1]['failure'],'completed_runs':len(rows),'new_tasks_allowed':False})
            raise ValueError('major execution contract failure; stop before additional runs')
    write_new(root/(task+'_summary.json'),{'rows':rows,'wall_s':time.perf_counter()-start,
        'M1_calls':sum(r['M1_calls'] for r in rows),'API_calls':sum(r['API_calls'] for r in rows)})
    return response(task.upper()+'_COMPLETE',{'M1':sum(r['M1_calls'] for r in rows),'API':sum(r['API_calls'] for r in rows)})


def dispatch(mode,out):
    root=Path(out).resolve()
    if mode=='freeze':return freeze(root)
    if mode=='smoke':return smoke(root)
    if mode in ('task1','task2','task3'):return run_task(root,mode)
    if mode=='report':
        from .ablation_report import report
        return report(root)
    raise ValueError('unknown ablation phase')
