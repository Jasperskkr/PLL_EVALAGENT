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
    """Index canonical outputs only; legacy copies remain internal evidence."""
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
        'schema_version': 'pll-run-manifest-1.0',
        'execution_route': result['execution_route'],
        'problem_source': problem_source,
        'artifacts': artifacts,
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
