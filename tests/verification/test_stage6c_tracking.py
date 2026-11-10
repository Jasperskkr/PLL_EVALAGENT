"""Tracking protocol checks use synthetic/saved data, no new circuit simulation."""
from copy import deepcopy
import numpy as np
import pytest
from pll_allocation.verification.noise_tracking import steady_tracking
from pll_allocation.pipeline_contracts import load_inputs
from tools.freeze_stage6c import documents


def fixture():
    q=deepcopy(documents()['noise_protocol.json']);q['protocol_id']='pll-noise-verification-1.1'
    _,_,_,p=load_inputs();t=np.arange(0,.004200001,20e-9);z=np.zeros((len(t),6));z[:,0]=t;z[:,3:5]=.6
    return {'trace':z,'summary':{'actual_clamp_events':0}},q,p


def test_zero_tracking_and_white_frequency_is_not_coldcapture():
    run,q,p=fixture();assert steady_tracking(run,q,p)['status']=='PASS_CONDITIONAL_OBSERVATION'
    # 500kHz phase modulation with tiny divided phase has large one-us mean-frequency
    # variance but stays within same phase branch, demonstrating separate quantities.
    run['trace'][:,1]=.02*np.cos(2*np.pi*.5e6*run['trace'][:,0])
    result=steady_tracking(run,q,p)
    assert result['status']=='PASS_CONDITIONAL_OBSERVATION'
    assert result['deterministic_1us_frequency_bound_failures_diagnostic']>1000


@pytest.mark.parametrize('kind',['phase','slip','clamp','rail','control','frequency'])
def test_bad_tracking_cannot_pass(kind):
    run,q,p=fixture();z=run['trace'];t=z[:,0]
    if kind=='phase':z[t>.001,1]=.2
    elif kind=='slip':z[t>.001,1]=2*np.pi
    elif kind=='clamp':z[t>.001,5]=1
    elif kind=='rail':z[t>.001,3]=1.2
    elif kind=='control':z[:,3]+=.01*np.sin(2*np.pi*1e6*t)
    else:z[:,1]=2*np.pi*100e3*t/8
    assert steady_tracking(run,q,p)['status']=='UNKNOWN'


@pytest.mark.parametrize('kind',['short','reversed','nan','missing','irregular','gap_final'])
def test_malformed_observation_never_passes(kind):
    run,q,p=fixture();z=run['trace']
    if kind=='short':run['trace']=z[(z[:,0]>=q['warmup_s'])][:10]
    elif kind=='reversed':run['trace']=z[::-1]
    elif kind=='nan':z[10000,3]=np.nan
    elif kind=='missing':run['trace']=z[:len(z)//2]
    elif kind=='gap_final':run['trace']=np.concatenate([z[:len(z)//2],z[-1:]])
    else:z[10000,0]+=1e-9
    assert steady_tracking(run,q,p)['status']=='UNKNOWN'
