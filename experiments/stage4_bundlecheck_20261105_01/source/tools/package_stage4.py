"""Explicit compact review export; no raw NPZ, native binaries, caches or credentials."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.audit_stage4 import PRIMARY, credential_values, read, sha, write

EXCLUDED_PARTS = {'.git', '__pycache__', '.pytest_cache', 'build', 'build_stage4', 'tmp', 'source'}
SOURCE_SUFFIXES = {'.py', '.cpp', '.cmd', '.json', '.csv', '.m', '.md', '.txt', '.toml', '.yml', '.yaml'}


def source_paths():
    paths = []
    for folder in ('pll_allocation', 'configs', 'tests', 'tools', 'data', 'examples'):
        paths.extend(p for p in (ROOT/folder).rglob('*') if p.is_file()
                     and not set(p.relative_to(ROOT).parts) & EXCLUDED_PARTS and p.suffix in SOURCE_SUFFIXES)
    paths.extend(ROOT/name for name in ('pyproject.toml', 'AGENTS.md', 'PROJECT_CHARTER.md',
        'docs/stage3a1/migration_manifest.json',
        'experiments/stage3a1_llm_retry_20261104_01/AllocationProposal.json'))
    return sorted(set(paths))


def prepare(out):
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    entries = []
    for path in source_paths():
        rel = path.relative_to(ROOT)
        target = out/'source'/rel
        target.parent.mkdir(parents=True, exist_ok=True)
        content = path.read_bytes()
        target.write_bytes(content)
        entries.append({'path': rel.as_posix(), 'sha256': hashlib.sha256(content).hexdigest(), 'bytes': len(content)})
    write(out/'prepared_source_hashes.json', entries)
    print(json.dumps({'prepared_files': len(entries), 'source': str(out/'source')}))


def package(out):
    out = Path(out).resolve()
    checksum = out.with_suffix(out.suffix+'.sha256')
    if out.exists() or checksum.exists():
        raise FileExistsError('review export refuses overwrite')
    audit = read(ROOT/'docs/stage4/final_audit_01/summary.json')
    if not audit['passed']:
        raise ValueError('final audit did not pass')
    paths = source_paths()
    paths.extend(ROOT/name for name in ('README.md', 'UGF_PM_MEASUREMENT_METHOD.md', 'UGF_PM_VALIDATION_REPORT.md',
        'frequency_response.csv', 'm1_m2_ugf_pm_comparison.csv', 'docs/DECISIONS.md', 'docs/PROJECT_STATUS.md'))
    paths.extend(p for p in (ROOT/'docs/stage4').rglob('*') if p.is_file() and p.suffix in SOURCE_SUFFIXES)
    for name in PRIMARY:
        paths.extend(p for p in (ROOT/'experiments'/name).rglob('*') if p.is_file() and p.suffix in {'.json', '.jsonl', '.md'})
    for folder in sorted((ROOT/'experiments').glob('stage4_*')):
        if folder.name in PRIMARY:
            continue
        if 'figures' in folder.name:
            suffixes = {'.json', '.csv', '.pdf', '.svg', '.png'} if folder.name.endswith('_02') else {'.json'}
        else:
            suffixes = {'.json', '.xml', '.log', '.md', '.csv'}
        paths.extend(p for p in folder.rglob('*') if p.is_file() and p.suffix in suffixes
                     and not set(p.relative_to(folder).parts) & EXCLUDED_PARTS)
    blobs = {}
    secrets = credential_values()
    for path in sorted(set(paths)):
        rel = path.relative_to(ROOT).as_posix()
        if set(Path(rel).parts) & EXCLUDED_PARTS:
            raise ValueError('excluded path selected: '+rel)
        content = path.read_bytes()
        if any(value in content for value in secrets):
            raise ValueError('credential match in selected export; path='+rel)
        blobs[rel] = content
    manifest = {'schema_version': 'stage4-review-manifest-1.0',
        'baseline_commit': '47afcb72011636e838b03d81cf91bcec49744a77',
        'branch': 'codex/stage4-ugf-pm', 'stage4_commit': None,
        'release_scope': 'working-tree review snapshot; Stage3A.1 release assets unchanged',
        'scientific_status': 'UGF / PM M2 MEASUREMENT NOT YET VALIDATED',
        'authoritative_summary': 'experiments/stage4_summary_20261105_05',
        'authoritative_pipeline': 'experiments/stage4_pipeline_feedback_20261105_03',
        'historical_note': 'earlier study formal_values are historical numerical-gate diagnostics, superseded by null/UNKNOWN extensions',
        'partial_failed_JSON': 'stage4_summary_20261105_01 retained as failed postprocessing evidence; not authoritative',
        'raw_waveforms': 'excluded; retained locally with paths/size/SHA256 in final_audit_01/experiment_file_hashes.json',
        'binary_and_cache_policy': 'DLL/OBJ/LIB/build/.git/venv/NPZ excluded; compile fresh Windows MSVC binaries',
        'dependencies': 'preinstalled Python/NumPy/SciPy/pytest; matplotlib for plotting; MSVC2022 x64 for build',
        'reproduction_scope': 'source checkout entry points; wheel installation and other platforms NOT_VERIFIED',
        'tests': '300 mainline + 28 original Track B; fresh-source verification separately recorded',
        'files': len(blobs)}
    blobs['STAGE4_REVIEW_MANIFEST.json'] = (json.dumps(manifest, ensure_ascii=False, indent=2)+'\n').encode()
    hashes = {name: hashlib.sha256(content).hexdigest() for name, content in sorted(blobs.items())}
    blobs['SHA256SUMS.json'] = (json.dumps(hashes, ensure_ascii=False, indent=2)+'\n').encode()
    with zipfile.ZipFile(out, 'x', zipfile.ZIP_DEFLATED, compresslevel=7) as archive:
        for name, content in sorted(blobs.items()):
            archive.writestr(name, content)
    with zipfile.ZipFile(out) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == set(hashes) | {'SHA256SUMS.json'}
        for name, expected in hashes.items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == expected, name
        assert json.loads(archive.read('SHA256SUMS.json')) == hashes
    checksum.write_text(sha(out)+'  '+out.name+'\n', encoding='ascii')
    print(json.dumps({'bundle': str(out), 'bytes': out.stat().st_size, 'entries': len(blobs),
                      'per_file_hashes_verified': len(hashes), 'secret_scan': 'PASS', 'sha256': sha(out)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare', type=Path)
    group.add_argument('--out', type=Path)
    args = parser.parse_args()
    prepare(args.prepare) if args.prepare else package(args.out)
