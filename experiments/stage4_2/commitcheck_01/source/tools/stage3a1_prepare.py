"""Create a reviewable pre-migration backup and real M1 baseline; no old writes."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pll_allocation.track_a.core import Meter, assess_m1, load_model, write_new
from pll_allocation.track_a.allocate import allocate


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    out = ROOT/'docs/stage3a1/pre_migration'
    out.mkdir(parents=True, exist_ok=False)
    state = {name: {key: subprocess.check_output(['git', '-C', str(folder), *args], text=True).strip()
        for key, args in [('head', ['rev-parse', 'HEAD']), ('branch', ['branch', '--show-current']),
                          ('status', ['status', '--short']), ('index', ['diff', '--cached', '--name-status'])]}
        for name, folder in [('main', ROOT), ('track_b', ROOT/'track_b')]}
    write_new(out/'git_before.json', state)
    protected = []
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in ('.git', '__pycache__', '.pytest_cache', '.venv', 'stage3a1')
                   and not d.startswith('stage3a1_')]
        for name in files:
            path = Path(base)/name
            protected.append({'path': path.relative_to(ROOT).as_posix(), 'sha256': sha(path), 'bytes': path.stat().st_size})
    write_new(out/'protected_before.json', protected)
    selected = []
    with zipfile.ZipFile(out/'working_tree_backup.zip', 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for row in protected:
            path = ROOT/row['path']
            if (path.suffix.lower() in ('.py', '.cpp', '.cmd', '.json', '.jsonl', '.md', '.toml', '.yaml', '.txt', '.csv', '.xml')
                    and (path.relative_to(ROOT).parts[0] in ('pll_allocation', 'configs', 'tests', 'tools', 'docs', 'data', 'examples')
                         or len(path.relative_to(ROOT).parts) == 1)) or row['path'] == '.gitignore':
                archive.write(path, row['path'])
                selected.append(row)
    write_new(out/'backup_manifest.json', {'zip_sha256': sha(out/'working_tree_backup.zip'), 'files': selected,
        'excluded': 'historical trajectories, nested .git, caches, virtual environments, ZIP packages and credentials'})
    request = Path(r'C:\Users\Lenovo\.codex\attachments\696816b9-b197-4e17-a6ee-9f807a912ef4\已粘贴的文本.txt')
    with (ROOT/'docs/stage3a1/TASK_REQUEST.md').open('xb') as stream:
        stream.write(request.read_bytes())
    model = load_model(ROOT/'configs/BLOCK_SPACE_MODEL_V1.json')
    spec = model['experiment']['system_spec']
    baseline = ROOT/'experiments/stage3a1_baseline_20261104_01'
    baseline.mkdir(parents=True, exist_ok=False)
    rows = []
    for strategy in ('nominal', 'analytical', 'sensitivity_optimization', 'random'):
        meter = Meter()
        candidate, metadata = allocate(strategy, model, spec, meter, 23)
        write_new(baseline/(strategy+'_candidate.json'), candidate)
        assessment = assess_m1(model, spec, candidate, meter)
        row = {'strategy': strategy, 'candidate': candidate, 'assessment': assessment,
               'metadata': metadata, 'cost': meter.counts}
        rows.append(row)
    write_new(baseline/'M1_baseline.json', rows)
    write_new(baseline/'binding.json', {'model_file_sha256': sha(ROOT/'configs/BLOCK_SPACE_MODEL_V1.json'),
        'protocol_file_sha256': sha(ROOT/'configs/verification/protocol_v1_1.json'),
        'kernel_sha256': sha(ROOT/'pll_allocation/verification/kernel.cpp'),
        'source': 'Actual pre-migration calls to track_a.allocate and core.assess_m1; not historical replay'})
    print(json.dumps({'protected_files': len(protected), 'backup_files': len(selected),
        'backup_zip_sha256': sha(out/'working_tree_backup.zip'), 'M1_baseline_cases': len(rows)}))


if __name__ == '__main__':
    main()
