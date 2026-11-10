import argparse
import json
from .validation import run_validation


def main():
    parser=argparse.ArgumentParser(description='Forward validation of Behavioral Block Space v1; refuses overwrite')
    parser.add_argument('--model',required=True)
    parser.add_argument('--out',required=True)
    parser.add_argument('--skip-event',action='store_true')
    args=parser.parse_args()
    print(json.dumps(run_validation(args.model,args.out,event_tb=not args.skip_event),indent=2,ensure_ascii=False))


if __name__=='__main__':
    main()
