"""Compact source/research review snapshot; raw waveforms stay local with SHA manifests."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.audit_stage4 import credential_values

EXT = {'.py', '.cpp', '.cmd', '.json', '.csv', '.m', '.md', '.txt', '.toml', '.yaml', '.yml'}


def paths_in(folder, suffixes=EXT):
    return [p for p in folder.rglob('*') if p.is_file() and p.suffix in suffixes
            and not any(x in ('.git', '__pycache__', '.pytest_cache', 'raw', 'tmp', 'source')
                        or x.startswith('build') for x in p.relative_to(folder).parts[:-1])]


def sources():
    paths = []
    for folder in ('pll_allocation', 'configs', 'tests', 'tools', 'data', 'examples'):
        paths.extend(paths_in(ROOT/folder))
    paths += list(ROOT.glob('*.md'))+[ROOT/'pyproject.toml', ROOT/'docs/stage3a1/migration_manifest.json']
    paths += paths_in(ROOT/'docs/stage4_2')+paths_in(ROOT/'docs/stage4_1')
    for name in ('summary.json', 'coupling_and_sensitivity.json'):
        paths.append(ROOT/'experiments/stage4_2/readiness_05'/name)
    paths.append(ROOT/'experiments/stage3a1_llm_retry_20261104_01/AllocationProposal.json')
    return sorted(set(paths))


def prepare(out):
    out = Path(out); out.mkdir(parents=True, exist_ok=False)
    records = []
    for path in sources():
        rel = path.relative_to(ROOT); dest = out/'source'/rel
        dest.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(path, dest)
        records.append({'path': rel.as_posix(), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    (out/'source_hashes.json').write_text(json.dumps(records, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'files': len(records), 'source': str((out/'source').resolve())}))


def package(out):
    out = Path(out)
    if out.exists() or out.with_suffix('.zip.sha256').exists():
        raise FileExistsError('refuse overwrite')
    paths = sources()
    paths += paths_in(ROOT/'experiments/stage4_1/final_summary_01')
    paths += paths_in(ROOT/'experiments/stage4_1/figures_02', EXT|{'.pdf', '.svg', '.png'})
    for name in ('analysis_02', 'execution_audit', 'protection_after', 'failures',
                 'tests_initial', 'tests_development', 'tests_preholdout', 'tests_final', 'track_b_tests'):
        paths += paths_in(ROOT/'experiments/stage4_1'/name, EXT|{'.xml', '.log'})
    for name in ('C09_holdout', 'C10_holdout'):
        paths += paths_in(ROOT/'experiments/stage4_1/holdout_01'/name/'steps')
    paths += list((ROOT/'experiments/stage4_1').glob('verifier*receipt.json'))
    paths += [ROOT/'experiments/stage4_1/holdout_lock.json', ROOT/'experiments/stage4_1/holdout_01/holdout_lock_used.json']
    paths += paths_in(ROOT/'experiments/stage4_1/rebuild_01', {'.log', '.xml'})
    paths += [ROOT/'experiments/stage4_1/rebuild_01/verifier_rebuild_receipt.json',
              ROOT/'experiments/stage4_1/rebuild_01/source_hashes.json']
    blobs = {}; secrets = credential_values()
    for p in sorted(set(paths)):
        data = p.read_bytes(); rel = p.relative_to(ROOT).as_posix()
        if any(v in data for v in secrets):
            raise ValueError('credential match, export blocked: '+rel)
        if p.suffix in {'.npz', '.dll', '.obj', '.lib', '.exp'}:
            raise ValueError('excluded raw/binary: '+rel)
        blobs[rel] = data
    manifest = {'schema_version': 'stage4_1-review-snapshot-0.1',
        'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip(),
        'branch': 'codex/stage4-1-engineering-validation',
        'baseline_stage3a1': '47afcb72011636e838b03d81cf91bcec49744a77',
        'stage4_2_commit': '66c4ddb3a2cf075a03c21e19a1a0eccbf69462e3',
        'stage4_checkpoint': '7270f31', 'holdout_execution_commit': '6f93a5fc9247a3094a5b294346959c92f2b242bd',
        'formal_PM_UGF': 'UNKNOWN', 'full_periodic_PM_certified': False,
        'scope': 'source checkout review snapshot, not wheel/PDK/multi-platform release',
        'raw_policy': 'NPZ retained locally; paths/bytes/SHA256 in execution_audit/raw_and_artifact_hashes.json',
        'excluded': ['large raw waveforms', 'DLL/OBJ/LIB', 'caches', 'credentials', 'Git database', 'duplicate old studies'],
        'reproduction': 'docs/stage4_1/RUN_AND_REPRODUCE.md', 'secret_scan': 'PASS'}
    blobs['STAGE4_1_REVIEW_MANIFEST.json'] = (json.dumps(manifest, indent=2)+'\n').encode()
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(blobs.items())}
    blobs['SHA256SUMS.json'] = (json.dumps(hashes, indent=2)+'\n').encode()
    with zipfile.ZipFile(out, 'x', zipfile.ZIP_DEFLATED, compresslevel=7) as archive:
        for name, data in sorted(blobs.items()):
            archive.writestr(name, data)
    with zipfile.ZipFile(out) as archive:
        assert archive.testzip() is None
        for name, expected in hashes.items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == expected
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    out.with_suffix('.zip.sha256').write_text(digest+'  '+out.name+'\n', encoding='ascii')
    print(json.dumps({'bundle': str(out.resolve()), 'files': len(blobs), 'bytes': out.stat().st_size,
                      'sha256': digest, 'all_member_hashes_verified': True, 'secret_scan': 'PASS'}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare'); group.add_argument('--out'); args = parser.parse_args()
    prepare(args.prepare) if args.prepare else package(args.out)
