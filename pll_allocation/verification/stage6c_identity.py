"""Independent optional native identity, retaining original build identity untouched."""
import hashlib
import json
import os
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def default_build():
    return Path(os.environ.get('PLL_STAGE6C_BUILD_DIR',str(HERE/'build_stage6c'))).resolve()


def identities(build=None):
    build=Path(build) if build is not None else default_build()
    paths=[HERE/'kernel.cpp',HERE/'stage6c_kernel.cpp',ROOT/'tools/generate_stage6c_kernel.py',
           HERE/'stage6c_native.py',HERE/'stage6c_identity.py',build/'kernel.dll']
    return {p.relative_to(ROOT).as_posix() if p.is_relative_to(ROOT) else p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def check_build(build=None):
    build=Path(build) if build is not None else default_build()
    saved=json.loads((build/'identity.json').read_text(encoding='utf-8'))
    if saved['sha256']!=identities(build):raise RuntimeError('STAGE6C_NATIVE_SOURCE_OR_BINARY_BINDING_MISMATCH')
    return saved


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--build-dir',type=Path,default=HERE/'build_stage6c');a=parser.parse_args()
    with (a.build_dir/'identity.json').open('x',encoding='utf-8') as f:
        json.dump({'sha256':identities(a.build_dir),'compiler':'MSVC C++17 /O2 /EHsc /LD','rng':'SplitMix64_BoxMuller_1.0'},f,indent=2)
