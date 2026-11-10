"""Research-only conservative adjudication; historical evidence is not a new TB."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('stage6a_study',ROOT/'experiments/stage6a/study.py')
study=importlib.util.module_from_spec(spec);spec.loader.exec_module(study)


def pair(a=33e-6,b=33e-6,converged=True,status='CAPTURED_WITHIN_WINDOW'):
    return {'numerical_converged':converged,'reliable_capture_status':status,
            'coarse':{'lock_time_s':a},'fine':{'lock_time_s':b}}


@pytest.mark.parametrize('a,b,expected',[(33e-6,33e-6,'PASS'),(44e-6,43e-6,'FAIL'),
    (40e-6,40e-6,'UNKNOWN'),(39.5e-6,39e-6,'UNKNOWN'),(None,33e-6,'UNKNOWN')])
def test_lock_time_interval_conservative(a,b,expected):
    assert study.capture_judgment(pair(a,b),40e-6)['status']==expected


def test_capture_nonconvergence_and_finite_window_failure_are_distinct():
    assert study.capture_judgment(pair(converged=False),40e-6)['status']=='UNKNOWN'
    result=study.capture_judgment(pair(status='NOT_CAPTURED_WITHIN_WINDOW'),40e-6)
    assert result['status']=='FAIL' and 'fixed conditions/window' in result['reason']


def historical(name):
    return ROOT/'experiments/stage5'/name


def test_stage5_s3_random11_bw_pass_pm_fail_is_never_joint_feasible():
    p=historical('repair_01/runs/S3__random__11/attempt_001')
    proposal=study.read(p/'AllocationProposal.json')
    measured=study.read(p/'BehavioralVerificationResult.json')
    result=study.joint_judgment(proposal['joint_block_spec'],proposal['system_spec'],measured)
    assert result['BW_status']=='PASS'
    assert result['M1_PREDICTED_FEASIBLE'] is False
    assert result['research_joint_status']=='FAIL'
    assert result['FULL_SYSTEMSPEC_CERTIFIED'] is False


def analytical_evidence():
    p=historical('firstshot_01/runs/S0__analytical/attempt_001')
    return study.read(p/'AllocationProposal.json'),study.read(p/'BehavioralVerificationResult.json')


def test_success_stays_mixed_evidence_and_full_certification_unknown():
    item,measured=analytical_evidence()
    result=study.joint_judgment(item['joint_block_spec'],item['system_spec'],measured,pair(),40e-6)
    assert result['research_joint_status']=='RESEARCH_JOINT_FEASIBLE'
    assert result['FULL_SYSTEMSPEC_CERTIFIED'] is False
    assert result['full_SystemSpec_status']=='UNKNOWN'
    assert measured['metrics']['PM_deg']['value'] is None


def test_m1_pass_cannot_fill_unknown_independent_bw():
    item,measured=analytical_evidence();measured['metrics']['BW_Hz']['status']='UNKNOWN'
    result=study.joint_judgment(item['joint_block_spec'],item['system_spec'],measured)
    assert result['M1_PREDICTED_FEASIBLE'] is True
    assert result['M2_MEASURED_PASS'] is False
    assert result['research_joint_status']=='UNKNOWN'


def test_missing_capture_never_passes_enabled_deadline():
    item,measured=analytical_evidence()
    result=study.joint_judgment(item['joint_block_spec'],item['system_spec'],measured,deadline_s=40e-6)
    assert result['research_joint_status']=='UNKNOWN'


def test_mismatched_candidate_rejected():
    item,measured=analytical_evidence();measured['parameter_sha256']='0'*64
    with pytest.raises(ValueError,match='binding'):
        study.joint_judgment(item['joint_block_spec'],item['system_spec'],measured)


def test_interior_tuning_boundary_cannot_be_a_joint_success():
    item,measured=analytical_evidence();c=deepcopy(item['joint_block_spec'])
    c['values']['f0']['value']=68e6;c['values']['Kvco']['value']=10e6
    measured['parameter_sha256']=study.fingerprint(c)
    result=study.joint_judgment(c,item['system_spec'],measured)
    assert result['M1_PREDICTED_FEASIBLE'] is False
    assert result['research_joint_status']!='RESEARCH_JOINT_FEASIBLE'
