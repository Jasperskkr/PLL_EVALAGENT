"""New full Pipeline experiments and explicit pre/post migration comparisons."""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pll_allocation.pipeline import run_pipeline
from pll_allocation.allocation.core import read, write_new


def equal(a, b):
    if isinstance(a, dict):
        return isinstance(b, dict) and a.keys() == b.keys() and all(equal(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return isinstance(b, list) and len(a) == len(b) and all(equal(x, y) for x, y in zip(a, b))
    if type(a) in (int, float) and type(b) in (int, float):
        return math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12)
    return a == b


def main(out):
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    baseline = {r['strategy']: r for r in read(ROOT/'experiments/stage3a1_baseline_20261104_01/M1_baseline.json')}
    rows = []
    for strategy in ('nominal', 'analytical', 'sensitivity_optimization', 'random', 'llm_agent'):
        folder = out/strategy
        result = run_pipeline(folder, strategy)
        row = {'strategy': strategy, 'status': result['status'], 'cost': result['cost'], 'failure': result['failure']}
        if not result['attempts']:
            row['verification'] = 'NOT_VERIFIED_NO_CANDIDATE'
        else:
            m1 = read(folder/'attempt_001/M1_prediction.json')
            m2 = read(folder/'attempt_001/BehavioralVerificationResult.json')
            candidate = read(folder/'initial_joint_block_spec.json')
            row.update(M1=m1['prediction']['metrics'], M2=m2['metrics'], constraints=m2['constraints'],
                       overall_status=m2['overall_status'], prediction_errors=m2['prediction_errors'])
            if strategy in baseline:
                old = read(ROOT/f'tests/fixtures/verification/{strategy}_M2_stage3a.json')
                row.update(candidate_exact=candidate == baseline[strategy]['candidate'],
                    M1_assessment_exact=m1 == baseline[strategy]['assessment'],
                    M2_metrics_exact=m2['metrics'] == old['metrics'],
                    M2_metrics_tolerance=equal(m2['metrics'], old['metrics']),
                    M2_constraints_exact=m2['constraints'] == old['constraints'],
                    M2_overall_exact=m2['overall_status'] == old['overall_status'])
                assert all(row[k] for k in ('candidate_exact', 'M1_assessment_exact', 'M2_metrics_tolerance',
                                            'M2_constraints_exact', 'M2_overall_exact')), row
            assert not result['full_behavioral_pass'] and m2['overall_status'] in ('UNKNOWN', 'FAIL')
            assert m2['metrics']['PM_deg']['value'] is None and m2['metrics']['UGF_Hz']['value'] is None
        rows.append(row)
        print(json.dumps({'strategy': strategy, 'status': result['status'], 'cost': result['cost']}), flush=True)
    repair = run_pipeline(out/'feedback_repair', 'random', m2_budget=2, repair_budget=1)
    assert [a['stage'] for a in repair['attempts']] == ['FIRST_SHOT', 'FEEDBACK_REPAIR']
    assert [a['M2_status'] for a in repair['attempts']] == ['M2_FAIL', 'M2_PARTIAL_PASS']
    assert repair['feedback_received_by_agent'] and not repair['full_behavioral_pass']
    write_new(out/'equivalence.json', {'numeric_comparison_tolerance': {'relative': 1e-12, 'absolute': 1e-12},
        'scope': 'metrics/constraints only; timestamps, IDs and measured timing costs excluded; no acceptance thresholds changed',
        'runs': rows, 'repair': repair})
    print('NEW_EXPERIMENTS_AND_EQUIVALENCE_COMPLETE', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    main(parser.parse_args().out)
