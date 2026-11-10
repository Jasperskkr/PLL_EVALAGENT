"""Read-only formal dependency and unchanged implementation checks."""
from __future__ import annotations
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def audit(root=ROOT):
    root = Path(root)
    package = root/'pll_allocation'
    paths = [package/'pipeline.py', package/'pipeline_contracts.py']
    for name in ('allocation', 'verification', 'physics_mapping', 'block_space'):
        paths.extend(sorted((package/name).glob('*.py')))
    violations = []
    imports = []
    for path in paths:
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
    manifest = json.loads((root/'docs/stage3a1/migration_manifest.json').read_text(encoding='utf-8'))
    preserved = []
    for row in manifest:
        if row['destination'].startswith('pll_allocation/allocation/'):
            actual = hashlib.sha256((root/row['destination']).read_bytes()).hexdigest()
            preserved.append({'file': row['destination'], 'sha256': actual,
                              'byte_identical': actual == row['source_sha256'] == row['destination_sha256']})
    return {'formal_files': len(paths), 'imports': imports, 'violations': violations,
            'allocation_preservation': preserved,
            'passed': not violations and len(preserved) == 6 and all(r['byte_identical'] for r in preserved)}


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
