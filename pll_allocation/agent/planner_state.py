"""Compact, point-based calibration for the real region policy."""
from collections import Counter
import json

from ..block_space.contracts import FREE_IDS
from ..exploration.contracts import check_candidate, screen_problem
from ..physics_mapping.model import METRIC_UNITS, fingerprint
from ..region_explorer.assessment import normalized_point
from ..region_explorer.explorer import slsqp_cost_model
from ..verification.resources import CONFIGS

REGISTRY = CONFIGS/'model/equations.json'


def compact_sample(row, problem):
    params = row['parameters']
    legal = (row['M1_status'] == 'OK' and
             check_candidate(problem, params)['status'] == 'NECESSARY_CONDITIONS_SATISFIED')
    origin = 'CALIBRATION_SENSITIVITY' if row['origin'].startswith('SENSITIVITY:') else row['origin']
    return {'evidence_id': row['evidence_id'], 'origin': origin, 'seed_eligible': legal,
            'values_SI': {k: params['values'][k]['value'] for k in FREE_IDS},
            'normalized': normalized_point(problem, params) if legal else None,
            'metrics': row['metrics'], 'M1_status': row['M1_status'],
            'm1_feasibility': row['judgment']['m1_feasibility'],
            'worst_normalized_margin': row['judgment']['minimum_normalized_margin'],
            'bound_margins': {c['metric']: c['bound_margins'] for c in row['judgment']['constraints'] if c['enabled']}}


def representative_rows(rows, limit, *, feasibility):
    # Deduplicate only exact parameter fingerprints. Rank current-spec results,
    # including finite formal violations; no region geometry is used.
    unique = {r['parameter_sha256']: r for r in reversed(rows)
              if r['M1_status'] == 'OK' and r['judgment']['m1_feasibility'] == feasibility
              and r['judgment']['minimum_normalized_margin'] is not None}
    return sorted(unique.values(), key=lambda r: (-r['judgment']['minimum_normalized_margin'], r['evidence_id']))[:limit]


def sensitivity(context, evidence=None):
    rows = []
    for i, rep in enumerate(context['sensitivity']['representatives'], 1):
        matrix = rep['normalized_matrix']
        jacobian = {}
        for spec in context['problem']['specs']:
            k = spec['metric']
            if not spec['enabled'] or k not in matrix:
                continue
            for side, sign in (('min', 1), ('max', -1)):
                if side in spec:
                    factor = sign*rep['metric_normalization_scales'][k]/spec['normalization_scale']
                    jacobian[k+':'+side] = {a: d*factor if d is not None else None for a, d in matrix[k].items()}
        center = (evidence or {}).get(rep['center_evidence_id'])
        rows.append({'evidence_id': f'SENS8B:{i:02d}', 'center_evidence_id': rep['center_evidence_id'],
            'center_values_SI': {k: center['parameters']['values'][k]['value'] for k in FREE_IDS} if center else {k: next(r for r in context['candidate_regions']
                 if r['representative_evidence_id'] == rep['center_evidence_id'])['representative_parameters']['values'][k]['value']
                 for k in FREE_IDS} if any(r['representative_evidence_id'] == rep['center_evidence_id']
                                          for r in context['candidate_regions']) else None,
            'scope': 'Local finite differences only; use current-spec metric scales and coordinate conventions.',
            'normalized_matrix': {k: matrix[k] for k in ('BW_Hz', 'PM_deg', 'UGF_Hz') if k in matrix},
            'normalized_bound_margin_jacobian': jacobian,
            'metric_normalization_scales': rep['metric_normalization_scales'],
            'stencils': {k: {field: col[field] for field in ('status', 'stencil', 'evidence_ids',
                                                            'parameter_points', 'normalized_points')}
                         for k, col in rep['columns'].items()},
            'metric_units': {k: METRIC_UNITS[k] for k in matrix}})
    return rows


def sensitivity_conflicts(derivatives, epsilon=1e-10):
    conflicts = []
    for metric in sorted({m for r in derivatives for m in r['normalized_matrix']}):
        for axis in FREE_IDS:
            values = [{'sensitivity_id': r['evidence_id'], 'center_evidence_id': r['center_evidence_id'],
                       'derivative': r['normalized_matrix'].get(metric, {}).get(axis)} for r in derivatives]
            finite = [r for r in values if r['derivative'] is not None]
            if any(r['derivative'] > epsilon for r in finite) and any(r['derivative'] < -epsilon for r in finite):
                conflicts.append({'metric': metric, 'variable': axis, 'working_points': finite,
                                  'meaning': 'Opposite local derivatives; no global monotonicity claim is justified.'})
    return conflicts


def knowledge(context):
    registry = json.loads(REGISTRY.read_text(encoding='utf-8'))
    return [
        *[{'evidence_id': e['equation_id'], 'kind': 'PHYSICS_PRIOR', 'expression': e['expression'],
           'domain': e['domain'], 'limitations': e['limitations']}
          for e in registry['equations'] if e['model_level'] == 'M1'],
        *[{'evidence_id': 'REL:'+k,
           'kind': 'HARD_CONSTRAINT' if k == 'phase_ceiling' else 'PHYSICS_PRIOR',
           'expression': v}
          for k, v in context['relations'].items()],
        {'evidence_id': 'HARD:DOMAIN', 'kind': 'HARD_CONSTRAINT',
         'expression': 'Stay within original global ranges and fixed inputs. Vreq must be strictly inside Vctrl range; '
                       'the M1 model and active supported Spec bounds must pass at the final candidate.'},
        {'evidence_id': 'HEUR:LOCAL', 'kind': 'HEURISTIC',
         'expression': 'Calibration points and local slopes can guide selection; no box or unsampled point is certified.'},
    ]


def compact_observation(obs):
    return {k: obs[k] for k in ('observation_id', 'status', 'region', 'normalized_bounds', 'active_variables',
        'seed_ids', 'original_minimum_normalized_margin', 'latest_minimum_normalized_margin',
        'best_evidence_id', 'final_recheck_evidence_id', 'final_recheck_status',
        'solver_runs', 'failure', 'budget_exhausted', 'cost') } | {
        'sample_count': len(obs['evidence_ids']), 'positive_count': len(obs['new_positive_evidence_ids']),
        'negative_count': len(obs['new_negative_evidence_ids']),
        'failure_reasons': dict(Counter((r['status']+': '+(r['reason'] or 'unspecified'))[:220]
                                        for r in obs['failures_and_unknowns']).most_common(5))}


def build_state(explorer, policy_config, history, *, round_number, calls_remaining, calibration,
                correction=None):
    context, problem = explorer.context, explorer.problem
    derivatives = sensitivity(context, explorer.evidence)
    rules = knowledge(context)
    unique_calibration_samples = [r for r in explorer.calibration_samples if not r.get('duplicate_of')]
    selected = {}
    for outcome in ('FEASIBLE', 'INFEASIBLE'):
        for r in representative_rows(unique_calibration_samples, 4, feasibility=outcome):
            selected[r['evidence_id']] = r
    for rep in derivatives:
        center = rep['center_evidence_id']
        selected[center] = explorer.evidence[center]
    archive = getattr(explorer, 'candidate_archive', None)
    summary = archive.summary(absolute=policy_config.get('improvement_abs', 1e-6),
                              relative=policy_config.get('improvement_rel', 1e-6)) if archive else {}
    for key in ('best_known', 'best_calibration', 'best_new'):
        if summary.get(key):
            row = summary[key]
            selected[row['evidence_id']] = row
    recent = []
    if history:
        for record in history:
            for obs in record['observations']:
                for k in ('best_evidence_id', 'final_recheck_evidence_id'):
                    sid = obs[k]
                    if sid:
                        selected[sid] = explorer.evidence[sid]
        new = [r for r in explorer.rows if r['formal_M1_called']]
        for outcome in ('FEASIBLE', 'INFEASIBLE'):
            for r in representative_rows(new, 3, feasibility=outcome):
                selected[r['evidence_id']] = r
        recent = [{'search_decision': record['decision'], 'execution_decisions': record['execution_decisions'],
                   'observations': [compact_observation(o) for o in record['observations']],
                   'outcome': record['outcome'], 'stop_basis':record.get('stop_basis')} for record in history]
    samples = [compact_sample(row, problem) for row in selected.values()]
    remaining = explorer.cost()['search_available_M1_calls']
    best = summary.get('best_known')
    tightest = min((s for s in best['judgment']['constraints'] if s['enabled'] and s['support_status'] == 'M1_SUPPORTED'
                    and s['normalized_margin'] is not None), key=lambda s: s['normalized_margin'], default=None) if best else None
    stalls = 0
    for record in reversed(history):
        if record['decision']['action'] == 'STOP' or record.get('progress', {}).get('material', False):
            break
        stalls += 1
    progress = {'best_known': compact_sample(best, problem) if best else None,
        'best_calibration': compact_sample(summary['best_calibration'], problem) if summary.get('best_calibration') else None,
        'best_new': compact_sample(summary['best_new'], problem) if summary.get('best_new') else None,
        'current_tightest_constraint': tightest,
        'improvement_over_best': history[-1].get('progress') if history else None,
        'improvement_over_calibration': summary.get('improvement_over_calibration'),
        'stalled_rounds': stalls, 'cost_per_round': [{'round': record['round'],
             'M1_calls': sum(o['cost']['M1_calls'] for o in record['observations'])} for record in history]}
    origin_counts = Counter(('SENSITIVITY_PROBE' if r['origin'].startswith('SENSITIVITY:') else
                             'SOBOL_GLOBAL' if r['origin'].startswith('SOBOL:') else
                             'PHYSICS_SEED' if r['origin'].startswith('PHYSICS_SEED:') else 'OTHER') for r in unique_calibration_samples)
    return {'schema_version': 'pll-llm-region-planner-state-1.0', 'round': round_number,
        'problem': {k: problem[k] for k in ('problem_id', 'schema_version', 'problem_sha256', 'topology',
                                           'parameters', 'fixed_parameters', 'specs')},
        'model': {'id': context['model']['model_id'], 'fingerprint': context['model']['model_sha256'],
                  'capability_boundary': context['capability_boundary'], 'metric_units': METRIC_UNITS},
        'context_sha256': context['context_sha256'], 'physics_knowledge': rules,
        'necessary_condition_screen': screen_problem(problem),
        **progress,
        'sensitivity_conflicts': sensitivity_conflicts(derivatives),
        'calibration': {**calibration, 'unique_calibration_points': len(unique_calibration_samples), 'origins_separately_counted': dict(origin_counts),
            'coverage_boundary': 'Sensitivity perturbations are local evidence, not independent global coverage.', 'M1_outcomes': dict(Counter(
            r['judgment']['m1_feasibility'] for r in unique_calibration_samples)), 'displayed_samples': samples,
            'coverage': 'Only sampled points carry evidence. Unsampled design space remains unknown.'},
        'sensitivity': derivatives,
        'budget': {'total_new_M1_limit': policy_config['total_m1_budget'], 'calibration_M1_calls': calibration['new_M1_calls'],
                   'executor_M1_calls': explorer.cost()['M1_calls'], 'remaining_M1_calls': remaining,
                   'max_this_decision_M1_calls': min(remaining, policy_config['max_round_m1']),
                   'remaining_LLM_calls_including_this': calls_remaining,
                   'max_auxiliary_probe_M1_calls': policy_config['seed_probe_budget'],
                   'final_recommendation_reserve': explorer.cost()['reserved_recommendation_M1_calls'],
                   'minimum_seeded_SLSQP_budget_by_active_dimension':
                       {str(d): slsqp_cost_model(d)['minimum_action_budget'] for d in range(1,7)},
                   'SLSQP_cost_models_by_active_dimension':{str(d):slsqp_cost_model(d) for d in range(1,7)}},
        'execution_and_stop': {'solver': 'continuous SLSQP maximin of supported M1 bound margins',
            'finite_difference_cost': 'Initial differences alone do not complete optimization. The controller budgets '
                                      'two update opportunities per admitted start; line searches can add more. '
                                      'Small legal budgets return SKIPPED_BUDGET, not invalid LLM decisions.',
            'quality_target_minimum_normalized_margin': policy_config['quality_target'],
            'quality_stop_minimum_decisions': policy_config['min_decisions_before_quality_stop'],
            'mode': policy_config.get('mode', 'INITIAL_ALLOCATION'),
            'material_improvement_abs': policy_config.get('improvement_abs', 1e-6),
            'material_improvement_rel': policy_config.get('improvement_rel', 1e-6),
            'LLM_can_stop_after_observation': bool(history),
            'meaning': 'Finding a feasible point does not certify the box or establish global optimality.'},
        'valid_seed_ids': [r['evidence_id'] for r in samples if r['seed_eligible']],
        'allowed_evidence_ids': sorted({r['evidence_id'] for r in rules+derivatives+samples} |
            {s for r in derivatives for c in r['stencils'].values() for s in c['evidence_ids']} |
            {o['observation_id'] for record in history for o in record['observations']}),
        'history': recent, 'validation_feedback': correction,
        'scope': 'Propose geometry; only the executor evaluates M1. Never infer M2, capture, lock time or jitter PASS.'}


def knowledge_identity(context):
    return fingerprint(knowledge(context))
