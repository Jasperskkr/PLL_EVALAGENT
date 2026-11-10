from __future__ import annotations
import argparse
import json
from .benchmark import benchmark
from .core import load_model, read
from .runner import run_first


def main():
    parser = argparse.ArgumentParser(description='Track A M1-only physics-guided allocation')
    parser.add_argument('command', choices=['run', 'benchmark'])
    parser.add_argument('--model', default='configs/BLOCK_SPACE_MODEL_V1.json')
    parser.add_argument('--plan', default='configs/track_a/benchmark_plan.json')
    parser.add_argument('--target', help='separate SystemSpec JSON; omission uses official snapshot')
    parser.add_argument('--strategy', default='analytical', choices=['nominal', 'analytical', 'sensitivity_optimization', 'random', 'mock_agent', 'llm_agent'])
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    if args.command == 'benchmark':
        benchmark(args.model, args.plan, args.out)
    else:
        model, plan = load_model(args.model), read(args.plan)
        target = read(args.target) if args.target else model['experiment']['system_spec']
        result = run_first(model, target, args.strategy, args.out, plan, seed=plan['random_seed'])
        print(json.dumps({k: result[k] for k in ('status', 'strategy', 'cost', 'metadata')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
