"""Stage4.2 existing-work protection and final read-only audit; no Git mutation."""
from concurrent.futures import ThreadPoolExecutor
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True, encoding='utf-8').strip()


def snapshot(out):
    out = Path(out); out.mkdir(parents=True, exist_ok=False)
    paths = sorted(p for p in ROOT.rglob('*') if p.is_file()
        and not set(p.relative_to(ROOT).parts) & {'.git', '__pycache__', '.pytest_cache', 'tmp'}
        and not any(x.startswith(('stage4_2', 'stage4.2')) for x in p.relative_to(ROOT).parts)
        and p.name != 'audit_stage4_2.py')
    write(out/'git_before.json', {'head': git('rev-parse','HEAD'), 'branch': git('branch','--show-current'),
          'status': git('status','--short'), 'staged': git('diff','--cached','--name-only'),
          'nested_track_b_head': git('-C','track_b','rev-parse','HEAD'),
          'nested_track_b_status': git('-C','track_b','status','--short')})
    backups = out/'dirty_source_backup'; backups.mkdir()
    for name in ('.gitignore','README.md','docs/DECISIONS.md','docs/PROJECT_STATUS.md','pll_allocation/pipeline.py'):
        target = backups/name; target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT/name).read_bytes())
    def record(p):
        return {'path': p.relative_to(ROOT).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha(p)}
    with ThreadPoolExecutor(max_workers=8) as pool:
        records = list(pool.map(record, paths))
    write(out/'protected_before.json', records)
    print(json.dumps({'protected_files':len(records),'bytes':sum(x['bytes'] for x in records),'git_head':git('rev-parse','HEAD')}))


def verify(before, out):
    out = Path(out); out.mkdir(parents=True, exist_ok=False)
    records = json.loads((Path(before)/'protected_before.json').read_text(encoding='utf-8'))
    permitted = {'docs/DECISIONS.md','docs/PROJECT_STATUS.md'}
    def check(row):
        p = ROOT/row['path']; actual = sha(p) if p.is_file() else None
        return None if actual == row['sha256'] else {**row,'actual_sha256':actual,'authorized_append':row['path'] in permitted}
    with ThreadPoolExecutor(max_workers=8) as pool:
        changes = [r for r in pool.map(check,records) if r]
    append_ok = all((ROOT/name).read_bytes().startswith((Path(before)/'dirty_source_backup'/name).read_bytes()) for name in permitted)
    old = json.loads((Path(before)/'git_before.json').read_text(encoding='utf-8'))
    nested_ok = git('-C','track_b','rev-parse','HEAD') == old['nested_track_b_head'] and git('-C','track_b','status','--short') == old['nested_track_b_status']
    passed = all(c['authorized_append'] for c in changes) and append_ok and nested_ok
    result = {'protected_files':len(records),'unchanged_files':len(records)-len(changes),'changes':changes,
              'stage4_dirty_sources_preserved':True if passed else None,'existing_stage_records_retained_as_prefix':append_ok,
              'nested_track_b_unchanged':nested_ok,'passed':passed}
    write(out/'protection.json',result)
    print(json.dumps(result))
    return 0 if passed else 1


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--snapshot');p.add_argument('--before');p.add_argument('--out',required=True);a=p.parse_args()
    if a.snapshot: snapshot(a.out)
    else: raise SystemExit(verify(a.before,a.out))
