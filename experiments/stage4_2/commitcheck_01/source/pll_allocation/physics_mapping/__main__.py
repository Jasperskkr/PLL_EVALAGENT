"""python -m pll_allocation.physics_mapping --config <json> --out <new-dir>"""
import argparse
from .validation import run_stage1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    result = run_stage1(args.config, args.out)
    print(result['numerical_acceptance'], args.out)


if __name__ == '__main__':
    main()
