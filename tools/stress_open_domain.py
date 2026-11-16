"""USER_UNBOUNDED input adapter, not an allocator or a model.

Finite windows are computational choices, not inferred user/device constraints.
Original inverse relations expose an explicit scale gauge to the real LLM.
"""
from copy import deepcopy
import math
from pll_allocation.allocation.core import Meter
from pll_allocation.allocation.physics import inverse_at_shape, RELATIONS
from pll_allocation.agent.region_policy import LLMRegionPolicy
from pll_allocation.agent.window_contract import normalize_window, check_physical_window, contract_decision
from pll_allocation.exploration.contracts import axes, resolve_problem, require, number
from pll_allocation.exploration.engine import model_identity
from pll_allocation.physics_mapping.model import fingerprint, PARAMETERS


class WindowDecisionError(ValueError):
    """A real window proposal failed the input adaptation contract."""


def observation_evidence(observation):
    """Register actual controller-produced verification records, not LLM citations."""
    if not observation:return []
    records=[]
    for i,record in enumerate((observation.get('stage9_result') or {}).get('verified_history',[])):
        evidence=record.get('evidence_id')
        if isinstance(evidence,str) and evidence:
            records.append({'evidence_id':evidence,'source':f'actual_observation.stage9_result.verified_history[{i}]',
                'candidate_sha256':record.get('candidate_sha256'),'status':record.get('M2_status')})
    return records

PROMPT='''Select a finite COMPUTATIONAL EXPLORATION WINDOW for USER_UNBOUNDED ideal CPPLL input.
The human supplied SystemSpec and NO min/max for any of the six variables. No old successful point is given.
This is input adaptation: do not allocate a nominal candidate or invent M1/M2 results.
Use supplied physics, explicit scale gauge, model/numerical restrictions and actual observations.
Absolute capacitor/current/impedance scale is not uniquely identifiable from BW/PM. The gauge is a heuristic,
not a physical/device capability bound. Choose all six numerical intervals yourself.
Return exactly one JSON with schema_version="pll-computational-window-decision-2.0",
action="OPEN_WINDOW" for round1 or "EXPAND_OR_SWITCH"/"STOP" after an observation,
reason(brief physical hypothesis and protected requirements), evidence_ids(nonempty supplied IDs),
parameters(null for STOP, otherwise Icp,Rz,C1,C2,f0,Kvco each {min,max,unit}).
Equivalent SI prefixes allowed; omitted unit means SI. Controller fixes coordinates.
Intervals finite positive min<max. Respect the explicit numerical
resource guard, which is NOT a user/physical bound. f0<target allows positive tuning; Kvco must also permit Vreq.
Round2 must include space outside the first window or STOP with an honest reason. Never claim open space
infeasible. Local sensitivities never prove global signs or whole-window feasibility.'''


def scale_context(template, *, z_gauge=1000.):
    """One original inverse call, no formal M1. The absolute gauge is arbitrary."""
    p=deepcopy(template);fixed=p['fixed_parameters'];fref=fixed['f_ref']['value']
    target=fref*fixed['N']['value'];rails=fixed['Vctrl_max']['value']-fixed['Vctrl_min']['value']
    require(isinstance(z_gauge,(int,float)) and not isinstance(z_gauge,bool) and math.isfinite(z_gauge) and z_gauge>0,
        'positive finite impedance gauge required')
    specs={s['metric']:s for s in p['specs']};c1=1/(2*math.pi*fref*z_gauge)
    pm=min(88.,max(10.,specs['PM_deg']['min']+4.));s=math.sin(math.radians(pm))
    q=(1+s)/(1-s);c2=c1*(q-1);kv=target/rails
    pseudo=axes(resolve_problem(p))
    for k in ('Icp','Kvco'):pseudo['variables'][k]['range']={'min':1e-20,'max':1e20}
    pseudo['variables']['f0']['range']={'min':target*.01,'max':target*.99}
    bw=(specs['BW_Hz']['min']+specs['BW_Hz']['max'])/2
    seed=inverse_at_shape(pseudo,c1,c2,bw,math.sqrt(q),Meter(cheap_limit=1,m1_limit=0))
    require(seed is not None,'original inverse could not derive computational gauge')
    product=seed['Icp']*seed['Kvco']
    anchors={'C1':c1,'C2':c2,'Rz':seed['Rz'],'Kvco':kv,'Icp':product/kv,'f0':target*.5}
    guard={k:({'min':v*1e-3,'max':v*1e3} if k!='f0' else
        {'min':target*1e-4,'max':target*(1-1e-6)}) for k,v in anchors.items()}
    return {'scale_anchors_SI':anchors,'numerical_resource_guard':guard,'required_gain_product_at_gauge':product,
        'source':'original inverse_at_shape, one algebraic call, NOT formal M1/measured evidence',
        'impedance_gauge_Ohm':z_gauge,'gauge_choice':'arbitrary numerical scale, NOT circuit capability',
        'absolute_scale_identifiable':False,'relations':RELATIONS,
        'hard_constraints':['positive canonical SI inputs; fixed ideal topology','interior Vreq=(N*fref-f0)/Kvco'],
        'M2_applicability':{'N':8,'fref_Hz':10e6,'rails_V':[0,1.2],
            'resolution':'dt*(C1+C2)/(Rz*C1*C2)<=.05; dt*max(fref,fmax/N)<=.02; dt=.4ns',
            'unsupported_point':'UNKNOWN; never silently change native timestep/protocol'},
        'M1_model':model_identity(),'analytic_calls':1,'M1_calls':0,'M2_calls':0,
        'no_global_bound_proven':True,'allowed_evidence_ids':['OPEN:SCALE_GAUGE','REL:frequency','REL:shape',
            'REL:phase_ceiling','REL:inverse_gain','OPEN:OBSERVATION']}


def validate_window(raw,state):
    normalized,_=normalize_window(raw,state)
    return check_physical_window(_validate_canonical_window(normalized,state))


def _validate_canonical_window(raw,state):
    fields={'schema_version','state_sha256','action','reason','evidence_ids','parameters'}
    require(isinstance(raw,dict) and set(raw)==fields and raw['schema_version']=='pll-computational-window-decision-1.0',
        'exact computational window decision required')
    require(raw['state_sha256']==state['state_sha256'],'window state binding mismatch')
    require(isinstance(raw['reason'],str) and 0<len(raw['reason'])<=4000,'window reason required')
    require(isinstance(raw['evidence_ids'],list) and bool(raw['evidence_ids']) and
        all(e in state['physics']['allowed_evidence_ids'] for e in raw['evidence_ids']),'invalid window evidence')
    first=state['round']==1
    require(raw['action'] in (('OPEN_WINDOW',) if first else ('EXPAND_OR_SWITCH','STOP')),'invalid window action')
    if raw['action']=='STOP':
        require(raw['parameters'] is None,'STOP has no window');return None
    require(isinstance(raw['parameters'],dict) and set(raw['parameters'])==set(state['template']['parameters']),
        'six complete finite window axes required')
    params={}
    for k,a in raw['parameters'].items():
        require(isinstance(a,dict) and set(a)=={'min','max','unit','scale'},k+': exact axis fields required')
        require(a['unit']==PARAMETERS[k][0] and a['scale']==('linear' if k=='f0' else 'log'),k+': canonical unit/scale required')
        lo,hi=number(a['min'],k),number(a['max'],k);g=state['physics']['numerical_resource_guard'][k]
        require(0<lo<hi and g['min']<=lo and hi<=g['max'],k+': numerical resource guard exceeded')
        params[k]=deepcopy(a)|{'default':(lo+hi)/2 if k=='f0' else math.sqrt(lo*hi)}
    if not first:
        old=state['previous_window']
        require(any(a['min']<old[k]['min'] or a['max']>old[k]['max'] for k,a in params.items()),
            'second window must explore outside previous window')
    p=deepcopy(state['template']);p['parameters']=params
    p['problem_id']=state['case_id']+':COMPUTATIONAL_WINDOW_'+str(state['round']);resolve_problem(p)
    return p


def choose_window(template,case_id,round_number,*,physics,previous_window,observation,provider_config,out):
    """Real policy, raw response/validation logs, no hidden default fallback."""
    from pathlib import Path
    from pll_allocation.allocation.core import write_new
    state={'schema_version':'pll-open-input-state-1.0','case_id':case_id,'round':round_number,
        'user_domain':{'mode':'USER_UNBOUNDED','six_axis_user_min_max':None},
        'template':deepcopy(template),'physics':deepcopy(physics),'previous_window':previous_window,
        'actual_observation':observation,'search_claim':'finite windows only; no open-domain infeasibility proof'}
    state['observation_evidence_catalog']=observation_evidence(observation)
    state['physics']['allowed_evidence_ids']=list(dict.fromkeys([
        *state['physics']['allowed_evidence_ids'],*[r['evidence_id'] for r in state['observation_evidence_catalog']]]))
    state['template']['parameters']={}
    state['state_sha256']=fingerprint(state)
    root=Path(out);root.mkdir(parents=True,exist_ok=False);write_new(root/'planner_state.json',state)
    policy=LLMRegionPolicy(provider_config,prompt=PROMPT)
    try:
        validation_state=deepcopy(state);validation_state['template']=deepcopy(template)
        def validate_current(raw,current):
            bound=deepcopy(current);bound['template']=deepcopy(template)
            return validate_window(raw,bound)
        try:p=contract_decision(policy,state,root,existing_directory=True,raw_alias='raw_window_decision.json',
            normalize=normalize_window,validate=validate_current)
        except ValueError as error:raise WindowDecisionError(str(error)) from error
        write_new(root/'controller_validation.json',{'accepted':True,'window_source':'REAL_LLM',
            'is_user_constraint':False,'resolved_problem':p})
        return p
    except Exception as error:
        write_new(root/'controller_validation.json',{'accepted':False,'error_type':type(error).__name__,'reason':str(error),
            'fallback_window_used':False})
        raise
