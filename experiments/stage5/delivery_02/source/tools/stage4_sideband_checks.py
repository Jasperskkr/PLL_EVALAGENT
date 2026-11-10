"""Independent reverse harmonic probes at measured crossover; not an M1 calculation."""
from pathlib import Path
import argparse
import sys
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pll_allocation.verification.return_ratio_native import simulate_port
from pll_allocation.verification.return_ratio import phasor_fit
from pll_allocation.verification.experiments import read, write


def main(study, out):
    study, out = Path(study), Path(out)
    out.mkdir(parents=True, exist_ok=False)
    write(out/'predeclared_plan.json', {'purpose': 'test reverse reference-rate harmonic conversion; no stability PASS from finite truncation',
        'frequency_selection': 'measured base crossover only; no M1 input', 'sidebands': ['fref-f', 'fref+f'],
        'amplitude_rad': .001, 'dt_pair_s': [.4e-9, .2e-9], 'cycles_of_base_frequency': 12,
        'onset_s': 20e-6, 'discard_s': 80e-6, 'record_s': 5e-9})
    results = {}
    for case in ('nominal', 'real_agent', 'pm_boundary'):
        p = read(study/case/'AllocationProposal.json')['joint_block_spec']
        data = read(study/case/'return_ratio_result.json')
        f = data['diagnostic_crossing']['UGF_Hz']
        rows = []
        for sign in (-1, 1):
            excitation = 10e6+sign*f
            for dt in (.4e-9, .2e-9):
                directory = out/case/f'sign{sign}_dt{dt:.0e}'
                directory.mkdir(parents=True)
                settings = {'frequency_Hz': excitation, 'amplitude_rad': .001, 'mode': 'clamp',
                    'duration_s': 100e-6+12/f, 'onset_s': 20e-6, 'dt_s': dt, 'record_interval_s': 5e-9}
                write(directory/'request.json', {'parameters': p, 'settings': settings})
                run = simulate_port(p, **settings)
                write(directory/'summary.json', {'summary': run['summary'], 'settings': run['settings']})
                np.savez_compressed(directory/'trajectory.npz', trace=run['trace'])
                z = run['trace']; z = z[(z[:, 0] >= 100e-6)&(z[:, 0] < settings['duration_s'])]
                # Joint regression includes both low response and actual injected high sideband.
                freqs = [f, excitation, 10e6-sign*f, 2*10e6+sign*f]
                t = z[:, 0]
                matrix = np.column_stack([np.ones(len(t)), (t-np.mean(t))/np.ptp(t)]+
                    [x for fr in freqs for x in (np.cos(2*np.pi*fr*t), np.sin(2*np.pi*fr*t))])
                coeff, _, _, _ = np.linalg.lstsq(matrix, z[:, 1], rcond=None)
                returned = complex(coeff[2], -coeff[3]); direct = complex(coeff[4], -coeff[5])
                injected = -.001j*np.exp(-2j*np.pi*excitation*settings['onset_s'])
                ratio = -returned/(injected if sign == 1 else np.conjugate(injected))
                row = {'base_Hz': f, 'excitation_Hz': excitation, 'dt_s': dt,
                    'reverse_conversion_complex': [ratio.real, ratio.imag], 'reverse_conversion_magnitude': abs(ratio),
                    'returned_high_frequency_magnitude': abs(direct/injected),
                    'scope': 'one-sided harmonic transfer; not complete harmonic return matrix or Floquet multiplier'}
                write(directory/'measurement.json', row); rows.append(row)
        results[case] = rows
    write(out/'harmonic_diagnostics.json', results)
    print({case: [r['reverse_conversion_magnitude'] for r in rows] for case, rows in results.items()})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--study', required=True); parser.add_argument('--out', required=True)
    args = parser.parse_args(); main(args.study, args.out)
