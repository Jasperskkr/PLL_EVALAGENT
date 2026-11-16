"""Read-only trace audit plus separately charged independent nominal M1 checks.

This is acceptance tooling, not a policy, decision validator, or solver. Partial
and failed provider outcomes are recorded; they are not retried or relabeled.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pll_allocation.allocation.core import write_new
from pll_allocation.agent.search_loop import source_manifest
from pll_allocation.exploration import load_physics_context
from pll_allocation.exploration.contracts import check_candidate, judge
from pll_allocation.physics_mapping.model import MappingResult, Status, evaluate, fingerprint
from pll_allocation.region_explorer.assessment import contains_parameters


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def lines(path):
    return [json.loads(s) for s in Path(path).read_text(encoding='utf-8').splitlines()]


def check(condition, message):
    if not condition:
        raise ValueError(message)


def ordering(row):
    return (row['judgment']['m1_feasibility'] != 'FEASIBLE',
            -row['judgment']['minimum_normalized_margin'], row['parameter_sha256'])


def audit(root):
    result, manifest, allocation = [read(root/name) for name in (
        'result.json', 'run_manifest.json', 'm1_allocation.json')]
    config = read(root/'loop_config.json')
    check(manifest['scope'] == 'REAL_LLM_REGION_PILOT', 'not a real provider run')
    check(read(root/'source_manifest.json') == source_manifest(), 'production source changed since run')
    context = load_physics_context(manifest['effective_context_path'])
    problem = context['problem']
    calibration = lines(Path(manifest['effective_context_path']).parent/'m1_samples.jsonl')
    samples = lines(root/'executor/m1_samples.jsonl')
    evidence = {r['evidence_id']: r for r in calibration+samples}
    decisions = {r['decision']['decision_id']: r['decision']
                 for r in lines(root/'executor/search_decisions.jsonl')}
    rechecks = lines(root/'executor/recommendation_rechecks.jsonl') if (
        root/'executor/recommendation_rechecks.jsonl').exists() else []
    # Recommendation verification is explicitly a domain audit, not hidden search
    # outside the accepted LLM box. Its source and envelope must be on disk.
    for record in rechecks:
        decisions[record['decision']['decision_id']] = record['decision']
    for row in samples:
        decision = decisions[row['decision_id']]
        check(contains_parameters(problem, decision['normalized_bounds'], row['parameters']),
              'sample outside declared execution envelope: '+row['evidence_id'])
        check(row['parameter_sha256'] == fingerprint(row['parameters']), 'sample parameter hash mismatch')
    formal_calls = sum(r['formal_M1_called'] for r in samples)
    check(formal_calls == result['cost']['executor']['M1_calls'], 'executor formal-call count differs')
    check(formal_calls+manifest['calibration']['new_M1_calls'] == result['cost']['M1_calls'],
          'calibration/executor total differs')
    check(result['cost']['M1_calls'] <= config['total_m1_budget'], 'session formal budget overrun')
    check(result['cost']['LLM_calls'] <= config['max_llm_calls'], 'provider budget overrun')
    check(result['cost']['M2_calls'] == 0, 'unexpected research M2 call')
    observations = lines(root/'executor/region_observations.jsonl')
    for observation in observations:
        check(observation['cost']['M1_calls'] <= observation['cost']['allocated_M1_budget'], 'action budget overrun')
    # Independently rejudge every applicable formal result under the current Spec.
    applicable = []
    for row in calibration+samples:
        raw = row.get('formal_M1_result')
        if not raw or row['M1_status'] != 'OK':
            continue
        check(row['problem_sha256'] == problem['problem_sha256'], 'stale problem binding')
        check(row['model_fingerprint'] == context['model']['model_sha256'], 'stale model binding')
        model_result = MappingResult(**(raw | {'status': Status(raw['status'])}))
        judgment = judge(problem, row['parameters'], model_result)
        if (model_result.status == Status.OK and judgment['minimum_normalized_margin'] is not None
                and check_candidate(problem, row['parameters'])['status'] == 'NECESSARY_CONDITIONS_SATISFIED'):
            check(judgment == row['judgment'], 'saved judgment differs from current Spec')
            applicable.append(row | {'judgment': judgment})
    archived = lines(root/'candidate_archive.jsonl')
    check({r['evidence_id'] for r in applicable} == {r['evidence_id'] for r in archived},
          'archive lost applicable formal evidence')
    best = min((r for r in applicable if r['judgment']['m1_feasibility'] == 'FEASIBLE'),
               key=ordering, default=None)
    recommended = allocation['recommended_nominal']
    check(bool(best) == bool(recommended), 'known feasible recommendation missing or fabricated')
    if best:
        check(best['parameter_sha256'] == recommended['parameter_sha256'], 'recommendation is not best known')
        recheck = allocation['recommendation_recheck']
        check(recheck.get('row', {}).get('formal_M1_called'), 'nominal lacks fresh formal M1 call')
        check(recheck['row']['parameters'] == recommended['parameters'], 'recheck evaluated another point')
        check(recheck['passed'] == (recheck['row']['metrics'] == recommended['metrics'] and
                                    recheck['row']['judgment'] == recommended['judgment'] and
                                    recheck['row']['M1_status'] == 'OK'), 'recheck status mismatch')
    states, calls, rounds = [], [], []
    for folder in sorted(root.glob('round_*')):
        for path in sorted(folder.glob('planner_state_*.json')):
            state = read(path)
            index = path.stem.rsplit('_', 1)[1]
            call = folder/f'llm_call_{index}'
            metadata = read(call/'metadata.json')
            if (call/'request.json').exists():
                request = read(call/'request.json')
                check(json.loads(request['messages'][0]['content']) == state, 'request differs from saved state')
                check(fingerprint(request) == metadata['request_sha256'], 'request fingerprint differs')
            check(metadata['state_sha256'] == fingerprint(state), 'state fingerprint differs')
            if state['round'] == 1:
                text = json.dumps(state)
                check('candidate_regions' not in text and 'normalized_bounds' not in text,
                      'first PlannerState leaked a fixed region menu')
            check(all(s['center_values_SI'] is not None for s in state['sensitivity']), 'local derivative lacks center')
            states.append(state)
            calls.append(metadata)
        if not (folder/'search_decision.json').exists():
            continue  # Failed validation/provider round remains evidence, not an executed decision.
        approved = read(folder/'search_decision.json')
        record = read(folder/'region_observation.json')
        check(approved['decision'] == record['decision'], 'accepted and observed decisions differ')
        d = record['decision']
        proposals = [read(p) for p in folder.glob('proposal_*.json')]
        if d['action'] == 'OPTIMIZE':
            check(any(p.get('normalized_bounds') == d['normalized_bounds'] and p.get('seed_ids') == d['seed_ids']
                      and p.get('active_variables') == d['active_variables'] for p in proposals), 'geometry silently changed')
            check(all(e['normalized_bounds'] == d['normalized_bounds'] for e in record['execution_decisions']),
                  'execution changed LLM box')
        for execution in record['execution_decisions']:
            check(decisions[execution['decision_id']] == execution, 'executor log differs from outer loop')
            for sid in execution['seed_ids']:
                check(contains_parameters(problem, execution['normalized_bounds'], evidence[sid]['parameters']),
                      'accepted seed outside box')
            for row in samples:
                if row['decision_id'] != execution['decision_id']:
                    continue
                for sid in execution['seed_ids']:
                    if row['origin'].startswith('SLSQP:'+sid+':'):
                        check(all(row['parameters']['values'][k] == evidence[sid]['parameters']['values'][k]
                                  for k in problem['parameters'] if k not in execution['active_variables']),
                              'inactive variable changed')
        for next_state in states:
            for previous in next_state['history']:
                if previous['search_decision']['decision_id'] == d['decision_id']:
                    check(previous['search_decision'] == d, 'feedback decision mismatch')
        rounds.append({'round': record['round'], 'LLM_decision': d, 'progress': record['progress'],
                       'outcome': record['outcome'], 'observations': record['observations']})
    check(sum(c['real_network_call'] for c in calls) == result['cost']['LLM_calls'], 'network call count differs')
    for state in states:
        for past in state['history']:
            actual = next(r for r in rounds if r['LLM_decision']['decision_id'] == past['search_decision']['decision_id'])
            check(actual['LLM_decision'] == past['search_decision'], 'next-state decision differs from execution')
            for original, exposed in zip(actual['observations'], past['observations']):
                check(all(original[k] == exposed[k] for k in ('observation_id', 'solver_runs', 'cost',
                          'latest_minimum_normalized_margin', 'best_evidence_id')), 'next-state observation differs')
        best_point = state['best_known']
        if best_point:
            check(best_point['metrics'] == evidence[best_point['evidence_id']]['metrics'], 'planner best metrics fabricated')
    artifacts = read(root/'output_manifest.json')
    check(all(hashlib.sha256((root/name).read_bytes()).hexdigest() == sha for name, sha in artifacts.items()),
          'saved artifact fingerprint changed')
    independent = None
    if recommended:
        start = time.perf_counter()
        fresh = evaluate(recommended['parameters'])
        judgment = judge(problem, recommended['parameters'], fresh)
        independent = {'scope': 'EXTERNAL_AUDIT; additional to120-call run budget, separately counted',
                       'evidence_id': recommended['evidence_id'], 'formal_M1_result': fresh.as_dict(),
                       'judgment': judgment, 'M1_calls': 1, 'wall_time_s': time.perf_counter()-start,
                       'exact_match': fresh.metrics == recommended['metrics'] and judgment == recommended['judgment']}
        check(independent['exact_match'], 'independent external M1 differs')
    token_totals = Counter()
    for call in calls:
        for key, value in (call.get('usage') or {}).items():
            if isinstance(value, (int, float)):
                token_totals[key] += value
    return {'run': str(root), 'checks_passed': True,
            'problem': problem, 'model': context['model'],
            'first_state': states[0] if states else None, 'rounds': rounds,
            'accepted_geometry_preserved': True, 'all_applicable_formal_candidates_archived': True,
            'stage7_origins': dict(Counter(r['origin'].split(':', 1)[0] for r in calibration)),
            'calibration_formal_calls_historical_or_new': sum(bool(r.get('formal_M1_result')) for r in calibration),
            'archived_candidates': len(archived), 'executor_sample_requests': len(samples),
            'solver_runs': [s for o in observations for s in o['solver_runs']],
            'termination_reason': result['termination_reason'], 'm1_allocation_status': result['m1_allocation_status'],
            'feedback_loop_status': result['feedback_loop_status'],
            'feedback_reoptimization_completed': result['feedback_reoptimization_completed'],
            'recommended_nominal': recommended, 'best_stage7_calibration': allocation['best_stage7_calibration'],
            'best_stage8b_new': allocation['best_stage8b_new'],
            'improvement_over_calibration': allocation['improvement_over_calibration'],
            'recommendation_recheck': allocation['recommendation_recheck'],
            'external_independent_M1': independent, 'cost': result['cost'],
            'provider_calls': calls, 'reported_token_totals': dict(token_totals),
            'monetary_cost': None, 'monetary_cost_reason': 'No configured provider pricing; token counts are actual reports.',
            'M2_status': 'NOT_EVALUATED', 'FULL_SYSTEMSPEC_CERTIFIED': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', nargs='+', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    summaries, errors = [], []
    for path in args.runs:
        try:
            item = audit(Path(path).resolve())
            summaries.append(item)
            write_new(out/(Path(path).name+'.json'), item)
        except Exception as error:
            errors.append({'run': path, 'error': type(error).__name__+': '+str(error)})
    result = {'cases': [dict(run=s['run'], termination_reason=s['termination_reason'],
                            m1_allocation_status=s['m1_allocation_status'], cost=s['cost'],
                            improvement=s['improvement_over_calibration']) for s in summaries],
              'all_evidence_checks_passed': not errors, 'errors': errors,
              'extra_audit_M1_calls': sum(s['external_independent_M1'] is not None for s in summaries),
              'LLM_calls': 0, 'M2_calls': 0}
    write_new(out/'summary.json', result)
    print(json.dumps(result, ensure_ascii=False))
    return bool(errors)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
