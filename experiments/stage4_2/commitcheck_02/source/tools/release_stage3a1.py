"""Build an exact Git-object review bundle after a real clean-export build/test/run."""
from __future__ import annotations
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


def canonical(data):
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def encode(data):
    return (json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+'\n').encode('utf-8')


def included(name):
    if any(part in {'build', 'raw', 'tmp', '__pycache__', '.venv', '.git', 'track_b'} for part in name.split('/')):
        return False
    if name.startswith(('pll_allocation/', 'configs/', 'tests/', 'data/', 'examples/')):
        return Path(name).suffix in {'.py', '.json', '.csv', '.md', '.cmd', '.cpp', '.m', '.yaml'}
    if name.startswith('tools/'):
        return 'stage3a1' in name or name == 'tools/audit_mainline.py'
    if name.startswith(('docs/stage3a/', 'docs/stage3a1/')):
        return Path(name).suffix in {'.md', '.json'}
    if name.startswith('experiments/stage3a1_'):
        return True  # only explicitly audited compact evidence is committed
    return name in {'pyproject.toml', '.gitattributes', '.gitignore', 'README.md',
        'PROJECT_CHARTER.md', 'AGENTS.md', 'MAINLINE_ARCHITECTURE.md', 'INTEGRATION_VALIDATION.md',
        'ARCHIVE_PLAN.md', 'P0_EXISTING_SYSTEM_AUDIT.md', 'P0_MIGRATION_PLAN.md',
        'P0_MODULE_REUSE_MATRIX.md', 'P0_TARGET_ARCHITECTURE.md',
        'docs/PROJECT_STATUS.md', 'docs/DECISIONS.md', 'docs/CORE_THREE_QUESTIONS_REVIEW.md'}


def main(out):
    commit = git('rev-parse', 'HEAD').decode().strip()
    branch = git('branch', '--show-current').decode().strip()
    assert branch == 'codex/stage3a1-mainline-freeze'
    assert not git('diff', '--cached', '--name-only').strip(), 'uncommitted staging exists'
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    source = out/'source'
    source.mkdir()
    names = [n for n in git('ls-tree', '-r', '--name-only', '-z', commit).decode('utf-8').split('\0') if n and included(n)]
    payload = {n: git('cat-file', 'blob', commit+':'+n) for n in names}
    secrets = [os.environ[k].encode() for k in ('ANTHROPIC_AUTH_TOKEN', 'ANTHROPIC_API_KEY', 'OPENAI_API_KEY') if os.environ.get(k)]
    assert not [n for n, data in payload.items() if any(s in data for s in secrets)], 'credential scan failed (values suppressed)'
    for name, data in payload.items():
        target = source/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    assert not (source/'track_b').exists() and not (source/'outputs').exists()
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

    def run(label, command):
        result = subprocess.run(command, cwd=source, capture_output=True, creationflags=flags)
        (out/(label+'.log')).write_bytes(result.stdout+result.stderr)
        if result.returncode:
            raise RuntimeError(label+' failed; see '+str(out/(label+'.log')))
        return {'command': command, 'exit_code': result.returncode}

    build = run('native_build', ['cmd', '/c', str(source/'pll_allocation/verification/build_kernel.cmd')])
    tests = run('tests', [sys.executable, '-m', 'pytest', '-q', 'tests', '-p', 'no:cacheprovider',
        '--basetemp='+str(out/'tmp'), '--junitxml='+str(out/'tests.xml')])
    suites = ET.parse(out/'tests.xml').getroot().iter('testsuite')
    counts = {k: 0 for k in ('tests', 'failures', 'errors', 'skipped')}
    for suite in suites:
        for k in counts:
            counts[k] += int(suite.get(k, 0))
    assert counts == {'tests': 283, 'failures': 0, 'errors': 0, 'skipped': 0}, counts
    end_to_end = run('pipeline', [sys.executable, '-m', 'pll_allocation', 'pipeline', '--strategy', 'analytical',
        '--out', str(out/'analytical')])
    result = json.loads((out/'analytical/result.json').read_text(encoding='utf-8'))
    assert result['status'] == 'M2_PARTIAL_PASS' and result['cost']['native_completed_runs'] == 106
    m2 = json.loads((out/'analytical/attempt_001/BehavioralVerificationResult.json').read_text(encoding='utf-8'))
    old = json.loads(payload['tests/fixtures/verification/analytical_M2_stage3a.json'])
    assert m2['metrics'] == old['metrics'] and m2['constraints'] == old['constraints']
    # The actual compiled/exported source must still match the frozen blobs after all tests.
    assert all((source/n).read_bytes() == data for n, data in payload.items()), 'frozen export mutated'
    for filename in ('native_build.log', 'tests.log', 'tests.xml', 'pipeline.log'):
        payload['release_validation/'+filename] = (out/filename).read_bytes()
    for filename in ('result.json', 'initial_joint_block_spec.json', 'attempt_001/BehavioralVerificationResult.json'):
        payload['release_validation/analytical/'+filename] = (out/'analytical'/filename).read_bytes()
    bindings = json.loads(payload['configs/pipeline_stage3a.json'])['bindings']
    inputs = {n: {'file_sha256': digest(payload[n]), 'canonical_json_sha256': digest(canonical(json.loads(payload[n])))}
        for n in ('configs/BLOCK_SPACE_MODEL_V1.json', 'configs/SYSTEM_SPEC_STAGE1_5.json',
                  'configs/PLL_EQUATION_REGISTRY_V1.json', 'configs/verification/protocol_v1_1.json')}
    manifest = {'schema_version': 'pll-stage3a1-release-1.0', 'git_commit': commit, 'branch': branch,
        'release_assets_are_external_to_commit': True,
        'formal_entry': 'python -m pll_allocation pipeline', 'formal_config': 'configs/pipeline_stage3a.json',
        'bindings': bindings, 'frozen_inputs': inputs,
        'environment': {'python': sys.version, 'platform': platform.platform(),
            'dependencies': {n: importlib.metadata.version(n) for n in ('numpy', 'scipy', 'pytest')},
            'compiler': 'MSVC2022 x64 C++17 /O2 /EHsc /LD'},
        'working_tree_tests': json.loads(payload['docs/stage3a1/final_audit_01/audit.json'])['tests'],
        'release_reproduction': {'source': 'exact frozen Git blobs, no historical Track B/outputs/DLL cache',
            'build': build, 'tests': tests, 'test_counts': counts, 'pipeline': end_to_end,
            'pipeline_status': result['status'], 'native_completed_runs': result['cost']['native_completed_runs'],
            'M2_analytical_metrics_exact': True,
            'native_identity': json.loads((source/'pll_allocation/verification/build/identity.json').read_text(encoding='utf-8'))},
        'known_gaps': ['real LLM autonomous M2 feedback repair', 'M2 PM/UGF certification',
            'strict microHz output-frequency certification', 'noise/jitter/power',
            'multi-seed/multi-target fair comparisons', 'cross-platform native backend', 'wheel/install acceptance'],
        'experiment_scope': {'primary_M2_verifications': 7, 'primary_native_runs': 758, 'real_LLM_requests': 4,
            'LLM_failed_JSON_requests': 1, 'LLM_successful_decisions': 3, 'monetary_cost': None,
            'release_reproduction_native_runs': 106, 'tests_extra_native_runs_excluded': True},
        'excluded': ['large trajectories/raw', 'historical track_b and nested .git', 'build caches/DLL',
            'virtual environments', 'credentials', 'external historical ZIPs', 'pre-migration backup ZIP'],
        'secret_scan': {'credential_values_checked': len(secrets), 'hits': 0},
        'git_files': [{'path': n, 'sha256': digest(payload[n]), 'git_blob': git('rev-parse', commit+':'+n).decode().strip()}
                      for n in names],
        'generated_validation_files': [n for n in payload if n.startswith('release_validation/')]}
    payload['RELEASE_MANIFEST.json'] = encode(manifest)
    sums = {n: digest(data) for n, data in sorted(payload.items())}
    payload['SHA256SUMS.json'] = encode(sums)
    assert not [n for n, data in payload.items() if any(s in data for s in secrets)], 'generated credential scan failed'
    manifest_path, zip_path = ROOT/'RELEASE_MANIFEST.json', ROOT/'stage3a1_review_bundle.zip'
    assert not manifest_path.exists() and not zip_path.exists(), 'release assets already exist; refuse overwrite'
    with manifest_path.open('xb') as stream:
        stream.write(payload['RELEASE_MANIFEST.json'])
    with zipfile.ZipFile(zip_path, 'x', zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(payload.items()):
            archive.writestr(name, data)
    with zipfile.ZipFile(zip_path) as archive:
        assert archive.testzip() is None
        assert all(digest(archive.read(n)) == expected for n, expected in sums.items())
        assert all(archive.read(n) == git('cat-file', 'blob', commit+':'+n) for n in names)
    zip_sha = digest(zip_path.read_bytes())
    with (ROOT/'stage3a1_review_bundle.zip.sha256').open('x', encoding='ascii') as stream:
        stream.write(zip_sha+'  stage3a1_review_bundle.zip\n')
    (out/'publication.json').write_bytes(encode({'git_commit': commit, 'zip_sha256': zip_sha,
        'zip_bytes': zip_path.stat().st_size, 'files': len(payload), 'test_counts': counts,
        'git_files_exact': True, 'all_file_checksums_valid': True}))
    print((out/'publication.json').read_text(encoding='utf-8'))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    main(parser.parse_args().out)
