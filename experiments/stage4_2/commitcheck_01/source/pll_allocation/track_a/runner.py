"""First official candidate is frozen on disk before independent final M1/M2 handoff."""
from __future__ import annotations
from copy import deepcopy
import platform
import sys
import time
from pathlib import Path
from .agent import MessagesPolicy, MockPolicy, run_agent
from .allocate import allocate, perturbation_check
from .core import Meter, assess_m1, file_manifest, fingerprint, proposal, read, target_experiment, write_new


def run_first(model, system_spec, strategy, out, config, *, seed=23):
    target_experiment(model, system_spec)
    if config['M2_budget'] != 0 or config['formal_submissions'] != 1:
        raise ValueError('Track A first-shot runner requires one formal submission and M2 budget zero')
    root = Path(out).resolve()
    root.mkdir(parents=True, exist_ok=False)
    write_new(root/'input_system_spec.json', system_spec)
    write_new(root/'block_space_snapshot.json', model)
    write_new(root/'topology_snapshot.json', model['topology'])
    runtime_paths = sorted(Path(__file__).parent.glob('*.py'))
    runtime_paths += [Path(__file__).parents[1]/'physics_mapping'/'model.py', Path(__file__).parents[1]/'block_space'/'contracts.py']
    source_manifest = file_manifest(runtime_paths, 'runtime source identity')
    write_new(root/'source_manifest.json', source_manifest)
    meter = Meter(config['cheap_budget'], config['M1_budget'])
    baseline_hash, target_hash = fingerprint(model), fingerprint(system_spec)
    start = time.perf_counter()
    candidate, meta, assessment, exported = None, {}, None, None
    status = 'NO_CANDIDATE'
    allocation_cost, assessment_cost = None, None
    try:
        if strategy in ('mock_agent', 'llm_agent'):
            policy = MockPolicy() if strategy == 'mock_agent' else MessagesPolicy(config['llm'], root/'llm_calls', meter)
            candidate, meta = run_agent(deepcopy(model), deepcopy(system_spec), meter, root, policy)
        else:
            candidate, meta = allocate(strategy, deepcopy(model), deepcopy(system_spec), meter, seed)
        generation_elapsed = time.perf_counter() - start
        allocation_cost = deepcopy(meter.counts)
        if candidate is not None:
            write_new(root/'initial_joint_block_spec.json', candidate)
            write_new(root/'first_submission.json', {'candidate_sha256': fingerprint(candidate),
                'first_shot_definition': 'No current-target M2 feedback; cheap/M1 design calls counted separately',
                'cost_before_final_assessment': deepcopy(meter.counts), 'M2_calls': 0})
            assessment = assess_m1(model, system_spec, candidate, meter)
            assessment_cost = {k: meter.counts[k] - allocation_cost[k] for k in meter.counts}
            status = assessment['judgment']['verdict']
            exported = proposal(model, system_spec, candidate, strategy, assessment, meta,
                                root.parent.name+'-'+root.name+'-'+fingerprint(candidate)[:12])
            write_new(root/'AllocationProposal.json', exported)
            try:
                stress = (perturbation_check(model, system_spec, candidate, meter)
                          if meter.cheap_limit-meter.counts['analytic_calls'] >= 16 else
                          {'status': 'SKIPPED_REMAINING_CHEAP_BUDGET', 'rows': [], 'scope': 'post-selection diagnostic'})
            except Exception as error:
                stress = {'status': 'DIAGNOSTIC_FAILED', 'error_type': type(error).__name__,
                          'reason': str(error), 'rows': []}
            write_new(root/'perturbation_diagnostic.json', stress)
        else:
            status = meta.get('status', 'NO_CANDIDATE')
    except Exception as error:
        generation_elapsed = time.perf_counter() - start
        status = 'FAILED'
        meta.update(error_type=type(error).__name__, reason=str(error))
    if fingerprint(model) != baseline_hash or fingerprint(system_spec) != target_hash:
        raise RuntimeError('INPUT_MUTATED')
    if file_manifest(runtime_paths, 'runtime source identity') != source_manifest:
        raise RuntimeError('RUNTIME_SOURCE_CHANGED')
    write_new(root/'cost_events.json', meter.events)
    summary = {'schema_version': 'track-a-first-shot-result-1.0', 'strategy': strategy, 'status': status,
        'parameter_sha256': fingerprint(candidate) if candidate else None,
        'candidate': candidate, 'metadata': meta, 'cost': meter.counts,
        'allocation_cost': allocation_cost, 'formal_assessment_cost': assessment_cost,
        'cost_scope': 'cost includes post-selection 16-corner stress; allocation_cost excludes final M1 and stress',
        'candidate_generation_elapsed_s': generation_elapsed, 'total_elapsed_s': time.perf_counter() - start,
        'assessment': assessment, 'margins': exported['constraint_margins'] if exported else None,
        'budget': {k: config[k] for k in ('cheap_budget', 'M1_budget', 'M2_budget', 'formal_submissions')},
        'environment': {'python': sys.version, 'platform': platform.platform()},
        'M2_status': 'NOT_EVALUATED', 'verified_joint_block_spec': False,
        'official_first_candidate_saved': candidate is not None,
        'LLM_performance': 'MOCK_NOT_LLM' if strategy == 'mock_agent' else 'REAL_REQUESTS_ONLY' if strategy == 'llm_agent' else 'NOT_APPLICABLE'}
    write_new(root/'result.json', summary)
    return summary
