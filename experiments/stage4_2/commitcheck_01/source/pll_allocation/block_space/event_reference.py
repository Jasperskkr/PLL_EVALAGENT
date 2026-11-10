"""Audited existing Python edge TB adapter, explicitly separate from continuous M1."""
from __future__ import annotations
import ast
import hashlib
import json
import math
from pathlib import Path
import time

PROTOCOL = {
    'id': 'edge_euler_summary_crosscheck_v1', 'duration_s': 160e-6,
    'tail_fraction': .2, 'initial_control_V': .15,
    'coarse_samples_per_max_vco_period': 25, 'refinement_factor': 2,
    'tracking_frequency_tolerance_ppm': 100, 'tracking_phase_rms_limit_deg': 5,
    'frequency_agreement_limit_ppm': 100, 'control_agreement_limit_V': .001,
    'refinement_frequency_delta_limit_ppm': 1, 'refinement_control_delta_limit_V': .0001,
    'refinement_phase_rms_delta_limit_deg': .1,
    'not_system_spec': True,
    'unsupported': ['BW','PM','UGF','formal_lock_time','certified_static_phase_error'],
}


def load_existing_simulator(reference_dir):
    """Extract exactly the old simulate function; never execute its check()/I/O."""
    reference_dir = Path(reference_dir)
    source = reference_dir/'python_crosscheck.py'
    provenance = json.loads((reference_dir/'provenance.json').read_text(encoding='utf-8'))
    if hashlib.sha256(source.read_bytes()).hexdigest() != provenance['sha256']:
        raise ValueError('event reference SHA mismatch')
    tree = ast.parse(source.read_text(encoding='utf-8'), filename=str(source))
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'simulate']
    if len(functions) != 1:
        raise ValueError('expected single audited simulate function')
    import numpy as np  # Optional only for this crosscheck; core domain and M1 use stdlib.
    namespace = {'np': np, 'math': math, 'time': time}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), 'exec'), namespace)
    return namespace['simulate'], provenance


def clean_summary(raw):
    summary, missing = {}, []
    for name, value in raw.items():
        x = float(value)
        if not math.isfinite(x):
            summary[name] = None
            missing.append(name)
        else:
            summary[name] = int(x) if name in {'n','clip_count'} else x
    return summary, missing


def compare_event(candidate, simulator):
    p = {k: x['value'] for k,x in candidate['values'].items()}
    unsupported = [k for k in ('Kvco2','CP_mismatch','CP_leakage','q0','PFD_reset_delay','Cload','Gload') if p[k] != 0]
    if unsupported or p['Vctrl_min'] != 0 or p['Vctrl_max'] != 1.2:
        return {'status': 'UNSUPPORTED', 'reason': 'reference supports only ideal M1 subset and fixed 0..1.2 V rails',
                'behavioral_calls': 0, 'runs': [], 'M2_system_verdict': 'NOT_EVALUATED'}
    fmax = p['f0']+p['Kvco']*p['Vctrl_max']
    target = p['N']*p['f_ref']
    dt = 1/(PROTOCOL['coarse_samples_per_max_vco_period']*max(fmax,target,p['f_ref']))
    # Defend reference's one-edge-per-step assumption, Euler LF stability and resource bounds.
    lf_rate = (p['C1']+p['C2'])/(p['Rz']*p['C1']*p['C2'])
    if dt >= min(1/p['f_ref'],p['N']/fmax)/2 or dt*lf_rate >= .1:
        return {'status': 'OUT_OF_DOMAIN', 'reason': 'reference time step fails edge/Euler domain',
                'behavioral_calls': 0, 'runs': [], 'M2_system_verdict': 'NOT_EVALUATED'}
    runs, missing = [], []
    for refinement in (1,2):
        if math.ceil(PROTOCOL['duration_s']/(dt/refinement))+1 > 2000000:
            return {'status': 'OUT_OF_DOMAIN', 'reason': 'event reference point budget exceeded',
                    'behavioral_calls': len(runs), 'runs': runs, 'M2_system_verdict': 'NOT_EVALUATED'}
        raw = simulator(sim_time=PROTOCOL['duration_s'],dt=dt/refinement,v0=PROTOCOL['initial_control_V'],
            R=p['Rz'],c1=p['C1'],c2=p['C2'],I=p['Icp'],kv=p['Kvco'],f0=p['f0'],
            N=p['N'],fref=p['f_ref'],verbose=False)
        summary, missing_fields = clean_summary(raw)
        runs.append(summary)
        missing.append(missing_fields)
    coarse, fine = runs
    vreq = (target-p['f0'])/p['Kvco']
    errors = {'frequency_prediction_error_ppm': (fine['fout_avg']-target)/target*1e6,
              'Vctrl_endpoint_prediction_error_V': fine['vfinal']-vreq,
              'refinement_frequency_delta_ppm': (fine['fout_avg']-coarse['fout_avg'])/target*1e6,
              'refinement_control_delta_V': fine['vfinal']-coarse['vfinal'],
              'refinement_phase_rms_delta_deg': fine['phase_rms_deg']-coarse['phase_rms_deg']}
    converged = (abs(errors['refinement_frequency_delta_ppm']) <= PROTOCOL['refinement_frequency_delta_limit_ppm']
                 and abs(errors['refinement_control_delta_V']) <= PROTOCOL['refinement_control_delta_limit_V']
                 and abs(errors['refinement_phase_rms_delta_deg']) <= PROTOCOL['refinement_phase_rms_delta_limit_deg'])
    tracking = (abs(fine['ppm']) < PROTOCOL['tracking_frequency_tolerance_ppm']
                and fine['phase_rms_deg'] < PROTOCOL['tracking_phase_rms_limit_deg'])
    agreement = (converged and tracking and abs(errors['frequency_prediction_error_ppm']) <= PROTOCOL['frequency_agreement_limit_ppm']
                 and abs(errors['Vctrl_endpoint_prediction_error_V']) <= PROTOCOL['control_agreement_limit_V'])
    interior = p['Vctrl_min'] < vreq < p['Vctrl_max']
    return {'status': 'COMPLETED', 'protocol': PROTOCOL, 'runs': runs, 'nonfinite_summary_fields': missing,
        'behavioral_calls': 2, 'integration_points': sum(x['n'] for x in runs),
        'step_refinement_converged': converged, 'tail_tracking_observed': tracking,
        'no_rail_samples_observed': all(x['clip_count'] == 0 for x in runs),
        'interior_tuning_predicted': interior,
        'conditional_frequency_control_agreement': agreement if interior else False,
        'errors': errors, 'M2_system_verdict': 'NOT_EVALUATED',
        'limitations': ['summaries only; no sustained lock certificate or raw waveform',
                        'clip_count counts near-rail samples, not actual clamp events',
                        'tail phase RMS is diagnostic, not supported SystemSpec static error',
                        'frequency comparison tolerance belongs to crosscheck, not frozen SystemSpec',
                        'BW/PM/UGF are not measured by this TB']}
