import hashlib
import json
from pathlib import Path
import pytest
from pll_allocation._legacy.evaluation.python_behavioral import PythonBehavioralEvaluator
from pll_allocation.behavioral import PythonBehavioralBackend, MetricVerifier, screen
from pll_allocation.contracts import candidate_grid
from test_contracts import ROOT, problem

REFERENCE=json.loads((ROOT/'data/legacy/matlab_regression_cases.json').read_text(encoding='utf-8'))

@pytest.mark.parametrize('case',REFERENCE['CASES'],ids=lambda x:x['job_id'])
def test_independent_corrected_matlab_anchors(case):
    p=problem()
    request={k:p[k] for k in ('operating_context','initialization','measurement','system_spec')}
    request['operating_context']={**request['operating_context'],'pfd_reset_s':2e-9}
    target={k:case[k] for k in ('Rz_Ohm','I_up_A','I_down_A','q0_C')}
    target.update(C1_F=1e-10,C2_F=1e-9,Cload_F=5e-14,Rload_Ohm=1e9,circuit_id='verifier_only')
    result=PythonBehavioralEvaluator(request,REFERENCE['VCO']).evaluate(target)
    assert result['metrics']['signed_mean_phase_deg']==pytest.approx(case['expected_signed_mean_phase_deg'],abs=1e-7)
    assert result['metrics']['tail_max_abs_frequency_error_ppm']==pytest.approx(case['expected_tail_ppm'],abs=1e-4)
    assert len(result['cycles'])==400
    assert result['empirical_cp_trajectory_domain']=='OUT_OF_LOCAL_TIMING_DOMAIN'
    assert result['independent_system_qualified_verdict']=='UNKNOWN'

def test_extracted_files_remain_byte_identical():
    for row in json.loads((ROOT/'data/legacy/legacy_manifest.json').read_text(encoding='utf-8')):
        assert hashlib.sha256((ROOT/row['destination']).read_bytes()).hexdigest()==row['sha256']

def test_real_tb_failure_and_unsupported_metric(tmp_path):
    p=problem('unsupported_jitter80'); c=next(candidate_grid(p))
    raw=PythonBehavioralBackend().run(p,c,tmp_path)
    judgement=MetricVerifier().judge(p,c,raw)
    assert raw['reference_cycles']==400
    assert judgement['verdict']=='UNKNOWN'
    assert judgement['checks'][-1]['status']=='UNSUPPORTED'
    assert screen(p,c)['behavioral_evaluations']==0
    assert raw['metrics']['mean_phase_abs_deg']!=screen(p,c)['metrics']['mean_phase_abs_deg']

@pytest.mark.parametrize('field,value',[
    ('candidate_sha256','wrong'),('problem_sha256','wrong'),('completed',False),
    ('reference_cycles',399),('domain_status','OUT_OF_DECLARED_NUMERIC_DOMAIN'),('kind','PREDICTION')])
def test_unqualified_result_cannot_pass(tmp_path,field,value):
    p=problem(); c=next(candidate_grid(p)); raw=PythonBehavioralBackend().run(p,c,tmp_path)
    raw[field]=value
    assert MetricVerifier().judge(p,c,raw)['verdict']=='UNKNOWN'
