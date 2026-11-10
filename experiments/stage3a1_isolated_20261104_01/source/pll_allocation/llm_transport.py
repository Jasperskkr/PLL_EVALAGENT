"""Isolated HTTP worker so the policy can enforce a total process deadline."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import urllib.error
import urllib.request

def save(path,value): Path(path).write_text(json.dumps(value,ensure_ascii=False,allow_nan=False),encoding='utf-8')

def main():
    parser=argparse.ArgumentParser()
    for flag in ('request','config','response','status'): parser.add_argument('--'+flag,required=True)
    args=parser.parse_args()
    config=json.loads(Path(args.config).read_text(encoding='utf-8'))
    body=Path(args.request).read_bytes()
    base=os.environ[config.get('base_url_env','ANTHROPIC_BASE_URL')].rstrip('/')
    if not base.endswith('/v1'): base+='/v1'
    key=os.environ[config.get('api_key_env','ANTHROPIC_AUTH_TOKEN')]
    headers={'Content-Type':'application/json','anthropic-version':'2023-06-01'}
    bearer=config.get('auth_mode','bearer')=='bearer'
    headers['Authorization' if bearer else 'x-api-key']='Bearer '+key if bearer else key
    state={'status':'CONNECTING','real_network_call':True,'http_status':None}
    save(args.status,state)
    request=urllib.request.Request(base+'/messages',data=body,headers=headers,method='POST')
    try:
        with urllib.request.urlopen(request,timeout=config.get('timeout_s',60)) as response:
            state.update(status='READING_RESPONSE',http_status=response.status); save(args.status,state)
            raw=response.read()
        parsed=json.loads(raw.decode('utf-8'))
        save(args.response,parsed)
        state['status']='RESPONDED'; save(args.status,state)
        return 0
    except urllib.error.HTTPError as e:
        state.update(status='SERVICE_UNAVAILABLE',http_status=e.code,error_type='HTTPError')
    except (urllib.error.URLError,TimeoutError,OSError,ValueError) as e:
        state.update(status='SERVICE_UNAVAILABLE',error_type=type(e).__name__)
    save(args.status,state)
    return 1

if __name__=='__main__': raise SystemExit(main())
