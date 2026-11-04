from __future__ import annotations
import argparse
from datetime import datetime
import json
from pathlib import Path
from .contracts import ContractError, canonical
from .policies import RulePolicy, GridPolicy, RandomPolicy, ReplayPolicy, LLMPolicy, FeedbackSearchPolicy
from .runner import run
from .behavioral import write_json

def read(path):
    value=json.loads(Path(path).read_text(encoding='utf-8-sig'))
    canonical(value)
    return value

def make_policy(name,out,*,seed=0,llm_config=None,replay=None):
    if name=='rule': return RulePolicy()
    if name=='grid': return GridPolicy()
    if name=='random': return RandomPolicy(seed)
    if name=='feedback': return FeedbackSearchPolicy()
    if name in {'llm_initial','llm_feedback'}:
        return LLMPolicy(read(llm_config or 'configs/llm_env.json'),Path(out)/'llm_calls')
    if name=='replay' and replay: return ReplayPolicy(replay)
    raise ValueError('invalid policy or missing replay path')

def main():
    parser=argparse.ArgumentParser(description='Behavioral joint PLL BlockSpec allocation')
    sub=parser.add_subparsers(dest='command',required=True)
    single=sub.add_parser('run')
    single.add_argument('--problem',required=True); single.add_argument('--out',required=True)
    single.add_argument('--policy',choices=['rule','grid','random','feedback','llm_initial','llm_feedback','replay'],default='rule')
    single.add_argument('--budget',type=int,default=30); single.add_argument('--max-attempts',type=int)
    single.add_argument('--seed',type=int,default=0); single.add_argument('--llm-config'); single.add_argument('--replay')
    suite=sub.add_parser('suite')
    suite.add_argument('--out',required=True); suite.add_argument('--budget',type=int,default=30)
    suite.add_argument('--cases',nargs='+',default=['regular80','tight80','finite_domain80','joint84','unsupported_jitter80'])
    suite.add_argument('--policies',nargs='+',default=['rule','grid','random']); suite.add_argument('--seed',type=int,default=0)
    args=parser.parse_args()
    try:
        if args.command=='run':
            policy=make_policy(args.policy,args.out,seed=args.seed,llm_config=args.llm_config,replay=args.replay)
            result=run(read(args.problem),policy,args.out,budget=1 if args.policy=='llm_initial' else args.budget,
                       max_attempts=1 if args.policy=='llm_initial' else args.max_attempts)
            print(json.dumps({'status':result['status'],'metrics':result['metrics'],'out':str(Path(args.out).resolve())},ensure_ascii=False))
        else:
            out=Path(args.out); out.mkdir(parents=True,exist_ok=False); rows=[]
            for case in args.cases:
                for name in args.policies:
                    folder=out/f'{case}__{name}'
                    policy=make_policy(name,folder,seed=args.seed)
                    result=run(read('examples/'+case+'.json'),policy,folder,budget=1 if name=='llm_initial' else args.budget)
                    rows.append({'case':case,'policy':name,'status':result['status'],'metrics':result['metrics']})
                    print(case,name,result['status'],result['metrics']['behavioral_evaluations'],flush=True)
            summary={'rows':rows,'budget':args.budget,'seed':args.seed,'created_at':datetime.now().astimezone().isoformat(),
                     'llm_initial_budget_semantics':'one-shot experimental arm; one candidate only; compare separately from repair/search'}
            write_json(out/'suite_summary.json',summary)
        return 0
    except (ContractError,ValueError,FileExistsError,KeyError) as error:
        print(json.dumps({'status':'INPUT_OR_OUTPUT_ERROR','detail':str(error)},ensure_ascii=False))
        return 2

if __name__=='__main__': raise SystemExit(main())
