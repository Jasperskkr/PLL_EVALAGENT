"""Steady stochastic tracking diagnostics, separate from frozen cold-capture metric."""
import math
import numpy as np
from .measure import capture_metrics


def terminal_capture(run,protocol,window_s=160e-6):
    """Exact terminal original blocks, cheap suffix only; NEVER use this lock_time.

    Absolute timestamps preserved so original one-us block membership is identical.
    Earliest capture/early-recapture labels can differ; only terminal CAPTURED boolean
    and terminal metrics are used. Full observation slips/clamps checked separately.
    """
    trace=run['trace'];start=trace[-1,0]-window_s
    # Include preceding block-boundary tolerance from original capture mask.
    suffix=trace[np.searchsorted(trace[:,0],start-2e-15):]
    result=capture_metrics({**run,'trace':suffix},protocol)
    return {'terminal_captured':result['status']=='CAPTURED_WITHIN_WINDOW',
            'output_frequency_Hz':result['output_frequency_Hz'],'steady_control_V':result['steady_control_V'],
            'terminal_phase_error_peak_deg':result['terminal_phase_error_peak_deg'],
            'net_cycle_index':result['net_cycle_index'],'hold_window_s':result['hold_window_s'],
            'terminal_blocks':result['blocks'][-protocol['capture']['hold_blocks']:],
            'lock_time_s':None,'scope':'TERMINAL_DIAGNOSTIC_ONLY_NO_CAPTURE_TIME'}


def steady_tracking(run,noise_protocol,capture_protocol):
    """Finite declared observation evidence, no global/periodic stability claim.

    Existing deterministic capture is a required BEFORE-noise gate. White frequency
    noise has nonzero one-us frequency variance, so that deterministic per-block
    frequency inequality is recorded, not used as stochastic loss-of-lock identity.
    """
    q=noise_protocol
    if q.get('protocol_id')!='pll-noise-verification-1.1':raise ValueError('UNSUPPORTED: explicit tracking protocol1.1 required')
    trace=np.asarray(run['trace']);end=q['warmup_s']+q.get('noise_settle_s',0.)+q['observation_s']
    if (trace.ndim!=2 or trace.shape[1]<6 or len(trace)<10 or not np.isfinite(trace).all()
        or not np.all(np.diff(trace[:,0])>0)):
        return {'status':'UNKNOWN','reason':'nonfinite, unordered or malformed trace'}
    nominal=q['record_interval_s'];delta=np.diff(trace[:,0]);actual=float(np.median(delta))
    # The original kernel may append a partial final record; PSD interval excludes it.
    if (trace[0,0]>q['warmup_s']+nominal or trace[-1,0]<end-nominal
        or actual>nominal*1.01 or np.any(delta[:-1]>actual*(1+1e-7))
        or np.any(delta[:-1]<actual*(1-1e-7)) or delta[-1]>actual*(1+1e-7)):
        return {'status':'UNKNOWN','reason':'incomplete observation or invalid record sampling'}
    keep=(trace[:,0]>=q['warmup_s'])&(trace[:,0]<end);z=trace[keep]
    if len(z)<10:return {'status':'UNKNOWN','reason':'insufficient observation'}
    t=z[:,0];error=z[:,2]-z[:,1];branch=np.floor((error+np.pi)/(2*np.pi));wrapped=error-2*np.pi*branch
    phase=float(np.max(np.abs(wrapped))*180/np.pi);slips=int(np.sum(np.abs(np.diff(branch))))
    clamps=int(round(z[-1,5]-z[0,5]));half=[]
    for sub in (z[:len(z)//2],z[len(z)//2:]):
        half.append(float(8*(sub[-1,1]-sub[0,1])/(2*np.pi*(sub[-1,0]-sub[0,0]))/80e6*1e6))
    cfg=capture_protocol['capture'];block=cfg['block_reference_cycles']/1e7
    first=int(math.ceil(t[0]/block));last=int(math.floor(t[-1]/block));maxrange=0.
    # Same interpolation/membership as the original block diagnostic, batch once.
    boundaries=np.arange(first,last+1,dtype=float)*block
    phases=np.interp(boundaries,np.ascontiguousarray(t),np.ascontiguousarray(z[:,1]))
    frequencies=8*np.diff(phases)/(2*np.pi*block)/80e6*1e6
    oldfreqfail=int(np.sum(np.abs(frequencies)>cfg['block_frequency_error_limit_ppm']))
    left=np.searchsorted(t,boundaries[:-1]-1e-15);right=np.searchsorted(t,boundaries[1:]+1e-15,side='right')
    for i,j in zip(left,right):
        v=z[i:j,3]
        if len(v)>=4:maxrange=max(maxrange,float(np.ptp(v)))
    no_rails=bool(np.all((z[:,3]>0)&(z[:,3]<1.2)))
    checks={'no_cycle_slips':slips==0,'no_clamps':clamps==0,'interior_control':no_rails,
        'phase_bound':phase<=cfg['peak_phase_error_limit_deg'],'control_block_range':maxrange<=cfg['block_control_range_limit_V'],
        'halfwindow_mean_frequency':max(map(abs,half))<=cfg['block_frequency_error_limit_ppm']}
    return {'status':'PASS_CONDITIONAL_OBSERVATION' if all(checks.values()) else 'UNKNOWN','checks':checks,
        'wrapped_divided_phase_peak_deg':phase,'cycle_slips':slips,'clamps':clamps,'max_control_block_range_V':maxrange,
        'halfwindow_mean_frequency_error_ppm':half,'deterministic_1us_frequency_bound_failures_diagnostic':int(oldfreqfail),
        'source':'ACTUAL_NOISY_TRAJECTORY','protocol_id':q['protocol_id'],'strict_periodic_PM_status':'UNKNOWN',
        'scope':'declared finite condition/window, not global stability or exact tail-probability bound'}
