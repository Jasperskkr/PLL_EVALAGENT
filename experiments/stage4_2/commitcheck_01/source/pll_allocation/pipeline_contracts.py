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
    if item.get('validation_level') == 'NOT_VALIDATED' and item['overall_status'] == 'UNKNOWN':
        if not item.get('failure_reasons') or item.get('metrics'):
            raise ValueError('invalid failure result')
        return
    for actual, expected in [('candidate_id', proposal['candidate_id']),
                             ('parameter_sha256', proposal['parameter_sha256']),
                             ('joint_block_spec', proposal['joint_block_spec']),
                             ('proposal_versions', proposal['versions']),
                             ('model_version', MODEL_VERSION),
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
    return {'schema_version': 'allocation-feedback-1.0', 'source': 'M2',
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
