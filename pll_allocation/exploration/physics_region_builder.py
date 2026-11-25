"""Bounded joint construction using the original inverse; never an M1 evaluator.

Strategy preferences choose a sampling order. Only the original user domain is
used for the inverse. A local search box is constructed AFTER a complete seed.
"""
from copy import deepcopy
import math
import re
import time

from scipy.stats import qmc

from ..allocation.core import Meter
from ..allocation.physics import inverse_at_shape, pm_ceiling
from ..block_space.contracts import FREE_IDS
from ..physics_mapping.model import fingerprint
from ..region_explorer.assessment import contains_parameters, normalized_point, physical_coordinate
from .contracts import active_m1_specs, axes, check_candidate, make_parameters, number, require, screen_problem

REQUEST_SCHEMA = 'pll-physics-region-request-1.0'
OBJECTIVE_REQUEST_SCHEMA = 'pll-physics-region-request-1.1'
PROPOSAL_SCHEMA = 'pll-physics-region-proposal-1.0'
STRATEGIES = {'HIGH_PM_LF_SHAPE', 'BW_TARGETED_INVERSE', 'GAIN_SPLIT_EXPLORATION',
              'VCO_TUNING_EXPLORATION', 'DIVERSITY_EXPLORATION'}
FOCI = {'LF_SHAPE', 'LOOP_GAIN', 'GAIN_SPLIT', 'TUNING', 'DIVERSITY'}
RADII = {'LOCAL': .08, 'BALANCED': .15, 'BROAD': .25}


class PhysicsRequestError(ValueError):
    def __init__(self, path, expected, actual):
        self.details = {'path': path, 'missing_fields': sorted(expected-set(actual)) if isinstance(actual, dict) else sorted(expected),
                        'unexpected_fields': sorted(set(actual)-expected) if isinstance(actual, dict) else [],
                        'expected_fields': sorted(expected), 'actual_type': type(actual).__name__}
        super().__init__('Physics request field mismatch: '+str(self.details))


def available_physical_objectives(physics_options):
    options = physics_options or {}
    return (['NOISE_AWARE'] if options.get('noise_allocation_enabled') else []) + (
        ['INITIAL_STATE_AWARE', 'FAST_LOCK'] if options.get('initial_state_aware_enabled') else [])


def validate_objectives(request, physics_options):
    """Only the versioned opt-in request may select conditional preferences.

    These are priorities within configured feasibility tiers, not permission to
    replace limits, profile, startup settings, six parameters or verdicts.
    """
    goals = request['physical_objectives']
    allowed = available_physical_objectives(physics_options)
    require(bool(allowed), 'physical objectives are not enabled by configuration')
    require(isinstance(goals, list) and 1 <= len(goals) <= len(allowed) and
            all(isinstance(g, str) and g in allowed for g in goals) and len(set(goals)) == len(goals),
            'unique enabled physical objectives in priority order required')
    require(request['tool_options_sha256'] == fingerprint(physics_options), 'current physical tool options binding required')


def validate_request(raw, problem, model_fingerprint, allowed_evidence, *, attempts_left, m1_left,
                     physics_options=None):
    if isinstance(raw, dict) and raw.get('schema_version') == OBJECTIVE_REQUEST_SCHEMA:
        fields = {'schema_version', 'request_id', 'problem_sha256', 'model_fingerprint', 'strategy',
                  'target_bw_fraction', 'physics_focus', 'tuning_preference', 'seed_count',
                  'region_width_policy', 'budget', 'evidence_ids', 'physical_objectives', 'tool_options_sha256'}
        if set(raw) != fields:
            raise PhysicsRequestError('request', fields, raw)
        validate_objectives(raw, physics_options)
        legacy = {k: deepcopy(v) for k, v in raw.items() if k not in ('physical_objectives', 'tool_options_sha256')}
        legacy['schema_version'] = REQUEST_SCHEMA
        validate_request(legacy, problem, model_fingerprint, allowed_evidence,
                         attempts_left=attempts_left, m1_left=m1_left)
        return deepcopy(raw)
    fields = {'schema_version', 'request_id', 'problem_sha256', 'model_fingerprint', 'strategy',
              'target_bw_fraction', 'physics_focus', 'tuning_preference', 'seed_count',
              'region_width_policy', 'budget', 'evidence_ids'}
    if not isinstance(raw, dict) or set(raw) != fields:
        raise PhysicsRequestError('request', fields, raw)
    require(raw['schema_version'] == REQUEST_SCHEMA, 'unsupported PhysicsRegionRequest version')
    r = deepcopy(raw)
    require(isinstance(r['request_id'], str) and re.fullmatch(r'[A-Za-z0-9_:-]{1,70}', r['request_id']) is not None,
            'request_id requires 1..70 letters/digits/underscore/colon/hyphen')
    require(r['problem_sha256'] == problem['problem_sha256'] and r['model_fingerprint'] == model_fingerprint,
            'current problem/model binding required')
    require(r['strategy'] in STRATEGIES, 'unsupported physics strategy')
    f = r['target_bw_fraction']
    require(isinstance(f, list) and len(f) == 2 and 0 <= number(f[0], 'BW fraction') <= number(f[1], 'BW fraction') <= 1,
            'BW target fraction must stay inside supported target interval')
    require(isinstance(r['physics_focus'], list) and bool(r['physics_focus']) and
            all(x in FOCI for x in r['physics_focus']), 'supported physics focus required')
    require(r['tuning_preference'] in ('INTERIOR', 'LOW_VOLTAGE', 'HIGH_VOLTAGE', 'DIVERSE'), 'invalid tuning preference')
    require(type(r['seed_count']) is int and 1 <= r['seed_count'] <= 8, 'one to eight seeds required')
    require(r['region_width_policy'] in RADII, 'unknown region width policy')
    b = r['budget']
    if not isinstance(b, dict) or set(b) != {'construction_attempts', 'm1_calls'}:
        raise PhysicsRequestError('request.budget', {'construction_attempts', 'm1_calls'}, b)
    require(type(b['construction_attempts']) is int and 1 <= b['construction_attempts'] <= min(64, attempts_left),
            'construction attempt hard budget exceeded')
    require(type(b['m1_calls']) is int and r['seed_count'] <= b['m1_calls'] <= m1_left,
            'M1 budget must cover requested seeds and fit session')
    require(isinstance(r['evidence_ids'], list) and bool(r['evidence_ids']) and
            all(isinstance(i, str) and i in allowed_evidence for i in r['evidence_ids']), 'unknown/empty physics evidence')
    return r


def gain_tuning_interval(problem, product):
    """Intersection of Icp*Kvco=P with user gain bounds and open tuning rails.

    This is interval arithmetic on the Registry's gain/tuning equations, not a
    new dynamic model. Dividing inequalities handles negative/zero rail values.
    """
    a = problem['parameters']; fixed = problem['fixed_parameters']
    lo = max(a['Kvco']['min'], product/a['Icp']['max'])
    hi = min(a['Kvco']['max'], product/a['Icp']['min'])
    out = {'required_Icp_Kvco_product': product,
           'user_Icp_A': [a['Icp']['min'], a['Icp']['max']],
           'user_Kvco_Hz_per_V': [a['Kvco']['min'], a['Kvco']['max']],
           'gain_compatible_Kvco_interval': [lo, hi], 'status': 'NO_COMPATIBLE_GAIN_SPLIT'}
    if lo > hi:
        return out
    target = fixed['N']['value']*fixed['f_ref']['value']
    # kv*vmin < target-f0min; kv*vmax > target-f0max. Both are strict.
    for coefficient, rhs, less in (
        (fixed['Vctrl_min']['value'], target-a['f0']['min'], True),
        (fixed['Vctrl_max']['value'], target-a['f0']['max'], False)):
        if coefficient == 0:
            if not (0 < rhs if less else 0 > rhs):
                out.update(status='TUNING_CONFLICT', tuning_compatible_Kvco_interval=None)
                return out
            continue
        edge = rhs/coefficient
        upper = less == (coefficient > 0)
        if upper:
            hi = min(hi, math.nextafter(edge, -math.inf))
        else:
            lo = max(lo, math.nextafter(edge, math.inf))
    out.update(status='JOINT_INTERVAL_COMPATIBLE' if lo <= hi else 'TUNING_CONFLICT',
               tuning_compatible_Kvco_interval=[lo, hi],
               user_f0_Hz=[a['f0']['min'], a['f0']['max']],
               Vctrl_rails_V=[fixed['Vctrl_min']['value'], fixed['Vctrl_max']['value']])
    return out


def around_seed(problem, seed, width_policy):
    radius = RADII[width_policy]
    u = normalized_point(problem, seed)
    bounds = {k: [max(0., v-radius), min(1., v+radius)] for k, v in u.items()}
    require(all(0 <= lo < hi <= 1 for lo, hi in bounds.values()) and contains_parameters(problem, bounds, seed),
            'constructed seed/region containment failed')
    return bounds


def target_interval(problem):
    bw = next((s for s in active_m1_specs(problem) if s['metric'] == 'BW_Hz'), None)
    if bw is None:
        return None
    # One-sided requests have an explicit heuristic target range; never relax
    # the original hard judgment. Negative/zero BW limits cannot seed inverse.
    lo = bw.get('min', bw.get('max', 0.)*.5)
    hi = bw.get('max', lo*1.5)
    return [lo, hi] if 0 < lo <= hi else None


def build_physics_region(problem, request, *, model_fingerprint, random_seed, history=(), excluded=(), physics_options=None,
                         minimum_distance=0.):
    """Return prechecked seeds/proposals only. Caller owns validation and M1.

    At most one original inverse per charged construction attempt. The exact
    same cap/shape/target is never retried within a request. Global necessary
    contradictions stop before any inverse. Non-certifying construction failure
    never becomes a global infeasibility certificate.
    """
    start, cpu = time.perf_counter(), time.process_time()
    cap = request['budget']['construction_attempts']; meter = Meter(cheap_limit=cap, m1_limit=0)
    trace, seeds, seen = [], [], set(excluded)
    conditional = None
    noise_search = bool(physics_options and physics_options['noise_allocation_enabled'])
    startup_search = bool(physics_options and physics_options['initial_state_aware_enabled'])
    extended_search = noise_search or startup_search
    if physics_options:
        from .conditional_physics import ConditionalPhysics
        conditional = ConditionalPhysics(problem, physics_options)
    goals = []
    if request.get('schema_version') == OBJECTIVE_REQUEST_SCHEMA:
        validate_objectives(request, physics_options)
        goals = request['physical_objectives']
    trial_cache = {}
    result = {'schema_version': PROPOSAL_SCHEMA, 'strategy_id': request['request_id'],
        'request': deepcopy(request), 'problem_sha256': problem['problem_sha256'], 'model_fingerprint': model_fingerprint,
        'status': 'NO_SEED_FOUND_WITHIN_ATTEMPT_BUDGET', 'seeds': seeds, 'regions': [],
        'evidence_ids': list(request['evidence_ids']), 'relations': ['REL:shape', 'REL:phase_ceiling', 'REL:inverse_gain', 'REL:frequency'],
        'm1_evaluated': False, 'm1_status': 'M1_NOT_EVALUATED', 'whole_region_M1_certified': False,
        'global_infeasibility_proven': False, 'attempts': trace, 'failure_reasons': []}
    screen = screen_problem(problem); result['global_screening'] = screen
    targets = target_interval(problem)
    if screen['certificates']:
        result.update(status='GLOBAL_NECESSARY_CONTRADICTION', global_infeasibility_proven=True)
    elif targets is None:
        result.update(status='LF_SHAPE_NOT_SUPPORTED', failure_reasons=[{'code': 'INVERSE_REQUIRES_POSITIVE_SUPPORTED_BW_TARGET'}])
    else:
        a = problem['parameters']; pm = next((s['min']-s['tolerance'] for s in active_m1_specs(problem)
                                              if s['metric'] == 'PM_deg' and 'min' in s), -math.inf)
        draws = qmc.Sobol(d=4, scramble=True, seed=random_seed).random_base2((cap-1).bit_length())
        strategy = request['strategy']
        previous = [normalized_point(problem, p) for p in history]
        for i, draw in enumerate(draws[:cap]):
            if len(seeds) >= request['seed_count'] and not extended_search:
                break
            c1 = physical_coordinate(a['C1'], float(draw[0])); c2 = physical_coordinate(a['C2'], float(draw[1]))
            if i == 0:
                c1, c2 = a['C1']['min'], a['C2']['max']
            elif strategy == 'HIGH_PM_LF_SHAPE':
                c1 = physical_coordinate(a['C1'], float(draw[0])*.5)
                c2 = physical_coordinate(a['C2'], .5+float(draw[1])*.5)
            ceiling = pm_ceiling(c1, c2)
            fraclo, frachi = request['target_bw_fraction']
            bw = targets[0]+(targets[1]-targets[0])*(fraclo+(frachi-fraclo)*float(draw[2]))
            # Peak first, then two sides and continuous shape exploration.
            factor = 1. if i == 0 else (.8, 1.25, 1.)[(i-1)%3]
            if strategy == 'DIVERSITY_EXPLORATION' and i:
                factor = .6+float(draw[3])*1.1
            shape = math.sqrt(1+c2/c1)*factor
            entry = {'index': len(trace)+1, 'C1_F': c1, 'C2_F': c2, 'target_BW_Hz': bw,
                     'shape_x': shape, 'PM_ceiling_deg': ceiling, 'status': 'STARTED'}
            trace.append(entry)
            if ceiling < pm:
                entry.update(status='LF_SHAPE_NOT_SUPPORTED', reason='CAPACITOR_RATIO_PM_CEILING')
                continue
            try:
                raw = inverse_at_shape(axes(problem), c1, c2, bw, shape, meter)
                if meter.events and meter.events[-1].get('boundary_corrections'):
                    entry['boundary_corrections'] = deepcopy(meter.events[-1]['boundary_corrections'])
                    entry['formal_M1_required'] = True
                if raw is None:
                    entry.update(status='NO_COMPATIBLE_GAIN_SPLIT', global_Icp_A=[a['Icp']['min'], a['Icp']['max']],
                                 global_Kvco_Hz_per_V=[a['Kvco']['min'], a['Kvco']['max']])
                    continue
                if not a['Rz']['min'] <= raw['Rz'] <= a['Rz']['max']:
                    entry.update(status='GLOBAL_BOUNDS_CONFLICT', axis='Rz', value=raw['Rz'],
                                 bounds=[a['Rz']['min'], a['Rz']['max']])
                    continue
                product = raw['Icp']*raw['Kvco']; joint = gain_tuning_interval(problem, product)
                entry['joint_precheck'] = joint
                if joint['status'] != 'JOINT_INTERVAL_COMPATIBLE':
                    entry['status'] = joint['status']
                    continue
                klo, khi = joint['tuning_compatible_Kvco_interval']
                split = [0., .5, 1.] if extended_search else ([.2, .5, .8] if strategy in (
                    'GAIN_SPLIT_EXPLORATION', 'VCO_TUNING_EXPLORATION') else [.5])
                for fraction in split:
                    kv = math.exp(math.log(klo)+fraction*(math.log(khi)-math.log(klo))) if klo != khi else klo
                    current = deepcopy(raw); current.update(Icp=product/kv, Kvco=kv)
                    target = problem['fixed_parameters']['N']['value']*problem['fixed_parameters']['f_ref']['value']
                    vlo = max(problem['fixed_parameters']['Vctrl_min']['value'], (target-a['f0']['max'])/kv)
                    vhi = min(problem['fixed_parameters']['Vctrl_max']['value'], (target-a['f0']['min'])/kv)
                    preference = request['tuning_preference']
                    tuning_fractions = [.2, .5, .8] if preference == 'DIVERSE' else [
                        .2 if preference == 'LOW_VOLTAGE' else .8 if preference == 'HIGH_VOLTAGE' else .5]
                    voltages = [(vlo+vf*(vhi-vlo), 'LEGACY_TUNING') for vf in tuning_fractions]
                    if startup_search:
                        safe = physics_options['safe_rail_margin_V']
                        safe_lo = max(vlo, problem['fixed_parameters']['Vctrl_min']['value']+safe)
                        safe_hi = min(vhi, problem['fixed_parameters']['Vctrl_max']['value']-safe)
                        if safe_lo <= safe_hi:
                            voltages = [(min(safe_hi, max(safe_lo, .15+delta)), 'STARTUP_OFFSET:'+str(delta))
                                        for delta in physics_options['delta_offsets_V']]
                            voltages += [((safe_lo+safe_hi)/2, 'MID_TUNING')]
                        else:
                            entry['startup_fallback'] = 'EMPTY_SAFE_INTERVAL_KEEP_LEGAL_LEGACY_TUNING'
                    for voltage, purpose in voltages:
                        current['f0'] = target-kv*voltage
                        candidate = make_parameters(problem, current)
                        screened = check_candidate(problem, candidate)
                        if screened['status'] != 'NECESSARY_CONDITIONS_SATISFIED':
                            entry.setdefault('rejected_splits', []).append(screened)
                            continue
                        key = fingerprint(candidate)
                        if key in seen:
                            entry.setdefault('duplicate_candidates', 0); entry['duplicate_candidates'] += 1
                            continue
                        seen.add(key)
                        sid = 'PRB:'+request['request_id']+':S'+str(len(seeds)+1)
                        box = around_seed(problem, candidate, request['region_width_policy'])
                        point = normalized_point(problem, candidate)
                        distance = min((math.sqrt(sum((point[k]-p[k])**2 for k in FREE_IDS)) for p in previous), default=None)
                        if strategy == 'DIVERSITY_EXPLORATION' and distance is not None and distance < .05:
                            entry.setdefault('diversity_rejections', 0); entry['diversity_rejections'] += 1
                            continue
                        seed = {'seed_id': sid, 'region_id': sid+':R', 'parameters': candidate,
                            'parameter_sha256': key, 'normalized_bounds': box,
                            'source': 'TOOL_COMPUTED_GLOBAL_JOINT_INVERSE', 'construction_attempt': entry['index'],
                            'screening': screened, 'gain_tuning_precheck': joint,
                            'nearest_existing_normalized_distance': distance,
                            'm1_evaluated': False, 'm1_status': 'M1_NOT_EVALUATED'}
                        if startup_search:
                            from ..physics_mapping.analytic_features import analytic_features
                            seed['construction_purpose'] = purpose
                            seed['analytic_features'] = analytic_features(candidate)
                        if extended_search:
                            from ..allocation.physics import raw_prediction
                            from ..physics_mapping.model import parse_parameters
                            p = parse_parameters(candidate)
                            trial_key = tuple(p[k] for k in ('Icp', 'Kvco', 'Rz', 'C1', 'C2'))
                            if noise_search and trial_key not in trial_cache:
                                trial_cache[trial_key] = conditional.cheap_estimate(candidate)
                            value = trial_cache.get(trial_key)
                            metrics = raw_prediction(p)
                            margins = [(metrics[s['metric']]-s['min']+s['tolerance'])/s['normalization_scale']
                                       for s in active_m1_specs(problem) if 'min' in s]
                            margins += [(s['max']-metrics[s['metric']]+s['tolerance'])/s['normalization_scale']
                                        for s in active_m1_specs(problem) if 'max' in s]
                            seed['conditional_construction'] = {'predicted_jitter_trial_s': value,
                                'M1_proxy_margin': min(margins), 'formal_M1_evaluated': False,
                                'noise_limit_s': conditional.limit}
                        seeds.append(seed)
                        entry['status'] = 'SEED_CONSTRUCTED'
                        if len(seeds) >= request['seed_count'] and not extended_search:
                            break
                    if len(seeds) >= request['seed_count'] and not extended_search:
                        break
                if entry['status'] == 'STARTED':
                    entry['status'] = 'NO_NEW_LEGAL_SEED'
            except (ValueError, ArithmeticError, RuntimeError) as error:
                entry.update(status='INVERSE_MODE_FAILED', reason=type(error).__name__+': '+str(error),
                             reason_code=getattr(error, 'reason_code', 'INVERSE_CONSTRUCTION_ERROR'),
                             numerical_diagnostics=getattr(error, 'diagnostics', {}), global_infeasibility_proven=False)
        if extended_search and seeds:
            # Lexicographic conditional frontier: never trade a supported M1
            # bound for noise. Failed noise trials remain proposals/evidence.
            def priority(seed):
                info = seed['conditional_construction']; value = info['predicted_jitter_trial_s']
                return (info['M1_proxy_margin'] < 0,
                    noise_search and conditional.limit is not None and value > conditional.limit,
                    value if value is not None else 0., -info['M1_proxy_margin'], seed['parameter_sha256'])
            ordered = sorted(seeds, key=priority)
            result['conditional_search'] = {'trial_count': len(seeds), 'noise_integrations': len(trial_cache),
                'noise_limit_s': conditional.limit, 'best_predicted_trial_s': min(trial_cache.values(), default=None),
                'stop_reason': 'CONSTRUCTION_ATTEMPT_LIMIT',
                'selection_rule': 'M1 proxy feasibility, conditional jitter limit, minimum jitter, M1 margin; formal recheck required'}
            chosen = []
            from ..region_explorer.assessment import normalized_point as point_of
            if startup_search:
                # Within the best M1/conditional feasibility tier, retain distinct
                # implementation preferences and shapes, not only minimum delta.
                tier = priority(ordered[0])[:2]
                viable = [s for s in ordered if priority(s)[:2] == tier]
                def quantities(s):
                    p = s['parameters']['values']; f = s['analytic_features']
                    return p, f
                selectors = [
                    ('NOISE_FAVORABLE', lambda s: s['conditional_construction']['predicted_jitter_trial_s'] or 0.),
                    ('FAST_LOCK_PROXY', lambda s: abs(quantities(s)[1]['initial_frequency_error_Hz'])),
                    ('MID_TUNING', lambda s: -quantities(s)[1]['tuning_rail_margin_V']),
                    ('LOW_TOTAL_CAPACITANCE', lambda s: quantities(s)[0]['C1']['value']+quantities(s)[0]['C2']['value']),
                    ('LOW_ICP', lambda s: quantities(s)[0]['Icp']['value']),
                    ('LF_SHAPE_DIVERSITY', lambda s: -quantities(s)[0]['C2']['value']/quantities(s)[0]['C1']['value'])]
                if goals:
                    targeted = {
                        'NOISE_AWARE': selectors[0],
                        'FAST_LOCK': selectors[1],
                        'INITIAL_STATE_AWARE': ('INITIAL_STATE_AWARE', lambda s: abs(
                            s['screening']['derived']['Vctrl_required_V']-.15))}
                    preferences = [targeted[g] for g in goals]
                    selectors = preferences+[s for s in selectors if s[0] not in {p[0] for p in preferences}]
                diverse = []
                for label, selector in selectors:
                    for s in sorted(viable, key=lambda s: (selector(s), priority(s))):
                        point = point_of(problem, s['parameters'])
                        if all(math.sqrt(sum((point[k]-old[k])**2 for k in FREE_IDS)) >= minimum_distance and
                               point != old for old in previous+[point_of(problem, x['parameters']) for x in diverse]):
                            s['selection_preference'] = label; diverse.append(s); break
                ordered = diverse+[s for s in ordered if s not in diverse]
            for seed in ordered:
                point = point_of(problem, seed['parameters'])
                # Preserve the original downstream distance filter; avoid wasting
                # the small formal seed quota on identical or very close trials.
                if all(math.sqrt(sum((point[k]-old[k])**2 for k in FREE_IDS)) >= minimum_distance and point != old
                       for old in previous+[point_of(problem, s['parameters']) for s in chosen]):
                    chosen.append(seed)
                if len(chosen) >= request['seed_count']:
                    break
            result['conditional_trial_frontier'] = [{'parameter_sha256': s['parameter_sha256'],
                'parameters': s['parameters'], **s['conditional_construction']} for s in ordered]
            seeds[:] = chosen
        if seeds:
            result['status'] = 'SEEDS_CONSTRUCTED' if len(seeds) == request['seed_count'] else 'PARTIAL_SEEDS_CONSTRUCTED'
        result['regions'] = [{'region_id': s['region_id'], 'seed_id': s['seed_id'],
                              'normalized_bounds': s['normalized_bounds'], 'whole_region_M1_certified': False} for s in seeds]
        result['failure_reasons'] = [deepcopy(e) for e in trace if e['status'] != 'SEED_CONSTRUCTED']
    result['seed_ids'] = [s['seed_id'] for s in seeds]; result['region_ids'] = [s['region_id'] for s in seeds]
    result['cost'] = {'construction_attempts': len(trace), 'construction_failures': sum(e['status'] != 'SEED_CONSTRUCTED' for e in trace),
        'inverse_calls': meter.counts['analytic_calls'], 'attempt_limit': cap, 'remaining_attempt_budget': cap-len(trace),
        'M1_calls': 0, 'wall_time_s': time.perf_counter()-start, 'process_cpu_s': time.process_time()-cpu}
    if goals:
        result['objective_selection'] = {'physical_objectives': deepcopy(goals),
            'tool_options_sha256': request['tool_options_sha256'],
            'semantics': 'Ordered construction preferences inside configured M1/conditional noise tiers; no formal PASS',
            'effective_seed_preferences': [s.get('selection_preference', 'NOISE_FAVORABLE') for s in seeds]}
    result['proposal_sha256'] = fingerprint(result)
    return result
