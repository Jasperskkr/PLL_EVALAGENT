"""English research figures from complete measured evidence; no certification upgrade."""
from pathlib import Path
import argparse
import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import NullLocator, NullFormatter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pll_allocation.verification.experiments import read, write
from pll_allocation.physics_mapping.model import parse_parameters, _response


def main(summary, out, qa_scripts):
    summary, out = Path(summary), Path(out); out.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, qa_scripts)
    from audit_panel_alignment import require_matplotlib_panel_alignment
    plt.rcParams.update({'font.family': 'sans-serif', 'font.sans-serif': ['Arial', 'DejaVu Sans'],
        'font.size': 8, 'axes.titlesize': 9, 'axes.labelsize': 8, 'xtick.labelsize': 7,
        'ytick.labelsize': 7, 'legend.fontsize': 8, 'pdf.fonttype': 42, 'svg.fonttype': 'none',
        'axes.spines.top': False, 'axes.spines.right': False, 'legend.frameon': False})
    records = read(summary/'full_results.json'); byid = {r['candidate_id'][:3]: r for r in records}
    source_rows = []
    def save(fig, name):
        fig.canvas.draw()
        if len(fig.axes) > 1:
            require_matplotlib_panel_alignment(fig, json_out=out/(name+'.alignment.json'),
                overlay_svg=out/(name+'.alignment.svg'), tolerance_pt=1.5, gutter_tolerance_pt=1.5, strict=True)
        for suffix in ('pdf', 'svg', 'png'):
            fig.savefig(out/(name+'.'+suffix), dpi=300)
        plt.close(fig)
    for page in range(2):
        group = records[page*5:(page+1)*5]
        fig, axes = plt.subplots(2, len(group), figsize=(11.8, 5.2), sharex=True, sharey='row', squeeze=False)
        fig.subplots_adjust(left=.065, right=.985, bottom=.13, top=.78, hspace=.34, wspace=.28)
        for col, r in enumerate(group):
            p = parse_parameters(r['joint_block_spec']); grid = np.geomspace(25000, 1e6, 300)
            lin = np.array([_response(p, float(f))[1] for f in grid])
            axes[0, col].semilogx(grid/1000, 20*np.log10(abs(lin)), color='#333333', lw=1.3, label='M1 Prediction')
            axes[1, col].semilogx(grid/1000, np.rad2deg(np.unwrap(np.angle(lin))), color='#333333', lw=1.3)
            for mode, color, marker, label in [('base', '#0072B2', 'o', 'M2 Series Local'),
                    ('independent_clamp', '#D55E00', 's', 'M2 Direct Port Local')]:
                points = r['frequency_runs'][mode]['points']
                f = np.array([pt['frequency_Hz'] for pt in points]); z = np.array([complex(*pt['L_complex']) for pt in points])
                phase = np.rad2deg(np.unwrap(np.angle(z)))
                axes[0, col].semilogx(f/1000, 20*np.log10(abs(z)), color=color, marker=marker, ms=2.6,
                                     fillstyle='none', lw=.75, label=label)
                axes[1, col].semilogx(f/1000, phase, color=color, marker=marker, ms=2.6, fillstyle='none', lw=.75)
                for j, pt in enumerate(points):
                    if pt['status'] != 'MEASURED':
                        axes[0, col].plot(f[j]/1000, 20*np.log10(abs(z[j])), 'x', color='#CC0000', ms=6)
                        axes[1, col].plot(f[j]/1000, phase[j], 'x', color='#CC0000', ms=6)
                    source_rows.append({'figure': 'frequency', 'candidate': r['candidate_id'], 'curve': mode,
                        'x': f[j], 'y': abs(z[j]), 'phase_deg': phase[j], 'status': pt['status']})
            axes[0, col].set_title(r['candidate_id'].replace('_', '\n', 1))
            for ax in axes[:, col]:
                ax.set_xticks([25, 100, 1000], labels=['25', '100', '1000'])
                ax.xaxis.set_minor_locator(NullLocator()); ax.xaxis.set_minor_formatter(NullFormatter())
                ax.set_xlim(25, 1000)
            axes[0, col].axhline(0, color='#AAAAAA', lw=.7, ls=':')
            axes[1, col].set_xlabel('Frequency (kHz)')
        axes[0, 0].set_ylabel('Return Magnitude (dB)'); axes[1, 0].set_ylabel('Return Phase (deg)')
        axes[0, 0].set_ylim(-30, 31); axes[1, 0].set_ylim(-185, -75)
        fig.legend(*axes[0, 0].get_legend_handles_labels(), loc='upper center', ncol=3, bbox_to_anchor=(.52, .965))
        fig.text(.52, .035, 'All frequency points retained. Local return ratios do not certify full periodic-system PM.', ha='center', fontsize=8)
        save(fig, 'frequency_response_'+str(page+1))

    def curve(cid):
        r = byid[cid]
        return np.loadtxt(Path(r['step_analysis_path'])/'plus_cycle_response.csv', delimiter=',', skiprows=1)
    for name, ids, title in [('matched_PM', ['C04', 'C05', 'C06'], 'Matched UGF: LF Shape Also Changes'),
                              ('low_PM', ['C04', 'C07'], 'Low PM: More Ringing, Local Recovery Retained'),
                              ('gain_split', ['C01', 'C08'], 'Gain Split: Equal Product and RC Dynamics')]:
        fig, axes = plt.subplots(2, 1, figsize=(7.2, 5.1), sharex=True)
        fig.subplots_adjust(left=.11, right=.98, bottom=.12, top=.79, hspace=.38)
        colors = ['#0072B2', '#D55E00', '#009E73']
        for cid, color in zip(ids, colors):
            data = curve(cid); mask = data[:, 0] <= 40e-6
            data = data[mask]; x = data[:, 0]*1e6
            pm = byid[cid]['M1']['metrics']['PM_deg']; label = f'{cid}, M1 PM {pm:.1f} deg'
            axes[0].plot(x, data[:, 2], color=color, lw=1.4, label=label+'; M2 Observation')
            axes[0].plot(x, data[:, 3], color=color, lw=1., ls='--', label=label+'; M1 Prediction')
            if name != 'gain_split':
                axes[1].plot(x, (data[:, 2]-data[:, 3])*100, color=color, lw=1.1, label=cid)
        if name == 'gain_split':
            a, b = curve(ids[0]), curve(ids[1]); mask = a[:, 0] <= 40e-6
            diff = b[:, 2]-a[:, 2]
            axes[1].plot(a[mask, 0]*1e6, diff[mask]*1e6, color='#D55E00', lw=1.1)
            axes[1].set_ylabel('C08 - C01 (ppm of Step)')
        else:
            axes[1].set_ylabel('M2 - M1 (% of Step)')
        axes[0].axhline(1, color='#AAAAAA', ls=':', lw=.8)
        axes[0].set_ylabel('Divided Phase / Input Step'); axes[0].set_title(title, pad=9)
        axes[1].set_xlabel('Time From Phase-Step Onset (us)'); axes[1].axhline(0, color='#AAAAAA', lw=.7)
        axes[0].set_xlim(0, 40)
        fig.legend(*axes[0].get_legend_handles_labels(), loc='upper center', bbox_to_anchor=(.54, .985), ncol=2, fontsize=7)
        save(fig, name)

    fig, axes = plt.subplots(2, 2, figsize=(9.6, 6.1))
    fig.subplots_adjust(left=.08, right=.98, bottom=.15, top=.87, hspace=.55, wspace=.30)
    x = np.arange(len(records)); labels = [r['candidate_id'][:3] for r in records]
    for key, label, color in [('BW_relative', 'BW', '#333333'), ('base_UGF_relative', 'Series UGF', '#0072B2'),
                              ('independent_clamp_UGF_relative', 'Direct Port UGF', '#D55E00')]:
        axes[0, 0].plot(x, [100*r['contract']['errors'][key] for r in records], 'o-', ms=3, lw=1, color=color, label=label)
    axes[0, 0].set_title('Frequency Prediction Error'); axes[0, 0].set_ylabel('M2 / M1 - 1 (%)'); axes[0, 0].legend(fontsize=7)
    for key, label, color in [('base_PM_difference_deg', 'Series', '#0072B2'), ('independent_clamp_PM_difference_deg', 'Direct Port', '#D55E00')]:
        axes[0, 1].plot(x, [r['contract']['errors'][key] for r in records], 'o-', ms=3, lw=1, color=color, label=label)
    axes[0, 1].set_title('Local PM Difference'); axes[0, 1].set_ylabel('M2 - M1 (deg)'); axes[0, 1].legend(fontsize=7)
    for field, label, color in [('normalized_RMSE', 'RMSE', '#0072B2'), ('max_normalized_error', 'Maximum', '#D55E00')]:
        axes[1, 0].plot(x, [100*r['steps']['results']['plus']['comparison'][field] for r in records], 'o-', ms=3, lw=1, color=color, label=label)
    axes[1, 0].set_title('Closed-loop Waveform Difference'); axes[1, 0].set_ylabel('Error (% of Step)'); axes[1, 0].legend(fontsize=7)
    for i, r in enumerate(records):
        axes[1, 1].scatter(r['M1']['metrics']['PM_deg'], 100*r['steps']['results']['plus']['M2']['overshoot_relative'],
                            marker='s' if i >= 8 else 'o', s=25, color='#D55E00' if i == 6 else '#0072B2')
    axes[1, 1].set_title('Observed Overshoot vs M1 PM'); axes[1, 1].set_xlabel('M1 PM (deg)'); axes[1, 1].set_ylabel('Overshoot (%)')
    for ax in [axes[0, 0], axes[0, 1], axes[1, 0]]:
        ax.set_xticks(x, labels); ax.axhline(0, lw=.6, color='#AAAAAA')
    fig.text(.52, .04, 'Squares: untouched holdouts. All PM certification remains UNKNOWN; no full SystemSpec PASS.', ha='center', fontsize=8)
    save(fig, 'prediction_error_and_risk')
    write(out/'figure_contract.json', {'archetype': 'quantitative grids', 'backend': 'python',
        'claims': ['local frequency agreement for all ten enumerated candidates', 'time response discrimination with LF confounding disclosed',
                   'low-PM recovery can remain stable', 'ideal gain-split invariance', 'error bounds are observed finite tests only'],
        'source': str(summary.resolve()), 'uncertainty': 'deterministic measured refinements, no statistical confidence intervals',
        'exclusion': 'none for frequency evidence; step figures show predeclared representative groups and first40us, full80/160us data retained',
        'not_journal_submission': True})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--summary', required=True); parser.add_argument('--out', required=True)
    parser.add_argument('--qa-scripts', required=True)
    args = parser.parse_args(); main(args.summary, args.out, args.qa_scripts)
