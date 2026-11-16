"""New opt-in physical contracts; original Builder and formal Explorer preserved."""
from copy import deepcopy
from pathlib import Path
import pytest
from pll_allocation.agent.experiment_a_plus import read,ROOT
from pll_allocation.agent.multi_region_study import deterministic_plan,MultiTrial
from pll_allocation.agent.subregion_contracts import validate_multi_plan,intent_problem
from pll_allocation.exploration.physics_region_builder import build_physics_region
from pll_allocation.exploration.engine import model_identity
from pll_allocation.physics_mapping.model import fingerprint
from tools.stress_open_domain import scale_context


def inputs(spec):
    raw=read(ROOT/'experiments/initial_allocation_a_plus/frozen'/(spec+'.json'))
    physics=scale_context(raw)
    physics['numerical_resource_guard']={k:{'min':a['min'],'max':a['max']} for k,a in raw['parameters'].items()}
    return raw,physics


@pytest.mark.parametrize('spec',['SW','SN','ST'])
def test_rule_plan_compiles_distinct_real_builder_seeds_without_M1(spec):
    raw,physics=inputs(spec);plan=deterministic_plan(raw,physics)
    validate_multi_plan(plan,template=raw,physics=physics)
    hashes=[];domains=[]
    for intent in plan['regions']:
        domain,p=intent_problem(raw,intent,physics['scale_anchors_SI']);domains.append(domain['parameters'])
        req={'schema_version':'pll-physics-region-request-1.0','request_id':intent['region_id'],
            'problem_sha256':p['problem_sha256'],'model_fingerprint':model_identity()['model_sha256'],
            'strategy':intent['strategy'],'target_bw_fraction':intent['target_bw_fraction'],'physics_focus':['LF_SHAPE'],
            'tuning_preference':intent['tuning_preference'],'seed_count':3,'region_width_policy':'BALANCED',
            'budget':{'construction_attempts':64,'m1_calls':3},'evidence_ids':intent['evidence_ids']}
        prop=build_physics_region(p,req,model_fingerprint=model_identity()['model_sha256'],random_seed=1301,excluded=hashes)
        assert prop['seeds'] and prop['cost']['M1_calls']==0
        assert prop['seeds'][0]['parameter_sha256'] not in hashes
        hashes.extend(s['parameter_sha256'] for s in prop['seeds'])
    assert len(set(fingerprint(d) for d in domains))==3


@pytest.mark.parametrize('issue',['evidence','ratio','guard','budget','duplicate','priority','bw','tuning'])
def test_illegal_multi_intent_rejected_before_tools(issue):
    raw,physics=inputs('ST');plan=deterministic_plan(raw,physics);r=plan['regions'][0]
    if issue=='evidence':r['evidence_ids']=['FAKE']
    if issue=='ratio':r['c2_c1_ratio']=[1,1.01]
    if issue=='guard':r['c1_scale_decades']=[4,5]
    if issue=='budget':r['m1_budget']=64;plan['regions'][1]['m1_budget']=64
    if issue=='duplicate':plan['regions'][1]=deepcopy(r)
    if issue=='priority':r['priority']=2
    if issue=='bw':r['target_bw_fraction']=[0,.2]
    if issue=='tuning':r['kvco_scale_decades']=[-2.9,-2.5];r['f0_target_fraction']=[.1,.2]
    with pytest.raises(ValueError):validate_multi_plan(plan,template=raw,physics=physics)


def test_original_models_and_builder_unchanged_from_A_plus():
    source=read(ROOT/'experiments/initial_allocation_a_plus/frozen/source_manifest.json')
    from pll_allocation.agent.experiment_a_plus import sha
    for name in source:
        if name.startswith(('pll_allocation/physics_mapping/','pll_allocation/verification/')) or name=='pll_allocation/exploration/physics_region_builder.py':
            assert sha(ROOT/name)==source[name],name


@pytest.mark.parametrize('spec',['SW','SN','ST'])
def test_actual_execution_box_contains_its_exact_builder_seeds(tmp_path,spec):
    from pll_allocation.region_explorer.assessment import contains_parameters
    raw,physics=inputs(spec);trial=object.__new__(MultiTrial)
    trial.raw=raw;trial.physics=physics;trial.guard=raw['parameters'];trial.entry={'seed':1301}
    trial.cfg={'compiler_version':'coupled-intent-contained-slice-v2'}
    trial.constructions=[];trial.candidates=[];trial.regions={};trial.plans=[]
    trial.timed=lambda kind,name,fn:fn()
    for intent in deterministic_plan(raw,physics)['regions']:
        folder=tmp_path/intent['region_id'];folder.mkdir()
        r=trial.build_intent(intent,folder)
        for seed in r['proposal']['seeds']:
            assert contains_parameters(raw,r['bounds'],seed['parameters'])
        for change in trial.plans[-1]['derived_coordinate_roundoff']:
            assert abs(change['before']-change['after'])<1e-13


def test_coupled_intent_compiles_contained_slice_instead_of_false_contradiction():
    raw,physics=inputs('SN');r=deterministic_plan(raw,physics)['regions'][0]
    r['c1_scale_decades']=[-1,1];r['c2_c1_ratio']=[80,200]
    domain,p=intent_problem(raw,r,physics['scale_anchors_SI'])
    a=domain['parameters'];requested=[physics['scale_anchors_SI']['C1']*10**v for v in r['c1_scale_decades']]
    assert requested[0]<=a['C1']['min']<a['C1']['max']<=requested[1]
    assert a['C2']['min']/a['C1']['max']>=80*(1-1e-14)
    assert a['C2']['max']/a['C1']['min']<=200*(1+1e-14)
    assert a['C1']['max']/a['C1']['min']<100
