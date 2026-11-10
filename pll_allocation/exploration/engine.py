"""Physics-guided Sobol exploration using the original M1 evaluator and algebra."""
from copy import deepcopy
import csv
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import sys
import time

from ..allocation.core import Meter, values, write_new
from ..allocation.physics import RELATIONS, inverse_at_shape, raw_prediction
from ..block_space.contracts import FREE_IDS
from ..physics_mapping.model import MODEL_ID, evaluate, fingerprint
from .contracts import active_m1_specs, axes, check_candidate, coordinate, judge, load_problem, make_parameters, screen_problem
from .regions import candidate_regions, sensitivity

ROOT = Path(__file__).resolve().parents[2]
AUDITED = ('block_space/contracts.py', 'physics_mapping/model.py', 'physics_mapping/registry.py',
           'physics_mapping/experiment.py', 'allocation/physics.py', 'allocation/allocate.py',
           'allocation/multispec_search.py', 'allocation/agent.py', 'pipeline.py')


def source_identity():
    package = ROOT/'pll_allocation'
    paths = [package/name for name in AUDITED] + sorted(Path(__file__).parent.glob('*.py'))
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def model_identity():
    sources = source_identity()
    return {'model_id': MODEL_ID, 'model_sha256': fingerprint({k: v for k, v in sources.items()
            if k.endswith(('physics_mapping/model.py', 'physics_mapping/experiment.py', 'allocation/physics.py'))}),
            'source_fingerprints': sources, 'scan': 'unchanged formal M1 default FrequencyScan(points=8000)',
            'domain_status': 'USER_DECLARED_MATHEMATICAL_DOMAIN; M2_EQUIVALENCE_NOT_ESTABLISHED'}


def run_exploration(problem_path, out, *, seed=None, budget=None):
    from scipy.stats import qmc
    problem = load_problem(problem_path, seed=seed, budget=budget)
    root = Path(out).resolve()
    root.mkdir(parents=True, exist_ok=False)
    identity = model_identity()
    input_sha = hashlib.sha256(Path(problem_path).read_bytes()).hexdigest()
    started, cpu = time.perf_counter(), time.process_time()
    meter = Meter(problem['exploration']['max_analytic_calls'], problem['exploration']['max_m1_evaluations'])
    counts = {'proposals': 0, 'duplicates': 0, 'screen_rejections': 0, 'seed_failures': 0,
              'analytic_failures': 0, 'M1_failures': 0, 'M1_budget_skips': 0, 'sobol_samples': 0}
    metadata = {'problem_schema_version': problem['schema_version'], 'problem_sha256': problem['problem_sha256'],
                'problem_id': problem['problem_id'], 'model_fingerprint': identity['model_sha256'],
                'source_fingerprint': fingerprint(identity['source_fingerprints']),
                'seed': problem['exploration']['seed'], 'scope': 'STAGE7_CONTINUOUS_M1_EXPLORATION_ONLY'}
    samples, cache, failure = [], {}, None
    trace_path, samples_path = root/'run_events.jsonl', root/'m1_samples.jsonl'
    trace_path.touch(exist_ok=False)
    samples_path.touch(exist_ok=False)

    def cost():
        return {**meter.counts, **counts, 'LLM_calls': 0, 'M2_calls': 0}

    def emit(event, **data):
        row = {'event_id': f'E{emit.index+1:06d}', **metadata, 'event': event, 'cost': cost(), **data}
        emit.index += 1
        with trace_path.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False)+'\n')
    emit.index = 0

    def sample(candidate, origin):
        meter.charge('candidate_generations', origin=origin)
        counts['proposals'] += 1
        row = {**metadata, 'evidence_id': f'S{len(samples)+1:06d}', 'origin': origin, 'parameters': candidate,
               'parameter_sha256': fingerprint(candidate)}
        key = row['parameter_sha256']
        emit('CANDIDATE_PROPOSED', action='ProposeContinuousParameters', origin=origin, parameters=candidate,
             parameter_sha256=key, decision='Persist full proposal before screening and formal M1')
        if key in cache:
            counts['duplicates'] += 1
            original = cache[key]
            row.update(duplicate_of=original['evidence_id'], screening=original['screening'],
                       M1_status='DUPLICATE_REFERENCE', metrics=original['metrics'], judgment=original['judgment'],
                       cheap_prediction=None, formal_M1_result=None)
        else:
            screening = check_candidate(problem, candidate)
            row.update(screening=screening, cheap_prediction=None, formal_M1_result=None)
            result = None
            if screening['status'] != 'NECESSARY_CONDITIONS_SATISFIED':
                counts['screen_rejections'] += 1
                row['M1_status'] = 'NOT_EVALUATED_SCREEN_REJECTED'
            elif meter.counts['M1_calls'] >= meter.m1_limit:
                counts['M1_budget_skips'] += 1
                row['M1_status'] = 'NOT_EVALUATED_M1_BUDGET_EXHAUSTED'
            else:
                if meter.counts['analytic_calls'] < meter.cheap_limit:
                    try:
                        row['cheap_prediction'] = meter.timed('analytic_calls', raw_prediction, values(candidate))
                    except (ArithmeticError, ValueError) as error:
                        counts['analytic_failures'] += 1
                        row['cheap_failure'] = {'type': type(error).__name__, 'reason': str(error)}
                result = meter.timed('M1_calls', evaluate, candidate)
                row['M1_status'] = result.status.value
                row['formal_M1_result'] = result.as_dict()
                if result.status.value != 'OK':
                    counts['M1_failures'] += 1
            row['metrics'] = result.metrics if result else {}
            row['judgment'] = judge(problem, candidate, result)
            if row['cheap_prediction'] and row['metrics']:
                row['quick_minus_formal'] = {k: v-row['metrics'][k] for k, v in row['cheap_prediction'].items()}
            cache[key] = row
        row['cost'] = cost()
        samples.append(row)
        with samples_path.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False)+'\n')
        emit('CANDIDATE_RECORDED', action='ScreenAndEvaluateM1', evidence_id=row['evidence_id'], origin=origin,
             parameter_sha256=key, observation={'screening': row['screening'], 'M1_status': row['M1_status'],
                                              'judgment': row['judgment']},
             decision='Reference existing evidence' if row.get('duplicate_of') else 'Apply independent configured constraints')
        return cache[key]

    screening = screen_problem(problem)
    write_new(root/'problem_resolved.json', {'metadata': metadata, 'problem': problem, 'model': identity,
               'status': 'RESOLVED_BEFORE_EXPLORATION', 'cost': cost()})
    write_new(root/'run_manifest.json', {'metadata': metadata, 'model': identity,
               'input_file_sha256': input_sha, 'environment': {'python': sys.version, 'platform': platform.platform(),
                   'scipy': importlib.metadata.version('scipy'), 'numpy': importlib.metadata.version('numpy')},
               'budgets': problem['exploration'], 'status': 'STARTED', 'cost': cost()})
    emit('RUN_STARTED', action='PhysicsScreening', observation=screening, decision='Proceed only without a necessary-condition contradiction')
    regions, derivatives = {'regions': [], 'feasible_evidence_ids': []}, {'representatives': []}
    try:
        if not screening['certificates']:
            settings = problem['exploration']
            if settings['physics_seed_count']:
                sample(make_parameters(problem), 'PHYSICS_SEED:USER_DEFAULT')
            bw = next((s for s in active_m1_specs(problem) if s['metric'] == 'BW_Hz'), None)
            target_bw = ((bw['min']+bw['max'])/2 if {'min', 'max'} <= set(bw) else
                         bw['min']*1.2 if 'min' in bw else bw['max']*.8) if bw else None
            for i in range(max(0, settings['physics_seed_count']-1)):
                origin = f'PHYSICS_SEED:INVERSE_SHAPE:{i+1:03d}'
                try:
                    if target_bw is None or target_bw <= 0:
                        raise ValueError('No positive supported BW target for inverse seed')
                    c1axis, c2axis = problem['parameters']['C1'], problem['parameters']['C2']
                    if i == 0:
                        c1, c2 = c1axis['default'], c2axis['default']
                    elif i == 1:
                        c1, c2 = c1axis['min'], c2axis['max']
                    else:
                        c1 = coordinate(c1axis, (i*.6180339887498949) % 1, inverse=True)
                        c2 = coordinate(c2axis, (i*.4142135623730951) % 1, inverse=True)
                    shape = math.sqrt(1+c2/c1)*(1., .8, 1.25)[i % 3]
                    emit('PHYSICS_SEED_PLANNED', origin=origin, C1_F=c1, C2_F=c2, shape_x=shape,
                         target_BW_Hz=target_bw, action='InverseAtShape', decision='Use existing continuous-shape inverse')
                    proposed = inverse_at_shape(axes(problem), c1, c2, target_bw, shape, meter)
                    if proposed is None:
                        raise ValueError('No legal Icp/Kvco gain split for inverse seed')
                    sample(make_parameters(problem, proposed, check_bounds=False), origin)
                except (ValueError, ArithmeticError, RuntimeError) as error:
                    counts['seed_failures'] += 1
                    emit('PHYSICS_SEED_FAILED', origin=origin, reason=str(error),
                         action='InverseAtShape', decision='Keep failure cost; do not clip or replace the seed')
            n = settings['sobol_samples']
            if n:
                draws = qmc.Sobol(d=6, scramble=True, seed=settings['seed']).random_base2((n-1).bit_length())
                emit('SOBOL_PLAN', requested_samples=n, generated_unit_points=len(draws), used_prefix=n,
                     action='SobolContinuousSampling', decision='Configured linear/log transforms; no rejection resampling')
                for i, u in enumerate(draws[:n]):
                    overrides = {name: coordinate(problem['parameters'][name], float(value), inverse=True)
                                 for name, value in zip(FREE_IDS, u)}
                    counts['sobol_samples'] += 1
                    sample(make_parameters(problem, overrides), f'SOBOL:{i+1:06d}')
            exploration_samples = list(samples)
            regions = candidate_regions(problem, exploration_samples)
            derivatives = sensitivity(problem, regions, sample)
        else:
            exploration_samples = []
        if source_identity() != identity['source_fingerprints'] or hashlib.sha256(Path(problem_path).read_bytes()).hexdigest() != input_sha:
            raise RuntimeError('SOURCE_OR_INPUT_MUTATED_DURING_RUN')
    except Exception as error:
        failure = {'type': type(error).__name__, 'reason': str(error)}
        emit('EXPLORATION_ERROR', failure=failure)
    unique = [r for r in samples if not r.get('duplicate_of')]
    feasible = [r for r in unique if r['judgment']['m1_feasibility'] == 'FEASIBLE' and not r['origin'].startswith('SENSITIVITY:')]
    status = ('PIPELINE_ERROR' if failure else 'PROVEN_M1_INFEASIBLE' if screening['certificates'] else
              'M1_FEASIBLE_SAMPLES_FOUND' if feasible else 'M1_BUDGET_EXHAUSTED_NO_FEASIBLE_SAMPLE' if counts['M1_budget_skips'] else
              'M1_NOT_REQUESTED' if not active_m1_specs(problem) else 'NO_M1_FEASIBLE_SAMPLE_FOUND')
    costs = {**cost(), 'wall_time_s': time.perf_counter()-started, 'process_cpu_s': time.process_time()-cpu,
             'timing_scope': 'post-resolution screening/sampling/sensitivity; excludes startup and final export',
             'monetary_cost': None}
    summary = {'status': status, 'exploration_feasible_samples': len(feasible), 'unique_candidates': len(unique),
               'M1_budget_exhausted': counts['M1_budget_skips'] > 0,
               'valid_formal_M1_samples': sum(r['M1_status'] == 'OK' for r in unique),
               'region_count': len(regions['regions']), 'unsupported_or_pending_enabled_specs': [s['metric'] for s in problem['specs']
                    if s['enabled'] and s['support_status'] != 'M1_SUPPORTED'], 'FULL_SYSTEMSPEC_CERTIFIED': False,
               'verified_joint_block_spec': False, 'failure': failure}
    scientific = {'problem_sha256': problem['problem_sha256'], 'model_fingerprint': identity['model_sha256'],
                  'samples': [{k: r[k] for k in ('evidence_id', 'origin', 'parameter_sha256', 'M1_status', 'metrics', 'judgment')} for r in samples],
                  'regions': regions, 'sensitivity': derivatives, 'summary': summary}
    science_sha = fingerprint(scientific)
    common = {'metadata': metadata, 'model': identity, 'cost': costs, 'status': status,
              'run_status': status, 'scientific_sha256': science_sha}
    write_new(root/'physics_screening.json', {**common, **screening})
    write_new(root/'candidate_regions.json', {**common, **regions})
    write_new(root/'sensitivity.json', {**common, **derivatives})
    write_new(root/'cost_events.json', {**common, 'events': meter.events})
    write_new(root/'feasible_candidates.json', {**common, 'candidates': [
        {'evidence_id': r['evidence_id'], 'origin': r['origin'], 'parameters': r['parameters'],
         'metrics': r['metrics'], 'judgment': r['judgment']} for r in feasible]})
    with (root/'m1_samples.csv').open('x', encoding='utf-8-sig', newline='') as stream:
        fields = ['evidence_id', 'origin', 'parameter_sha256', 'duplicate_of', *make_parameters(problem)['values'],
                  'M1_status', 'm1_feasibility', 'all_enabled_specs_status', 'BW_Hz', 'PM_deg', 'UGF_Hz', 'Vctrl_required_V',
                  'screening_status', 'reason', 'constraints_json', 'units_json', 'cost_json',
                  'problem_schema_version', 'problem_sha256', 'model_fingerprint', 'source_fingerprint']
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for r in samples:
            writer.writerow({'evidence_id': r['evidence_id'], 'origin': r['origin'], 'parameter_sha256': r['parameter_sha256'],
                'duplicate_of': r.get('duplicate_of'), **values(r['parameters']), 'M1_status': r['M1_status'],
                **{k: r['judgment'][k] for k in ('m1_feasibility', 'all_enabled_specs_status')},
                **{k: r['metrics'].get(k) for k in ('BW_Hz', 'PM_deg', 'UGF_Hz', 'Vctrl_required_V')},
                'screening_status': r['screening']['status'],
                'reason': (r.get('formal_M1_result') or {}).get('reason') or
                          ('M1 budget exhausted' if r['M1_status'] == 'NOT_EVALUATED_M1_BUDGET_EXHAUSTED' else
                           r['screening']['reason'] if r['M1_status'] != 'OK' else ''),
                'constraints_json': json.dumps(r['judgment']['constraints']),
                'units_json': json.dumps({k: v['unit'] for k, v in r['parameters']['values'].items()}),
                'cost_json': json.dumps(r['cost']), **{k: metadata[k] for k in ('problem_schema_version', 'problem_sha256', 'model_fingerprint', 'source_fingerprint')}})
    artifacts = {name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in (
        'problem_resolved.json', 'm1_samples.jsonl', 'candidate_regions.json', 'sensitivity.json', 'feasible_candidates.json')}
    context = {**common, 'schema_version': 'pll-physics-context-1.0', 'summary': summary, 'problem': problem,
               'relations': RELATIONS, 'candidate_regions': regions['regions'], 'sensitivity': derivatives,
               'evidence_artifacts': artifacts, 'evidence_ids': [r['evidence_id'] for r in samples],
               'capability_boundary': {'BW_PM_UGF': 'ideal continuous locked-point M1 only',
                   'tuning': 'static interior condition; no capture implication', 'lock_time_s': 'PENDING_M2',
                   'jitter_s': 'UNSUPPORTED_WITHOUT_FIXED_NOISE_MAPPING', 'M2_executed': False, 'LLM_executed': False,
                   'new_domain_empirically_validated': False, 'whole_regions_certified': False}}
    context['context_sha256'] = fingerprint(context)
    write_new(root/'physics_context.json', context)
    emit('RUN_COMPLETED', action='ExportPhysicsContext', observation=summary,
         decision='Stop at Stage7; no LLM or M2 execution', scientific_sha256=science_sha, evaluation_cost=costs)
    result = {**common, **summary, 'strategy': 'stage7_physics_guided_m1_exploration', 'summary': summary,
              'physics_context': 'physics_context.json'}
    write_new(root/'result.json', result)
    lines = ['# Stage 7 PhysicsExplorationReport', '', f'Problem: `{problem["problem_id"]}` / `{problem["schema_version"]}`',
             f'Status: **{status}**. Seed: {metadata["seed"]}.', '',
             f'Model fingerprint: `{identity["model_sha256"]}`', f'Source fingerprint: `{metadata["source_fingerprint"]}`',
             f'Scientific digest: `{science_sha}`', '',
             f'Exploration feasible candidates: {len(feasible)}; regions: {len(regions["regions"])}.',
             f'Formal M1 calls: {costs["M1_calls"]}; algebra calls: {costs["analytic_calls"]}; duplicates: {counts["duplicates"]}.',
             f'Screen rejections: {counts["screen_rejections"]}; seed failures: {counts["seed_failures"]}; M1 failures: {counts["M1_failures"]}; budget skips: {counts["M1_budget_skips"]}.',
             f'Wall: {costs["wall_time_s"]:.6f}s; process CPU: {costs["process_cpu_s"]:.6f}s. LLM=0; M2=0.', '',
             f'Enabled pending/unsupported: {summary["unsupported_or_pending_enabled_specs"]}.',
             'No feasible sample is not an infeasibility proof. Certificates apply only to the declared ideal M1 assumptions.',
             'Regions are search suggestions around measured M1 sample points. Their interiors/corners are not certified.',
             'M1 predictions do not establish capture, periodic PM, jitter, circuit feasibility or full SystemSpec certification.', '',
             '## Representative regions', '']
    for r in regions['regions']:
        lines.append(f'- {r["region_id"]}: {r["representative_evidence_id"]}; BW={r["representative_metrics"]["BW_Hz"]:.9g}Hz; PM={r["representative_metrics"]["PM_deg"]:.9g}deg; tightest={r["tightest_constraint"]["metric"]}.')
    lines.extend(['', '## Evidence and Stage8 interface', '',
        '`m1_samples.jsonl` holds full inputs, formal MappingResult, cheap predictions, reasons and per-Spec margins.',
        '`physics_context.json` includes source fingerprints, formulas, regions, sensitivities, evidence hashes and capability limits.',
        'Read it with `pll_allocation.exploration.load_physics_context(path)`; do not pass this continuous domain to the frozen Stage6B checker.',
        '', f'Failure: {failure}', ''])
    with (root/'stage7_report.md').open('x', encoding='utf-8') as stream:
        stream.write('\n'.join(lines))
    return result


def load_physics_context(path):
    """Validate exported Stage7 evidence for Stage8 without invoking any solver."""
    path = Path(path).resolve()
    context = json.loads(path.read_text(encoding='utf-8'))
    digest = context.pop('context_sha256')
    if context.get('schema_version') != 'pll-physics-context-1.0' or fingerprint(context) != digest:
        raise ValueError('PhysicsContext schema/hash mismatch')
    if context['model']['model_sha256'] != model_identity()['model_sha256']:
        raise ValueError('PhysicsContext M1 model fingerprint mismatch')
    for name, sha in context['evidence_artifacts'].items():
        artifact = (path.parent/name).resolve()
        if not artifact.is_relative_to(path.parent) or hashlib.sha256(artifact.read_bytes()).hexdigest() != sha:
            raise ValueError('PhysicsContext evidence binding mismatch: ' + name)
    context['context_sha256'] = digest
    return context
