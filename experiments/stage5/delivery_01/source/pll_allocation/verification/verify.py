"""Track A AllocationProposal -> executed, independent behavioral verification.

Uses the existing SI candidate envelope and frozen model; no Track A policy import.
M1 is called only after all measurements. A proposal's predictions are never trusted.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from .resources import CONFIGS
import sys
from .experiments import HERE,read,write,response_sweep
from .run_suite import capture_pair,comparison_after_measurement
from .simulator import MODEL_VERSION,validate_parameters

from pll_allocation.block_space.contracts import FREE_IDS,check_parameters,load_model
from pll_allocation.physics_mapping.model import fingerprint

RESULT_SCHEMA='behavioral-verification-result-1.0'


def frozen_model():
    return load_model(CONFIGS/'BLOCK_SPACE_MODEL_V1.json')


def validate_proposal(item):
    """Validate Track A's public envelope, without importing its optimizer or M1."""
    model=frozen_model()
    if not isinstance(item,dict) or item.get('schema_version')!='allocation-proposal-1.0':
        raise ValueError('allocation-proposal-1.0 required')
    if not isinstance(item.get('candidate_id'),str) or not item['candidate_id'].strip():
        raise ValueError('nonempty candidate_id required')
    p=item['joint_block_spec'];validate_parameters(p)
    if item['parameter_sha256']!=fingerprint(p):raise ValueError('parameter hash mismatch')
    if item['block_space_sha256']!=fingerprint(model) or item['topology']!=model['topology']:
        raise ValueError('frozen Block Space/topology binding mismatch')
    if item['system_spec']!=model['experiment']['system_spec'] or item['system_spec_sha256']!=fingerprint(item['system_spec']):
        raise ValueError('Track B v1 supports only unchanged Stage 1.5 SystemSpec')
    versions=item['versions']
    if any(versions.get(k)!=v for k,v in model['versions'].items()):raise ValueError('model version mismatch')
    if versions.get('block_space_schema')!=model['schema_version'] or versions.get('system_spec')!=item['system_spec']['version']:
        raise ValueError('contract version mismatch')
    expected={k:v for k,v in p['values'].items() if k not in FREE_IDS}
    if item['operating_conditions']!=expected:raise ValueError('fixed operating conditions mismatch')
    if item.get('verified_joint_block_spec') is not False or item.get('M2_status')!='NOT_EVALUATED':
        raise ValueError('proposal cannot self-certify M2')
    domain=check_parameters(model,p)
    if domain['declared_domain']!='IN_DECLARED_DOMAIN':raise ValueError('OUT_OF_DECLARED_DOMAIN')
    return model,p,domain


def example_proposal(parameters,candidate_id='track_b_reference_nominal'):
    """Same external envelope as Track A; no fabricated allocator/M1 invocation."""
    model=frozen_model();spec=model['experiment']['system_spec']
    return {'schema_version':'allocation-proposal-1.0','candidate_id':candidate_id,
        'parameter_sha256':fingerprint(parameters),'joint_block_spec':parameters,
        'block_space_sha256':fingerprint(model),'system_spec_sha256':fingerprint(spec),
        'system_spec':deepcopy(spec),'topology':deepcopy(model['topology']),
        'versions':{**model['versions'],'baseline':'track-b-interface-reference-1.0',
            'block_space_schema':model['schema_version'],'system_spec':spec['version']},
        'operating_conditions':deepcopy({k:v for k,v in parameters['values'].items() if k not in FREE_IDS}),
        'allocation_strategy':'STAGE1_5_REFERENCE_NO_AGENT',
        'blocks':{b:[n for n,a in model['variables'].items() if a['block']==b] for b in model['topology']['blocks']},
        'M1':None,'constraint_margins':None,'allocation_metadata':{'purpose':'verification integration test'},
        'validation_level':'NOT_VALIDATED','verified_joint_block_spec':False,'M2_status':'NOT_EVALUATED',
        'prediction_confidence':{'status':'NOT_USED_BY_VERIFIER'}}


def interval_judgment(interval,spec):
    if interval is None:return 'UNKNOWN'
    lo,hi=interval;tol=spec.get('tolerance',0)
    low=spec.get('min',float('-inf'))-tol;high=spec.get('max',float('inf'))+tol
    if hi<low or lo>high:return 'FAIL'
    if lo>=low and hi<=high:return 'PASS'
    return 'UNKNOWN'


def assemble_result(proposal,doc,domain,capture,response,comparison):
    """Pure decision adapter. No M1 prediction can fill any M2 metric slot."""
    fine=capture['fine'];checks=capture['step_comparison'];settled=capture['reliable_capture_status']=='CAPTURED_WITHIN_WINDOW'
    f=fine['output_frequency_Hz'];voltage=fine['steady_control_V']
    empirical_resolution=max(.01,2*checks['frequency_difference_ppm']*80.)
    f_interval=[f-empirical_resolution,f+empirical_resolution] if capture['numerical_converged'] else None
    bwok=bool(comparison and comparison['numerical_converged'])
    bw=comparison['M2_BW_measurement'].get('BW_Hz') if bwok else None
    bw_interval=comparison['BW_numerical_envelope_Hz'] if bwok else None
    metrics={
        'output_frequency_Hz':{'value':f,'unit':'Hz','status':'MEASURED_STEADY' if settled else 'MEASURED_TERMINAL_WINDOW',
            'numerical_envelope':f_interval,'required_precision_validated':False,
            'uncertainty_basis':'empirical two-step difference with 0.01 Hz reporting floor; not a certified confidence bound',
            'confidence':'CONDITIONAL_ON_TRACE_WINDOW'},
        'steady_control_V':{'value':voltage,'unit':'V','status':'MEASURED_STEADY' if settled else 'MEASURED_TERMINAL_WINDOW',
            'step_difference_V':checks['control_difference_V']},
        'capture':{'value':capture['reliable_capture_status'],'status':'MEASURED_WINDOW_CONDITIONAL',
            'initial_control_V':capture['initial_control_V'],'duration_s':capture['duration_s']},
        'lock_time_s':{'value':fine['lock_time_s'] if settled else None,'unit':'s','status':fine['lock_time_status'] if settled else 'UNKNOWN',
            'resolution_s':1e-6,'step_difference_s':checks['lock_time_difference_s']},
        'BW_Hz':{'value':bw,'unit':'Hz','status':'MEASURED_CONVERGED' if bwok else 'UNKNOWN',
            'numerical_envelope':bw_interval,'confidence':'LOCAL_WARM_START_SAMPLED_POINTS_ONLY' if bwok else 'UNKNOWN',
            'observable':'continuous divided VCO phase fundamental / reference phase fundamental',
            'edge_only_equivalence':'NOT_ESTABLISHED; edge timestamp harmonic fits show different sampled response',
            'envelope_scope':'bracketing and amplitude/step/window refinements; excludes cross-observable systematic difference'},
        'PM_deg':{'value':None,'unit':'deg','status':'PM_M2_UNKNOWN'},
        'UGF_Hz':{'value':None,'unit':'Hz','status':'UNKNOWN_NO_DIRECT_LOOP_INJECTION'}}
    constraints=[]
    for spec in proposal['system_spec']['metrics']:
        name=spec['metric'];status='UNKNOWN';reason='PM_M2_UNKNOWN' if name=='PM_deg' else ''
        if name=='BW_Hz':
            status=interval_judgment(bw_interval,spec);reason='converged measured BW envelope' if bwok else 'no converged independent BW'
        if name=='output_frequency_Hz':
            # Finite-window tracking cannot certify the frozen 1 microHz equality.
            judged=interval_judgment(f_interval,spec)
            if judged=='FAIL' and capture['numerical_converged'] and abs(f-80e6)>8000:
                status='FAIL';reason='converged terminal frequency fails equality and even the capture tracking threshold; finite-window only'
            else:reason='UNKNOWN_REQUIRED_PRECISION: frozen 1e-6 Hz tolerance not independently validated'
        constraints.append({'metric':name,'target':deepcopy(spec),'status':status,'reason':reason})
    overall='FAIL' if any(x['status']=='FAIL' for x in constraints) else 'PASS' if all(x['status']=='PASS' for x in constraints) else 'UNKNOWN'
    errors={}
    m1=comparison['M1_prediction'] if comparison else None
    if m1 and m1['status']=='OK':
        predictions=m1['metrics']
        for name,m2,pred in [('BW_Hz',bw,predictions.get('BW_Hz')),
            ('output_frequency_Hz',f,predictions.get('output_frequency_Hz')),
            ('steady_control_V',voltage,predictions.get('Vctrl_required_V'))]:
            valid=m2 is not None and pred is not None and (name=='BW_Hz' or settled)
            errors[name]={'M1_prediction':pred,'M2_measurement':m2,'comparable':valid,
                'absolute_error':m2-pred if valid else None,'relative_error':(m2/pred-1) if valid and pred else None}
    feedback=[]
    if not settled:feedback.append({'code':'CAPTURE_NOT_ESTABLISHED','initial_control_V':capture['initial_control_V'],
        'action':'compare additional initial conditions or a longer window; do not infer absolute nonlockability'})
    if fine['actual_clamp_events']:feedback.append({'code':'VCTRL_CLAMP_OBSERVED','count':fine['actual_clamp_events'],
        'action':'inspect trajectory and terminal clamps; warm local BW does not establish cold capture'})
    feedback.extend([{'code':'PM_M2_UNKNOWN','action':'direct loop return-ratio protocol required'},
        {'code':'FREQUENCY_PRECISION_UNKNOWN','action':'use measured frequency as diagnostic; keep frozen equality unresolved'}])
    for x in constraints:
        if x['status']=='FAIL':feedback.append({'code':'MEASURED_CONSTRAINT_FAIL','metric':x['metric'],'reason':x['reason']})
    return {'schema_version':RESULT_SCHEMA,'candidate_id':proposal['candidate_id'],
        'parameter_sha256':proposal['parameter_sha256'],'joint_block_spec':deepcopy(proposal['joint_block_spec']),
        'proposal_versions':deepcopy(proposal['versions']),'model_version':MODEL_VERSION,
        'protocol_id':doc['protocol_id'],'protocol_sha256':fingerprint(doc),
        'fixed_system_spec_sha256':proposal['system_spec_sha256'],'domain':domain,
        'metrics':metrics,'constraints':constraints,'overall_status':overall,'verified_joint_block_spec':False,
        'validation_level':'M2_PARTIAL_INDEPENDENT_METRICS','M1_posthoc':m1,'prediction_errors':errors,
        'PM_diagnostic_only':comparison.get('conditional_PM_prototype') if comparison else None,
        'reliability':{'capture_step_converged':capture['numerical_converged'],'BW_converged':bwok,
            'required_PM_supported':False,'domain_wide_claim':False,'cold_capture_does_not_follow_from_warm_BW':True},
        'structured_feedback':feedback,'failure_reasons':[x['reason'] for x in constraints if x['status']!='PASS'],
        'simulation_settings':{'capture':doc['capture'],'frequency_response':doc['frequency_response'],
            'actual_capture_duration_s':capture['duration_s'],'actual_initial_control_V':capture['initial_control_V']},
        'source_hashes':{'kernel.cpp':hashlib.sha256((HERE/'kernel.cpp').read_bytes()).hexdigest(),
            'model':fingerprint(frozen_model())}}


def verify(proposal,out,*,initial_control_V=.15,capture_duration_s=160e-6):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    write(out/'proposal.json',proposal)  # persisted before any TB
    doc=read(CONFIGS/'verification/protocol_v1_1.json');write(out/'protocol.json',doc)
    try:
        model,p,domain=validate_proposal(proposal)
        capture=capture_pair(out/'capture',p,initial_control_V,capture_duration_s,protocol_document=doc)
        values=validate_parameters(p);vreq=(80e6-values['f0'])/values['Kvco'];responses={};comparison=None
        if values['Vctrl_min']<vreq<values['Vctrl_max']:
            for key,amp,dt,cycles in [('base',.01,.4e-9,12),('amplitude_half',.005,.4e-9,12),
                ('step_half',.01,.2e-9,12),('window_double',.01,.4e-9,24)]:
                responses[key]=response_sweep(out/key,p,amplitude=amp,dt=dt,cycles=cycles,protocol_document=doc)
            comparison=comparison_after_measurement(p,responses,protocol_document=doc)  # only now call M1
        result=assemble_result(proposal,doc,domain,capture,responses,comparison)
    except Exception as error:
        validity=getattr(getattr(error,'status',None),'value','INPUT_OR_EXECUTION_FAILURE')
        result={'schema_version':RESULT_SCHEMA,'candidate_id':proposal.get('candidate_id') if isinstance(proposal,dict) else None,
            'joint_block_spec':proposal.get('joint_block_spec') if isinstance(proposal,dict) else None,
            'overall_status':'UNKNOWN','verified_joint_block_spec':False,'validation_level':'NOT_VALIDATED',
            'failure_reasons':[type(error).__name__+': '+str(error)],'validity_status':validity,'metrics':{},'protocol_id':doc['protocol_id'],
            'structured_feedback':[{'code':'INPUT_OR_EXECUTION_FAILURE','action':'inspect recorded failure before resubmitting'}]}
    # Include real cost even on partial failure. Reused evidence is never counted here.
    summaries=[read(p)['summary'] for p in out.rglob('summary.json')]
    result['execution_cost']={'completed_native_runs':len(summaries),
        'integration_points':sum(s['integration_points'] for s in summaries),
        'native_elapsed_s':sum(s['elapsed_s'] for s in summaries),'failed_attempts':len(list(out.rglob('failure.json')))}
    write(out/'result.json',result);return result


