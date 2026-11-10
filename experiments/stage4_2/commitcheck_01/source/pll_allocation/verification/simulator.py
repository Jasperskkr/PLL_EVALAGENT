"""Observation/stimulus adapter to isolated original edge/Euler equations. No M1 imports."""
import ctypes
import hashlib
import math
from pathlib import Path
from .resources import CONFIGS
import time
import numpy as np

HERE=Path(__file__).resolve().parent
MODEL_VERSION='edge_euler_observed_phase_input_1.0'


def validate_parameters(envelope):
    # Share the existing parameter semantics, never redefine a second BlockSpec.
    import sys
    from pll_allocation.physics_mapping.model import parse_parameters
    return parse_parameters(envelope)


def simulate(parameters, *, duration_s=160e-6, dt_s=.4e-9, initial_control_V=.15,
             phase_amplitude_rad=0., modulation_Hz=0., onset_s=50e-6, record_interval_s=20e-9):
    p=validate_parameters(parameters)
    if p['f_ref']!=10e6 or p['N']!=8 or p['Vctrl_min']!=0 or p['Vctrl_max']!=1.2:
        raise ValueError('UNSUPPORTED: Track B protocol fixes 10MHz x 8 and 0..1.2V rails')
    if any(type(x) not in (int,float) or not math.isfinite(x) for x in
            (duration_s,dt_s,initial_control_V,phase_amplitude_rad,modulation_Hz,onset_s,record_interval_s)):
        raise ValueError('finite simulation settings required')
    if (not 0<dt_s<duration_s or record_interval_s<dt_s or not p['Vctrl_min']<=initial_control_V<=p['Vctrl_max']
            or not 0<=onset_s<=duration_s or phase_amplitude_rad<0 or modulation_Hz<0):
        raise ValueError('invalid time, voltage or stimulus domain')
    fmax=p['f0']+p['Kvco']*p['Vctrl_max']
    rate=(p['C1']+p['C2'])/(p['Rz']*p['C1']*p['C2'])
    if dt_s*rate>.05 or dt_s*max(p['f_ref'],fmax/p['N'])>.02:
        raise ValueError('step violates edge/Euler resolution domain')
    if phase_amplitude_rad*modulation_Hz>=p['f_ref']:
        raise ValueError('nonmonotonic phase stimulus')
    if phase_amplitude_rad and (not modulation_Hz or record_interval_s*modulation_Hz>.05):
        raise ValueError('insufficient waveform sampling')
    library=HERE/'build/kernel.dll'
    if not library.is_file():
        raise RuntimeError('native event backend unavailable: run build_kernel.cmd; no fabricated fallback')
    n=math.ceil(duration_s/dt_s)+1
    stride=max(1,int(record_interval_s/(duration_s/(n-1))))
    count=(n-1)//stride+2
    edgecap=math.ceil(duration_s*max(p['f_ref'],fmax/p['N']))+10
    trace=np.empty((count,6),dtype=np.float64)
    ref=np.empty(edgecap,dtype=np.float64); div=np.empty_like(ref)
    stats=np.empty(13,dtype=np.float64)
    values=np.array([p['f_ref'],p['N'],p['Icp'],p['Rz'],p['C1'],p['C2'],p['f0'],p['Kvco'],
        p['Vctrl_min'],p['Vctrl_max'],initial_control_V,duration_s,dt_s,phase_amplitude_rad,
        modulation_Hz,onset_s,record_interval_s],dtype=np.float64)
    from .build_identity import check_build
    check_build()
    lib=ctypes.CDLL(str(library)); fn=lib.simulate
    ptr=ctypes.POINTER(ctypes.c_double)
    fn.argtypes=[ptr,ptr,ctypes.c_longlong,ptr,ptr,ctypes.c_longlong,ptr]
    fn.restype=ctypes.c_int
    start=time.perf_counter()
    code=fn(values.ctypes.data_as(ptr),trace.ctypes.data_as(ptr),count,
        ref.ctypes.data_as(ptr),div.ctypes.data_as(ptr),edgecap,stats.ctypes.data_as(ptr))
    if code:
        raise RuntimeError('event backend domain/numerical failure code '+str(code))
    settings=dict(duration_s=duration_s,requested_dt_s=dt_s,actual_dt_s=float(stats[1]),
        initial_control_V=initial_control_V,phase_amplitude_rad=phase_amplitude_rad,modulation_Hz=modulation_Hz,
        onset_s=onset_s,record_interval_s=record_interval_s)
    return {'trace':trace[:int(stats[2])].copy(),'ref_edges':ref[:int(stats[10])].copy(),
        'div_edges':div[:int(stats[11])].copy(),'settings':settings,
        'summary':{'integration_points':int(stats[0]),'actual_clamp_events':int(stats[3]),
            'near_rail_samples':int(stats[4]),'tail_frequency_Hz':float(stats[5]),
            'tail_phase_mean_deg':float(stats[6]),'tail_phase_rms_deg':float(stats[7]),
            'vfinal_V':float(stats[8]),'vc2_final_V':float(stats[9]),'elapsed_s':time.perf_counter()-start,
            'kernel_sha256':hashlib.sha256((HERE/'kernel.cpp').read_bytes()).hexdigest(),
            'library_sha256':hashlib.sha256(library.read_bytes()).hexdigest(),'model_version':MODEL_VERSION}}
