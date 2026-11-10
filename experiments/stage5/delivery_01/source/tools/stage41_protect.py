"""Read-only inventory/backup of the pre-existing workspace; never alters old files."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def git(*args, root=ROOT):
    return subprocess.check_output(['git', '-C', str(root), *args]).decode('utf-8', errors='replace').strip()


def main(out):
    out = Path(out); out.mkdir(parents=True, exist_ok=False)
    rows = []
    for p in sorted(ROOT.rglob('*')):
        rel = p.relative_to(ROOT)
        if not p.is_file() or any(x in ('.git', '__pycache__', '.pytest_cache', '.venv') for x in rel.parts):
            continue
        if 'stage4_1' in rel.parts:
            continue
        rows.append({'path': rel.as_posix(), 'bytes': p.stat().st_size, 'sha256': sha(p)})
    record = {'HEAD': git('rev-parse', 'HEAD'), 'branch': git('branch', '--show-current'),
              'status': git('status', '--porcelain=v1'),
              'track_b_HEAD': git('rev-parse', 'HEAD', root=ROOT/'track_b'),
              'track_b_status': git('status', '--porcelain=v1', root=ROOT/'track_b'), 'files': rows}
    (out/'inventory.json').write_text(json.dumps(record, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    names = ['.gitignore', 'README.md', 'docs/DECISIONS.md', 'docs/PROJECT_STATUS.md',
             'pll_allocation/pipeline.py', 'UGF_PM_MEASUREMENT_METHOD.md', 'UGF_PM_VALIDATION_REPORT.md']
    names += [r['path'] for r in rows if r['path'].startswith('docs/stage4/')]
    names += [r['path'] for r in rows if r['path'].startswith(('configs/verification/return_ratio_',
              'pll_allocation/verification/return_ratio', 'pll_allocation/verification/build_return_ratio',
              'tests/verification/test_return_ratio_', 'tools/run_stage4.', 'tools/finalize_stage4.',
              'tools/plot_stage4.', 'tools/audit_stage4.', 'tools/package_stage4.', 'tools/stage4_sideband'))]
    with zipfile.ZipFile(out/'dirty_stage4_source_backup.zip', 'x', zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(set(names)):
            archive.write(ROOT/name, name)
    print(json.dumps({'files': len(rows), 'HEAD': record['HEAD'], 'track_b_status': record['track_b_status'],
                      'backup_sha256': sha(out/'dirty_stage4_source_backup.zip')}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--out', required=True)
    main(parser.parse_args().out)
