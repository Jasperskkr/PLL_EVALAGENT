"""Independent physical/units/limits checks, no native runs in Phase A."""
from copy import deepcopy
import math
from pathlib import Path
import numpy as np
import pytest
from pll_allocation.pipeline_contracts import load_inputs
from pll_allocation.block_space.contracts import make_candidate
from pll_allocation.block_space.extensions import validate_noise,source_psd,validate_nonideal,K_B
from pll_allocation.physics_mapping.model import evaluate,parse_parameters
from pll_allocation.physics_mapping.noise import transfers,noise_mapping,noise_sensitivity
from tools.freeze_stage6c import documents


@pytest.fixture
def inputs():
    _,model,_,_=load_inputs()
    return model,make_candidate(model),documents()


def test_transfer_limits_and_units(inputs):
    _,c,_=inputs;p=parse_parameters(c);h=transfers(c,np.array([.01,1e12]))
    assert abs(h['reference'][0]/p['N']-1)<1e-8
    assert abs(h['vco'][0])<1e-10
    assert abs(h['vco'][1]-1)<1e-6
    assert abs(abs(h['cp'][0])/(2*math.pi*p['N']/p['Icp'])-1)<1e-8


def test_resistor_independent_nodal_kcl(inputs):
    _,c,_=inputs;p=parse_parameters(c)
    # Unit series voltage and physical KCL, independent matrix solve including feedback CP current.
    for f in np.geomspace(1,1e8,23):
        s=2j*np.pi*f;r=p['Rz'];k0=2*np.pi*p['Kvco'];kpd=p['Icp']/(2*np.pi)
        a=np.array([[s*p['C1']+1/r,-1/r,kpd/p['N']],[-1/r,s*p['C2']+1/r,0],[-k0,0,s]],complex)
        v,u,phi=np.linalg.solve(a,[1/r,-1/r,0])
        assert np.isclose(phi,transfers(c,[f])['resistor'][0],rtol=2e-12)


def test_zero_additivity_scaling_and_old_metrics(inputs):
    _,c,d=inputs;band=[1e4,1e6]
    zero=noise_mapping(c,d['noise_zero.json'],band)
    assert zero['integrated_jitter_s']==0
    assert zero['metrics']==evaluate(c).as_dict()['metrics']
    alln=noise_mapping(c,d['noise_all.json'],band)
    single=[noise_mapping(c,d['noise_'+sid+'.json'],band) for sid in ('reference','vco','cp','resistor')]
    assert np.isclose(sum(x['integrated_jitter_s']**2 for x in single),alln['integrated_jitter_s']**2,rtol=1e-14,atol=0)
    q=deepcopy(d['noise_cp.json']);q['sources'][0]['psd_values']['level']*=4
    assert noise_mapping(c,q,band)['integrated_jitter_s']==pytest.approx(2*single[2]['integrated_jitter_s'])


def test_sidedness_ssb_table_and_thermal(inputs):
    _,c,d=inputs;p=parse_parameters(c);src=deepcopy(d['noise_reference.json']['sources'][0]);f=[100,1000]
    src['unit']='dBc/Hz';src['psd_values']={'level':-100}
    assert np.allclose(source_psd(src,f,p['Rz']),2e-10,rtol=1e-12,atol=0)
    src['unit']='rad^2/Hz';src['psd_values']={'level':1e-10};src['one_sided_or_two_sided']='two_sided'
    assert np.allclose(source_psd(src,f,p['Rz']),2e-10,rtol=1e-12,atol=0)
    src.update(psd_type='table',frequency_range_Hz=[100,1000],one_sided_or_two_sided='one_sided',
               psd_values={'frequency_Hz':[100,1000],'psd':[1e-6,1e-8]})
    assert source_psd(src,[math.sqrt(1e5)],p['Rz'])[0]==pytest.approx(1e-7)
    r=d['noise_resistor.json']['sources'][0]
    assert source_psd(r,f,p['Rz'])[0]==4*K_B*300*p['Rz']


@pytest.mark.parametrize('mutation',[
    lambda p:p.update(independent_sources=False),lambda p:p['sources'][0].update(unit='V/sqrt(Hz)'),
    lambda p:p['sources'][0]['psd_values'].update(level=-1),lambda p:p['sources'][0]['psd_values'].update(level=float('inf')),
    lambda p:p['sources'][0].update(frequency_range_Hz=[0,1e6]),
    lambda p:p['sources'][0].update(injection_location='control_voltage')])
def test_invalid_rejected(inputs,mutation):
    _,c,d=inputs;p=deepcopy(d['noise_reference.json']);mutation(p)
    with pytest.raises(ValueError):noise_mapping(c,p,[1e4,1e6])


def test_no_extrapolation_or_singular_integral(inputs):
    _,c,d=inputs
    for band in ([0,1e6],[1e4,1e7]):
        with pytest.raises(ValueError):noise_mapping(c,d['noise_reference.json'],band)


def test_mesh_and_bandwidth_tradeoff(inputs):
    model,c,d=inputs;band=[1e4,1e6]
    a=noise_mapping(c,d['noise_all.json'],band,points=1025);b=noise_mapping(c,d['noise_all.json'],band,points=8193)
    assert abs(a['integrated_jitter_s']/b['integrated_jitter_s']-1)<2e-5
    # Gain increase widens BW: reference contribution increases, VCO contribution decreases.
    q=make_candidate(model,{'Icp':c['values']['Icp']['value']*1.1})
    assert evaluate(q).metrics['BW_Hz']>evaluate(c).metrics['BW_Hz']
    assert noise_mapping(q,d['noise_reference.json'],band)['integrated_jitter_s']>noise_mapping(c,d['noise_reference.json'],band)['integrated_jitter_s']
    assert noise_mapping(q,d['noise_vco.json'],band)['integrated_jitter_s']<noise_mapping(c,d['noise_vco.json'],band)['integrated_jitter_s']


def test_sensitivity_frozen_sources_and_discrete_caps(inputs):
    model,c,d=inputs;r=noise_sensitivity(model,c,d['noise_all.json'],[1e4,1e6])
    assert set(r['columns'])=={'Icp','Rz','Kvco','f0'}
    assert 'DISCRETE' in r['C1_C2']
    assert all('UNMODELED' in x['intrinsic_dependence'] for x in r['columns'].values())
    assert abs(r['columns']['f0']['transfer_log_elasticity']['integrated_jitter_s'])<1e-12


@pytest.mark.parametrize('name',['zero','K2_plus','K2_minus','mismatch_plus','mismatch_minus','reset','combined'])
def test_nonideal_static_contract(inputs,name):
    _,c,d=inputs;v=validate_nonideal(d['nonideal_'+name+'.json'],c)
    assert v['tuning_root_V']==pytest.approx(v['Vstar_V'],abs=1e-12)
    assert v['local_Kvco_Hz_per_V']>0


def test_independent_review_invalid_table_anchor_and_metadata(inputs):
    _,c,d=inputs;p=deepcopy(d['noise_reference.json'])
    p['sources'][0].update(psd_type='table',frequency_range_Hz=[1e4,1e6],
        psd_values={'frequency_Hz':[-1,1e4,1e6],'psd':[1e-13]*3})
    with pytest.raises(ValueError):noise_mapping(c,p,[1e4,1e6])
    q=deepcopy(d['nonideal_zero.json']);q['profile_id']=123
    with pytest.raises(ValueError):validate_nonideal(q,c)
