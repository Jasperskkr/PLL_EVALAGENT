"""Independent verifier setup: immutable command logs and baseline protection."""
import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent

def write(name, value):
    with (OUT / name).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def sources():
    result = {}
    for folder in ('pll_allocation', 'configs', 'tests'):
        for p in sorted((ROOT / folder).rglob('*')):
            if p.is_file() and not any(x in p.parts for x in ('__pycache__', 'build', 'build_stage4', 'build_stage4_1_r2')):
                result[p.relative_to(ROOT).as_posix()] = {'sha256': sha(p), 'bytes': p.stat().st_size}
    return result

def command(label, argv):
    started = datetime.now(timezone.utc).isoformat()
    start = time.perf_counter()
    with (OUT / (label + '.stdout.txt')).open('xb') as stdout, (OUT / (label + '.stderr.txt')).open('xb') as stderr:
        proc = subprocess.run(argv, cwd=ROOT, stdout=stdout, stderr=stderr, check=False)
    record = {'argv': argv, 'cwd': str(ROOT), 'started_utc': started, 'elapsed_s': time.perf_counter()-start, 'returncode': proc.returncode,
              'stdout': label+'.stdout.txt', 'stderr': label+'.stderr.txt'}
    write(label + '.command.json', record)
    print(json.dumps(record), flush=True)
    return record

before = sources()
write('source_before.json', before)
baseline = json.loads((ROOT/'experiments/stage6b/safety_01/baseline_files.json').read_text(encoding='utf-8'))
write('baseline_source_comparison.json', {'changed': [rel for rel in before if rel in baseline and before[rel]['sha256'] != baseline[rel]['sha256']],
                                         'added': [rel for rel in before if rel not in baseline]})
write('environment.json', {'python': sys.version, 'executable': sys.executable, 'platform': platform.platform(),
                          'dependencies': {name: importlib.metadata.version(name) for name in ('numpy', 'scipy', 'pytest')},
                          'compiler_setup': r'C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat'})
builds = []
for label in ('kernel', 'return_ratio', 'closed_loop'):
    builds.append(command('build_'+label, ['cmd', '/c', 'pll_allocation\\verification\\build_'+label+'.cmd']))
if any(r['returncode'] for r in builds):
    write('receipt.json', {'status': 'BUILD_FAILURE', 'builds': builds})
    raise SystemExit(1)
build_artifacts = {}
for name in ('build', 'build_stage4', 'build_stage4_1_r2'):
    for path in (ROOT/'pll_allocation/verification'/name).glob('*'):
        if path.is_file():
            build_artifacts[path.relative_to(ROOT).as_posix()] = {'sha256': sha(path), 'bytes': path.stat().st_size}
write('build_artifacts.json', build_artifacts)
testdir = ROOT/'experiments/stage6b/pretests_01'
testdir.mkdir(exist_ok=False)
tests = command('pretests', [sys.executable, '-B', '-m', 'pytest', '-q', 'tests', '-p', 'no:cacheprovider',
                            '--basetemp=experiments/stage6b/pretests_01/tmp', '--junitxml=experiments/stage6b/pretests_01/tests.xml'])
after = sources()
write('source_after.json', after)
write('receipt.json', {'status': 'PASS' if tests['returncode'] == 0 else 'TEST_FAILURE', 'builds': builds, 'tests': tests,
                       'changed_during_run': [rel for rel in before if after.get(rel) != before[rel]],
                       'added_during_run': [rel for rel in after if rel not in before],
                       'new_M2_study_candidates': 0, 'new_LLM_calls': 0})
