from copy import deepcopy
import json
import math
import numpy as np
import pytest
from pathlib import Path
FIXTURES = Path(__file__).resolve().parents[1]/"fixtures"
from pll_allocation.verification.resources import CONFIGS
from pll_allocation.verification.experiments import protocol as formal_protocol
def protocol():
    return __import__("json").loads((FIXTURES/"verification/protocol_v1_0.json").read_text(encoding="utf-8"))
from pll_allocation.verification.experiments import HERE,candidate,read
from pll_allocation.verification.measure import capture_metrics,response_metrics
from pll_allocation.verification.verify import (assemble_result,example_proposal,interval_judgment,validate_proposal,verify)
from pll_allocation.physics_mapping.model import fingerprint


def test_integer_startup_slips_do_not_preclude_terminal_lock():
    t=np.linspace(0,30e-6,1501)
    z=np.column_stack([t,np.full(len(t),-16*math.pi),np.zeros(len(t)),
        np.full(len(t),.4),np.full(len(t),.4),np.zeros(len(t))])
    run={'trace':z,'summary':{'actual_clamp_events':0}}
    old=capture_metrics(run,protocol())
    corrected=capture_metrics(run,read(CONFIGS/'verification/protocol_v1_1.json'))
    assert old['status']=='NOT_CAPTURED_WITHIN_WINDOW'
    assert corrected['status']=='CAPTURED_WITHIN_WINDOW'
    assert corrected['net_cycle_index']==8
    z[:,1]=2*math.pi*t/1e-6
    assert capture_metrics(run,read(CONFIGS/'verification/protocol_v1_1.json'))['status']=='NOT_CAPTURED_WITHIN_WINDOW'


def test_shared_allocation_proposal_and_fixed_bindings():
    item=example_proposal(candidate())
    model,p,domain=validate_proposal(item)
    assert p==candidate() and domain['declared_domain']=='IN_DECLARED_DOMAIN'
    item['system_spec']['metrics'][1]['max']=350000
    with pytest.raises(ValueError,match='SystemSpec'):validate_proposal(item)


@pytest.mark.parametrize('mutation', ['hash','unit','nonideal','domain','conditions'])
def test_bad_proposal_cannot_invoke_backend_or_pass(tmp_path,mutation):
    p=example_proposal(candidate())
    if mutation=='hash':p['parameter_sha256']='bad'
    if mutation=='unit':p['joint_block_spec']['values']['Kvco']['unit']='rad/s/V'
    if mutation=='nonideal':p['joint_block_spec']['values']['PFD_reset_delay']['value']=1e-9
    if mutation=='domain':p['joint_block_spec']['values']['Icp']['value']=1
    if mutation=='conditions':p['operating_conditions']['f_ref']['value']=9e6
    if mutation!='hash':p['parameter_sha256']=fingerprint(p['joint_block_spec'])
    result=verify(p,tmp_path/'bad')
    assert result['overall_status']=='UNKNOWN'
    assert not result['verified_joint_block_spec']
    assert result['execution_cost']['completed_native_runs']==0
    assert (tmp_path/'bad/proposal.json').is_file()
    if mutation=='nonideal':assert result['validity_status']=='UNSUPPORTED'


def test_constraints_use_measurement_envelopes_and_keep_PM_frequency_unknown():
    prop=example_proposal(candidate())
    fixture=read(FIXTURES/'stage3a_nominal_measured.json')
    capture=fixture['capture'];compared=fixture['comparison']
    doc=read(CONFIGS/'verification/protocol_v1_1.json')
    result=assemble_result(prop,doc,{},capture,{},compared)
    checks={x['metric']:x['status'] for x in result['constraints']}
    assert checks=={'output_frequency_Hz':'UNKNOWN','BW_Hz':'PASS','PM_deg':'UNKNOWN'}
    assert result['metrics']['PM_deg']['value'] is None
    assert result['metrics']['UGF_Hz']['value'] is None
    assert result['overall_status']=='UNKNOWN' and not result['verified_joint_block_spec']
    # A spoofed prediction in the proposal must not influence M2 or its decision.
    prop['M1']={'metrics':{'BW_Hz':1,'PM_deg':100}}
    again=assemble_result(prop,doc,{},capture,{},compared)
    assert again['metrics']==result['metrics']
    assert interval_judgment([299960,302943],prop['system_spec']['metrics'][1])=='UNKNOWN'
    assert interval_judgment([301200,301400],prop['system_spec']['metrics'][1])=='FAIL'
    compared['numerical_converged']=False
    bad=assemble_result(prop,doc,{},capture,{},compared)
    assert bad['metrics']['BW_Hz']['value'] is None


def test_saturation_or_nonlinear_response_is_not_accepted():
    f=1e5;t=np.arange(0,220e-6,20e-9)
    ref=.01*np.sin(2*math.pi*f*t)
    y=.008*np.sin(2*math.pi*f*t)+.003*np.sin(4*math.pi*f*t)
    trace=np.column_stack([t,y,ref,np.full(len(t),.4),np.full(len(t),.4),np.zeros(len(t))])
    run={'trace':trace,'settings':{'modulation_Hz':f,'onset_s':50e-6}}
    m=response_metrics(run,protocol(),measurement_start_s=80e-6,measurement_end_s=200e-6)
    assert m['status']=='UNKNOWN' and 'harmonic_distortion' in m['reasons']


@pytest.mark.parametrize('condition',['undersampled','nonfinite','unordered'])
def test_unreliable_trace_cannot_be_a_response_measurement(condition):
    f=1e6;t=np.arange(0,220e-6,100e-9 if condition=='undersampled' else 20e-9)
    ref=.01*np.sin(2*math.pi*f*t)
    trace=np.column_stack([t,ref,ref,np.full(len(t),.4),np.full(len(t),.4),np.zeros(len(t))])
    if condition=='nonfinite':trace[len(trace)//2,1]=np.nan
    if condition=='unordered':trace[len(trace)//2,0]-=1e-6
    m=response_metrics({'trace':trace,'settings':{'modulation_Hz':f,'onset_s':50e-6}},protocol(),
        measurement_start_s=80e-6,measurement_end_s=200e-6)
    assert m['status']=='UNKNOWN'
