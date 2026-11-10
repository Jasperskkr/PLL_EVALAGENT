"""Prespecified longer-window follow-up of observed near-rail acquisition discrepancy."""
from __future__ import annotations
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from pll_allocation.block_space.event_reference import clean_summary,load_existing_simulator
from pll_allocation.block_space.validation import write_new


def main():
    output=ROOT/'outputs/block_space_boundary_diagnostic_20261104_01'
    output.mkdir(parents=True,exist_ok=False)
    case=json.loads((ROOT/'outputs/block_space_v1_20261104_01/cases/C130/result.json').read_text(encoding='utf-8'))
    write_new(output/'plan.json',{'parent_case':'outputs/block_space_v1_20261104_01/cases/C130/result.json',
        'reason':'interior Vreq=1.199V but no observed tracking at 160us; distinguish horizon/acquisition from M1 static error',
        'candidate':case['case']['parameters'],'durations_s':[640e-6],
        'dt_s':[case['event']['runs'][0]['dt'],case['event']['runs'][1]['dt']],
        'system_spec_changes':False,'no_lock_time_spec_or_measurement':True})
    simulate,provenance=load_existing_simulator(ROOT/'data/behavioral_space_v1/reference')
    p={k:x['value'] for k,x in case['case']['parameters']['values'].items()}
    summaries=[]
    for old in case['event']['runs']:
        raw=simulate(sim_time=640e-6,dt=old['dt'],v0=.15,R=p['Rz'],c1=p['C1'],c2=p['C2'],
                     I=p['Icp'],kv=p['Kvco'],f0=p['f0'],N=p['N'],fref=p['f_ref'],verbose=False)
        clean,missing=clean_summary(raw)
        summaries.append({'summary':clean,'nonfinite_summary_fields':missing})
    result={'runs':summaries,'source':provenance,'M2_system_verdict':'NOT_EVALUATED',
        'behavioral_calls':len(summaries),'MATLAB_runtime_calls':0,
        'interpretation':'longer finite-window diagnostic, not a lock-time protocol or full-M2 BW/PM verification'}
    write_new(output/'result.json',result)
    print(json.dumps(result,indent=2,ensure_ascii=False))


if __name__=='__main__':
    main()
