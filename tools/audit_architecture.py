"""Read-only formal dependency and unchanged implementation checks."""
from __future__ import annotations
import ast
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def audit_names(root=ROOT):
    """Reject phase-based active filenames/imports; versioned evidence is data."""
    root=Path(root)
    receipt=json.loads((root/'configs/provenance/naming_migration.json').read_text(encoding='utf-8'))
    aliases={row['path'] for row in receipt['compatibility_modules']}
    pattern=re.compile(r'(?:stage[_-]?\d|track[_-]?[ab](?:[_.-]|$))', re.I)
    violations=[]
    sources=[p for folder in ('pll_allocation','tools','tests') for p in (root/folder).rglob('*')
             if p.suffix in ('.py','.cpp','.cmd') and '__pycache__' not in p.parts
             and 'fixtures' not in p.parts and not any(part.startswith('build') for part in p.parts[:-1])]
    for path in sources:
        rel=path.relative_to(root).as_posix()
        if rel in aliases or '/_legacy/' in rel:
            continue
        if any(pattern.search(part) for part in path.relative_to(root).parts):
            violations.append({'file':rel,'reason':'phase-based active source path'})
        if path.suffix!='.py':
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if isinstance(node, ast.Import):
                names=[item.name for item in node.names]
            elif isinstance(node, ast.ImportFrom):
                names=[node.module] if node.module else [item.name for item in node.names]
            else:
                continue
            for name in names:
                if pattern.search(name):
                    violations.append({'file':rel,'line':node.lineno,'import':name})
    return {'source_files':len(sources),'compatibility_paths':sorted(aliases),
            'violations':violations,'passed':not violations}


def audit(root=ROOT):
    root = Path(root)
    package = root/'pll_allocation'
    paths = [package/'pipeline.py', package/'pipeline_contracts.py']
    for name in ('allocation', 'verification', 'physics_mapping', 'block_space'):
        paths.extend(sorted((package/name).glob('*.py')))
    violations = []
    imports = []
    for path in paths:
        # Compatibility aliases are excluded from the active dependency graph.
        # Their exact identity is checked separately by release interface tests.
        if path.read_text(encoding='utf-8').startswith('"""Compatibility alias;'):
            continue
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or '']
                for name in names:
                    imports.append({'file': path.relative_to(root).as_posix(), 'module': name})
                    parts = name.split('.')
                    forbidden = {'track_a', 'track_b'}
                    if path.parent.name == 'verification':
                        forbidden |= {'allocation'}
                    if set(parts) & forbidden:
                        violations.append(imports[-1])
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                # Old labels/provenance in strings are valid; old filesystem inputs are not.
                value = node.value.replace('\\', '/')
                if any(value.startswith(p) for p in ('outputs/', 'track_b/', '../track_b/', '../outputs/')):
                    violations.append({'file': path.relative_to(root).as_posix(), 'historical_path': value})
    manifest = json.loads((root/'configs/provenance/allocation_sources.json').read_text(encoding='utf-8'))
    preserved = []
    for row in manifest:
        if row['destination'].startswith('pll_allocation/allocation/'):
            actual = hashlib.sha256((root/row['destination']).read_bytes()).hexdigest()
            preserved.append({'file': row['destination'], 'sha256': actual,
                              'byte_identical': actual == row['source_sha256'] == row['destination_sha256']})
    naming=audit_names(root)
    return {'formal_files': len(paths), 'imports': imports, 'violations': violations,
            'naming':naming,
            'allocation_preservation': preserved,
            'passed': not violations and naming['passed'] and len(preserved) == 6 and all(r['byte_identical'] for r in preserved)}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    result = audit()
    with args.out.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in result.items() if k != 'imports'}))
    raise SystemExit(0 if result['passed'] else 1)
