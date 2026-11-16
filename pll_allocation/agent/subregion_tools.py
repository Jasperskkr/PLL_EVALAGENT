"""Proposal adapters to original M1 exploration algebra/Sensitivity and RegionExplorer.

No evaluator or alternate feasibility logic is implemented here. Every actual
M1 candidate passes through RegionExplorer's one cache and hard budget.
"""
from copy import deepcopy
import math
from scipy.stats import qmc

from ..allocation.core import Meter
from ..allocation.physics import inverse_at_shape
from ..block_space.contracts import FREE_IDS
from ..exploration.contracts import active_m1_specs,axes,make_parameters
from ..exploration.regions import sensitivity
from ..physics_mapping.model import fingerprint
from ..region_explorer.assessment import physical_coordinate
from ..region_explorer.contracts import OBJECTIVE,SCHEMA
from .subregion_contracts import region_problem


def envelope(explorer, *, decision_id,region_id,bounds,budget,seed,proposals):
    return {'schema_version':SCHEMA,'decision_id':decision_id,'context_sha256':explorer.context['context_sha256'],
        'action':'PROBE','region':{'region_id':region_id,'parent_region_id':None},
        'normalized_bounds':deepcopy(bounds),'active_variables':list(FREE_IDS),'seed_ids':[],
        'm1_budget':budget,'objective':OBJECTIVE,'reason':'Explicit exploration tool envelope; source recorded by controller.',
        'evidence_ids':[],'random_seed':seed,'search_method':'SOBOL','settings':{'sample_count':proposals}}


def inverse_proposals(explorer,d,meter,origin):
    """Original inverse_at_shape: continuous caps, exact requested six-axis box."""
    local=region_problem(explorer.problem,d['normalized_bounds'])
    bw=next((s for s in active_m1_specs(local) if s['metric']=='BW_Hz'),None)
    if bw is None:
        explorer._event('TOOL_UNAVAILABLE_FOR_PROBLEM',tool=origin,reason='No supported BW target')
        return
    target=(bw['min']+bw['max'])/2 if {'min','max'}<=set(bw) else bw['min']*1.2 if 'min' in bw else bw['max']*.8
    n=d['settings']['sample_count']
    draws=qmc.Sobol(d=2,scramble=True,seed=d['random_seed']).random_base2((n-1).bit_length())
    for i,u in enumerate(draws[:n]):
        if meter.counts['analytic_calls']>=meter.cheap_limit:
            explorer._event('ANALYTIC_BUDGET_EXHAUSTED',tool=origin,attempt=i)
            return
        c1=physical_coordinate(local['parameters']['C1'],float(u[0]))
        c2=physical_coordinate(local['parameters']['C2'],float(u[1]))
        # The existing M1 exploration extreme/phase-shape pattern is retained, using
        # local continuous bounds; never the frozen discrete capacitor table.
        if i==0:c1,c2=local['parameters']['C1']['min'],local['parameters']['C2']['max']
        shape=math.sqrt(1+c2/c1)*(1.,.8,1.25)[i%3]
        try:
            proposed=inverse_at_shape(axes(local),c1,c2,target,shape,meter)
            if proposed is None:raise ValueError('No local legal Icp/Kvco split')
            yield make_parameters(explorer.problem,proposed,check_bounds=False)
        except (ArithmeticError,ValueError,RuntimeError) as error:
            explorer._event('INVERSE_PROPOSAL_FAILED',tool=origin,attempt=i,reason=str(error),
                            C1_F=c1,C2_F=c2,shape=shape,target_BW_Hz=target)


def sensitivity_plan(explorer,seed_id,bounds):
    center=explorer.evidence[seed_id]
    # Reuse the existing finite-difference routine to generate its exact
    # stencil, then again to interpret only the actual evaluated evidence.
    p=deepcopy(explorer.problem)
    p['exploration']['sensitivity_representatives']=1
    planned=[]
    region={'region_id':'LOCAL:'+seed_id,'representative_evidence_id':seed_id,'representative_parameters':center['parameters'],
            'representative_metrics':center['metrics']}
    def collect(candidate,origin):
        planned.append(candidate)
        return {'evidence_id':'PLANNED_NOT_EVIDENCE','M1_status':'NOT_EVALUATED','metrics':{}}
    sensitivity(p,{'regions':[region]},collect)
    return planned,region


def execute_tool(explorer, *, decision_id,region,tool,seed,config,meter):
    method=tool['method']
    count=min(config['max_tool_proposals'],max(64,tool['m1_budget']*8))
    d=envelope(explorer,decision_id=decision_id,region_id=decision_id+':'+region['region_id']+':'+method,
        bounds=region['normalized_bounds'],budget=tool['m1_budget'],seed=seed,proposals=count)
    before=len(explorer.rows);analytic_before=meter.counts['analytic_calls'];derivative=None
    if method=='SOBOL_IN_REGION':
        observation=explorer.execute(d)
    elif method in ('ANALYTICAL_INVERSE','PHYSICS_GUIDED_SEEDS'):
        observation=explorer.execute(d,candidate_stream=inverse_proposals(explorer,d,meter,method),tool_name=method)
    elif method=='SLSQP':
        d.update(action='OPTIMIZE',search_method='SLSQP',seed_ids=[tool['seed_id']] if tool.get('seed_id') else [],
                 settings={'maxiter':40,'finite_difference_step':1e-5})
        if config.get('active_variables'):d['active_variables']=list(config['active_variables'])
        observation=explorer.execute(d)
    elif method=='LOCAL_SENSITIVITY':
        planned,rep=sensitivity_plan(explorer,tool['seed_id'],region['normalized_bounds'])
        d['settings']['sample_count']=len(planned)
        observation=explorer.execute(d,candidate_stream=iter(planned),tool_name='LOCAL_SENSITIVITY')
        seen={r['parameter_sha256']:r for r in explorer.calibration_samples+explorer.rows}
        def actual(candidate,origin):
            return seen.get(fingerprint(candidate),{'evidence_id':None,'M1_status':'NOT_EVALUATED','metrics':{}})
        local=deepcopy(explorer.problem)
        local['exploration']['sensitivity_representatives']=1
        derivative=sensitivity(local,{'regions':[rep]},actual)
    else:
        raise ValueError('unsupported subregion tool: '+str(method))
    observation['tool_method']=method
    observation['requested_region_id']=region['region_id']
    observation['analytic_calls']=meter.counts['analytic_calls']-analytic_before
    observation['actual_region_equals_requested']=observation['normalized_bounds']==region['normalized_bounds']
    observation['M1_feasible_fraction']=len(observation['new_positive_evidence_ids'])/observation['cost']['M1_calls'] if observation['cost']['M1_calls'] else None
    observation['formal_evidence_ids']=[r['evidence_id'] for r in explorer.rows[before:] if r['formal_M1_called']]
    observation['sensitivity']=derivative
    return observation
