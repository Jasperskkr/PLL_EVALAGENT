"""English response plots: measured local scalars versus frozen M1; no certification claim."""
import argparse
import csv
from pathlib import Path
import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import NullLocator, NullFormatter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pll_allocation.verification.experiments import read
from pll_allocation.physics_mapping.model import _response, parse_parameters


def main(study, out, qa_scripts):
    study, out = Path(study), Path(out); out.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, qa_scripts)
    from audit_panel_alignment import require_matplotlib_panel_alignment
    plt.rcParams.update({'font.family': 'sans-serif', 'font.sans-serif': ['Arial', 'DejaVu Sans'],
        'font.size': 8, 'pdf.fonttype': 42, 'svg.fonttype': 'none', 'axes.spines.top': False,
        'axes.spines.right': False, 'axes.linewidth': .7, 'legend.frameon': False})
    fig, axes = plt.subplots(2, 3, figsize=(7.2, 4.7), sharex=True, sharey='row')
    fig.subplots_adjust(left=.09, right=.98, bottom=.15, top=.79, hspace=.27, wspace=.24)
    source_rows = []
    for col, (case, label) in enumerate([('nominal', 'Nominal'), ('real_agent', 'Saved Real Agent'), ('pm_boundary', 'PM Boundary')]):
        data = read(study/case/'return_ratio_result.json')
        p = parse_parameters(read(study/case/'AllocationProposal.json')['joint_block_spec'])
        frequencies = np.geomspace(25000, 1000000, 200)
        linear = np.array([_response(p, float(f))[1] for f in frequencies])
        curves = [(frequencies, linear, 'M1 Continuous', '#555555', '-', 1.2)]
        for name, title, color, style in [('base', 'M2 Series (Diagnostic)', '#0072B2', '-'),
                                         ('independent_clamp', 'M2 Direct Port (Diagnostic)', '#D55E00', '--')]:
            points = sorted(data['runs'][name]['points'], key=lambda x: x['frequency_Hz'])
            f = np.array([x['frequency_Hz'] for x in points])
            l = np.array([complex(*x['L_complex']) for x in points])
            curves.append((f, l, title, color, style, 1.05))
        for f, l, title, color, style, width in curves:
            assert np.all(f > 0) and np.all(np.abs(l) > 0)
            axes[0, col].semilogx(f/1000, 20*np.log10(abs(l)), color=color, linestyle=style, linewidth=width, label=title)
            axes[1, col].semilogx(f/1000, np.rad2deg(np.unwrap(np.angle(l))), color=color, linestyle=style, linewidth=width)
            for freq, value in zip(f, l):
                source_rows.append({'case': case, 'curve': title, 'frequency_Hz': freq,
                    'real': value.real, 'imag': value.imag, 'phase_deg': np.angle(value, deg=True)})
        cross = data['diagnostic_crossing']; ugf = cross['UGF_Hz']/1000
        axes[0, col].plot(ugf, 0., 'o', ms=3.5, color='#0072B2', zorder=4)
        for ax in axes[:, col]:
            ax.axvline(ugf, color='#0072B2', alpha=.35, linewidth=.7, linestyle=':')
            ax.set_xlim(25, 1000); ax.set_xticks([30, 100, 300, 1000], labels=['30', '100', '300', '1000'])
            ax.xaxis.set_minor_locator(NullLocator()); ax.xaxis.set_minor_formatter(NullFormatter())
            ax.tick_params(labelsize=7)
        axes[0, col].axhline(0., color='#AAAAAA', linewidth=.65, linestyle=':')
        axes[0, col].set_title(label+'\nLocal UGF '+f'{ugf:.3f}'+' kHz', fontsize=8, pad=7)
        axes[1, col].set_xlabel('Frequency (kHz)')
    axes[0, 0].set_ylabel('Return Magnitude (dB)')
    axes[1, 0].set_ylabel('Return Phase (deg)')
    axes[0, 0].set_ylim(-27, 28); axes[1, 0].set_ylim(-185, -85)
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='upper center', bbox_to_anchor=(.52, .975), ncol=1, fontsize=8)
    fig.text(.52, .035, 'Local phase-port responses are repeatable; periodic-system PM certification remains UNKNOWN.',
             ha='center', fontsize=7)
    fig.canvas.draw()
    require_matplotlib_panel_alignment(fig, json_out=out/'frequency_response.alignment.json',
        overlay_svg=out/'frequency_response.alignment.svg', tolerance_pt=1.5, gutter_tolerance_pt=1.5, strict=True)
    fig.savefig(out/'frequency_response.pdf')
    fig.savefig(out/'frequency_response.svg')
    fig.savefig(out/'frequency_response.png', dpi=300)
    with (out/'frequency_response_plot_source.csv').open('x', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(source_rows[0])); writer.writeheader(); writer.writerows(source_rows)
    plt.close(fig)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--study', required=True); parser.add_argument('--out', required=True)
    parser.add_argument('--qa-scripts', required=True); args = parser.parse_args(); main(args.study, args.out, args.qa_scripts)
