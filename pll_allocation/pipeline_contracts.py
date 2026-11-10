"""Stage3A binding and feedback adapters. No physical equations or measurements."""
from copy import deepcopy
import hashlib
from pathlib import Path
from .block_space.contracts import load_model
from .physics_mapping.model import fingerprint
from .allocation.core import read
from .verification.resources import CONFIGS
from .verification.simulator import MODEL_VERSION

CONFIG_SCHEMA = 'pll-unified-pipeline-1.0'
RESULT_SCHEMA = 'behavioral-verification-result-1.0'


def load_inputs(config_path=None):
    path = Path(config_path).resolve() if config_path else CONFIGS/'pipeline_stage3a.json'
    config = read(path)
    if config.get('schema_version') != CONFIG_SCHEMA:
        raise ValueError('unsupported pipeline config version')
    base = path.parent
    model = load_model(base/config['model'])
    spec, doc, equations = (read(base/config[k]) for k in ('system_spec', 'protocol', 'equations'))
    bindings = config['bindings']
    for name, item in [('model', model), ('system_spec', spec), ('protocol', doc), ('equations', equations)]:
        if fingerprint(item) != bindings[name+'_sha256']:
            raise ValueError(name+' version/hash binding mismatch')
    # The extracted backend supports precisely these formal assets. Custom targets are rejected.
    if model != load_model(CONFIGS/'BLOCK_SPACE_MODEL_V1.json') or spec != model['experiment']['system_spec']:
        raise ValueError('frozen Block Space/SystemSpec mismatch')
    if doc != read(CONFIGS/'verification/protocol_v1_1.json') or doc['protocol_id'] != 'track_b_metrics_1.1':
        raise ValueError('unsupported measurement protocol')
    if bindings['versions'] != model['versions']:
        raise ValueError('physical model version mismatch')
    kernel = Path(__file__).parent/'verification/kernel.cpp'
    if hashlib.sha256(kernel.read_bytes()).hexdigest() != bindings['kernel_sha256']:
        raise ValueError('native kernel source binding mismatch')
    return config, model, spec, doc


def check_result(item, proposal, protocol):
    if item.get('schema_version') != RESULT_SCHEMA or item.get('overall_status') not in ('PASS', 'FAIL', 'UNKNOWN'):
        raise ValueError('unsupported BehavioralVerificationResult')
    if proposal.get('research_scenario') is not None:
        from .scenarios import validate_proposal_scenario
        binding = validate_proposal_scenario(proposal)[4]
        if item.get('scenario_binding') != binding or item.get('research_scenario') != proposal['research_scenario']:
            raise ValueError('M2 scenario binding mismatch')
    if item.get('validation_level') == 'NOT_VALIDATED' and item['overall_status'] == 'UNKNOWN':
        if not item.get('failure_reasons') or item.get('metrics'):
            raise ValueError('invalid failure result')
        return
    expected_model=MODEL_VERSION
    if proposal.get('behavioral_extension'):
        from .verification.stage6c_native import MODEL_ID
        from .verification.stage6c import validate_extension
        ext=validate_extension(proposal['behavioral_extension']);expected_model=MODEL_ID
        actual=item.get('extension',{})
        if actual.get('extension_id')!=ext['extension_id'] or actual.get('profile_hashes')!=ext['source_profile_hashes']:
            raise ValueError('Stage6C profile result binding mismatch')
        from .verification.stage6c_identity import check_build
        if actual.get('native_build_identity')!=check_build():raise ValueError('Stage6C native result identity mismatch')
        nr=actual.get('noise_result')
        if nr is not None:
            if (nr.get('candidate_sha256')!=proposal['parameter_sha256']
                or nr.get('noise_profile_sha256')!=ext['source_profile_hashes']['noise_profile']
                or nr.get('protocol_sha256')!=ext['source_profile_hashes']['noise_protocol']):
                raise ValueError('Stage6C actual noise measurement binding mismatch')
            from .verification.noise import aggregate
            measured=item.get('metrics',{}).get('integrated_jitter_s',{})
            if nr.get('status')=='STATISTICALLY_RESOLVED_CONDITIONAL':
                rebuilt=aggregate(nr['measurements'],ext['noise_protocol'],ext['jitter_limit_s'])
                for name in ('status','integrated_jitter_s','jitter_interval_s','jitter_constraint_status'):
                    if rebuilt[name]!=nr[name]:raise ValueError('Stage6C statistical evidence mismatch:'+name)
                if not nr.get('all_observations_locked') or not all(r.get('locked_during_observation')is True for r in nr['measurements']):
                    raise ValueError('Stage6C unresolved stochastic tracking')
                if (measured.get('status')!=nr['status'] or measured.get('value')!=nr['integrated_jitter_s']
                    or measured.get('statistical_interval_s')!=nr['jitter_interval_s']):raise ValueError('Stage6C scalar jitter differs from raw-seed evidence')
    for actual, expected in [('candidate_id', proposal['candidate_id']),
                             ('parameter_sha256', proposal['parameter_sha256']),
                             ('joint_block_spec', proposal['joint_block_spec']),
                             ('proposal_versions', proposal['versions']),
                             ('model_version', expected_model),
                             ('fixed_system_spec_sha256', proposal['system_spec_sha256']),
                             ('protocol_id', protocol['protocol_id']),
                             ('protocol_sha256', fingerprint(protocol))]:
        if item.get(actual) != expected:
            raise ValueError('M2 result binding mismatch: '+actual)
    checks = item.get('constraints', [])
    if item.get('source_hashes', {}).get('model') != proposal['block_space_sha256']:
        raise ValueError('M2 model source binding mismatch')
    kernel = Path(__file__).parent/'verification/kernel.cpp'
    if item.get('source_hashes', {}).get('kernel.cpp') != hashlib.sha256(kernel.read_bytes()).hexdigest():
        raise ValueError('M2 kernel source binding mismatch')
    specs = proposal['system_spec']['metrics']
    if len(checks) != len(specs) or {x['metric'] for x in checks} != {x['metric'] for x in specs}:
        raise ValueError('all required M2 metrics must be reported')
    by_name = {s['metric']: s for s in specs}
    for check in checks:
        if check['target'] != by_name[check['metric']] or check['status'] not in ('PASS', 'FAIL', 'UNKNOWN'):
            raise ValueError('M2 target/status mismatch')
        if proposal.get('research_scenario') is not None and check['metric'] == 'BW_Hz':
            from .verification.verify import interval_judgment
            bw = item['metrics']['BW_Hz']
            expected_bw = interval_judgment(bw.get('numerical_envelope'), check['target']) if bw['status'] == 'MEASURED_CONVERGED' else 'UNKNOWN'
            if check['status'] != expected_bw:
                raise ValueError('M2 research BW judgment mismatch')
    if any(c['status'] == 'PASS' and c['metric'] in ('PM_deg', 'output_frequency_Hz') for c in checks):
        raise ValueError('unsupported precision/PM cannot pass current M2')
    expected = 'FAIL' if any(c['status'] == 'FAIL' for c in checks) else 'PASS' if all(c['status'] == 'PASS' for c in checks) else 'UNKNOWN'
    if item['overall_status'] != expected or item.get('verified_joint_block_spec') is not False:
        raise ValueError('invalid overall M2 certification')


def m2_label(item):
    statuses = [c['status'] for c in item.get('constraints', [])]
    if item.get('overall_status') == 'FAIL':
        return 'M2_FAIL'
    if item.get('overall_status') == 'PASS':
        return 'M2_PASS'
    if 'PASS' in statuses:
        return 'M2_PARTIAL_PASS'
    return 'M2_UNKNOWN'


def make_feedback(proposal, result, protocol, remaining):
    constraints = deepcopy(result.get('constraints', []))
    bw = result.get('metrics', {}).get('BW_Hz', {})
    failed = [c['metric'] for c in constraints if c['status'] == 'FAIL']
    kind = 'UNRELIABLE_MEASUREMENT'
    domain = result.get('domain', {})
    if domain and (domain.get('declared_domain') != 'IN_DECLARED_DOMAIN' or domain.get('model_validity') != 'VALID'):
        kind = 'MODEL_OUT_OF_DOMAIN'
    elif failed == ['BW_Hz'] and bw.get('status') == 'MEASURED_CONVERGED':
        kind = 'BW'
    elif result.get('metrics', {}).get('capture', {}).get('value') == 'NOT_CAPTURED_WITHIN_WINDOW':
        kind = 'COLD_START_CAPTURE'
    measurements = deepcopy(result.get('metrics', {}))
    if 'BW_Hz' in measurements:
        measurements['BW_Hz']['reliable'] = bw.get('status') == 'MEASURED_CONVERGED'
    return {**({'scenario_binding': deepcopy(proposal['scenario_binding'])} if 'scenario_binding' in proposal else {}),
            'schema_version': 'allocation-feedback-1.0', 'source': 'M2',
            'parameter_sha256': proposal['parameter_sha256'], 'candidate_id': proposal['candidate_id'],
            'system_spec_sha256': proposal['system_spec_sha256'], 'block_space_sha256': proposal['block_space_sha256'],
            'protocol_id': protocol['protocol_id'], 'protocol_sha256': fingerprint(protocol),
            'kind': kind, 'verdict': 'FAIL' if result['overall_status'] == 'FAIL' else 'UNKNOWN',
            'measurements': measurements, 'constraints': constraints,
            'passed_metrics': [c['metric'] for c in constraints if c['status'] == 'PASS'],
            'failed_metrics': failed, 'unknown_metrics': [c['metric'] for c in constraints if c['status'] == 'UNKNOWN'],
            'prediction_errors': deepcopy(result.get('prediction_errors', {})),
            'failure_reasons': deepcopy(result.get('failure_reasons', [])),
            'verifier_diagnostics': deepcopy(result.get('structured_feedback', [])),
            'remaining': remaining, 'learning_performed': False}
