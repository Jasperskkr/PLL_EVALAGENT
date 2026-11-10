"""Optional original event-kernel extension. No M1 transfer/noise waveform imports."""
import ctypes
import hashlib
import math
from pathlib import Path
import time
import numpy as np
from ..block_space.extensions import validate_noise,validate_nonideal,source_psd
from .simulator import validate_parameters,simulate as ideal_simulate
from .stage6c_identity import check_build,default_build

HERE=Path(__file__).resolve().parent
MODEL_ID='cppll-fixed-grid-nonideal-stochastic-1.0'
RNG_ID='SplitMix64_BoxMuller_1.0_separate_source_streams'


def noise_levels(profile,p):
    """Allowed process definitions only; M1's 1/f^3/table remain UNSUPPORTED here."""
    if profile is None:return dict(reference=0.,vco=0.,cp=0.,resistor=0.)
    profile=validate_noise(profile);out=dict(reference=0.,vco=0.,cp=0.,resistor=0.)
    for src in profile['sources']:
        sid=src['source_id'];typ=src['psd_type']
        if sid=='vco':
            if typ!='power_law' or src['psd_values']['exponent']!=-2:
                raise ValueError('UNSUPPORTED: M2 VCO requires 1/f^2 from white frequency noise')
            out[sid]=float(source_psd(src,[max(1.,src['frequency_range_Hz'][0])],p['Rz'])[0])*max(1.,src['frequency_range_Hz'][0])**2
        else:
            if typ!='white' and not (sid=='resistor' and typ=='thermal'):raise ValueError('UNSUPPORTED: M2 requires white sources/thermal R')
            out[sid]=float(source_psd(src,[max(1.,src['frequency_range_Hz'][0])],p['Rz'])[0])
    return out


def simulate(candidate,nonideal,noise=None,*,seed=11,noise_onset_s=200e-6,
             duration_s=160e-6,dt_s=.4e-9,initial_control_V=.15,phase_amplitude_rad=0.,
             modulation_Hz=0.,onset_s=50e-6,record_interval_s=20e-9,cp_gated_psd=None,build_dir=None,phase_end_s=None):
    p=validate_parameters(candidate);derived=validate_nonideal(nonideal,candidate);level=noise_levels(noise,p)
    if p['f_ref']!=1e7 or p['N']!=8 or p['Vctrl_min']!=0 or p['Vctrl_max']!=1.2:raise ValueError('UNSUPPORTED: frequency plan/rails')
    if type(seed)is not int or not 0<=seed<2**64:raise ValueError('OUT_OF_DOMAIN: uint64 seed')
    settings=dict(duration_s=duration_s,dt_s=dt_s,initial_control_V=initial_control_V,
        phase_amplitude_rad=phase_amplitude_rad,modulation_Hz=modulation_Hz,onset_s=onset_s,record_interval_s=record_interval_s)
    if any(type(x)not in (float,int) or not math.isfinite(x) for x in [*settings.values(),noise_onset_s]):raise ValueError('finite simulation settings')
    if not 0<dt_s<duration_s or not dt_s<=record_interval_s or not 0<=initial_control_V<=1.2 or not 0<=onset_s<=duration_s or noise_onset_s<0:
        raise ValueError('OUT_OF_DOMAIN: settings')
    if phase_amplitude_rad<0 or modulation_Hz<0 or phase_amplitude_rad*modulation_Hz>=p['f_ref']:raise ValueError('OUT_OF_DOMAIN: stimulus')
    if phase_amplitude_rad and (not modulation_Hz or record_interval_s*modulation_Hz>.05):raise ValueError('OUT_OF_DOMAIN: waveform resolution')
    if phase_end_s is not None:
        if (type(phase_end_s)not in (int,float) or not math.isfinite(phase_end_s) or not onset_s<phase_end_s<=duration_s
            or not modulation_Hz or abs((phase_end_s-onset_s)*modulation_Hz-round((phase_end_s-onset_s)*modulation_Hz))>1e-8):
            raise ValueError('OUT_OF_DOMAIN: continuous integer-cycle stimulus ending')
    gated={'up_A2_per_Hz':0.,'down_A2_per_Hz':0.} if cp_gated_psd is None else cp_gated_psd
    if set(gated)!={'up_A2_per_Hz','down_A2_per_Hz'} or any(type(x)not in (float,int) or not math.isfinite(x) or x<0 for x in gated.values()):
        raise ValueError('OUT_OF_DOMAIN: explicit gated UP/DOWN PSD')
    if level['cp'] and any(gated.values()):raise ValueError('UNSUPPORTED: effective/gated CP double counting')
    mechanisms=('K2_Hz_per_V2','cp_mismatch','leakage_A','reset_delay_s','cp_voltage_coefficient_per_V')
    if all(nonideal[k]==0 for k in mechanisms) and not any(level.values()) and not any(gated.values()) and phase_end_s is None:
        run=ideal_simulate(candidate,**settings)
        run['extension']={'model_id':MODEL_ID,'active':False,'original_direct_dispatch':True,'derived':derived}
        return run
    vmax=p['Vctrl_max'];fmax=p['f0']+p['Kvco']*vmax+nonideal['K2_Hz_per_V2']*vmax*(vmax-derived['Vstar_V'])
    rate=(p['C1']+p['C2'])/(p['Rz']*p['C1']*p['C2'])
    if dt_s*rate>.05 or dt_s*max(p['f_ref'],fmax/8)>.02:raise ValueError('OUT_OF_DOMAIN: edge/Euler resolution')
    n=math.ceil(duration_s/dt_s)+1;actual=duration_s/(n-1);stride=max(1,int(record_interval_s/actual));count=(n-1)//stride+2
    # Reference noise can add/advance only small timing perturbations; backend rejects illegal edges.
    edgecap=math.ceil(duration_s*max(p['f_ref'],fmax/8)*1.05)+32
    trace=np.empty((count,28));ref=np.empty(edgecap);div=np.empty_like(ref);stats=np.empty(25)
    values=np.array([p['f_ref'],p['N'],p['Icp'],p['Rz'],p['C1'],p['C2'],p['f0'],p['Kvco'],0.,1.2,
        initial_control_V,duration_s,dt_s,phase_amplitude_rad,modulation_Hz,onset_s,record_interval_s],float)
    q=np.array([nonideal[k] for k in mechanisms]+[noise_onset_s,math.sqrt(level['reference']*p['f_ref']/2),
        level['vco'],level['cp'],level['resistor'],gated['up_A2_per_Hz'],gated['down_A2_per_Hz'],
        duration_s+dt_s if phase_end_s is None else phase_end_s],float)
    build=Path(build_dir).resolve() if build_dir is not None else default_build();identity=check_build(build)
    lib=ctypes.CDLL(str(build/'kernel.dll'));fn=lib.simulate_nonideal;ptr=ctypes.POINTER(ctypes.c_double)
    fn.argtypes=[ptr,ptr,ctypes.c_uint64,ptr,ctypes.c_longlong,ptr,ptr,ctypes.c_longlong,ptr];fn.restype=ctypes.c_int
    start=time.perf_counter();code=fn(values.ctypes.data_as(ptr),q.ctypes.data_as(ptr),seed,
        trace.ctypes.data_as(ptr),count,ref.ctypes.data_as(ptr),div.ctypes.data_as(ptr),edgecap,stats.ctypes.data_as(ptr))
    elapsed=time.perf_counter()-start
    if code:raise RuntimeError('STAGE6C_NATIVE_FAILURE:'+str(code)+'; elapsed_s='+str(elapsed)+'; requested_points='+str(n))
    trace=trace[:int(stats[2])].copy();ref=ref[:int(stats[10])].copy();div=div[:int(stats[11])].copy()
    if not np.isfinite(trace).all() or np.any(np.diff(ref)<=0) or np.any(np.diff(div)<=0):raise RuntimeError('STAGE6C_INVALID_TRACE_OR_EDGES')
    summary={'integration_points':int(stats[0]),'actual_clamp_events':int(stats[3]),'near_rail_samples':int(stats[4]),
        'tail_frequency_Hz':float(stats[5]),'tail_phase_mean_deg':float(stats[6]),'tail_phase_rms_deg':float(stats[7]),
        'vfinal_V':float(stats[8]),'vc2_final_V':float(stats[9]),'elapsed_s':elapsed,'model_version':MODEL_ID,
        'kernel_sha256':identity['sha256']['pll_allocation/verification/stage6c_kernel.cpp'],
        'library_sha256':hashlib.sha256((build/'kernel.dll').read_bytes()).hexdigest()}
    diagnostics=dict(zip(['input_charge_C','clamp_charge_C','branch_charge_C','up_on_time_s','down_on_time_s',
        'up_noise_charge_C','down_noise_charge_C','effective_cp_noise_charge_C','R_noise_branch_charge_C',
        'vco_noise_phase_rad','reset_count','capacitor_charge_change_C'],map(float,stats[13:])))
    diagnostics['charge_balance_residual_C']=diagnostics['capacitor_charge_change_C']-diagnostics['input_charge_C']-diagnostics['clamp_charge_C']
    return {'trace':trace[:,:6].copy(),'extended_trace':trace,'ref_edges':ref,'div_edges':div,
        'settings':{**settings,'requested_dt_s':dt_s,'actual_dt_s':float(stats[1]),'seed':seed,'noise_onset_s':noise_onset_s,'phase_end_s':phase_end_s},
        'summary':summary,'extension':{'model_id':MODEL_ID,'active':True,'derived':derived,'noise_levels':level,
            'rng':RNG_ID,'cp_model':'GATED_UP_DOWN' if any(gated.values()) else 'CONTINUOUS_EFFECTIVE',
            'diagnostics':diagnostics,'build_identity':identity}}
