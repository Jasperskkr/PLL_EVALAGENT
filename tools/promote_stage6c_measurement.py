"""One-time audited relocation of tested measurement into formal verification owner."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if __name__=='__main__':
    p=ROOT/'tools/run_stage6c_nonideal.py';s=p.read_text(encoding='utf-8')
    a=s.index('def deterministic_measure(');b=s.index("\n\nif __name__",a);fn=s[a:b]
    header='''"""Optional nonideal adapter over original sweep/capture/convergence verifier."""
import json
from pathlib import Path
import time
from ..allocation.core import write_new
from ..physics_mapping.model import fingerprint
from .stage6c_native import simulate
from .experiments import save_run,response_sweep
from .run_suite import comparison_after_measurement


'''
    fn=fn.replace("'nominal_M1':evaluate(candidate).as_dict()","'nominal_M1':comparison['M1_prediction']")
    with (ROOT/'pll_allocation/verification/stage6c.py').open('x',encoding='utf-8') as f:f.write(header+fn+'\n')
    p.write_text(s[:a]+'from pll_allocation.verification.stage6c import deterministic_measure\n'+s[b:],encoding='utf-8')
