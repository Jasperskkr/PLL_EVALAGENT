"""TEST-only input adaptation/aggregation checks; zero real Provider/M2."""
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch
import pytest

from pll_allocation.agent.computational_window import scale_context,validate_window,observation_evidence
from pll_allocation.exploration.contracts import resolve_problem

ROOT=Path(__file__).resolve().parents[1]

def template():
    p=json.loads((ROOT/'configs/problems/nominal.json').read_text(encoding='utf-8'))
    return p

def decision_state():
    t=template();physics=scale_context(t)
    state={'case_id':'TEST_OPEN','round':1,'physics':physics,'template':t,'state_sha256':'TEST','previous_window':None}
    params={k:{'min':v*.8,'max':v*1.2,'unit':t['parameters'][k]['unit'],
        'scale':t['parameters'][k]['scale']} for k,v in physics['scale_anchors_SI'].items()}
    return state,{'schema_version':'pll-computational-window-decision-1.0','state_sha256':'TEST',
        'action':'OPEN_WINDOW','reason':'TEST finite gauge window, not user bound',
        'evidence_ids':['OPEN:SCALE_GAUGE'],'parameters':params}

def test_scale_is_original_algebra_not_formal_or_global_bound():
    p=scale_context(template())
    assert p['M1_calls']==p['M2_calls']==0 and p['analytic_calls']==1
    assert p['absolute_scale_identifiable'] is False and p['no_global_bound_proven']
    assert len(p['scale_anchors_SI'])==6

def test_open_decision_finite_continuous_problem():
    state,raw=decision_state();p=validate_window(raw,state);resolved=resolve_problem(p)
    assert resolved['parameters']['C1']['min']!=template()['parameters']['C1']['min']
    assert p['problem_id']=='TEST_OPEN:COMPUTATIONAL_WINDOW_1'

@pytest.mark.parametrize('issue',('evidence','hash','unit','zero','order','guard','missing','nan'))
def test_bad_window_rejected(issue):
    state,raw=decision_state()
    if issue=='evidence':raw['evidence_ids']=['invented']
    elif issue=='hash':raw['state_sha256']='wrong'
    elif issue=='unit':raw['parameters']['C1']['unit']='pF'
    elif issue=='zero':raw['parameters']['Icp']['min']=0
    elif issue=='order':raw['parameters']['C2']['max']=raw['parameters']['C2']['min']
    elif issue=='guard':raw['parameters']['Kvco']['max']=1e30
    elif issue=='missing':del raw['parameters']['f0']
    elif issue=='nan':raw['parameters']['Rz']['min']=float('nan')
    with pytest.raises(ValueError):validate_window(raw,state)

def test_expansion_cannot_silently_repeat_and_stop_is_explicit():
    state,raw=decision_state();p=validate_window(raw,state)
    state.update(round=2,previous_window=p['parameters']);raw['action']='EXPAND_OR_SWITCH'
    with pytest.raises(ValueError,match='outside'):validate_window(raw,state)
    raw['parameters']['C1']['min']*=.5
    assert validate_window(raw,state)['parameters']['C1']['min']<p['parameters']['C1']['min']
    raw.update(action='STOP',parameters=None);assert validate_window(raw,state) is None



def test_observation_evidence_is_registered_from_verifier_not_llm():
    evidence='M2:TEST_RANDOM_RUN:V3'
    observation={'stage9_result':{'verified_history':[{'evidence_id':evidence,'M2_status':'UNKNOWN',
        'candidate_sha256':'TEST_CANDIDATE'}],'searches':[{'evidence_ids':['INVENTED']} ]}}
    records=observation_evidence(observation)
    assert [r['evidence_id'] for r in records]==[evidence]
    state,raw=decision_state();raw['evidence_ids']=[evidence]
    with pytest.raises(ValueError,match='evidence'):validate_window(raw,state)
    state['physics']['allowed_evidence_ids'] += [r['evidence_id'] for r in records]
    assert validate_window(raw,state)
    assert observation_evidence(None)==[]


def test_saved_pilot_window_evidence_registration_regression():
    folder=ROOT/'experiments/stage7_stage9_randomized_stress/pilots/B_USER_UNBOUNDED/window_plan_2'
    if not folder.exists():pytest.skip('actual pilot evidence not present in this checkout')
    state=json.loads((folder/'planner_state.json').read_text(encoding='utf-8'))
    raw=json.loads((folder/'raw_window_decision.json').read_text(encoding='utf-8'))
    state['template']['parameters']=template()['parameters']
    with pytest.raises(ValueError,match='evidence'):validate_window(raw,state)
    state['physics']['allowed_evidence_ids'] += [r['evidence_id'] for r in observation_evidence(state['actual_observation'])]
    assert validate_window(raw,state) # TEST replay only, never a new LLM/simulation.



