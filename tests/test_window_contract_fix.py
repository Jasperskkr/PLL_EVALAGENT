"""Recorded response replay and adversarial contracts; zero real LLM/M1/M2."""
from copy import deepcopy
from pathlib import Path
import json
import pytest
from pll_allocation.agent.window_contract import (
    normalize_window,check_physical_window,contract_decision,COMPACT)
from tools.stress_open_domain import validate_window

ROOT=Path(__file__).resolve().parents[1]
RUNS=('SW_P2_1301','SN_P2_2603','ST_P2_2603')


def recorded(run=RUNS[0]):
    folder=ROOT/'experiments/initial_allocation_a_plus'
    state=json.loads((folder/'runs'/run/'window_01/PlannerState.json').read_text(encoding='utf-8'))
    state['template']=json.loads((folder/'frozen'/(run[:2]+'.json')).read_text(encoding='utf-8'))
    raw=json.loads((folder/'runs'/run/'window_01/RegionIntent.json').read_text(encoding='utf-8'))
    return state,raw


def adapted(raw,state):
    normalized,trace=normalize_window(raw,state)
    return check_physical_window(validate_window(normalized,state)),trace


@pytest.mark.parametrize('run',RUNS)
def test_three_recorded_interface_failures(run):
    state,raw=recorded(run)
    from tools import stress_open_domain as module
    old_validate=getattr(module,'_validate_canonical_window',module.validate_window)
    with pytest.raises(ValueError,match='unit/scale'):old_validate(raw,state)
    p,trace=adapted(raw,state)
    assert p and trace['changes'] and not trace['numerical_clipping']
    for k,a in raw['parameters'].items():
        assert (a['min'],a['max'])==(p['parameters'][k]['min'],p['parameters'][k]['max'])


@pytest.mark.parametrize('axis,unit,factor',[
    ('Icp','µA',1e-6),('Icp','mA',1e-3),('Rz','kΩ',1e3),('Rz','ohm',1),
    ('C1','nF',1e-9),('C2','pF',1e-12),('f0','MHz',1e6),('Kvco','MHz/V',1e6)])
def test_equivalent_units_preserve_actual_SI(axis,unit,factor):
    state,raw=recorded();base,_=adapted(raw,state)
    a=raw['parameters'][axis];a['unit']=unit
    for key in ('min','max'):a[key]/=factor
    p,trace=adapted(raw,state)
    for key in ('min','max'):assert p['parameters'][axis][key]==pytest.approx(base['parameters'][axis][key],rel=1e-14)
    assert trace['changes']


def test_compact_format_has_no_scale_or_state_metadata():
    state,raw=recorded();raw['schema_version']=COMPACT;del raw['state_sha256']
    for a in raw['parameters'].values():a.pop('scale')
    assert adapted(raw,state)[0]['parameters']['Icp']['scale']=='log'


@pytest.mark.parametrize('issue',['evidence','state','negative','guard','nan','dimension','phase','tuning'])
def test_actual_invalid_physics_is_not_repaired(issue):
    state,raw=recorded()
    if issue=='evidence':raw['evidence_ids']=['FAKE']
    if issue=='state':raw['state_sha256']='wrong'
    if issue=='negative':raw['parameters']['Icp']['min']=-1
    if issue=='guard':raw['parameters']['Rz']['max']=1e40
    if issue=='nan':raw['parameters']['C1']['min']=float('nan')
    if issue=='dimension':raw['parameters']['C1']['unit']='Hz'
    if issue=='phase':
        raw['parameters']['C1'].update(min=1e-9,max=2e-9)
        raw['parameters']['C2'].update(min=1e-14,max=2e-14)
    if issue=='tuning':
        raw['parameters']['f0'].update(min=1e6,max=2e6)
        raw['parameters']['Kvco'].update(min=1e5,max=2e5)
    with pytest.raises(ValueError):adapted(raw,state)


class Policy:
    def __init__(self,outputs):self.outputs=iter(outputs);self.states=[]
    def decide(self,state,directory):
        self.states.append(deepcopy(state));out=deepcopy(next(self.outputs))
        if 'state_sha256' in out:out['state_sha256']=state['state_sha256']
        return out


def test_exactly_one_structured_correction_with_raw_trace(tmp_path):
    state,raw=recorded();bad=deepcopy(raw);del bad['parameters']['C1']
    policy=Policy([bad,raw])
    value=contract_decision(policy,state,tmp_path/'call',normalize=normalize_window,
        validate=lambda x,s:check_physical_window(validate_window(x,s)))
    assert value and len(policy.states)==2 and 'validation_feedback' in policy.states[1]
    from pll_allocation.physics_mapping.model import fingerprint
    second=deepcopy(policy.states[1]);digest=second.pop('state_sha256')
    assert digest==fingerprint(second)
    assert json.loads((tmp_path/'call/decision_diff.json').read_text())['before']==bad
    policy=Policy([bad,bad,raw])
    with pytest.raises(ValueError):contract_decision(policy,state,tmp_path/'twice',normalize=normalize_window,validate=lambda x,s:x)
    assert len(policy.states)==2


def test_physical_rejection_does_not_retry(tmp_path):
    state,raw=recorded();raw['evidence_ids']=['INVENTED'];policy=Policy([raw,raw])
    with pytest.raises(ValueError):contract_decision(policy,state,tmp_path/'call',normalize=normalize_window,
        validate=lambda x,s:validate_window(x,s))
    assert len(policy.states)==1


def test_canonical_legacy_is_unchanged():
    state,raw=recorded();raw,_=normalize_window(raw,state)
    out,trace=normalize_window(raw,state)
    assert out==raw and not trace['changes']


@pytest.mark.parametrize('issue',['negative','guard','dimension','phase','tuning'])
def test_physical_errors_never_trigger_provider_repair(tmp_path,issue):
    state,raw=recorded()
    if issue=='negative':raw['parameters']['Icp']['min']=-1
    if issue=='guard':raw['parameters']['Rz']['max']=1e40
    if issue=='dimension':raw['parameters']['C1']['unit']='Hz'
    if issue=='phase':
        raw['parameters']['C1'].update(min=1e-9,max=2e-9)
        raw['parameters']['C2'].update(min=1e-14,max=2e-14)
    if issue=='tuning':
        raw['parameters']['f0'].update(min=1e6,max=2e6)
        raw['parameters']['Kvco'].update(min=1e5,max=2e5)
    policy=Policy([raw,raw])
    with pytest.raises(ValueError):contract_decision(policy,state,tmp_path/issue,normalize=normalize_window,validate=lambda x,s:validate_window(x,s))
    assert len(policy.states)==1


def test_nonfinite_json_is_terminal_and_provider_is_distinct(tmp_path):
    from pll_allocation.agent.region_policy import InvalidNumericResponse,ProviderError
    class ErrorPolicy:
        def __init__(self,error):self.calls=0;self.error=error
        def decide(self,state,directory):self.calls+=1;raise self.error
    state,_=recorded()
    p=ErrorPolicy(InvalidNumericResponse('nonfinite'))
    with pytest.raises(InvalidNumericResponse):contract_decision(p,state,tmp_path/'nonfinite',normalize=normalize_window,validate=lambda x,s:x)
    assert p.calls==1
    p=ErrorPolicy(ProviderError('provider unavailable'))
    with pytest.raises(ProviderError):contract_decision(p,state,tmp_path/'provider',normalize=normalize_window,validate=lambda x,s:x)
    assert p.calls==1
