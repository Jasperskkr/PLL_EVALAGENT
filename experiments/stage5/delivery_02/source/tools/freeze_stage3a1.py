"""Protect history, audit evidence and prepare an explicit release staging allowlist."""
from __future__ import annotations
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.audit_mainline import audit
from pll_allocation.pipeline_contracts import load_inputs


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def functions(path):
    return {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(path.read_text(encoding='utf-8')).body
            if isinstance(n, ast.FunctionDef)}


def test_counts(path):
    tree = ET.parse(path)
    suites = list(tree.getroot().iter('testsuite'))
    return {k: sum(int(s.get(k, 0)) for s in suites) for k in ('tests', 'failures', 'errors', 'skipped')}


def selected_files():
    names = {'.gitattributes', '.gitignore', 'README.md', 'MAINLINE_ARCHITECTURE.md',
             'INTEGRATION_VALIDATION.md', 'ARCHIVE_PLAN.md', 'pyproject.toml',
             'docs/DECISIONS.md', 'docs/PROJECT_STATUS.md', 'pll_allocation/cli.py',
             'pll_allocation/pipeline.py', 'pll_allocation/pipeline_contracts.py',
             'tests/test_block_space_v1.py', 'tests/test_pipeline_stage3a.py', 'tests/test_mainline_migration.py',
             'configs/SYSTEM_SPEC_STAGE1_5.json', 'configs/pipeline_stage3a.json'}
    for directory, suffixes in [('pll_allocation/allocation', {'.py'}),
            ('pll_allocation/verification', {'.py', '.cmd', '.cpp'}),
            ('tests/verification', {'.py'}), ('tests/fixtures', {'.json', '.py'}),
            ('configs/verification', {'.json'}), ('data', {'.json', '.csv', '.py', '.md'})]:
        for p in (ROOT/directory).rglob('*'):
            if p.is_file() and p.suffix in suffixes and not {'build', '__pycache__'} & set(p.parts):
                names.add(p.relative_to(ROOT).as_posix())
    for name in ('core', 'physics', 'allocate', 'agent', 'repair', 'feedback_agent'):
        names.add(f'pll_allocation/track_a/{name}.py')
    for p in (ROOT/'tools').glob('*stage3a*.py'):
        names.add(p.relative_to(ROOT).as_posix())
    names.add('tools/audit_mainline.py')
    for p in (ROOT/'docs/stage3a').rglob('*'):
        if p.is_file() and p.suffix in {'.md', '.json'} and p.stat().st_size < 100000:
            names.add(p.relative_to(ROOT).as_posix())
    for p in (ROOT/'docs/stage3a1').rglob('*'):
        if p.is_file() and p.suffix in {'.md', '.json'} and 'release_assets' not in p.parts:
            names.add(p.relative_to(ROOT).as_posix())
    folders = ['stage3a1_baseline_20261104_01', 'stage3a1_pretests_20261104_01',
        'stage3a1_postmigration_tests_20261104_01', 'stage3a1_verificationtests_20261104_01',
        'stage3a1_finaltests_20261104_01', 'stage3a1_finaltests_20261104_02',
        'stage3a1_original_trackb_tests_20261104_01', 'stage3a1_acceptance_20261104_01',
        'stage3a1_llm_retry_20261104_01']
    for folder in folders:
        for p in (ROOT/'experiments'/folder).rglob('*'):
            if p.is_file() and p.suffix in {'.json', '.jsonl', '.xml', '.md'} and not {'raw', 'tmp'} & set(p.parts):
                names.add(p.relative_to(ROOT).as_posix())
    for name in ('source_manifest.json', 'native_build.log', 'tests.xml', 'tests.log', 'isolation.json'):
        names.add('experiments/stage3a1_isolated_20261104_01/'+name)
    return sorted(names)


def main(out):
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    read = lambda p: json.loads(p.read_text(encoding='utf-8'))
    allowed = {'.gitignore', 'README.md', 'docs/DECISIONS.md', 'docs/PROJECT_STATUS.md',
        'MAINLINE_ARCHITECTURE.md', 'pll_allocation/pipeline.py', 'pll_allocation/pipeline_contracts.py',
        'pll_allocation/allocation/__init__.py', 'pll_allocation/verification/build_identity.py',
        'pll_allocation/verification/build_kernel.cmd', 'tests/test_block_space_v1.py', 'tests/test_pipeline_stage3a.py'}
    allowed |= {f'pll_allocation/track_a/{n}.py' for n in ('core', 'physics', 'allocate', 'agent', 'repair', 'feedback_agent')}
    protected = read(ROOT/'docs/stage3a1/pre_migration/protected_before.json')
    changes = []
    for row in protected:
        p = ROOT/row['path']
        actual = sha(p) if p.is_file() else None
        if actual != row['sha256']:
            changes.append({**row, 'after_sha256': actual, 'authorized': row['path'] in allowed})
    assert all(r['authorized'] for r in changes), changes
    track_b = {'head': subprocess.check_output(['git', '-C', str(ROOT/'track_b'), 'rev-parse', 'HEAD'], text=True).strip(),
        'status': subprocess.check_output(['git', '-C', str(ROOT/'track_b'), 'status', '--short'], text=True).strip()}
    assert track_b['head'] == read(ROOT/'docs/stage3a1/pre_migration/git_before.json')['track_b']['head'] and not track_b['status']
    numerical = {'kernel_byte_identical': sha(ROOT/'track_b/kernel.cpp') == sha(ROOT/'pll_allocation/verification/kernel.cpp'),
        'protocol_byte_identical': sha(ROOT/'track_b/protocol_v1_1.json') == sha(ROOT/'configs/verification/protocol_v1_1.json')}
    for name, funcs in [('measure.py', None), ('run_suite.py', ['capture_pair']),
            ('verify.py', ['assemble_result', 'interval_judgment']),
            ('experiments.py', ['response_point', 'response_sweep', 'compare_sweeps'])]:
        old, new = functions(ROOT/'track_b'/name), functions(ROOT/'pll_allocation/verification'/name)
        for fn in funcs or old:
            numerical[name+':'+fn] = old[fn] == new[fn]
    assert all(numerical.values()), numerical
    config, model, spec, protocol = load_inputs()
    files = selected_files()
    secrets = [os.environ[k].encode() for k in ('ANTHROPIC_AUTH_TOKEN', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY') if os.environ.get(k)]
    secret_hits = [name for name in files if any(s in (ROOT/name).read_bytes() for s in secrets)]
    assert not secret_hits, 'secret scan rejected selected files (values suppressed)'
    result = {'protected_files': len(protected), 'unchanged': len(protected)-len(changes),
        'authorized_changes': changes, 'unexpected_changes': [], 'track_b': track_b,
        'numerical_preservation': numerical, 'dependencies': audit(), 'bindings': config['bindings'],
        'tests': {name: test_counts(ROOT/path) for name, path in {
            'pre_migration': 'experiments/stage3a1_pretests_20261104_01/tests.xml',
            'postmigration_failed': 'experiments/stage3a1_postmigration_tests_20261104_01/tests.xml',
            'formal_final': 'experiments/stage3a1_finaltests_20261104_02/tests.xml',
            'original_track_b': 'experiments/stage3a1_original_trackb_tests_20261104_01/tests.xml',
            'isolated_rebuilt': 'experiments/stage3a1_isolated_20261104_01/tests.xml'}.items()},
        'secret_scan': {'selected_files': len(files), 'credential_values_checked': len(secrets), 'hits': 0},
        'staging_files': files, 'staging_total_bytes': sum((ROOT/name).stat().st_size for name in files)}
    for name, obj in [('audit.json', result), ('staging_allowlist.json', files)]:
        with (out/name).open('x', encoding='utf-8') as stream:
            json.dump(obj, stream, ensure_ascii=False, indent=2)
    print(json.dumps({k: result[k] for k in ('protected_files', 'unchanged', 'tests', 'secret_scan', 'staging_total_bytes')}))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    main(parser.parse_args().out)
