"""One explanatory conditional ordering for first and subsequent M2 proposals."""
from copy import deepcopy
import math

from ..exploration.conditional_physics import ConditionalPhysics, jitter_limit
from ..region_explorer.assessment import normalized_point
from .candidates import rank

PRIORITIES = ['conditional_noise_tier', 'normalized_noise_gap', 'slip_risk',
    'initial_frequency_error', 'negative_tuning_margin', 'conditional_lock_time',
    'negative_M1_margin', 'Icp', 'total_capacitance_proxy', 'negative_diversity']


def choose_physics_candidate(eligible, problem, config, tested=()):
    """Formal M1/quality/distance filters are owned by candidate_pool.

    Lexicographic priority, no weighted trade against hard feasibility. Unknown
    components use neutral 0.5, never remove a candidate. With no valid physics
    at all, reuse the original tested-distance/M1 ordering exactly.
    """
    if not eligible:
        return None
    options = config['physics_options']; physics = ConditionalPhysics(problem, options)
    rows = [deepcopy(r) for r in eligible]
    for row in rows:
        # Recompute against the active options; archived metadata may come from
        # another profile, or be unavailable in this selection context.
        for key in ('analytic_features', 'predicted_jitter_s', 'noise_source_fractions',
                    'dominant_noise_source', 'noise_profile_identity', 'physics_selection'):
            row.pop(key, None)
        row.update(physics.describe(row['parameters']))
        if options['noise_allocation_enabled']:
            row['joint_conditional_feasibility'] = ('CONDITIONAL_FEASIBLE' if physics.qualified(row) else 'NOT_ESTABLISHED')
    usable = any(r.get('analytic_features', {}).get('prediction_validity', {}).get('status') ==
                 'CONDITIONAL_IDEAL_LINEAR' for r in rows)
    usable |= any(r.get('predicted_jitter_s') is not None for r in rows)
    from .candidate_pool import distance
    def legacy(r):
        return (-min(distance(problem, r, old) for old in tested), rank(r)) if tested else (0., rank(r))
    limit = jitter_limit(problem); target = problem['fixed_parameters']['N']['value']*problem['fixed_parameters']['f_ref']['value']
    span = problem['fixed_parameters']['Vctrl_max']['value']-problem['fixed_parameters']['Vctrl_min']['value']
    lock_limit = next((s['max'] for s in problem['specs'] if s['enabled'] and s['metric'] == 'lock_time_s' and 'max' in s), None)
    def bounded(value):
        return max(0., min(1., value))
    def score(r):
        f = r.get('analytic_features', {}); valid = f.get('prediction_validity', {}).get('status') == 'CONDITIONAL_IDEAL_LINEAR'
        jitter = r.get('predicted_jitter_s')
        tier, gap = 0., 0.
        if options['noise_allocation_enabled'] and limit is not None:
            tier = .5 if jitter is None else 0. if jitter <= limit else 1.
            gap = .5 if jitter is None else bounded(max(0., jitter-limit)/max(limit+max(0., jitter-limit), 1e-300))
        risk = {'LOW': 0., 'MEDIUM': .5, 'HIGH': 1., 'UNKNOWN': .5}.get(f.get('slip_risk'), .5)
        error = bounded(abs(f['initial_frequency_error_Hz'])/target) if valid else .5
        rail = bounded(f['tuning_rail_margin_V']/(span/2)) if valid else .5
        lock = bounded(f['predicted_lock_time_s']/lock_limit) if valid and lock_limit and f.get('predicted_lock_time_s') is not None else .5
        margin = r['judgment']['minimum_normalized_margin']; margin = margin/(1+abs(margin))
        u = normalized_point(problem, r['parameters'])
        diversity = min((distance(problem, r, old)/math.sqrt(6) for old in tested), default=0.)
        return [tier, gap, risk, error, -rail, lock, -margin, u['Icp'], (u['C1']+u['C2'])/2, -diversity]
    selected = min(rows, key=lambda r: (*score(r), r['parameter_sha256'])) if usable else min(rows, key=legacy)
    selected['physics_selection'] = {
        'schema_version': 'pll-physics-ranking-1.0', 'legacy_fallback': not usable,
        'reason': 'Lexicographic conditional physics priority after formal M1 quality and distance gates'
            if usable else 'No applicable physics predictions; original tested-distance and M1-margin ordering',
        'priority': PRIORITIES, 'normalized_components': dict(zip(PRIORITIES, score(selected))),
        'missing_prediction_rule': 'Neutral 0.5 per unavailable component; retained, no capture rejection',
        'predicted_jitter_s': selected.get('predicted_jitter_s'),
        'slip_risk': selected.get('analytic_features', {}).get('slip_risk', 'UNKNOWN'),
        'tuning_rail_margin_V': selected.get('analytic_features', {}).get('tuning_rail_margin_V'),
        'M1_minimum_normalized_margin': selected['judgment']['minimum_normalized_margin'],
        'eligible_count': len(rows), 'tested_count': len(tested), 'formal_M2_certified': False}
    return selected
