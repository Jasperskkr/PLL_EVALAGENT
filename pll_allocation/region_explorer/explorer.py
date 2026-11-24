"""Decision-controlled continuous search using the existing formal M1 only."""
from copy import deepcopy
import csv
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import sys
import time

from ..allocation.core import write_new
from ..block_space.contracts import FREE_IDS
from ..exploration import load_physics_context
from ..exploration.contracts import check_candidate, coordinate, judge, make_parameters, require
from ..physics_mapping.model import evaluate, fingerprint
from .assessment import assess_regions, contains_parameters, normalized_point, physical_coordinate
from .contracts import decision_signature, validate_decision


class BudgetExhausted(RuntimeError):
    pass


class SearchTargetReached(RuntimeError):
    """An optional controller stop predicate was met by recorded evidence."""


def sources():
    package = Path(__file__).resolve().parents[1]
    paths = [package/'pipeline.py']
    for folder in ('region_explorer', 'exploration', 'physics_mapping', 'allocation', 'block_space'):
        paths.extend(sorted((package/folder).glob('*.py')))
    return {p.relative_to(package.parent).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def margin_vector(problem, row):
    """Each supported bound remains a separate constraint; no BW-only objective."""
    checks = row['judgment']['constraints']
    if row['M1_status'] != 'OK' or row['judgment']['minimum_normalized_margin'] is None:
        return None
    return [c['bound_margins'][bound]/c['normalization_scale'] for c in checks
            if c['enabled'] and c['support_status'] == 'M1_SUPPORTED'
            for bound in ('min', 'max') if bound in c]


def slsqp_cost_model(active_dimensions, *, seed_cached=True):
    """Conservative opportunity estimate, never a convergence guarantee.

    Budget two updates after the initial finite-difference stencil. A new base,
    d differences and one line-search point can be needed for each update.
    Every actual call still passes through the hard session/action limits.
    """
    initial = 0 if seed_cached else 1
    iteration = active_dimensions+2
    work = initial+active_dimensions+2*iteration
    return {'initial_evaluation_cost': initial, 'finite_difference_cost': active_dimensions,
            'estimated_iteration_cost': iteration, 'target_update_opportunities': 2,
            'minimum_work_budget': work, 'final_recheck_reserve': 1,
            'minimum_action_budget': work+1,
            'estimate_scope': 'Opportunity estimate only; line searches/failures can consume more.'}


class RegionExplorer:
    """One serialized, append-only session with a single hard formal-M1 budget.

    Cache keys use complete candidate fingerprints without coordinate rounding.
    Decisions and proposals are persisted before execution. A final SLSQP recheck
    bypasses the cache and is charged to both action and session budgets.
    """

    def __init__(self, context_path, out, *, m1_budget, reserved_final_calls=0, budget_scheduling=False, stop_when=None):
        require(type(m1_budget) is int and m1_budget > 0, 'positive session M1 budget required')
        require(type(reserved_final_calls) is int and 0 <= reserved_final_calls < m1_budget, 'invalid final call reserve')
        self.reserved_final_calls = reserved_final_calls
        self.budget_scheduling = budget_scheduling
        self.stop_when = stop_when
        self.conditional_physics = None
        self.context_path = Path(context_path).resolve()
        self.context = load_physics_context(self.context_path)
        self.problem = deepcopy(self.context['problem'])
        require(fingerprint({k: v for k, v in self.problem.items() if k != 'problem_sha256'}) ==
                self.problem['problem_sha256'], 'resolved problem hash mismatch')
        self.original_problem_hash = fingerprint(self.problem)
        self.original_context_hash = fingerprint(self.context)
        self.source_manifest = sources()
        self.calibration_samples = [json.loads(s) for s in (self.context_path.parent/'m1_samples.jsonl').read_text(encoding='utf-8').splitlines()]
        require([s['evidence_id'] for s in self.calibration_samples] == self.context['evidence_ids'] and
                len(set(self.context['evidence_ids'])) == len(self.calibration_samples), 'M1 exploration evidence index mismatch')
        self.evidence = {s['evidence_id']: deepcopy(s) for s in self.calibration_samples}
        self.assessment = assess_regions(self.context, self.calibration_samples)
        self.evidence.update({r['assessment_id']: r for r in self.assessment['regions']})
        self.regions = {r['region_id']: deepcopy(r['normalized_bounds']) for r in self.context['candidate_regions']}
        self.cache = {}
        for row in self.calibration_samples:
            require(row['problem_sha256'] == self.problem['problem_sha256'] and
                    row['model_fingerprint'] == self.context['model']['model_sha256'] and
                    row['parameter_sha256'] == fingerprint(row['parameters']), 'M1 exploration sample binding mismatch')
            if row['M1_status'] == 'OK' and not row.get('duplicate_of'):
                self.cache[fingerprint(row['parameters'])] = deepcopy(row)
        self.root = Path(out).resolve()
        self.root.mkdir(parents=True, exist_ok=False)
        self.limit = m1_budget
        self.started, self.cpu = time.perf_counter(), time.process_time()
        self.counts = {k: 0 for k in ('M1_calls', 'M1_failures', 'requests', 'cache_hits', 'inherited_cache_hits',
                                      'screen_rejections', 'budget_blocked_requests', 'coordinate_endpoint_corrections')}
        self.rows, self.observations = [], []
        self.seen_ids, self.seen_signatures = set(), set()
        self.last_region, self.stopped, self.closed = None, False, False
        self.metadata = {'context_sha256': self.context['context_sha256'],
            'problem_schema_version': self.problem['schema_version'], 'problem_sha256': self.problem['problem_sha256'],
            'model_fingerprint': self.context['model']['model_sha256'], 'source_fingerprint': fingerprint(self.source_manifest),
            'scope': 'STAGE8A_FIXED_ALGORITHM_M1_ONLY', 'LLM_calls': 0, 'M2_calls': 0}
        for name in ('run_events.jsonl', 'search_decisions.jsonl', 'm1_samples.jsonl', 'region_observations.jsonl'):
            (self.root/name).touch(exist_ok=False)
        write_new(self.root/'source_manifest.json', self.source_manifest)
        write_new(self.root/'region_assessment.json', {**self.metadata, **self.assessment})
        write_new(self.root/'problem_resolved.json', {**self.metadata, 'problem': self.problem})
        write_new(self.root/'run_manifest.json', {**self.metadata, 'session_m1_budget': self.limit,
            'stage7_context_path': str(self.context_path), 'stage7_evidence_artifacts': self.context['evidence_artifacts'],
            'environment': {'python': sys.version, 'platform': platform.platform(),
                **{k: importlib.metadata.version(k) for k in ('numpy', 'scipy')}},
            'source_manifest': 'source_manifest.json', 'candidate_origin': 'EXPLICIT_FIXED_ALGORITHM_DECISIONS',
            'status': 'STARTED; result.json is terminal state'})
        self._event('SESSION_STARTED', remaining_m1_budget=self.limit)

    def cost(self):
        extra = ({'conditional_prediction_calls': self.conditional_physics.prediction_calls}
                 if self.conditional_physics is not None else {})
        return {**self.counts, **extra, 'M1_limit': self.limit, 'remaining_M1_calls': self.limit-self.counts['M1_calls'],
                'reserved_recommendation_M1_calls': self.reserved_final_calls,
                'search_available_M1_calls': max(0, self.limit-self.counts['M1_calls']-self.reserved_final_calls),
                'LLM_calls': 0, 'M2_calls': 0, 'analytic_calls': 0, 'monetary_cost': None}

    def planner_state(self):
        """Serializable input for a future planner, with no authority to modify it."""
        return deepcopy({**self.metadata, 'schema_version': 'pll-region-planner-state-1.0',
            'physics_context': self.context, 'region_assessment': self.assessment,
            'observations': self.observations, 'known_regions': self.regions,
            'available_evidence_ids': list(self.evidence), 'remaining_m1_budget': self.limit-self.counts['M1_calls'],
            'stopped': self.stopped, 'decision_schema': 'pll-search-decision-1.0',
            'execution_boundary': 'Planner proposes JSON only; executor independently validates and judges every candidate.'})

    def _append(self, name, obj):
        with (self.root/name).open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(obj, ensure_ascii=False, allow_nan=False) + '\n')

    @property
    def stage7_samples(self):
        """Compatibility view; use calibration_samples."""
        return self.calibration_samples

    def _event(self, event, **data):
        self._append('run_events.jsonl', {**self.metadata, 'event': event, **data, 'cost': self.cost()})

    def _check_frozen(self):
        require(fingerprint(self.problem) == self.original_problem_hash and
                fingerprint(self.context) == self.original_context_hash, 'session problem/context mutated')
        require(sources() == self.source_manifest, 'source mutated during session')
        require(load_physics_context(self.context_path) == self.context, 'M1 exploration evidence mutated during session')

    def validate(self, decision):
        require(not self.closed, 'session closed')
        self._check_frozen()
        return validate_decision(decision, context=self.context, evidence=self.evidence, regions=self.regions,
            remaining_budget=self.limit-self.counts['M1_calls']-self.reserved_final_calls, seen_ids=self.seen_ids,
            seen_signatures=self.seen_signatures, last_region=self.last_region, stopped=self.stopped)

    def _record(self, row):
        if self.conditional_physics is not None:
            row.update(self.conditional_physics.describe(row['parameters']))
            if 'conditional_noise_status' in row:
                row['joint_conditional_feasibility'] = ('CONDITIONAL_FEASIBLE' if
                    row['judgment']['m1_feasibility'] == 'FEASIBLE' and self.conditional_physics.qualified(row)
                    else 'NOT_ESTABLISHED')
        self.rows.append(row)
        self.evidence[row['evidence_id']] = row
        self._append('m1_samples.jsonl', row)
        self._event('M1_OBSERVATION', evidence_id=row['evidence_id'], decision_id=row['decision_id'],
                    M1_status=row['M1_status'], judgment=row['judgment'], reason=row.get('reason'))
        return row

    def _sample(self, candidate, decision, origin, *, force=False, reserve=0):
        self.counts['requests'] += 1
        key = fingerprint(candidate)
        row = {**self.metadata, 'evidence_id': f'A8S{len(self.rows)+1:07d}',
            'decision_id': decision['decision_id'], 'origin': origin, 'parameters': deepcopy(candidate),
            'parameter_sha256': key, 'formal_M1_result': None, 'formal_M1_called': False,
            'independent_final_recheck': force}
        self._event('CANDIDATE_PROPOSED', **{k: row[k] for k in ('evidence_id', 'decision_id', 'origin', 'parameters', 'parameter_sha256')})
        screening = check_candidate(self.problem, candidate)
        row['screening'] = screening
        result = None
        evaluation_timing = None
        start, cpu = time.perf_counter(), time.process_time()
        if not contains_parameters(self.problem, decision['normalized_bounds'], candidate):
            # Never silently clip solver requests to a region or enlarge its bounds.
            row.update(M1_status='NOT_EVALUATED_OUTSIDE_DECISION_REGION', reason='candidate outside SearchDecision region')
            self.counts['screen_rejections'] += 1
        elif screening['status'] != 'NECESSARY_CONDITIONS_SATISFIED':
            self.counts['screen_rejections'] += 1
            row.update(M1_status='NOT_EVALUATED_SCREEN_REJECTED', reason=screening['reason'])
        elif key in self.cache and not force:
            original = self.cache[key]
            self.counts['cache_hits'] += 1
            inherited = not original['evidence_id'].startswith('A8S')
            self.counts['inherited_cache_hits'] += int(inherited)
            row.update(M1_status=original['M1_status'], reason=original.get('reason'),
                       duplicate_of=original['evidence_id'], cache_source='STAGE7' if inherited else 'SESSION',
                       metrics=deepcopy(original['metrics']), judgment=deepcopy(original['judgment']))
        elif (self.counts['M1_calls'] >= self.limit-self.reserved_final_calls or
              self.counts['M1_calls']-self.action_start_calls >= decision['m1_budget']-reserve):
            self.counts['budget_blocked_requests'] += 1
            row.update(M1_status='NOT_EVALUATED_BUDGET_EXHAUSTED', reason='action/session formal M1 budget exhausted')
        else:
            self.counts['M1_calls'] += 1  # Charge before calling, including exceptions and failures.
            row['formal_M1_called'] = True
            evaluation_started = time.perf_counter()
            try:
                result = evaluate(candidate)
                row.update(formal_M1_result=result.as_dict(), M1_status=result.status.value, reason=result.reason)
                if result.status.value != 'OK':
                    self.counts['M1_failures'] += 1
            except Exception as error:
                self.counts['M1_failures'] += 1
                row.update(M1_status='EVALUATOR_EXCEPTION', reason=f'{type(error).__name__}: {error}')
            finally:
                evaluation_timing = {'perf_counter_started': evaluation_started,
                    'perf_counter_finished': time.perf_counter(),
                    'wall_time_s': time.perf_counter()-evaluation_started}
        if 'judgment' not in row:
            row.update(metrics=result.metrics if result else {}, judgment=judge(self.problem, candidate, result))
        row['cost'] = {**self.cost(), 'wall_time_s': time.perf_counter()-start,
                       'process_cpu_s': time.process_time()-cpu}
        if evaluation_timing is not None:
            row['cost']['evaluation_timing'] = evaluation_timing
        self._record(row)
        if row['formal_M1_called']:
            self.cache[key] = row
        if row['M1_status'] == 'NOT_EVALUATED_BUDGET_EXHAUSTED':
            raise BudgetExhausted(row['reason'])
        if row['formal_M1_called'] and self.stop_when is not None and self.stop_when(row):
            raise SearchTargetReached('controller target reached by '+row['evidence_id'])
        return row

    def _decode(self, decision, base, active, coordinates):
        updates = {k: base['values'][k]['value'] for k in FREE_IDS}
        for k, u in zip(active, coordinates):
            require(decision['normalized_bounds'][k][0] <= float(u) <= decision['normalized_bounds'][k][1],
                    'solver coordinate outside decision bounds')
            axis = self.problem['parameters'][k]
            raw = coordinate(axis, float(u), inverse=True)
            updates[k] = physical_coordinate(axis, float(u))
            if raw != updates[k]:
                self.counts['coordinate_endpoint_corrections'] += 1
                self._event('COORDINATE_ENDPOINT_ROUNDING_REPAIRED', decision_id=decision['decision_id'],
                            axis=k, normalized_coordinate=float(u), raw_value=raw, corrected_value=updates[k])
        return make_parameters(self.problem, updates)

    def _probe(self, decision):
        from scipy.stats import qmc
        n = decision['settings']['sample_count']
        active = decision['active_variables']
        base = (self.evidence[decision['seed_ids'][0]]['parameters'] if decision['seed_ids'] else make_parameters(self.problem))
        draws = qmc.Sobol(d=len(active), scramble=True, seed=decision['random_seed']).random_base2((n-1).bit_length())
        completed = 0
        for i, draw in enumerate(draws[:n]):
            u = [decision['normalized_bounds'][k][0] + float(x)*(decision['normalized_bounds'][k][1]-decision['normalized_bounds'][k][0])
                 for k, x in zip(active, draw)]
            try:
                self._sample(self._decode(decision, base, active, u), decision, f'LOCAL_SOBOL:{i+1:06d}')
            except BudgetExhausted as error:
                return [{'solver': 'SOBOL', 'status': 'BUDGET_EXHAUSTED', 'message': str(error),
                         'requested_samples': n, 'completed_samples': completed,
                         'budget_blocked_index': i+1, 'unattempted_samples': n-i-1}]
            completed += 1
        return [{'solver': 'SOBOL', 'status': 'COMPLETED', 'requested_samples': n, 'completed_samples': completed}]

    def _optimize(self, decision):
        import numpy as np
        from scipy.optimize import minimize
        active = decision['active_variables']
        bounds = [tuple(decision['normalized_bounds'][k]) for k in active]
        constraint_count = sum(sum(b in s for b in ('min', 'max')) for s in self.problem['specs']
                               if s['enabled'] and s['support_status'] == 'M1_SUPPORTED')
        supported_constraint_count = constraint_count
        noise_active = (self.conditional_physics is not None and
                        self.conditional_physics.options['noise_allocation_enabled'] and
                        self.conditional_physics.limit is not None)
        def optimization_margins(row):
            margins = margin_vector(self.problem, row)
            if margins is not None and self.conditional_physics is not None:
                margins += self.conditional_physics.extra_margin(row)
            return margins
        if self.conditional_physics is not None:
            constraint_count += len(self.conditional_physics.extra_margin(self.evidence[decision['seed_ids'][0]]))
        runs = []
        # The default regional executor path keeps its existing start order/behavior.
        # Agent opt-in schedules one useful start at a time; early convergence
        # can free the residual budget for another diverse, high-quality seed.
        pending = list(decision['seed_ids'])
        planned, selected_points = [], []
        if self.budget_scheduling:
            scores = [self.evidence[s]['judgment']['minimum_normalized_margin'] for s in pending]
            low, high = min(scores), max(scores)
            def priority(sid):
                row = self.evidence[sid]
                point = normalized_point(self.problem, row['parameters'])
                quality = (row['judgment']['minimum_normalized_margin']-low)/(high-low) if high>low else 0.
                distance = min((sum((point[k]-p[k])**2 for k in FREE_IDS)/len(FREE_IDS))**.5
                               for p in selected_points) if selected_points else 0.
                return (row['judgment']['m1_feasibility'] != 'FEASIBLE',
                        -(quality+.25*distance), decision['seed_ids'].index(sid))
        while pending:
            sid = min(pending,key=priority) if self.budget_scheduling else pending[0]
            pending.remove(sid)
            model = slsqp_cost_model(len(active), seed_cached=fingerprint(self.evidence[sid]['parameters']) in self.cache)
            remaining = min(decision['m1_budget']-(self.counts['M1_calls']-self.action_start_calls),
                            self.limit-self.reserved_final_calls-self.counts['M1_calls'])
            if self.budget_scheduling and remaining < model['minimum_action_budget']:
                runs.append({'solver': 'scipy.optimize.SLSQP', 'seed_id': sid, 'status': 'SKIPPED_BUDGET',
                    'started': False, 'success': False, 'iterations': 0, 'M1_calls': 0,
                    'allocated_M1_budget': 0, 'cost_model': model,
                    'remaining_action_M1_calls': remaining,
                    'remaining_session_search_M1_calls':self.cost()['search_available_M1_calls'],
                    'message': 'insufficient budget for initial stencil, two update opportunities and action final recheck'})
                continue
            planned.append(sid)
            selected_points.append(normalized_point(self.problem,self.evidence[sid]['parameters']))
            allocated = max(0, remaining-1)
            count_before = self.counts['M1_calls']
            sample_index = len(self.rows)
            iterates = []
            def callback(u):
                iterates.append({'iteration': len(iterates)+1,
                    'normalized_active': {k: float(v) for k,v in zip(active,u)},
                    'M1_calls_since_start': self.counts['M1_calls']-count_before})
            base = self.evidence[sid]['parameters']
            initial = normalized_point(self.problem, base)
            record = {'solver': 'scipy.optimize.SLSQP', 'seed_id': sid,
                      'started': True, 'allocated_M1_budget': allocated, 'cost_model': model,
                      'start_priority_rule':'feasibility first, normalized margin + 0.25 * normalized parameter distance; original index tie-break'
                          if self.budget_scheduling else 'legacy supplied seed order',
                      'estimated_initial_difference_calls': len(active)+1,
                      'coordinates': active, 'bounds': dict(zip(active, bounds)), 'fixed_values': {
                          k: base['values'][k]['value'] for k in FREE_IDS if k not in active}}
            if self.conditional_physics is not None:
                record['conditional_noise_constraint'] = {'enabled': self.conditional_physics.options['noise_allocation_enabled'],
                    'jitter_limit_s': self.conditional_physics.limit,
                    'strategy': 'Existing maximin SLSQP plus normalized hard jitter margin; formal M1 bounds retained'}
            requests_before = self.counts['requests']

            def trial(u):
                if self.counts['requests']-requests_before >= max(256, decision['m1_budget']*30):
                    raise RuntimeError('SOLVER_REQUEST_LIMIT: bounded screening/cache-only iterations')
                candidate = self._decode(decision, base, active, u[:len(active)])
                row = self._sample(candidate, decision, f'SLSQP:{sid}:TRIAL', reserve=1)
                margins = optimization_margins(row)
                return np.array(margins if margins else [-1e6]*constraint_count)

            def constraints(u):
                margins = trial(u)
                # Conditional maximin can improve an infeasible jitter gap, but
                # may never buy that improvement by crossing supported M1 bounds.
                # Once noise is feasible, u[-1]>=0 also preserves that tier.
                return np.r_[margins-u[-1], margins[:supported_constraint_count]] if noise_active else margins-u[-1]

            start = [initial[k] for k in active]
            m0 = min(optimization_margins(self.evidence[sid]))
            try:
                solution = minimize(lambda u: -u[-1], np.array(start + [m0-.001]), method='SLSQP',
                    bounds=bounds + [(0. if noise_active and m0 >= 0 else -1e6, 1e6)],
                    constraints=[{'type': 'ineq', 'fun': constraints}],
                    callback=callback,
                    options={'maxiter': decision['settings']['maxiter'], 'ftol': 1e-8,
                             'eps': decision['settings']['finite_difference_step']})
                endpoint = self._sample(self._decode(decision, base, active, solution.x[:len(active)]),
                                        decision, f'SLSQP:{sid}:ENDPOINT', reserve=1)
                record.update(status='CONVERGED' if solution.success else 'NOT_CONVERGED',
                    success=bool(solution.success), status_code=int(solution.status), message=str(solution.message),
                    iterations=int(solution.nit), endpoint_evidence_id=endpoint['evidence_id'],
                    endpoint_margin=endpoint['judgment']['minimum_normalized_margin'])
            except SearchTargetReached as error:
                record.update(status='CONTROLLER_TARGET_REACHED', success=False, message=str(error))
            except BudgetExhausted as error:
                record.update(status='BUDGET_EXHAUSTED', success=False, message=str(error))
            except Exception as error:
                record.update(status='SOLVER_EXCEPTION', success=False, message=f'{type(error).__name__}: {error}')
            record['M1_calls'] = self.counts['M1_calls']-count_before
            record.setdefault('iterations', len(iterates))
            intermediate = [r for r in self.rows[sample_index:] if margin_vector(self.problem,r)]
            best = max(intermediate,key=lambda r:r['judgment']['minimum_normalized_margin'],default=None)
            record.update(iteration_trace=iterates, callback_iterations=len(iterates),
                best_intermediate_evidence_id=best['evidence_id'] if best else None,
                best_intermediate_margin=best['judgment']['minimum_normalized_margin'] if best else None,
                remaining_action_M1_calls=decision['m1_budget']-(self.counts['M1_calls']-self.action_start_calls),
                remaining_session_search_M1_calls=self.cost()['search_available_M1_calls'])
            runs.append(record)
            if record['status'] == 'CONTROLLER_TARGET_REACHED':
                break
            if record['status'] == 'BUDGET_EXHAUSTED' and not self.budget_scheduling:
                break
        return runs

    def recheck_recommendation(self, candidate):
        """One explicit audit call using the same charged evaluator, even after STOP.

        This is not a search or a replacement for an accepted LLM region. Its full
        original-domain envelope and exact source candidate are saved separately.
        """
        require(not self.closed, 'session closed')
        if self.reserved_final_calls < 1:
            return {'status': 'NO_RESERVED_BUDGET', 'passed': False, 'evidence_id': None}
        self._check_frozen()
        self.reserved_final_calls -= 1
        d = {'decision_id': 'RECOMMENDATION:FINAL_RECHECK', 'm1_budget': 1,
             'normalized_bounds': {k: [0., 1.] for k in FREE_IDS}}
        self._append('recommendation_rechecks.jsonl', {'purpose': 'FINAL_RECOMMENDATION_RECHECK_NOT_SEARCH',
                     'source_evidence_id': candidate['evidence_id'], 'decision': d, 'parameters': candidate['parameters']})
        self.action_start_calls = self.counts['M1_calls']
        try:
            row = self._sample(candidate['parameters'], d, 'RECOMMENDATION:FINAL_RECHECK', force=True)
            equal = row['metrics'] == candidate['metrics'] and row['judgment'] == candidate['judgment']
            return {'status': row['M1_status'] if equal else 'RECHECK_CHANGED_OR_FAILED',
                    'passed': row['judgment']['m1_feasibility'] == 'FEASIBLE' and equal,
                    'evidence_id': row['evidence_id'], 'source_evidence_id': candidate['evidence_id'],
                    'metrics_equal_to_source': row['metrics'] == candidate['metrics'], 'row': deepcopy(row)}
        except BudgetExhausted as error:
            return {'status': 'BUDGET_EXHAUSTED', 'passed': False, 'evidence_id': None, 'reason': str(error)}

    def execute(self, raw, *, candidate_stream=None, tool_name=None):
        """Optional bounded tool proposals share the original screening/cache/M1.

        The explicit stream adapter is for exploration tools only; normal
        regional executor/Agent calls retain their existing sampling and SLSQP semantics.
        """
        if candidate_stream is not None:
            require(tool_name in ('ANALYTICAL_INVERSE', 'PHYSICS_GUIDED_SEEDS', 'LOCAL_SENSITIVITY', 'FEEDBACK_SEED_FRESH_M1', 'LOCAL_CONNECTIVITY'),
                    'unsupported external proposal tool')
            require(raw.get('action') == 'PROBE' and raw.get('search_method') == 'SOBOL',
                    'proposal tools require a bounded PROBE envelope')
        else:
            require(tool_name is None, 'tool_name requires actual candidate stream')
        try:
            d = self.validate(raw)
        except (ValueError, TypeError, KeyError) as error:
            try:
                json.dumps(raw, allow_nan=False)
                rejected = raw
            except (ValueError, TypeError):
                rejected = {'invalid_decision_repr': repr(raw)}
            self._event('DECISION_REJECTED', decision=rejected, reason=str(error))
            raise ValueError(str(error)) from error
        self.seen_ids.add(d['decision_id'])
        self.seen_signatures.add(decision_signature(d))
        self._append('search_decisions.jsonl', {**self.metadata, 'candidate_origin': 'EXPLICIT_FIXED_ALGORITHM_DECISION', 'decision': d})
        self._event('DECISION_ACCEPTED', decision=d)
        self.regions[d['region']['region_id']] = deepcopy(d['normalized_bounds'])
        before, index = deepcopy(self.counts), len(self.rows)
        self.action_start_calls = self.counts['M1_calls']
        start, cpu = time.perf_counter(), time.process_time()
        seeds = [self.evidence[s] for s in d['seed_ids']]
        original_margin = max((r['judgment']['minimum_normalized_margin'] for r in seeds
                               if r['judgment']['minimum_normalized_margin'] is not None), default=None)
        solver_runs, failure, final = [], None, None
        if d['action'] == 'STOP':
            self.stopped = True
        else:
            try:
                if candidate_stream is not None:
                    completed = 0
                    for candidate in candidate_stream:
                        require(completed < d['settings']['sample_count'], 'tool proposal count exceeds declared limit')
                        self._sample(candidate, d, tool_name+f':{completed+1:06d}')
                        completed += 1
                    solver_runs = [{'solver': tool_name, 'status': 'COMPLETED', 'completed_samples': completed}]
                else:
                    solver_runs = self._probe(d) if d['search_method'] == 'SOBOL' else self._optimize(d)
            except SearchTargetReached as error:
                solver_runs = [{'solver': tool_name or d['search_method'], 'status': 'CONTROLLER_TARGET_REACHED',
                                'message': str(error)}]
            except BudgetExhausted as error:
                solver_runs = [{'solver': d['search_method'], 'status': 'BUDGET_EXHAUSTED', 'message': str(error)}]
            except Exception as error:
                failure = {'type': type(error).__name__, 'reason': str(error)}
            candidates = [r for r in seeds+self.rows[index:] if margin_vector(self.problem, r)]
            if candidates and d['search_method'] == 'SLSQP' and not any(r.get('status') == 'CONTROLLER_TARGET_REACHED' for r in solver_runs):
                best = max(candidates, key=lambda r: r['judgment']['minimum_normalized_margin'])
                try:
                    final = self._sample(best['parameters'], d, 'SLSQP:INDEPENDENT_FINAL_RECHECK', force=True)
                except BudgetExhausted as error:
                    failure = {'type': type(error).__name__, 'reason': 'final recheck: '+str(error)}
        self._check_frozen()
        new = self.rows[index:]
        usable = [r for r in seeds+new if margin_vector(self.problem, r)]
        best = max(usable, key=lambda r: r['judgment']['minimum_normalized_margin'], default=None)
        positive = [r['evidence_id'] for r in new if r['formal_M1_called'] and r['judgment']['m1_feasibility'] == 'FEASIBLE']
        negative = [r['evidence_id'] for r in new if r['formal_M1_called'] and r['judgment']['m1_feasibility'] == 'INFEASIBLE']
        status = ('STOPPED' if self.stopped else 'ACTION_ERROR' if failure else
                  'M1_FEASIBLE_OBSERVED' if any(r['judgment']['m1_feasibility'] == 'FEASIBLE' for r in seeds+new)
                  else 'NO_M1_FEASIBLE_OBSERVED')
        observation = {**self.metadata, 'schema_version': 'pll-region-observation-1.0',
            'observation_id': f'RA8O{len(self.observations)+1:05d}', 'decision_id': d['decision_id'],
            'action': d['action'], 'region': d['region'], 'normalized_bounds': d['normalized_bounds'],
            'physical_bounds': {k: {'min': physical_coordinate(self.problem['parameters'][k], lo),
                'max': physical_coordinate(self.problem['parameters'][k], hi), 'unit': self.problem['parameters'][k]['unit']}
                for k, (lo, hi) in d['normalized_bounds'].items()},
            'active_variables': d['active_variables'], 'seed_ids': d['seed_ids'], 'status': status,
            'fixed_values_by_seed': {sid: {k: self.evidence[sid]['parameters']['values'][k]['value'] for k in FREE_IDS
                                         if k not in d['active_variables']} for sid in d['seed_ids']},
            'original_minimum_normalized_margin': original_margin,
            'latest_minimum_normalized_margin': best['judgment']['minimum_normalized_margin'] if best else None,
            'best_evidence_id': best['evidence_id'] if best else None,
            'best_candidate': ({k: deepcopy(best[k]) for k in ('evidence_id', 'origin', 'parameters', 'metrics', 'judgment')}
                               if best else None),
            'new_candidate_summaries': [{k: deepcopy(r.get(k)) for k in ('evidence_id', 'origin', 'parameter_sha256',
                'M1_status', 'formal_M1_called', 'duplicate_of')} | {
                'minimum_normalized_margin': r['judgment']['minimum_normalized_margin'],
                'm1_feasibility': r['judgment']['m1_feasibility']} for r in new],
            'candidate_evidence_artifact': 'm1_samples.jsonl',
            'final_recheck_evidence_id': final['evidence_id'] if final else None,
            'final_recheck_status': final['M1_status'] if final else 'NOT_REQUESTED_OR_NO_VALID_CANDIDATE',
            'new_positive_evidence_ids': positive, 'new_negative_evidence_ids': negative,
            'new_unique_candidate_ids': [r['evidence_id'] for r in new if r['formal_M1_called'] and not r['independent_final_recheck']],
            'evidence_ids': [r['evidence_id'] for r in new],
            'failures_and_unknowns': [{'evidence_id': r['evidence_id'], 'status': r['M1_status'], 'reason': r.get('reason'),
                'screening': r['screening']} for r in new if r['M1_status'] != 'OK'],
            'solver_runs': solver_runs, 'failure': failure,
            'budget_exhausted': any(r['M1_status'] == 'NOT_EVALUATED_BUDGET_EXHAUSTED' for r in new),
            'cost': {**{k: self.counts[k]-before[k] for k in before}, 'allocated_M1_budget': d['m1_budget'],
                'wall_time_s': time.perf_counter()-start, 'process_cpu_s': time.process_time()-cpu,
                'LLM_calls': 0, 'M2_calls': 0},
            'whole_region_M1_certified': False, 'FULL_SYSTEMSPEC_CERTIFIED': False, 'M2_status': 'NOT_EVALUATED'}
        self.observations.append(observation)
        self.evidence[observation['observation_id']] = observation
        self.last_region = d['region']['region_id']
        self._append('region_observations.jsonl', observation)
        self._event('ACTION_COMPLETED', observation=observation)
        return deepcopy(observation)

    def close(self, *, failure=None):
        require(not self.closed, 'session already closed')
        self._check_frozen()
        cost = {**self.cost(), 'wall_time_s': time.perf_counter()-self.started, 'process_cpu_s': time.process_time()-self.cpu,
                'timing_scope': 'session setup/execution; excludes input load and final export'}
        scientific = {'decisions': sorted(self.seen_ids), 'observations': [
            {k: v for k, v in o.items() if k != 'cost'} for o in self.observations], 'samples': [
            {k: v for k, v in r.items() if k != 'cost'} for r in self.rows]}
        action_errors = [o['failure'] for o in self.observations if o['failure']]
        if action_errors and failure is None:
            failure = {'type': 'ActionErrors', 'reasons': action_errors}
        result = {**self.metadata, 'schema_version': 'pll-region-run-1.0', 'status': 'PIPELINE_ERROR' if failure else 'COMPLETED',
            'strategy': 'stage8a_fixed_region_explorer', 'cost': cost, 'failure': failure,
            'action_count': len(self.observations), 'scientific_sha256': fingerprint(scientific),
            'FULL_SYSTEMSPEC_CERTIFIED': False, 'M2_status': 'NOT_EVALUATED'}
        write_new(self.root/'region_observations.json', {**self.metadata, 'observations': self.observations})
        write_new(self.root/'planner_state.json', self.planner_state())
        write_new(self.root/'cost_summary.json', {**self.metadata, **cost})
        with (self.root/'m1_samples.csv').open('x', encoding='utf-8-sig', newline='') as stream:
            fields = ['evidence_id', 'decision_id', 'origin', *FREE_IDS, 'M1_status', 'm1_feasibility',
                      'minimum_normalized_margin', 'formal_M1_called', 'duplicate_of', 'reason', 'BW_Hz', 'PM_deg',
                      'constraints_json', 'problem_sha256', 'model_fingerprint', 'context_sha256', 'source_fingerprint']
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for r in self.rows:
                writer.writerow({**{k: r.get(k) for k in fields if k in r},
                    **{k: r['parameters']['values'][k]['value'] for k in FREE_IDS},
                    **{k: r['judgment'][k] for k in ('m1_feasibility', 'minimum_normalized_margin')},
                    **{k: r['metrics'].get(k) for k in ('BW_Hz', 'PM_deg')},
                    'constraints_json': json.dumps(r['judgment']['constraints'])})
        self._event('SESSION_COMPLETED', result=result)
        write_new(self.root/'result.json', result)
        lines = ['# regional executor Region Exploration Report', '',
                 f'Status: {result["status"]}; actions: {len(self.observations)}.',
                 f'Context: `{self.context["context_sha256"]}`.',
                 f'Model: `{self.metadata["model_fingerprint"]}`.',
                 f'M1 calls: {cost["M1_calls"]}/{self.limit}; cache hits: {cost["cache_hits"]}; '
                 f'formal failures: {cost["M1_failures"]}. M2=0; LLM=0.', '',
                 'Each region is a search suggestion; no entire region or full SystemSpec is certified.',
                 'Solver convergence and pointwise M1 feasibility are reported separately.', '',
                 '|Decision|Method/action|Initial margin|Best observed margin|Final recheck|Solver state|',
                 '|---|---|---:|---:|---|---|']
        for o in self.observations:
            lines.append(f'|{o["decision_id"]}|{o["action"]}|{o["original_minimum_normalized_margin"]}|'
                         f'{o["latest_minimum_normalized_margin"]}|{o["final_recheck_status"]}|'
                         f'{", ".join(r["status"] for r in o["solver_runs"])}|')
        lines.extend(['', 'Full inputs/results/reasons are in m1_samples.jsonl. Cache rows reference the original evidence ID.',
                      'planner_state.json includes M1 exploration PhysicsContext, assessment, observations and remaining budget.',
                      'These are explicit fixed-algorithm decisions, not LLM decisions or M2 verification.',
                      '', f'Failure: {failure}', ''])
        with (self.root/'region_exploration_report.md').open('x', encoding='utf-8') as stream:
            stream.write('\n'.join(lines))
        (self.root/'stage8a_report.md').write_bytes((self.root/'region_exploration_report.md').read_bytes())
        write_new(self.root/'output_manifest.json', {**self.metadata, 'artifacts': {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(self.root.iterdir()) if p.is_file()}})
        self.closed = True
        return result


def run_region_exploration(context_path, decisions_path, out, *, m1_budget):
    """CLI/GUI/tool shared batch interface; reads saved M1 exploration, never resamples it."""
    raw = json.loads(Path(decisions_path).read_text(encoding='utf-8-sig'))
    require(isinstance(raw, list), 'decisions file must be a JSON list')
    explorer = RegionExplorer(context_path, out, m1_budget=m1_budget)
    write_new(explorer.root/'decisions_input.json', raw)
    failure = None
    try:
        for decision in raw:
            explorer.execute(decision)
    except Exception as error:
        failure = {'type': type(error).__name__, 'reason': str(error)}
    return explorer.close(failure=failure)
