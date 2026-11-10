"""Predeclared Nominal gate, then frozen Agent/boundary comparisons. New outputs only."""
from pathlib import Path
import argparse
from copy import deepcopy
import hashlib
import json
import sys
import time
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pll_allocation.verification.return_ratio import protocol, sweep, crossings
from pll_allocation.verification.experiments import candidate, read, write
from pll_allocation.verification.verify import example_proposal, verify
from pll_allocation.physics_mapping.model import evaluate, fingerprint
from pll_allocation.block_space.contracts import load_model, check_parameters


def compare(a, b):
    x = {p['frequency_Hz']: p for p in a['points'] if p['status'] == 'MEASURED'}
    rows = []
    for p in b['points']:
        if p['frequency_Hz'] in x and p['status'] == 'MEASURED':
            u, v = complex(*x[p['frequency_Hz']]['L_complex']), complex(*p['L_complex'])
            rows.append({'f_Hz': p['frequency_Hz'], 'complex_relative': abs(v-u)/abs(u),
                         'phase_deg': abs(float(np.angle(v/u, deg=True)))})
    ca, cb = a['crossing'], b['crossing']
    return {'shared_points': len(rows), 'points': rows,
        'max_complex_relative': max((r['complex_relative'] for r in rows), default=None),
        'max_phase_deg': max((r['phase_deg'] for r in rows), default=None),
        'UGF_relative': abs(cb['UGF_Hz']/ca['UGF_Hz']-1) if 'UGF_Hz' in ca and 'UGF_Hz' in cb else None,
        'PM_absolute_deg': abs(cb['PM_deg']-ca['PM_deg']) if 'PM_deg' in ca and 'PM_deg' in cb else None}


def measurement_gate(runs, doc):
    limits = doc['limits']; base = runs['base']; diagnostics = {}
    reasons = []
    for key, run in runs.items():
        crossing = run['crossing']
        if crossing['status'] != 'MEASURED_BRACKETED' or crossing.get('bracket_relative_width', 1) > doc['crossing_bracket_relative_width']:
            reasons.append(key+':no_converged_crossing')
        if any(p['status'] != 'MEASURED' for p in run['points']):
            # Low-frequency open-port drift can invalidate remote points without erasing local data.
            reasons.append(key+':invalid_frequency_points')
        if key == 'base':
            continue
        comparison = compare(base, run); diagnostics[key] = comparison
        for field, threshold in [('UGF_relative', limits['UGF_relative_refinement']),
                                 ('PM_absolute_deg', limits['PM_refinement_deg'])]:
            if comparison[field] is None or comparison[field] > threshold:
                reasons.append(key+':'+field)
        if key != 'offset_grid':
            if comparison['shared_points'] < 3:
                reasons.append(key+':insufficient_shared_points')
            for field, threshold in [('max_complex_relative', limits['complex_refinement']),
                                     ('max_phase_deg', limits['phase_refinement_deg'])]:
                if comparison[field] is None or comparison[field] > threshold:
                    reasons.append(key+':'+field)
    return {'passed': not reasons, 'reasons': reasons, 'comparisons': diagnostics,
        'scope': 'local fundamental phase-port measurements; not global periodic stability certification'}


def run_case(folder, proposal):
    folder = Path(folder); folder.mkdir(parents=True, exist_ok=False)
    write(folder/'AllocationProposal.json', proposal)
    p = proposal['joint_block_spec']; doc = protocol()
    write(folder/'protocol.json', doc)
    runs = {}
    variants = [('base', 'series', .01, .4e-9, 12, doc['grid_Hz']),
        ('amplitude_half', 'series', .005, .4e-9, 12, doc['grid_Hz']),
        ('step_half', 'series', .01, .2e-9, 12, doc['grid_Hz']),
        ('window_double', 'series', .01, .4e-9, 24, doc['grid_Hz']),
        ('offset_grid', 'series', .01, .4e-9, 12, doc['offset_grid_Hz']),
        ('independent_clamp', 'clamp', .01, .4e-9, 12, doc['grid_Hz'])]
    for name, mode, amp, dt, cycles, grid in variants:
        runs[name] = sweep(folder/'raw'/name, p, mode=mode, amplitude=amp, dt=dt, cycles=cycles, grid=grid, doc=doc)
        print(folder.name, name, json.dumps(runs[name]['crossing']), flush=True)
    gate = measurement_gate(runs, doc)
    # Always save independent diagnostics before any M1 comparison.
    result = {'parameter_sha256': fingerprint(p), 'protocol_sha256': fingerprint(doc),
        'runs': runs, 'measurement_gate': gate, 'formal_values': None,
        'local_converged_values': None,
        'diagnostic_crossing': runs['base']['crossing'],
        'M1_used_for_measurement': False, 'global_periodic_stability_certified': False}
    if gate['passed']:
        result['local_converged_values'] = {k: runs['base']['crossing'][k] for k in ('UGF_Hz', 'PM_deg')}
    write(folder/'return_ratio_result.json', result)
    write(folder/'M1_posthoc.json', evaluate(p).as_dict())
    bw = verify(proposal, folder/'BW_protocol1_1')
    write(folder/'BW_result.json', bw)
    return result


def boundary_candidate():
    # Domain-only one-dimensional search; selecting an experiment, never changing an allocator.
    model = load_model(ROOT/'configs/BLOCK_SPACE_MODEL_V1.json')
    bounds = model['variables']['Rz']['range']; lo, hi = bounds['min'], bounds['max']
    target = next(s['min'] for s in model['experiment']['system_spec']['metrics'] if s['metric'] == 'PM_deg')
    rows = []
    for i in range(48):
        rz = (lo+hi)/2
        p = candidate({'Rz': rz}); prediction = evaluate(p).as_dict()
        pm = prediction['metrics']['PM_deg']
        rows.append({'Rz_Ohm': rz, 'PM_deg': pm})
        if pm < target:
            lo = rz
        else:
            hi = rz
    p = candidate({'Rz': hi})
    assert check_parameters(model, p)['declared_domain'] == 'IN_DECLARED_DOMAIN'
    assert abs(evaluate(p).metrics['PM_deg']-target) < .01
    return p, {'method': '48 bisections of nominal Rz within original range, target existing PM lower bound',
               'target_PM_deg': target, 'steps': rows, 'prediction': evaluate(p).as_dict()}


def main(out):
    out = Path(out).resolve(); out.mkdir(parents=True, exist_ok=False)
    write(out/'source_manifest.json', [{'path': p.relative_to(ROOT).as_posix(),
        'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
        for folder in ('pll_allocation/verification', 'configs/verification')
        for p in sorted((ROOT/folder).glob('*')) if p.is_file()])
    nominal = run_case(out/'nominal', example_proposal(candidate(), 'stage4_nominal'))
    results = {'nominal': nominal, 'extended_cases': 'NOT_STARTED_NOMINAL_GATE_PENDING'}
    if nominal['measurement_gate']['passed']:
        agent = read(ROOT/'experiments/stage3a1_llm_retry_20261104_01/AllocationProposal.json')
        results['real_agent'] = run_case(out/'real_agent', agent)
        p, selection = boundary_candidate()
        write(out/'boundary_selection.json', selection)
        results['pm_boundary'] = run_case(out/'pm_boundary', example_proposal(p, 'stage4_pm_boundary'))
        results['extended_cases'] = 'EXECUTED_AFTER_NOMINAL_GATE_PASSED'
    write(out/'study.json', results)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    main(parser.parse_args().out)
