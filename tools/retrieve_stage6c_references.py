"""Read-only primary-source retrieval; retain HTTP failures without claiming review."""
import hashlib
import json
from pathlib import Path
import urllib.request
ROOT=Path(__file__).resolve().parents[1]
URLS={
    'kundert_noise_jitter':'https://designers-guide.org/analysis/PLLnoise%2Bjitter.pdf',
    'kundert_modeling':'https://designers-guide.org/forum/Attachments/PLLjitter.pdf',
    'hanumolu2004':'https://doi.org/10.1109/TCSI.2004.834516',
    'homayoun2016':'https://doi.org/10.1109/TCSI.2016.2537823',
    'wang2022':'https://doi.org/10.1002/cta.3211',
    'zou2006':'https://doi.org/10.1145/1146909.1146919',
    'scipy_welch':'https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.welch.html'}
if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--out',required=True);args=parser.parse_args()
    out=Path(args.out);out.mkdir(parents=True,exist_ok=False);records=[]
    for key,url in URLS.items():
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'PLL-behavioral-research/1.0'})
            with urllib.request.urlopen(req,timeout=18) as resp:
                data=resp.read(8_000_000);ctype=resp.headers.get('Content-Type','');actual=resp.url
            path=out/(key+('.pdf' if data.startswith(b'%PDF') else '.html'))
            with path.open('xb') as f:f.write(data)
            records.append(dict(id=key,url=url,actual_url=actual,content_type=ctype,bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),
                path=path.name,status='RETRIEVED_NOT_YET_REVIEWED'))
        except Exception as error:records.append(dict(id=key,url=url,status='UNAVAILABLE',reason=type(error).__name__+': '+str(error)))
        with (out/'progress.json').open('w',encoding='utf-8') as f:json.dump(records,f,indent=2)
    with (out/'receipt.json').open('x',encoding='utf-8') as f:json.dump(records,f,indent=2)
