import csv
import hashlib
import json
from pathlib import Path
import pytest
from pll_allocation._legacy.evaluation.python_behavioral import PythonBehavioralEvaluator
from test_contracts import ROOT,problem

REFERENCE=json.loads((ROOT/'data/legacy/matlab_regression_cases.json').read_text(encoding='utf-8'))

@pytest.mark.parametrize('case',REFERENCE['CASES'],ids=lambda x:x['job_id'])
def test_full_historical_corrected_matlab_trajectory(case):
    p=problem(); req={k:p[k] for k in ('operating_context','initialization','measurement','system_spec')}
    req['operating_context']={**req['operating_context'],'pfd_reset_s':2e-9}
    target={k:case[k] for k in ('Rz_Ohm','I_up_A','I_down_A','q0_C')}
    target.update(C1_F=1e-10,C2_F=1e-9,Cload_F=5e-14,Rload_Ohm=1e9)
    actual=PythonBehavioralEvaluator(req,REFERENCE['VCO']).evaluate(target)['cycles']
    folder=ROOT/'data/verification_reference'/case['job_id']
    with (folder/'cycles_matlab.csv').open(encoding='utf-8-sig',newline='') as f: expected=list(csv.DictReader(f))
    assert len(actual)==len(expected)==400
    assert max(abs(a['phase_deg']-float(b['error_cycles'])*360) for a,b in zip(actual,expected))<6e-7
    assert max(abs(a['frequency_cycle_Hz']-float(b['frequency_cycle_Hz']))/80e6*1e6 for a,b in zip(actual,expected))<4e-4
    assert max(abs(a['vctrl_pre_V']-float(b['vctrl_pre_V'])) for a,b in zip(actual,expected))<4e-10

def test_reference_snapshot_hashes():
    data=json.loads((ROOT/'data/verification_reference/manifest.json').read_text(encoding='utf-8'))
    assert data['records']==24 and len(data['entries'])==96
    for row in data['entries']:
        assert hashlib.sha256((ROOT/row['destination']).read_bytes()).hexdigest()==row['sha256']
