"""Post-process existing handoffs. No allocation, simulation or verdict mutation."""
import argparse
from pathlib import Path

from ..allocation.core import write_new
from .contract import assess_feedback, export_guidance, read_json, validate_source


def main():
    p = argparse.ArgumentParser(description=__doc__)
    commands = p.add_subparsers(dest='command', required=True)
    export = commands.add_parser('export')
    export.add_argument('--handoff', required=True, type=Path)
    export.add_argument('--out', type=Path)
    export.add_argument('--options', type=Path)
    assess = commands.add_parser('assess')
    for name in ('handoff', 'guidance', 'feedback', 'out'):
        assess.add_argument('--'+name, required=True, type=Path)
    assess.add_argument('--options', type=Path, help='Independent original design policy used for export')
    prepare = commands.add_parser('prepare')
    for name in ('handoff', 'guidance', 'feedback', 'problem', 'out'):
        prepare.add_argument('--'+name, required=True, type=Path)
    prepare.add_argument('--options', type=Path, help='Independent original design policy used for export')
    region = commands.add_parser('region')
    region.add_argument('--handoff', required=True, type=Path)
    region.add_argument('--out', required=True, type=Path)
    region.add_argument('--candidate-sha256', required=True)
    region.add_argument('--experiment-id', required=True)
    region.add_argument('--kvco-values', type=float, nargs='+')
    region.add_argument('--vlock-values', type=float, nargs='+')
    region.add_argument('--sample-budget', type=int, default=64)
    region.add_argument('--m1-budget', type=int, default=64)
    region.add_argument('--m2-budget', type=int, default=0)
    region.add_argument('--m2-timeout-s', type=float, default=180)
    region.add_argument('--revalidation-problem', type=Path)
    args = p.parse_args()
    if args.command == 'export':
        export_guidance(args.handoff, args.out, options=read_json(args.options) if args.options else None)
    elif args.command == 'assess':
        write_new(args.out, assess_feedback(read_json(args.feedback), read_json(args.guidance), read_json(args.handoff),
            options=read_json(args.options) if args.options else None, source_handoff_path=args.handoff))
    elif args.command == 'prepare':
        from .revalidation import prepare_revalidation
        write_new(args.out, prepare_revalidation(read_json(args.feedback), read_json(args.guidance),
            read_json(args.handoff), problem=read_json(args.problem),
            options=read_json(args.options) if args.options else None, source_handoff_path=args.handoff))
    else:
        from .region import analyze_vco_acceptance_region
        problem, candidates = validate_source(read_json(args.handoff))
        selected = [c for c in candidates if c['parameter_sha256'] == args.candidate_sha256]
        if len(selected) != 1:
            p.error('--candidate-sha256 must identify exactly one delivered source candidate')
        analyze_vco_acceptance_region(selected[0], problem=problem, out=args.out, experiment_id=args.experiment_id,
            kvco_values=args.kvco_values, vlock_values=args.vlock_values,
            sample_budget=args.sample_budget, m1_budget=args.m1_budget, m2_budget=args.m2_budget,
            m2_timeout_s=args.m2_timeout_s,
            revalidation_problem=read_json(args.revalidation_problem) if args.revalidation_problem else None)


if __name__ == '__main__':
    main()
