"""Independent verifier harness: original complete measurements with optional kernel.

Not a formal second Pipeline: this runs mechanism-validation experiments only.
All response fitting/refinement/convergence code is reused from verification.
"""
from functools import partial
import json
from pathlib import Path
import sys
import time
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from pll_allocation.pipeline_contracts import load_inputs
from pll_allocation.allocation.allocate import analytical
from pll_allocation.allocation.core import Meter,write_new
from pll_allocation.physics_mapping.model import evaluate,fingerprint
from pll_allocation.verification.stage6c_native import simulate
from pll_allocation.verification.experiments import save_run,response_sweep
from pll_allocation.verification.measure import capture_metrics
from pll_allocation.verification.run_suite import comparison_after_measurement


from pll_allocation.verification.stage6c import deterministic_measure


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--profiles',nargs='+',default=['zero','K2_plus','mismatch_plus','reset','combined']);args=p.parse_args()
    root=Path(args.out);root.mkdir(parents=True,exist_ok=False)
    _,model,spec,protocol=load_inputs();meter=Meter(10000,96);candidate,meta=analytical(model,spec,meter)
    write_new(root/'first_candidate.json',dict(candidate=candidate,metadata=meta,counts=meter.counts))
    rows=[]
    for name in args.profiles:
        ni=json.loads((ROOT/'configs/stage6c/frozen_01'/('nonideal_'+name+'.json')).read_text())
        try:rows.append(deterministic_measure(candidate,ni,root/name,protocol))
        except Exception as e:
            write_new(root/(name+'_failure.json'),dict(status='UNKNOWN',reason=type(e).__name__+': '+str(e)))
    write_new(root/'summary.json',rows)
