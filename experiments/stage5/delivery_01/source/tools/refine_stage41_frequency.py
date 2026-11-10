"""Complete unchanged Stage4 convergence suite for C03-C08; no holdout access."""
from pathlib import Path
import argparse
from run_stage41 import inputs, bindings, frequency_variants
from run_stage4 import measurement_gate
from pll_allocation.verification.experiments import read, write
from pll_allocation.verification.return_ratio import sweep, protocol


def main(development, out):
    out = Path(out); out.mkdir(parents=True, exist_ok=False)
    write(out/'source_bindings.json', bindings())
    candidates, _ = inputs(); doc = protocol()
    for c in candidates[2:8]:
        folder = out/c['candidate_id']; folder.mkdir()
        previous = read(Path(development)/c['candidate_id']/'frequency_result.json')
        runs = {'base': previous['series'], 'independent_clamp': previous['clamp']}
        for name, mode, amp, dt, cycles, grid in frequency_variants(doc)[1:5]:
            runs[name] = sweep(folder/'raw'/name, c['joint_block_spec'], mode=mode,
                               amplitude=amp, dt=dt, cycles=cycles, grid=grid, doc=doc)
        write(folder/'result.json', {'runs': runs, 'measurement_gate': measurement_gate(runs, doc),
              'existing_base_reference': str((Path(development)/c['candidate_id']).resolve()),
              'reused_runs_are_not_new_simulations': True})
        print(c['candidate_id'], 'frequency gate', measurement_gate(runs, doc)['passed'], flush=True)
    write(out/'complete.json', {'candidate_ids': [c['candidate_id'] for c in candidates[2:8]]})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--development', required=True); parser.add_argument('--out', required=True)
    args = parser.parse_args(); main(args.development, args.out)
