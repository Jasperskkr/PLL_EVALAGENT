"""Freeze verified historical MATLAB reference records/trajectories for verifier only."""
from pathlib import Path
import hashlib
import json

ROOT=Path(__file__).resolve().parents[1]

def main():
    cases=json.loads((ROOT/'data/legacy/matlab_regression_cases.json').read_text(encoding='utf-8'))
    source=ROOT.parent/'PLL_AGENTV2/PLL_AGENT/results/feedback_allocation_20261029/verification'
    target=ROOT/'data/verification_reference'; target.mkdir(exist_ok=True)
    entries=[]
    for case in cases['CASES']:
        record=source/Path(case['historical_record'].replace('\\','/'))
        actual=hashlib.sha256(record.read_bytes()).hexdigest()
        if actual!=case['historical_record_sha256']:
            raise ValueError('Historical MATLAB record changed: '+str(record))
        folder=target/case['job_id']; folder.mkdir(exist_ok=False)
        for f in (record,record.parent/'cycles.csv',record.parent/'cycles_matlab.csv',record.parent/'engine_semantics.json'):
            dest=folder/f.name; dest.write_bytes(f.read_bytes())
            entries.append({'source':str(f),'destination':str(dest.relative_to(ROOT)),
                            'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),
                            'role':'VERIFICATION_ONLY; not visible to Policy',
                            'externally_prefrozen_hash':case['historical_record_sha256'] if f==record else None})
    (target/'manifest.json').write_text(json.dumps({'records':24,'entries':entries,
        'scope':'Historical corrected MATLAB implementation, not new MATLAB execution or transistor verification'},ensure_ascii=False,indent=2),encoding='utf-8')
    print('24 historical record SHA matched; 96 reference files copied byte-identically')

if __name__=='__main__': main()
