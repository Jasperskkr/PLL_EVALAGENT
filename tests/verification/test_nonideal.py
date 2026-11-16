"""Native mechanism tests, executed only by independent verifier."""
from copy import deepcopy
import json
import math
from pathlib import Path
import numpy as np
import pytest
from pll_allocation.verification.stage6c_native import simulate
from pll_allocation.verification.simulator import simulate as original
from pll_allocation.verification.stage6c_identity import check_build
from pll_allocation.block_space.contracts import make_candidate
from pll_allocation.pipeline_contracts import load_inputs
from tools.freeze_stage6c import documents
from tools.generate_stage6c_kernel import source,HERE


@pytest.fixture
def data():
    _,m,_,proto=load_inputs();return make_candidate(m),documents(),proto


def test_generated_reproducible_and_build_bound():
    assert (HERE/'stage6c_kernel.cpp').read_text(encoding='utf-8')==source()
    assert check_build()['rng']=='SplitMix64_BoxMuller_1.0'


def test_zero_exact_fallback(data):
    c,d,_=data;settings=dict(duration_s=160e-6,dt_s=.4e-9)
    a=original(c,**settings);b=simulate(c,d['nonideal_zero.json'],d['noise_zero.json'],**settings)
    for k in ('trace','ref_edges','div_edges'):assert np.array_equal(a[k],b[k])
    assert b['extension']['original_direct_dispatch']


@pytest.mark.parametrize('name',['K2_plus','K2_minus','mismatch_plus','mismatch_minus','reset','leak_plus','leak_minus','compliance','combined'])
def test_mechanism_charge_edges_and_dt(data,name):
    from pll_allocation.verification.measure import capture_metrics
    c,d,proto=data;runs=[];caps=[]
    for dt in (.4e-9,.2e-9):
        run=simulate(c,d['nonideal_'+name+'.json'],dt_s=dt)
        runs.append(run);caps.append(capture_metrics(run,proto));x=run['extension']['diagnostics'];z=run['extended_trace']
        assert abs(x['charge_balance_residual_C'])<2e-18
        assert np.all(np.diff(run['ref_edges'])>0) and np.all(np.diff(run['div_edges'])>0)
        assert np.all(np.diff(z[:,6])>0)
        assert np.all((z[:,3]>=0)&(z[:,3]<=1.2))
        assert np.all(np.diff(z[:,13])>=0) and np.all(np.diff(z[:,14])>=0)
        assert np.isfinite(z).all()
        if name=='reset':
            # Simultaneous reset current intervals contribute equal UP and DOWN time, ideal matched pulses conserve DC charge.
            assert x['reset_count']>1000
            assert x['up_on_time_s']>x['reset_count']*1.5e-9
            assert x['down_on_time_s']>x['reset_count']*1.5e-9
    assert caps[0]['status']==caps[1]['status']
    assert abs(runs[0]['summary']['tail_frequency_Hz']-runs[1]['summary']['tail_frequency_Hz'])<80
    assert abs(runs[0]['summary']['vfinal_V']-runs[1]['summary']['vfinal_V'])<1e-4


def test_phase_frequency_law_and_pulse_charge(data):
    c,d,_=data;p={k:v['value'] for k,v in c['values'].items()};ni=d['nonideal_combined.json']
    r=simulate(c,ni,record_interval_s=.4e-9,duration_s=30e-6,onset_s=30e-6);z=r['extended_trace'];dt=np.diff(z[:,0])
    assert np.allclose(np.diff(z[:,6]),2*np.pi*z[:-1,7]*dt,rtol=1e-8,atol=1e-11)
    x=r['extension']['diagnostics'];iup=p['Icp']*(1+ni['cp_mismatch']/2);idown=p['Icp']*(1-ni['cp_mismatch']/2)
    assert x['input_charge_C']==pytest.approx(iup*x['up_on_time_s']-idown*x['down_on_time_s'],abs=2e-18)
    # Independent first Euler step: no edge yet, no charge, v=u => constant LF, VCO uses nonlinear law.
    assert z[1,3]==z[0,3] and z[1,4]==z[0,4]
    vstar=r['extension']['derived']['Vstar_V'];expected=p['f0']+p['Kvco']*.15+ni['K2_Hz_per_V2']*.15*(.15-vstar)
    assert z[0,7]==pytest.approx(expected)


def test_rail_clamp_charge_accounted(data):
    c,d,_=data;p=deepcopy(d['nonideal_zero.json']);p['leakage_A']=.01
    r=simulate(c,p,duration_s=10e-6,onset_s=10e-6);x=r['extension']['diagnostics']
    assert r['summary']['actual_clamp_events']>100
    assert x['clamp_charge_C']<0
    assert abs(x['charge_balance_residual_C'])<1e-16


def test_nonpositive_tuning_and_invalid_nonideal_rejected(data):
    c,d,_=data
    for key,val in [('K2_Hz_per_V2',1e9),('cp_mismatch',2.),('reset_delay_s',1e-7)]:
        p=deepcopy(d['nonideal_zero.json']);p[key]=val
        with pytest.raises(ValueError):simulate(c,p)


def test_finite_perturbation_and_reset_boundary(data):
    c,d,_=data
    r=simulate(c,d['nonideal_reset.json'],duration_s=200e-6,onset_s=50e-6,phase_end_s=100e-6,
        phase_amplitude_rad=.4,modulation_Hz=1e5,record_interval_s=20e-9)
    t=r['trace'][:,0];z=r['trace'][:,2]
    assert np.max(np.abs(z[t>=100e-6]))<1e-10
    assert np.max(np.abs(z[(t>50e-6)&(t<100e-6)]))>.39
    with pytest.raises(ValueError):simulate(c,d['nonideal_zero.json'],phase_end_s=100.1e-6,modulation_Hz=1e5)


@pytest.mark.parametrize('name',['K2_plus','mismatch_plus'])
def test_long_low_frequency_no_latched_reset(data,name):
    from pll_allocation.verification.measure import response_metrics
    c,d,proto=data;p={k:v['value'] for k,v in c['values'].items()};freq=1e4;duration=50e-6+20/freq
    r=simulate(c,d['nonideal_'+name+'.json'],duration_s=duration,initial_control_V=(80e6-p['f0'])/p['Kvco'],
        phase_amplitude_rad=.01,modulation_Hz=freq,onset_s=50e-6)
    m=response_metrics(r,proto,measurement_start_s=50e-6+8/freq,measurement_end_s=duration)
    assert m['status']=='MEASURED',m
    z=r['extended_trace'];assert z[-1,17]>duration*1e7*.98
    assert np.max(np.diff(z[:,6]))<2*np.pi*80e6*21e-9
