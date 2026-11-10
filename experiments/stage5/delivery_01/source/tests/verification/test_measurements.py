import ast
from copy import deepcopy
import json
import math
from pathlib import Path
import time
import numpy as np
import pytest
from pathlib import Path
FIXTURES = Path(__file__).resolve().parents[1]/"fixtures"
from pll_allocation.verification.resources import CONFIGS
from pll_allocation.verification.experiments import protocol as formal_protocol
def protocol():
    return __import__("json").loads((FIXTURES/"verification/protocol_v1_0.json").read_text(encoding="utf-8"))
from pll_allocation.verification.experiments import HERE,candidate,response_point
from pll_allocation.verification.measure import (bandwidth_from_response,capture_metrics,compare_transfers,
                     pm_identification_prototype,response_metrics)
from pll_allocation.verification.simulator import simulate


@pytest.mark.parametrize('overrides,initial',[({},.15),({'Icp':120e-6},.4),
    ({'C1':50e-12,'Rz':4500},.15),({'f0':68.01e6,'Kvco':10e6},.15)])
def test_native_unmodulated_equations_regress_existing_python(overrides,initial):
    source=FIXTURES/'verification/python_crosscheck.py'
    tree=ast.parse(source.read_text(encoding='utf-8'))
    fn=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='simulate']
    ns={'np':np,'math':math,'time':time}
    exec(compile(ast.Module(body=fn,type_ignores=[]),str(source),'exec'),ns)
    p=candidate(overrides);v={k:x['value'] for k,x in p['values'].items()}
    expected=ns['simulate'](sim_time=20e-6,dt=.4e-9,v0=initial,I=v['Icp'],R=v['Rz'],
        c1=v['C1'],c2=v['C2'],f0=v['f0'],kv=v['Kvco'],verbose=False)
    actual=simulate(p,duration_s=20e-6,dt_s=.4e-9,initial_control_V=initial,onset_s=20e-6)
    s=actual['summary']
    assert s['tail_frequency_Hz']==pytest.approx(expected['fout_avg'],abs=.01)
    assert s['tail_phase_rms_deg']==pytest.approx(expected['phase_rms_deg'],abs=1e-5)
    assert s['vfinal_V']==pytest.approx(expected['vfinal'],abs=1e-7)
    assert s['near_rail_samples']==expected['clip_count']


def test_steady_state_edges_and_divider_normalization():
    run=simulate(candidate(),duration_s=5e-6,dt_s=.4e-9,initial_control_V=.4,onset_s=5e-6)
    assert np.mean(np.diff(run['div_edges']))==pytest.approx(1e-7,abs=1e-14)
    assert run['summary']['actual_clamp_events']==0
    assert np.max(np.abs(run['trace'][:,1]))<1e-7


@pytest.mark.parametrize('bad',[
    {'dt_s':1e-6},{'initial_control_V':1.3},{'modulation_Hz':1e9,'phase_amplitude_rad':1},
    {'phase_amplitude_rad':.01,'modulation_Hz':1e6,'record_interval_s':1e-6},
    {'duration_s':float('nan')},
])
def test_invalid_numerical_conditions_fail_before_simulation(bad):
    with pytest.raises(ValueError):simulate(candidate(),**bad)


def test_complex_response_fit_recovers_known_gain_phase_independent_of_M1():
    cfg=protocol();f=100e3; dt=20e-9;t=np.arange(0,220e-6,dt)
    ref=.01*np.sin(2*math.pi*f*t)
    value=.8*np.exp(-.7j)
    y=.01*.8*np.sin(2*math.pi*f*t-.7)+.02+20*t
    # Offset and linear drift should not masquerade as sinusoidal response.
    trace=np.column_stack([t,y,ref,np.full(len(t),.4),np.full(len(t),.4),np.zeros(len(t))])
    run={'trace':trace,'settings':{'modulation_Hz':f,'onset_s':50e-6}}
    result=response_metrics(run,cfg,measurement_start_s=80e-6,measurement_end_s=200e-6)
    assert complex(*result['T_complex'])==pytest.approx(value,abs=1e-9)
    assert result['quality']['harmonic_distortion']<1e-8


def test_missing_crossing_and_bad_point_not_accepted():
    points=[{'frequency_Hz':f,'status':'MEASURED','magnitude':m} for f,m in [(1,1),(2,.95),(3,.9)]]
    assert bandwidth_from_response(points)['status']=='UNKNOWN'
    points[-1]['magnitude']=.5
    measured=bandwidth_from_response(points)
    assert measured['status']=='MEASURED_BRACKETED'
    assert measured['bracket_Hz']==[2,3]


def test_PM_inversion_prototype_never_claims_independent_measurement():
    points=[{'frequency_Hz':1e5,'status':'MEASURED','T_complex':[.8,-.3]},
            {'frequency_Hz':2e5,'status':'MEASURED','T_complex':[.2,-.4]}]
    result=pm_identification_prototype(points)
    assert result['status']=='PM_M2_UNKNOWN'
    assert result['independent_PM_deg'] is None
    assert len(result['obstacles'])>=2


def test_window_capture_failure_is_not_absolute_nonlockability():
    run=simulate(candidate({'f0':60e6,'Kvco':10e6}),duration_s=30e-6,onset_s=30e-6)
    result=capture_metrics(run,protocol())
    assert result['status']=='NOT_CAPTURED_WITHIN_WINDOW'
    assert result['lock_time_s'] is None
    assert result['finite_window_not_absolute_nonlockability'] is True


def test_output_refuses_overwrite(tmp_path):
    folder=tmp_path/'point';folder.mkdir()
    with pytest.raises(FileExistsError):response_point(folder,candidate(),200e3)


def test_simulation_measurement_modules_do_not_use_M1_transfers():
    for name in ('kernel.cpp','measure.py','simulator.py'):
        text=(HERE/name).read_text(encoding='utf-8')
        assert 'M1Evaluator' not in text and 'polynomial_reference' not in text
        if name.endswith('.py'):
            tree=ast.parse(text)
            assert not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='_response'
                           for n in ast.walk(tree))
