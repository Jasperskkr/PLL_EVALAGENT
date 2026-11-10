"""Separate exact-lock initialization check; does not replace failed acquisition runs."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from pll_allocation.block_space.event_reference import clean_summary,load_existing_simulator
from pll_allocation.block_space.validation import write_new


def main():
    out=ROOT/'outputs/block_space_warmstart_diagnostic_20261104_01'
    out.mkdir(parents=True,exist_ok=False)
    case=json.loads((ROOT/'outputs/block_space_v1_20261104_01/cases/C130/result.json').read_text(encoding='utf-8'))
    p={k:x['value'] for k,x in case['case']['parameters']['values'].items()}
    vreq=(p['N']*p['f_ref']-p['f0'])/p['Kvco']
    write_new(out/'plan.json',{'candidate':case['case']['parameters'],'initial_control_V':vreq,
        'reason':'distinguish locked-point consistency from failed cold acquisition; parent failures retained',
        'duration_s':160e-6,'steps':[x['dt'] for x in case['event']['runs']],
        'system_spec_changes':False,'not_a_capture_test':True})
    simulate,provenance=load_existing_simulator(ROOT/'data/behavioral_space_v1/reference')
    runs=[]
    for old in case['event']['runs']:
        raw=simulate(sim_time=160e-6,dt=old['dt'],v0=vreq,R=p['Rz'],c1=p['C1'],c2=p['C2'],
            I=p['Icp'],kv=p['Kvco'],f0=p['f0'],N=p['N'],fref=p['f_ref'],verbose=False)
        result,missing=clean_summary(raw)
        runs.append({'summary':result,'nonfinite_summary_fields':missing})
    write_new(out/'result.json',{'runs':runs,'source':provenance,'behavioral_calls':2,
        'initial_control_V':vreq,'capture_verified':False,'M2_system_verdict':'NOT_EVALUATED'})
    print(json.dumps(runs,indent=2))


if __name__=='__main__':
    main()
