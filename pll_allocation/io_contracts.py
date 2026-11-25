"""Strict external JSON inputs and the authoritative public artifact index."""
import hashlib
import json
import math
from pathlib import Path


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError('duplicate JSON key: ' + key)
        result[key] = value
    return result


def _constant(value):
    raise ValueError('non-finite JSON number: ' + value)


def _float(value):
    result = float(value)
    if not math.isfinite(result):
        _constant(value)
    return result


def read_json(path):
    """Reject ambiguous keys and non-finite numbers before contract validation."""
    return json.loads(Path(path).read_text(encoding='utf-8-sig'),
                      object_pairs_hook=_pairs, parse_constant=_constant, parse_float=_float)


def file_identity(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def write_run_manifest(root, result, *, problem_source):
    """Index current inputs, canonical outputs and distinct downstream gates."""
    root = Path(root)
    names = {
        'resolved_problem': 'problem_resolved.json',
        'resolved_allocator': 'allocation_config.json',
        'result': 'allocation_result.json',
        'candidates': 'candidates.json',
        'cost': 'cost_summary.json',
        'report': 'allocation_report.md',
        'downstream_handoff': 'sizing_handoff.json',
    }
    artifacts = {role: {'path': name, 'sha256': file_identity(root / name)['sha256']}
                 for role, name in names.items()}
    manifest = {
        'schema_version': 'pll-run-manifest-2.0',
        'execution_route': result['execution_route'],
        'problem_source': problem_source,
        'inputs': {
            'problem': {'schema_version': 'pll-research-problem-2.0',
                        'source': problem_source, 'resolved': 'problem_resolved.json',
                        'role': 'SystemSpec, six variable domains, fixed integer N and model inputs'},
            'allocator': {'schema_version': result['configuration_schema'],
                          'resolved': 'allocation_config.json',
                          'role': 'Policy mode, candidate targets, M1/M2/LLM budgets and search options'},
        },
        'artifacts': artifacts,
        'handoffs': {
            'm1_to_verification': {
                'path': 'initial/verification_handoff.json',
                'schema_version': 'pll-m1-verification-handoff-2.0',
                'ready_field': 'ready_for_verification',
                'consumer': 'pll_allocation.agent.feedback.load_handoff',
                'role': 'Independently rechecked M1 candidate; M2 has not been certified'},
            'verified_to_sizing': {
                'path': 'sizing_handoff.json', 'schema_version': 'pll-sizing-targets-1.0',
                'candidate_set': '#/candidates',
                'consumer': 'pll_allocation.delivery.validate_sizing_handoff',
                'role': 'Only native supported-M2 passing candidates; an empty list delivers no candidates'},
        },
        'delivery': {'status': result['joint_status'],
                     'candidate_count': result['M2_supported_pass_count'],
                     'target_count': result['m2_target_count'],
                     'target_reached': result['joint_target_reached'],
                     'candidate_set': 'sizing_handoff.json#/candidates',
                     'recommended_candidate': 'allocation_result.json#/recommended_M2_supported',
                     'evidence_scope': 'NATIVE_M2_SUPPORTED_METRICS_ONLY',
                     'FULL_SYSTEMSPEC_CERTIFIED': False},
        'internal_evidence_directories': [name for name in ('initial', 'initial_empty_context', 'verification')
                                          if (root / name).is_dir()],
    }
    with (root / 'run_manifest.json').open('x', encoding='utf-8') as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    return manifest
