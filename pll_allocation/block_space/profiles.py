"""Versioned external research profiles; original 17-input contract stays frozen."""
from copy import deepcopy
import math
import numpy as np
from ..physics_mapping.model import fingerprint, parse_parameters

K_B = 1.380649e-23
LOCATIONS = {'reference': 'reference_phase', 'vco': 'free_vco_phase',
             'cp': 'lf_input_current_effective', 'resistor': 'Rz_series_voltage'}
UNITS = {'reference': 'rad^2/Hz', 'vco': 'rad^2/Hz', 'cp': 'A^2/Hz', 'resistor': 'V^2/Hz'}


def number(x, name, nonnegative=False):
    if type(x) not in (float, int) or not math.isfinite(x) or (nonnegative and x < 0):
        raise ValueError('OUT_OF_DOMAIN: finite '+('nonnegative ' if nonnegative else '')+name)
    return x


def validate_noise(profile):
    keys={'schema_version','profile_id','provenance','assumption_level','independent_sources','sources'}
    if not isinstance(profile,dict) or set(profile)!=keys or profile['schema_version']!='pll-noise-profile-1.0':
        raise ValueError('UNSUPPORTED: noise profile contract')
    if profile['independent_sources'] is not True:
        raise ValueError('UNSUPPORTED: correlated sources need a cross-spectral model')
    if any(not isinstance(profile[k],str) or not profile[k] for k in ('profile_id','provenance','assumption_level')):
        raise ValueError('OUT_OF_DOMAIN: profile identity/provenance required')
    if not isinstance(profile['sources'],list):raise ValueError('OUT_OF_DOMAIN: source list required')
    seen=set()
    for src in profile['sources']:
        required={'source_id','injection_location','psd_type','psd_values','unit','one_sided_or_two_sided',
                  'frequency_range_Hz','profile_id','provenance','assumption_level'}
        if not isinstance(src,dict) or set(src)!=required:raise ValueError('OUT_OF_DOMAIN: complete source required')
        sid=src['source_id']
        if sid not in LOCATIONS or sid in seen:raise ValueError('UNSUPPORTED: unknown/duplicate source')
        seen.add(sid)
        if src['injection_location']!=LOCATIONS[sid]:raise ValueError('UNSUPPORTED: injection location')
        for k in ('profile_id','provenance','assumption_level'):
            if not isinstance(src[k],str) or not src[k]:raise ValueError('OUT_OF_DOMAIN: source metadata')
        band=src['frequency_range_Hz']
        if not isinstance(band,list) or len(band)!=2:raise ValueError('OUT_OF_DOMAIN: band')
        if not 0<number(band[0],'fmin')<number(band[1],'fmax'):raise ValueError('OUT_OF_DOMAIN: positive band')
        side=src['one_sided_or_two_sided']
        if side not in ('one_sided','two_sided'):raise ValueError('UNSUPPORTED: PSD sidedness')
        if src['unit']!=UNITS[sid] and not (sid in ('reference','vco') and src['unit']=='dBc/Hz' and side=='one_sided'):
            raise ValueError('UNSUPPORTED: canonical PSD unit or one-sided SSB required')
        typ=src['psd_type'];v=src['psd_values']
        if typ=='white':
            if set(v)!={'level'}:raise ValueError('OUT_OF_DOMAIN: white level')
            number(v['level'],'level',src['unit']!='dBc/Hz')
        elif typ=='power_law':
            if src['unit']=='dBc/Hz' or set(v)!={'coefficient','exponent'}:raise ValueError('UNSUPPORTED: power law SI only')
            number(v['coefficient'],'coefficient',True);number(v['exponent'],'exponent')
            if v['exponent'] not in (0,-1,-2,-3):raise ValueError('UNSUPPORTED: declared power exponents 0,-1,-2,-3')
        elif typ=='table':
            if set(v)!={'frequency_Hz','psd'}:raise ValueError('OUT_OF_DOMAIN: table keys')
            f=np.asarray(v['frequency_Hz'],float);y=np.asarray(v['psd'],float)
            if (f.ndim!=1 or f.size<2 or f.shape!=y.shape or not np.all(np.isfinite(f)) or not np.all(f>0) or not np.all(np.diff(f)>0)
                or f[0]>band[0] or f[-1]<band[1] or not np.all(np.isfinite(y))
                or (src['unit']!='dBc/Hz' and not np.all(y>0))):
                raise ValueError('OUT_OF_DOMAIN: positive log-log PSD table covers its declared band')
        elif typ=='thermal':
            if sid!='resistor' or src['unit']!='V^2/Hz' or side!='one_sided' or set(v)!={'temperature_K'}:
                raise ValueError('UNSUPPORTED: resistor thermal convention')
            number(v['temperature_K'],'temperature',True)
        else:raise ValueError('UNSUPPORTED: PSD type')
    return deepcopy(profile)


def source_psd(src, frequency, Rz):
    f=np.asarray(frequency,float);lo,hi=src['frequency_range_Hz']
    if not np.all(np.isfinite(f)) or np.any(f<=0) or np.any(f<lo) or np.any(f>hi):
        raise ValueError('OUT_OF_DOMAIN: unauthorized PSD extrapolation or zero offset')
    v=src['psd_values'];typ=src['psd_type']
    if typ=='white':y=np.full_like(f,float(v['level']))
    elif typ=='thermal':y=np.full_like(f,4*K_B*v['temperature_K']*Rz)
    elif typ=='power_law':y=v['coefficient']*f**v['exponent']
    else:
        yt=np.asarray(v['psd'],float)
        if src['unit']=='dBc/Hz':yt=2*10**(yt/10)
        y=np.exp(np.interp(np.log(f),np.log(v['frequency_Hz']),np.log(yt)))
    if src['unit']=='dBc/Hz' and typ!='table':y=2*10**(y/10)
    if src['one_sided_or_two_sided']=='two_sided':y=2*y
    if not np.all(np.isfinite(y)) or np.any(y<0):raise ValueError('OUT_OF_DOMAIN: nonfinite/negative PSD')
    return y


def validate_nonideal(profile, candidate):
    required={'schema_version','profile_id','provenance','K2_Hz_per_V2','cp_mismatch','leakage_A',
              'reset_delay_s','cp_voltage_coefficient_per_V'}
    if not isinstance(profile,dict) or set(profile)!=required or profile['schema_version']!='pll-nonideal-profile-1.0':
        raise ValueError('UNSUPPORTED: nonideal profile contract')
    if any(not isinstance(profile[k],str) or not profile[k] for k in ('profile_id','provenance')):
        raise ValueError('OUT_OF_DOMAIN: string identity/provenance')
    for k in required-{'schema_version','profile_id','provenance'}:number(profile[k],k)
    p=parse_parameters(candidate);vstar=(p['N']*p['f_ref']-p['f0'])/p['Kvco'];k2=profile['K2_Hz_per_V2']
    if not p['Vctrl_min']<vstar<p['Vctrl_max']:raise ValueError('OUT_OF_DOMAIN: interior tuning root')
    if abs(profile['cp_mismatch'])>=2 or not 0<=profile['reset_delay_s']<1/p['f_ref']:
        raise ValueError('OUT_OF_DOMAIN: CP currents/reset delay')
    for v in (p['Vctrl_min'],p['Vctrl_max']):
        if p['f0']+p['Kvco']*v+k2*v*(v-vstar)<=0 or p['Kvco']+k2*(2*v-vstar)<=0:
            raise ValueError('OUT_OF_DOMAIN: positive frequency and monotonic tuning throughout rails')
        if 1+profile['cp_voltage_coefficient_per_V']*(v-vstar)<=0:raise ValueError('OUT_OF_DOMAIN: CP voltage gain')
    # Independent bracketed numerical root of the actually simulated tuning law.
    from scipy.optimize import brentq
    root=brentq(lambda v:p['f0']+p['Kvco']*v+k2*v*(v-vstar)-p['N']*p['f_ref'],p['Vctrl_min'],p['Vctrl_max'])
    return {'profile_sha256':fingerprint(profile),'Vstar_V':vstar,'tuning_root_V':root,
            'local_Kvco_Hz_per_V':p['Kvco']+k2*(2*root-vstar),'vco_law':'anchored_quadratic',
            'ignored_by_ideal_M1':[k for k in required if k not in ('schema_version','profile_id','provenance') and profile[k]!=0]}
