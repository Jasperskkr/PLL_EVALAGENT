"""Read-only summaries of M1 exploration point evidence; never region certification."""
from copy import deepcopy
import math

from ..block_space.contracts import FREE_IDS
from ..exploration.contracts import coordinate


def normalized_point(problem, parameters):
    return {k: coordinate(problem['parameters'][k], parameters['values'][k]['value']) for k in FREE_IDS}


def contains(bounds, point):
    return all(lo <= point[k] <= hi for k, (lo, hi) in bounds.items())


def physical_coordinate(axis, u):
    """Use M1 exploration's transform, repairing only floating endpoint roundoff.

    For valid u, an exact inverse lies inside the global domain. exp(log(min))
    can round one ULP below min even for tiny positive u. This is numerical
    endpoint repair, never projection of an out-of-domain strategy coordinate.
    """
    value = coordinate(axis, u, inverse=True)
    if 0 <= u <= 1:
        for endpoint in ('min', 'max'):
            bound = axis[endpoint]
            if ((value < bound if endpoint == 'min' else value > bound)
                    and math.isclose(value, bound, rel_tol=1e-14, abs_tol=0.)):
                return bound
    return value


def contains_parameters(problem, bounds, parameters):
    # Compare physical endpoints directly: log(exp(u)) can land one ULP outside
    # an exactly requested normalized boundary. Do not round cache keys or clip.
    return all(physical_coordinate(problem['parameters'][k], lo) <= parameters['values'][k]['value'] <=
               physical_coordinate(problem['parameters'][k], hi) for k, (lo, hi) in bounds.items())


def summarize(row):
    result = {k: deepcopy(row.get(k)) for k in ('evidence_id', 'origin', 'parameters', 'M1_status',
                                               'metrics', 'judgment', 'screening')}
    result['formal_model_diagnostics'] = deepcopy((row.get('formal_M1_result') or {}).get('diagnostics'))
    return result


def assess_regions(context, samples):
    problem = context['problem']
    unique = [r for r in samples if not r.get('duplicate_of')]
    summaries = []
    for region in context['candidate_regions']:
        rows = [r for r in unique if contains_parameters(problem, region['normalized_bounds'], r['parameters'])]
        groups = {name: [] for name in ('feasible', 'violated', 'invalid', 'unknown')}
        for row in rows:
            state = row['judgment']['m1_feasibility']
            group = ('invalid' if row['screening']['status'] == 'INVALID_CANDIDATE' else
                     'feasible' if state == 'FEASIBLE' else 'violated' if state == 'INFEASIBLE' or
                     row['screening']['status'] == 'NECESSARY_CONDITION_FAIL' else 'unknown')
            groups[group].append(row['evidence_id'])
        summaries.append({
            'assessment_id': 'RA8:' + region['region_id'], 'region_id': region['region_id'],
            'bounds': deepcopy(region['bounds']), 'normalized_bounds': deepcopy(region['normalized_bounds']),
            'representative': {k: deepcopy(region[k]) for k in ('representative_evidence_id',
                'representative_parameters', 'representative_metrics', 'representative_constraints', 'tightest_constraint')},
            'support_count': len(rows), 'sample_groups': groups, 'samples': [summarize(r) for r in rows],
            'sensitivity': [deepcopy(s) for s in context['sensitivity']['representatives'] if s['region_id'] == region['region_id']],
            'evidence_ids': [r['evidence_id'] for r in rows],
            'model_validity': 'POINTWISE_FORMAL_M1_ONLY; see individual M1_status and model diagnostics',
            'whole_region_M1_certified': False, 'M2_status': 'NOT_EVALUATED',
        })
    return {'schema_version': 'pll-region-assessment-1.0', 'context_sha256': context['context_sha256'],
            'problem_sha256': problem['problem_sha256'], 'model_fingerprint': context['model']['model_sha256'],
            'regions': summaries,
            'unknown_space': {'normalized_design_domain': {k: [0., 1.] for k in FREE_IDS},
                'description': 'All unsampled points remain unknown, including box interiors and points outside boxes. '
                               'A new decision may propose any legal box within the original user domain.',
                'infeasibility_certificates': context.get('summary', {}).get('status') == 'PROVEN_M1_INFEASIBLE'},
            'capability_boundary': deepcopy(context['capability_boundary'])}
