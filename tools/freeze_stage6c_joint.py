"""Freeze both joint study scenarios before optimization/measurements."""
from copy import deepcopy
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from pll_allocation.physics_mapping.model import fingerprint
from pll_allocation.allocation.multispec_constraints import extension_rules,validate_problem
from pll_allocation.pipeline_contracts import load_inputs


if __name__=='__main__':
    out=ROOT/'configs/stage6c/joint_frozen_01';out.mkdir(parents=True,exist_ok=False)
    read=lambda path:json.loads((ROOT/path).read_text(encoding='utf-8'))
    config,model,spec,protocol=load_inputs();base=read('experiments/stage6b/frozen_01/B1.json')
    for name,ni in [('J0_ideal','zero'),('J1_nonideal','combined')]:
        p=deepcopy(base);p.update(schema_version='pll-multispec-problem-1.1',problem_id=name,version='stage6c-joint-1.0',objective='margin_then_capture')
        for row in p['research_system_spec']['metrics']:
            if row['metric']=='BW_Hz':row.update(min=200000.,max=250000.)
            if row['metric']=='PM_deg':row['min']=60.
        p['constraints'][0].update(lower_bound=200000.,upper_bound=250000.,normalization_scale=25000.)
        p['constraints'][1].update(lower_bound=60.,normalization_scale=60.)
        ext=dict(extension_id='stage6c-joint-behavioral-1.0',noise_profile=read('configs/stage6c/frozen_01/noise_all.json'),
            nonideal_profile=read('configs/stage6c/frozen_01/nonideal_'+ni+'.json'),
            noise_protocol=read('configs/stage6c/protocol11_01/noise_protocol.json'),jitter_limit_s=100e-12)
        ext['source_profile_hashes']={k:fingerprint(ext[k]) for k in ('noise_profile','nonideal_profile','noise_protocol')}
        p['behavioral_extension']=ext;p['constraints'].extend(extension_rules(ext))
        p['problem_sha256']=fingerprint({k:v for k,v in p.items() if k!='problem_sha256'})
        validate_problem(p,config,model,spec,protocol)
        with (out/(name+'.json')).open('x',encoding='utf-8') as f:json.dump(p,f,indent=2);f.write('\n')
