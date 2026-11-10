"""Delivery checks: original-file protection, proposal ingestion and repeatability."""
from __future__ import annotations
import argparse
from pathlib import Path
from .benchmark import check_protection
from .core import load_model, read, validate_proposal, write_new


def audit(model_path, before_path, first, second, llm, out):
    model = load_model(model_path)
    first, second, llm = Path(first), Path(second), Path(llm)
    a, b = read(first/'all_results.json'), read(second/'all_results.json')
    decisions = lambda rows: {(r['target_id'], r['strategy']): (r['parameter_sha256'], r['status']) for r in rows}
    identical = decisions(a) == decisions(b)
    checked = []
    for folder in (first, second, llm):
        for path in folder.rglob('AllocationProposal.json'):
            validate_proposal(model, read(path))
            checked.append(str(path))
    result = {'protected': check_protection('.', read(before_path)),
        'repeatability': {'cases': len(a), 'identical_candidate_hash_and_verdict': identical,
                          'wall_time_compared': False, 'reason': 'one timing sample, import/cache effects; counts are primary'},
        'proposal_ingestion': {'validated_count': len(checked), 'paths': checked},
        'real_llm': {'executed': True, 'result': str(llm/'result.json'),
            'calls': len(read(llm/'result.json')['metadata']['LLM_calls']), 'replayed': False},
        'M2_calls': 0, 'verified_joint_block_spec': False}
    result['accepted'] = result['protected']['all_unchanged'] and identical
    write_new(out, result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    print(audit('configs/BLOCK_SPACE_MODEL_V1.json', 'docs/track_a/protected_before.json',
        'outputs/track_a_benchmark_20261104_01', 'outputs/track_a_benchmark_20261104_02',
        'outputs/track_a_llm_20261104_01', args.out)['accepted'])
