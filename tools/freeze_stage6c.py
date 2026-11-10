"""Write predeclared research environments once. No simulations, no result tuning."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def documents():
    from pll_allocation.block_space.extensions import LOCATIONS,UNITS
    sources=[]
    for sid,typ,psd in [('reference','white',{'level':1e-13}),('vco','power_law',{'coefficient':100.,'exponent':-2}),
                        ('cp','white',{'level':1e-24}),('resistor','thermal',{'temperature_K':300.})]:
        sources.append(dict(source_id=sid,injection_location=LOCATIONS[sid],psd_type=typ,psd_values=psd,
            unit=UNITS[sid],one_sided_or_two_sided='one_sided',frequency_range_Hz=[1.,5e6 if sid=='reference' else 1e12],
            profile_id='research-source-'+sid+'-1.0',provenance='predeclared engineering environment; no device characterization',
            assumption_level='INDEPENDENT_RESEARCH_SOURCE'))
    profile=dict(schema_version='pll-noise-profile-1.0',profile_id='stage6c-fixed-noise-1.0',
        provenance='docs/stage6c/IMPLEMENTATION_DESIGN.md; not retuned from results',assumption_level='RESEARCH_ONLY',
        independent_sources=True,sources=sources)
    docs={'noise_all.json':profile}
    from copy import deepcopy
    for sid in ['zero']+[s['source_id'] for s in sources]:
        one=deepcopy(profile);one['profile_id']='stage6c-noise-'+sid+'-1.0'
        one['sources']=[] if sid=='zero' else [s for s in sources if s['source_id']==sid]
        docs['noise_'+sid+'.json']=one
    base=dict(schema_version='pll-nonideal-profile-1.0',profile_id='ideal-1.0',provenance='predeclared engineering environment',
              K2_Hz_per_V2=0.,cp_mismatch=0.,leakage_A=0.,reset_delay_s=0.,cp_voltage_coefficient_per_V=0.)
    docs['nonideal_zero.json']=base
    for name,k,v in [('K2_plus','K2_Hz_per_V2',4e6),('K2_minus','K2_Hz_per_V2',-4e6),
                     ('mismatch_plus','cp_mismatch',.1),('mismatch_minus','cp_mismatch',-.1),
                     ('reset','reset_delay_s',2e-9),('leak_plus','leakage_A',1e-7),('leak_minus','leakage_A',-1e-7),
                     ('compliance','cp_voltage_coefficient_per_V',.05)]:
        p={**base,k:v,'profile_id':name+'-1.0'};docs['nonideal_'+name+'.json']=p
    docs['nonideal_combined.json']={**base,'K2_Hz_per_V2':4e6,'cp_mismatch':.1,'reset_delay_s':2e-9,'profile_id':'combined-1.0'}
    docs['noise_protocol.json']=dict(protocol_id='pll-noise-verification-1.0',warmup_s=200e-6,observation_s=.004,
        record_interval_s=20e-9,band_Hz=[1e4,1e6],nperseg=16384,overlap_fraction=.5,window='hann',detrend='constant',
        seeds=[11,23,47,71,101],dt_pair_s=[.4e-9,.2e-9],confidence=.95,max_dt_variance_relative_difference=.2,
        max_seed_relative_CI_halfwidth=.35,minimum_seeds=5,minimum_segments=8,carrier_Hz=80e6,
        phase_residual='unwrapped_output_phase_minus_2pi_80MHz_t; mean only',
        deterministic_separation='same_nonideal_noise_off_difference; also report unsubtracted total PSD',
        reference_model='iid_phase_at_fref_linear_interpolation_sinc4; valid_band_max_0.1fref',
        cp_model='continuous_effective; gated UP/DOWN separate experiment, no automatic M1 equivalence')
    return docs


if __name__=='__main__':
    import sys
    sys.path.insert(0,str(ROOT))
    target=ROOT/'configs/stage6c/frozen_01';target.mkdir(parents=True,exist_ok=False)
    manifest=[]
    for name,doc in documents().items():
        path=target/name
        with path.open('x',encoding='utf-8') as stream:json.dump(doc,stream,indent=2,allow_nan=False);stream.write('\n')
        manifest.append({'path':name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    with (target/'manifest.json').open('x',encoding='utf-8') as stream:json.dump(manifest,stream,indent=2)
