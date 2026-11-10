"""ResearchProblemV2 adapts continuous user domains to the unchanged formal M1."""
from copy import deepcopy
import json
import math
from pathlib import Path

from ..allocation.physics import pm_ceiling
from ..block_space.contracts import FREE_IDS
from ..physics_mapping.experiment import parameters_from_experiment
from ..physics_mapping.model import (
    METRIC_PROTOCOLS, METRIC_UNITS, MODEL_ID, PARAMETERS, ModelError, fingerprint, parse_parameters,
)

SCHEMA = 'pll-research-problem-2.0'
PENDING_UNITS = {'lock_time_s': 's', 'jitter_s': 's', 'power_W': 'W'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def number(value, label):
    require(type(value) in (int, float) and math.isfinite(value), label + ': finite number required')
    return value


def capability(metric, source):
    if metric in METRIC_UNITS and source == 'M1':
        return 'M1_SUPPORTED'
    if metric == 'lock_time_s' and source == 'M2':
        return 'PENDING_M2'
    if metric in METRIC_UNITS and source == 'M2':
        return 'PENDING_M2'
    return 'UNSUPPORTED'


def resolve_problem(raw, *, seed=None, budget=None):
    require(isinstance(raw, dict) and raw.get('schema_version') == SCHEMA, 'ResearchProblemV2 required')
    p = deepcopy(raw)
    require(set(p) == {'schema_version', 'problem_id', 'topology', 'parameters', 'fixed_parameters',
                       'specs', 'exploration'}, 'unexpected or missing ResearchProblemV2 field')
    require(isinstance(p['problem_id'], str) and bool(p['problem_id']), 'problem_id required')
    require(p['topology'] == 'integer_n_cppll', 'only existing integer_n_cppll topology supported')
    require(isinstance(p['parameters'], dict) and set(p['parameters']) == set(FREE_IDS), 'six continuous axes required')
    for name, axis in p['parameters'].items():
        require(isinstance(axis, dict) and set(axis) == {'min', 'max', 'default', 'unit', 'scale'},
                name + ': min/max/default/unit/scale required')
        require(axis['unit'] == PARAMETERS[name][0], name + ': canonical SI unit required')
        lo, hi, default = [number(axis[k], name + '.' + k) for k in ('min', 'max', 'default')]
        require(0 < lo < hi and lo <= default <= hi, name + ': positive ordered range and contained default required')
        require(axis['scale'] in ('linear', 'log'), name + ': linear/log scale required')
    fixed = p['fixed_parameters']
    require(isinstance(fixed, dict) and set(fixed) == set(PARAMETERS)-set(FREE_IDS), 'all eleven fixed inputs required')
    for name, item in fixed.items():
        require(isinstance(item, dict) and set(item) == {'value', 'unit'} and item['unit'] == PARAMETERS[name][0],
                name + ': fixed canonical quantity required')
        number(item['value'], name)
    # The official parser owns ideality, integer N, signs and voltage/frequency semantics.
    try:
        parse_parameters(make_parameters(p))
    except ModelError as error:
        raise ValueError('unsupported fixed/default model inputs: ' + error.reason) from error
    require(isinstance(p['specs'], list) and bool(p['specs']), 'nonempty specs required')
    seen = set()
    units = {**METRIC_UNITS, **PENDING_UNITS}
    for spec in p['specs']:
        require(isinstance(spec, dict) and set(spec) <= {'metric', 'unit', 'enabled', 'min', 'max',
                'tolerance', 'evaluation_source', 'normalization_scale'} and
                {'metric', 'unit', 'enabled', 'evaluation_source'} <= set(spec), 'invalid Spec fields')
        name = spec['metric']
        require(isinstance(name, str) and name in units and name not in seen, 'unknown or duplicate Spec')
        seen.add(name)
        require(spec['unit'] == units[name] and type(spec['enabled']) is bool, name + ': unit/enabled mismatch')
        require(spec['evaluation_source'] in ('M1', 'M2', 'UNSUPPORTED'), name + ': explicit evaluation source required')
        bounds = [spec[k] for k in ('min', 'max') if k in spec]
        require(not spec['enabled'] or bool(bounds), name + ': enabled Spec needs a bound')
        for value in bounds:
            number(value, name + '.bound')
        require(not {'min', 'max'} <= set(spec) or spec['min'] <= spec['max'], name + ': inverted Spec bounds')
        spec.setdefault('tolerance', 0.)
        require(number(spec['tolerance'], name + '.tolerance') >= 0, 'negative tolerance')
        width = spec.get('max', 0) - spec.get('min', 0) if {'min', 'max'} <= set(spec) else 0
        spec.setdefault('normalization_scale', width/2 if width > 0 else max([abs(x) for x in bounds] + [1e-30]))
        require(number(spec['normalization_scale'], name + '.normalization_scale') > 0, 'positive normalization required')
        spec['support_status'] = capability(name, spec['evaluation_source'])
        spec['protocol'] = METRIC_PROTOCOLS[name] if spec['support_status'] == 'M1_SUPPORTED' else 'NOT_EVALUATED_IN_STAGE7'
    e = p['exploration']
    required = {'seed', 'sobol_samples', 'physics_seed_count', 'max_m1_evaluations', 'max_analytic_calls',
                'region_count', 'region_radius', 'sensitivity_step', 'sensitivity_representatives'}
    require(isinstance(e, dict) and set(e) == required, 'complete explicit exploration settings required')
    if seed is not None:
        e['seed'] = seed
    if budget is not None:
        e['max_m1_evaluations'] = budget
    for key in ('seed', 'sobol_samples', 'physics_seed_count', 'max_m1_evaluations', 'max_analytic_calls',
                'region_count', 'sensitivity_representatives'):
        require(type(e[key]) is int and e[key] >= 0, key + ': nonnegative integer required')
    require(e['seed'] < 2**32 and e['sobol_samples'] <= 1000000 and e['physics_seed_count'] <= 128,
            'bounded seed/sample settings required')
    require(e['sobol_samples'] + e['physics_seed_count'] > 0, 'at least one proposal required')
    require(e['max_m1_evaluations'] > 0 and e['region_count'] > 0, 'positive M1 and region budgets required')
    require(e['sensitivity_representatives'] <= e['region_count'], 'sensitivity representatives exceed regions')
    for key in ('region_radius', 'sensitivity_step'):
        require(0 < number(e[key], key) <= .5, key + ': normalized coordinate fraction in (0,.5] required')
    p['problem_sha256'] = fingerprint(p)
    return p


def load_problem(path, **overrides):
    return resolve_problem(json.loads(Path(path).read_text(encoding='utf-8-sig')), **overrides)


def axes(problem):
    return {'variables': {
        **{k: {'unit': v['unit'], 'default': v['default'], 'range': {'min': v['min'], 'max': v['max']}}
           for k, v in problem['parameters'].items()},
        **{k: {'unit': v['unit'], 'default': v['value'], 'fixed': v['value']}
           for k, v in problem['fixed_parameters'].items()}}}


def make_parameters(problem, overrides=None, *, check_bounds=True):
    model = axes(problem)
    updates = {name: float(axis['default']) for name, axis in problem['parameters'].items()}
    updates.update(overrides or {})
    for name in set(updates) & set(FREE_IDS):
        updates[name] = float(number(updates[name], name))
    if check_bounds:
        return parameters_from_experiment({'block_space': model}, updates)
    candidate = parameters_from_experiment({'block_space': model})
    for name, value in updates.items():
        require(name in candidate['values'], 'unknown candidate input: ' + name)
        candidate['values'][name]['value'] = float(value) if name in FREE_IDS else value
    return candidate


def coordinate(axis, value, *, inverse=False):
    lo, hi = axis['min'], axis['max']
    if inverse and value in (0, 1):
        return lo if value == 0 else hi
    if axis['scale'] == 'log':
        lo, hi = math.log(lo), math.log(hi)
        return math.exp(lo + value*(hi-lo)) if inverse else (math.log(value)-lo)/(hi-lo)
    return lo + value*(hi-lo) if inverse else (value-lo)/(hi-lo)


def active_m1_specs(problem):
    return [s for s in problem['specs'] if s['enabled'] and s['support_status'] == 'M1_SUPPORTED']


def check_candidate(problem, candidate):
    """Necessary conditions only. Never returns formal M1 or behavioral PASS."""
    try:
        p = parse_parameters(candidate)
        expected = make_parameters(problem, p)
        require(candidate == expected, 'unit/completeness/domain/fixed-input mismatch')
        vreq = (p['N']*p['f_ref']-p['f0'])/p['Kvco']
        q = 1 + p['C2']/p['C1']
        derived = {'output_frequency_Hz': p['N']*p['f_ref'], 'Vctrl_required_V': vreq,
                   'tuning_margin_V': min(vreq-p['Vctrl_min'], p['Vctrl_max']-vreq),
                   'Icp_Kvco_product': p['Icp']*p['Kvco'], 'loop_gain_Icp_Kvco_over_N': p['Icp']*p['Kvco']/p['N'],
                   'q': q, 'LF_zero_rad_s': 1/(p['Rz']*p['C2']),
                   'LF_pole_rad_s': q/(p['Rz']*p['C2']), 'PM_ceiling_deg': pm_ceiling(p['C1'], p['C2'])}
        require(all(math.isfinite(x) for x in derived.values()), 'nonfinite derived quantity')
        require(derived['tuning_margin_V'] > 0, 'no interior VCO tuning point')
        required = next((s['min']-s['tolerance'] for s in active_m1_specs(problem)
                         if s['metric'] == 'PM_deg' and 'min' in s), None)
        if required is not None and derived['PM_ceiling_deg'] < required:
            return {'status': 'NECESSARY_CONDITION_FAIL', 'reason': 'CAPACITOR_RATIO_PM_CEILING',
                    'derived': derived, 'required_PM_deg': required, 'formal_M1_evaluated': False}
        return {'status': 'NECESSARY_CONDITIONS_SATISFIED', 'reason': 'formal M1 still required',
                'derived': derived, 'formal_M1_evaluated': False}
    except (ModelError, ValueError, KeyError, TypeError, ArithmeticError) as error:
        return {'status': 'INVALID_CANDIDATE', 'reason': str(error), 'derived': {}, 'formal_M1_evaluated': False}


def screen_problem(problem):
    a = problem['parameters']
    try:
        ceiling = pm_ceiling(a['C1']['min'], a['C2']['max'])
        if not math.isfinite(ceiling):
            ceiling = None
    except (ArithmeticError, ValueError):
        ceiling = None
    target = problem['fixed_parameters']['N']['value']*problem['fixed_parameters']['f_ref']['value']
    certificates = []
    for s in active_m1_specs(problem):
        if s['metric'] == 'PM_deg' and 'min' in s and ceiling is not None and s['min']-s['tolerance'] > ceiling:
            certificates.append({'kind': 'GLOBAL_CAPACITOR_RATIO_PM_CEILING', 'upper_bound_deg': ceiling,
                                 'required_deg': s['min']-s['tolerance']})
        if s['metric'] == 'output_frequency_Hz' and (
                target < s.get('min', -math.inf)-s['tolerance'] or target > s.get('max', math.inf)+s['tolerance']):
            certificates.append({'kind': 'FIXED_FREQUENCY_PLAN', 'target_Hz': target})
        if s['metric'] in ('BW_Hz', 'UGF_Hz', 'PM_deg') and 'max' in s and s['max']+s['tolerance'] <= 0:
            certificates.append({'kind': 'POSITIVE_IDEAL_METRIC', 'metric': s['metric']})
    # All possible f0/Kvco/voltage endpoints bound the attainable static frequency union.
    frequencies = [f + k*v for f in (a['f0']['min'], a['f0']['max'])
                   for k in (a['Kvco']['min'], a['Kvco']['max'])
                   for v in (problem['fixed_parameters']['Vctrl_min']['value'],
                             problem['fixed_parameters']['Vctrl_max']['value'])]
    if all(math.isfinite(f) for f in frequencies) and not min(frequencies) < target < max(frequencies):
        certificates.append({'kind': 'GLOBAL_TUNING_UNREACHABLE', 'target_Hz': target,
                             'outer_frequency_envelope_Hz': [min(frequencies), max(frequencies)]})
    return {'status': 'PROVEN_M1_INFEASIBLE' if certificates else 'NECESSARY_CONDITIONS_ONLY',
            'global_PM_ceiling_deg': ceiling, 'certificates': certificates,
            'strict_conditions': ['positive SI inputs', 'complete fixed ideal topology', 'interior VCO tuning',
                                  'PM <= ideal continuous LF phase ceiling'],
            'heuristics': ['peak-phase inverse seeds', 'nearby coordinate boxes; no rejection by heuristic'],
            'domain_claim': 'USER_DECLARED_CONTINUOUS_BEHAVIORAL_DOMAIN; NO_CIRCUIT_CAPABILITY_CLAIM',
            'not_proven': 'No certificate is not proof of feasibility; sampling does not certify a region.'}


def judge(problem, candidate, result):
    valid = (result is not None and result.status.value == 'OK' and result.model_id == MODEL_ID
             and result.model_level == 'M1' and result.parameter_sha256 == fingerprint(candidate)
             and check_candidate(problem, candidate)['status'] != 'INVALID_CANDIDATE')
    checks = []
    for spec in problem['specs']:
        row = deepcopy(spec)
        known = (valid and spec['support_status'] == 'M1_SUPPORTED' and
                 result.units.get(spec['metric']) == spec['unit'] and
                 result.protocols.get(spec['metric']) == spec['protocol'])
        value = result.metrics.get(spec['metric']) if known else None
        known = known and type(value) in (int, float) and math.isfinite(value)
        by_bound = ({**({'min': value-spec['min']+spec['tolerance']} if 'min' in spec else {}),
                     **({'max': spec['max']-value+spec['tolerance']} if 'max' in spec else {})}
                    if known and spec['enabled'] else {})
        margin = min(by_bound.values(), default=None)
        row.update(value=value, margin=margin, normalized_margin=margin/spec['normalization_scale'] if margin is not None else None,
                   bound_margins=by_bound, tightest_bound=min(by_bound, key=by_bound.get) if by_bound else None,
                   status='DISABLED' if not spec['enabled'] else 'UNKNOWN' if margin is None else 'SATISFIED' if margin >= 0 else 'VIOLATED')
        checks.append(row)
    active = [r for r in checks if r['enabled'] and r['support_status'] == 'M1_SUPPORTED']
    state = 'NOT_REQUESTED' if not active else 'UNKNOWN' if any(r['status'] == 'UNKNOWN' for r in active) else (
        'INFEASIBLE' if any(r['status'] == 'VIOLATED' for r in active) else 'FEASIBLE')
    enabled = [r for r in checks if r['enabled']]
    all_status = 'FAIL' if any(r['status'] == 'VIOLATED' for r in enabled) else (
        'UNKNOWN' if any(r['status'] == 'UNKNOWN' for r in enabled) else 'M1_ONLY_SATISFIED' if enabled else 'NOT_REQUESTED')
    return {'m1_feasibility': state, 'all_enabled_specs_status': all_status, 'constraints': checks,
            'minimum_normalized_margin': min((r['normalized_margin'] for r in active if r['normalized_margin'] is not None), default=None),
            'verified_joint_block_spec': False, 'M2_status': 'NOT_EVALUATED'}
