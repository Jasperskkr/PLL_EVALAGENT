"""Research index must preserve frozen constraints and reject unsafe evidence mixing."""
from copy import deepcopy
import json
from pathlib import Path
import pytest

from pll_allocation.physics_mapping.registry import load_registry, query, route
from pll_allocation.physics_mapping.model import fingerprint
from pll_allocation.block_space.contracts import load_model, check_parameters

ROOT=Path(__file__).resolve().parents[1]
REGISTRY=ROOT/'docs/stage4_2/PHYSICS_MAPPING_REGISTRY.json'


def test_index_only_enables_exact_formal_constraints_and_never_executes():
    registry=load_registry(REGISTRY)
    assert {x['system_metric_id'] for x in registry['mappings'] if x['enabled_in_frozen_SystemSpec']} == {'output_frequency_Hz','BW_Hz','PM_deg'}
    for mid,capability in [('Vctrl_required_V','ANALYTICAL_INVERSE'),('BW_Hz','NUMERICAL_INVERSE'),
                           ('capture','BEHAVIORAL_ONLY'),('static_phase_error_deg','PHYSICS_SCREENING'),('RUR','UNSUPPORTED')]:
        choice=route(registry,mid)
        assert choice['inverse_capability']==capability
        assert not choice['executes_solver'] and not choice['may_change_SystemSpec'] and not choice['may_issue_behavioral_PASS']
    row=query(registry,'PM_deg');row['model_limitations'].append('mutation')
    assert 'mutation' not in query(registry,'PM_deg')['model_limitations']


@pytest.mark.parametrize('mutation',[
    lambda x:x['source_bindings'][0].update(sha256='wrong'),
    lambda x:x['source_bindings'].pop(),
    lambda x:x['model_versions'].update(formula_version='wrong'),
    lambda x:x['mappings'][5].update(enabled_in_frozen_SystemSpec=True),
    lambda x:x['mappings'][0].update(inverse_capability='FORWARD_MEANS_INVERSE'),
    lambda x:x['mappings'][0].update(equation_ids=['UNKNOWN']),
    lambda x:x['mappings'][2].update(unit='kHz'),
    lambda x:x.update(replaces_formal_model=True),
])
def test_registry_rejects_source_version_semantic_or_scope_changes(tmp_path,mutation):
    item=json.loads(REGISTRY.read_text(encoding='utf-8'));mutation(item)
    path=tmp_path/'bad.json';path.write_text(json.dumps(item),encoding='utf-8')
    with pytest.raises(ValueError):load_registry(path)


def test_only_declared_line_ending_difference_is_accepted_and_reported(tmp_path):
    registry=load_registry(REGISTRY)
    for row in registry['source_bindings']:
        path=tmp_path/row['path'];path.parent.mkdir(parents=True,exist_ok=True)
        content=(ROOT/row['path']).read_bytes().replace(b'\r\n',b'\n')
        path.write_bytes(content)
    reread=load_registry(REGISTRY,root=tmp_path)
    assert any(r['match']=='EXPLICIT_CRLF_LF_EQUIVALENCE' for r in reread['runtime_binding_checks'])
    path=tmp_path/'pll_allocation/allocation/physics.py';path.write_bytes(path.read_bytes()+b'\n# substantive edit\n')
    with pytest.raises(ValueError,match='source binding mismatch'):load_registry(REGISTRY,root=tmp_path)


def test_future_candidates_are_legal_complete_and_keep_negative_controls():
    model=load_model(ROOT/'configs/BLOCK_SPACE_MODEL_V1.json')
    item=json.loads((ROOT/'docs/stage4_2/M2_VALIDATION_CANDIDATES.json').read_text(encoding='utf-8'))
    cases=item['candidates'];assert len(cases)==10
    for case in cases:
        p=case['joint_block_spec'];domain=check_parameters(model,p)
        assert domain['declared_domain']=='IN_DECLARED_DOMAIN' and domain['model_validity']=='VALID'
        assert case['parameter_sha256']==fingerprint(p)==case['M1_prediction']['parameter_sha256']
        assert not case['verified_joint_block_spec'] and case['M2_status']=='NOT_RUN_STAGE4_2'
        assert not case['independence']['M2_used_for_selection']
        assert case['M1_judgment']['verdict'] in {'M1_SPEC_PASS','M1_SPEC_FAIL'}
    pair=cases[3:6]
    assert all(abs(x['M1_prediction']['metrics']['UGF_Hz']-140000)<1e-5 for x in pair)
    for name in ('C1','C2','Kvco','f0'):
        assert len({x['joint_block_spec']['values'][name]['value'] for x in pair})==1
    assert cases[6]['M1_judgment']['verdict']=='M1_SPEC_FAIL'
    holds=[x for x in cases if x['role']=='HOLDOUT'];assert len(holds)==2
    assert all(not x['independence']['used_for_method_tuning'] and not x['independence']['exact_match_to_reviewed_historical_anchor_set'] for x in holds)
    assert all(x['M1_judgment']['verdict']=='M1_SPEC_FAIL' for x in holds)  # no success-based selection


def test_numerical_scan_is_reproducible_finite_evidence_not_behavioral_accuracy():
    folder=ROOT/'experiments/stage4_2/readiness_05'
    summary=json.loads((folder/'summary.json').read_text(encoding='utf-8'))
    assert summary['scan_points']==1728 and summary['domain_counts']=={'OUT_OF_DOMAIN':216,'VALID':1512}
    assert summary['M1_spec_counts']=={'UNKNOWN':216,'M1_SPEC_FAIL':1300,'M1_SPEC_PASS':212}
    assert summary['numerical_consistency_passed'] and summary['research_M2_calls']==summary['research_LLM_calls']==0
    data=json.loads((folder/'coupling_and_sensitivity.json').read_text(encoding='utf-8'))
    for case in data['invariance_and_scale']:
        assert max(case['normalized_errors'].values())<1e-7
    assert data['nominal_log_derivatives']['Icp']['UGF_Hz']==pytest.approx(data['nominal_log_derivatives']['Kvco']['UGF_Hz'])


def test_existing_cp_sign_and_charge_units_are_explicit():
    from pll_allocation._legacy.physics.cp import equilibrium_timing,charge_window
    import math
    fref=10e6;icp=100e-6;q=1e-15
    dt=equilibrium_timing({'q0_C':q,'I_up_A':icp,'I_down_A':icp})
    assert dt==-q/icp
    phi=2*math.pi*fref*dt
    assert math.degrees(phi)==pytest.approx(-.036)
    limits=charge_window(.036,fref,icp,icp)
    assert limits['min_C']==pytest.approx(-q) and limits['max_C']==pytest.approx(q)
    # Nonzero charge is algebraic sign evidence, not a legal Stage1.5 M1/M2 operating condition.
