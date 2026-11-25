"""Native multi-candidate delivery contract shared by producer and consumers."""
from .agent.handoff import validate_handoff
from .exploration.contracts import check_candidate, judge, require
from .exploration.engine import model_identity
from .physics_mapping.model import MappingResult, Status, fingerprint, parse_parameters

SCHEMA = 'pll-sizing-targets-1.0'


def validate_recorded_protocol(request):
    """Check versioned recorded protocols without requiring the original DLL.

    Old fixed-N8 records remain readable. The integer-N adapter adds frequency
    metadata and changes its scope, while retaining the base measurement limits.
    """
    from .verification.experiments import protocol
    expected = protocol()
    p = parse_parameters(request['parameters'])
    version = request['M2_model']['adapter_version']
    require((p['f_ref'], p['Vctrl_min'], p['Vctrl_max']) == (10e6, 0, 1.2),
            'recorded M2 frequency/rail scope mismatch')
    if version == 'pll-continuous-m2-1.0':
        require(p['N'] == 8, 'legacy M2 protocol requires N=8')
    elif version in ('pll-continuous-m2-1.1', 'pll-continuous-m2-1.2'):
        from .verification.metric_protocols import integer_n_protocol
        expected = integer_n_protocol(p, legacy=version == 'pll-continuous-m2-1.1')
    else:
        raise ValueError('unsupported recorded M2 adapter version')
    require(request['protocol'] == expected and request['protocol_id'] == expected['protocol_id'] and
            request['protocol_sha256'] == fingerprint(expected), 'recorded M2 protocol/frequency binding mismatch')


def validate_sizing_handoff(handoff, *, require_current_model=True):
    """Validate summary and recorded evidence without rerunning physics or a DLL."""
    require(isinstance(handoff, dict) and handoff.get('schema_version') == SCHEMA,
            'unsupported source handoff')
    problem = handoff['problem']
    require(problem['problem_sha256'] == fingerprint({k: v for k, v in problem.items()
            if k != 'problem_sha256'}), 'problem fingerprint mismatch')
    rows, count, target = handoff['candidates'], handoff['candidate_count'], handoff['m2_target_count']
    require(isinstance(rows, list) and type(count) is int and count == len(rows) and
            type(target) is int and 1 <= target <= 100, 'invalid delivery candidate count or target')
    reached = count >= target
    require(type(handoff['joint_target_reached']) is bool and handoff['joint_target_reached'] == reached,
            'delivery target flag disagrees with candidate count')
    status = handoff['joint_status']
    valid_status = status == ('TARGET_REACHED' if reached else 'PARTIAL') if count else status in ('DISABLED', 'TEST_ONLY', 'NOT_REACHED')
    require(valid_status, 'delivery status disagrees with candidate count')
    require(handoff['evidence_scope'] == 'NATIVE_M2_SUPPORTED_METRICS_ONLY' and
            handoff['FULL_SYSTEMSPEC_CERTIFIED'] is False, 'invalid multi-candidate delivery scope')
    keys = {row['parameter_sha256'] for row in rows}
    require(handoff['recommended_candidate_sha256'] in keys if count else
            handoff['recommended_candidate_sha256'] is None, 'delivery recommendation is not a delivered candidate')
    from .verification.continuous import judge_measurements
    seen = set()
    for row in rows:
        key = fingerprint(row['parameters'])
        require(row['parameter_sha256'] == key and key not in seen, 'candidate hash/duplicate mismatch')
        seen.add(key)
        if require_current_model:
            require(row['model_fingerprint'] == model_identity()['model_sha256'], 'candidate model mismatch')
        require(row['problem_sha256'] == problem['problem_sha256'], 'candidate problem mismatch')
        require(check_candidate(problem, row['parameters'])['status'] == 'NECESSARY_CONDITIONS_SATISFIED',
                'source candidate outside original domain or necessary conditions')
        raw = row['formal_M1_result']; result = MappingResult(**(raw | {'status': Status(raw['status'])}))
        require(result.status == Status.OK and row['metrics'] == result.metrics and
                row['judgment'] == judge(problem, row['parameters'], result) and
                row['judgment']['m1_feasibility'] == 'FEASIBLE', 'source formal M1 evidence mismatch')
        require(row['M2_evidence_scope'] == 'NATIVE' and row['M2_supported_status'] == 'PASS' and
                bool(row['M2_observations']), 'native M2 evidence required for multi-point delivery')
        record = row['M2_observations'][-1]; request, measured = record['request'], record['observation']
        parameters = validate_handoff(request['handoff'], require_current_model=require_current_model)
        validate_recorded_protocol(request)
        require(parameters == row['parameters'] == request['parameters'] and
                row['model_fingerprint'] == request['handoff']['model_fingerprint'] and
                request['handoff']['problem'] == problem and request['candidate_sha256'] == key and
                request['problem_sha256'] == problem['problem_sha256'] and
                request['specs'] == problem['specs'] and
                request['candidate_id'] == row['evidence_id'] and
                request['request_sha256'] == fingerprint({k: v for k, v in request.items()
                                                         if k != 'request_sha256'}) and
                request['protocol_sha256'] == fingerprint(request['protocol']), 'M2 request binding mismatch')
        require(all(measured[k] == request[k] for k in
                    ('candidate_sha256', 'request_sha256', 'problem_sha256', 'protocol_sha256')) and
                measured['M2_model_fingerprint'] == fingerprint(request['M2_model']) and
                row['M2_status'] == measured['overall_status'] and
                measured['cost']['completed_native_runs'] > 0 and
                measured['evidence_id'].startswith('M2:'), 'native observation binding mismatch')
        judgment = judge_measurements(request, measured['capture'], measured['frequency_response_comparison'])
        require(judgment['supported_metrics_status'] == 'PASS' and all(measured[k] == judgment[k] for k in
                ('supported_metrics_status', 'overall_status', 'constraints', 'metrics', 'FULL_SYSTEMSPEC_CERTIFIED')),
                'recorded native verdict mismatch')
    return problem, rows
