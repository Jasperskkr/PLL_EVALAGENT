"""Domain contracts, numerical invariants and actual short event checks."""
from copy import deepcopy
import json
import math
from pathlib import Path
import pytest
from pll_allocation.block_space import check_parameters, forward, load_model, make_candidate, validate_model
from pll_allocation.block_space.calibration import discrepancy_record
from pll_allocation.block_space.event_reference import compare_event, load_existing_simulator
from pll_allocation.block_space.sampling import abnormal_cases, representative_cases
from pll_allocation.physics_mapping.model import ModelError, Status, _crossing, fingerprint

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def model():
    return load_model(ROOT/'configs/BLOCK_SPACE_MODEL_V1.json')


def test_experiment_and_domain_exactly_preserve_stage1(model):
    old=json.loads((ROOT/'configs/physics_mapping_stage1_v2.json').read_text(encoding='utf-8'))
    assert model['experiment']==old
    assert model['experiment_freeze']['experiment_sha256']==fingerprint(old)
    assert model['experiment_freeze']['global_research_spec_frozen'] is False
    assert set(name for name,axis in model['variables'].items() if axis['kind']=='free_allocation_parameter')=={'Icp','Rz','C1','C2','f0','Kvco'}


@pytest.mark.parametrize('mutation',[
    lambda m:m['experiment']['system_spec']['metrics'][1].update(min=100000),
    lambda m:m['variables']['Icp']['range'].update(max=.001),
    lambda m:m['topology'].update(id='fractional_n'),
    lambda m:m['variables']['Kvco'].update(unit='rad/s/V'),
    lambda m:m['joint_constraints'].pop(),
    lambda m:m['variable_catalog'].pop(),
])
def test_changed_freeze_or_unmapped_model_rejected(model,mutation):
    mutation(model)
    with pytest.raises(ValueError):
        validate_model(model)


def test_declared_domain_not_same_as_validity_or_feasibility(model):
    nominal=forward(model,make_candidate(model))
    assert nominal['judgment']['verdict']=='M1_SPEC_PASS'
    unreachable=make_candidate(model,{'f0':60e6,'Kvco':10e6})
    domain=check_parameters(model,unreachable)
    assert domain['declared_domain']=='IN_DECLARED_DOMAIN'
    assert domain['model_validity']=='OUT_OF_DOMAIN'
    assert forward(model,unreachable)['judgment']['verdict']=='UNKNOWN'
    lowpm=forward(model,make_candidate(model,{'Icp':200e-6,'Kvco':40e6,'Rz':8000}))
    assert lowpm['domain']['model_validity']=='VALID'
    assert lowpm['judgment']['verdict']=='M1_SPEC_FAIL'
    assert lowpm['prediction']['factors']['F_LOOP']['routh_stable'] is True


def test_routh_difference_positive_at_declared_corners(model):
    for case in representative_cases(model):
        d=check_parameters(model,case['parameters'])
        if d['derived']:
            p={k:v['value'] for k,v in case['parameters']['values'].items()}
            expected=p['Icp']*p['Kvco']/p['N']*p['Rz']*p['C2']**2
            assert d['derived']['Routh_bc_minus_ad']==pytest.approx(expected,rel=1e-12)
            assert expected>0


def test_plan_is_deterministic_diverse_and_predeclared(model):
    cases=representative_cases(model)
    assert cases==representative_cases(model)
    assert len(cases)>=50
    assert len({fingerprint(c['parameters']) for c in cases})==len(cases)
    assert {'nominal','local_sensitivity','single_parameter_boundary','coupled_boundary',
        'capacitor_coupling','low_discrepancy','system_boundary_slice','tuning_boundary'} <= {c['category'] for c in cases}
    assert all(check_parameters(model,c['parameters'])['declared_domain']=='IN_DECLARED_DOMAIN' for c in cases)
    assert sum(c['event_selected'] for c in cases)>=15


def test_outside_domain_anomalies_cannot_pass(model):
    for case in abnormal_cases(model):
        result=forward(model,case['parameters'])
        assert result['domain']['declared_domain']=='OUT_OF_DECLARED_DOMAIN'
        assert result['judgment']['verdict']=='UNKNOWN'
        assert result['prediction'] is None


def test_multiple_and_absent_crossings_rejected_by_original_kernel():
    with pytest.raises(ModelError) as multiple:
        _crossing([1,2,3,4,5],lambda f: math.cos(math.pi*(f-1)), 'synthetic')
    assert multiple.value.status==Status.NUMERICAL_FAILURE
    assert 'found 2' in multiple.value.reason
    with pytest.raises(ModelError):
        _crossing([1,2,3],lambda f:1,'missing')
    with pytest.raises(ModelError):
        _crossing([1,2,3],lambda f:float('nan'),'nonfinite')


def test_equation_registry_sources_and_scope():
    registry=json.loads((ROOT/'configs/PLL_EQUATION_REGISTRY_V1.json').read_text(encoding='utf-8'))
    assert len(registry['equations'])==11
    for equation in registry['equations']:
        assert all(equation.get(key) for key in ('expression','inputs','outputs','units_and_conversions',
                    'model_level','source','domain','implementation','validation_evidence','limitations','what','how'))
        assert equation['model_level']=='M1'
        for source in equation['source_files']:
            import hashlib
            assert hashlib.sha256(Path(source['path']).read_bytes()).hexdigest()==source['sha256']


def test_calibration_record_separates_protocols_and_does_not_correct(model):
    p=make_candidate(model)
    kwargs=dict(metric='output_frequency_Hz',prediction=80e6,reference=80e6+.001,unit='Hz',
        prediction_protocol='conditional_locked_tuning_frequency',reference_protocol='event_tail_mean',
        evidence='case/file.json',classification='UNRESOLVED',recommended_action='check refinement first',
        known_limitations=['no BW injection'],comparability='CONDITIONAL_LOCKED_COMPARISON')
    row=discrepancy_record(model,p,**kwargs)
    assert row['raw_formula_modified'] is False
    assert row['prediction_error']['interpretation']=='CONDITIONAL'
    assert row['formula_version']==model['versions']['formula_version']
    with pytest.raises(ValueError):
        discrepancy_record(model,p,**dict(kwargs,comparability='SAME_PROTOCOL'))
    with pytest.raises(ValueError):
        discrepancy_record(model,p,**dict(kwargs,classification='AUTOMATICALLY_CORRECTED'))


def test_reference_snapshot_and_actual_short_event_simulation():
    pytest.importorskip('numpy')
    simulate,provenance=load_existing_simulator(ROOT/'data/behavioral_space_v1/reference')
    result=simulate(sim_time=2e-6,dt=1e-9,v0=.4,verbose=False)
    assert result['fout_avg']==pytest.approx(80e6,abs=.1)
    assert float(result['vfinal'])==pytest.approx(.4,abs=1e-8)
    assert result['clip_count']==0
    assert provenance['mode']=='byte_identical_read_only_reference'


def test_event_adapter_rejects_model_semantics_it_cannot_simulate(model):
    p=deepcopy(make_candidate(model))
    p['values']['PFD_reset_delay']['value']=1e-9
    def must_not_run(**kwargs):
        raise AssertionError('nonideal model must be rejected before execution')
    result=compare_event(p,must_not_run)
    assert result['status']=='UNSUPPORTED' and result['behavioral_calls']==0


def test_reference_blockspec_is_complete_scoped_and_bound(model):
    path=ROOT/'tests/fixtures/verification/REFERENCE_BLOCKSPEC.json'
    reference=json.loads(path.read_text(encoding='utf-8'))
    assert reference['validation_status']=='M1_VALIDATED'
    assert reference['M2_system_verdict']=='NOT_EVALUATED'
    assert reference['M1_result']['judgment']['verdict']=='M1_SPEC_PASS'
    assert reference['parameters']==make_candidate(model)
