"""Physics-tool policy adapter for the existing AgentSearchLoop orchestrator."""
from copy import deepcopy
import json
from pathlib import Path

from ..allocation.core import Meter, write_new
from ..exploration import load_physics_context
from ..exploration.contracts import load_problem, require
from ..exploration.physics_region_builder import around_seed, build_physics_region
from ..physics_mapping.model import fingerprint
from .search_loop import AgentSearchLoop
from .subregion_context import was_formal_call
from .subregion_loop import prepare_initial
from .subregion_tools import envelope, execute_tool
from .physics_tool_policy import adapt, build_state, make_policy, validate_config, validate_feedback


class PhysicsToolSearchLoop(AgentSearchLoop):
    """Adds physical construction to the original executor/archive/finalization.

    This class owns strategy-to-tool translation only. It inherits the one
    original runner's provider handling, bounded repairs, run states, candidate
    ranking, recommendation recheck and handoff creation.
    """
    def __init__(self, context_path, out, *, config, provider_config=None, policy=None, feedback=None, policy_injected=None):
        cfg = validate_config(config)
        self.injected_policy = policy is not None if policy_injected is None else policy_injected
        context = load_physics_context(context_path)
        cold = cfg.get('bootstrap') == 'COLD'
        require(context.get('exploration_source') == ('EMPTY_BOOTSTRAP_NO_SEARCH' if cold else 'SMALL_INITIAL_SOBOL_ONLY'),
                'cold mode requires matching empty bootstrap provenance' if cold else 'integrated mode requires small initial calibration')
        samples = [json.loads(s) for s in (Path(context_path).parent/'m1_samples.jsonl').read_text(encoding='utf-8').splitlines()]
        if cold:
            require(not samples and context['evidence_ids'] == [] and context['summary']['formal_M1_calls'] == 0,
                    'cold bootstrap must contain no imported evidence or calls')
        self.initial_calls = sum(was_formal_call(s) for s in samples)
        require(self.initial_calls <= cfg['initial_m1_budget'] and len(samples) <= cfg['initial_sobol_samples'] and
                all(s['origin'].startswith('LOCAL_SOBOL:') for s in samples), 'small Sobol initial contract exceeded')
        self.external_feedback = validate_feedback(feedback, context['problem'], context['model']['model_sha256'])
        self.reverification_request = None
        self.integrated_config = cfg
        self.tool_regions, self.tool_evidence_ids = {}, set()
        self.tool_signatures, self.build_request_ids = set(), set()
        self.sensitivity_actions, self.feedback_seed_rechecks = {}, []
        self.construction_attempts, self.constructions, self.compact_history = 0, [], []
        old_config = {'schema_version': 'pll-llm-region-loop-1.1', 'max_decisions': cfg['max_decisions'],
            'max_llm_calls': cfg['max_llm_calls'], 'validation_retries': cfg['validation_retries'],
            'min_decisions_before_quality_stop': cfg['max_decisions'],
            'total_m1_budget': cfg['total_m1_budget']-self.initial_calls,
            'max_round_m1': min(cfg['max_round_m1'], cfg['total_m1_budget']-self.initial_calls),
            'calibration_budget': 0, 'quality_target': 1e100, 'seed': cfg['seed'],
            'seed_probe_budget': 1, 'seed_probe_samples': 1, 'slsqp': cfg['slsqp']}
        super().__init__(context_path, out, config=old_config, provider_config=provider_config or {},
                         policy=policy if policy is not None else make_policy(cfg, provider_config))
        options = cfg.get('candidate_pool', {}).get('physics_options')
        if options:
            from ..exploration.conditional_physics import ConditionalPhysics
            self.explorer.conditional_physics = ConditionalPhysics(self.explorer.problem, options)
        write_new(self.root/'initial_allocation_config.json', cfg)
        write_new(self.root/'external_feedback.json', self.external_feedback)
        # Caller-supplied measurements never become PASS by import. Persist the
        # input first, then freshly evaluate optional exact seeds via our one
        # executor, under its remaining search budget and final-call reserve.
        feedback_seeds = [o for o in (self.external_feedback or {}).get('observations', []) if 'parameters' in o]
        require(len(feedback_seeds) <= self.explorer.cost()['search_available_M1_calls'],
                'feedback seed rechecks exceed available M1 budget')
        for i, item in enumerate(feedback_seeds):
            box = around_seed(self.explorer.problem, item['parameters'], 'BALANCED')
            rid = 'FEEDBACK:'+str(i+1)
            d = envelope(self.explorer, decision_id=rid+':FRESH_M1', region_id=rid, bounds=box,
                budget=1, seed=cfg['seed']+i, proposals=1)
            first = len(self.explorer.rows)
            o = self.explorer.execute(d, candidate_stream=iter([item['parameters']]), tool_name='FEEDBACK_SEED_FRESH_M1')
            rows = self.explorer.rows[first:]
            formal = [r for r in rows if r['M1_status'] == 'OK' and r['formal_M1_called']]
            references = formal + [self.explorer.evidence[r['duplicate_of']] for r in rows if r.get('duplicate_of')
                and self.explorer.evidence[r['duplicate_of']]['M1_status'] == 'OK']
            self.tool_regions[rid] = {'strategy':'CALLER_FEEDBACK_FRESH_M1', 'normalized_bounds':box,
                'formal_seed_ids':[r['evidence_id'] for r in references], 'construction_seed_id':item['evidence_id']}
            self.feedback_seed_rechecks.append({'source_external_evidence_id':item['evidence_id'],
                'observation_id':o['observation_id'], 'formal_evidence_ids':[r['evidence_id'] for r in references],
                'M1_calls':o['cost']['M1_calls'], 'status':'FRESH_FORMAL_M1' if formal else
                    'CURRENT_CONTEXT_CACHE_REVALIDATED' if references else 'NO_VALID_FORMAL_SEED'})
        self.archive.sync()
        write_new(self.root/'tool_run_manifest.json', {'schema_version': 'pll-initial-allocation-run-1.0',
            'policy': cfg['policy'], 'initial_M1_calls': self.initial_calls,
            'formal_session_cap_including_initial': cfg['total_m1_budget'],
            'context_sha256': context['context_sha256'], 'problem_sha256': context['problem']['problem_sha256'],
            'model_fingerprint': context['model']['model_sha256'],
            'source_scope': 'Existing AgentSearchLoop/RegionExplorer/CandidateArchive; explicit physical strategy policy adapter',
            'policy_scope': 'TEST_POLICY' if self.injected_policy else cfg.get('candidate_pool', {}).get('mode', cfg['policy']),
            'external_feedback_scope': 'OPTIONAL_CALLER_SUPPLIED_NOT_M2_VERIFICATION', 'M2_status': 'NOT_EVALUATED'})

    def _build_state(self, round_number, correction):
        return build_state(self, round_number, correction)

    def _adapt(self, raw, state, round_number):
        return adapt(raw, self, state, round_number)

    def _decision_provenance(self):
        return {'region_origin': 'TOOL_COMPUTED_AFTER_JOINT_GLOBAL_INVERSE',
                'strategy_proposer': 'TEST_POLICY' if self.injected_policy else 'REAL_LLM' if self.real_policy else 'DETERMINISTIC',
                'numeric_seed_and_box_proposer': 'PHYSICS_REGION_BUILDER'}

    def _seed_allowed(self, seed):
        return True

    def _execute(self, decision):
        if decision.get('decision_id') in self.sensitivity_actions:
            o = execute_tool(self.explorer, decision_id=decision['decision_id'], region=decision['region'] |
                {'normalized_bounds':decision['normalized_bounds']},
                tool={'method':'LOCAL_SENSITIVITY','seed_id':self.sensitivity_actions[decision['decision_id']],
                      'm1_budget':decision['m1_budget']}, seed=decision['random_seed'],
                config={'max_tool_proposals':12}, meter=Meter(cheap_limit=0,m1_limit=0))
            actual = json.loads((self.explorer.root/'search_decisions.jsonl').read_text(encoding='utf-8').splitlines()[-1])['decision']
            self._remember(decision, [o], None)
            return [actual], [o], 'EXECUTED'
        if decision['action'] == 'PROBE':
            # Sobol already supplies complete points; SLSQP's seed probe would
            # spend a second budget and reject a legal one/two-call probe.
            o = self.explorer.execute(decision)
            self._remember(decision, [o], None)
            return [decision], [o], 'EXECUTED'
        if decision['action'] != 'BUILD_PHYSICS_REGION':
            executed, observations, outcome = super()._execute(decision)
            self._remember(decision, observations, None)
            return executed, observations, outcome
        request = decision['request']; self.build_request_ids.add(request['request_id'])
        folder = self.root/'physics_tools'/request['request_id'].replace(':', '_')
        folder.mkdir(parents=True, exist_ok=False)
        write_new(folder/'request.json', request)
        proposal = build_physics_region(self.explorer.problem, request,
            model_fingerprint=self.explorer.context['model']['model_sha256'],
            random_seed=self.config['seed']+len(self.constructions),
            history=[r['parameters'] for r in self.archive.entries],
            excluded={r['parameter_sha256'] for r in self.archive.entries},
            physics_options=self.integrated_config.get('candidate_pool', {}).get('physics_options'),
            minimum_distance=self.integrated_config.get('candidate_pool', {}).get('minimum_distance', 0.))
        # Construction artifact is persisted BEFORE any formal evaluation.
        write_new(folder/'proposal_before_M1.json', proposal)
        self.construction_attempts += proposal['cost']['construction_attempts']
        require(self.construction_attempts <= self.integrated_config['construction_attempt_budget'], 'construction session hard limit exceeded')
        self.constructions.append(proposal)
        observations, executed, links = [], [], []
        for i, seed in enumerate(proposal['seeds']):
            if self._search_target_reached():
                break
            if not self._seed_allowed(seed):
                links.append({'construction_seed_id': seed['seed_id'], 'M1_status': 'SKIPPED_NEAR_DUPLICATE',
                              'formal_evidence_ids': [], 'reason': 'pool normalized-distance filter; no M1 called'})
                continue
            remaining = request['budget']['m1_calls']-sum(o['cost']['M1_calls'] for o in observations)
            if remaining < 1:
                break
            d = envelope(self.explorer, decision_id=request['request_id']+':M1:'+str(i+1), region_id=seed['region_id'],
                bounds=seed['normalized_bounds'], budget=1, seed=self.config['seed']+i, proposals=1)
            first = len(self.explorer.rows)
            o = self.explorer.execute(d, candidate_stream=iter([seed['parameters']]), tool_name='PHYSICS_GUIDED_SEEDS')
            rows = self.explorer.rows[first:]
            formal = [r for r in rows if r['M1_status'] == 'OK']
            self.tool_regions[seed['region_id']] = {'strategy': request['strategy'], 'normalized_bounds': seed['normalized_bounds'],
                'formal_seed_ids': [r['evidence_id'] for r in formal], 'construction_seed_id': seed['seed_id']}
            self.tool_evidence_ids.add(seed['seed_id'])
            self.explorer.evidence[seed['seed_id']] = deepcopy(seed)
            links.append({'construction_seed_id': seed['seed_id'], 'region_id': seed['region_id'],
                          'formal_evidence_ids': [r['evidence_id'] for r in rows],
                          'M1_status': rows[0]['M1_status'] if rows else 'NOT_EVALUATED',
                          'judgment': rows[0]['judgment'] if rows else None})
            executed.append(d); observations.append(o)
        write_new(folder/'M1_observation_links.json', links)
        self.archive.sync()
        self._remember(decision, observations, proposal)
        return executed, observations, proposal['status']

    def _remember(self, decision, observations, proposal):
        entry = {'action': decision['action'], 'reason': decision['reason'],
            'construction_status': proposal['status'] if proposal else None,
            'construction_evidence': proposal['strategy_id'] if proposal else None,
            'construction_cost': proposal['cost'] if proposal else None,
            'failure_reasons': (proposal['failure_reasons'][:8] if proposal else []),
            'observations': [{'observation_id': o['observation_id'], 'region_id': o['region']['region_id'],
                'M1_calls': o['cost']['M1_calls'], 'positive_ids': o['new_positive_evidence_ids'],
                'negative_ids': o['new_negative_evidence_ids'], 'best': o['best_candidate'],
                'solver_runs': o['solver_runs'], 'failure': o['failure']} for o in observations]}
        if proposal and 'objective_selection' in proposal:
            entry['objective_selection'] = deepcopy(proposal['objective_selection'])
        self.compact_history.append(entry)
        with (self.root/'SEARCH_DECISION_TRACE.jsonl').open('a', encoding='utf-8') as f:
            f.write(json.dumps({'decision': decision, 'actual': entry}, ensure_ascii=False, allow_nan=False)+'\n')

    def cost(self):
        cost = super().cost()
        cost.update(M1_calls=self.initial_calls+self.explorer.counts['M1_calls'],
            M1_limit=self.integrated_config['total_m1_budget'], initial_shared_M1_calls=self.initial_calls,
            incremental_M1_calls=self.explorer.counts['M1_calls'], construction_attempts=self.construction_attempts,
            construction_failures=sum(c['cost']['construction_failures'] for c in self.constructions),
            inverse_calls=sum(c['cost']['inverse_calls'] for c in self.constructions),
            construction_wall_s=sum(c['cost']['wall_time_s'] for c in self.constructions))
        cost['feedback_seed_recheck_M1_calls'] = sum(o['M1_calls'] for o in self.feedback_seed_rechecks)
        if self.explorer.conditional_physics is not None:
            cost['conditional_prediction_calls'] = self.explorer.conditional_physics.prediction_calls
            cost['conditional_noise_trial_integrations'] = sum(
                c.get('conditional_search', {}).get('noise_integrations', 0) for c in self.constructions)
        return cost

    def _result_fields(self):
        write_new(self.root/'REGION_CONSTRUCTION_RESULTS.json', {'proposals': self.constructions,
            'attempt_limit': self.integrated_config['construction_attempt_budget'], 'actual_attempts': self.construction_attempts,
            'tool_regions': self.tool_regions, 'M1_authority': 'Only executor/m1_samples.jsonl; proposals are not evaluated claims'})
        return {'strategy': self.integrated_config['policy'], 'region_origin': 'TOOL_CONSTRUCTED_AFTER_JOINT_GLOBAL_INVERSE',
                'execution_route': 'CONTINUOUS_SINGLE_ALLOCATION',
                'actual_policy_execution': 'TEST_POLICY' if self.injected_policy else
                    'REAL_LLM_EXECUTED' if self.cost()['LLM_calls'] else
                    'DETERMINISTIC_ONLY' if not self.real_policy else 'LLM_BRANCH_NO_REAL_CALL',
                'm2_reverification_request': deepcopy(self.reverification_request),
                'constructed_seed_count': sum(len(c['seeds']) for c in self.constructions),
                'construction_attempts': self.construction_attempts,
                'initial_M1_calls': self.initial_calls, 'M2_status': 'NOT_EVALUATED'}


def run_initial_allocation(problem_config, out, *, config, provider_config=None, initial_context=None,
                           feedback=None, policy=None):
    """verification feedback-ready initial-search function; never invokes an M2 evaluator."""
    cfg = validate_config(config); problem = load_problem(problem_config)
    policy_injected = policy is not None
    path = initial_context
    if path is None and cfg.get('bootstrap') == 'COLD':
        from .subregion_context import export_context
        root = Path(out); require(not root.exists(), 'output directory already exists')
        path = export_context(problem, [], root.with_name(root.name+'_empty_context'),
                              cost={'M1_calls': 0}, scope='EMPTY_BOOTSTRAP_NO_SEARCH')
    if path is None:
        # Same existing small-calibration tool; no new global engine.
        root = Path(out); require(not root.exists(), 'output directory already exists')
        calibration = root.with_name(root.name+'_calibration')
        pilot = {'schema_version': 'pll-subregion-pilot-1.0', 'strategy': 'DETERMINISTIC_PHYSICS_STAGE7',
            'seed': cfg['seed'], 'total_m1_budget': cfg['total_m1_budget'], 'initial_m1_budget': cfg['initial_m1_budget'],
            'initial_sobol_samples': cfg['initial_sobol_samples'], 'global_m1_budget': 1, 'global_sobol_samples': 1,
            'max_decisions': 1, 'round_m1_budget': 1, 'validation_retries': 0, 'max_llm_calls': 1,
            'max_tool_proposals': 12, 'analytic_call_limit': 1, 'region_radius': problem['exploration']['region_radius']}
        path = prepare_initial(problem_config, calibration, pilot)
    require(load_physics_context(path)['problem'] == problem, 'current problem differs from initial calibration')
    loop_type = PhysicsToolSearchLoop
    if 'candidate_pool' in cfg:
        from .pool_search import PoolSearchLoop
        loop_type = PoolSearchLoop
    elif (feedback and policy is None and cfg['policy'] == 'DETERMINISTIC_PHYSICS_TOOL'
          and feedback.get('observations') and feedback['observations'][0]['measurements'].get('schema_version') == 'pll-m2-feedback-summary-1.0'):
        from .deterministic_feedback import DeterministicFeedbackPolicy
        policy = DeterministicFeedbackPolicy()
    loop = loop_type(path, out, config=cfg, provider_config=provider_config, policy=policy, feedback=feedback,
                     policy_injected=policy_injected)
    return loop.run()
