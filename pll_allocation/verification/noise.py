"""Independent steady-process PSD/jitter measurement. No M1 transfers used.

Inference samples are independent seed runs, never overlapping Welch segments.
Total PSD and matched noise-off residual PSD are both retained, including spurs.
"""
from copy import deepcopy
import json
import math
from pathlib import Path
import time
import numpy as np
from scipy.signal import welch
from scipy.stats import t as student_t
from .stage6c_native import simulate
from .measure import capture_metrics
from .experiments import write as write_new
from ..physics_mapping.model import fingerprint

PROTOCOL_ID='pll-noise-verification-1.0'


def validate_protocol(protocol):
    q=protocol
    if q.get('protocol_id') not in (PROTOCOL_ID,'pll-noise-verification-1.1'):raise ValueError('UNSUPPORTED: noise protocol')
    if q['protocol_id']=='pll-noise-verification-1.1' and q.get('noise_settle_s')!=100e-6:
        raise ValueError('UNSUPPORTED: explicit 100us noise-on settling in protocol1.1')
    if q['carrier_Hz']!=80e6 or q['detrend']!='constant' or q['window']!='hann' or q['overlap_fraction']!=.5:
        raise ValueError('UNSUPPORTED: PSD conventions')
    if len(q['seeds'])<q['minimum_seeds'] or q['minimum_seeds']<5 or len(set(q['seeds']))!=len(q['seeds']):
        raise ValueError('OUT_OF_DOMAIN: >=5 independent seeds')
    if any(type(s)is not int or not 0<=s<2**64 for s in q['seeds']):raise ValueError('OUT_OF_DOMAIN: seeds')
    if len(q['dt_pair_s'])!=2 or not 0<q['dt_pair_s'][1]<q['dt_pair_s'][0]:raise ValueError('paired steps')
    if not 0<q['band_Hz'][0]<q['band_Hz'][1]<=min(1e6,.45/q['record_interval_s']):raise ValueError('band/aliasing domain')
    if q['warmup_s']<160e-6 or q['observation_s']<=0 or q['nperseg']<256:raise ValueError('warmup/window')
    df=1/(q['record_interval_s']*q['nperseg'])
    if q['band_Hz'][0]<3*df or q['observation_s']<q['nperseg']*q['record_interval_s']*(1+(q['minimum_segments']-1)/2):
        raise ValueError('UNKNOWN: unresolved low offset or insufficient independent observation')
    if not .9<=q['confidence']<1 or not 0<q['max_dt_variance_relative_difference']<=.3:raise ValueError('inference contract')
    return deepcopy(q)


def band_integral(f,psd,band):
    f=np.asarray(f);psd=np.asarray(psd);lo,hi=band
    if lo<f[0] or hi>f[-1] or not 0<lo<hi or np.any(np.diff(f)<=0) or np.any(psd<0):raise ValueError('PSD band')
    keep=(f>lo)&(f<hi);x=np.r_[lo,f[keep],hi];y=np.interp(x,f,psd)
    return float(np.trapezoid(y,x))


def estimate_phase(trace,baseline,protocol):
    q=validate_protocol(protocol);t=trace[:,0];begin=q['warmup_s']+q.get('noise_settle_s',0.)
    take=(t>=begin)&(t<begin+q['observation_s'])
    t=t[take];phase=8*trace[take,1] # actual output phi minus nominal carrier, already unwrapped
    if len(t)<q['nperseg'] or not np.all(np.diff(t)>0):raise ValueError('UNKNOWN: insufficient/unordered phase')
    dt=float(np.median(np.diff(t)))
    if np.max(np.abs(np.diff(t)-dt))>1e-8*dt:raise ValueError('UNKNOWN: nonuniform observation samples')
    off=np.interp(t,baseline[:,0],8*baseline[:,1]);difference=phase-off
    opts=dict(fs=1/dt,window='hann',nperseg=q['nperseg'],noverlap=q['nperseg']//2,detrend='constant',scaling='density')
    f,total=welch(phase,**opts);_,random=welch(difference,**opts);_,det=welch(off,**opts)
    variance=band_integral(f,random,q['band_Hz']);totalvar=band_integral(f,total,q['band_Hz'])
    return {'time_s':t,'unwrapped_phase_residual_rad':phase,'time_error_s':phase/(2*np.pi*80e6),
        'matched_noise_off_residual_rad':difference,'frequency_Hz':f,'total_psd_rad2_per_Hz':total,
        'random_residual_psd_rad2_per_Hz':random,'deterministic_psd_rad2_per_Hz':det,
        'summary':{'random_phase_variance_rad2':variance,'random_integrated_jitter_s':math.sqrt(variance)/(2*np.pi*80e6),
            'total_phase_variance_rad2':totalvar,'total_integrated_jitter_s':math.sqrt(totalvar)/(2*np.pi*80e6),
            'deterministic_band_phase_variance_rad2':band_integral(f,det,q['band_Hz']),
            'output_frequency_error_Hz':(phase[-1]-phase[0])/(2*np.pi*(t[-1]-t[0])),
            'record_dt_s':dt,'frequency_resolution_Hz':float(f[1]-f[0]),'samples':len(t),
            'welch_segments':1+(len(t)-q['nperseg'])//(q['nperseg']//2),
            'degrees_of_freedom_policy':'NOT_USED_AS_MONTE_CARLO_SAMPLES',
            'no_linear_slope_subtraction':True,'band_Hz':q['band_Hz']}}


def seed_interval(variances,confidence=.95):
    x=np.asarray(variances,float)
    if x.ndim!=1 or len(x)<5 or not np.isfinite(x).all() or np.any(x<0):raise ValueError('UNKNOWN: >=5 independent finite variances')
    mean=float(x.mean());half=float(student_t.ppf((1+confidence)/2,len(x)-1)*x.std(ddof=1)/np.sqrt(len(x)))
    return {'mean_variance_rad2':mean,'variance_CI_rad2':[max(0.,mean-half),mean+half],
        'relative_halfwidth':half/mean if mean else 0.,'independent_seed_count':len(x),
        'confidence':confidence,'method':'Student-t across independent seed integrated phase variances; approximate finite-sample CI',
        'welch_segments_are_not_independent_samples':True}


def aggregate(measurements,protocol,limit_s=None):
    q=validate_protocol(protocol);bydt={}
    for dt in q['dt_pair_s']:
        rows=[r for r in measurements if r['requested_dt_s']==dt]
        if sorted(r['seed'] for r in rows)!=sorted(q['seeds']):raise ValueError('UNKNOWN: missing independent seed bundle')
        bydt[str(dt)]=seed_interval([r['random_phase_variance_rad2'] for r in rows],q['confidence'])
    a,b=list(bydt.values());delta=abs(a['mean_variance_rad2']-b['mean_variance_rad2'])/max(b['mean_variance_rad2'],1e-300)
    reliable=delta<=q['max_dt_variance_relative_difference'] and all(r['relative_halfwidth']<=q['max_seed_relative_CI_halfwidth'] for r in bydt.values())
    var=[min(r['variance_CI_rad2'][0] for r in bydt.values()),max(r['variance_CI_rad2'][1] for r in bydt.values())]
    jitter=[math.sqrt(x)/(2*np.pi*80e6) for x in var]
    verdict='UNKNOWN'
    if reliable and limit_s is not None:verdict='PASS' if jitter[1]<=limit_s else 'FAIL' if jitter[0]>limit_s else 'UNKNOWN'
    return {'status':'STATISTICALLY_RESOLVED_CONDITIONAL' if reliable else 'UNKNOWN','jitter_constraint_status':verdict,
        'integrated_jitter_s':math.sqrt(b['mean_variance_rad2'])/(2*np.pi*80e6),'jitter_interval_s':jitter,
        'statistical_variance_interval_rad2':var,'per_dt_seed_statistics':bydt,'dt_relative_variance_difference':delta,
        'uncertainty_type':'conditional statistical seed CI + conservative union over dt; not deterministic BW envelope',
        'limit_s':limit_s,'profile_stationarity_assumption':True,'strict_periodic_PM_status':'UNKNOWN'}


def verify_noise(candidate,nonideal,noise,noise_protocol,capture_protocol,out,*,limit_s=None,emit=None,cp_gated_psd=None):
    q=validate_protocol(noise_protocol);out=Path(out);out.mkdir(parents=True,exist_ok=False)
    calls=[];start=time.perf_counter();measurements=[];failure=None;all_locked=True
    emit=emit or (lambda *a,**k:None)
    write_new(out/'request.json',dict(candidate=candidate,nonideal=nonideal,noise=noise,noise_protocol=q,
        capture_protocol=capture_protocol,limit_s=limit_s,cp_gated_psd=cp_gated_psd))
    def native(folder,noiseprofile,dt,seed):
        folder.mkdir(exist_ok=False);event={'index':len(calls)+1,'folder':folder.name,'requested_dt_s':dt,'seed':seed}
        calls.append(event);began=time.perf_counter();emit('NATIVE_STARTED',**event)
        try:
            r=simulate(candidate,nonideal,noiseprofile,seed=seed,duration_s=q['warmup_s']+q.get('noise_settle_s',0.)+q['observation_s'],
                noise_onset_s=q['warmup_s'],dt_s=dt,record_interval_s=q['record_interval_s'],onset_s=q['warmup_s'],cp_gated_psd=cp_gated_psd if noiseprofile else None)
            if 'extended_trace' in r:
                ext=r['extended_trace'];diag=r['extension']['diagnostics']
                for column,name in [(13,'up'),(14,'down')]:
                    enabled_time=float(ext[-1,column]-np.interp(q['warmup_s'],ext[:,0],ext[:,column]))
                    diag[name+'_noise_enabled_on_time_s']=enabled_time
                    density=cp_gated_psd[name+'_A2_per_Hz'] if cp_gated_psd and noiseprofile else 0.
                    diag[name+'_expected_noise_charge_variance_C2']=density*enabled_time/2
                diag['effective_cp_expected_noise_charge_variance_C2']=r['extension']['noise_levels']['cp']*(q.get('noise_settle_s',0.)+q['observation_s'])/2
            np.savez_compressed(folder/'trajectory.npz',trace=r['trace'],ref_edges=r['ref_edges'],div_edges=r['div_edges'])
            write_new(folder/'native_summary.json',{k:r[k] for k in ('settings','summary','extension')})
            event.update(status='COMPLETED',integration_points=r['summary']['integration_points'],native_elapsed_s=r['summary']['elapsed_s'])
            return r
        except Exception as error:
            event.update(status='FAILED',reason=type(error).__name__+': '+str(error));write_new(folder/'failure.json',event);raise
        finally:
            event['wall_s']=time.perf_counter()-began
            with (out/'native_events.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(event,allow_nan=False)+'\n')
            emit('NATIVE_COMPLETED' if event.get('status')=='COMPLETED' else 'NATIVE_FAILED',**event)
    try:
        for index,dt in enumerate(q['dt_pair_s']):
            baseline=native(out/('dt'+str(index)+'_noise_off'),None,dt,0)
            for seed in q['seeds']:
                folder=out/('dt'+str(index)+'_seed'+str(seed));r=native(folder,noise,dt,seed)
                # Warmup lock and continuing lock checked from original capture block definitions.
                pre={**r,'trace':r['trace'][r['trace'][:,0]<=q['warmup_s']]}
                before=capture_metrics(pre,capture_protocol)
                tracking=None
                if q['protocol_id']=='pll-noise-verification-1.1':
                    from .noise_tracking import terminal_capture,steady_tracking
                    after=terminal_capture(r,capture_protocol);tracking=steady_tracking(r,q,capture_protocol)
                    good=before['status']=='CAPTURED_WITHIN_WINDOW' and tracking['status']=='PASS_CONDITIONAL_OBSERVATION'
                    after_status='CAPTURED_WITHIN_WINDOW' if after['terminal_captured'] else 'DETERMINISTIC_TERMINAL_BOUND_NOT_MET'
                else:
                    after=capture_metrics(r,capture_protocol)
                    good=before['status']=='CAPTURED_WITHIN_WINDOW' and after['status']=='CAPTURED_WITHIN_WINDOW'
                    after_status=after['status']
                z=r['trace'];during=z[:,0]>=q['warmup_s'];clamps=int(z[during][-1,5]-z[during][0,5])
                # No slips anywhere in observation, even if loop recaptures before terminal hold.
                error=z[during,2]-z[during,1];branches=np.floor((error+np.pi)/(2*np.pi))
                good=bool(good and clamps==0 and np.ptp(branches)==0)
                all_locked=all_locked and good
                est=estimate_phase(r['trace'],baseline['trace'],q)
                np.savez_compressed(folder/'noise_observation.npz',**{k:v for k,v in est.items() if k!='summary'})
                row={**est['summary'],'seed':seed,'requested_dt_s':dt,'locked_during_observation':good,
                    'pre_noise_lock':before['status'],'terminal_lock':after_status,'stochastic_tracking':tracking,'clamps_in_observation':clamps,
                    'evidence':str(folder.relative_to(out))}
                measurements.append(row);write_new(folder/'measurement.json',row)
        result=aggregate(measurements,q,limit_s)
        if not all_locked:result.update(status='UNKNOWN',jitter_constraint_status='UNKNOWN',reason='lock/slips/clamps during observation')
    except Exception as error:
        failure={'type':type(error).__name__,'reason':str(error)}
        result={'status':'UNKNOWN','jitter_constraint_status':'UNKNOWN','integrated_jitter_s':None,'jitter_interval_s':None}
    result.update(model_id='independent-event-noise-measurement-1.0',candidate_sha256=fingerprint(candidate),
        noise_profile_id=noise['profile_id'],noise_profile_sha256=fingerprint(noise),nonideal_profile_id=nonideal['profile_id'],
        protocol_id=q['protocol_id'],protocol_sha256=fingerprint(q),measurements=measurements,failure=failure,
        all_observations_locked=all_locked,cp_gated_absolute_M1_comparison='UNSUPPORTED_UNCALIBRATED_DUTY_EQUIVALENCE' if cp_gated_psd else 'CONTINUOUS_EFFECTIVE_MODEL',
        cost={'native_calls':len(calls),'native_completed':sum(c.get('status')=='COMPLETED' for c in calls),
            'native_failed':sum(c.get('status')=='FAILED' for c in calls),
            'native_elapsed_s':sum(c.get('native_elapsed_s',0.) for c in calls),
            'integration_points':sum(c.get('integration_points',0) for c in calls),'wall_s':time.perf_counter()-start})
    write_new(out/'result.json',result);return result
