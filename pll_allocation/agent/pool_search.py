"""Multi-candidate policy adapter; the original Runner/Builder/M1 do the work."""
from copy import deepcopy

from ..allocation.core import write_new
from ..exploration.physics_region_builder import around_seed
from ..physics_mapping.model import fingerprint
from .candidate_pool import distance, distinct_candidates
from .deterministic_feedback import DeterministicFeedbackPolicy
from .initial_allocation import PhysicsToolSearchLoop
from .physics_tool_policy import SCHEMA_VERSION, DeterministicToolPolicy, prompt_for_options
from .region_policy import LLMRegionPolicy, ProviderError
from .subregion_tools import envelope


class PoolDeterministicPolicy(DeterministicToolPolicy):
    """Inverse first; V2 feedback rules; diversify before bounded local search."""
    def decide(self, state, directory):
        cfg = state['candidate_pool']['config']
        replenishing = any(o['measurements'].get('search_purpose') == 'REPLENISH_JOINT_POOL'
                           for o in (state['external_feedback'] or {}).get('observations', []))
        if state['budget']['max_build_attempts'] == 0:
            return {'schema_version': SCHEMA_VERSION, 'state_sha256': state['state_sha256'],
                'evidence_ids': ['REL:shape'], 'action': 'STOP', 'stop_basis': 'BUDGET',
                'reason': 'The charged physical construction attempt budget is exhausted.'}
        if ((state['external_feedback'] or {}).get('observations') and not state['history'] and
                state['external_feedback']['observations'][0]['measurements'].get('schema_version') == 'pll-m2-feedback-summary-1.0' and
                state['external_feedback']['observations'][0]['measurements']['supported_metrics_status'] != 'PASS'):
            return DeterministicFeedbackPolicy().decide(state, directory)
        regions = [r for r in state['available_tool_regions'] if r['formal_M1_seed_ids']]
        # When feasible points miss the quality gate, use the existing maximin
        # optimizer; it cannot improve dynamic capture or certify M2.
        if (not replenishing and regions and state['candidate_pool']['feasible_count'] and not state['candidate_pool']['quality_count']
                and not any(h['action'] == 'OPTIMIZE' for h in state['history'])):
            return super().decide(state, directory)
        common = {'schema_version': SCHEMA_VERSION, 'state_sha256': state['state_sha256'],
                  'evidence_ids': ['REL:shape', 'REL:inverse_gain'],
                  'reason': 'Construct distinct joint inverse seeds; formal M1 and the pool quality gate own acceptance.'}
        strategies = ('HIGH_PM_LF_SHAPE', 'GAIN_SPLIT_EXPLORATION', 'VCO_TUNING_EXPLORATION', 'DIVERSITY_EXPLORATION')
        index = len(state['history'])
        if replenishing:
            index += 3  # Successful points need diverse alternatives, not failure correction.
        count = min(8, max(1, cfg['target_count']-state['candidate_pool']['quality_count']),
                    state['budget']['max_this_decision_M1_calls'])
        fraction = (.5, .5) if index < 2 else ((.25, .75) if index % 2 else (.1, .9))
        return common | {'action': 'BUILD_PHYSICS_REGION', 'request': {
            'schema_version': 'pll-physics-region-request-1.0', 'request_id': 'POOL:'+str(state['round']),
            'problem_sha256': state['problem']['problem_sha256'], 'model_fingerprint': state['model']['model_sha256'],
            'strategy': strategies[index % len(strategies)], 'target_bw_fraction': list(fraction),
            'physics_focus': ['LF_SHAPE', 'GAIN_SPLIT', 'TUNING', 'DIVERSITY'],
            'tuning_preference': 'INTERIOR' if index == 0 else 'DIVERSE', 'seed_count': count,
            'region_width_policy': 'BALANCED', 'budget': {
                'construction_attempts': state['budget']['max_build_attempts'], 'm1_calls': count},
            'evidence_ids': common['evidence_ids']}}


class PoolLLMPolicy(LLMRegionPolicy):
    """Original physics prompt/transport with explicit paid-call authorization."""
    def __init__(self, provider_config, config, offline_policy=None):
        super().__init__(provider_config or {}, prompt=prompt_for_options(config.get('physics_options')) + '''
The candidate_pool field specifies K, quality and diversity requirements. A single
feasible point is insufficient. Continue tool construction/search until the pool
target is reached, or explain a real budget/stall. All M2 verdicts remain external.''')
        self.pool_config = config
        self.deterministic = PoolDeterministicPolicy()
        self.branch_history = []
        self.offline_policy = offline_policy
        self.offline_calls = 0

    def decide(self, state, directory):
        cfg = self.pool_config
        prior_searches = any(s.get('search_purpose') != 'REPLENISH_JOINT_POOL'
                             for o in (state['external_feedback'] or {}).get('observations', [])
                             for s in o['measurements'].get('previous_searches', []))
        if cfg['mode'] == 'AUTO_HYBRID' and state['round'] <= cfg['deterministic_rounds'] and not prior_searches:
            self.branch_history.append('DETERMINISTIC')
            return self.deterministic.decide(state, directory)
        self.branch_history.append('LLM_PHYSICS_GUIDED')
        if self.offline_policy is not None:
            if self.offline_calls >= cfg['llm_call_limit']:
                raise ProviderError('OFFLINE_POLICY_CALL_BUDGET_EXHAUSTED')
            self.offline_calls += 1
            return self.offline_policy.decide(state, directory)
        if not cfg['allow_paid_llm']:
            raise ProviderError('REAL_LLM_NOT_AUTHORIZED: LLM branch reached; no network call executed')
        if sum(bool(c.get('real_network_call')) for c in self.calls) >= cfg['llm_call_limit']:
            raise ProviderError('REAL_LLM_CALL_BUDGET_EXHAUSTED: no network call executed')
        return super().decide(state, directory)


class PoolSearchLoop(PhysicsToolSearchLoop):
    """Adds pool stopping and V2 on-demand Sobol to the existing runner.

    Cold bootstrap initialization is shared with PhysicsToolSearchLoop. No
    alternate M1, optimizer, physical formulas or behavioral verdicts exist here.
    """
    def __init__(self, context_path, out, *, config, provider_config=None, policy=None, feedback=None, policy_injected=None):
        self.pool_config = config['candidate_pool']
        self.injected_policy = policy is not None if policy_injected is None else policy_injected
        self.on_demand_calibration = None
        if self.pool_config['mode'] != 'DETERMINISTIC':
            if isinstance(policy, LLMRegionPolicy):
                raise ValueError('Inject offline decision interfaces only; real provider must use the authorization gate')
            policy = PoolLLMPolicy(provider_config, self.pool_config, offline_policy=policy)
        elif policy is None:
            policy = PoolDeterministicPolicy()
        super().__init__(context_path, out, config=config, provider_config=provider_config, policy=policy, feedback=feedback,
                         policy_injected=self.injected_policy)
        self.explorer.stop_when = lambda row: self._search_target_reached()

    def _pool(self, quality_only=False, *, conditional_only=False):
        self.archive.sync()
        rows = self.archive.entries
        if quality_only:
            excluded = set(self.pool_config.get('excluded_hashes', []))
            excluded |= {o['candidate_sha256'] for o in (self.external_feedback or {}).get('observations', [])}
            passed = [r for o in (self.external_feedback or {}).get('observations', [])
                      for r in o['measurements'].get('joint_pass_candidates', [])]
            # All tool outputs (including SLSQP/Sobol) must count only useful
            # new points; filtering just inverse seeds can stop repair early.
            rows = [r for r in rows if r['parameter_sha256'] not in excluded and
                    all(distance(self.explorer.problem, r, old) >= self.pool_config['minimum_distance'] for old in passed)]
        if conditional_only and getattr(self.explorer, 'conditional_physics', None) is not None:
            rows = [r for r in rows if self.explorer.conditional_physics.qualified(r)]
        return distinct_candidates(rows, self.explorer.problem, self.pool_config, quality_only=quality_only)

    def _search_target_reached(self):
        # Imported feedback seeds alone must not stop a reallocation. They have
        # already measured M2; demand a distinct useful new search point.
        rows = self._pool(True, conditional_only=True)
        return len(rows) >= self.pool_config['target_count']

    def _seed_allowed(self, seed):
        self.archive.sync()
        if seed['parameter_sha256'] in self.pool_config.get('excluded_hashes', []):
            return False
        passed = [r for o in (self.external_feedback or {}).get('observations', [])
                  for r in o['measurements'].get('joint_pass_candidates', [])]
        if any(distance(self.explorer.problem, seed, old) < self.pool_config['minimum_distance'] for old in passed):
            return False
        # Keep failed M1 neighborhoods searchable; only feasible near-duplicates
        # can be redundant. Quality selection itself remains post-M1.
        return all(distance(self.explorer.problem, seed, old) >= self.pool_config['minimum_distance']
                   for old in self._pool(True, conditional_only=True))

    def _build_state(self, round_number, correction):
        state = super()._build_state(round_number, correction)
        state.pop('state_sha256')
        state['candidate_pool'] = {'config': deepcopy(self.pool_config), 'feasible_count': len(self._pool()),
            'quality_count': len(self._pool(True)), 'target_reached': self._search_target_reached()}
        if self.explorer.conditional_physics is not None and self.pool_config['physics_options']['noise_allocation_enabled']:
            state['candidate_pool']['M1_quality_count'] = state['candidate_pool']['quality_count']
            state['candidate_pool']['quality_count'] = len(self._pool(True, conditional_only=True))
            state['candidate_pool']['quality_scope'] = 'FORMAL_M1_AND_CONDITIONAL_NOISE'
        state['state_sha256'] = fingerprint(state)
        return state

    def _adapt(self, raw, state, round_number):
        if raw.get('action') == 'STOP' and raw.get('stop_basis') == 'SPEC_SATISFIED' and not self._search_target_reached():
            raise ValueError('SPEC_SATISFIED cannot stop before K distinct quality-qualified M1 points')
        return super()._adapt(raw, state, round_number)

    def _decision_provenance(self):
        branches = getattr(self.policy, 'branch_history', [])
        return super()._decision_provenance() | {
            'strategy_proposer': 'TEST_POLICY' if self.injected_policy else branches[-1] if branches else 'DETERMINISTIC',
            'execution_route': 'CONTINUOUS_SPEC_ALLOCATION'}

    def _execute(self, decision):
        executed, observations, outcome = super()._execute(decision)
        # V2 Cold Start fallback: original Sobol, same executor/cache/reserve,
        # actually paid only when inverse failed to form an adequate pool.
        if (decision['action'] != 'BUILD_PHYSICS_REGION' or self.on_demand_calibration is not None
                or self._search_target_reached() or self.external_feedback):
            return executed, observations, outcome
        self.on_demand_calibration = {'M1_calls': 0, 'status': 'UNAVAILABLE_BUDGET'}
        # Prefer more inverse constructions when at least one quality point was
        # found. Global Sobol is needed only when inverse has no adequate seed.
        if self._pool(True):
            self.on_demand_calibration['status'] = 'SKIPPED_INVERSE_QUALITY_SUFFICIENT'
        else:
            budget = min(24, self.explorer.cost()['search_available_M1_calls'])
            if budget:
                d = envelope(self.explorer, decision_id='COLD:ON_DEMAND_CALIBRATION', region_id='COLD_GLOBAL',
                    bounds={k: [0., 1.] for k in self.explorer.problem['parameters']},
                    budget=budget, seed=self.config['seed'], proposals=128)
                first = len(self.explorer.rows)
                obs = self.explorer.execute(d)
                for row in self.explorer.rows[first:]:
                    if row['formal_M1_called'] and row['M1_status'] == 'OK':
                        self.tool_regions['COLD_CAL:'+row['evidence_id']] = {
                            'strategy': 'ACTUAL_ON_DEMAND_GLOBAL_SOBOL',
                            'normalized_bounds': around_seed(self.explorer.problem, row['parameters'], 'BALANCED'),
                            'formal_seed_ids': [row['evidence_id']], 'construction_seed_id': row['evidence_id']}
                self.on_demand_calibration = {'M1_calls': obs['cost']['M1_calls'],
                    'status': 'ACTUALLY_EXECUTED_ORIGINAL_SOBOL', 'observation_id': obs['observation_id']}
                self._remember(d, [obs], None)
                executed, observations = executed+[d], observations+[obs]
        write_new(self.root/'on_demand_calibration.json', self.on_demand_calibration)
        return executed, observations, outcome

    def finish(self):
        # Independent final audit must run even after the pool stop predicate.
        self.explorer.stop_when = None
        return super().finish()

    def _select_recommendation(self):
        options = self.pool_config.get('physics_options', {})
        if options.get('physics_ranking_enabled') or options.get('noise_allocation_enabled'):
            from .candidate_pool import select_m2
            return select_m2(self.archive.entries, self.explorer.problem, self.pool_config)
        return super()._select_recommendation()

    def cost(self):
        cost = super().cost()
        cost['policy_decisions'] = self.calls
        cost['offline_llm_decisions'] = getattr(self.policy, 'offline_calls', 0)
        cost['deterministic_decisions'] = (getattr(self.policy, 'branch_history', []).count('DETERMINISTIC')
                                          if isinstance(self.policy, PoolLLMPolicy) else self.calls)
        cost['test_policy_calls'] = self.calls if self.injected_policy else 0
        cost['on_demand_calibration_M1_calls'] = (self.on_demand_calibration or {}).get('M1_calls', 0)
        return cost

    def _result_fields(self):
        return super()._result_fields() | {'allocation_mode': self.pool_config['mode'],
            'execution_route': 'CONTINUOUS_SPEC_ALLOCATION',
            'actual_policy_execution': 'TEST_POLICY' if self.injected_policy else
                'REAL_LLM_EXECUTED' if self.cost()['LLM_calls'] else 'DETERMINISTIC_ONLY' if
                not getattr(self.policy, 'branch_history', []).count('LLM_PHYSICS_GUIDED') else 'LLM_BRANCH_NO_REAL_CALL',
            'execution_scope': 'TEST_POLICY_NOT_REAL_LLM' if self.injected_policy else 'PRODUCTION_PHYSICS_TOOLS',
            'M1_distinct_feasible_count': len(self._pool()), 'M1_quality_count': len(self._pool(True)),
            'pool_target_reached': self._search_target_reached(),
            'policy_branches': getattr(self.policy, 'branch_history', ['DETERMINISTIC']*self.calls)}
