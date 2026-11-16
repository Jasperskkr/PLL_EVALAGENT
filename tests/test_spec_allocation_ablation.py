from copy import deepcopy
import math
import pytest
from pll_allocation.agent.experiment_a_plus import ROOT, read, sha
from pll_allocation.agent.spec_allocation_ablation import (
    subdomain, inverse_stream, loop_signature, equivalent_signature, physics_context,
    AblationTrial, SEEDS, ALL,
)
from pll_allocation.exploration.contracts import resolve_problem, make_parameters
from pll_allocation.exploration.physics_region_builder import build_physics_region
from tools.stress_open_domain import scale_context


def problem(spec='SN'):
    return read(ROOT/'experiments/initial_allocation_a_plus/frozen'/(spec+'.json'))


def test_scale_default_is_exactly_preserved_and_guard_override_is_fixed():
    p=problem()
    assert scale_context(p)==scale_context(p,z_gauge=1000.)
    contexts=[physics_context(p,z) for z in (100.,1000.,10000.)]
    assert all(c['numerical_resource_guard']==contexts[0]['numerical_resource_guard'] for c in contexts)
    for c,z in zip(contexts,(100.,1000.,10000.)):
        assert c['impedance_gauge_Ohm']==z
        assert c['scale_anchors_SI']['C1']==pytest.approx(1/(2*math.pi*10e6*z))


@pytest.mark.parametrize('value',[0,-1,float('nan'),float('inf'),True])
def test_bad_gauge_rejected(value):
    with pytest.raises(ValueError):scale_context(problem(),z_gauge=value)


@pytest.mark.parametrize('spec',['SW','SN','ST'])
def test_S1_S2_share_domain_and_all_nonfirst_shape_draws(spec):
    p=resolve_problem(subdomain(problem(spec),{k:[.1,.9] for k in ALL}))
    kwargs=dict(seed=1301,attempts=63,max_seeds=63,target_fraction=(.5,.5),tuning='INTERIOR')
    a=list(inverse_stream(p,mode='S1',**kwargs));b=list(inverse_stream(p,mode='S2',**kwargs))
    assert len(a)==len(b)==63
    assert not a[0]['corner_priority'] and b[0]['corner_priority']
    assert b[0]['C1_F']==p['parameters']['C1']['min']
    assert b[0]['C2_F']==p['parameters']['C2']['max']
    for x,y in zip(a[1:],b[1:]):
        for key in ('C1_F','C2_F','shape_x','target_BW_Hz','status','parameter_sha256'):
            assert x.get(key)==y.get(key)


def test_original_model_judgment_builder_explorer_inverse_unchanged():
    manifest=read(ROOT/'experiments/stage7_8_multiregion_20261113_02/frozen/source_manifest.json')
    for name in manifest:
        if name.startswith(('pll_allocation/physics_mapping/','pll_allocation/verification/','pll_allocation/region_explorer/')) or name in (
            'pll_allocation/exploration/contracts.py','pll_allocation/exploration/physics_region_builder.py','pll_allocation/allocation/physics.py'):
            assert sha(ROOT/name)==manifest[name],name


def test_scale_equivalence_uses_loop_not_parameter_distance():
    p=resolve_problem(problem());parameters=make_parameters(p)
    scaled=deepcopy(parameters)
    for k in ('C1','C2','Icp'):scaled['values'][k]['value']*=10
    scaled['values']['Rz']['value']/=10
    assert equivalent_signature(loop_signature(parameters),loop_signature(scaled))
    scaled['values']['Rz']['value']*=1.01
    assert not equivalent_signature(loop_signature(parameters),loop_signature(scaled))


def test_S0_schedule_never_invokes_inverse_or_scale(monkeypatch,tmp_path):
    import pll_allocation.agent.spec_allocation_ablation as module
    def forbidden(*args,**kwargs):raise AssertionError('inverse leak')
    monkeypatch.setattr(module,'inverse_at_shape',forbidden)
    monkeypatch.setattr(module,'physics_context',forbidden)
    obj=object.__new__(AblationTrial)
    obj.root=tmp_path;obj.raw=problem();obj.entry={'arm':'S0'};obj.task='task1'
    obj.cfg={'model':{},'task_definitions':{'task1':{'fixed_region_normalized':{k:[.1,.9] for k in ALL}}}}
    obj.limit=128;obj.explorers=[];obj.error=None;obj.legal=None
    recorded=[];obj.region=lambda *args,**kwargs:recorded.append((args,kwargs));obj.finish=lambda:recorded
    result=obj.run()
    assert result[0][0][3]=='S0'


def test_source_budget_and_three_region_prompt_preregistered():
    from pll_allocation.agent.spec_allocation_ablation import PROMPT
    assert 'exactly THREE' in PROMPT
    assert '43' in PROMPT and '42' in PROMPT
    assert 'no feedback/replanning' in PROMPT


def test_executor_error_is_not_hidden_by_existing_PASS(tmp_path):
    from types import SimpleNamespace
    obj=object.__new__(AblationTrial);obj.root=tmp_path
    obj.timed=lambda category,name,func:func()
    ex=SimpleNamespace(rows=[],execute=lambda *args,**kwargs:{'failure':{'type':'ToolException','reason':'bad'},'status':'ACTION_ERROR'})
    with pytest.raises(ValueError,match='ACTION_ERROR'):
        obj.execute(ex,{'search_method':'SOBOL','decision_id':'TEST'})
