"""Extension boundaries, no invented native evidence; synthetic fixtures labeled."""
from copy import deepcopy
import json
from pathlib import Path
import pytest
from pll_allocation.pipeline_contracts import load_inputs
from pll_allocation.allocation.allocate import analytical
from pll_allocation.allocation.core import Meter,assess_m1
from pll_allocation.allocation.multispec_constraints import validate_problem,evaluate_constraints,objective_key
from pll_allocation.block_space.contracts import check_parameters
from pll_allocation.physics_mapping.model import fingerprint
from pll_allocation.physics_mapping.noise import noise_mapping,optimizer_noise_estimate
ROOT=Path(__file__).resolve().parents[1]


def inputs():
    config,model,spec,protocol=load_inputs();p=json.loads((ROOT/'configs/stage6c/joint_frozen_01/J0_ideal.json').read_text())
    meter=Meter(10000,96);c,_=analytical(model,p['research_system_spec'],meter);a=assess_m1(model,p['research_system_spec'],c,meter)
    return config,model,spec,protocol,p,c,a


def synthetic(c,a,p,jitter_status='STATISTICALLY_RESOLVED_CONDITIONAL',jitter_interval=None):
    """Contract test fixture only. No native M2 evidence or physical experiment."""
    bw=a['prediction']['metrics']['BW_Hz'];ji=jitter_interval or [50e-12,60e-12]
    return dict(parameter_sha256=fingerprint(c),overall_status='UNKNOWN',validation_level='M2_PARTIAL_INDEPENDENT_METRICS',
        extension={'profile_hashes':p['behavioral_extension']['source_profile_hashes'],
            'noise_result':{'status':jitter_status,'all_observations_locked':True,'integrated_jitter_s':sum(ji)/2,'jitter_interval_s':ji}},
        metrics={'BW_Hz':{'value':bw,'status':'MEASURED_CONVERGED','numerical_envelope':[bw-1,bw+1]},
            'capture':{'value':'CAPTURED_WITHIN_WINDOW','initial_control_V':.15,'duration_s':160e-6},
            'lock_time_s':{'value':33e-6,'status':'MEASURED_WINDOW_CONDITIONAL','step_difference_s':0.,'resolution_s':1e-6},
            'integrated_jitter_s':{'value':sum(ji)/2,'status':jitter_status,'statistical_interval_s':ji},
            'nonlinear_recovery_status':{'value':'PASS_CONDITIONAL_FINITE_WINDOW'}},
        reliability={'capture_step_converged':True,'BW_converged':True})


def test_versioned_joint_contract_and_fixed_profile():
    cfg,m,s,pro,p,c,a=inputs();assert validate_problem(p,cfg,m,s,pro)==p
    q=deepcopy(p);q['behavioral_extension']['noise_profile']['sources'][0]['psd_values']['level']*=2
    with pytest.raises(ValueError):validate_problem(q,cfg,m,s,pro)


@pytest.mark.parametrize('interval,expected',[([50e-12,60e-12],'RESEARCH_JOINT_FEASIBLE'),([110e-12,120e-12],'FAIL'),([90e-12,110e-12],'UNKNOWN')])
def test_all_hard_constraints_and_statistics(interval,expected):
    _,m,_,_,p,c,a=inputs();r=evaluate_constraints(m,p,c,a,synthetic(c,a,p,jitter_interval=interval))
    assert r['research_joint_status']==expected
    j=next(x for x in r['constraints'] if x['metric_name']=='integrated_jitter_s')
    assert j['statistical_interval']==interval and j['numerical_envelope'] is None
    assert r['strict_periodic_PM_status']=='UNKNOWN' and not r['FULL_SYSTEMSPEC_CERTIFIED']
    assert all(x['noise_profile_id'] and x['nonideal_profile_id'] and x['unit'] and x['evidence_path'] for x in r['constraints'])


def test_unresolved_or_wrong_binding_never_passes():
    _,m,_,_,p,c,a=inputs();bad=synthetic(c,a,p,jitter_status='UNKNOWN')
    assert evaluate_constraints(m,p,c,a,bad)['research_joint_status']=='UNKNOWN'
    bad=synthetic(c,a,p);bad['extension']['profile_hashes']={}
    with pytest.raises(ValueError):evaluate_constraints(m,p,c,a,bad)


def test_feasibility_has_priority_over_improved_other_metrics():
    _,m,_,_,p,c,a=inputs();good=evaluate_constraints(m,p,c,a,synthetic(c,a,p))
    bad=synthetic(c,a,p,jitter_interval=[110e-12,120e-12]);bad['metrics']['lock_time_s']['value']=1e-6
    fail=evaluate_constraints(m,p,c,a,bad)
    assert objective_key(good,p['objective'])<objective_key(fail,p['objective'])


def test_fast_optimizer_noise_mesh_matches_full_mapping():
    _,m,_,_,p,c,a=inputs();ext=p['behavioral_extension'];raw={k:v['value'] for k,v in c['values'].items()}
    cheap=optimizer_noise_estimate(raw,ext['noise_profile'],ext['noise_protocol']['band_Hz'])
    full=noise_mapping(c,ext['noise_profile'],ext['noise_protocol']['band_Hz'])
    assert cheap==pytest.approx(full['integrated_jitter_s'],rel=1e-4)


@pytest.mark.parametrize('kind',['negative','nan','outside','underlying_unknown'])
def test_bad_statistical_evidence_never_feasible(kind):
    _,m,_,_,p,c,a=inputs();bad=synthetic(c,a,p)
    j=bad['metrics']['integrated_jitter_s']
    if kind=='negative':j.update(value=-1.5e-11,statistical_interval_s=[-2e-11,-1e-11])
    elif kind=='nan':j['value']=float('nan')
    elif kind=='outside':j['value']=1e-9
    else:bad['extension']['noise_result']['status']='UNKNOWN'
    assert evaluate_constraints(m,p,c,a,bad)['research_joint_status']!='RESEARCH_JOINT_FEASIBLE'


def test_generated_solver_is_original_with_only_margin_hook():
    import inspect
    from pll_allocation.allocation.noise_optimization import generated_source
    from pll_allocation.allocation.allocate import optimize
    a=inspect.getsource(optimize);b=generated_source()
    assert b.count('extra=extra_margin(p,prediction)')==1
    assert 'extra_margin' not in a and 'scipy.optimize.SLSQP' in b
