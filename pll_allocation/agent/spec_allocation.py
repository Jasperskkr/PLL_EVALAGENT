"""Small multi-strategy entry adapter to the formal allocation/feedback pipeline."""
from copy import deepcopy
import json
from pathlib import Path
import time

from ..allocation.core import write_new
from ..delivery import validate_sizing_handoff
from ..io_contracts import file_identity, write_run_manifest
from ..exploration.contracts import load_problem, number, require
from .candidate_pool import distinct_candidates, joint_candidates, validate_pool_config
from .candidates import rank
from .feedback import run_feedback
from .initial_allocation import run_initial_allocation
from ..exploration.conditional_physics import FLAGS, allocation_options

SCHEMA = 'pll-spec-allocation-1.0'
DEFAULTS = {
    'mode': 'DETERMINISTIC', 'target_count': 5, 'm1_budget': 96, 'm2_budget': 3,
    'm2_target_count': 1,  # Omitted by historical configs: retain first-pass behavior.
    'llm_budget': 4, 'minimum_margin': 0., 'minimum_distance': .05,
    'deterministic_rounds': 3, 'allow_paid_llm': False, 'max_reallocations': 2,
    'initial_search_m1_budget': 32, 'max_decisions': 8, 'max_round_m1': 24,
    'construction_attempt_budget': 128, 'max_build_attempts': 16,
    'm2_timeout_s': 180, 'seed': 23,
    **{k: False for k in FLAGS}, 'physics_options': {},
}


def validate_config(raw):
    require(isinstance(raw, dict) and raw.get('schema_version') == SCHEMA and
            set(raw) <= set(DEFAULTS) | {'schema_version'}, 'unsupported spec allocation configuration')
    c = DEFAULTS | deepcopy(raw)
    for k in ('m1_budget', 'm2_budget', 'llm_budget', 'max_reallocations', 'initial_search_m1_budget',
              'max_decisions', 'max_round_m1', 'construction_attempt_budget', 'max_build_attempts', 'seed'):
        require(type(c[k]) is int and c[k] >= 0, k+': nonnegative integer required')
    require(c['m1_budget'] >= 3 and c['initial_search_m1_budget'] >= 3, 'at least three M1 calls required')
    require(c['m2_budget'] <= 32 and c['llm_budget'] <= 20 and c['max_reallocations'] <= 10, 'bounded allocation budgets required')
    require(type(c['m2_target_count']) is int and 1 <= c['m2_target_count'] <= 100,
            'm2_target_count must be 1..100')
    require(1 <= c['max_decisions'] <= 10 and 4 <= c['max_round_m1'] and
            c['seed']+c['max_decisions'] < 2**32, 'invalid search rounds/seed')
    require(1 <= c['max_build_attempts'] <= 64 and
            c['max_build_attempts'] <= c['construction_attempt_budget'] <= 1024, 'invalid construction budget')
    require(0 < number(c['m2_timeout_s'], 'm2_timeout_s') <= 3600, 'invalid M2 deadline')
    validate_pool_config(pool_config(c))
    allocation_options(c)
    return c


def pool_config(c):
    result = {k: c[k] for k in ('mode', 'target_count', 'minimum_margin', 'minimum_distance',
                            'deterministic_rounds', 'allow_paid_llm')} | {'llm_call_limit': c['llm_budget']}
    options = allocation_options(c)
    if options is not None:
        result['physics_options'] = options
    return result


def search_config(c, budget):
    return {'schema_version': 'pll-initial-allocation-1.0', 'bootstrap': 'COLD',
        'policy': 'DETERMINISTIC_PHYSICS_TOOL' if c['mode'] == 'DETERMINISTIC' else 'LLM_PHYSICS_TOOL',
        'candidate_pool': pool_config(c), 'total_m1_budget': budget, 'initial_m1_budget': 1,
        'initial_sobol_samples': 1, 'max_decisions': c['max_decisions'],
        'max_llm_calls': min(20, c['max_decisions']*2), 'validation_retries': 1,
        'max_round_m1': min(c['max_round_m1'], budget),
        'construction_attempt_budget': c['construction_attempt_budget'],
        'max_build_attempts': c['max_build_attempts'], 'seed': c['seed'],
        'slsqp': {'maxiter': 40, 'finite_difference_step': .00001}}


def rows(path):
    p = Path(path)
    return [json.loads(line) for line in p.read_text(encoding='utf-8').splitlines() if line.strip()] if p.exists() else []


def run_spec_allocation(problem_config, out, *, config, provider_config=None, feedback=None,
                        policy=None, m2_executor=None):
    """Real tools by default; explicit injected interfaces are TEST-only.

    M1/M2 totals include independent audits and posthoc M1. The formal
    feedback controller owns all M2 requests, native evidence and reallocation.
    External feedback can guide a new allocation but never imports a PASS.
    """
    c = validate_config(config); problem = load_problem(problem_config)
    problem_source = file_identity(problem_config)
    root = Path(out).resolve(); root.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    write_new(root/'allocation_config.json', c)
    write_new(root/'problem_resolved.json', problem)
    # Leave room for selected-point M2 audits/posthoc checks; budget pressure
    # may legitimately prevent M2. No uncharged emergency verification.
    initial_budget = min(c['initial_search_m1_budget'], max(3, c['m1_budget']-2*c['m2_budget']))
    initial_budget = min(initial_budget, c['m1_budget'])
    initial = run_initial_allocation(problem_config, root/'initial',
        config=search_config(c, initial_budget), provider_config=provider_config, feedback=feedback, policy=policy)
    cost = {'M1_calls': initial['cost']['M1_calls'], 'M2_verifications': 0,
            'LLM_calls': initial['cost']['LLM_calls'], 'completed_native_runs': 0,
            'integration_points': 0, 'native_elapsed_s': 0., 'test_policy_calls': initial['cost']['test_policy_calls']}
    for k in ('policy_decisions', 'offline_llm_decisions', 'deterministic_decisions'):
        cost[k] = initial['cost'].get(k, 0)
    for k in ('conditional_prediction_calls', 'conditional_noise_trial_integrations'):
        if k in initial['cost']:
            cost[k] = initial['cost'][k]
    ledger = rows(root/'initial/candidate_archive.jsonl')
    for row in ledger:
        row['source_run'] = str(root/'initial')
    qualified = distinct_candidates(ledger, problem, pool_config(c), quality_only=True)
    handoff_path = root/'initial/verification_handoff.json'
    h = json.loads(handoff_path.read_text(encoding='utf-8'))
    verification = None
    verification_started_s = None
    if qualified and h['ready_for_stage9'] and c['m2_budget'] and cost['M1_calls'] < c['m1_budget']:
        child = search_config(c, max(3, c['m1_budget']-cost['M1_calls']))
        child['candidate_pool']['llm_call_limit'] = max(0, c['llm_budget']-cost['LLM_calls'])
        verification_started_s = time.perf_counter()-started
        verification = run_feedback(handoff_path, root/'verification', problem_config=problem_config,
            feedback_config={'schema_version': 'pll-stage9-feedback-1.0',
                'm1_budget': c['m1_budget']-cost['M1_calls'], 'm2_budget': c['m2_budget'],
                'm2_target_count': c['m2_target_count'],
                'llm_budget': max(0, c['llm_budget']-cost['LLM_calls']), 'max_reallocations': c['max_reallocations'],
                'm2_timeout_s': c['m2_timeout_s'], 'search': child},
            provider_config=provider_config, policy=policy, m2_executor=m2_executor)
        for k in tuple(cost):
            cost[k] += verification['cost'].get(k, 0)
        for row in rows(root/'verification/candidate_archive.jsonl'):
            row['source_run'] = row.get('stage9_source_run', str(root/'verification'))
            ledger.append(row)
    verified = rows(root/'verification/m2_verifications.jsonl')
    by_hash = {}
    for item in verified:
        by_hash.setdefault(item['request']['candidate_sha256'], []).append(item)
    candidates = distinct_candidates(ledger, problem, pool_config(c))
    # Keep every actually verified point visible even if a later stronger M1
    # point falls inside its diversity neighborhood.
    seen = {r['parameter_sha256'] for r in candidates}
    for row in sorted(ledger, key=rank):
        if row['parameter_sha256'] in by_hash and row['parameter_sha256'] not in seen:
            candidates.append(row); seen.add(row['parameter_sha256'])
    test_m2 = m2_executor is not None
    for row in candidates:
        row['M1_feasibility'] = row['judgment']['m1_feasibility']
        row['quality_qualified'] = row['judgment']['minimum_normalized_margin'] >= c['minimum_margin']
        observations = by_hash.get(row['parameter_sha256'], [])
        row['M2_observations'] = observations
        row['M2_status'] = observations[-1]['observation']['overall_status'] if observations else 'NOT_EVALUATED'
        row['M2_supported_status'] = observations[-1]['observation']['supported_metrics_status'] if observations else 'NOT_EVALUATED'
        row['M2_evidence_scope'] = 'TEST_INJECTED_NOT_RESEARCH' if test_m2 and observations else 'NATIVE' if observations else 'NOT_EVALUATED'
    qualified = distinct_candidates(ledger, problem, pool_config(c), quality_only=True)
    passing_hashes = {r['parameter_sha256'] for r in candidates if r['M2_supported_status'] == 'PASS' and not test_m2}
    passed = joint_candidates(candidates, problem, pool_config(c), passing_hashes)
    joint_reached = len(passed) >= c['m2_target_count']
    joint_status = ('DISABLED' if not c['m2_budget'] else 'TEST_ONLY' if test_m2 else
                    'TARGET_REACHED' if joint_reached else 'PARTIAL' if passed else 'NOT_REACHED')
    recommended = min(passed, key=rank, default=None)
    best_m1 = min((r for r in candidates if r['quality_qualified']), key=rank, default=None)
    if c['physics_ranking_enabled'] or c['noise_allocation_enabled']:
        from .candidate_pool import select_m2
        recommended = select_m2(passed, problem, pool_config(c))
        best_m1 = select_m2(candidates, problem, pool_config(c))
    selected = recommended or best_m1
    cost.update(wall_time_s=time.perf_counter()-started, M1_limit=c['m1_budget'], M2_limit=c['m2_budget'],
                LLM_limit=c['llm_budget'])
    require(cost['M1_calls'] <= c['m1_budget'] and cost['M2_verifications'] <= c['m2_budget'] and
            cost['LLM_calls'] <= c['llm_budget'], 'cross-stage allocation hard budget exceeded')
    result = {'schema_version': SCHEMA, 'execution_route': 'CONTINUOUS_SPEC_ALLOCATION',
        'configuration_schema': SCHEMA, 'status': ('M2_JOINT_TARGET_REACHED' if joint_reached else 'M2_JOINT_PARTIAL')
        if recommended and c['m2_target_count'] > 1 else 'M2_SUPPORTED_METRICS_PASS' if recommended else
        'M1_POOL_ONLY' if candidates else 'NO_FEASIBLE_POINT_FOUND_WITHIN_BUDGET',
        'strategy': c['mode'], 'allocation_mode': c['mode'], 'target_count': c['target_count'],
        'M1_distinct_feasible_count': len(distinct_candidates(ledger, problem, pool_config(c))),
        'M1_quality_count': len(qualified), 'pool_target_reached': len(qualified) >= c['target_count'],
        'M2_supported_pass_count': len(passed), 'TEST_M2_injected': test_m2,
        'm2_target_count': c['m2_target_count'], 'joint_target_reached': joint_reached,
        'joint_status': joint_status, 'joint_candidates': passed,
        'time_to_first_joint_s': (verification_started_s + verification['time_to_first_joint_s']
                                 if passed and verification and verification['time_to_first_joint_s'] is not None else None),
        'time_to_joint_target_s': (verification_started_s + verification['time_to_joint_target_s']
                                  if joint_reached and verification and verification['time_to_joint_target_s'] is not None else None),
        'LLM_validation': 'REAL_CALL_EXECUTED' if cost['LLM_calls'] else 'OFFLINE_INTERFACE_ONLY' if policy else 'REAL_LLM_NOT_EXECUTED',
        'candidates': candidates, 'recommended': selected, 'recommended_M2_supported': recommended,
        'recommendation_basis': 'Formal M1 quality and native M2 supported metrics PASS; full M2 remains separate' if recommended else
            'M1 only: no native M2 supported-metrics PASS found; see actual failed/UNKNOWN/unexecuted evidence' if selected else
            'No quality-qualified feasible recommendation found within the configured budgets',
        'initial_termination': initial['termination_reason'],
        'verification_termination': verification['termination_reason'] if verification else 'NOT_EXECUTED',
        'failed_M2_constraints': [{'candidate_sha256': item['request']['candidate_sha256'],
            'evidence_id': item['observation']['evidence_id'],
            'constraints': [v for v in item['observation']['constraints'] if v['status'] == 'FAIL']}
            for item in verified if any(v['status'] == 'FAIL' for v in item['observation']['constraints'])],
        'M1_failure_artifacts': [str(p.relative_to(root)) for p in root.rglob('m1_samples.jsonl')],
        'cost': cost, 'failure': verification['failure'] if verification and verification['failure'] else initial['failure'],
        'M2_status': selected['M2_status'] if selected else 'NOT_EVALUATED',
        'FULL_SYSTEMSPEC_CERTIFIED': False,
        'scope': 'Fixed topology behavioral allocation; M2 PM/jitter remain UNKNOWN; search failure is not proof of infeasibility'}
    if c['noise_allocation_enabled']:
        from ..exploration.conditional_physics import ConditionalPhysics
        physics = ConditionalPhysics(problem, allocation_options(c))
        for row in candidates:
            row.update(physics.describe(row['parameters']))
            row['joint_conditional_feasibility'] = ('CONDITIONAL_FEASIBLE' if
                row['M1_feasibility'] == 'FEASIBLE' and physics.qualified(row) else 'NOT_ESTABLISHED')
        # Best-within-budget includes every quality-qualified formal point,
        # even when M1-only packing chose a nearby higher-margin representative.
        noise_ledger = [deepcopy(r) for r in ledger if r['judgment']['m1_feasibility'] == 'FEASIBLE' and
                        r['judgment']['minimum_normalized_margin'] >= c['minimum_margin']]
        for row in noise_ledger:
            row.update(physics.describe(row['parameters']))
        known = [r for r in noise_ledger if r.get('predicted_jitter_s') is not None]
        best_noise = min(known, key=lambda r: r['predicted_jitter_s'], default=None)
        count = len(distinct_candidates([r for r in noise_ledger if physics.qualified(r)],
                                       problem, pool_config(c), quality_only=True))
        result['conditional_noise_summary'] = {
            'status': 'CONDITIONAL_TARGET_REACHED' if count >= c['target_count'] else 'NOT_FOUND_WITHIN_BUDGET',
            'conditional_qualified_count': count, 'jitter_limit_s': physics.limit,
            'best_predicted_jitter_s': best_noise['predicted_jitter_s'] if best_noise else None,
            'best_candidate_sha256': best_noise['parameter_sha256'] if best_noise else None,
            'best_candidate': best_noise,
            'constraint_gap_s': max(0., best_noise['predicted_jitter_s']-physics.limit)
                if best_noise and physics.limit is not None else None,
            'stop_reason': initial['termination_reason'], 'formal_M2_jitter_status': 'UNKNOWN',
            'global_infeasibility_proven': False}
        result['pool_target_reached'] = len(qualified) >= c['target_count'] and count >= c['target_count']
    delivery = {
        'schema_version': 'pll-sizing-targets-1.0', 'problem': problem,
        'm2_target_count': c['m2_target_count'], 'joint_status': joint_status,
        'joint_target_reached': joint_reached, 'candidate_count': len(passed),
        'candidates': passed, 'recommended_candidate_sha256': recommended['parameter_sha256'] if recommended else None,
        'evidence_scope': 'NATIVE_M2_SUPPORTED_METRICS_ONLY',
        'not_certified': ['M2 PM', 'jitter', 'transistor realizability', 'PVT', 'parameter tolerance regions'],
        'FULL_SYSTEMSPEC_CERTIFIED': False,
        'scope': 'Behavioral targets and bound evidence for downstream sizing; no transistor sizing is executed.'}
    validate_sizing_handoff(delivery)
    write_new(root/'allocation_result.json', result)
    write_new(root/'cost_summary.json', cost)
    write_new(root/'candidates.json', candidates)
    write_new(root/'sizing_handoff.json', delivery)
    report = [f"Mode: {c['mode']}", f"M1 distinct/quality: {result['M1_distinct_feasible_count']}/{len(qualified)}; K={c['target_count']}",
        f"Native quality-distinct M1 + supported-M2 passing points: {len(passed)}/{c['m2_target_count']}; {joint_status}",
        'sizing_handoff.json contains only native jointly passing candidates, explicit units and verification evidence.',
        result['recommendation_basis'],
        f"Initial: {result['initial_termination']}; verification: {result['verification_termination']}",
        'Six parameters use explicit SI units in candidates.json; M1 metrics/margins/source and all executed M2 observations are retained.',
        'Recommended parameters (SI): '+json.dumps({k: v for k, v in selected['parameters']['values'].items()
            if k in problem['parameters']}, ensure_ascii=False) if selected else 'Recommended: none',
        json.dumps(cost, ensure_ascii=False, indent=2)]
    (root/'allocation_report.md').write_text('\n\n'.join(report)+'\n', encoding='utf-8')
    write_run_manifest(root, result, problem_source=problem_source)
    return result
