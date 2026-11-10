"""Deterministic first-shot policies; only propose complete 17-input candidates."""
from __future__ import annotations
import itertools
import math
import random
from .core import assess_m1, bounds, make_candidate, margin_details, values
from .physics import cheap_predict, inverse_at_shape, propagate, raw_prediction


def generated(model, overrides, meter):
    meter.charge('candidate_generations')
    return make_candidate(model, overrides)


def analytical(model, system_spec, meter):
    domain = propagate(model, system_spec)
    if domain['status'] == 'PROVEN_INFEASIBLE':
        return None, {'status': 'PROVEN_INFEASIBLE', 'propagation': domain}
    bw = next(s for s in system_spec['metrics'] if s['metric'] == 'BW_Hz')
    target = (bw['min'] + bw['max'])/2
    candidates, rejected = [], []
    for pair in domain['capacitor_pairs']:
        if pair['x_interval'] is None:
            continue
        c1, c2 = pair['C1'], pair['C2']
        p = inverse_at_shape(model, c1, c2, target, math.sqrt(1 + c2/c1), meter)
        try:
            if p is None:
                raise ValueError('gain split interval empty')
            c = generated(model, p, meter)
            pred = cheap_predict(model, c, meter)
            margins = margin_details(model, system_spec, c, pred)
            candidates.append((margins['minimum_normalized_margin'], c, pred))
        except ValueError as error:
            rejected.append({'C1': c1, 'C2': c2, 'reason': str(error)})
    if not candidates:
        return None, {'status': 'NOT_FOUND', 'rejected_pairs': rejected, 'propagation': domain}
    score, candidate, pred = max(candidates, key=lambda item: item[0])
    return candidate, {'status': 'PROPOSED', 'propagation': domain, 'target_BW_Hz': target,
        'free_variables': ['capacitor_pair', 'x=sqrt(q)', 'Kvco_gain_split', 'f0_tuning_center'],
        'analytically_derived': ['Rz', 'Icp_from_product'], 'numerically_solved': ['BW/UGF ratio'],
        'rationale': 'Choose peak phase-lead shape per capacitor ratio, set BW scale, split gain within bounds, center tuning then project f0.',
        'cheap_prediction': pred, 'selection_score': score, 'candidate_pairs': len(candidates), 'rejected_pairs': rejected}


def sensitivity(model, system_spec, meter, candidate=None):
    candidate = candidate or make_candidate(model)
    p = values(candidate)
    center = assess_m1(model, system_spec, candidate, meter)
    if not center['prediction'] or center['prediction']['status'] != 'OK':
        raise ValueError('sensitivity requires a valid center')
    m0 = center['prediction']['metrics']
    columns = {}
    for name in ('Icp', 'Rz', 'f0', 'Kvco'):
        lo, hi = bounds(model, name)
        a, b = max(lo, p[name]*.99), min(hi, p[name]*1.01)
        lower = assess_m1(model, system_spec, generated(model, {**p, name: a}, meter), meter)
        upper = assess_m1(model, system_spec, generated(model, {**p, name: b}, meter), meter)
        if not lower['prediction'] or not upper['prediction']:
            columns[name] = {'status': 'DOMAIN_LIMITED'}
            continue
        ma, mb = lower['prediction']['metrics'], upper['prediction']['metrics']
        delta = math.log(b/a)
        columns[name] = {'status': 'OK', 'points': [a, b],
            'log_elasticity': {k: math.log(mb[k]/ma[k])/delta for k in ('BW_Hz', 'UGF_Hz', 'Vctrl_required_V')},
            'PM_deg_per_log_parameter': (mb['PM_deg'] - ma['PM_deg'])/delta,
            'PM_curvature_log': (mb['PM_deg'] + ma['PM_deg'] - 2*m0['PM_deg'])/(delta/2)**2}
    return {'center_parameter_sha256': center['prediction']['parameter_sha256'], 'columns': columns,
            'continuous_step_fraction': .01, 'discrete_C': 'enumerated, not differentiated',
            'free_coordinate_decision': 'Icp and Kvco have identical loop elasticities: solve in product gain, Rz, Kvco and Vreq',
            'scope': 'local M1 derivatives; curvature diagnostic; not a global model-error bound'}


def optimize(model, system_spec, meter, sensitivity_result=None, *, maxiter=60):
    """SLSQP epigraph maximin in scaled gain/R/Kvco/Vreq coordinates.

    Cheap algebraic trials may violate allocation bounds; only a checked complete
    candidate is returned. Solver success flags never determine M1 PASS.
    """
    import numpy as np
    from scipy.optimize import minimize
    domain = propagate(model, system_spec)
    if domain['status'] == 'PROVEN_INFEASIBLE':
        return None, {'status': 'PROVEN_INFEASIBLE', 'propagation': domain}
    sens = sensitivity_result or sensitivity(model, system_spec, meter)
    bw = next(s for s in system_spec['metrics'] if s['metric'] == 'BW_Hz')
    pm = next(s for s in system_spec['metrics'] if s['metric'] == 'PM_deg')
    target_bw, bwscale = (bw['min'] + bw['max'])/2, (bw['max'] - bw['min'])/2
    if bwscale <= 0:
        raise ValueError('optimizer requires a nonzero BW interval')
    # First-order 1% independent-box allowance at nominal; explicitly heuristic.
    columns = [c for c in sens['columns'].values() if c['status'] == 'OK']
    guards = {'BW_Hz:min': .01*target_bw/bwscale*sum(abs(c['log_elasticity']['BW_Hz']) for c in columns),
              'PM_deg:min': .01/max(abs(pm.get('min', 0)), 1)*sum(abs(c['PM_deg_per_log_parameter']) for c in columns)}
    guards['BW_Hz:max'] = guards['BW_Hz:min']
    p0 = values(make_candidate(model))
    n = p0['N']
    ilo, ihi = bounds(model, 'Icp')
    klo, khi = bounds(model, 'Kvco')
    glo, ghi = ilo*klo/n, ihi*khi/n
    rlo, rhi = bounds(model, 'Rz')
    vlo, vhi = p0['Vctrl_min'], p0['Vctrl_max']
    lows = np.array([glo, rlo, klo, vlo + 1e-8])
    highs = np.array([ghi, rhi, khi, vhi - 1e-8])
    results, options = [], []
    for pair in domain['capacitor_pairs']:
        if pair['x_interval'] is None:
            continue
        if meter.counts['analytic_calls'] > meter.cheap_limit - 180:
            results.append({'status': 'SKIPPED_REMAINING_CHEAP_BUDGET', 'pair': pair})
            continue
        c1, c2 = pair['C1'], pair['C2']
        seed = inverse_at_shape(model, c1, c2, target_bw, math.sqrt(1 + c2/c1), meter)
        seed = {**p0, **(seed or {}), 'C1': c1, 'C2': c2}
        initial = np.clip((np.array([seed['Icp']*seed['Kvco']/n, seed['Rz'], seed['Kvco'],
                                    (n*p0['f_ref'] - seed['f0'])/seed['Kvco']]) - lows)/(highs - lows), 0, 1)
        cache = {}

        def trial(u):
            key = tuple(float(t) for t in u[:4])
            if key not in cache:
                gain, rz, kv, vreq = lows + np.asarray(u[:4])*(highs - lows)
                p = {**p0, 'C1': c1, 'C2': c2, 'Icp': float(n*gain/kv), 'Rz': float(rz),
                     'Kvco': float(kv), 'f0': float(n*p0['f_ref'] - kv*vreq)}
                prediction = meter.timed('analytic_calls', raw_prediction, p)
                meter.events[-1].update(parameters=p, scope='ALGEBRAIC_OPTIMIZER_TRIAL_NOT_M1')
                envelope = {'values': {k: {'value': v, 'unit': model['variables'][k]['unit']} for k, v in p.items()}}
                normalized = margin_details(model, system_spec, envelope, prediction)['normalized']
                margin = np.array([v - guards.get(k, 0) for k, v in normalized.items()])
                cache[key] = (p, prediction, margin)
            return cache[key]

        initial_t = min(trial(initial)[2]) - .01
        try:
            solved = minimize(lambda u: -u[4], np.r_[initial, initial_t], method='SLSQP',
                bounds=[(0, 1)]*4 + [(-10, 1)],
                constraints=[{'type': 'ineq', 'fun': lambda u: trial(u)[2] - u[4]}],
                options={'maxiter': maxiter, 'ftol': 1e-8, 'eps': 1e-6})
            p, pred, margins = trial(solved.x)
            record = {'C1': c1, 'C2': c2, 'solver_success': bool(solved.success),
                      'message': str(solved.message), 'iterations': int(solved.nit),
                      'unique_algebraic_trials': len(cache), 'robust_min_margin': float(min(margins))}
            results.append(record)
            try:
                candidate = generated(model, p, meter)
                cheap_predict(model, candidate, meter)
                options.append((float(min(margins)), candidate))
            except ValueError:
                record['candidate_status'] = 'ILLEGAL_OR_NO_INTERIOR_TUNING'
        except RuntimeError as error:
            results.append({'status': str(error), 'unique_algebraic_trials': len(cache)})
            break
    if not options:
        return None, {'status': 'NOT_FOUND', 'solver_runs': results, 'sensitivity': sens}
    score, candidate = max(options, key=lambda item: item[0])
    return candidate, {'status': 'PROPOSED', 'solver': 'scipy.optimize.SLSQP',
        'coordinates': ['Icp*Kvco/N', 'Rz', 'Kvco', 'Vctrl_required_V'],
        'objective': 'maximize worst normalized BW/PM/continuous-domain/tuning margin minus local first-order guard',
        'guard_assumption': '1% independent continuous parameter perturbations; nominal local heuristic, not model-error evidence',
        'guards': guards, 'selection_score': score, 'solver_runs': results, 'sensitivity': sens,
        'rationale': 'Use M1 sensitivities to expose equal loop-gain columns, reduce coupling and guard nominal derivatives; enumerate actual C choices.'}


def random_candidate(model, meter, seed=23):
    rng = random.Random(seed)
    p = {}
    for name, axis in model['variables'].items():
        if 'choices' in axis:
            p[name] = rng.choice(axis['choices'])
        elif 'range' in axis:
            lo, hi = bounds(model, name)
            p[name] = rng.uniform(lo, hi)
    return generated(model, p, meter), {'status': 'PROPOSED', 'seed': seed,
                                      'rationale': 'One uniform declared-domain draw, no rejection search or feedback.'}


def allocate(strategy, model, system_spec, meter, seed=23):
    if strategy == 'nominal':
        return generated(model, {}, meter), {'status': 'PROPOSED', 'rationale': 'Published model defaults; known prior.'}
    if strategy == 'analytical':
        return analytical(model, system_spec, meter)
    if strategy == 'sensitivity_optimization':
        return optimize(model, system_spec, meter)
    if strategy == 'random':
        return random_candidate(model, meter, seed)
    raise ValueError('unknown strategy')


def perturbation_check(model, system_spec, candidate, meter, fraction=.01):
    """16 corners of the four continuous parameters, no clipping/resampling."""
    p = values(candidate)
    rows = []
    for signs in itertools.product((-1, 1), repeat=4):
        updates = {name: p[name]*(1 + fraction*sign) for name, sign in zip(('Icp', 'Rz', 'f0', 'Kvco'), signs)}
        try:
            c = generated(model, {**p, **updates}, meter)
            pred = cheap_predict(model, c, meter)
            margins = margin_details(model, system_spec, c, pred)
            rows.append({'signs': signs, 'status': 'PREDICTED', 'metrics': pred, 'margins': margins})
        except ValueError:
            rows.append({'signs': signs, 'status': 'OUT_OF_DECLARED_OR_MODEL_DOMAIN'})
    return {'fraction': fraction, 'rows': rows, 'scope': 'post-selection M1-equation stress diagnostic; no M2 or silicon probability'}
