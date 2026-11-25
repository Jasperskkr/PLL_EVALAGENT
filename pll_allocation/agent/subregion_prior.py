"""Current-problem physical evidence organization; no search-box selection."""
from collections import Counter
from copy import deepcopy
import hashlib
import json

from ..allocation.physics import RELATIONS
from ..exploration.contracts import screen_problem
from ..physics_mapping.model import fingerprint
from ..verification.resources import CONFIGS
from .planner_state import compact_sample
from .candidates import rank
from .subregion_contracts import TOOLS
from .subregion_context import was_formal_call

REGISTRY=CONFIGS/'model/equations.json'
DEPENDENCIES={
 'frequency':(['N','f_ref','f0','Kvco'],['output_frequency_Hz','Vctrl_required_V']),
 'CP':(['Icp','Kvco'],['BW_Hz','UGF_Hz','PM_deg']),
 'LF':(['Rz','C1','C2'],['BW_Hz','PM_deg']),
 'loop':(['Icp','Kvco','N','Rz','C1','C2'],['BW_Hz','UGF_Hz','PM_deg']),
 'shape':(['Rz','C1','C2','Icp','Kvco'],['PM_deg','UGF_Hz']),
 'phase_ceiling':(['C1','C2'],['PM_deg']),
 'inverse_gain':(['Icp','Kvco','C1','C2','N'],['BW_Hz','UGF_Hz','PM_deg']),
 'scaling':(['Rz','Icp','Kvco'],['BW_Hz','UGF_Hz','PM_deg']),
 'stability':(['Icp','Kvco','N','Rz','C2'],['local_continuous_stability'])}


def physics_relations(model):
    registry=json.loads(REGISTRY.read_text(encoding='utf-8'))
    source={'path':'configs/model/equations.json','sha256':hashlib.sha256(REGISTRY.read_bytes()).hexdigest()}
    relations=[{'evidence_id':e['equation_id'],'category':'ANALYTICAL_RELATION','expression':e['expression'],
        'variables':e['inputs'],'metrics':e['outputs'],'applicability':e['domain'],'limitations':e['limitations'],
        'source':source,'model_fingerprint':model['model_sha256']} for e in registry['equations'] if e['model_level']=='M1']
    for k,v in RELATIONS.items():
        variables,metrics=DEPENDENCIES[k]
        relations.append({'evidence_id':'REL:'+k,'category':'NECESSARY' if k=='phase_ceiling' else 'ANALYTICAL_RELATION',
            'expression':v,'variables':variables,'metrics':metrics,'applicability':'Current ideal positive continuous locked-point CPPLL; supplied fixed N/fref',
            'limitations':'No M2/capture/noise claim; phase ceiling is necessary, not sufficient; scaling fixes capacitors',
            'source':{'path':'pll_allocation/allocation/physics.py','sha256':model['source_fingerprints']['pll_allocation/allocation/physics.py']},
            'model_fingerprint':model['model_sha256']})
    relations +=[{'evidence_id':'NEC:TUNING','category':'NECESSARY','expression':'Vctrl_min < (N*f_ref-f0)/Kvco < Vctrl_max',
        'variables':['f0','Kvco','N','f_ref'],'metrics':['Vctrl_required_V'],'applicability':'Static ideal operating point',
        'limitations':'Does not prove capture','source':{'path':'pll_allocation/exploration/contracts.py'},'model_fingerprint':model['model_sha256']},
        {'evidence_id':'HEUR:LOCAL','category':'HEURISTIC','expression':'Use sampled evidence for search hypotheses, never extrapolate local signs globally',
        'variables':list(DEPENDENCIES['loop'][0]),'metrics':['BW_Hz','PM_deg'],'applicability':'Sample-neighborhood guidance only',
        'limitations':'Unknown outside sampled points','source':{'path':'pll_allocation/agent/subregion_prior.py'},'model_fingerprint':model['model_sha256']}]
    return relations


def build_prior(explorer,config,history,round_number,correction=None):
    samples=explorer.calibration_samples+explorer.rows
    formal=[s for s in samples if s['M1_status']=='OK' and s.get('formal_M1_result')]
    best=min(formal,key=rank,default=None)
    # At most24 initial actual M1 results; later rounds expose all bounded new
    # formal evidence and representative screening failures, no hidden full run.
    failures=[s for s in samples if s['M1_status'] not in ('OK','DUPLICATE_REFERENCE')][:8]
    displayed=[compact_sample(s,explorer.problem)|{'screening':s['screening']} for s in formal+failures]
    relations=physics_relations(explorer.context['model'])
    derivatives=[]
    for h in history:
        for o in h['observations']:
            if o.get('sensitivity'):
                for rep in o['sensitivity']['representatives']:
                    center=explorer.evidence[rep['center_evidence_id']]
                    derivatives.append({'evidence_id':'SENS75:'+o['observation_id'],
                        'category':'LOCAL_SENSITIVITY','center_parameters':center['parameters'],
                        'center_evidence_id':center['evidence_id'],'matrix':rep,
                        'source':'pll_allocation/exploration/regions.py::sensitivity',
                        'variables':list(explorer.problem['parameters']),'metrics':list(rep['normalized_matrix']),
                        'applicability':'Local actual formal-M1 stencil at this operating point only',
                        'model_fingerprint':explorer.context['model']['model_sha256']})
    evidence_ids={s['evidence_id'] for s in displayed}|{r['evidence_id'] for r in relations+derivatives}|{o['observation_id'] for h in history for o in h['observations']}
    p={'schema_version':'pll-physics-prior-context-1.0','round':round_number,'problem':deepcopy(explorer.problem),
       'model':deepcopy(explorer.context['model']),'relations':relations,'samples':displayed,
       'normalization':'Each axis maps u in[0,1] with its own declared linear/log scale; 0 never means zero physical parameter',
       'necessary_conditions':screen_problem(explorer.problem),'capability_boundary':deepcopy(explorer.context['capability_boundary']),
       'best_known':compact_sample(best,explorer.problem) if best else None,
       'tightest_constraint':min((c for c in best['judgment']['constraints'] if c['enabled'] and c['normalized_margin'] is not None),key=lambda c:c['normalized_margin'],default=None) if best else None,
       'distribution':{'formal_M1_points':len(formal),'formal_outcomes':dict(Counter(s['judgment']['m1_feasibility'] for s in formal)),
            'screen_reasons':dict(Counter(s['screening']['reason'] for s in samples if s['M1_status']=='NOT_EVALUATED_SCREEN_REJECTED'))},
       'local_sensitivity':derivatives,'sensitivity_scope':'Only evidence with actual stencils; no initial derivative claimed without evaluation',
       'tools':{'implemented':sorted(TOOLS),'unimplemented':['BOUNDARY_PROBING'],
            'semantics':{'SOBOL_IN_REGION':'Actual fixed-seed Sobol, screening then formal M1',
              'ANALYTICAL_INVERSE':'Original inverse_at_shape, continuous C1/C2, BW midpoint and peak phase shape family; no formal success assumed',
              'PHYSICS_GUIDED_SEEDS':'Same original inverse generator with continuous caps; alias, not a distinct physics model',
              'LOCAL_SENSITIVITY':'Original six-axis local finite differences centered at one in-region formal evidence point'}},
       'execution_seed':config['seed']+10*round_number,
       'budget':{'total_M1_hard_limit':config['total_m1_budget'],'initial_actual_M1':sum(was_formal_call(s) for s in explorer.calibration_samples),
           'session_new_M1':explorer.counts['M1_calls'],'round_M1_limit':config['round_m1_budget'],
           'global_coverage_reserve_M1':config['global_m1_budget'],'max_proposals_per_tool':config['max_tool_proposals'],
           'remaining_decisions':config['max_decisions']-round_number+1},
       'allowed_evidence_ids':sorted(evidence_ids),'history':deepcopy(history),'validation_feedback':correction,
       'M2_status':'NOT_EVALUATED','whole_regions_certified':False,'scope':'Select exploration envelopes from small calibration, not final BlockSpec or existing region menu'}
    p['prior_context_sha256']=fingerprint(p)
    return p
