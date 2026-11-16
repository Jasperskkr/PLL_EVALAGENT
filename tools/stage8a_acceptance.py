"""Run explicit Stage8A acceptance decisions through the one formal CLI.

Consumes an existing Stage7 review directory read-only. Never runs global sampling,
M2 or an LLM. Outputs refuse to overwrite any existing files/directories.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pll_allocation.allocation.allocate import analytical
from pll_allocation.allocation.core import Meter, assess_m1, write_new
from pll_allocation.block_space.contracts import FREE_IDS
from pll_allocation.exploration import load_physics_context
from pll_allocation.exploration.contracts import check_candidate, judge
from pll_allocation.physics_mapping.model import evaluate
from pll_allocation.pipeline_contracts import load_inputs
from pll_allocation.region_explorer.contracts import OBJECTIVE, SCHEMA


def decisions(context, case):
    regions = context['candidate_regions']
    region = regions[min(1, len(regions)-1)] if regions else None
    sid = region['representative_evidence_id'] if region else None
    bounds = deepcopy(region['normalized_bounds']) if region else {k: [0., 1.] for k in FREE_IDS}
    rid = region['region_id'] if region else 'NEW:FULL_USER_DOMAIN'
    base = {'schema_version': SCHEMA, 'decision_id': case+'_probe', 'context_sha256': context['context_sha256'],
        'action': 'PROBE', 'region': {'region_id': rid, 'parent_region_id': None}, 'normalized_bounds': bounds,
        'active_variables': list(FREE_IDS), 'seed_ids': [sid] if sid else [], 'm1_budget': 32,
        'objective': OBJECTIVE, 'reason': 'Fixed algorithm acceptance: probe a saved Stage7 box; no LLM decision.',
        'evidence_ids': [sid] if sid else [], 'random_seed': 20261110, 'search_method': 'SOBOL',
        'settings': {'sample_count': 24}}
    result = [base]
    if region:
        opt = deepcopy(base)
        opt.update(decision_id=case+'_optimize', action='OPTIMIZE', search_method='SLSQP', m1_budget=192,
                   settings={'maxiter': 60, 'finite_difference_step': 1e-5},
                   reason='Fixed algorithm acceptance: maximize the minimum supported M1 bound margin in this exact six-axis box.')
        result.append(opt)
        if case == 'continuous':
            subset = deepcopy(opt)
            subset.update(decision_id=case+'_capacitors', m1_budget=64, active_variables=['C1', 'C2'],
                          reason='Test continuous non-enumerated capacitors while fixing all other variables at the legal seed.')
            result.append(subset)
    return result


def run_command(command, out, name):
    started = time.perf_counter()
    process = subprocess.run(command, cwd=ROOT, text=True, encoding='utf-8', errors='replace', capture_output=True)
    with (out/'commands.jsonl').open('a', encoding='utf-8') as stream:
        stream.write(json.dumps({'argv': command, 'cwd': str(ROOT), 'exit_code': process.returncode,
                                 'wall_time_s': time.perf_counter()-started}, ensure_ascii=False)+'\n')
    (out/(name+'_stdout.txt')).write_text(process.stdout, encoding='utf-8')
    (out/(name+'_stderr.txt')).write_text(process.stderr, encoding='utf-8')
    if process.returncode:
        raise RuntimeError(f'{name} CLI exited {process.returncode}: {process.stdout[-2000:]}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage7-root', required=True, help='directory containing global/tight/impossible/continuous runs')
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    source, out = Path(args.stage7_root).resolve(), Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out/'commands.jsonl').touch(exist_ok=False)
    inputs = {case: source/case/'physics_context.json' for case in ('global', 'tight', 'impossible', 'continuous')}
    contexts = {case: load_physics_context(path) for case, path in inputs.items()}
    protected = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for case, c in contexts.items()
                 for p in [inputs[case], *[inputs[case].parent/n for n in c['evidence_artifacts']]]}
    results, observations = {}, {}
    for case in (*inputs, 'reproducibility'):
        origin = 'global' if case == 'reproducibility' else case
        batch = decisions(contexts[origin], origin)
        file = out/(case+'_decisions.json')
        write_new(file, batch)
        command = [sys.executable, '-m', 'pll_allocation', 'pipeline', '--region-context', str(inputs[origin]),
                   '--search-decisions', str(file), '--region-m1-budget', str(sum(d['m1_budget'] for d in batch)),
                   '--out', str(out/case)]
        run_command(command, out, case)
        results[case] = json.loads((out/case/'result.json').read_text())
        observations[case] = json.loads((out/case/'region_observations.json').read_text())['observations']
        print(case, results[case]['status'], results[case]['cost']['M1_calls'], flush=True)
    require_same = results['global']['scientific_sha256'] == results['reproducibility']['scientific_sha256']
    if not require_same:
        raise AssertionError('Same-seed scientific digests differ')
    independent = []
    for case in ('global', 'tight', 'continuous'):
        rows = {r['evidence_id']: r for r in map(json.loads, (out/case/'m1_samples.jsonl').read_text().splitlines())}
        for obs in observations[case]:
            if not obs['final_recheck_evidence_id']:
                continue
            candidate = rows[obs['final_recheck_evidence_id']]
            start, cpu = time.perf_counter(), time.process_time()
            result = evaluate(candidate['parameters'])
            checked = judge(contexts[case]['problem'], candidate['parameters'], result)
            exact = result.metrics == candidate['metrics'] and checked == candidate['judgment']
            independent.append({'case': case, 'decision_id': obs['decision_id'], 'evidence_id': candidate['evidence_id'],
                'parameters': candidate['parameters'], 'formal_M1_result': result.as_dict(), 'judgment': checked,
                'exact_match': exact, 'M1_calls': 1, 'wall_time_s': time.perf_counter()-start,
                'process_cpu_s': time.process_time()-cpu, 'scope': 'INDEPENDENT_POST_RUN_RECHECK_OUTSIDE_EXECUTOR_BUDGET'})
            if not exact:
                raise AssertionError('Independent real M1 recheck differs')
    write_new(out/'independent_m1_rechecks.json', independent)
    # Reuse the unchanged Stage6B analytical implementation as a comparison only.
    # Its frozen discrete domain differs; never insert its candidates as legal new-domain seeds without checking.
    _, model, _, _ = load_inputs()
    references = []
    for case, name in (('global', 'B1'), ('tight', 'B2')):
        old_problem = json.loads((ROOT/f'configs/stage6b/{name}.json').read_text())
        meter = Meter(2000, 4)
        start, cpu = time.perf_counter(), time.process_time()
        candidate, metadata = analytical(model, old_problem['research_system_spec'], meter)
        assessment = assess_m1(model, old_problem['research_system_spec'], candidate, meter) if candidate else None
        references.append({'case': case, 'method': 'UNCHANGED_STAGE6B_ANALYTICAL', 'parameters': candidate,
            'metadata': metadata, 'assessment': assessment, 'cost': {**meter.counts,
                'wall_time_s': time.perf_counter()-start, 'process_cpu_s': time.process_time()-cpu},
            'continuous_domain_check': check_candidate(contexts[case]['problem'], candidate) if candidate else None,
            'scope': 'Different discrete domain; reference only, not an equal-budget algorithm comparison. No M2.'})
    write_new(out/'legacy_analytical_reference.json', references)
    unchanged = all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha for p, sha in protected.items())
    if not unchanged:
        raise AssertionError('Stage7 input artifact changed')
    summary = {'cases': {case: {'result': result, 'observations': observations[case]} for case, result in results.items()},
        'reproducible_scientific_digest': require_same, 'stage7_protected_artifacts': len(protected),
        'stage7_artifacts_unchanged': unchanged, 'independent_rechecks_exact': all(r['exact_match'] for r in independent),
        'cost': {'executor_M1_calls': sum(r['cost']['M1_calls'] for r in results.values()),
            'independent_recheck_M1_calls': len(independent), 'legacy_reference_M1_calls': sum(r['cost']['M1_calls'] for r in references),
            'legacy_reference_analytic_calls': sum(r['cost']['analytic_calls'] for r in references), 'M2_calls': 0, 'LLM_calls': 0},
        'boundary': 'Pointwise M1 research only; boxes, lock time and jitter are not certified.'}
    write_new(out/'acceptance_summary.json', summary)
    print(json.dumps({'cost': summary['cost'], 'reproducible': require_same, 'Stage7_unchanged': unchanged}))


if __name__ == '__main__':
    main()
