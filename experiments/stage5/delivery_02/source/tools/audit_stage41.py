"""Verify pre-existing evidence byte protection and enumerate real execution costs."""
from pathlib import Path
import argparse
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from stage41_protect import sha

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pll_allocation.verification.experiments import read, write


def protect(out):
    out = Path(out); out.mkdir(parents=True, exist_ok=False)
    before = read(ROOT/'experiments/stage4_1/protection_before/inventory.json')
    allowed = {'.gitignore', 'README.md', 'docs/DECISIONS.md', 'docs/PROJECT_STATUS.md'}
    changed = []; missing = []; permitted = []
    for row in before['files']:
        p = ROOT/row['path']
        if not p.exists():
            missing.append(row['path'])
        elif sha(p) != row['sha256']:
            (permitted if row['path'] in allowed else changed).append(row['path'])
    status = subprocess.check_output(['git', '-C', str(ROOT/'track_b'), 'status', '--porcelain']).decode().strip()
    head = subprocess.check_output(['git', '-C', str(ROOT/'track_b'), 'rev-parse', 'HEAD']).decode().strip()
    record = {'protected_files': len(before['files']), 'unexpected_changes': changed, 'missing': missing,
              'permitted_documentation_or_ignore_changes': permitted,
              'track_b_HEAD': head, 'track_b_status': status,
              'passed': not changed and not missing and head == before['track_b_HEAD'] and status == before['track_b_status'],
              'preexisting_deleted_ZIPs': ['docs/physics_mapping_stage1.zip', 'docs/stage1_5.zip'],
              'preexisting_deletions_preserved_not_committed': True}
    write(out/'protection.json', record); print(json.dumps(record, indent=2, ensure_ascii=False))


def costs(out):
    out = Path(out); out.mkdir(parents=True, exist_ok=False)
    rows = []; manifests = []
    for foldername in ('anchors_01', 'development_01', 'frequency_refinements_01', 'holdout_01', 'pipeline_regression_01'):
        folder = ROOT/'experiments/stage4_1'/foldername
        cost = {'experiment': foldername, 'native_runs': 0, 'DC_pilots': 0, 'integration_points': 0,
                'native_elapsed_s': 0., 'failure_files': 0}
        for p in sorted(folder.rglob('*')):
            if not p.is_file() or p.suffix not in ('.json', '.npz', '.csv', '.log', '.xml'):
                continue
            manifests.append({'path': p.relative_to(ROOT).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha(p)})
            if p.name == 'failure.json':
                cost['failure_files'] += 1
            if p.suffix == '.json' and (p.name == 'summary.json' or p.name.startswith(('summary_', 'pilot_summary_'))):
                doc = read(p); s = doc.get('summary', {})
                if 'integration_points' in s:
                    cost['native_runs'] += 1; cost['integration_points'] += s['integration_points']
                    cost['native_elapsed_s'] += s.get('native_elapsed_s', s.get('elapsed_s', 0.))
                    cost['DC_pilots'] += int(p.name.startswith('pilot_summary_'))
        if (folder/'run_manifest.json').exists() and (folder/'complete.json').exists():
            start = read(folder/'run_manifest.json').get('started_unix')
            finish = read(folder/'complete.json').get('completed_unix')
            cost['wall_elapsed_s'] = finish-start if start and finish else None
        rows.append(cost)
    totals = {k: sum(row[k] for row in rows) for k in ('native_runs', 'DC_pilots', 'integration_points', 'native_elapsed_s', 'failure_files')}
    tests = []
    for p in (ROOT/'experiments/stage4_1').rglob('tests.xml'):
        node = ET.parse(p).getroot(); suites = list(node.iter('testsuite'))
        tests.append({'path': p.relative_to(ROOT).as_posix(), **{k: sum(int(s.get(k, 0)) for s in suites)
                     for k in ('tests', 'failures', 'errors', 'skipped')},
                     'time_s': sum(float(s.get('time', 0)) for s in suites)})
    write(out/'execution_costs.json', {'experiments': rows, 'totals': totals,
          'new_LLM_calls': 0, 'money_cost': 'NOT_AVAILABLE',
          'cost_scope': 'actual saved native summaries; includes pilots. Tests/rebuild internal calls separate, repeated evidence references not counted',
          'compile_failure_before_M2': 'experiments/stage4_1/failures/build_01.json'})
    write(out/'raw_and_artifact_hashes.json', manifests); write(out/'test_runs.json', tests)
    print(json.dumps({'totals': totals, 'hashed_artifacts': len(manifests), 'test_runs': tests}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--mode', choices=['protect', 'costs'], required=True)
    parser.add_argument('--out', required=True); args = parser.parse_args()
    protect(args.out) if args.mode == 'protect' else costs(args.out)
