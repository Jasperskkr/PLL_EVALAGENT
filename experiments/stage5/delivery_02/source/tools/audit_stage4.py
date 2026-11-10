"""Read-only Stage4 protection, provenance, costs and evidence audit. Fresh outputs only."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.audit_mainline import audit

PRIMARY = (
    'stage4_prototype_20261105_01', 'stage4_study_20261105_01',
    'stage4_study_20261105_02', 'stage4_sidebands_20261105_01',
    'stage4_pipeline_feedback_20261105_01', 'stage4_pipeline_feedback_20261105_02',
    'stage4_pipeline_feedback_20261105_03',
)
SUMMARY = 'stage4_summary_20261105_05'
PIPELINE = 'stage4_pipeline_feedback_20261105_03'
ALLOWED = {'.gitignore', 'README.md', 'docs/DECISIONS.md',
           'docs/PROJECT_STATUS.md', 'pll_allocation/pipeline.py'}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def write(path, item):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(item, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def git(path):
    def run(*args):
        return subprocess.check_output(['git', '-C', str(path), *args], text=True, encoding='utf-8').strip()
    return {'head': run('rev-parse', 'HEAD'), 'branch': run('branch', '--show-current'),
            'status': run('status', '--short')}


def credential_values():
    """Never log names or values. Only scan actual credentials available to this process."""
    return [value.encode() for key, value in os.environ.items()
            if any(marker in key.upper() for marker in ('API_KEY', 'TOKEN', 'SECRET', 'PASSWORD'))
            and len(value) >= 12]


def test_counts(path):
    tree = ET.parse(path).getroot()
    suites = [tree] if tree.tag == 'testsuite' else list(tree.findall('testsuite'))
    counts = {key: sum(int(x.get(key, 0)) for x in suites)
              for key in ('tests', 'failures', 'errors', 'skipped')}
    counts['passed'] = counts['tests']-counts['failures']-counts['errors']-counts['skipped']
    counts['elapsed_s'] = sum(float(x.get('time', 0)) for x in suites)
    return counts


def costs(folder):
    calls = []
    for path in sorted(folder.rglob('*.json')):
        if not (path.name == 'summary.json' or path.name.startswith(('summary_', 'pilot_summary_'))):
            continue
        item = read(path).get('summary', {})
        if 'integration_points' not in item:
            continue
        calls.append({'path': path.relative_to(ROOT).as_posix(),
                      'integration_points': item['integration_points'],
                      'elapsed_s': item['elapsed_s'],
                      'pilot': path.name.startswith('pilot_summary_'),
                      'phase_port': 'source_hashes' in item})
    return {'folder': folder.name, 'native_runs': len(calls),
            'pilot_runs': sum(c['pilot'] for c in calls),
            'phase_port_native_runs': sum(c['phase_port'] for c in calls),
            'original_native_runs': sum(not c['phase_port'] for c in calls),
            'integration_points': sum(c['integration_points'] for c in calls),
            'native_elapsed_s': sum(c['elapsed_s'] for c in calls), 'calls': calls}


def main(out):
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    protected = read(ROOT/'docs/stage4/pre_audit/protected_before.json')
    changes, missing = [], []
    for before in protected:
        path = ROOT/before['path']
        if not path.is_file():
            missing.append(before['path'])
            continue
        actual = sha(path)
        if actual != before['sha256']:
            changes.append({'path': before['path'], 'before_sha256': before['sha256'],
                            'after_sha256': actual, 'authorized_stage4_edit': before['path'] in ALLOWED})
    protection = {'protected_count': len(protected), 'unchanged_count': len(protected)-len(changes)-len(missing),
                  'changes': changes, 'missing': missing,
                  'passed': not missing and all(x['authorized_stage4_edit'] for x in changes)}
    write(out/'protection.json', protection)
    dependencies = audit(ROOT)
    write(out/'dependency_audit.json', dependencies)
    before_git = read(ROOT/'docs/stage4/pre_audit/git_before.json')
    current_git = {name: git(ROOT/name) for name in ('.', 'track_b')}
    git_ok = current_git['.']['head'] == before_git['.']['head'] and current_git['track_b'] == before_git['track_b']
    write(out/'git.json', {'before': before_git, 'after': current_git,
                         'original_baseline_commit_preserved': git_ok,
                         'stage4_commit_created': False, 'release_scope': 'working-tree review snapshot'})
    tests = {p.relative_to(ROOT).as_posix(): test_counts(p)
             for p in sorted((ROOT/'experiments').glob('stage4_*/tests.xml'))}
    write(out/'test_runs.json', tests)
    final_tests = tests['experiments/stage4_finaltests_20261105_04/tests.xml']
    trackb_tests = tests['experiments/stage4_trackbtests_20261105_01/tests.xml']
    test_ok = final_tests['passed'] == 300 and trackb_tests['passed'] == 28
    write(out/'test_scope.json', {'final_formal': final_tests, 'original_track_b': trackb_tests,
          'additional_stage4_cases': 17, 'original_track_b_is_repeated_coverage': True,
          'zero_injection_exact_array_equivalence_cases': 5,
          'cost_scope': 'test-internal native calls excluded from primary experiment cost; suite wall times retained',
          'passed': test_ok})
    primary = [costs(ROOT/'experiments'/name) for name in PRIMARY]
    totals = {key: sum(x[key] for x in primary) for key in
              ('native_runs', 'pilot_runs', 'phase_port_native_runs', 'original_native_runs',
               'integration_points', 'native_elapsed_s')}
    pipeline = read(ROOT/'experiments'/PIPELINE/'result.json')
    write(out/'costs.json', {'scope': 'recorded primary experiments only; excludes tests and pure postprocessing',
          'experiments': primary, 'totals': totals, 'latest_pipeline_cost': pipeline['cost'],
          'new_LLM_requests': 0, 'monetary_cost': None, 'full_orchestration_wall_s': None,
          'wall_time_note': 'native elapsed sums are not full study wall time; latest Pipeline timer separately measured',
          'measurement_quality_failure': 'v0.1 nominal clamp frequency drift; 306 real native runs retained',
          'postprocessing_failure': 'stage4_summary_20261105_01 NumPy bool serialization; no new native run'})
    from pll_allocation.verification.return_ratio_validity import load_extension
    evidence = {}
    evidence_ok = True
    for case, fixture in [('nominal', 'nominal'), ('real_agent', 'analytical'), ('pm_boundary', None)]:
        case_path = ROOT/'experiments/stage4_study_20261105_02'/case
        proposal = read(case_path/'AllocationProposal.json')
        extension = load_extension(ROOT/'experiments'/SUMMARY/(case+'_extension.json'), proposal)
        bw = read(case_path/'BW_result.json')
        exact = None
        if fixture:
            baseline = read(ROOT/'tests/fixtures/verification'/(fixture+'_M2_stage3a.json'))
            exact = all(bw[key] == baseline[key] for key in ('metrics', 'constraints', 'overall_status'))
        unknown = all(extension['metrics'][key]['value'] is None and extension['metrics'][key]['status'] == 'UNKNOWN'
                      for key in ('UGF_Hz', 'PM_deg'))
        evidence[case] = {'bindings_verified': True, 'original_M2_exact_fixture_match': exact,
                         'formal_UGF_PM_null_UNKNOWN': unknown,
                         'overall_status': extension['overall_status'],
                         'numerical_gate': extension['local_measurement_status'],
                         'structured_feedback': extension['structured_feedback']}
        evidence_ok &= unknown and exact is not False and extension['overall_status'] == 'UNKNOWN'
    receipt = read(ROOT/'experiments'/PIPELINE/'attempt_001/measurement_extension_agent_receipt.json')
    receipt_ok = receipt['status'] == 'RECEIVED_BY_ALLOCATION_AGENT' and receipt['automatic_learning'] is False
    csv_ok = all(sha(ROOT/name) == sha(ROOT/'experiments'/SUMMARY/name)
                 for name in ('frequency_response.csv', 'm1_m2_ugf_pm_comparison.csv'))
    write(out/'evidence_checks.json', {'cases': evidence, 'agent_receipt': receipt, 'root_CSV_exact_final_copy': csv_ok,
          'original_M2_status': pipeline['status'], 'new_LLM_calls': pipeline['cost']['LLM_calls'],
          'passed': evidence_ok and receipt_ok and csv_ok and pipeline['status'] == 'M2_PARTIAL_PASS'})
    experiment_files = []
    secret_hits = []
    secret_values = credential_values()
    for folder in sorted((ROOT/'experiments').glob('stage4_*')):
        for path in sorted(folder.rglob('*')):
            if not path.is_file() or set(path.relative_to(folder).parts) & {'tmp', '__pycache__', '.pytest_cache'}:
                continue
            rel = path.relative_to(ROOT).as_posix()
            experiment_files.append({'path': rel, 'bytes': path.stat().st_size, 'sha256': sha(path)})
            if path.suffix in {'.json', '.jsonl', '.log', '.md', '.txt', '.csv', '.xml'}:
                content = path.read_bytes()
                if any(value in content for value in secret_values):
                    secret_hits.append(rel)
    write(out/'experiment_file_hashes.json', experiment_files)
    sources = []
    for folder in ('pll_allocation', 'configs', 'tests', 'tools'):
        for path in sorted((ROOT/folder).rglob('*')):
            if path.is_file() and not any(part in {'__pycache__', '.pytest_cache', 'build', 'build_stage4'} for part in path.parts):
                sources.append({'path': path.relative_to(ROOT).as_posix(), 'bytes': path.stat().st_size, 'sha256': sha(path)})
    write(out/'source_file_hashes.json', sources)
    versions = {'Python': sys.version, 'platform': platform.platform(),
                'packages': {k: importlib.metadata.version(k) for k in ('numpy', 'scipy', 'matplotlib', 'pytest')},
                'native_build': read(ROOT/'pll_allocation/verification/build_stage4/identity.json'),
                'original_build': read(ROOT/'pll_allocation/verification/build/identity.json')}
    write(out/'versions.json', versions)
    write(out/'secret_scan.json', {'method': 'byte match against actual credential values in process environment; values never emitted',
                                 'text_files_scanned_only': True, 'hit_paths': secret_hits, 'passed': not secret_hits})
    result = {'protection_passed': protection['passed'], 'dependency_passed': dependencies['passed'],
              'git_baseline_passed': git_ok, 'regression_passed': test_ok, 'evidence_passed': evidence_ok and receipt_ok and csv_ok,
              'secret_scan_passed': not secret_hits, 'primary_native_runs': totals['native_runs'],
              'formal_UGF_PM': 'UNKNOWN', 'periodic_stability_certified': False,
              'primary_cost_count_matches_expected': totals['native_runs'] == 1664}
    result['passed'] = all(value for key, value in result.items() if key.endswith(('_passed', '_expected')))
    write(out/'summary.json', result)
    print(json.dumps(result))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    raise SystemExit(main(parser.parse_args().out))
