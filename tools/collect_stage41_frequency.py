"""Adapt already executed six-sweep development receipts; zero new M2 calls."""
from pathlib import Path
import argparse
from run_stage41 import inputs
from run_stage4 import measurement_gate
from pll_allocation.verification.experiments import read, write
from pll_allocation.verification.return_ratio import protocol


def main(development, out):
    out = Path(out); out.mkdir(parents=True, exist_ok=False)
    candidates, _ = inputs()
    for c in candidates[2:8]:
        source = Path(development)/c['candidate_id']/'frequency_result.json'
        runs = read(source)
        if set(runs) != {'base', 'amplitude_half', 'step_half', 'window_double', 'offset_grid', 'independent_clamp'}:
            raise ValueError('requires completed six-sweep receipts; original two-sweep history uses refine_stage41_frequency.py')
        folder = out/c['candidate_id']; folder.mkdir()
        write(folder/'result.json', {'runs': runs, 'measurement_gate': measurement_gate(runs, protocol()),
                                    'source': str(source.resolve()), 'new_M2_calls': 0})
    write(out/'complete.json', {'new_M2_calls': 0})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--development', required=True); parser.add_argument('--out', required=True)
    args = parser.parse_args(); main(args.development, args.out)
