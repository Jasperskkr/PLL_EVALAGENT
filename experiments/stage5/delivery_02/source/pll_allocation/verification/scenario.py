"""Research decision adapter over the unchanged full formal M2 verifier."""
from copy import deepcopy
from pathlib import Path
from .verify import verify, validate_proposal, interval_judgment
from .experiments import write
from ..scenarios import validate_proposal_scenario
from ..physics_mapping.model import fingerprint


def measurement_proposal(item):
    _, _, frozen, _, binding = validate_proposal_scenario(item)
    projected = deepcopy(item)
    projected.pop('research_scenario', None)
    projected.pop('scenario_binding', None)
    projected['system_spec'] = frozen
    projected['system_spec_sha256'] = fingerprint(frozen)
    projected['versions']['system_spec'] = frozen['version']
    # Explicit measurement-only projection: predictions are not consumed by verifier.
    projected['M1'] = None
    projected['constraint_margins'] = None
    projected['validation_level'] = 'NOT_VALIDATED'
    validate_proposal(projected)
    return projected, binding


def validate_research_proposal(item):
    projected, _ = measurement_proposal(item)
    return validate_proposal(projected)


def rejudge(item, measured):
    projected, binding = measurement_proposal(item)
    from ..pipeline_contracts import check_result, load_inputs
    check_result(measured, projected, load_inputs()[3])
    result = deepcopy(measured)
    result.update(scenario_binding=binding, research_scenario=deepcopy(item['research_scenario']),
        base_system_spec_sha256=binding['base_system_spec_sha256'],
        fixed_system_spec_sha256=item['system_spec_sha256'],
        effective_system_spec_sha256=item['system_spec_sha256'],
        proposal_versions=deepcopy(item['versions']), parameter_sha256=item['parameter_sha256'],
        candidate_id=item['candidate_id'], joint_block_spec=deepcopy(item['joint_block_spec']))
    if result.get('validation_level') == 'NOT_VALIDATED':
        return result
    by_name = {s['metric']: s for s in item['system_spec']['metrics']}
    for check in result['constraints']:
        check['target'] = deepcopy(by_name[check['metric']])
        if check['metric'] == 'BW_Hz':
            bw = result['metrics']['BW_Hz']
            check['status'] = interval_judgment(bw.get('numerical_envelope'), check['target']) if bw['status'] == 'MEASURED_CONVERGED' else 'UNKNOWN'
            check['reason'] = 'research threshold over unchanged measured BW numerical envelope' if bw['status'] == 'MEASURED_CONVERGED' else 'no converged independent BW'
    result['overall_status'] = ('FAIL' if any(c['status'] == 'FAIL' for c in result['constraints'])
        else 'PASS' if all(c['status'] == 'PASS' for c in result['constraints']) else 'UNKNOWN')
    result['failure_reasons'] = [c['reason'] for c in result['constraints'] if c['status'] != 'PASS']
    result['structured_feedback'] = [x for x in result.get('structured_feedback', []) if x['code'] != 'MEASURED_CONSTRAINT_FAIL']
    result['structured_feedback'] += [{'code': 'MEASURED_CONSTRAINT_FAIL', 'metric': c['metric'], 'reason': c['reason']}
        for c in result['constraints'] if c['status'] == 'FAIL']
    result['measured_hard_metric_subset'] = ['BW_Hz'] if result['metrics']['BW_Hz']['status'] == 'MEASURED_CONVERGED' else []
    return result


def verify_research(item, out):
    # Validate before any execution; raw request and original result retain frozen contract.
    projected, binding = measurement_proposal(item)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    write(out/'research_proposal.json', item)
    write(out/'measurement_projection.json', {'scenario_binding': binding,
        'purpose': 'unchanged full TB, then metric-level research threshold evaluation',
        'source_result': 'frozen_measurement/result.json'})
    measured = verify(projected, out/'frozen_measurement')
    # Original result goes through original independent result checks as well.
    from ..pipeline_contracts import check_result, load_inputs
    check_result(measured, projected, load_inputs()[3])
    result = rejudge(item, measured)
    write(out/'result.json', result)
    return result
