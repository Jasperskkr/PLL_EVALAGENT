"""VCO delivery uses real M1 and native multi-point evidence; no verdict promotion."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from pll_allocation.agent.handoff import validate_handoff
from pll_allocation.agent.spec_allocation import run_spec_allocation
from pll_allocation.exploration.contracts import check_candidate, judge, load_problem, make_parameters
from pll_allocation.exploration.engine import model_identity
from pll_allocation.physics_mapping.model import evaluate, fingerprint
from pll_allocation.vco_sizing.contract import (FEEDBACK_SCHEMA, UNITS, assess_feedback, build_guidance,
                                              export_guidance, validate_guidance)
from pll_allocation.vco_sizing.revalidation import prepare_revalidation

ROOT = Path(__file__).resolve().parents[1]
CONFIG = {'schema_version': 'pll-spec-allocation-1.0', 'target_count': 5, 'm2_budget': 0,
          'm1_budget': 40, 'initial_search_m1_budget': 16}
REF = {'uri': 'simulation/measurement.json', 'sha256': 'a'*64}
ENV = {'pdk': 'TEST_PDK', 'corner': 'tt', 'temperature_c': 27, 'supply_v': 1.2}


@pytest.fixture(scope='module')
def nominal(tmp_path_factory):
    out = tmp_path_factory.mktemp('vco_contract')/'nominal'
    result = run_spec_allocation(ROOT/'configs/problems/nominal.json', out, config=CONFIG)
    path = out/'initial/verification_handoff.json'
    return path, json.loads(path.read_text(encoding='utf-8')), result


def guidance(h, **options):
    return build_guidance(h, source_uri='TEST:handoff', options=options)


def measured(g, *, kv=35e6, v=.5):
    entry = g['candidates'][0]; target = entry['target_frequency_hz']
    return {'schema_version': FEEDBACK_SCHEMA, 'units': deepcopy(UNITS),
        **{k: entry[k] for k in ('source_candidate_id', 'source_candidate_sha256', 'source_handoff_sha256', 'problem_sha256')},
        'experiment_id': 'TEST:physical-vco-01', 'target_frequency_hz': target,
        'mos_design': {'netlist': REF, 'sizes_and_biases': {'M1': {'w_m': 2e-6, 'l_m': .18e-6}, 'ibias_a': 100e-6}},
        'conditions': ENV, 'evidence': [REF], 'measurement_method': 'Transient periods; central secant around target',
        'validation_status': 'MEASURED', 'failure_reasons': [], 'startup_status': 'PASS', 'divider_drive_status': 'PASS',
        'vco_valid_control_voltage': {'min': .1, 'max': 1.1, 'unit': 'V'},
        'cp_compliance': {'min': .1, 'max': 1.1, 'unit': 'V', 'conditions': ENV, 'evidence': [REF],
                          'source_candidate_sha256': entry['source_candidate_sha256']},
        'target_reachable': True, 'frequency_tolerance_hz': 1,
        'vlock_v': v, 'kvco_local_hz_per_v': kv, 'f0_local_hz': target-kv*v,
        'kvco_extraction_voltages_v': [v-.01, v+.01],
        'tuning_samples': [{'vctrl_v': x, 'frequency_hz': target+kv*(x-v)} for x in (.1, v-.01, v, v+.01, 1.1)]}


def new_problem():
    p = json.loads((ROOT/'configs/problems/nominal.json').read_text(encoding='utf-8'))
    p['problem_id'] = 'TEST:independent-measured-vco'
    return p


def test_export_does_not_mutate_handoff_hash_or_model(nominal, tmp_path):
    path, h, r = nominal
    before = path.read_bytes(); identity = model_identity(); saved = deepcopy(h)
    out = tmp_path/'vco_sizing_guidance.json'
    g = export_guidance(path, out)
    assert path.read_bytes() == before and h == saved and model_identity() == identity
    assert validate_handoff(h) == h['recommended_nominal']['parameters']
    assert g['source_file_sha256'] == hashlib.sha256(before).hexdigest()
    assert g['source_handoff_sha256'] == h['handoff_sha256']
    assert g['candidates'][0]['source_candidate_sha256'] == fingerprint(h['recommended_nominal']['parameters'])
    assert not (path.parent/'vco_sizing_guidance.json').exists()
    assert r['M2_supported_pass_count'] == 0 and r['M2_status'] == 'NOT_EVALUATED'
    with pytest.raises(FileExistsError):
        export_guidance(path, out)


def test_target_units_and_unconfirmed_cp_range(nominal):
    _, h, _ = nominal; g = guidance(h); e = g['candidates'][0]
    p = h['recommended_nominal']['parameters']['values']
    assert e['target_frequency_hz'] == p['N']['value']*p['f_ref']['value'] == 80e6
    assert e['preferred_vlock_v'] == (80e6-p['f0']['value'])/p['Kvco']['value']
    assert e['units']['preferred_vlock_v'] == 'V' and e['units']['preferred_kvco_hz_per_v'] == 'Hz/V'
    assert e['units']['target_frequency_hz'] == 'Hz'
    assert not e['exact_f0_match_required'] and not e['exact_kvco_match_required']
    assert e['cp_compliance'] is None and not e['control_voltage_limits']['physically_verified']
    assert e['joint_cp_vco_valid_interval_status'].startswith('UNCONFIRMED')
    assert e['source_evidence_status']['M2'] == 'NOT_EVALUATED'


def test_nominal_deviation_does_not_fail_mos_or_promote_system_verdict(nominal):
    _, h, _ = nominal
    policy = {'required_tuning_margin': {'voltage_v': .05, 'frequency_hz': 1e6}}
    g = guidance(h, **policy)
    f = measured(g); before = deepcopy(h); r = assess_feedback(f, g, h, options=policy)
    assert r['physical_status'] == 'READY_FOR_SYSTEM_REVALIDATION'
    assert r['nominal_parameter_errors']['target_match_status'] == 'NOMINAL_DEVIATION'
    assert r['nominal_parameter_errors']['kvco_error_hz_per_v'] != 0
    assert r['actual_local_parameters']['f0_local_hz'] == 62.5e6
    assert 'NOT_MEASURED_ZERO_VOLT' in r['nominal_parameter_errors']['f0_local_semantics']
    assert r['M1_status'] == r['M2_status'] == 'NOT_EVALUATED' and not r['FULL_SYSTEMSPEC_CERTIFIED'] and h == before


def test_unreachable_is_explicit_and_never_converted(nominal):
    _, h, _ = nominal; g = guidance(h); f = measured(g)
    f.update(target_reachable=False, vlock_v=None, kvco_local_hz_per_v=None, f0_local_hz=None,
             failure_reasons=['Target above measured tuning range'])
    f['tuning_samples'] = [{'vctrl_v': .1, 'frequency_hz': 55e6}, {'vctrl_v': 1.1, 'frequency_hz': 70e6}]
    r = assess_feedback(f, g, h)
    assert r['reachability_status'] == 'FREQUENCY_UNREACHABLE_IN_REPORTED_SCAN'
    assert r['physical_status'] == 'REQUIREMENTS_FAILED' and r['M2_status'] == 'NOT_EVALUATED'
    with pytest.raises(ValueError, match='measured target'):
        prepare_revalidation(f, g, h, problem=new_problem())


@pytest.mark.parametrize('state', ['FAILED', 'INCOMPLETE'])
def test_failed_or_incomplete_scan_without_measurements_is_valid_feedback(nominal, state):
    _, h, _ = nominal; g = guidance(h); f = measured(g)
    f.update(validation_status=state, startup_status='FAIL' if state == 'FAILED' else 'UNKNOWN',
        divider_drive_status='UNKNOWN', failure_reasons=['No valid oscillation measurements'],
        tuning_samples=[], vco_valid_control_voltage=None, target_reachable=None,
        vlock_v=None, kvco_local_hz_per_v=None, f0_local_hz=None)
    r = assess_feedback(f, g, h)
    assert r['reachability_status'] == 'UNKNOWN_NO_VALID_TUNING_MEASUREMENTS'
    assert r['physical_status'] == ('REQUIREMENTS_FAILED' if state == 'FAILED' else 'UNKNOWN')
    assert r['M2_status'] == 'NOT_EVALUATED' and r['failure_reasons'] == f['failure_reasons']


def test_unknown_cp_margin_and_validation_stay_unknown(nominal):
    _, h, _ = nominal; g = guidance(h); f = measured(g); f['cp_compliance'] = None
    r = assess_feedback(f, g, h)
    assert r['physical_checks']['common_voltage'] == 'UNKNOWN'
    assert r['physical_checks']['margin_voltage_v'] == 'UNKNOWN'
    assert r['physical_status'] == 'UNKNOWN'
    f['cp_compliance'] = measured(g)['cp_compliance']; f['validation_status'] = 'INCOMPLETE'
    assert assess_feedback(f, g, h)['physical_status'] == 'UNKNOWN'


def test_explicit_hard_constraints_remain_hard(nominal):
    _, h, _ = nominal
    policy = {'hard_constraints': {'kvco_local_hz_per_v': {'min': 10e6, 'max': 20e6, 'unit': 'Hz/V'}}}
    g = guidance(h, **policy)
    r = assess_feedback(measured(g), g, h, options=policy)
    assert r['physical_checks']['kvco_local_hz_per_v'] == 'FAIL'
    assert r['physical_status'] == 'REQUIREMENTS_FAILED'
    converted = prepare_revalidation(measured(g), g, h, problem=new_problem(), options=policy)
    assert converted['status'] == 'PHYSICAL_REQUIREMENTS_FAILED' and converted['parameters'] is None
    policy['hard_constraints']['kvco_local_hz_per_v'] = {'min': 35e6, 'max': 35e6, 'unit': 'Hz/V'}
    g = guidance(h, **policy)
    assert assess_feedback(measured(g), g, h, options=policy)['physical_checks']['kvco_local_hz_per_v'] == 'PASS'


@pytest.mark.parametrize('mutation', ['unit', 'source', 'slope', 'intercept', 'reachability', 'conditions', 'scan', 'cp_candidate'])
def test_bad_feedback_cannot_become_success(nominal, mutation):
    _, h, _ = nominal; g = guidance(h); f = measured(g)
    if mutation == 'unit': f['units']['kvco_local_hz_per_v'] = 'rad/s/V'
    if mutation == 'source': f['source_handoff_sha256'] = 'bad'
    if mutation == 'slope': f['kvco_local_hz_per_v'] *= 2
    if mutation == 'intercept': f['f0_local_hz'] += 100
    if mutation == 'reachability': f['tuning_samples'][2]['frequency_hz'] += 1e6
    if mutation == 'conditions': f['cp_compliance'] = deepcopy(f['cp_compliance']); f['cp_compliance']['conditions'] = ENV | {'corner': 'ss'}
    if mutation == 'scan': f['tuning_samples'] = f['tuning_samples'][1:]
    if mutation == 'cp_candidate': f['cp_compliance']['source_candidate_sha256'] = '0'*64
    with pytest.raises(ValueError): assess_feedback(f, g, h)


def test_guidance_and_source_tampering_rejected(nominal):
    _, h, _ = nominal; g = guidance(h)
    g['candidates'][0]['preferred_kvco_hz_per_v'] *= 2
    with pytest.raises(ValueError, match='binding'): validate_guidance(g, h)
    changed = deepcopy(h); changed['recommended_nominal']['parameter_sha256'] = 'bad'
    with pytest.raises(ValueError): build_guidance(changed, source_uri='TEST')


def test_original_search_domain_is_distinct_from_measured_domain(nominal):
    _, h, _ = nominal; g = guidance(h); f = measured(g, kv=85e6)
    actual = deepcopy(h['recommended_nominal']['parameters'])
    actual['values']['Kvco']['value'] = 85e6; actual['values']['f0']['value'] = 37.5e6
    assert check_candidate(h['problem'], actual)['status'] == 'INVALID_CANDIDATE'
    assert assess_feedback(f, g, h)['reachability_status'] == 'MEASURED_TARGET_REACHED'
    r = prepare_revalidation(f, g, h, problem=new_problem())
    assert r['status'] == 'REVALIDATION_DOMAIN_REJECTED'
    p = new_problem(); p['parameters']['Kvco']['max'] = 90e6; p['parameters']['f0']['min'] = 30e6
    r = prepare_revalidation(f, g, h, problem=p)
    assert r['status'] == 'READY_FOR_FORMAL_REVALIDATION'
    assert r['original_search_domain_status'] == 'OUTSIDE_ORIGINAL_SEARCH_DOMAIN'
    assert set(r['outside_original_axes']) == {'Kvco', 'f0'}
    assert r['problem']['specs'] == h['problem']['specs'] and not r['FULL_SYSTEMSPEC_CERTIFIED']
    m1 = judge(r['problem'], r['parameters'], evaluate(r['parameters']))
    lock = next(c for c in m1['constraints'] if c['metric'] == 'lock_time_s')
    assert lock['support_status'] == 'PENDING_M2' and lock['status'] == 'UNKNOWN'
    assert r['M2_status'] == 'NOT_EVALUATED'


def test_cannot_reuse_problem_identity_or_relax_system_spec(nominal):
    _, h, _ = nominal; g = guidance(h); f = measured(g); p = new_problem()
    p['problem_id'] = h['problem']['problem_id']
    with pytest.raises(ValueError, match='independent'): prepare_revalidation(f, g, h, problem=p)
    p = new_problem(); p['specs'][0]['max'] *= 2
    with pytest.raises(ValueError, match='SystemSpec'): prepare_revalidation(f, g, h, problem=p)


def test_default_deterministic_fingerprints_match_stable_baseline(nominal):
    _, _, r = nominal
    expected = ['520c7bd154522a92e13a690f4ade41f1489b2069f204cf90ac0661c9ac8bd2aa',
                '0f7d5eb93e1d7d38b92dafe7521d49445d7d9a4775e49cd58a74f919d654e0fa',
                'fcef11e6f1560d8e6f2a3fb3984f159279aaee4c94d99e2e6ff7c2aa1b5a345a',
                '5b77c406214cd61b7562ec3bb50eb1c5c8cbf55acceb3f386032c392194b6194',
                '56a576ca1649b538e65e4d84842c42f107e90adaecfea08fc7d9edae3152a495']
    assert [c['parameter_sha256'] for c in r['candidates']] == expected
    assert r['cost']['M1_calls'] == 6 and r['cost']['LLM_calls'] == 0 and r['status'] == 'M1_POOL_ONLY'


def test_real_target_with_illegal_global_tangent_is_not_mos_failure(nominal):
    _, h, _ = nominal; g = guidance(h); f = measured(g, kv=180e6)
    r = assess_feedback(f, g, h)
    assert r['reachability_status'] == 'MEASURED_TARGET_REACHED' and r['actual_local_parameters']['f0_local_hz'] < 0
    assert r['physical_status'] != 'REQUIREMENTS_FAILED'
    assert prepare_revalidation(f, g, h, problem=new_problem())['status'] == 'REVALIDATION_DOMAIN_REJECTED'


def test_stable_native_anchor_is_bound_to_parameters_not_only_run_id(nominal, tmp_path):
    from pll_allocation.verification.build_identity import check_build
    from pll_allocation.verification.run_suite import capture_pair
    try:
        check_build()
    except (FileNotFoundError, RuntimeError) as error:
        pytest.skip('native build unavailable: '+str(error))
    _, _, r = nominal
    row = next(c for c in r['candidates'] if c['evidence_id'] == 'M1_SAMPLE:0000005')
    assert row['parameter_sha256'] == '0f7d5eb93e1d7d38b92dafe7521d49445d7d9a4775e49cd58a74f919d654e0fa'
    assert row['metrics']['BW_Hz'] == pytest.approx(225e3, abs=.01)
    assert row['metrics']['PM_deg'] == pytest.approx(77.23570951350865, abs=1e-6)
    capture = capture_pair(tmp_path/'capture', row['parameters'], .15, 160e-6)
    assert capture['numerical_converged'] and capture['reliable_capture_status'] == 'CAPTURED_WITHIN_WINDOW'
    assert capture['fine']['lock_time_s'] == pytest.approx(35e-6, abs=1e-9)


@pytest.fixture(scope='module')
def native_multi(tmp_path_factory):
    from pll_allocation.verification.build_identity import check_build
    try:
        check_build()
    except (FileNotFoundError, RuntimeError) as error:
        pytest.skip('native build unavailable: '+str(error))
    root = tmp_path_factory.mktemp('vco_native')/'run'
    run_spec_allocation(ROOT/'configs/problems/nominal.json', root,
        config=CONFIG | {'target_count': 5, 'm2_target_count': 2, 'm2_budget': 4})
    h = json.loads((root/'sizing_handoff.json').read_text(encoding='utf-8'))
    assert len(h['candidates']) >= 2
    return root, h


def test_every_native_delivered_candidate_has_bound_guidance(native_multi):
    root, h = native_multi; before = (root/'sizing_handoff.json').read_bytes()
    g = export_guidance(root/'sizing_handoff.json')
    assert len(g['candidates']) == h['candidate_count'] >= 2
    for e, row in zip(g['candidates'], h['candidates']):
        p = row['parameters']['values']
        assert e['source_candidate_id'] == row['evidence_id']
        assert e['source_candidate_sha256'] == row['parameter_sha256']
        assert e['source_handoff_sha256'] == fingerprint(h)
        assert e['native_verification_handoff_sha256'] == row['M2_observations'][-1]['request']['handoff']['handoff_sha256']
        assert e['preferred_vlock_v'] == (80e6-p['f0']['value'])/p['Kvco']['value']
        assert e['source_evidence_status']['M2_supported'] == 'PASS'
    assert (root/'sizing_handoff.json').read_bytes() == before
    assert validate_guidance(g, h) == g


def shifted_measurement(g, *, frequency_hz, kv=35e6, v=.5):
    f = measured(g, kv=kv, v=v)
    offset = frequency_hz-f['target_frequency_hz']
    for point in f['tuning_samples']:
        point['frequency_hz'] += offset
    f['f0_local_hz'] = frequency_hz-kv*v
    return f


def test_near_target_counterexample_never_translates_measured_curve(nominal):
    _, h, _ = nominal; g = guidance(h)
    f = shifted_measurement(g, frequency_hz=80.4e6)
    f['frequency_tolerance_hz'] = 500e3
    r = assess_feedback(f, g, h)
    assert r['actual_local_parameters']['f0_local_hz'] == 62.9e6
    assert r['frequency_residual_hz'] == 400e3
    assert not r['target_operating_point_confirmed']
    assert r['reachability_status'] != 'MEASURED_TARGET_REACHED'
    assert r['target_root']['status'] == 'INTERPOLATED_NOT_REMEASURED'
    assert r['target_root']['estimated_vlock_v'] != f['vlock_v']
    converted = prepare_revalidation(f, g, h, problem=new_problem())
    assert converted['status'] == 'TARGET_OPERATING_POINT_UNCONFIRMED' and converted['parameters'] is None
    f['f0_local_hz'] = 62.5e6
    with pytest.raises(ValueError, match='intercept'): assess_feedback(f, g, h)


def test_stage6_finite_precision_anchor_accepts_trusted_measurement(nominal):
    _, h, _ = nominal
    policy = {'target_confirmation': {'max_frequency_error_hz': 4000}}
    g = guidance(h, **policy)
    f = shifted_measurement(g, frequency_hz=79.9987e6, kv=22.365e6, v=.47214)
    f['frequency_tolerance_hz'] = 2000
    f['target_point_measurement'] = {'frequency_uncertainty_hz': 1500,
        'method': 'Transient period measurement with finite-window error bound', 'evidence': [REF]}
    r = assess_feedback(f, g, h, options=policy)
    assert r['target_operating_point_confirmed'] and r['frequency_residual_hz'] == -1300
    assert r['target_root']['status'] == 'MEASURED_WITHIN_TRUSTED_ACCURACY'
    assert r['actual_local_parameters']['f0_local_hz'] == pytest.approx(79.9987e6-22.365e6*.47214)
    converted = prepare_revalidation(f, g, h, problem=new_problem(), options=policy)
    assert converted['status'] == 'READY_FOR_FORMAL_REVALIDATION'
    assert converted['parameters']['values']['f0']['value'] == r['actual_local_parameters']['f0_local_hz']
    assert converted['parameters']['values']['Icp'] == h['recommended_nominal']['parameters']['values']['Icp']
    assert converted['M1_status'] == converted['M2_status'] == 'NOT_EVALUATED'


@pytest.mark.parametrize('problem', ['no_evidence', 'inflated_uncertainty', 'unlinked_evidence', 'incomplete'])
def test_feedback_cannot_self_authorize_frequency_accuracy(nominal, problem):
    _, h, _ = nominal; policy = {'target_confirmation': {'max_frequency_error_hz': 4000}}
    g = guidance(h, **policy); f = shifted_measurement(g, frequency_hz=79.9987e6)
    f['frequency_tolerance_hz'] = 500e3
    if problem != 'no_evidence':
        f['target_point_measurement'] = {'frequency_uncertainty_hz': 1500, 'method': 'TEST:period bound', 'evidence': [REF]}
    if problem == 'inflated_uncertainty': f['target_point_measurement']['frequency_uncertainty_hz'] = 500e3
    if problem == 'unlinked_evidence':
        f['target_point_measurement']['evidence'] = [REF | {'sha256': 'b'*64}]
        with pytest.raises(ValueError, match='evidence'): assess_feedback(f, g, h, options=policy)
        return
    if problem == 'incomplete': f['validation_status'] = 'INCOMPLETE'
    r = assess_feedback(f, g, h, options=policy)
    assert not r['target_operating_point_confirmed'] and r['physical_status'] != 'READY_FOR_SYSTEM_REVALIDATION'


@pytest.mark.parametrize('mutation', ['delete_hard', 'loosen_kvco', 'loosen_margin'])
def test_independent_policy_detects_deleted_or_relaxed_requirements(nominal, mutation):
    _, h, _ = nominal
    policy = {'hard_constraints': {'kvco_local_hz_per_v': {'min': 10e6, 'max': 20e6, 'unit': 'Hz/V'}},
              'required_tuning_margin': {'voltage_v': .1, 'frequency_hz': None}}
    g = guidance(h, **policy)
    assert validate_guidance(g, h, options=policy) == g
    with pytest.raises(ValueError): validate_guidance(g, h)
    changed = deepcopy(g)
    if mutation == 'delete_hard': changed['candidates'][0]['hard_constraints'] = {}
    if mutation == 'loosen_kvco': changed['candidates'][0]['hard_constraints']['kvco_local_hz_per_v']['max'] = 30e6
    if mutation == 'loosen_margin': changed['candidates'][0]['required_tuning_margin']['voltage_v'] = 0
    with pytest.raises(ValueError): validate_guidance(changed, h, options=policy)


def cp_policy(g, lo=.3, hi=.6):
    return {'cp_compliance': measured(g)['cp_compliance'] | {'min': lo, 'max': hi}}


@pytest.mark.parametrize('v,expected', [(.7, 'FAIL'), (.5, 'PASS')])
def test_cp_feedback_cannot_expand_bound_upstream_interval(nominal, v, expected):
    _, h, _ = nominal; policy = cp_policy(guidance(h)); g = guidance(h, **policy)
    f = measured(g, v=v); r = assess_feedback(f, g, h, options=policy)
    assert r['common_valid_voltage_interval'] == {'min': .3, 'max': .6, 'unit': 'V'}
    assert r['physical_checks']['common_voltage'] == expected
    assert len(r['cp_evidence_sources']) == 2
    if v == .7:
        assert prepare_revalidation(f, g, h, problem=new_problem(), options=policy)['status'] == 'PHYSICAL_REQUIREMENTS_FAILED'


def test_cp_intersection_empty_or_incomparable_is_never_pass(nominal):
    _, h, _ = nominal; policy = cp_policy(guidance(h)); g = guidance(h, **policy); f = measured(g)
    f['cp_compliance'].update(min=.7, max=1.1)
    r = assess_feedback(f, g, h, options=policy)
    assert r['joint_valid_interval_status'] == 'NO_COMMON_INTERVAL'
    assert r['common_valid_voltage_interval'] is None and r['physical_checks']['common_voltage'] == 'FAIL'
    f = measured(g); f['cp_compliance']['conditions'] = ENV | {'corner': 'ss'}
    with pytest.raises(ValueError, match='conditions'): assess_feedback(f, g, h, options=policy)
    f = measured(g); f['cp_compliance']['source_candidate_sha256'] = '0'*64
    with pytest.raises(ValueError, match='candidate'): assess_feedback(f, g, h, options=policy)


def test_api_parsed_validation_reports_byte_check_not_performed(nominal):
    _, h, _ = nominal; g = guidance(h)
    r = assess_feedback(measured(g), g, h)
    assert r['guidance_validation']['source_file_bytes_status'] == 'NOT_CHECKED_PARSED_JSON_ONLY'
    assert r['guidance_validation']['policy_status'] == 'MATCHED_DEFAULT_POLICY'
    assert r['guidance_validation']['authentication_status'] == 'NOT_AUTHENTICATED'


def test_legacy_exact_feedback_is_compatible_but_custom_policy_is_not_inferred(nominal):
    _, h, _ = nominal
    for policy in ({}, {'required_tuning_margin': {'voltage_v': .1, 'frequency_hz': None}}):
        g = guidance(h, **policy); g.pop('contract_revision'); g.pop('design_policy_sha256')
        for e in g['candidates']: e.pop('target_confirmation')
        assert validate_guidance(g, h, options=policy) == g
        r = assess_feedback(measured(g), g, h, options=policy)
        assert r['target_operating_point_confirmed'] and r['target_root']['status'] == 'LEGACY_EXACT_SAMPLE'
        if policy:
            with pytest.raises(ValueError): validate_guidance(g, h)


def test_trusted_hard_range_allows_nominal_gain_deviation(nominal):
    _, h, _ = nominal
    policy = {'hard_constraints': {'kvco_local_hz_per_v': {'min': 30e6, 'max': 40e6, 'unit': 'Hz/V'}}}
    g = guidance(h, **policy); r = assess_feedback(measured(g), g, h, options=policy)
    assert r['physical_checks']['kvco_local_hz_per_v'] == 'PASS'
    assert r['nominal_parameter_errors']['target_match_status'] == 'NOMINAL_DEVIATION'
    assert r['physical_status'] != 'REQUIREMENTS_FAILED'


def test_unknown_cp_is_recorded_without_physical_compliance_promotion(nominal):
    _, h, _ = nominal; g = guidance(h); f = measured(g); f['cp_compliance'] = None
    r = prepare_revalidation(f, g, h, problem=new_problem())
    assert r['status'] == 'READY_FOR_FORMAL_REVALIDATION'
    assert r['physical_assessment']['physical_checks']['common_voltage'] == 'UNKNOWN'
    assert r['physical_assessment']['joint_valid_interval_status'] == 'UNCONFIRMED'
    assert r['physical_assessment']['physical_status'] == 'UNKNOWN'
    assert r['M1_status'] == r['M2_status'] == 'NOT_EVALUATED' and not r['FULL_SYSTEMSPEC_CERTIFIED']


def test_source_file_sha_is_distinct_from_canonical_identity(nominal, tmp_path):
    path, h, _ = nominal; g = export_guidance(path, tmp_path/'guidance.json')
    original = path.read_bytes()
    validate_guidance(g, h, source_handoff_path=path)
    reformatted = tmp_path/'reformatted_handoff.json'
    reformatted.write_text(json.dumps(h, separators=(',', ':')), encoding='utf-8')
    assert json.loads(reformatted.read_text(encoding='utf-8')) == h
    with pytest.raises(ValueError, match='file.*SHA256'):
        validate_guidance(g, h, source_handoff_path=reformatted)
    changed = deepcopy(g); changed['source_file_sha256'] = '0'*64
    with pytest.raises(ValueError, match='file.*SHA256'): validate_guidance(changed, h, source_handoff_path=path)
    assert path.read_bytes() == original


@pytest.mark.parametrize('command', ['assess', 'prepare'])
def test_cli_requires_original_policy_and_checks_source_bytes(nominal, tmp_path, monkeypatch, command):
    import sys
    from pll_allocation.vco_sizing.__main__ import main
    path, h, _ = nominal; policy = {'required_tuning_margin': {'voltage_v': .1, 'frequency_hz': None}}
    g = export_guidance(path, tmp_path/'guidance.json', options=policy)
    inputs = {'feedback': measured(g), 'options': policy, 'problem': new_problem()}
    for name, value in inputs.items():
        (tmp_path/(name+'.json')).write_text(json.dumps(value), encoding='utf-8')
    args = ['vco_sizing', command, '--handoff', str(path), '--guidance', str(tmp_path/'guidance.json'),
            '--feedback', str(tmp_path/'feedback.json'), '--out', str(tmp_path/'result.json')]
    if command == 'prepare': args += ['--problem', str(tmp_path/'problem.json')]
    monkeypatch.setattr(sys, 'argv', args)
    with pytest.raises(ValueError): main()
    args += ['--options', str(tmp_path/'options.json')]
    monkeypatch.setattr(sys, 'argv', args); main()
    saved = json.loads((tmp_path/'result.json').read_text(encoding='utf-8'))
    assessment = saved if command == 'assess' else saved['physical_assessment']
    assert assessment['guidance_validation']['source_file_bytes_status'] == 'VERIFIED'
    bad = tmp_path/'bad.json'; bad.write_text(json.dumps(h), encoding='utf-8')
    args[args.index('--handoff')+1] = str(bad)
    args[args.index('--out')+1] = str(tmp_path/'bad_result.json')
    monkeypatch.setattr(sys, 'argv', args)
    with pytest.raises(ValueError, match='file.*SHA256'): main()
    assert not (tmp_path/'bad_result.json').exists()


def test_multi_native_evidence_cannot_be_downgraded_to_test_or_forged(native_multi):
    _, original = native_multi
    for field, value in [('M2_evidence_scope', 'TEST_INJECTED_NOT_RESEARCH'), ('parameter_sha256', 'bad')]:
        h = deepcopy(original); h['candidates'][0][field] = value
        with pytest.raises(ValueError): build_guidance(h, source_uri='TEST')
    h = deepcopy(original); h['candidates'][0]['M2_observations'][-1]['observation']['metrics']['BW_Hz']['value'] = 1
    with pytest.raises(ValueError): build_guidance(h, source_uri='TEST')


def test_cp_measurement_is_only_applied_to_its_bound_candidate(native_multi):
    _, h = native_multi; cp = {'min': .1, 'max': 1.1, 'unit': 'V', 'conditions': ENV, 'evidence': [REF],
                              'source_candidate_sha256': h['candidates'][-1]['parameter_sha256']}
    g = guidance(h, cp_compliance=cp)
    assert g['candidates'][0]['cp_compliance'] is None and g['candidates'][-1]['cp_compliance'] == cp
    assert validate_guidance(g, h, options={'cp_compliance': cp}) == g
