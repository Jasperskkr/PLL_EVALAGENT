"""Export source without history/build caches, build unchanged native source, run all formal tests."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main(out):
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    source = out/'source'
    source.mkdir()
    for name in ('pll_allocation', 'configs', 'tests', 'data', 'examples'):
        shutil.copytree(ROOT/name, source/name, ignore=shutil.ignore_patterns('__pycache__', '.pytest_cache', 'build'))
    for name in ('pyproject.toml', 'tools/audit_mainline.py', 'docs/stage3a1/migration_manifest.json'):
        target = source/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/name, target)
    files = [{'path': p.relative_to(source).as_posix(), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
             for p in sorted(source.rglob('*')) if p.is_file()]
    (out/'source_manifest.json').write_text(json.dumps(files, indent=2), encoding='utf-8')
    build_command = ['cmd', '/c', str(source/'pll_allocation/verification/build_kernel.cmd')]
    build = subprocess.run(build_command, cwd=source, capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
    (out/'native_build.log').write_bytes(build.stdout+build.stderr)
    report = {'build_command': build_command, 'build_exit_code': build.returncode,
        'source_files': len(files), 'track_b_present': (source/'track_b').exists(),
        'historical_outputs_present': (source/'outputs').exists(),
        'native_cache_copied': False, 'cross_platform': 'NOT_VERIFIED_WINDOWS_ONLY'}
    if build.returncode:
        (out/'isolation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        raise RuntimeError('isolated native build failed; see native_build.log')
    report['native_identity'] = json.loads((source/'pll_allocation/verification/build/identity.json').read_text(encoding='utf-8'))
    command = [sys.executable, '-m', 'pytest', '-q', 'tests', '-p', 'no:cacheprovider',
        '--basetemp='+str(out/'tmp'), '--junitxml='+str(out/'tests.xml')]
    result = subprocess.run(command, cwd=source, capture_output=True)
    (out/'tests.log').write_bytes(result.stdout+result.stderr)
    report.update(test_command=command, test_exit_code=result.returncode)
    with (out/'isolation.json').open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps(report, indent=2))
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    main(parser.parse_args().out)
