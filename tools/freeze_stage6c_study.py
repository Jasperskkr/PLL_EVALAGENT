"""Freeze execution-source identity for the existing six-arm study driver."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from pll_allocation.allocation.core import write_new
from pll_allocation.pipeline import source_identity
from pll_allocation.verification.stage6c_identity import check_build,default_build


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args()
    out=Path(a.out);out.mkdir(parents=True,exist_ok=False)
    inputdir=ROOT/'configs/stage6c/joint_frozen_01';names=['J0_ideal','J1_nonideal']
    for name in names:
        data=(inputdir/(name+'.json')).read_bytes()
        with (out/(name+'.json')).open('xb') as f:f.write(data)
    sources={Path(row['path']).relative_to(ROOT).as_posix():row for row in source_identity()}
    extras=list((ROOT/'pll_allocation/verification').glob('*.cpp'))+[ROOT/'tools/generate_stage6c_kernel.py',ROOT/'tools/run_stage6b.py']
    extras.extend(default_build().glob('kernel.dll'));extras.extend(default_build().glob('identity.json'))
    for path in extras:sources[path.relative_to(ROOT).as_posix()]={'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    source_rows=[{'path':k,'sha256':v['sha256']} for k,v in sorted(sources.items())]
    write_new(out/'plan.json',dict(version='stage6c-sixarm-1.0',sources=source_rows,
        order=[[name,method] for name in names for method in ('A','B','C')],budgets='same6candidate96M110000cheap',
        native_build_identity=check_build(),sole_entry='python -m pll_allocation pipeline',
        source_profiles='predeclared and frozen before experiments; no result tuning',
        output_policy='fresh directory; retain UNKNOWN and failures; no automatic master merge'))
