"""Read-only discovery, source fingerprints and inherited-data provenance audit."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT.parent
PROJECTS = {
    'baseline': 'PLL_SPEC_ALLOC_BASELINE', 'm05_repo': 'PLL_SPEC_ALLOC_M05_REPO',
    'm05': 'PLL_SPEC_ALLOC_M05_WORKTREE', 'm06': 'PLL_SPEC_ALLOC_M06_WORKTREE',
    'm07': 'PLL_SPEC_ALLOC_M07_WORKTREE', 'agent_v2': 'PLL_AGENTV2/PLL_AGENT',
    'agent_v1': 'PLL_AGENT', 'experiment_a': 'PLLngspice_vs_matlab',
    'factor_graph_matlab': 'PLL_Physics_FactorGraph_MATLAB/PLL_Physics_FactorGraph_MATLAB',
    'final_plan': 'PLL_FINAL', 'zou_replication': 'PLL_Zou2006_Replication',
}
SUFFIXES = {'.py', '.m', '.md', '.yaml', '.yml', '.toml', '.inc', '.cir', '.sp', '.json'}
EXCLUDED = {'.git', '.venv', '__pycache__', '.pytest_cache', 'node_modules', 'tmp', 'archive'}
DATA_DIRS = {'runs', 'results', 'data'}

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def git(path, *args):
    result = subprocess.run(['git', '-C', str(path), *args], capture_output=True, text=True, encoding='utf-8')
    return result.stdout.strip() if result.returncode == 0 else None

def inventory():
    projects, sources, data = {}, [], []
    for key, relative in PROJECTS.items():
        path = PARENT / relative
        item = {'path': str(path), 'exists': path.is_dir(), 'git_marker': (path/'.git').exists()}
        if item['git_marker']:
            item.update(head=git(path, 'rev-parse', 'HEAD'), branch=git(path, 'branch', '--show-current'),
                        status=git(path, 'status', '--porcelain'), worktrees=git(path, 'worktree', 'list', '--porcelain'),
                        remotes=git(path, 'remote', '-v'))
        projects[key] = item
        if not path.is_dir():
            continue
        # Source trees only; raw waveforms and secrets are never loaded.
        stack = [path]
        while stack:
            folder = stack.pop()
            for f in folder.iterdir():
                if f.is_dir():
                    if f.name in EXCLUDED:
                        continue
                    if f.name in DATA_DIRS:
                        counts, sizes = Counter(), Counter()
                        for d in f.rglob('*'):
                            if d.is_file():
                                counts[d.suffix.lower()] += 1
                                sizes[d.suffix.lower()] += d.stat().st_size
                        data.append({'project': key, 'path': str(f), 'file_counts': dict(counts), 'bytes': dict(sizes),
                                     'role': 'metadata_only; not loaded into policy'})
                    else:
                        stack.append(f)
                elif f.suffix.lower() in SUFFIXES and f.stat().st_size <= 2_000_000:
                    sources.append({'project': key, 'relative_path': f.relative_to(path).as_posix(),
                                    'path': str(f), 'bytes': f.stat().st_size, 'sha256': sha(f)})
    provenance = []
    baseline = PARENT / PROJECTS['baseline']
    for name in ['fixtures/provenance.json', 'fixtures/feedback/provenance.json']:
        document = json.loads((baseline/name).read_text(encoding='utf-8-sig'))
        roots = {'project': PARENT/PROJECTS['agent_v2'], 'experiment_a': PARENT/PROJECTS['experiment_a']}
        for row in document['sources']:
            path = roots[row['root_id']] / row['relative_path']
            actual = sha(path) if path.is_file() else None
            provenance.append({'manifest': name, 'source_id': row['source_id'], 'path': str(path),
                               'expected': row['sha256'], 'actual': actual,
                               'status': 'MATCH' if actual == row['sha256'] else 'MISSING' if actual is None else 'MISMATCH'})
    return {'audit_schema': 'p0-source-audit-1', 'projects': projects, 'sources': sorted(sources, key=lambda x:x['path']),
            'data_inventory': data, 'provenance_checks': provenance,
            'literal_PLL_AGENT2_exists': (PARENT/'PLL_AGENT2').exists(),
            'literal_PLL_BASELINE_exists': (PARENT/'PLL_BASELINE').exists(),
            'name_resolution': 'PLL_AGENT2 -> observed PLL_AGENTV2/PLL_AGENT; PLL_BASELINE -> observed PLL_SPEC_ALLOC_BASELINE; aliases are documented, not assumed exact identities'}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--compare', type=Path)
    args = parser.parse_args()
    result = inventory()
    if args.compare:
        old = json.loads(args.compare.read_text(encoding='utf-8'))
        previous = {r['path']:r['sha256'] for r in old['sources']}
        current = {r['path']:r['sha256'] for r in result['sources']}
        result['protection'] = {'checked': len(previous), 'changed_or_missing': [p for p,h in previous.items() if current.get(p)!=h],
                                'new_source_paths': sorted(set(current)-set(previous)),
                                'scope': 'audited source files and provenance-linked historical artifacts; raw waveform contents not rehashed'}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps({'projects': len(result['projects']), 'source_files': len(result['sources']),
                      'provenance': dict(Counter(r['status'] for r in result['provenance_checks'])),
                      'out': str(args.out), 'protection': result.get('protection')}, ensure_ascii=False))

if __name__ == '__main__':
    main()
