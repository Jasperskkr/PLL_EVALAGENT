"""Explicit measured-point conversion into a separately identified legal problem."""
from copy import deepcopy

from ..exploration.contracts import check_candidate, make_parameters, require, resolve_problem
from ..physics_mapping.model import ModelError, fingerprint, parse_parameters
from .contract import assess_feedback


def prepare_revalidation(feedback, guidance, handoff, *, problem, options=None, source_handoff_path=None):
    """Return input for the existing M1/M2 path, without executing or changing it.

    A caller must supply a new raw ResearchProblemV2 with an independent ID.
    Any widening of the old search bounds is explicit and recorded. The full
    formal model/domain gate remains in charge, including positive frequencies.
    """
    assessment = assess_feedback(feedback, guidance, handoff, options=options, source_handoff_path=source_handoff_path)
    require(assessment['actual_local_parameters'] is not None, 'measured target operating point required')
    original = handoff['problem']; updated = resolve_problem(problem)
    require(updated['problem_id'] != original['problem_id'], 'independent revalidation problem_id required')
    require(updated['specs'] == original['specs'] and updated['fixed_parameters'] == original['fixed_parameters'] and
            updated['topology'] == original['topology'], 'original SystemSpec/fixed topology must be preserved')
    entry = next(g for g in guidance['candidates'] if g['source_candidate_sha256'] == feedback['source_candidate_sha256'])
    p = parse_parameters(entry['nominal_block_spec'])
    actual = assessment['actual_local_parameters']
    overrides = {k: p[k] for k in updated['parameters']}
    overrides.update(f0=actual['f0_local_hz'], Kvco=actual['kvco_local_hz_per_v'])
    outside_old = [k for k, v in overrides.items() if not original['parameters'][k]['min'] <= v <= original['parameters'][k]['max']]
    result = {'schema_version': 'pll-vco-revalidation-input-1.0', 'experiment_id': feedback['experiment_id'],
        'source_candidate_sha256': entry['source_candidate_sha256'], 'source_problem_sha256': original['problem_sha256'],
        'source_candidate_id': entry['source_candidate_id'], 'model_fingerprint': entry['model_fingerprint'],
        'source_handoff_sha256': guidance['source_handoff_sha256'], 'feedback_sha256': fingerprint(feedback),
        'original_search_domain_status': 'OUTSIDE_ORIGINAL_SEARCH_DOMAIN' if outside_old else 'INSIDE_ORIGINAL_SEARCH_DOMAIN',
        'outside_original_axes': outside_old, 'problem': deepcopy(updated), 'parameters': None,
        'physical_assessment': assessment, 'M1_status': 'NOT_EVALUATED', 'M2_status': 'NOT_EVALUATED',
        'FULL_SYSTEMSPEC_CERTIFIED': False,
        'model_scope': 'Local tangent surrogate only; native linear VCO is not the measured nonlinear curve'}
    if not assessment['target_operating_point_confirmed']:
        return result | {'status': 'TARGET_OPERATING_POINT_UNCONFIRMED',
                         'reason': 'Approximate/interpolated operating point has not been measurement-confirmed'}
    if assessment['physical_status'] == 'REQUIREMENTS_FAILED':
        return result | {'status': 'PHYSICAL_REQUIREMENTS_FAILED',
                         'reason': 'Measured physical or explicit block hard constraint failed; see assessment'}
    try:
        parameters = make_parameters(updated, overrides)
        parse_parameters(parameters)
        check = check_candidate(updated, parameters)
        require(check['status'] == 'NECESSARY_CONDITIONS_SATISFIED', check['reason'])
    except (ModelError, ValueError, KeyError, TypeError) as error:
        result.update(status='REVALIDATION_DOMAIN_REJECTED', reason=str(error))
        return result
    result.update(status='READY_FOR_FORMAL_REVALIDATION', parameters=parameters,
        parameter_sha256=fingerprint(parameters), screening=check)
    return result
