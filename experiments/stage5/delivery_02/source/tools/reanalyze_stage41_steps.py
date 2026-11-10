"""Reanalyze preserved development trajectories only, no M2 calls or overwritten outputs."""
from pathlib import Path
import argparse
import numpy as np
from run_stage41 import inputs, bindings
from pll_allocation.verification.experiments import read, write
from pll_allocation.verification.closed_loop import analyze, compare_refinements, protocol


def main(development, out):
    out = Path(out); out.mkdir(parents=True, exist_ok=False)
    write(out/'source_bindings.json', bindings())
    candidates, _ = inputs()
    for c in candidates[:8]:
        folder = out/c['candidate_id']; folder.mkdir(); source = Path(development)/c['candidate_id']/'steps'
        def load(name):
            path = source/'raw'/name
            return read(path/'summary.json') | dict(np.load(path/'trajectory.npz'))
        zeros = {name: load('zero_'+name) for name in ('base', 'fine', 'long')}
        results = {}; curves = {}
        for name in ('plus', 'minus', 'double_plus', 'double_minus', 'fine_plus', 'fine_minus', 'long_plus', 'long_minus'):
            run = load(name); zero = zeros['fine' if name.startswith('fine') else 'long' if name.startswith('long') else 'base']
            result, curve = analyze(c['joint_block_spec'], run, zero, protocol()); results[name] = result
            if curve is not None:
                curves[name] = curve
                np.savetxt(folder/(name+'_cycle_response.csv'), curve, delimiter=',',
                           header='time_from_onset_s,input_normalized,M2_observed,M1_prediction', comments='')
            write(folder/(name+'_metrics.json'), result)
        convergence = compare_refinements(results, curves, protocol())
        write(folder/'result.json', {'status': 'MEASURED' if convergence['converged'] else 'UNKNOWN',
              'results': results, 'convergence': convergence, 'no_new_M2_calls': True,
              'raw_source': str(source.resolve()), 'change': 'exact partial-bin integration of piecewise linear records; no criterion change'})
    write(out/'complete.json', {'new_M2_calls': 0, 'candidate_ids': [c['candidate_id'] for c in candidates[:8]]})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--development', required=True); parser.add_argument('--out', required=True)
    args = parser.parse_args(); main(args.development, args.out)
