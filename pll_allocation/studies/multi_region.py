"""Opt-in scheduling study over existing subregion tools, Builder and Explorer.

There is no evaluator or optimizer here. P1/P2 differ only in physical intents
and feedback choices; the controller executes identical tools and hard budgets.
"""
from copy import deepcopy
import json
import math
from pathlib import Path
import random
import time
import numpy as np
from ..allocation.core import Meter,write_new
from ..block_space.contracts import FREE_IDS
from ..exploration.contracts import resolve_problem,coordinate,make_parameters,require
from ..exploration.engine import model_identity
from ..exploration.physics_region_builder import build_physics_region,validate_request
from ..physics_mapping.model import fingerprint
from ..region_explorer.assessment import normalized_point,physical_coordinate,contains_parameters
from .initial_allocation import Trial,read,sha,utc,append,sources,SPECS,SEEDS,response
from ..agent.region_policy import LLMRegionPolicy,ProviderError
from ..agent.window_contract import contract_decision,ContractError
from ..agent.subregion_contracts import MULTI_SCHEMA,normalize_multi,validate_multi_plan,intent_problem,volume
from ..agent.subregion_tools import envelope,execute_tool

PROMPT='''Plan multiple testable physical hypotheses for the USER_UNBOUNDED ideal CPPLL.
No historical/reference point is provided. Do not compute or invent M1 measurements.
Return only JSON: {"schema_version":"pll-multi-region-plan-1.0","action":"MULTI_REGION_PLAN",
"reason":"...","regions":[2 or 3 region objects]}. Each region has EXACTLY:
Prefer two carefully checked, distinct hypotheses. Add a third only when all
three independently obey the contract. Controller still allows both two and three.
region_id (unique letters/digits/_/- <=40), hypothesis, evidence_ids (from allowed IDs), priority(unique1..3),
target_bw_fraction [lo,hi] (position WITHIN BW spec), reserved_bw_margin_fraction (0.01..0.49,
lo>=margin and hi<=1-margin), c1_scale_decades [lo,hi] relative to scale_anchors_SI.C1,
c2_c1_ratio [positive lo,hi], kvco_scale_decades [lo,hi] relative to scale_anchors_SI.Kvco,
f0_target_fraction [lo,hi] between0 and1 relative N*fref, strategy (original Builder strategy),
tuning_preference INTERIOR/LOW_VOLTAGE/HIGH_VOLTAGE/DIVERSE,
search_tools (unique shared supported methods, MUST include PHYSICS_GUIDED_SEEDS and SOBOL_IN_REGION;
may include SLSQP,LOCAL_SENSITIVITY,ANALYTICAL_INVERSE), m1_budget(integer24..64, sum<=128),
expected_improvements(nonempty string list), failure_modes(nonempty string list).
Choose genuinely different LF shape/absolute scale, gain split, tuning, or BW hypotheses; explain physical evidence.
Controller compiles the coupled LF intent into a finite contained computational slice;
it chooses a centered C1 subinterval narrow enough to satisfy all requested C2/C1 ratios.
You choose physical envelopes, not coordinate/corner arithmetic. Compiler output is not credited as LLM output.
Chosen C1/Kvco/f0 endpoints MUST fit the supplied fixed hard guard. f0 minimum MUST BE STRICTLY POSITIVE
and at least guard.f0.min/(N*fref), never 0. Ratios must support PM; see necessary_ratio_min.
target_bw_fraction is the fractional position INSIDE the BW spec, not absolute BW or fref fraction.
Both target endpoints must preserve reserved_bw_margin_fraction; e.g. [.2,.8] with margin.1 is legal.
Use ONLY physics.allowed_evidence_ids verbatim; identifiers are not equation names you invent.
Rz/Icp remain guard-bounded for the original inverse to solve. Ratio ceiling must support PM spec.
Gain/tuning compatibility is enforced. Fixed coordinates/units/hashes are Controller metadata; do not supply them.
Builder strategies: HIGH_PM_LF_SHAPE,BW_TARGETED_INVERSE,GAIN_SPLIT_EXPLORATION,VCO_TUNING_EXPLORATION,DIVERSITY_EXPLORATION.
Initial per-region diagnostic schedule: up to3 original Builder seeds, up to3 Sobol M1,
then up to12 sensitivity M1 if requested and a legal in-box point exists. Deferred SLSQP needs feedback.
Every region really searches its own constructed box; no global seed reuse. Unused allocated calls are unspent.
After RegionObservations you will choose a next actual region action. All formal calls, including probes,
differences and connectivity, are charged. Lock/jitter/M2 are outside this experiment.
If validation_feedback appears, repair the specified structural error once; physical invalidity is terminal.'''

FEEDBACK_PROMPT='''Read actual controller RegionObservations of the ideal CPPLL search; do not invent actions/results.
Return exactly {action,region_id,region,m1_budget,reason,evidence_ids} as JSON.
action: CONTINUE_REGION / REFINE_REGION / EXPLORE_ANOTHER / STOP.
CONTINUE_REGION selects an existing region_id; region=null. It runs the same original SLSQP and
coupled inverse, then local Sobol if needed. Prefer measured tight constraints/sensitivity and distinct coverage.
REFINE_REGION or EXPLORE_ANOTHER supplies a complete new region object with the exact initial-plan fields,
new unique region_id, physically distinct parameters and hypothesis. region_id must equal that new region's ID.
All original intent constraints still apply (provided initial_contract). New regions execute their own construction/probes.
m1_budget is integer24..available_search_M1 for an action; STOP uses0 and region_id=null,region=null.
For STOP cite actual evidence/reason; eight points means only if actual top8_count==8 and first included.
Choose STOP when useful budget is insufficient, sufficient points found, or honestly justified measured stall.
Cite only allowed_evidence_ids, including actual OBS records. Local slopes are local, rectangles are uncertified.
All decisions are proposals; the Controller logs the actual tool execution. No spec/guard/model changes.'''


def response(status,cost):
    return {'status':status,'strategy':'multi_region_study','cost':cost,'failure':None}


def deterministic_plan(template,physics):
    pm=next(s['min'] for s in template['specs'] if s['metric']=='PM_deg')
    sine=math.sin(math.radians(min(87.,pm+8.)));ratio=(1+sine)/(1-sine)-1
    regions=[]
    for i,(cap,bw,kv,tune,strategy) in enumerate([
        ([-.6,-.2],[.42,.58],[-.1,.4],'INTERIOR','HIGH_PM_LF_SHAPE'),
        ([.15,.55],[.24,.4],[.4,.9],'LOW_VOLTAGE','GAIN_SPLIT_EXPLORATION'),
        ([-1.2,-.8],[.6,.76],[-.2,.3],'HIGH_VOLTAGE','VCO_TUNING_EXPLORATION')],1):
        regions.append({'region_id':'RULE_'+str(i),'hypothesis':[
            'Peak LF phase shape, central BW and interior tuning.',
            'Larger capacitors and higher Kvco trade current for gain; lower BW guards PM.',
            'Smaller capacitance, upper BW and high-voltage tuning test a distinct scale.'][i-1],
            'evidence_ids':['REL:shape','REL:phase_ceiling','REL:inverse_gain','REL:frequency'],
            'priority':i,'target_bw_fraction':bw,'reserved_bw_margin_fraction':.12,
            'c1_scale_decades':cap,'c2_c1_ratio':[ratio,min(ratio*16,
                template['parameters']['C2']['max']/(physics['scale_anchors_SI']['C1']*10**cap[0])*.9)],
            'kvco_scale_decades':kv,'f0_target_fraction':[.1,.9],
            'strategy':strategy,'tuning_preference':tune,
            'search_tools':['PHYSICS_GUIDED_SEEDS','SOBOL_IN_REGION','LOCAL_SENSITIVITY','SLSQP'],
            'm1_budget':(43,43,42)[i-1],'expected_improvements':['BW interval headroom','PM phase ceiling'],
            'failure_modes':['Original inverse may not find gain/tuning intersection','Measured PM can fall below phase ceiling']})
    return {'schema_version':MULTI_SCHEMA,'action':'MULTI_REGION_PLAN',
        'reason':'Preregistered three physical hypotheses from spec-relative phase ceiling and scale gauge.', 'regions':regions}


def freeze(out):
    root=Path(out).resolve();require(read(root/'PHASE0_GATE.json')['accepted'],'Phase0 regression gate required')
    folder=root/'frozen';folder.mkdir(exist_ok=False)
    baseline=Path(__file__).resolve().parents[2]/'experiments/initial_allocation_a_plus'
    old=read(baseline/'frozen/config.json')
    for s in SPECS:write_new(folder/(s+'.json'),read(baseline/'frozen'/(s+'.json')))
    order=[{'run_id':f'{s}_{p}_{seed}','spec':s,'policy':p,'seed':seed} for seed in SEEDS for s in SPECS for p in ('P1','P2')]
    random.Random(2026111308).shuffle(order)
    cfg={k:deepcopy(old[k]) for k in ('hard_numerical_resource_guard','minimum_normalized_margin',
        'minimum_tuning_margin_V','diversity_rms_threshold','slsqp','provider')}
    cfg.update(schema_version='pll-multi-region-study-1.0',domain_mode='USER_UNBOUNDED',user_parameter_bounds=None,
        seeds=list(SEEDS),run_order=order,phase1_M1_limit=128,phase2_M1_limit=128,connectivity_reserve=21,
        max_feedback_decisions=2,structured_corrections_per_decision=1,initial_regions=[2,3],initial_Stage7_M1=0,
        probe_schedule='Builder3 + Sobol3 + optional original sensitivity12 per region; each region cap from planner',
        expansion_schedule='feedback selected region: original subset SLSQP, coupled Builder, local Sobol; same P1/P2',
        budget_semantics='initial m1_budget caps diagnostic probe; feedback m1_budget authorizes additional region search; all share first128+extra128 hard caps',
        total_source='same frozen guard/spec/model as A+, fresh plans/seeds/API; no historical candidate is loaded',
        reference_status_gate=read(baseline/'REFERENCE_GATE.json'),reference_witness_shared=False,
        baseline_input_hashes={s:sha(baseline/'frozen'/(s+'.json')) for s in SPECS},
        baseline_label='SINGLE_WINDOW; never pooled with multi-region',M2_calls=0,
        compiler_version='coupled-intent-contained-slice-v2',
        compiler_rule='geometric feasible C1 center, log halfwidth min(original halfwidth, log(ratio_hi/lo)/4); C2 obeys ratio corners and guard',
        model=model_identity(),planner_prompt=PROMPT,feedback_prompt=FEEDBACK_PROMPT,frozen_utc=utc())
    write_new(folder/'config.json',cfg);write_new(folder/'source_manifest.json',sources())
    write_new(folder/'input_manifest.json',{p.name:sha(p) for p in folder.iterdir() if p.is_file()})
    snap=root/'source_snapshot';snap.mkdir()
    for name in sources():
        p=snap/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((Path(__file__).resolve().parents[2]/name).read_bytes())
    write_new(root/'EXPERIMENT_DESIGN.json',cfg)
    return response('MULTI_REGION_FROZEN',{'M1_calls':0})


def check_freeze(root):
    folder=root/'frozen';require(sources()==read(folder/'source_manifest.json'),'source changed after freeze')
    for name,digest in read(folder/'input_manifest.json').items():require(sha(folder/name)==digest,'frozen input changed')
    return read(folder/'config.json')


class MultiTrial(Trial):
    def __init__(self,root,entry,cfg):
        super().__init__(root,entry,cfg)
        self.regions={};self.observations=[];self.feedback=[];self.active_bounds={k:[0.,1.] for k in FREE_IDS}
        self.first_ex=None;self.feedback_used=[];self.inverse_meter_calls=0
    def target(self,row):
        self.log(row)
        if self.first is None and row['formal_M1_called'] and row['judgment']['m1_feasibility']=='FEASIBLE':
            self.first=self.candidates[-1];self.first_region=self.current_region
            self.ex.limit=self.first['M1_call_index']+self.cfg['phase2_M1_limit']
            self.ex._event('CONTROLLER_PHASE2_BUDGET_ACTIVATED',first_formal_PASS_call=self.first['M1_call_index'],
                extra_M1_limit=128,total_session_limit=self.ex.limit)
        return self.phase=='PHASE2_SEARCH' and len(self.selected)==8
    def remaining(self,reserve=0):
        cap=(self.first['M1_call_index']+128) if self.first else 128
        return max(0,cap-self.calls()-(reserve if self.first else 0))
    def point(self,ex,p,ident,tool='PHYSICS_GUIDED_SEEDS'):
        d=envelope(ex,decision_id=ident,region_id=ident,bounds=self.active_bounds,budget=1,
            seed=self.entry['seed']+len(self.actions),proposals=1)
        return self.perform(ex,d,iter([p]),tool)
    def tool(self,r,method,budget,seed_id=None):
        if budget<=0:return None
        before=len(self.ex.rows);meter=Meter(cheap_limit=64,m1_limit=0)
        ident=r['intent']['region_id']+':'+method+':'+str(len(self.actions))
        config={'max_tool_proposals':128}
        if method=='SLSQP':
            relevant=next((o for o in reversed(self.observations) if o['region_id']==r['intent']['region_id'] and o.get('sensitivity')),None)
            reps=relevant['sensitivity'].get('representatives',[]) if relevant else []
            if reps:
                center=self.ex.evidence[reps[0]['center_evidence_id']]
                constraints=[c for c in center['judgment']['constraints'] if c['enabled'] and c['normalized_margin'] is not None]
                tight=min(constraints,key=lambda c:c['normalized_margin']) if constraints else None
                column=reps[0]['normalized_matrix'].get(tight['metric'],{}) if tight else {}
                ranked=sorted((k for k,v in column.items() if v is not None and abs(v)>1e-10),key=lambda k:-abs(column[k]))
                if ranked:config['active_variables']=ranked[:3]
        obs=self.timed('optimizer' if method=='SLSQP' else 'sensitivity' if method=='LOCAL_SENSITIVITY' else 'search_tool',ident,
            lambda:execute_tool(self.ex,decision_id=ident,region={'region_id':r['intent']['region_id'],
                'normalized_bounds':r['bounds']},tool={'method':method,'m1_budget':budget,'seed_id':seed_id},
                seed=self.entry['seed']+len(self.actions),config=config,meter=meter))
        for row in self.ex.rows[before:]:self.log(row)
        self.inverse_meter_calls+=meter.counts['analytic_calls']
        action={'phase':self.phase,'window':self.current_region,'decision':{'decision_id':ident,
            'search_method':'SLSQP' if method=='SLSQP' else method,'m1_budget':budget,'normalized_bounds':r['bounds']},'observation':obs}
        self.actions.append(action);append(self.root/'actions.jsonl',action)
        return obs
    def in_region_best(self,r):
        return [row for row in self.best(self.ex) if contains_parameters(self.ex.problem,r['bounds'],row['parameters'])]
    def build_intent(self,intent,folder):
        raw,local=intent_problem(self.raw,intent,self.physics['scale_anchors_SI'])
        req={'schema_version':'pll-physics-region-request-1.0','request_id':intent['region_id'],
            'problem_sha256':local['problem_sha256'],'model_fingerprint':model_identity()['model_sha256'],
            'strategy':intent['strategy'],'target_bw_fraction':intent['target_bw_fraction'],
            'physics_focus':['LF_SHAPE','GAIN_SPLIT','TUNING'],'tuning_preference':intent['tuning_preference'],
            'seed_count':3,'region_width_policy':'BALANCED','budget':{'construction_attempts':64,'m1_calls':3},
            'evidence_ids':intent['evidence_ids']}
        validate_request(req,local,model_identity()['model_sha256'],set(self.physics['allowed_evidence_ids']),attempts_left=64,m1_left=3)
        write_new(folder/'intent_domain.json',raw);write_new(folder/'builder_request.json',req)
        prop=self.timed('physics',intent['region_id'],lambda:build_physics_region(local,req,
            model_fingerprint=model_identity()['model_sha256'],random_seed=self.entry['seed']+len(self.constructions),
            history=[c['parameters'] for c in self.candidates if c['formal_M1_called']],
            excluded={c['parameter_sha256'] for c in self.candidates if c['formal_M1_called']}))
        self.constructions.append(prop);write_new(folder/'proposal_before_M1.json',prop)
        local_boxes=[s['normalized_bounds'] for s in prop['seeds']]
        # Convert Builder's actual local boxes into the common frozen coordinates.
        bounds={k:[coordinate(self.guard[k],physical_coordinate(local['parameters'][k],
                min(b[k][0] for b in local_boxes) if endpoint==0 else max(b[k][1] for b in local_boxes)))
                for endpoint in (0,1)] for k in FREE_IDS} if local_boxes else {
                    k:[coordinate(self.guard[k],local['parameters'][k]['min']),coordinate(self.guard[k],local['parameters'][k]['max'])] for k in FREE_IDS}
        # Endpoints derive from in-domain boxes; preserve the exact hard endpoints.
        roundoff=[]
        for k in FREE_IDS:
            for j in (0,1):
                if bounds[k][j]!=j and abs(bounds[k][j]-j)<1e-14:
                    roundoff.append({'axis':k,'endpoint':j,'before':bounds[k][j],'after':float(j),
                        'basis':'derived coordinate endpoint floating-point roundoff; LLM physical intent unchanged'})
                    bounds[k][j]=float(j)
        # Directed rounding encloses the exact seed defining a local box after
        # its log coordinates are transformed into the common guard coordinates.
        for k in FREE_IDS:
            values=[s['parameters']['values'][k]['value'] for s in prop['seeds']]
            if not values:continue
            for j,target in ((0,min(values)),(1,max(values))):
                before=bounds[k][j];endpoint=physical_coordinate(self.guard[k],before)
                if not (endpoint>target if j==0 else endpoint<target):continue
                require(math.isclose(endpoint,target,rel_tol=1e-13,abs_tol=0),
                    'constructed box excludes seed beyond floating roundoff')
                for _ in range(32):
                    bounds[k][j]=math.nextafter(bounds[k][j],-math.inf if j==0 else math.inf)
                    require(0<=bounds[k][j]<=1,'directed rounding exceeds hard guard')
                    endpoint=physical_coordinate(self.guard[k],bounds[k][j])
                    if (endpoint<=target if j==0 else endpoint>=target):break
                else:raise ValueError('cannot enclose constructed seed within roundoff limit')
                roundoff.append({'axis':k,'endpoint':j,'before':before,'after':bounds[k][j],
                    'seed_value_SI':target,'basis':'directed rounding of derived coordinate; exact Builder seed enclosed'})
        r={'intent':deepcopy(intent),'bounds':bounds,'proposal':prop,'folder':folder,'index':len(self.regions)+1}
        self.regions[intent['region_id']]=r
        plan={'window':r['index'],'region_id':intent['region_id'],'parameters':local['parameters'],
            'actual_normalized_bounds':bounds,'builder_seed_hashes':[s['parameter_sha256'] for s in prop['seeds']],
            'derived_coordinate_roundoff':roundoff,
            'intent_compilation':{'original_physics_intent':deepcopy(intent),
                'compiler_owner':'Controller, not LLM','compiler_version':self.cfg.get('compiler_version','unknown'),
                'requested_C1_F':[self.physics['scale_anchors_SI']['C1']*10**v for v in intent['c1_scale_decades']],
                'executed_construction_C1_F':[local['parameters']['C1']['min'],local['parameters']['C1']['max']],
                'requested_ratio':intent['c2_c1_ratio'],
                'compiled_C1_log_width_fraction':(math.log(local['parameters']['C1']['max']/local['parameters']['C1']['min'])/
                    ((intent['c1_scale_decades'][1]-intent['c1_scale_decades'][0])*math.log(10)))},
            'seed_parameters_source':'PhysicsRegionBuilder, not LLM numeric output','whole_region_certified':False}
        self.plans.append(plan);write_new(folder/'actual_subspace.json',plan)
        return r

    def observe(self,r,before,derivative=None,inclusive_wall_s=None):
        rows=[c for c in self.candidates[before:] if c['formal_M1_called']]
        passed=[c for c in rows if c['judgment']['m1_feasibility']=='FEASIBLE']
        ranked=sorted((c for c in rows if c['judgment']['minimum_normalized_margin'] is not None),
            key=lambda c:-c['judgment']['minimum_normalized_margin'])
        best=ranked[0] if ranked else None
        margins=[] if best is None else [c for c in best['judgment']['constraints'] if c['enabled'] and c['normalized_margin'] is not None]
        overlap={}
        for key,other in self.regions.items():
            if key==r['intent']['region_id']:continue
            intersect=math.prod(max(0,min(r['bounds'][k][1],other['bounds'][k][1])-max(r['bounds'][k][0],other['bounds'][k][0])) for k in FREE_IDS)
            overlap[key]=intersect/min(volume(r['bounds']),volume(other['bounds']))
        distances=[self.distance(a['parameters'],b['parameters']) for i,a in enumerate(rows) for b in rows[i+1:]]
        obs={'evidence_id':'OBS:'+r['intent']['region_id']+':'+str(len(self.observations)),
            'region_id':r['intent']['region_id'],'region_index':r['index'],'actual_normalized_bounds':r['bounds'],
            'seed_count':len(r['proposal']['seeds']),'seed_hashes':[s['parameter_sha256'] for s in r['proposal']['seeds']],
            'construction_failures':r['proposal']['failure_reasons'],'inverse_attempts':r['proposal']['cost']['inverse_calls'],
            'construction_wall_s':r['proposal']['cost']['wall_time_s'],'formal_M1_calls':len(rows),
            'formal_feasible_count':len(passed),'best_candidate':best,'constraint_margins':margins,
            'tightest_constraint':min(margins,key=lambda c:c['normalized_margin']) if margins else None,
            'sensitivity':derivative,'sensitivity_scope':'actual finite M1 probes; null if unavailable',
            'M1_wall_s':sum(c['M1_wall_s'] or 0 for c in rows),'candidate_hashes':[c['parameter_sha256'] for c in rows],
            'parameter_distance_min_rms':min(distances,default=None),'parameter_distance_max_rms':max(distances,default=None),
            'overlap_fraction_of_smaller_box':overlap,'overlap_scope':'box geometry, not feasible coverage',
            'budget_remaining_search_M1':self.remaining(21),'whole_region_certified':False}
        obs['inclusive_wall_s']=inclusive_wall_s
        self.observations.append(obs);append(self.root/'RegionObservations.jsonl',obs)
        return obs

    def probe(self,r):
        self.current_region=r['index'];self.active_bounds=r['bounds'];self.phase='REGION_PROBE'
        before=len(self.candidates);start=time.perf_counter();calls=self.calls();sens=None
        for i,s in enumerate(r['proposal']['seeds']):
            if self.remaining(21)<=0:break
            self.point(self.ex,s['parameters'],r['intent']['region_id']+':SEED:'+str(i))
        b=min(3,self.remaining(21),r['intent']['m1_budget']-(self.calls()-calls))
        if b>0:self.tool(r,'SOBOL_IN_REGION',b)
        best=self.in_region_best(r)
        if best and 'LOCAL_SENSITIVITY' in r['intent']['search_tools'] and self.remaining(21)>=12 and r['intent']['m1_budget']-(self.calls()-calls)>=12:
            sens=self.tool(r,'LOCAL_SENSITIVITY',12,best[0]['evidence_id'])['sensitivity']
        obs=self.observe(r,before,sens,time.perf_counter()-start)
        write_new(r['folder']/'RegionObservation.json',obs)
        return obs

    def phase1(self):
        from pll_allocation.agent.computational_window import scale_context
        self.physics=self.timed('physics','SHARED_SCALE_PRIOR',lambda:scale_context(self.raw))
        self.physics['numerical_resource_guard']={k:{'min':a['min'],'max':a['max']} for k,a in self.guard.items()}
        self.physics['M2_applicability']={'status':'NOT_EVALUATED'}
        pm=next(s['min'] for s in self.raw['specs'] if s['metric']=='PM_deg')
        sine=math.sin(math.radians(pm))
        self.physics['necessary_ratio_min']=(1+sine)/(1-sine)-1
        self.physics['necessary_ratio_basis']='original ideal LF phase ceiling inequality; necessary, not sufficient or a reference witness'
        write_new(self.root/'shared_physics_prior.json',self.physics)
        state={'schema_version':'pll-multi-region-state-1.0','case_id':self.entry['run_id'],
            'user_domain':{'mode':'USER_UNBOUNDED','user_bounds':None},
            'specs':self.raw['specs'],'fixed_parameters':self.raw['fixed_parameters'],
            'physics':self.physics,'budget':{'initial_plan_M1':128,'first_pass_limit':128,'extra_after_first':128},
            'initial_contract':PROMPT,'controller_seed':self.entry['seed']}
        state['state_sha256']=fingerprint(state);write_new(self.root/'PlannerState.json',state)
        if self.entry['policy']=='P2':
            policy=LLMRegionPolicy(self.cfg['provider'],prompt=PROMPT)
            try:plan=self.timed('llm','INITIAL_MULTI_REGION',lambda:contract_decision(policy,state,self.root/'initial_decision',
                normalize=normalize_multi,validate=lambda raw,_:validate_multi_plan(raw,template=self.raw,physics=self.physics)))
            finally:
                self.llm.extend(policy.calls)
                self.initial_llm_attempts=len(self.llm)
        else:
            plan=self.timed('planner','RULE_MULTI_REGION',lambda:validate_multi_plan(deterministic_plan(self.raw,self.physics),template=self.raw,physics=self.physics))
        write_new(self.root/'MULTI_REGION_PLAN.json',plan)
        exfolder=self.root/'shared_executor';exfolder.mkdir()
        self.ex=self.timed('setup','EMPTY_CONTEXT',lambda:self.new_ex(resolve_problem(self.raw),exfolder,128))
        from ..agent.subregion_loop import execute_multi_region_plan
        execute_multi_region_plan(self,plan)
        if not self.first:self.stop_reason='NOT_FOUND_WITHIN_BUDGET_AND_FEEDBACK_LIMIT'
        return self.ex if self.first else None

    def feedback_state(self):
        available=self.remaining(21)
        state={'schema_version':'pll-multi-region-feedback-state-1.0','case_id':self.entry['run_id'],
            'specs':self.raw['specs'],'physics':self.physics,'initial_contract':PROMPT,
            'regions':[r['intent'] for r in self.regions.values()],
            'RegionObservations':self.observations,'prior_feedback_and_execution':self.feedback,
            'available_search_M1':available,'connectivity_reserve':21,'total_M1':self.calls(),
            'first_M1_pass_call':self.first['M1_call_index'] if self.first else None,
            'top8_count':len(self.selected),'first_in_top8':bool(self.first and any(c['id']==self.first['id'] for c in self.selected)),
            'allowed_evidence_ids':[*self.physics['allowed_evidence_ids'],*[o['evidence_id'] for o in self.observations]]}
        state['state_sha256']=fingerprint(state);return state

    def validate_feedback(self,raw,state):
        fields={'action','region_id','region','m1_budget','reason','evidence_ids'}
        if not isinstance(raw,dict) or set(raw)!=fields:raise ContractError('feedback fields required: '+str(sorted(fields)),repairable=True)
        require(raw['action'] in ('CONTINUE_REGION','REFINE_REGION','EXPLORE_ANOTHER','STOP'),'invalid region feedback action')
        require(isinstance(raw['reason'],str) and raw['reason'].strip(),'feedback reason required')
        require(isinstance(raw['evidence_ids'],list) and bool(raw['evidence_ids']) and
            all(e in state['allowed_evidence_ids'] for e in raw['evidence_ids']),'invalid feedback evidence ID')
        if raw['action']=='STOP':
            require(raw['m1_budget']==0 and raw['region_id'] is None and raw['region'] is None,'STOP has no execution parameters')
        else:
            require(type(raw['m1_budget']) is int and 24<=raw['m1_budget']<=state['available_search_M1'],'feedback exceeds useful/hard budget')
            if raw['action']=='CONTINUE_REGION':
                require(raw['region_id'] in self.regions and raw['region'] is None,'continue requires existing region')
            else:
                require(isinstance(raw['region'],dict) and raw['region_id']==raw['region'].get('region_id') and
                    raw['region_id'] not in self.regions,'new physical region ID required')
                validate_multi_plan({'schema_version':MULTI_SCHEMA,'action':'MULTI_REGION_PLAN','reason':raw['reason'],'regions':[raw['region']]},
                    template=self.raw,physics=self.physics,max_budget=raw['m1_budget'],min_regions=1,max_regions=1)
                candidate,_=intent_problem(self.raw,raw['region'],self.physics['scale_anchors_SI'])
                require(all(candidate['parameters']!=intent_problem(self.raw,r['intent'],self.physics['scale_anchors_SI'])[0]['parameters']
                    or raw['region']['target_bw_fraction']!=r['intent']['target_bw_fraction'] for r in self.regions.values()),
                    'refine/explore must change effective region')
        return deepcopy(raw)

    def rule_feedback(self,state):
        if len(self.selected)==8 or state['available_search_M1']<24:
            return {'action':'STOP','region_id':None,'region':None,'m1_budget':0,
                'reason':'Measured eight points complete or useful remaining search budget insufficient.',
                'evidence_ids':[self.observations[-1]['evidence_id']]}
        pool=[o for o in self.observations if o['region_id'] not in self.feedback_used and o['best_candidate']]
        if not pool:pool=[o for o in self.observations if o['best_candidate']]
        if not pool:
            return {'action':'STOP','region_id':None,'region':None,'m1_budget':0,'reason':'No legal measured starting point in the constructed boxes.',
                'evidence_ids':[self.observations[-1]['evidence_id']]}
        best=max(pool,key=lambda o:(o['formal_feasible_count'],o['best_candidate']['judgment']['minimum_normalized_margin']))
        return {'action':'CONTINUE_REGION','region_id':best['region_id'],'region':None,
            'm1_budget':min(48,state['available_search_M1']),'reason':'Continue the measured feasible-yield/margin leader; alternate after a completed action.',
            'evidence_ids':[best['evidence_id']]}

    def expand_region(self,r,cap):
        self.current_region=r['index'];self.active_bounds=r['bounds'];self.phase='PHASE2_SEARCH' if self.first else 'PHASE1_SEARCH'
        before=len(self.candidates);start_calls=self.calls();derivative=None
        def left():return min(self.remaining(21),max(0,cap-(self.calls()-start_calls)))
        best=self.in_region_best(r)
        if best and 'SLSQP' in r['intent']['search_tools'] and left()>=23 and len(self.selected)<8:
            self.tool(r,'SLSQP',min(32,left()),best[0]['evidence_id'])
        if len(self.selected)<8 and left()>0:
            # More coupled seeds use the SAME original Builder and original physical intent.
            raw,local=intent_problem(self.raw,r['intent'],self.physics['scale_anchors_SI'])
            req=deepcopy(r['proposal']['request']);req['request_id']=r['intent']['region_id']+':EXPAND'+str(len(self.constructions))
            req['seed_count']=min(8,left());req['budget']['m1_calls']=req['seed_count'];req['strategy']='DIVERSITY_EXPLORATION'
            validate_request(req,local,model_identity()['model_sha256'],set(self.physics['allowed_evidence_ids']),attempts_left=64,m1_left=left())
            prop=self.timed('physics',req['request_id'],lambda:build_physics_region(local,req,
                model_fingerprint=model_identity()['model_sha256'],random_seed=self.entry['seed']+len(self.constructions),
                history=[c['parameters'] for c in self.candidates if c['formal_M1_called']],
                excluded={c['parameter_sha256'] for c in self.candidates if c['formal_M1_called']}))
            self.constructions.append(prop);write_new(r['folder']/('expansion_proposal_'+str(len(self.constructions))+'.json'),prop)
            # The execution contract remains the actual constructed local box.
            for i,s in enumerate(prop['seeds']):
                if left()<=0 or len(self.selected)==8:break
                if contains_parameters(self.ex.problem,r['bounds'],s['parameters']):
                    self.point(self.ex,s['parameters'],req['request_id']+':'+str(i))
        if left()>0 and len(self.selected)<8:self.tool(r,'SOBOL_IN_REGION',left())
        return self.observe(r,before,derivative)

    def feedback_rounds(self):
        for i in range(len(self.feedback),self.cfg['max_feedback_decisions']):
            state=self.feedback_state();folder=self.root/f'feedback_{i+1:02d}';folder.mkdir()
            write_new(folder/'PlannerState.json',state)
            if self.entry['policy']=='P2':
                policy=LLMRegionPolicy(self.cfg['provider'],prompt=FEEDBACK_PROMPT)
                def normalize(raw,_):
                    if not isinstance(raw,dict) or set(raw)!={'action','region_id','region','m1_budget','reason','evidence_ids'}:
                        raise ContractError('feedback object fields mismatch',repairable=True)
                    return raw,{'raw':raw,'normalized':raw,'changes':[]}
                try:d=self.timed('llm','REGION_FEEDBACK_'+str(i+1),lambda:contract_decision(policy,state,folder/'decision',
                    normalize=normalize,validate=self.validate_feedback))
                finally:self.llm.extend(policy.calls)
            else:d=self.validate_feedback(self.rule_feedback(state),state)
            write_new(folder/'decision.json',d)
            record={'decision':d,'actual_tools_executed':False,'observation':None};self.feedback.append(record)
            if d['action']=='STOP':
                write_new(folder/'execution.json',record);break
            if d['action']=='CONTINUE_REGION':r=self.regions[d['region_id']]
            else:
                newfolder=folder/'new_region';newfolder.mkdir();r=self.build_intent(d['region'],newfolder)
                before=self.calls();record['new_region_probe_observation']=self.probe(r)
                d=deepcopy(d);d['m1_budget']=max(0,d['m1_budget']-(self.calls()-before))
            self.feedback_used.append(d['region_id'])
            record['observation']=self.expand_region(r,min(d['m1_budget'],self.remaining(21)))
            record['actual_tools_executed']=(record['observation']['formal_M1_calls']+
                record.get('new_region_probe_observation',{}).get('formal_M1_calls',0))>0
            write_new(folder/'execution.json',record)

    def connectivity_check(self):
        self.phase='CONNECTIVITY';self.active_bounds={k:[0.,1.] for k in FREE_IDS}
        if len(self.selected)<2:return
        center=self.selected[0];u=normalized_point(self.ex.problem,center['parameters'])
        for i,other in enumerate(self.selected[1:],1):
            samples=[];v=normalized_point(self.ex.problem,other['parameters'])
            for fraction in (.25,.5,.75):
                if self.remaining()<=0:break
                p=make_parameters(self.ex.problem,{k:physical_coordinate(self.ex.problem['parameters'][k],u[k]+fraction*(v[k]-u[k])) for k in FREE_IDS})
                self.point(self.ex,p,f'CONNECT:{i}:{fraction}','LOCAL_CONNECTIVITY');c=self.candidates[-1]
                samples.append({'fraction':fraction,'candidate_id':c['id'],'formal_M1_called':c['formal_M1_called'],
                    'M1_status':c['M1_status'],'feasibility':c['judgment']['m1_feasibility'],
                    'minimum_normalized_margin':c['judgment']['minimum_normalized_margin']})
            self.connectivity.append({'from':center['id'],'to':other['id'],'samples':samples,
                'sampled_connection_pass':len(samples)==3 and all(c['M1_status']=='OK' and c['feasibility']=='FEASIBLE' for c in samples),
                'continuous_segment_certified':False})

    def phase2(self,ex):
        self.p2start=time.perf_counter();self.p2calls=self.first['M1_call_index']
        self.feedback_rounds();self.connectivity_check()
        f=self.root/'expansion';f.mkdir()
        write_new(f/'top8_points.json',{'points':self.selected,'diversity_rms_threshold':.02,'whole_region_certified':False})
        write_new(f/'local_connectivity.json',self.connectivity)
        included=any(c['id']==self.first['id'] for c in self.selected)
        self.stop_reason='FIRST_PASS_MARGIN_INSUFFICIENT' if not included else 'TOP8_COMPLETED' if len(self.selected)==8 else 'SEARCH_BUDGET_BELOW_RESERVE_OR_MIN_ACTION' if self.remaining(21)<24 else 'PLANNER_STOP_OR_MAX_FEEDBACK'

    def run(self):
        result=super().run()
        result.update(experiment='MULTI_REGION_PLAN',initial_region_count=len(read(self.root/'MULTI_REGION_PLAN.json')['regions']) if (self.root/'MULTI_REGION_PLAN.json').exists() else 0,
            actual_regions=len(self.regions),actual_searched_regions=len({o['region_id'] for o in self.observations if o['formal_M1_calls']>0}),
            RegionObservations=self.observations,region_feedback=self.feedback,
            LLM_first_decision_latency_s=sum(c.get('elapsed_s',0) for c in self.llm[:self.initial_llm_attempts]) if hasattr(self,'initial_llm_attempts') else None,
            cross_region_top8_count=len({c['window'] for c in self.selected}),
            remaining_hard_M1=self.remaining(),remaining_useful_search_M1=self.remaining(21),
            physics_inverse_attempts=result['physics_inverse_attempts']+self.inverse_meter_calls,
            initial_decision_legal=(self.root/'MULTI_REGION_PLAN.json').exists())
        if self.first:result['incremental_expansion_wall_s']=result['timing']['wall']-self.first['elapsed_s']
        if result['failure']:
            kind=result['failure']['type']
            result['execution_failure_class']='PROVIDER_FAILURE' if kind=='ProviderError' else 'INVALID_PLANNER_DECISION' if kind in ('ValueError','ContractError','InvalidResponse','InvalidNumericResponse') else 'CONTROLLER_EXECUTION_FAILURE'
        # Keep base result as a provenance artifact; never overwrite it.
        write_new(self.root/'multi_region_result.json',result)
        return result


def run(out):
    root=Path(out).resolve();cfg=check_freeze(root);folder=root/'runs';folder.mkdir(exist_ok=False)
    rows=[];start=time.perf_counter()
    for entry in cfg['run_order']:
        check_freeze(root);r=MultiTrial(folder/entry['run_id'],entry,cfg).run();rows.append(r)
        compact={k:r[k] for k in ('run_id','status','stop_reason','top8_count','total_M1_calls','time_to_first_pass_s','time_to_eight_s')}
        append(root/'run_completion.jsonl',compact);print(json.dumps(compact),flush=True)
    write_new(root/'execution_summary.json',{'run_count':len(rows),'main_M1_calls':sum(r['total_M1_calls'] for r in rows),
        'main_LLM_API_calls':sum(r['LLM_API_calls'] for r in rows),'wall_s':time.perf_counter()-start,
        'execution_failures':sum(r['status']=='EXECUTION_FAILED' for r in rows),'M2_calls':0,'completed_utc':utc()})
    return response('MULTI_REGION_COMPLETE',read(root/'execution_summary.json'))


def dispatch(mode,out):return {'freeze':freeze,'run':run}[mode](out)
