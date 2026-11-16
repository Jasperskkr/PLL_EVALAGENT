"""Source statistics and honest inference boundaries, independent-verifier owned runs."""
from copy import deepcopy
import ctypes
import math
import numpy as np
import pytest
from scipy.signal import welch
from pll_allocation.verification.stage6c_identity import check_build,default_build
from pll_allocation.verification.stage6c_native import simulate,noise_levels
from pll_allocation.verification.noise import seed_interval,aggregate,estimate_phase,validate_protocol
from pll_allocation.pipeline_contracts import load_inputs
from pll_allocation.block_space.contracts import make_candidate
from tools.freeze_stage6c import documents


def samples(seed,n,dt,snu=100.,si=1e-24,on=.2):
    check_build();lib=ctypes.CDLL(str(default_build()/'kernel.dll'));f=lib.sample_process;ptr=ctypes.POINTER(ctypes.c_double)
    f.argtypes=[ctypes.c_uint64,ctypes.c_longlong,ctypes.c_double,ctypes.c_double,ctypes.c_double,ctypes.c_double,ptr]
    f.restype=ctypes.c_int;out=np.empty((n,4))
    assert f(seed,n,dt,snu,si,on,out.ctypes.data_as(ptr))==0
    return out


def test_physical_source_variances_dt_repeatability_and_independence():
    n=262144;a=samples(11,n,1e-8);b=samples(11,n,2e-8);c=samples(23,n,1e-8)
    assert np.array_equal(a,samples(11,n,1e-8))
    assert not np.array_equal(a,c)
    expected=[(2*np.pi)**2*100*1e-8/2,1e-24/(2e-8),1e-24*1e-8*.2/2,1e-24*1e-8*.2/2]
    assert np.allclose(a.var(axis=0),expected,rtol=.015,atol=0)
    assert np.allclose(b.var(axis=0)/a.var(axis=0),[2,.5,2,2],rtol=1e-12,atol=0)
    corr=np.corrcoef(a.T)-np.eye(4);assert np.max(np.abs(corr))<.01
    off=samples(11,1024,1e-8,on=0);assert np.all(off[:,2:]==0)


def test_free_vco_diffusion_and_phase_psd():
    dt=1e-8;a=samples(47,524288,dt)[:,0]
    for length in (64,1024):
        diffusion=a.reshape(-1,length).sum(axis=1).var(ddof=1)
        assert diffusion==pytest.approx((2*np.pi)**2*100*(length*dt)/2,rel=.2)
    f,p=welch(np.cumsum(a),fs=1/dt,window='hann',nperseg=16384,noverlap=8192,detrend='constant')
    keep=(f>=1e5)&(f<=3e6)
    slope=np.polyfit(np.log10(f[keep]),np.log10(p[keep]),1)[0]
    assert -2.12<slope<-1.88
    assert np.median(p[keep]*f[keep]**2/100)==pytest.approx(1.,rel=.12)


def test_reference_reconstruction_spectrum_and_native_streams():
    _,model,_,_=load_inputs();c=make_candidate(model);d=documents()
    args=dict(duration_s=400e-6,noise_onset_s=160e-6,dt_s=.4e-9,record_interval_s=20e-9)
    a=simulate(c,d['nonideal_zero.json'],d['noise_reference.json'],seed=11,**args)
    b=simulate(c,d['nonideal_zero.json'],d['noise_reference.json'],seed=11,**args)
    assert np.array_equal(a['trace'],b['trace'])
    assert np.all(np.diff(a['ref_edges'])>0)
    assert np.isfinite(a['extended_trace']).all()
    # Reference phase input is directly observed, independent of PLL output transfer.
    z=a['trace'];keep=z[:,0]>=180e-6;dt=np.median(np.diff(z[keep,0]))
    f,p=welch(z[keep,2],fs=1/dt,nperseg=2048,noverlap=1024,detrend='constant')
    band=(f>1e5)&(f<1e6);shape=np.sinc(f[band]/1e7)**4
    assert np.mean(p[band]/shape)==pytest.approx(1e-13,rel=.22)


def test_gated_cp_native_off_duty_and_charge_balance():
    _,model,_,_=load_inputs();c=make_candidate(model);d=documents()
    gated={'up_A2_per_Hz':1e-24,'down_A2_per_Hz':1e-24}
    r=simulate(c,d['nonideal_reset.json'],d['noise_zero.json'],cp_gated_psd=gated,
        duration_s=250e-6,noise_onset_s=200e-6,record_interval_s=20e-9)
    x=r['extension']['diagnostics']
    assert r['extension']['cp_model']=='GATED_UP_DOWN'
    assert x['up_on_time_s']>x['reset_count']*1e-9
    assert abs(x['charge_balance_residual_C'])<2e-18
    assert x['up_noise_charge_C']!=0 and x['down_noise_charge_C']!=0


def test_unsupported_noise_and_observation_protocol():
    _,m,_,_=load_inputs();c=make_candidate(m);d=documents();p={k:v['value'] for k,v in c['values'].items()}
    bad=deepcopy(d['noise_vco.json']);bad['sources'][0]['psd_values']['exponent']=-3
    with pytest.raises(ValueError,match='UNSUPPORTED'):noise_levels(bad,p)
    for mutation in [lambda q:q.update(observation_s=1e-5),lambda q:q.update(band_Hz=[100,1e6]),lambda q:q.update(seeds=[11])]:
        q=deepcopy(d['noise_protocol.json']);mutation(q)
        with pytest.raises(ValueError):validate_protocol(q)


def test_seed_CI_constraint_boundary_no_welch_pseudoreplication():
    d=documents();q=d['noise_protocol.json'];rows=[]
    for dt in q['dt_pair_s']:
        for seed,var in zip(q['seeds'],[.9,1.,1.1,.95,1.05]):
            rows.append(dict(requested_dt_s=dt,seed=seed,random_phase_variance_rad2=var))
    value=1/(2*np.pi*80e6)
    assert aggregate(rows,q,value*2)['jitter_constraint_status']=='PASS'
    assert aggregate(rows,q,value*.5)['jitter_constraint_status']=='FAIL'
    assert aggregate(rows,q,value)['jitter_constraint_status']=='UNKNOWN'
    assert seed_interval([.9,1.,1.1,.95,1.05])['independent_seed_count']==5
    # Statistical convergence cannot be promoted by a larger number of overlapping PSD segments.
    for r in rows[:5]:r['random_phase_variance_rad2']*=2
    assert aggregate(rows,q,value*3)['jitter_constraint_status']=='UNKNOWN'


def test_phase_psd_normalization_and_deterministic_separation():
    q=documents()['noise_protocol.json'];dt=q['record_interval_s'];t=np.arange(0,.0042,dt)
    f0=100e3;amplitude=.01;det=.002*np.sin(2*np.pi*2e5*t)
    baseline=np.zeros((len(t),6));baseline[:,0]=t;baseline[:,1]=det/8
    run=baseline.copy();run[:,1]+=(amplitude*np.sin(2*np.pi*f0*t)+.2*t)/8
    est=estimate_phase(run,baseline,q);expected=amplitude**2/2
    assert est['summary']['random_phase_variance_rad2']==pytest.approx(expected,rel=.001)
    assert est['summary']['total_phase_variance_rad2']>est['summary']['random_phase_variance_rad2']
    assert est['summary']['no_linear_slope_subtraction']


def test_protocol11_settling_is_before_full_observation():
    q=documents()['noise_protocol.json'];q.update(protocol_id='pll-noise-verification-1.1',noise_settle_s=100e-6)
    dt=q['record_interval_s'];t=np.arange(0,.004300001,dt);z=np.zeros((len(t),6));z[:,0]=t
    z[:,1]=.01*np.sin(2*np.pi*1e5*t)/8
    est=estimate_phase(z,z.copy(),q)
    assert est['time_s'][0]>=300e-6
    assert est['time_s'][-1]-est['time_s'][0]>=q['observation_s']-2*dt
    assert est['summary']['random_integrated_jitter_s']==0
    bad=deepcopy(q);bad['noise_settle_s']=0
    with pytest.raises(ValueError):validate_protocol(bad)
