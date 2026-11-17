"""Bounded policy loop; the regional executor owns all numerical execution."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time

from ..allocation.core import write_new
from ..block_space.contracts import FREE_IDS
from ..exploration.contracts import active_m1_specs, number, require, screen_problem
from ..physics_mapping.model import fingerprint
from ..region_explorer import RegionExplorer
from .calibration import prepare_context
from .decision_adapter import adapt_decision
from .planner_state import build_state, knowledge, sensitivity
from .region_policy import InvalidResponse, LLMRegionPolicy, ProviderError
from .candidates import CandidateArchive, material_change, rank
from .run_state import run_state, optimization_executed, quality_state


def validate_config(raw):
    fields = {'schema_version', 'max_decisions', 'max_llm_calls', 'validation_retries', 'min_decisions_before_quality_stop',
              'total_m1_budget', 'max_round_m1', 'calibration_budget', 'quality_target', 'seed',
              'seed_probe_budget', 'seed_probe_samples', 'slsqp'}
    optional = {'mode', 'improvement_abs', 'improvement_rel', 'stall_round_limit'}
    require(isinstance(raw, dict) and fields <= set(raw) <= fields|optional and
            raw['schema_version'] in ('pll-llm-region-loop-1.0', 'pll-llm-region-loop-1.1'),
            'complete versioned loop configuration required')
    cfg = deepcopy(raw)
    cfg.setdefault('mode', 'INITIAL_ALLOCATION')
    cfg.setdefault('improvement_abs', 1e-6)
    cfg.setdefault('improvement_rel', 1e-6)
    cfg.setdefault('stall_round_limit', 2)
    require(cfg['mode'] in ('INITIAL_ALLOCATION', 'FEEDBACK_REOPTIMIZATION_ACCEPTANCE'), 'invalid run mode')
    require(type(cfg['stall_round_limit']) is int and cfg['stall_round_limit'] > 0, 'positive stall limit required')
    for k in ('improvement_abs', 'improvement_rel'):
        require(number(cfg[k], k) >= 0, 'nonnegative improvement threshold required')
    for k in fields-{'schema_version', 'slsqp', 'quality_target'}:
        require(type(cfg[k]) is int and cfg[k] >= 0, k+': nonnegative integer required')
    require(1 <= cfg['max_decisions'] <= 10 and cfg['max_decisions'] <= cfg['max_llm_calls'] <= 20, 'bounded decision/call budgets required')
    require(cfg['validation_retries'] <= 3 and 1 <= cfg['min_decisions_before_quality_stop'] <= cfg['max_decisions'],
            'invalid repair/minimum decision settings')
    require(2 <= cfg['max_round_m1'] <= cfg['total_m1_budget'] and cfg['calibration_budget'] < cfg['total_m1_budget']-1,
            'invalid total/round/calibration M1 budgets')
    require(1 <= cfg['seed_probe_budget'] <= cfg['max_round_m1']-2 and
            1 <= cfg['seed_probe_samples'] <= 128, 'bounded seed probe settings required')
    require(cfg['seed']+cfg['max_decisions'] < 2**32, 'bounded uint32 seed required')
    number(cfg['quality_target'], 'quality_target')
    s = cfg['slsqp']
    require(isinstance(s, dict) and set(s) == {'maxiter', 'finite_difference_step'} and
            type(s['maxiter']) is int and 1 <= s['maxiter'] <= 200 and
            0 < number(s['finite_difference_step'], 'finite difference step') <= .01, 'invalid SLSQP settings')
    return cfg


def source_manifest():
    root = Path(__file__).resolve().parents[2]
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [*sorted((root/'pll_allocation/agent').glob('*.py')),
                      *sorted((root/'pll_allocation/region_explorer').glob('*.py')),
                      root/'pll_allocation/llm_transport.py', root/'pll_allocation/pipeline.py',
                      *sorted((root/'pll_allocation/exploration').glob('physics_region*.py')),
                      root/'configs/model/equations.json']}


class AgentSearchLoop:
    def __init__(self, context_path, out, *, config, provider_config, problem_path=None, policy=None):
        self.config = validate_config(config)
        self.root = Path(out).resolve()
        self.root.mkdir(parents=True, exist_ok=False)
        self.start, self.cpu = time.perf_counter(), time.process_time()
        self.sources = source_manifest()
        write_new(self.root/'source_manifest.json', self.sources)
        write_new(self.root/'loop_config.json', self.config)
        self.trace = self.root/'run_events.jsonl'
        self.trace.touch(exist_ok=False)
        resolved_context, self.calibration = prepare_context(context_path, problem_path, self.root/'calibration_current',
                                                             calibration_budget=self.config['calibration_budget'])
        self.explorer = RegionExplorer(resolved_context, self.root/'executor',
            m1_budget=self.config['total_m1_budget']-self.calibration['new_M1_calls'],
            reserved_final_calls=1, budget_scheduling=True)
        self.archive = CandidateArchive(self.explorer, self.root/'candidate_archive.jsonl')
        self.explorer.candidate_archive = self.archive
        self.policy = policy if policy is not None else LLMRegionPolicy(provider_config)
        self.real_policy = isinstance(self.policy, LLMRegionPolicy)
        self.history, self.proposals = [], set()
        self.calls = 0
        self.status, self.failure = 'NOT_STARTED', None
        self.reused_best = self.archive.best('STAGE7_CALIBRATION')
        for item in knowledge(self.explorer.context)+sensitivity(self.explorer.context):
            self.explorer.evidence[item['evidence_id']] = item
        write_new(self.root/'run_manifest.json', {'schema_version': 'pll-llm-region-run-1.0',
            'scope': 'REAL_LLM_REGION_PILOT' if self.real_policy else 'TEST_POLICY_NOT_REAL_LLM',
            'source_context_path': str(Path(context_path).resolve()), 'effective_context_path': str(resolved_context),
            'problem_sha256': self.explorer.problem['problem_sha256'],
            'context_sha256': self.explorer.context['context_sha256'],
            'calibration': self.calibration, 'new_global_sampling_on_unchanged_problem': False,
            'source_fingerprint': fingerprint(self.sources), 'M2_status': 'NOT_EVALUATED',
            'initial_calibration_best': self.reused_best['evidence_id'] if self.reused_best else None})
        self.emit('RUN_STARTED', calibration=self.calibration)

    @staticmethod
    def _best(rows):
        return min((r for r in rows if r['M1_status'] == 'OK' and r['judgment']['minimum_normalized_margin'] is not None),
                   key=rank, default=None)

    def emit(self, event, **data):
        with self.trace.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({'event': event, **data}, ensure_ascii=False, allow_nan=False)+'\n')

    def cost(self):
        calls = getattr(self.policy, 'calls', [])
        return {'M1_calls': self.calibration['new_M1_calls']+self.explorer.cost()['M1_calls'],
            'M1_limit': self.config['total_m1_budget'], 'calibration': self.calibration,
            'executor': self.explorer.cost(), 'LLM_attempts': self.calls,
            'LLM_calls': sum(c.get('real_network_call', False) for c in calls) if self.real_policy else 0,
            'test_policy_calls': self.calls if not self.real_policy else 0,
            'reported_usage': [c.get('usage') for c in calls],
            'LLM_elapsed_s': sum(c.get('elapsed_s', 0) for c in calls),
            'wall_time_s': time.perf_counter()-self.start, 'process_cpu_s': time.process_time()-self.cpu,
            'M2_calls': 0, 'monetary_cost': None}

    def _execute(self, decision):
        d = deepcopy(decision)
        executed, observations = [], []
        if d['action'] == 'STOP':
            obs = self.explorer.execute(d)
            return [d], [obs], 'LLM_STOP'
        if not d['seed_ids']:
            probe = deepcopy(d)
            probe.update(decision_id=d['decision_id']+':SEED_PROBE', action='PROBE', search_method='SOBOL',
                active_variables=list(FREE_IDS), m1_budget=min(self.config['seed_probe_budget'],
                                                              d['m1_budget']-2),
                settings={'sample_count': self.config['seed_probe_samples']},
                reason='Bounded numerical seeding strictly inside the LLM-proposed box. '+d['reason'])
            first = len(self.explorer.rows)
            obs = self.explorer.execute(probe)
            executed.append(probe)
            observations.append(obs)
            legal = [r for r in self.explorer.rows[first:] if r['M1_status'] == 'OK' and
                     r['judgment']['minimum_normalized_margin'] is not None]
            if not legal:
                return executed, observations, 'NO_EVALUABLE_SEED_IN_LLM_REGION'
            seed = self._best(legal)
            d['seed_ids'] = [seed['evidence_id']]
            d['m1_budget'] -= obs['cost']['M1_calls']
            d['evidence_ids'] = list(dict.fromkeys(d['evidence_ids']+[seed['evidence_id']]))
        obs = self.explorer.execute(d)
        executed.append(d)
        observations.append(obs)
        return executed, observations, 'EXECUTED'

    def _build_state(self, round_number, correction):
        return build_state(self.explorer, self.config, self.history, round_number=round_number,
            calls_remaining=self.config['max_llm_calls']-self.calls, calibration=self.calibration, correction=correction)

    def _adapt(self, raw, state, round_number):
        return adapt_decision(raw, self.explorer, state, self.config,
            round_number=round_number, first=not self.history)

    def _result_fields(self):
        """Explicit policy extensions may add provenance without changing M1 authority."""
        return {}

    def _search_target_reached(self):
        return False

    def _decision_provenance(self):
        return {'region_origin': 'LLM_PROPOSED',
                'proposer': 'REAL_LLM' if self.real_policy else 'UNIT_TEST_POLICY'}

    def run(self):
        screen = screen_problem(self.explorer.problem)
        if screen['certificates']:
            self.status = 'PROVEN_M1_INFEASIBLE'
            self.emit('PREFLIGHT_STOP', screening=screen)
            return self.finish()
        if not active_m1_specs(self.explorer.problem):
            self.status = 'M1_CAPABILITY_INSUFFICIENT'
            self.emit('PREFLIGHT_STOP', reason='No enabled metric has a supported formal M1 mapping')
            return self.finish()
        self.status = 'DECISION_BUDGET_EXHAUSTED'
        try:
            for round_no in range(1, self.config['max_decisions']+1):
                if self._search_target_reached():
                    self.status = 'M1_POOL_TARGET_REACHED'
                    break
                if self.calls >= self.config['max_llm_calls']:
                    self.status = 'LLM_CALL_BUDGET_EXHAUSTED'
                    break
                if self.explorer.cost()['search_available_M1_calls'] < 3:
                    self.status = 'M1_SEARCH_BUDGET_EXHAUSTED'
                    break
                self.archive.sync()
                before_best = self.archive.best()
                folder = self.root/f'round_{round_no:02d}'
                folder.mkdir(exist_ok=False)
                correction, accepted, stop_basis = None, None, None
                for repair in range(self.config['validation_retries']+1):
                    if self.calls >= self.config['max_llm_calls']:
                        self.status = 'LLM_CALL_BUDGET_EXHAUSTED'
                        break
                    state = self._build_state(round_no, correction)
                    write_new(folder/f'planner_state_{repair:02d}.json', state)
                    self.calls += 1
                    self.emit('LLM_REQUEST_STARTED', round=round_no, attempt=repair, state_sha256=fingerprint(state),
                              real_policy=self.real_policy, observed_history_rounds=len(self.history))
                    try:
                        raw = self.policy.decide(deepcopy(state), folder/f'llm_call_{repair:02d}')
                        # Save injected test decisions too, always tagged in the run manifest.
                        write_new(folder/f'proposal_{repair:02d}.json', raw)
                        decision = self._adapt(raw, state, round_no)
                        signature = fingerprint({k: v for k, v in raw.items() if k not in ('reason', 'evidence_ids')})
                        require(signature not in self.proposals, 'duplicate effective LLM proposal; choose a new search or STOP')
                        self.proposals.add(signature)
                        accepted = decision
                        stop_basis = ('M2_REVERIFICATION_REQUEST' if raw.get('action')=='REVERIFY' else
                            raw.get('stop_basis','SPEC_SATISFIED')) if decision['action'] == 'STOP' else None
                        write_new(folder/'search_decision.json', {**self._decision_provenance(),
                            'decision': decision, 'stop_basis':stop_basis})
                        self.emit('LLM_DECISION_VALIDATED', round=round_no, decision=decision)
                        break
                    except (ValueError, TypeError, KeyError) as error:
                        correction = {'code': 'INVALID_LLM_DECISION', 'error_type': type(error).__name__,
                                      'message': str(error), 'attempt': repair,
                                      'details': getattr(error, 'details', None),
                                      'action': 'Repair the JSON only; no optimizer has run for this rejected proposal.'}
                        write_new(folder/f'validation_error_{repair:02d}.json', correction)
                        self.emit('LLM_DECISION_REJECTED', round=round_no, error=correction)
                if accepted is None:
                    if self.status != 'LLM_CALL_BUDGET_EXHAUSTED':
                        self.status = 'INVALID_LLM_DECISION'
                    break
                executed, observations, outcome = self._execute(accepted)
                self.archive.sync()
                after_best = self.archive.best()
                progress = material_change(before_best['judgment']['minimum_normalized_margin'] if before_best else None,
                    after_best['judgment']['minimum_normalized_margin'] if after_best else None,
                    absolute=self.config['improvement_abs'], relative=self.config['improvement_rel'])
                record = {'round': round_no, 'decision': accepted, 'execution_decisions': executed,
                          'observations': observations, 'outcome': outcome, 'progress': progress, 'stop_basis':stop_basis}
                self.history.append(record)
                write_new(folder/'region_observation.json', record)
                self.emit('LLM_ROUND_COMPLETED', round=round_no, outcome=outcome,
                          observations=[o['observation_id'] for o in observations], cost=self.cost())
                if self._search_target_reached():
                    self.status = 'M1_POOL_TARGET_REACHED'
                    break
                if outcome == 'LLM_STOP':
                    self.status = 'STOPPED_BY_LLM'
                    break
                best = self.archive.best()
                acceptance_done = (self.config['mode'] != 'FEEDBACK_REOPTIMIZATION_ACCEPTANCE' or
                                   sum(optimization_executed(r) for r in self.history) >= 2)
                if quality_state(best,self.config['quality_target'])['status'] == 'REACHED' and (
                        round_no >= self.config['min_decisions_before_quality_stop'] and acceptance_done):
                    self.status = 'M1_QUALITY_TARGET_REACHED'
                    break
        except ProviderError as error:
            self.status = 'LLM_PROVIDER_FAILED'
            self.failure = {'type': type(error).__name__, 'reason': str(error)}
            self.emit('LLM_PROVIDER_FAILED', failure=self.failure, cost=self.cost())
        except Exception as error:
            self.status = 'PIPELINE_ERROR'
            self.failure = {'type': type(error).__name__, 'reason': str(error)}
            self.emit('RUN_ERROR', failure=self.failure)
        return self.finish()

    def finish(self):
        require(source_manifest() == self.sources, 'agent source mutated during run')
        summary = self.archive.summary(absolute=self.config['improvement_abs'], relative=self.config['improvement_rel'])
        recommended = self.archive.best(feasible_only=True)
        recheck = (self.explorer.recheck_recommendation(recommended) if recommended else
                   {'status': 'NO_KNOWN_FEASIBLE_CANDIDATE', 'passed': False, 'evidence_id': None})
        self.archive.sync()
        states = run_state(self.status, self.history, self.archive, recheck)
        states['quality_target_status'] = quality_state(recommended,self.config['quality_target'],recheck)
        states['llm_stop_basis'] = next((r.get('stop_basis') for r in reversed(self.history)
                                        if r['decision']['action'] == 'STOP'),None)
        executor_result = self.explorer.close()
        best = self.archive.best()
        scope_failure = self.status in ('PROVEN_M1_INFEASIBLE', 'M1_CAPABILITY_INSUFFICIENT')
        selected = self.archive.best('STAGE8B_SEARCH', feasible_only=True)
        def candidate(row):
            return ({k: deepcopy(row[k]) for k in ('evidence_id', 'origin', 'parameters', 'metrics', 'judgment', 'parameter_sha256')}
                    if row else None)
        allocation = {'schema_version': 'pll-m1-initial-allocation-1.0', 'status': 'M1_PREDICTED_FEASIBLE_NEW_POINT' if selected else
                      'CURRENT_M1_CAPABILITY_OR_PHYSICS_STOP' if scope_failure else 'NO_NEW_M1_FEASIBLE_ALLOCATION',
            'new_allocation': candidate(selected), 'best_observed_current_spec': candidate(best),
            'recommended_nominal': deepcopy(recommended),
            'recommendation_recheck': recheck,
            'best_stage7_calibration': summary['best_calibration'],
            'best_stage8b_new': summary['best_new'],
            'improvement_over_calibration': summary['improvement_over_calibration'],
            'candidate_archive_summary': summary,
            'selection_scope': 'recommended_nominal is best current feasible point; new_allocation is legacy search-only field and may be worse.',
            'legacy_non_authoritative_fields': ['status','new_allocation','best_observed_current_spec'],
            **states,
            'source_context_sha256': self.explorer.context['context_sha256'],
            'problem_sha256': self.explorer.problem['problem_sha256'],
            'model_fingerprint': self.explorer.context['model']['model_sha256'],
            'calibration_baseline': candidate(self.reused_best), 'M2_status': 'NOT_EVALUATED',
            'FULL_SYSTEMSPEC_CERTIFIED': False, 'region_whole_domain_certified': False}
        cost = self.cost()
        write_new(self.root/'m1_allocation.json', allocation)
        result = {'schema_version': 'pll-llm-region-loop-result-1.0', 'status': self.status,
            **states,
            'strategy': 'stage8b_real_llm_region_slsqp' if self.real_policy else 'stage8b_test_policy_not_llm',
            'decision_rounds': len(self.history), 'feedback_decision_completed': len(self.history) >= 2,
            'feedback_reoptimization_completed': states['feedback_reoptimization_count'] > 0,
            'new_M1_feasible_allocation': selected is not None,
            'region_origin': 'LLM_PROPOSED' if self.real_policy else 'UNIT_TEST_POLICY',
            'cost': cost, 'failure': self.failure, 'executor_result': executor_result,
            'FULL_SYSTEMSPEC_CERTIFIED': False, 'M2_status': 'NOT_EVALUATED'}
        result.update(self._result_fields())
        write_new(self.root/'cost_summary.json', cost)
        from .handoff import build_handoff
        handoff = build_handoff(self.explorer, self.archive, recommended, recheck, states, cost)
        write_new(self.root/'stage9_handoff.json',handoff)
        write_new(self.root/'verification_handoff.json',handoff)
        self.emit('RUN_COMPLETED', result=result)
        write_new(self.root/'result.json', result)
        write_new(self.root/'output_manifest.json', {p.relative_to(self.root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(self.root.rglob('*')) if p.is_file()})
        return result


def run_agent_search(context_path, out, *, config, provider_config, problem_path=None):
    return AgentSearchLoop(context_path, out, config=config, provider_config=provider_config, problem_path=problem_path).run()
