"""Trajectory/edge based extraction. No M1 import or transfer formula in measurements."""
import math
import numpy as np


def capture_metrics(run, protocol):
    cfg=protocol['capture']; trace=run['trace']; t=trace[:,0]
    period=1e-7; block=cfg['block_reference_cycles']*period
    count=int((t[-1]+1e-15)//block)
    records=[]
    for k in range(count):
        a,b=k*block,(k+1)*block
        keep=(t>=a-1e-15)&(t<=b+1e-15)
        z=trace[keep]
        if len(z)<4: continue
        ya,yb=np.interp([a,b],t,trace[:,1])
        freq=80e6+8*(yb-ya)/(2*math.pi*block)
        e=z[:,2]-z[:,1]
        wraps=np.floor((e+math.pi)/(2*math.pi))
        circular=cfg.get('phase_lock_reference')=='nearest_integer_cycle_with_no_terminal_slips'
        evaluated_error=e-2*math.pi*wraps if circular else e
        phasepeak=float(np.max(np.abs(evaluated_error))*180/math.pi)
        clamps=float(np.interp(b,t,trace[:,5])-np.interp(a,t,trace[:,5]))
        vrange=float(np.ptp(z[:,3])); meanv=float(np.mean(z[:,3]))
        okay=(abs((freq-80e6)/80e6*1e6)<=cfg['block_frequency_error_limit_ppm']
            and phasepeak<=cfg['peak_phase_error_limit_deg'] and vrange<=cfg['block_control_range_limit_V']
            and clamps==0 and np.max(wraps)==np.min(wraps) and (circular or wraps[0]==0))
        records.append({'start_s':a,'end_s':b,'frequency_Hz':freq,'control_mean_V':meanv,
            'phase_error_peak_deg':phasepeak,'control_range_V':vrange,'actual_clamps':int(round(clamps)),
            'cycle_index':int(wraps[-1]),'valid_tracking_block':bool(okay)})
    lastbad=max((i for i,x in enumerate(records) if not x['valid_tracking_block']),default=-1)
    tail=records[-cfg['hold_blocks']:]
    locked=len(records)-lastbad-1>=cfg['hold_blocks']
    locktime=records[lastbad+1]['start_s'] if locked else None
    freq=float(np.mean([x['frequency_Hz'] for x in tail])) if tail else None
    voltage=float(np.mean([x['control_mean_V'] for x in tail])) if tail else None
    # Explicit phase-slope estimate over the same terminal hold window.
    if tail:
        a,b=tail[0]['start_s'],tail[-1]['end_s']
        y0,y1=np.interp([a,b],t,trace[:,1])
        freq=80e6+8*(y1-y0)/(2*math.pi*(b-a))
    early=any(all(x['valid_tracking_block'] for x in records[i:i+cfg['hold_blocks']])
              for i in range(max(0,len(records)-cfg['hold_blocks']+1)))
    return {'status':'CAPTURED_WITHIN_WINDOW' if locked else 'LOST_LOCK_WITHIN_WINDOW' if early else 'NOT_CAPTURED_WITHIN_WINDOW',
        'output_frequency_Hz':freq,'steady_control_V':voltage,'lock_time_s':locktime,
        'lock_time_status':'MEASURED_WINDOW_CONDITIONAL' if locked else 'UNKNOWN',
        'actual_clamp_events':run['summary']['actual_clamp_events'],
        'phase_lock_reference':cfg.get('phase_lock_reference','absolute_unwrapped_phase_v1_0'),
        'net_cycle_index':records[-1]['cycle_index'] if records else None,
        'startup_cycle_slips_do_not_preclude_terminal_lock':circular,
        'terminal_phase_error_peak_deg':max((x['phase_error_peak_deg'] for x in tail),default=None),
        'hold_window_s':cfg['hold_blocks']*block,'blocks':records,
        'finite_window_not_absolute_nonlockability':True}


def _fit(t,y,frequency):
    w=2*math.pi*frequency*t
    trend=(t-np.mean(t))/(t[-1]-t[0])
    matrix=np.column_stack([np.ones(len(t)),trend]+[x for h in (1,2,3) for x in (np.sin(h*w),np.cos(h*w))])
    coeff,_,rank,_=np.linalg.lstsq(matrix,y,rcond=None)
    if rank!=8: raise ValueError('rank deficient sinusoid fit')
    phasors=[complex(coeff[3+2*i],-coeff[2+2*i]) for i in range(3)]
    residual=float(np.sqrt(np.mean((y-matrix@coeff)**2)))
    return phasors,residual


def response_metrics(run, protocol, *, measurement_start_s, measurement_end_s):
    cfg=protocol['frequency_response']; trace=run['trace']; f=run['settings']['modulation_Hz']
    keep=(trace[:,0]>=measurement_start_s)&(trace[:,0]<measurement_end_s)
    z=trace[keep]; t=z[:,0]
    if len(t)<100 or (t[-1]-t[0])*f<cfg['measurement_cycles']-.1:
        return {'status':'UNKNOWN','reason':'insufficient independent cycles/window'}
    if not np.isfinite(z).all() or np.any(np.diff(t)<=0):
        return {'status':'UNKNOWN','reason':'nonfinite or unordered trace'}
    if 1/(np.max(np.diff(t))*f)<cfg['minimum_samples_per_period']:
        return {'status':'UNKNOWN','reason':'insufficient samples per period'}
    output,residual=_fit(t,z[:,1],f); inp,_=_fit(t,z[:,2],f)
    if abs(inp[0])<1e-8: return {'status':'UNKNOWN','reason':'input excitation too small'}
    transfer=output[0]/inp[0]
    thd=math.sqrt(abs(output[1])**2+abs(output[2])**2)/max(abs(output[0]),1e-15)
    halves=[]
    for subset in (z[:len(z)//2],z[len(z)//2:]):
        o,_=_fit(subset[:,0],subset[:,1],f); r,_=_fit(subset[:,0],subset[:,2],f)
        halves.append(o[0]/r[0])
    delta=abs(halves[1]-halves[0])/max(abs(transfer),1e-15)
    clips=int(round(z[-1,5]-z[0,5])); e=z[:,2]-z[:,1]
    pre=trace[(trace[:,0]>=run['settings']['onset_s']-10e-6)&(trace[:,0]<run['settings']['onset_s'])]
    pre_locked=bool(len(pre)>100 and np.max(np.abs(pre[:,2]-pre[:,1]))<math.radians(5))
    ratios={'harmonic_distortion':thd,'half_window_relative_difference':delta,
            'residual_to_fundamental_ratio':residual/max(abs(output[0]),1e-15),
            'unwrapped_error_peak_rad':float(np.max(np.abs(e))),'clamps_in_measurement':clips,
            'pre_injection_locked':pre_locked,'samples_per_period':1/(np.median(np.diff(t))*f)}
    failures=[]
    for key,limit in [('harmonic_distortion',cfg['max_harmonic_distortion']),
                      ('half_window_relative_difference',cfg['max_half_window_transfer_relative_difference']),
                      ('residual_to_fundamental_ratio',cfg['max_residual_to_fundamental_ratio']),
                      ('unwrapped_error_peak_rad',cfg['max_unwrapped_error_peak_rad'])]:
        if ratios[key]>limit: failures.append(key)
    if clips or not pre_locked: failures.append('clipped_or_not_locked')
    return {'status':'MEASURED' if not failures else 'UNKNOWN','reasons':failures,
        'frequency_Hz':f,'T_complex':[transfer.real,transfer.imag],'magnitude':abs(transfer),
        'phase_deg':math.degrees(np.angle(transfer)), 'quality':ratios,
        'input_phase_amplitude_rad':abs(inp[0]),'output_divided_phase_amplitude_rad':abs(output[0]),
        'input_normalization':'phi_out/N divided by phi_ref; already normalized; no extra N multiplier',
        'measurement_window_s':[measurement_start_s,measurement_end_s]}


def compare_transfers(a,b):
    if a['status']!='MEASURED' or b['status']!='MEASURED':
        return {'status':'UNKNOWN'}
    x,y=complex(*a['T_complex']),complex(*b['T_complex'])
    return {'status':'COMPARED','relative_complex_difference':abs(y-x)/max(abs(y),1e-15),
            'phase_difference_deg':abs(math.degrees(np.angle(y/x)))}


def bandwidth_from_response(points):
    valid=sorted([p for p in points if p['status']=='MEASURED'],key=lambda p:p['frequency_Hz'])
    if len(valid)<3 or abs(valid[0]['magnitude']-1)>.03:
        return {'status':'UNKNOWN','reason':'no measured near-unity low-frequency anchor'}
    threshold=2**-.5
    pairs=[(a,b) for a,b in zip(valid,valid[1:]) if a['magnitude']>threshold>=b['magnitude']]
    if len(pairs)!=1: return {'status':'UNKNOWN','reason':'no unique measured downward BW crossing'}
    a,b=pairs[0]; y0,y1=math.log(a['magnitude']/threshold),math.log(b['magnitude']/threshold)
    bw=math.exp(math.log(a['frequency_Hz'])+(math.log(b['frequency_Hz']/a['frequency_Hz']))*(-y0)/(y1-y0))
    return {'status':'MEASURED_BRACKETED','BW_Hz':bw,'bracket_Hz':[a['frequency_Hz'],b['frequency_Hz']],
        'bracket_relative_width':b['frequency_Hz']/a['frequency_Hz']-1,
        'confidence':'CROSSING_BRACKET_ONLY_REQUIRES_AMPLITUDE_STEP_WINDOW_CHECKS'}


def pm_identification_prototype(points):
    inferred=[]
    for p in sorted(points,key=lambda x:x['frequency_Hz']):
        if p['status']!='MEASURED': continue
        t=complex(*p['T_complex'])
        if abs(1-t)<.05: continue
        l=t/(1-t)
        inferred.append({'f_Hz':p['frequency_Hz'],'L_conditional':[l.real,l.imag],
                         'magnitude':abs(l),'phase_deg':math.degrees(np.angle(l)),
                         'inverse_conditioning':1/abs(1-t)})
    pairs=[(a,b) for a,b in zip(inferred,inferred[1:]) if a['magnitude']>=1>b['magnitude']]
    estimate=None
    if len(pairs)==1:
        a,b=pairs[0]; alpha=-math.log(a['magnitude'])/math.log(b['magnitude']/a['magnitude'])
        phases=np.unwrap(np.radians([a['phase_deg'],b['phase_deg']]))
        phase=float(np.degrees(phases[0]+alpha*(phases[1]-phases[0])))
        estimate={'conditional_UGF_Hz':math.exp(math.log(a['f_Hz'])+alpha*math.log(b['f_Hz']/a['f_Hz'])),
                  'conditional_PM_deg':180+phase}
    return {'status':'PM_M2_UNKNOWN','independent_PM_deg':None,'prototype_estimate':estimate,
        'conditional_inferred_points':inferred,
        'obstacles':['T/(1-T) assumes scalar LTI unity feedback; edge PLL is sampled/periodic and harmonic return ratios are unmeasured',
                     'not a direct loop-break return-ratio measurement; no independent validation of inversion',
                     'finite frequency grid and conditioning near T=1; cannot certify PM from closed-loop magnitude'],
        'next':'Add phase-summing injection at divider/PFD, measure both sides of summing junction and harmonic sidebands with matched clock conventions.'}
