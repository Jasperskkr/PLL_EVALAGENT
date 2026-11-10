"""Conditional continuous M1 noise mapping. No time-domain simulator imports.

All phase is rad, frequency Hz, one-sided PSD. CP noise is continuous effective
LF-input current; R noise is a series voltage, not control-node voltage noise.
"""
from copy import deepcopy
import math
import numpy as np
from .model import parse_parameters, _response, evaluate, fingerprint
from ..block_space.extensions import validate_noise, source_psd

MODEL_ID='cppll-independent-noise-m1-1.0'


def transfers(candidate, frequency):
    return _transfers(parse_parameters(candidate),frequency)


def _transfers(p,frequency):
    f=np.asarray(frequency,float)
    if np.any(f<=0) or not np.all(np.isfinite(f)):raise ValueError('positive finite offsets required')
    s=2j*np.pi*f
    responses=np.asarray([_response(p,float(x)) for x in f.flat]).reshape(f.shape+(3,))
    z,L=responses[...,0],responses[...,1]
    dr=p['C2']/(p['C1']+p['C2']+s*p['Rz']*p['C1']*p['C2'])
    k0=2*np.pi*p['Kvco']
    return {'reference':p['N']*L/(1+L),'vco':1/(1+L),
            'cp':k0*z/s/(1+L),'resistor':k0*dr/s/(1+L)}


def optimizer_noise_estimate(parameters,profile,band_Hz,points=257):
    """Counted cheap solver trial, not checked M1; final candidate gets full mapping.

    Reuse same responses and explicit frozen source model; does not certify a trial
    outside declared domain or a nominally unstable loop. Other hard margins guard it.
    """
    f=np.geomspace(*band_Hz,points);h=_transfers(parameters,f);variance=0.
    for src in profile['sources']:
        y=np.abs(h[src['source_id']])**2*source_psd(src,f,parameters['Rz'])
        variance+=float(np.trapezoid(y,f))
    return math.sqrt(variance)/(2*np.pi*parameters['N']*parameters['f_ref'])


def noise_mapping(candidate, profile, band_Hz, *, points=2049, frozen_Rz=None):
    """Explicit band; log trapezoid, source variances added before sqrt."""
    profile=validate_noise(profile);p=parse_parameters(candidate)
    if (not isinstance(band_Hz,(list,tuple)) or len(band_Hz)!=2 or
        not all(type(x) in (int,float) and math.isfinite(x) for x in band_Hz) or
        not 0<band_Hz[0]<band_Hz[1] or type(points)is not int or points<17):
        raise ValueError('OUT_OF_DOMAIN: positive explicit band and >=17 mesh points')
    base=evaluate(candidate).as_dict()
    if base['status']!='OK':return {**base,'noise_validity':base['status'],'integrated_jitter_s':None}
    f=np.geomspace(*band_Hz,points);h=transfers(candidate,f);components={};variances={};inputs={}
    for src in profile['sources']:
        sid=src['source_id'];psd=source_psd(src,f,p['Rz'] if frozen_Rz is None else frozen_Rz)
        y=np.abs(h[sid])**2*psd;components[sid]=y.tolist();inputs[sid]=psd.tolist()
        variances[sid]=float(np.trapezoid(y,f))
    total=np.sum(list(components.values()),axis=0) if components else np.zeros_like(f)
    variance=sum(variances.values());den=(2*np.pi*p['N']*p['f_ref'])**2
    return {'status':'OK','noise_validity':'CONDITIONAL_INDEPENDENT_SMALL_SIGNAL','model_id':MODEL_ID,
        'parameter_sha256':fingerprint(candidate),'noise_profile_sha256':fingerprint(profile),'profile_id':profile['profile_id'],
        'metrics':base['metrics'],'frequency_Hz':f.tolist(),'input_psd':inputs,'source_output_psd_rad2_per_Hz':components,
        'output_psd_rad2_per_Hz':total.tolist(),'integrated_phase_variance_rad2':variance,
        'source_phase_variance_rad2':variances,'source_time_variance_s2':{k:v/den for k,v in variances.items()},
        'source_fractions':{k:v/variance if variance else 0. for k,v in variances.items()},
        'dominant_source':max(variances,key=variances.get) if variance else None,
        'integrated_jitter_s':math.sqrt(variance/den),'band_Hz':list(band_Hz),
        'protocol':{'id':'m1-noise-log-trapezoid-1.0','points':points,'sidedness':'one_sided','phase':'rad',
                    'output_frequency_Hz':p['N']*p['f_ref'],'source_independence':True},
        'intrinsic_noise_dependence':'UNMODELED; frozen source spectra except physical R thermal 4kTR',
        'verified_joint_block_spec':False}


def noise_sensitivity(model, candidate, profile, band_Hz, *, fraction=.01, points=1025):
    from ..allocation.core import bounds, values
    from ..block_space.contracts import make_candidate
    if not 0<fraction<.1:raise ValueError('finite-difference fraction')
    p=values(candidate);columns={}
    for name in ('Icp','Rz','Kvco','f0'):
        lo,hi=bounds(model,name);a=max(lo,p[name]*(1-fraction));b=min(hi,p[name]*(1+fraction))
        results=[]
        try:
            for x in (a,b):
                c=make_candidate(model,{**p,name:x})
                results.append((noise_mapping(c,profile,band_Hz,points=points,frozen_Rz=p['Rz']),
                                noise_mapping(c,profile,band_Hz,points=points)))
            if a==b or any(r[0]['status']!='OK' for r in results):raise ValueError('invalid stencil')
            delta=math.log(b/a);aa,bb=results[0][0],results[1][0]
            def elasticity(x,y):return math.log(y/x)/delta if x>0 and y>0 else None
            columns[name]={'status':'OK','points':[a,b],
                'transfer_log_elasticity':{**{k:elasticity(aa['metrics'][k],bb['metrics'][k]) for k in ('BW_Hz','UGF_Hz','PM_deg')},
                    'integrated_jitter_s':elasticity(aa['integrated_jitter_s'],bb['integrated_jitter_s'])},
                'including_known_thermal_R_jitter_elasticity':elasticity(results[0][1]['integrated_jitter_s'],results[1][1]['integrated_jitter_s']),
                'intrinsic_dependence':'UNMODELED, frozen profile; only resistor 4kTR dependence explicitly included above'}
        except ValueError as e:columns[name]={'status':'DOMAIN_LIMITED','reason':str(e)}
    return {'model_id':MODEL_ID,'parameter_sha256':fingerprint(candidate),'columns':columns,
            'C1_C2':'DISCRETE_ENUMERATION_REQUIRED','fraction':fraction}
