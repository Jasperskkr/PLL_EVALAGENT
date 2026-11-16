"""Isolated HTTP worker so the policy can enforce a total process deadline."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

def save(path,value): Path(path).write_text(json.dumps(value,ensure_ascii=False,allow_nan=False),encoding='utf-8')

def main():
    parser=argparse.ArgumentParser()
    for flag in ('request','config','response','status'): parser.add_argument('--'+flag,required=True)
    parser.add_argument('--redacted-body', help='Agent: preserve HTTP body with credential removed, without redirects')
    args=parser.parse_args()
    config=json.loads(Path(args.config).read_text(encoding='utf-8'))
    body=Path(args.request).read_bytes()
    base=os.environ[config.get('base_url_env','ANTHROPIC_BASE_URL')].rstrip('/')
    if not base.endswith('/v1'): base+='/v1'
    key=os.environ[config.get('api_key_env','ANTHROPIC_AUTH_TOKEN')]
    def redact(text):
        return text.replace(key, '[REDACTED]').replace(json.dumps(key)[1:-1], '[REDACTED]')
    def safe_json(value):
        if isinstance(value, str): return redact(value)
        if isinstance(value, list): return [safe_json(item) for item in value]
        if isinstance(value, dict): return {redact(k): safe_json(v) for k,v in value.items()}
        return value
    if args.redacted_body:
        url = urllib.parse.urlsplit(base)
        if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment:
            save(args.status, {'status':'INVALID_ENDPOINT', 'real_network_call':False, 'http_status':None})
            return 1
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *unused, **ignored): return None
        open_request = urllib.request.build_opener(NoRedirect).open
    else:
        open_request = urllib.request.urlopen
    headers={'Content-Type':'application/json','anthropic-version':'2023-06-01'}
    bearer=config.get('auth_mode','bearer')=='bearer'
    headers['Authorization' if bearer else 'x-api-key']='Bearer '+key if bearer else key
    state={'status':'CONNECTING','real_network_call':True,'http_status':None}
    save(args.status,state)
    request=urllib.request.Request(base+'/messages',data=body,headers=headers,method='POST')
    try:
        with open_request(request,timeout=config.get('timeout_s',60)) as response:
            state.update(status='READING_RESPONSE',http_status=response.status); save(args.status,state)
            raw=response.read()
        if args.redacted_body:
            Path(args.redacted_body).write_text(redact(raw.decode('utf-8', errors='replace')),encoding='utf-8')
        parsed=json.loads(raw.decode('utf-8'))
        save(args.response,safe_json(parsed) if args.redacted_body else parsed)
        state['status']='RESPONDED'; save(args.status,state)
        return 0
    except urllib.error.HTTPError as e:
        state.update(status='SERVICE_UNAVAILABLE',http_status=e.code,error_type='HTTPError')
        if args.redacted_body:
            try:
                Path(args.redacted_body).write_text(redact(e.read(65536).decode('utf-8',errors='replace')),encoding='utf-8')
            except (OSError, TimeoutError):
                pass
    except (urllib.error.URLError,TimeoutError,OSError,ValueError) as e:
        state.update(status='SERVICE_UNAVAILABLE',error_type=type(e).__name__)
    save(args.status,state)
    return 1

if __name__=='__main__': raise SystemExit(main())
