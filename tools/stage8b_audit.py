"""Independent Stage8B evidence checks and explicitly costed extra M1 rechecks."""
import argparse
import hashlib
import itertools
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
from pll_allocation.physics_mapping.model import evaluate, fingerprint
from pll_allocation.region_explorer.assessment import contains_parameters


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', nargs='+', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    summaries, rechecks = [], []
    for directory in args.runs:
        root = Path(directory).resolve()
        result, manifest = read(root/'result.json'), read(root/'run_manifest.json')
        assert result['feedback_decision_completed'] and result['new_M1_feasible_allocation'], result
        assert result['cost']['M1_calls'] <= result['cost']['M1_limit']
        assert result['cost']['LLM_calls'] <= 3 and result['cost']['M2_calls'] == 0
        assert manifest['scope'] == 'REAL_LLM_REGION_PILOT'
        assert read(root/'source_manifest.json') == source_manifest(), 'run source differs from current source'
        context = load_physics_context(manifest['effective_context_path'])
        states, requests = [], []
        for folder in sorted(root.glob('round_*')):
            approved = read(folder/'search_decision.json')
            assert approved['region_origin'] == 'LLM_PROPOSED' and approved['proposer'] == 'REAL_LLM'
            record = read(folder/'region_observation.json')
            assert approved['decision'] == record['decision']
            proposals = [read(p) for p in folder.glob('proposal_*.json')]
            if record['decision']['action'] != 'STOP':
                assert any(p.get('normalized_bounds') == record['decision']['normalized_bounds'] and
                           p.get('active_variables') == record['decision']['active_variables'] and
                           p.get('seed_ids') == record['decision']['seed_ids'] for p in proposals)
                assert all(d['normalized_bounds'] == record['decision']['normalized_bounds']
                           for d in record['execution_decisions'])
            for statefile in sorted(folder.glob('planner_state_*.json')):
                index = statefile.stem.rsplit('_', 1)[1]
                state = read(statefile)
                request = read(folder/f'llm_call_{index}/request.json')
                metadata = read(folder/f'llm_call_{index}/metadata.json')
                assert json.loads(request['messages'][0]['content']) == state
                assert metadata['state_sha256'] == fingerprint(state)
                assert metadata['request_sha256'] == fingerprint(request)
                assert metadata['real_network_call'] and metadata['http_status'] == 200
                assert metadata['status'] == 'RESPONDED' and metadata['usage']['output_tokens'] > 0
                if state['round'] == 1:
                    text = json.dumps(state)
                    assert not any(k in text for k in ('candidate_regions', 'R001', 'R002', 'R003', 'normalized_bounds'))
                states.append(state)
                requests.append(metadata)
        first = read(root/'round_01/region_observation.json')
        second = next(s for s in states if s['round'] == 2)
        assert second['history'][0]['search_decision'] == first['decision']
        for actual, exposed in zip(first['observations'], second['history'][0]['observations']):
            for key in ('observation_id', 'solver_runs', 'cost', 'latest_minimum_normalized_margin'):
                assert actual[key] == exposed[key], (key, actual, exposed)
        new_sample_ids = {r['evidence_id'] for r in second['calibration']['displayed_samples'] if r['evidence_id'].startswith('A8S')}
        assert new_sample_ids, 'second LLM request has no real new M1 sample'
        executor_rows = list(map(json.loads, (root/'executor/m1_samples.jsonl').read_text().splitlines()))
        rows = {r['evidence_id']: r for r in executor_rows}
        executed = {d['decision']['decision_id']: d['decision'] for d in
                    map(json.loads, (root/'executor/search_decisions.jsonl').read_text().splitlines())}
        for row in executor_rows:
            decision = executed[row['decision_id']]
            assert contains_parameters(context['problem'], decision['normalized_bounds'], row['parameters'])
        for sample in second['calibration']['displayed_samples']:
            if sample['evidence_id'] in new_sample_ids:
                assert sample['metrics'] == rows[sample['evidence_id']]['metrics']
        observations = read(root/'executor/region_observations.json')['observations']
        assert result['cost']['M1_calls'] == sum(r['formal_M1_called'] for r in executor_rows)
        for obs in observations:
            assert obs['cost']['M1_calls'] <= obs['cost']['allocated_M1_budget']
            for d in executed.values():
                if d['decision_id'] == obs['decision_id'] and d['search_method'] == 'SLSQP':
                    seeds = {r['evidence_id']: r for r in map(json.loads,
                             (Path(manifest['effective_context_path']).parent/'m1_samples.jsonl').read_text().splitlines())}
                    seeds.update(rows)
                    for run in obs['solver_runs']:
                        sid = run['seed_id']
                        source = seeds[sid]['parameters']['values']
                        for row in executor_rows:
                            if row['decision_id'] == d['decision_id'] and row['origin'].startswith('SLSQP:'+sid):
                                assert all(row['parameters']['values'][k] == source[k]
                                           for k in context['problem']['parameters'] if k not in d['active_variables'])
        allocation = read(root/'m1_allocation.json')['new_allocation']
        assert rows[allocation['evidence_id']]['independent_final_recheck']
        assert check_candidate(context['problem'], allocation['parameters'])['status'] == 'NECESSARY_CONDITIONS_SATISFIED'
        start, cpu = time.perf_counter(), time.process_time()
        independent = evaluate(allocation['parameters'])
        judgment = judge(context['problem'], allocation['parameters'], independent)
        assert independent.metrics == allocation['metrics'] and judgment == allocation['judgment']
        rechecks.append({'run': str(root), 'evidence_id': allocation['evidence_id'],
            'formal_M1_result': independent.as_dict(), 'judgment': judgment, 'exact_match': True,
            'M1_calls': 1, 'wall_time_s': time.perf_counter()-start, 'process_cpu_s': time.process_time()-cpu,
            'scope': 'POST_RUN_INDEPENDENT_AUDIT; outside planner and executor budget, counted separately'})
        proposal = first['decision']
        dimensions = list(proposal['normalized_bounds'])
        outside_example = next((dict(zip(dimensions, point)) for point in itertools.product(*proposal['normalized_bounds'].values())
            if not any(all(reg['normalized_bounds'][k][0] <= point[i] <= reg['normalized_bounds'][k][1]
                           for i,k in enumerate(dimensions)) for reg in context['candidate_regions'])), None)
        artifacts = read(root/'output_manifest.json')
        assert all(hashlib.sha256((root/name).read_bytes()).hexdigest() == sha for name,sha in artifacts.items())
        summaries.append({'run': str(root), 'status': result['status'],
            'real_LLM_calls': result['cost']['LLM_calls'], 'M1_calls': result['cost']['M1_calls'],
            'request_rows': len(executor_rows), 'formal_M1_recheck_exact': True,
            'rounds': result['decision_rounds'], 'feedback_observation_matches_next_request': True,
            'new_M1_samples_present_in_second_request': sorted(new_sample_ids),
            'first_region_not_equal_to_stage7_menu': all(proposal['normalized_bounds'] != r['normalized_bounds'] for r in context['candidate_regions']),
            'first_region_has_unsampled_menu_exterior_corner': outside_example,
            'corner_scope': 'Geometry comparison only; no feasibility claim for the corner',
            'source_and_output_hashes_valid': True, 'all_six_axis_request_bounds_valid': True,
            'raw_LLM_geometry_equals_validated_and_executed_geometry': True,
            'final_metrics': allocation['metrics'], 'final_parameters': allocation['parameters'],
            'final_judgment': allocation['judgment'], 'initial_best_calibration_margin':
                read(root/'m1_allocation.json')['calibration_baseline']['judgment']['minimum_normalized_margin'],
            'solver_runs': [s for o in observations for s in o['solver_runs']], 'cost': result['cost']})
    write_new(out/'independent_m1_rechecks.json', rechecks)
    write_new(out/'acceptance_summary.json', {'cases': summaries, 'all_evidence_checks_passed': True,
        'external_audit_M1_calls': len(rechecks), 'M2_calls': 0, 'LLM_calls': 0})
    print(json.dumps({'cases':len(summaries),'passed':True,'extra_M1_calls':len(rechecks)}))


if __name__ == '__main__':
    main()
