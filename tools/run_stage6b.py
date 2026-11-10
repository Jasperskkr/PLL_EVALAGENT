"""Experiment driver; all studies invoke the sole formal pipeline entry."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from pll_allocation.allocation.core import read,write_new


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',required=True)
    parser.add_argument('--frozen',default='experiments/stage6b/frozen_02');args=parser.parse_args()
    frozen=Path(args.frozen).resolve();plan=read(frozen/'plan.json')
    for row in plan['sources']:
        if hashlib.sha256((ROOT/row['path']).read_bytes()).hexdigest()!=row['sha256']:
            raise RuntimeError('FROZEN_SOURCE_CHANGED:'+row['path'])
    out=Path(args.out).resolve();out.mkdir(parents=True,exist_ok=False)
    write_new(out/'plan.json',plan);receipts=[]
    for scenario,method in plan['order']:
        name=scenario+'_'+method
        command=[sys.executable,'-B','-m','pll_allocation','pipeline','--multispec',str(frozen/(scenario+'.json')),
            '--method',method,'--out',str(out/'runs'/name),'--evaluation-cache',str(out/'evaluation_cache')]
        before=time.perf_counter();at=datetime.now(timezone.utc).isoformat()
        process=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
        (out/(name+'.stdout.txt')).write_text(process.stdout,encoding='utf-8')
        (out/(name+'.stderr.txt')).write_text(process.stderr,encoding='utf-8')
        receipt={'scenario':scenario,'method':method,'argv':command,'started_utc':at,
            'elapsed_s':time.perf_counter()-before,'returncode':process.returncode,'out':str(out/'runs'/name)}
        receipts.append(receipt);write_new(out/(name+'.receipt.json'),receipt)
        print(json.dumps(receipt),flush=True)
        if process.returncode:break
    write_new(out/'receipt.json',{'runs':receipts,'all_six_complete':len(receipts)==6 and all(r['returncode']==0 for r in receipts)})
    return 0 if len(receipts)==6 and all(r['returncode']==0 for r in receipts) else 2

if __name__=='__main__':raise SystemExit(main())
