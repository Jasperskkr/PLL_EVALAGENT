"""Rebind compatible saved M1 numbers to a new Spec, or explicitly recalibrate."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from ..allocation.core import write_new
from ..exploration import load_physics_context, load_problem, run_exploration
from ..exploration.contracts import active_m1_specs, check_candidate, judge, screen_problem
from ..exploration.regions import candidate_regions
from ..physics_mapping.model import MappingResult, Status, fingerprint


def raw_problem(problem):
    raw = deepcopy(problem)
    raw.pop('problem_sha256', None)
    for spec in raw['specs']:
        spec.pop('support_status', None)
        spec.pop('protocol', None)
    return raw


def prepare_context(context_path, new_problem_path, out, *, calibration_budget):
    """No global repeat on unchanged problems; new numerical work is explicit/capped."""
    context_path, out = Path(context_path).resolve(), Path(out)
    old = load_physics_context(context_path)
    new = load_problem(new_problem_path) if new_problem_path else old['problem']
    accounting = {'mode': 'READ_ONLY_SAVED_CALIBRATION', 'new_M1_calls': 0, 'analytic_calls': 0,
                  'source_context_sha256': old['context_sha256'], 'rejudged_for_new_spec': False}
    if new == old['problem']:
        return context_path, accounting
    compatible = all(new[k] == old['problem'][k] for k in ('topology', 'parameters', 'fixed_parameters'))
    if compatible:
        # Use the official judge and original full MappingResult, never cached old margins.
        out.mkdir(exist_ok=False)
        rows = [json.loads(s) for s in (context_path.parent/'m1_samples.jsonl').read_text(encoding='utf-8').splitlines()]
        formal_by_parameter = {r['parameter_sha256']: r['formal_M1_result'] for r in rows if r.get('formal_M1_result')}
        for row in rows:
            raw = formal_by_parameter.get(row['parameter_sha256'])
            result = MappingResult(**(raw | {'status': Status(raw['status'])})) if raw else None
            row.update(problem_sha256=new['problem_sha256'], problem_id=new['problem_id'],
                       screening=check_candidate(new, row['parameters']), judgment=judge(new, row['parameters'], result),
                       reused_numerical_evidence={'context_sha256': old['context_sha256'], 'evidence_id': row['evidence_id']})
        regions = candidate_regions(new, rows)
        rebound = deepcopy(old)
        rebound.update(problem=new, candidate_regions=regions['regions'])
        rebound['metadata'].update(problem_sha256=new['problem_sha256'], problem_id=new['problem_id'])
        rebound['summary'] = {'status': 'PROVEN_M1_INFEASIBLE' if screen_problem(new)['certificates']
                             else 'REJUDGED_COMPATIBLE_CALIBRATION_EVIDENCE'}
        # Derivatives are numeric metric slopes, independent of changed Spec. Preserve
        # original stencils/scales, drop stale region labels and explicitly explain use.
        for rep in rebound['sensitivity']['representatives']:
            rep['region_id'] = next((r['region_id'] for r in regions['regions']
                                    if r['representative_evidence_id'] == rep['center_evidence_id']), 'REUSED_POINT_SENSITIVITY')
        write_new(out/'problem_resolved.json', {'problem': new})
        write_new(out/'candidate_regions.json', regions)
        write_new(out/'sensitivity.json', rebound['sensitivity'])
        with (out/'m1_samples.jsonl').open('x', encoding='utf-8') as stream:
            for row in rows:
                stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False)+'\n')
        rebound['evidence_artifacts'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()}
        rebound.pop('context_sha256', None)
        rebound['context_sha256'] = fingerprint(rebound)
        write_new(out/'physics_context.json', rebound)
        accounting.update(mode='COMPATIBLE_NUMERICAL_REUSE_REJUDGE_CURRENT_SPEC', rejudged_for_new_spec=True,
                          reused_points=len(rows), old_problem_sha256=old['problem']['problem_sha256'])
        return out/'physics_context.json', accounting
    # Domain/fixed/topology changes cannot reuse old coordinates or samples as seeds.
    # Reuse the existing M1 exploration engine with a separately bounded part of total budget.
    if not active_m1_specs(new) or screen_problem(new)['certificates']:
        # A fresh context is still generated for an explicit current-problem stop.
        needed = 1
    else:
        needed = calibration_budget
    if needed < 1:
        raise ValueError('INCOMPATIBLE_CALIBRATION_REQUIRES_EXPLICIT_POSITIVE_BUDGET')
    result = run_exploration(new_problem_path, out, budget=needed)
    accounting.update(mode='EXPLICIT_NEW_M1_CALIBRATION_INCOMPATIBLE_COORDINATES',
                      new_M1_calls=result['cost']['M1_calls'], analytic_calls=result['cost']['analytic_calls'],
                      original_calibration_scope='Previous calibration not reused; current Spec/domain applied')
    return out/'physics_context.json', accounting
