"""Bind the exact native binary to the unchanged kernel source. No silent fallback."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def identities(build_dir=None):
    build = Path(build_dir) if build_dir is not None else HERE/'build'
    return {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in
            [('kernel.cpp', HERE/'kernel.cpp'), ('build/kernel.dll', build/'kernel.dll')]}


def check_build(build_dir=None):
    build = Path(build_dir) if build_dir is not None else HERE/'build'
    saved = json.loads((build/'identity.json').read_text(encoding='utf-8'))
    if saved['sha256'] != identities(build):
        raise RuntimeError('NATIVE_SOURCE_OR_BINARY_BINDING_MISMATCH: rebuild and record identity')
    return saved


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--build-dir', type=Path, default=HERE/'build')
    args = parser.parse_args()
    with (args.build_dir/'identity.json').open('x', encoding='utf-8') as stream:
        json.dump({'sha256': identities(args.build_dir), 'compiler': 'MSVC C++17 /O2 /EHsc /LD',
                   'origin': 'explicit build or audited byte-identical Track B DLL'}, stream, indent=2)
