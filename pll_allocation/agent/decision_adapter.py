"""LLM proposal envelope -> unchanged Stage8A SearchDecision validator."""
from copy import deepcopy
import json

from ..block_space.contracts import FREE_IDS
from ..exploration.contracts import require, screen_problem
from ..region_explorer.contracts import OBJECTIVE, SCHEMA
from ..region_explorer.assessment import normalized_point, physical_coordinate
from .run_state import optimization_executed, quality_state


class DecisionValidationError(ValueError):
    def __init__(self, message, details):
        super().__init__(message)
        self.details = details


def adapt_decision(raw, explorer, state, config, *, round_number, first):
    require(isinstance(raw, dict), 'decision must be a JSON object')
    stop = raw.get('action') == 'STOP'
    fields = {'action', 'reason', 'evidence_ids'} if stop else {
        'action', 'region_origin', 'normalized_bounds', 'active_variables', 'seed_ids', 'm1_budget', 'reason', 'evidence_ids'}
    require(set(raw)-({'stop_basis'} if stop else set()) == fields,
            'strict proposal fields required; do not include calculated metrics or model changes')
    require(raw['action'] in ('OPTIMIZE', 'STOP'), 'only SLSQP OPTIMIZE or STOP supported')
    require(not first or not stop, 'first decision must propose a six-axis region')
    require(isinstance(raw['evidence_ids'], list) and bool(raw['evidence_ids']) and
            all(isinstance(s, str) and s in state['allowed_evidence_ids'] for s in raw['evidence_ids']),
            'Evidence ID must be present in this PlannerState')
    if stop:
        basis = raw.get('stop_basis')
        best = state.get('best_known')
        if basis is None:
            # Version-1 decisions can cite the current best through its actual observation.
            ids = set(raw['evidence_ids'])
            direct = best and best['evidence_id'] in ids
            indirect = best and any(o['observation_id'] in ids and o['best_evidence_id'] and
                explorer.evidence[o['best_evidence_id']]['parameter_sha256'] ==
                explorer.evidence[best['evidence_id']]['parameter_sha256']
                for r in state['history'] for o in r['observations'])
            require(direct or indirect, 'STOP must reference current best or explicit budget/stall basis')
            basis = 'SPEC_SATISFIED'  # Legacy STOP means feasibility, never quality.
        require(basis in ('BEST_KNOWN_SUFFICIENT', 'SPEC_SATISFIED', 'BUDGET', 'STALLED'), 'invalid STOP basis')
        if basis in ('BEST_KNOWN_SUFFICIENT','SPEC_SATISFIED'):
            require(best is not None and best['m1_feasibility'] == 'FEASIBLE', 'STOP best must be currently M1 feasible')
            require(best['evidence_id'] in raw['evidence_ids'] or raw.get('stop_basis') is None,
                    'STOP must cite current best Evidence ID')
            if basis == 'BEST_KNOWN_SUFFICIENT':
                require(quality_state(best,config['quality_target'])['status'] == 'REACHED',
                        'quality STOP requires actual best-known margin to meet quality_target; use SPEC_SATISFIED for M1-only STOP')
            if config.get('mode') == 'FEEDBACK_REOPTIMIZATION_ACCEPTANCE':
                require(sum(optimization_executed(r) for r in state['history']) >= 2,
                        'acceptance mode needs an actual feedback optimization before quality STOP')
        elif basis == 'BUDGET':
            require(state['budget']['remaining_M1_calls'] < 3 or
                    state['budget']['remaining_LLM_calls_including_this'] <= 1,
                    'budget STOP requires actual limited remaining budget')
        else:
            require(state['stalled_rounds'] >= config.get('stall_round_limit', 2), 'stall STOP requires measured stalled rounds')
    if not stop:
        require(raw['region_origin'] == 'LLM_PROPOSED', 'region_origin must be LLM_PROPOSED')
        require(type(raw['m1_budget']) is int and 2 <= raw['m1_budget'] <= state['budget']['max_this_decision_M1_calls'],
                'm1_budget exceeds current round/session limit or is too small')
        require(isinstance(raw['seed_ids'], list) and all(isinstance(s, str) and s in state['valid_seed_ids'] for s in raw['seed_ids']),
                'seed must be an exposed current-spec legal M1 point')
        require(bool(raw['seed_ids']) or raw['m1_budget'] >= 3, 'seedless region requires probe plus final recheck budget')
        active = raw['active_variables']
        require(isinstance(active, list) and bool(active) and all(isinstance(k, str) and k in FREE_IDS for k in active)
                and len(set(active)) == len(active), 'invalid Active Variables')
        # A structurally legal small budget is not an invalid LLM decision.
        # The numerical scheduler reports SKIPPED_BUDGET if useful work cannot start.
    bounds = raw.get('normalized_bounds', {k: [0., 1.] for k in FREE_IDS})
    d = {'schema_version': SCHEMA, 'decision_id': f'LLM8B:R{round_number:02d}', 'context_sha256': explorer.context['context_sha256'],
        'action': 'STOP' if stop else 'OPTIMIZE',
        'region': {'region_id': f'LLM_PROPOSED:R{round_number:02d}', 'parent_region_id': None},
        'normalized_bounds': deepcopy(bounds), 'active_variables': [] if stop else deepcopy(raw['active_variables']),
        'seed_ids': [] if stop else deepcopy(raw['seed_ids']), 'm1_budget': 0 if stop else raw['m1_budget'],
        'objective': OBJECTIVE, 'reason': raw['reason'], 'evidence_ids': raw['evidence_ids'],
        'random_seed': config['seed']+round_number-1, 'search_method': 'NONE' if stop else 'SLSQP',
        'settings': {} if stop else deepcopy(config['slsqp'])}
    if not stop and not d['seed_ids']:
        # Validator checks the exact box and budget before any Probe. Six-axis
        # seeding explores only the LLM box; subset fixed values await a real seed.
        probe = deepcopy(d)
        probe.update(action='PROBE', search_method='SOBOL', active_variables=list(FREE_IDS),
                     settings={'sample_count': config['seed_probe_samples']})
        explorer.validate(probe)
    else:
        try:
            explorer.validate(d)
        except ValueError as error:
            if 'seed outside decision region' not in str(error):
                raise
            details = []
            for sid in d['seed_ids']:
                point = normalized_point(explorer.problem, explorer.evidence[sid]['parameters'])
                violations = {k: {'seed_normalized_coordinate': point[k], 'proposed_bounds': pair}
                              for k, pair in bounds.items() if not pair[0] <= point[k] <= pair[1]}
                if violations:
                    details.append({'seed_id': sid, 'violations': violations})
            raise DecisionValidationError(str(error)+'; seed_boundary_violations='+json.dumps(details, separators=(',', ':')),
                 {'code': 'SEED_OUTSIDE_REGION', 'seed_boundary_violations': details}) from None
    if not stop:
        local = deepcopy(explorer.problem)
        for k, pair in d['normalized_bounds'].items():
            axis = local['parameters'][k]
            lo, hi = [physical_coordinate(explorer.problem['parameters'][k], u) for u in pair]
            require(lo < hi, k+': region collapses in floating representation')
            axis.update(min=lo, max=hi)
        certificate = screen_problem(local)['certificates']
        require(not certificate, 'region has strict necessary-condition contradiction: '+str(certificate))
    return d
