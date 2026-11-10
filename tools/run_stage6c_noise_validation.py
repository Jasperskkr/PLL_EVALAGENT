"""Verifier-only physical source experiment harness, not an allocation pipeline."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from pll_allocation.pipeline_contracts import load_inputs
from pll_allocation.allocation.allocate import analytical
from pll_allocation.allocation.core import Meter,write_new
from pll_allocation.block_space.contracts import make_candidate
from pll_allocation.physics_mapping.noise import noise_mapping
from pll_allocation.verification.noise import verify_noise


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--sources',nargs='+',default=['reference','vco','cp','resistor','all']);p.add_argument('--nominal',action='store_true');p.add_argument('--gated',action='store_true');p.add_argument('--protocol');a=p.parse_args()
    out=Path(a.out);out.mkdir(parents=True,exist_ok=False);frozen=ROOT/'configs/stage6c/frozen_01'
    read=lambda n:json.loads((frozen/n).read_text())
    _,model,spec,cap=load_inputs();meter=Meter(10000,96)
    candidate=make_candidate(model) if a.nominal else analytical(model,spec,meter)[0]
    write_new(out/'first_candidate.json',candidate);q=json.loads(Path(a.protocol).read_text()) if a.protocol else read('noise_protocol.json');ni=read('nonideal_zero.json');rows=[]
    for sid in a.sources:
        noise=read('noise_'+sid+'.json');pred=noise_mapping(candidate,noise,q['band_Hz'])
        write_new(out/(sid+'_M1.json'),pred)
        result=verify_noise(candidate,ni,noise,q,cap,out/sid)
        result={'source':sid,'M1_integrated_jitter_s':pred['integrated_jitter_s'],'M2':result}
        if result['M2']['integrated_jitter_s'] is not None:
            result['M2_over_M1_jitter_ratio']=result['M2']['integrated_jitter_s']/pred['integrated_jitter_s'] if pred['integrated_jitter_s'] else None
        rows.append(result)
    if a.gated:
        rows.append({'source':'gated_cp','M1_absolute_comparison':'UNSUPPORTED_UNCALIBRATED_DUTY_EQUIVALENCE',
            'M2':verify_noise(candidate,read('nonideal_reset.json'),read('noise_zero.json'),q,cap,out/'gated_cp',
                cp_gated_psd={'up_A2_per_Hz':1e-24,'down_A2_per_Hz':1e-24})})
    write_new(out/'summary.json',rows)
