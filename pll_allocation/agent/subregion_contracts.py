"""Untrusted exploration geometry contracts; no parameter ranking or physics model."""
from copy import deepcopy
import itertools
import math

from ..block_space.contracts import FREE_IDS
from ..exploration.contracts import number, require, screen_problem
from ..physics_mapping.model import fingerprint
from ..region_explorer.assessment import physical_coordinate, contains_parameters

SCHEMA = 'pll-exploration-decision-1.0'
CONFIG_SCHEMA = 'pll-subregion-pilot-1.0'
TOOLS = {'SOBOL_IN_REGION', 'PHYSICS_GUIDED_SEEDS', 'ANALYTICAL_INVERSE', 'LOCAL_SENSITIVITY', 'SLSQP'}


def validate_config(raw):
    fields = {'schema_version','strategy','seed','total_m1_budget','initial_m1_budget','initial_sobol_samples',
        'global_m1_budget','global_sobol_samples','max_decisions','round_m1_budget','validation_retries',
        'max_llm_calls','max_tool_proposals','analytic_call_limit','region_radius'}
    require(isinstance(raw,dict) and set(raw)==fields and raw['schema_version']==CONFIG_SCHEMA,'complete pilot config required')
    c=deepcopy(raw)
    require(c['strategy'] in ('DETERMINISTIC_PHYSICS_STAGE7','LLM_GUIDED_STAGE7_5'),'unsupported exploration strategy')
    for k in fields-{'schema_version','strategy','region_radius'}:
        require(type(c[k]) is int and c[k]>=0,k+': nonnegative integer required')
    require(1<=c['max_decisions']<=2 and c['max_decisions']<=c['max_llm_calls']<=6,'bounded rounds/provider calls required')
    require(c['validation_retries']<=2 and c['seed']+100<2**32,'bounded retries/seed required')
    require(c['initial_m1_budget']>0 and c['global_m1_budget']>0 and c['round_m1_budget']>0,'positive phase caps required')
    require(c['initial_m1_budget']+c['global_m1_budget']+c['max_decisions']*c['round_m1_budget']<=c['total_m1_budget'],
            'phase caps exceed session M1 hard limit')
    require(1<=c['initial_sobol_samples']<=4096 and 1<=c['global_sobol_samples']<=4096 and
            12<=c['max_tool_proposals']<=4096 and c['analytic_call_limit']>0,'bounded actual proposal settings required')
    require(0<number(c['region_radius'],'region radius')<=.5,'legal candidate summary radius required')
    return c


def volume(bounds):
    return math.prod(hi-lo for lo,hi in bounds.values())


def union_volume(boxes):
    # Bounded pilot: at most twelve boxes. This measures planned envelopes,
    # never a sampled/certified continuous volume.
    total=0.
    for size in range(1,len(boxes)+1):
        for group in itertools.combinations(boxes,size):
            intersection={k:[max(b[k][0] for b in group),min(b[k][1] for b in group)] for k in FREE_IDS}
            v=math.prod(max(0.,hi-lo) for lo,hi in intersection.values())
            total+=v*(1 if size%2 else -1)
    return min(1.,max(0.,total))


def region_problem(problem,bounds):
    p=deepcopy(problem)
    for k,(lo,hi) in bounds.items():
        a=p['parameters'][k]
        a.update(min=physical_coordinate(problem['parameters'][k],lo),
                 max=physical_coordinate(problem['parameters'][k],hi))
        a['default']=min(a['max'],max(a['min'],a['default']))
    return p


def validate_exploration(raw, *, problem, allowed_evidence, evidence, max_budget, global_reserve,
                         prior_id, seen_ids=(), seen_signatures=()):
    fields={'schema_version','decision_id','prior_context_sha256','sampling_seed','regions','global_coverage_budget','reason','evidence_ids'}
    require(isinstance(raw,dict) and set(raw)==fields and raw['schema_version']==SCHEMA,'complete ExplorationDecision required')
    d=deepcopy(raw)
    require(isinstance(d['decision_id'],str) and 0<len(d['decision_id'])<=100 and d['decision_id'] not in seen_ids,'invalid/duplicate decision ID')
    require(d['prior_context_sha256']==prior_id,'current PhysicsPrior binding mismatch')
    require(type(d['sampling_seed']) is int and 0<=d['sampling_seed']<2**32-24,'bounded explicit sampling seed required')
    require(type(d['global_coverage_budget']) is int and d['global_coverage_budget']==global_reserve,'must preserve predeclared global coverage reserve')
    def refs(ids):
        require(isinstance(ids,list) and bool(ids) and len(set(ids))==len(ids) and
                all(isinstance(i,str) and i in allowed_evidence for i in ids),'unknown/empty/duplicate evidence IDs')
    refs(d['evidence_ids'])
    require(isinstance(d['reason'],str) and bool(d['reason'].strip()),'reason required')
    require(isinstance(d['regions'],list) and 1<=len(d['regions'])<=6,'one to six actual subregions required')
    diagnostics=[];cost=0;ids=set();boxes=[]
    for r in d['regions']:
        require(isinstance(r,dict) and set(r)=={'region_id','normalized_bounds','tools','focus_constraints',
                'evidence_ids','hypothesis','success_condition','failure_modes'},'complete region plan required')
        require(isinstance(r['region_id'],str) and r['region_id'] and r['region_id'] not in ids,'duplicate/invalid region ID')
        ids.add(r['region_id']);refs(r['evidence_ids'])
        for field in ('hypothesis','success_condition'):
            require(isinstance(r[field],str) and bool(r[field].strip()),field+' required')
        require(isinstance(r['failure_modes'],list) and bool(r['failure_modes']) and
                all(isinstance(x,str) and x for x in r['failure_modes']),'explicit potential failures required')
        metrics={s['metric'] for s in problem['specs'] if s['enabled'] and s['support_status']=='M1_SUPPORTED'}
        require(isinstance(r['focus_constraints'],list) and bool(r['focus_constraints']) and
                all(x in metrics for x in r['focus_constraints']),'focus must use currently supported M1 metrics')
        b=r['normalized_bounds']
        require(isinstance(b,dict) and set(b)==set(FREE_IDS),'complete six-axis bounds required')
        for k,pair in b.items():
            require(isinstance(pair,list) and len(pair)==2,k+': two bounds required')
            lo,hi=[number(x,k) for x in pair]
            require(0<=lo<hi<=1,k+': bounds outside original global domain')
        cert=screen_problem(region_problem(problem,b))
        require(not cert['certificates'],'region violates a proven necessary condition: '+str(cert['certificates']))
        v=volume(b)
        if v<1e-9:diagnostics.append({'region_id':r['region_id'],'code':'TINY_REGION','normalized_volume':v})
        require(isinstance(r['tools'],list) and 1<=len(r['tools'])<=4,'actual supported tools required')
        names=set()
        for t in r['tools']:
            require(isinstance(t,dict) and set(t)=={'method','m1_budget','seed_id'},'tool method/budget/seed required')
            require(t['method'] in TOOLS and t['method'] not in names,'unsupported or repeated tool')
            names.add(t['method'])
            require(type(t['m1_budget']) is int and t['m1_budget']>0,'positive tool M1 cap required')
            cost+=t['m1_budget']
            if t['method'] in ('LOCAL_SENSITIVITY','SLSQP'):
                s=evidence.get(t['seed_id'])
                require(s is not None and s.get('M1_status')=='OK' and contains_parameters(problem,b,s['parameters']),
                        'local optimizer/sensitivity requires a formal seed inside requested region')
            else:require(t['seed_id'] is None,'non-sensitivity tools do not require/select final seed values')
        for previous in boxes:
            intersection=math.prod(max(0.,min(b[k][1],previous[k][1])-max(b[k][0],previous[k][0])) for k in FREE_IDS)
            if intersection/min(v,volume(previous))>.8:
                diagnostics.append({'region_id':r['region_id'],'code':'LARGE_OVERLAP','smaller_box_overlap_fraction':intersection/min(v,volume(previous))})
            require(b!=previous,'duplicate region geometry in one decision')
        boxes.append(b)
    require(cost<=max_budget,'decision exceeds round/session available budget')
    signature=fingerprint({'sampling_seed':d['sampling_seed'],'regions':[{'bounds':r['normalized_bounds'],'tools':r['tools']} for r in d['regions']]})
    require(signature not in seen_signatures,'duplicate effective exploration decision')
    return d,{'accepted':True,'allocated_m1_budget':cost,'diagnostics':diagnostics,'signature':signature,
        'planned_box_union_fraction':union_volume(boxes),'whole_region_M1_certified':False}


MULTI_SCHEMA='pll-multi-region-plan-1.0'
INTENT_FIELDS={'region_id','hypothesis','evidence_ids','priority','target_bw_fraction','reserved_bw_margin_fraction',
    'c1_scale_decades','c2_c1_ratio','kvco_scale_decades','f0_target_fraction','strategy','tuning_preference',
    'search_tools','m1_budget','expected_improvements','failure_modes'}


def intent_problem(problem, intent, anchors):
    """Compile chosen physics inequalities into a conservative construction box.

    The chosen finite slice stays inside the physical envelopes and obeys the
    ratio at every corner. A legitimate coupled intent need not admit a single
    all-corner rectangle over its ENTIRE C1 envelope. Impossible intersections
    are rejected. This calls existing domain/necessary-condition contracts.
    """
    from ..exploration.contracts import resolve_problem
    raw={k:deepcopy(v) for k,v in problem.items() if k not in ('problem_sha256','screening')}
    # Resolved problem has annotations; caller supplies original ResearchProblemV2.
    a=raw['parameters'];fixed=raw['fixed_parameters'];target=fixed['N']['value']*fixed['f_ref']['value']
    c1lo,c1hi=[anchors['C1']*10**v for v in intent['c1_scale_decades']]
    require(a['C1']['min']<=c1lo<c1hi<=a['C1']['max'],'C1: intent outside hard guard')
    rlo,rhi=intent['c2_c1_ratio']
    require(0<rlo<rhi,'positive ordered LF ratio required')
    # A ratio interval describes coupled points, not every corner of the full
    # C1 envelope. Pick a finite computational slice INSIDE that intent. This
    # is Controller compilation, not a repair to the planner's physical bounds.
    feasible_lo=max(c1lo,a['C2']['min']/rhi)
    feasible_hi=min(c1hi,a['C2']['max']/rlo)
    require(feasible_lo<feasible_hi,'no C1/C2 ratio intersection within hard guard')
    center=(math.log(feasible_lo)+math.log(feasible_hi))/2
    half=min((math.log(feasible_hi)-math.log(feasible_lo))/2,
             math.log(rhi/rlo)/4)
    c1lo=max(feasible_lo,math.exp(center-half))
    c1hi=min(feasible_hi,math.exp(center+half))
    c2lo=max(a['C2']['min'],rlo*c1hi)
    c2hi=min(a['C2']['max'],rhi*c1lo)
    choices={'C1':[c1lo,c1hi],'C2':[c2lo,c2hi],
        'Kvco':[anchors['Kvco']*10**v for v in intent['kvco_scale_decades']],
        'f0':[target*v for v in intent['f0_target_fraction']]}
    for k,(lo,hi) in choices.items():
        require(0<lo<hi and a[k]['min']<=lo<hi<=a[k]['max'],k+': intent outside hard guard or contradictory coupling')
        a[k].update(min=lo,max=hi,default=(lo+hi)/2 if k=='f0' else math.sqrt(lo*hi))
    resolved=resolve_problem(raw)
    require(not screen_problem(resolved)['certificates'],'intent violates proven physical necessary condition')
    return raw,resolved


def normalize_multi(raw,state):
    from .window_contract import ContractError
    fields={'schema_version','action','reason','regions'}
    if not isinstance(raw,dict) or set(raw)!=fields or raw.get('schema_version')!=MULTI_SCHEMA:
        raise ContractError('MULTI_REGION_PLAN structure/schema required',repairable=True)
    if not isinstance(raw['regions'],list):raise ContractError('regions list required',repairable=True)
    for r in raw['regions']:
        if not isinstance(r,dict) or set(r)!=INTENT_FIELDS:
            raise ContractError('region fields required: '+str(sorted(INTENT_FIELDS)),repairable=True)
    return deepcopy(raw),{'raw':deepcopy(raw),'normalized':deepcopy(raw),'changes':[],
        'fixed_metadata_owner':'Controller','units':'SI; scale fields not requested'}


def validate_multi_plan(raw, *, template, physics, max_budget=128, min_regions=2, max_regions=3):
    from ..exploration.physics_region_builder import STRATEGIES
    normalize_multi(raw,{})
    require(raw['action']=='MULTI_REGION_PLAN','MULTI_REGION_PLAN action required')
    require(isinstance(raw['reason'],str) and bool(raw['reason'].strip()),'plan reason required')
    regions=raw['regions'];require(min_regions<=len(regions)<=max_regions,'two to three physical hypotheses required')
    seen=set();priorities=set();signatures=set();budget=0
    allowed=set(physics['allowed_evidence_ids'])
    for r in regions:
        require(isinstance(r['region_id'],str) and 0<len(r['region_id'])<=40 and
            all(c.isalnum() or c in '_-' for c in r['region_id']) and r['region_id'] not in seen,'unique safe region ID required')
        seen.add(r['region_id'])
        require(type(r['priority']) is int and 1<=r['priority']<=3 and r['priority'] not in priorities,'unique priority 1..3 required')
        priorities.add(r['priority'])
        require(isinstance(r['hypothesis'],str) and bool(r['hypothesis'].strip()),'physical hypothesis required')
        require(isinstance(r['evidence_ids'],list) and bool(r['evidence_ids']) and
            all(isinstance(e,str) and e in allowed for e in r['evidence_ids']),'unknown physical Evidence ID')
        for key in ('c1_scale_decades','kvco_scale_decades','c2_c1_ratio','f0_target_fraction','target_bw_fraction'):
            pair=r[key];require(isinstance(pair,list) and len(pair)==2,key+': two finite bounds required')
            lo,hi=[number(v,key) for v in pair];require(lo<hi,key+': ordered interval required')
        margin=number(r['reserved_bw_margin_fraction'],'reserved BW margin')
        require(.01<=margin<.5 and margin<=r['target_bw_fraction'][0]<r['target_bw_fraction'][1]<=1-margin,
            'BW targets must preserve the explicitly chosen positive interval margin')
        require(0<r['f0_target_fraction'][0]<r['f0_target_fraction'][1]<1,'positive below-target f0 required')
        require(0<r['c2_c1_ratio'][0]<r['c2_c1_ratio'][1],'positive LF ratio required')
        require(r['strategy'] in STRATEGIES,'unsupported original builder strategy')
        require(r['tuning_preference'] in ('INTERIOR','LOW_VOLTAGE','HIGH_VOLTAGE','DIVERSE'),'unsupported tuning preference')
        require(isinstance(r['search_tools'],list) and len(set(r['search_tools']))==len(r['search_tools']) and
            {'PHYSICS_GUIDED_SEEDS','SOBOL_IN_REGION'}<=set(r['search_tools'])<=TOOLS,'supported shared search tool pool required')
        require(type(r['m1_budget']) is int and 24<=r['m1_budget']<=64,'region budget 24..64 required')
        budget+=r['m1_budget']
        for key in ('expected_improvements','failure_modes'):
            require(isinstance(r[key],list) and bool(r[key]) and all(isinstance(x,str) and x for x in r[key]),key+' required')
        _,local=intent_problem(template,r,physics['scale_anchors_SI'])
        signature=fingerprint({'parameters':local['parameters'],'target':r['target_bw_fraction'],
            'strategy':r['strategy'],'tuning':r['tuning_preference']})
        require(signature not in signatures,'duplicate effective physical region')
        signatures.add(signature)
    require(budget<=max_budget,'multi-region allocation exceeds budget')
    return deepcopy(raw)
