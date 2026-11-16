"""Budget and evidence invariants for the opt-in stop hook and A+ adapter."""
from copy import deepcopy
from pathlib import Path
import json
import pytest
from pll_allocation.agent.subregion_context import export_context
from pll_allocation.agent.subregion_tools import envelope
from pll_allocation.exploration.contracts import load_problem, make_parameters
from pll_allocation.region_explorer.explorer import RegionExplorer
from pll_allocation.studies.initial_allocation import rule_window, Trial
from pll_allocation.agent.computational_window import scale_context,validate_window
from pll_allocation.physics_mapping.model import fingerprint

ROOT=Path(__file__).resolve().parents[1]

def test_stop_records_and_caches_before_ending_stream(tmp_path):
    p=load_problem(ROOT/'configs/problems/nominal.json')
    context=export_context(p,[],tmp_path/'context',cost={'M1_calls':0},scope='EMPTY_BOOTSTRAP_NO_SEARCH')
    observed=[]
    ex=RegionExplorer(context,tmp_path/'executor',m1_budget=4,stop_when=lambda r:observed.append(r['evidence_id']) or True)
    candidate=make_parameters(p)
    d=envelope(ex,decision_id='STOPHOOK',region_id='STOPHOOK',bounds={k:[0.,1.] for k in p['parameters']},budget=4,seed=1301,proposals=2)
    result=ex.execute(d,candidate_stream=iter([candidate,candidate]),tool_name='PHYSICS_GUIDED_SEEDS')
    assert ex.counts['M1_calls']==1 and len(ex.rows)==1 and len(observed)==1
    assert result['failure'] is None and result['solver_runs'][0]['status']=='CONTROLLER_TARGET_REACHED'
    assert fingerprint(candidate) in ex.cache
    assert ex.rows[0]['cost']['evaluation_timing']['wall_time_s']>0
    ex.close()

def test_stop_during_slsqp_does_not_spend_independent_recheck(tmp_path):
    p=load_problem(ROOT/'configs/problems/nominal.json')
    context=export_context(p,[],tmp_path/'context',cost={'M1_calls':0},scope='EMPTY_BOOTSTRAP_NO_SEARCH')
    ex=RegionExplorer(context,tmp_path/'executor',m1_budget=40,budget_scheduling=True)
    d=envelope(ex,decision_id='SEED',region_id='SEED',bounds={k:[0.,1.] for k in p['parameters']},budget=1,seed=1,proposals=1)
    ex.execute(d,candidate_stream=iter([make_parameters(p)]),tool_name='PHYSICS_GUIDED_SEEDS')
    ex.stop_when=lambda r:True
    d=deepcopy(d); d.update(decision_id='OPT',region={'region_id':'OPT','parent_region_id':None},action='OPTIMIZE',search_method='SLSQP',
        seed_ids=[ex.rows[0]['evidence_id']],m1_budget=32,settings={'maxiter':40,'finite_difference_step':1e-5})
    result=ex.execute(d)
    assert ex.counts['M1_calls']==2
    assert result['solver_runs'][0]['status']=='CONTROLLER_TARGET_REACHED' and result['failure'] is None
    assert result['final_recheck_evidence_id'] is None
    ex.close()

def test_rule_proposes_actual_six_axis_window_and_expands():
    raw=json.loads((ROOT/'configs/problems/nominal.json').read_text())
    physics=scale_context(raw)
    state={'round':1,'case_id':'test','physics':physics,'template':raw,'state_sha256':'test','previous_window':None}
    decision=rule_window(state); p=validate_window(decision,state)
    assert len(p['parameters'])==6
    state.update(round=2,previous_window=p['parameters'])
    p2=validate_window(rule_window(state),state)
    assert any(p2['parameters'][k]['min']<p['parameters'][k]['min'] for k in p['parameters'])

def test_common_guard_distance_not_local_window_distance():
    t=object.__new__(Trial); t.guard={k:{'min':1.,'max':100.,'scale':'log'} for k in ('Icp','Rz','C1','C2','f0','Kvco')}
    a={'values':{k:{'value':1.} for k in t.guard}}; b=deepcopy(a); b['values']['Icp']['value']=10.
    assert t.distance(a,b)==pytest.approx(.5/(6**.5))
