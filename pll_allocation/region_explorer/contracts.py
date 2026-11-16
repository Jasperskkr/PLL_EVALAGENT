"""Untrusted strategy decisions are checked independently of numeric solvers."""
from copy import deepcopy

from ..block_space.contracts import FREE_IDS
from ..exploration.contracts import active_m1_specs, check_candidate, number, require
from ..physics_mapping.model import fingerprint
from .assessment import contains_parameters

SCHEMA = 'pll-search-decision-1.0'
OBJECTIVE = 'MAXIMIZE_MIN_NORMALIZED_M1_MARGIN'
ACTIONS = {'PROBE', 'OPTIMIZE', 'REFINE', 'EXPAND', 'SWITCH', 'STOP'}


def decision_signature(decision):
    # Renaming the decision/region or rewriting its explanation cannot bypass duplicate detection.
    return fingerprint({k: decision[k] for k in ('action', 'normalized_bounds', 'active_variables',
                        'seed_ids', 'm1_budget', 'objective', 'random_seed', 'search_method', 'settings')})


def validate_decision(raw, *, context, evidence, regions, remaining_budget, seen_ids=(),
                      seen_signatures=(), last_region=None, stopped=False):
    require(not stopped, 'session already STOPPED')
    fields = {'schema_version', 'decision_id', 'context_sha256', 'action', 'region', 'normalized_bounds',
              'active_variables', 'seed_ids', 'm1_budget', 'objective', 'reason', 'evidence_ids',
              'random_seed', 'search_method', 'settings'}
    require(isinstance(raw, dict) and set(raw) == fields, 'complete SearchDecision fields required; unknown fields rejected')
    d = deepcopy(raw)
    require(d['schema_version'] == SCHEMA, 'unsupported SearchDecision version')
    require(isinstance(d['decision_id'], str) and 0 < len(d['decision_id']) <= 120, 'decision_id required')
    require(d['decision_id'] not in seen_ids, 'duplicate decision_id')
    require(d['context_sha256'] == context['context_sha256'], 'decision/context binding mismatch')
    require(isinstance(d['action'], str) and d['action'] in ACTIONS, 'unsupported action')
    require(isinstance(d['reason'], str) and bool(d['reason'].strip()), 'nonempty reason required')
    require(d['objective'] == OBJECTIVE, 'objective cannot change hard constraints')
    require(type(d['random_seed']) is int and 0 <= d['random_seed'] < 2**32, 'uint32 random_seed required')
    require(type(d['m1_budget']) is int and 0 <= d['m1_budget'] <= remaining_budget, 'action exceeds remaining M1 budget')
    bounds = d['normalized_bounds']
    require(isinstance(bounds, dict) and set(bounds) == set(FREE_IDS), 'all six normalized bounds required')
    for k, pair in bounds.items():
        require(isinstance(pair, list) and len(pair) == 2, k + ': [lower,upper] required')
        lo, hi = (number(v, k) for v in pair)
        require(0 <= lo < hi <= 1, k + ': bounds must be inside original domain [0,1]')
    active = d['active_variables']
    require(isinstance(active, list) and all(isinstance(k, str) and k in FREE_IDS for k in active)
            and len(set(active)) == len(active), 'invalid/duplicate active variables')
    # Canonical order makes equivalent decisions have identical signatures.
    d['active_variables'] = [k for k in FREE_IDS if k in active]
    for key in ('seed_ids', 'evidence_ids'):
        ids = d[key]
        require(isinstance(ids, list) and all(isinstance(k, str) and k in evidence for k in ids)
                and len(set(ids)) == len(ids), 'unknown/duplicate ' + key)
    region = d['region']
    require(isinstance(region, dict) and set(region) == {'region_id', 'parent_region_id'}, 'region and parent IDs required')
    rid, parent = region['region_id'], region['parent_region_id']
    require(isinstance(rid, str) and 0 < len(rid) <= 120, 'region_id required')
    require(parent is None or isinstance(parent, str) and parent in regions, 'unknown parent region')
    if rid in regions:
        require(bounds == regions[rid], 'known region ID cannot be rebound; use a new region ID')
    if d['action'] in ('REFINE', 'EXPAND'):
        require(parent is not None, 'REFINE/EXPAND require a known parent')
        outer, inner = (regions[parent], bounds) if d['action'] == 'REFINE' else (bounds, regions[parent])
        require(all(outer[k][0] <= inner[k][0] < inner[k][1] <= outer[k][1] for k in FREE_IDS)
                and outer != inner, 'REFINE/EXPAND must strictly shrink/enlarge parent within user domain')
    if d['action'] == 'SWITCH':
        require(rid != last_region, 'SWITCH requires a different region')
    method = d['search_method']
    require(method in ('SOBOL', 'SLSQP', 'NONE'), 'invalid search_method')
    if d['action'] == 'STOP':
        require(method == 'NONE' and not active and not d['seed_ids'] and d['m1_budget'] == 0
                and d['settings'] == {}, 'STOP cannot request search or M1 budget')
    else:
        require(bool(active) and d['m1_budget'] > 0 and method != 'NONE', 'search needs active variables and positive budget')
        require(d['action'] != 'PROBE' or method == 'SOBOL', 'PROBE uses SOBOL')
        require(d['action'] != 'OPTIMIZE' or method == 'SLSQP', 'OPTIMIZE uses SLSQP')
        for sid in d['seed_ids']:
            row = evidence[sid]
            require('parameters' in row and row.get('M1_status') == 'OK', 'seed requires valid formal M1 evidence')
            require(check_candidate(context['problem'], row['parameters'])['status'] == 'NECESSARY_CONDITIONS_SATISFIED',
                    'illegal seed/fixed values')
            require(contains_parameters(context['problem'], bounds, row['parameters']), 'seed outside decision region')
        if method == 'SLSQP':
            require(bool(d['seed_ids']) and bool(active_m1_specs(context['problem'])), 'SLSQP needs legal seeds and active M1 constraints')
            require(d['m1_budget'] >= 2, 'SLSQP needs budget including independent final recheck')
            settings = d['settings']
            require(isinstance(settings, dict) and set(settings) == {'maxiter', 'finite_difference_step'}, 'SLSQP settings required')
            require(type(settings['maxiter']) is int and 1 <= settings['maxiter'] <= 200, 'bounded maxiter required')
            require(0 < number(settings['finite_difference_step'], 'difference step') <= .01, 'difference step in (0,.01] required')
        else:
            require(len(active) == 6 or len(d['seed_ids']) == 1, 'subset probe needs exactly one seed for fixed values')
            settings = d['settings']
            require(isinstance(settings, dict) and set(settings) == {'sample_count'} and
                    type(settings['sample_count']) is int and 1 <= settings['sample_count'] <= 100000, 'bounded probe sample_count required')
    signature = decision_signature(d)
    require(signature not in seen_signatures, 'duplicate effective decision')
    return d
