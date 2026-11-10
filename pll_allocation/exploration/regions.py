"""Sample-supported regions and local derivatives, never region certification."""
import math

from ..block_space.contracts import FREE_IDS
from .contracts import active_m1_specs, coordinate, make_parameters


def point(problem, row):
    return [coordinate(problem['parameters'][name], row['parameters']['values'][name]['value']) for name in FREE_IDS]


def candidate_regions(problem, samples):
    feasible = [r for r in samples if not r.get('duplicate_of') and r['judgment']['m1_feasibility'] == 'FEASIBLE']
    ordered = sorted(feasible, key=lambda r: (-r['judgment']['minimum_normalized_margin'], r['evidence_id']))
    selected = ordered[:1]
    pool = ordered[1:]
    while pool and len(selected) < problem['exploration']['region_count']:
        def distance(row):
            u = point(problem, row)
            return min(sum((a-b)**2 for a, b in zip(u, point(problem, center))) for center in selected)
        chosen = max(pool, key=distance)
        selected.append(chosen)
        pool.remove(chosen)
    regions = []
    for index, center in enumerate(selected):
        u = point(problem, center)
        radius = problem['exploration']['region_radius']
        limits = {k: [max(0., value-radius), min(1., value+radius)] for k, value in zip(FREE_IDS, u)}
        bounds = {k: {'min': coordinate(problem['parameters'][k], lo, inverse=True),
                      'max': coordinate(problem['parameters'][k], hi, inverse=True),
                      'unit': problem['parameters'][k]['unit'], 'scale': problem['parameters'][k]['scale']}
                  for k, (lo, hi) in limits.items()}
        support = [r['evidence_id'] for r in feasible if all(lo <= value <= hi
                   for value, (lo, hi) in zip(point(problem, r), limits.values()))]
        constraints = [r for r in center['judgment']['constraints'] if r['enabled'] and r['support_status'] == 'M1_SUPPORTED']
        tightest = min(constraints, key=lambda r: r['normalized_margin'])
        regions.append({'region_id': f'R{index+1:03d}', 'representative_evidence_id': center['evidence_id'],
                        'representative_parameters': center['parameters'], 'representative_metrics': center['metrics'],
                        'representative_constraints': center['judgment']['constraints'], 'tightest_constraint': tightest,
                        'bounds': bounds, 'normalized_bounds': limits, 'support_evidence_ids': support,
                        'status': 'SAMPLED_POINT_SUPPORTED_SEARCH_SUGGESTION', 'whole_region_M1_certified': False,
                        'M2_status': 'NOT_EVALUATED'})
    return {'regions': regions, 'feasible_evidence_ids': [r['evidence_id'] for r in feasible],
            'selection': 'largest worst normalized margin, then farthest in configured normalized coordinates',
            'scope': 'Local boxes suggest where to search; unsampled interiors and corners are not certified.'}


def sensitivity(problem, regions, sample):
    results = []
    spec_scales = {s['metric']: s['normalization_scale'] for s in active_m1_specs(problem)}
    for region in regions['regions'][:problem['exploration']['sensitivity_representatives']]:
        center = region['representative_parameters']
        base = region['representative_metrics']
        scales = {k: spec_scales.get(k, max(abs(v), 1e-30)) for k, v in base.items()}
        columns = {}
        for name in FREE_IDS:
            axis = problem['parameters'][name]
            value = center['values'][name]['value']
            u = coordinate(axis, value)
            low, high = max(0., u-problem['exploration']['sensitivity_step']), min(1., u+problem['exploration']['sensitivity_step'])
            # Preserve exact domain endpoints rather than exp(log(bound)) rounding outside the domain.
            a = axis['min'] if low == 0 else coordinate(axis, low, inverse=True)
            b = axis['max'] if high == 1 else coordinate(axis, high, inverse=True)
            lower = sample(make_parameters(problem, {k: (a if k == name else v['value']) for k, v in center['values'].items()}),
                           f'SENSITIVITY:{region["region_id"]}:{name}:LOW')
            upper = sample(make_parameters(problem, {k: (b if k == name else v['value']) for k, v in center['values'].items()}),
                           f'SENSITIVITY:{region["region_id"]}:{name}:HIGH')
            column = {'status': 'DOMAIN_OR_BUDGET_LIMITED', 'evidence_ids': [lower['evidence_id'], upper['evidence_id']],
                      'parameter_points': [a, b], 'normalized_points': [low, high],
                      'stencil': 'CENTRAL' if low < u < high else 'ONE_SIDED'}
            if lower['M1_status'] == upper['M1_status'] == 'OK' and high > low and b > a:
                ma, mb = lower['metrics'], upper['metrics']
                relative_step = (b-a)/a
                dlog = math.log1p(relative_step) if math.isfinite(relative_step) else math.log(b)-math.log(a)
                column.update(status='OK', normalized_derivative={k: (mb[k]-ma[k])/scales[k]/(high-low) for k in base},
                              log_elasticity={k: math.log(mb[k]/ma[k])/dlog for k in base if ma[k] > 0 and mb[k] > 0},
                              PM_deg_per_log_parameter=(mb['PM_deg']-ma['PM_deg'])/dlog)
                if not all(math.isfinite(v) for v in column['normalized_derivative'].values()):
                    column.pop('normalized_derivative')
                    column['status'] = 'NUMERICALLY_UNRESOLVED_STENCIL'
            columns[name] = column
        results.append({'region_id': region['region_id'], 'center_evidence_id': region['representative_evidence_id'],
                        'metric_normalization_scales': scales, 'columns': columns,
                        'normalized_matrix': {metric: {k: c.get('normalized_derivative', {}).get(metric)
                                                      for k, c in columns.items()} for metric in base}})
    return {'representatives': results, 'definition': 'd(metric / metric_scale) / d(u); u is configured linear/log axis normalized to [0,1]',
            'scope': 'Six-variable local formal M1 finite differences; not capture/noise derivatives or a global guarantee.',
            'coupling': {'Icp_Kvco': 'Ideal BW/UGF/PM depend on Icp*Kvco/N; tuning also changes with Kvco and f0.',
                         'LF': 'C2/C1 sets the ideal phase ceiling; Rz*C2 sets the zero; all three change BW and PM.',
                         'tuning': 'Vreq=(N*f_ref-f0)/Kvco; gain splitting must retain interior tuning.'}}
