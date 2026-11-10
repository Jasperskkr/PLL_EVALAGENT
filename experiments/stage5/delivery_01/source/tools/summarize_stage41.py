"""Deterministic research confidence contract; never changes formal M2 decisions."""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import time
import numpy as np
from run_stage41 import inputs, bindings
from run_stage4 import measurement_gate
from pll_allocation.physics_mapping.model import evaluate, parse_parameters, _response
from pll_allocation.verification.closed_loop import protocol
from pll_allocation.verification.return_ratio import protocol as rr_protocol
from pll_allocation.verification.experiments import read, write


def table(path, rows):
    with path.open('x', encoding='utf-8', newline='') as stream:
        fields = list(dict.fromkeys(k for row in rows for k in row))
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(rows)


def evidence(c, args):
    cid = c['candidate_id']; index = int(cid[1:3])
    folder = (Path(args.development) if index <= 8 else Path(args.holdout))/cid
    if index <= 2:
        f = Path(args.anchors)/cid
        frequency = read(f/'return_ratio_result.json')['runs']; bw = read(f/'BW_result.json')
    elif index <= 8:
        frequency = read(Path(args.refinements)/cid/'result.json')['runs']; bw = read(folder/'BW_result.json')
    else:
        frequency = read(folder/'frequency_result.json'); bw = read(folder/'BW_result.json')
    stepfolder = Path(args.analysis)/cid if index <= 8 else folder/'steps'
    steps = read(stepfolder/'result.json')
    return folder, stepfolder, frequency, bw, steps


def classify(c, m1, frequency, bw, steps):
    cfg = protocol()['limits']; pp = parse_parameters(c['joint_block_spec'])
    measured_gate = measurement_gate(frequency, rr_protocol()); reasons = []; maxcomplex = 0.; maxphase = 0.
    for name in ('base', 'independent_clamp'):
        for pt in frequency[name]['points']:
            if pt['status'] != 'MEASURED':
                reasons.append(name+':invalid_point'); continue
            truth = _response(pp, pt['frequency_Hz'])[1]; got = complex(*pt['L_complex'])
            maxcomplex = max(maxcomplex, abs(got-truth)/abs(truth))
            maxphase = max(maxphase, abs(float(np.angle(got/truth, deg=True))))
    errors = {'BW_relative': None if bw['metrics'].get('BW_Hz', {}).get('value') is None else bw['metrics']['BW_Hz']['value']/m1['BW_Hz']-1,
              'max_frequency_complex_relative': maxcomplex, 'max_frequency_phase_deg': maxphase}
    for name in ('base', 'independent_clamp'):
        cross = frequency[name]['crossing']
        errors[name+'_UGF_relative'] = cross.get('UGF_Hz', m1['UGF_Hz'])/m1['UGF_Hz']-1 if 'UGF_Hz' in cross else None
        errors[name+'_PM_difference_deg'] = cross['PM_deg']-m1['PM_deg'] if 'PM_deg' in cross else None
    freq_ok = (not reasons and measured_gate['passed'] and errors['BW_relative'] is not None
               and abs(errors['BW_relative']) <= cfg['M1_BW_relative']
               and maxcomplex <= cfg['M1_frequency_complex_relative'] and maxphase <= cfg['M1_frequency_phase_deg'])
    for name in ('base', 'independent_clamp'):
        freq_ok = bool(freq_ok and errors[name+'_UGF_relative'] is not None and errors[name+'_PM_difference_deg'] is not None
                       and abs(errors[name+'_UGF_relative']) <= cfg['M1_UGF_relative']
                       and abs(errors[name+'_PM_difference_deg']) <= cfg['M1_PM_absolute_deg'])
    time_valid = bool(steps.get('convergence', {}).get('converged', False))
    all_valid = time_valid and all(r['status'] == 'MEASURED' for r in steps.get('results', {}).values())
    time_ok = all_valid and all(r['comparison']['supported'] for r in steps['results'].values())
    tags = ['FULL_PERIODIC_PM_NOT_CERTIFIED']
    if not measured_gate['passed'] or not all_valid:
        tags.append('MEASUREMENT_UNRELIABLE')
    elif freq_ok and time_ok:
        tags.append('LOCAL_MAPPING_SUPPORTED')
    else:
        tags.append('LOCAL_MAPPING_DISAGREEMENT')
    if all_valid and all(r['M2']['settling_s'] is not None and r['raw_validity']['cycle_slips'] == 0
                         and r['raw_validity']['clamps'] == 0 for r in steps['results'].values()):
        tags.append('CLOSED_LOOP_STABLE_OBSERVED')
    return {'tags': tags, 'errors': errors, 'frequency_gate': measured_gate,
            'time_comparison_supported': bool(time_ok), 'frequency_comparison_supported': bool(freq_ok),
            'formal_PM': {'value': None, 'status': 'UNKNOWN'}, 'formal_UGF': {'value': None, 'status': 'UNKNOWN'},
            'formal_overall_status': bw['overall_status'], 'verified_joint_block_spec': False}


def main(args):
    out = Path(args.out); out.mkdir(parents=True, exist_ok=False)
    candidates, registry = inputs(); rows = []; timerows = []; records = []; frequencyrows = []
    for c in candidates if args.holdout else candidates[:8]:
        folder, stepfolder, frequency, bw, steps = evidence(c, args)
        m1doc = evaluate(c['joint_block_spec']).as_dict(); m1 = m1doc['metrics']
        contract = classify(c, m1, frequency, bw, steps)
        row = {'candidate_id': c['candidate_id'], 'parameter_sha256': c['parameter_sha256'],
               'M1_spec_judgment': c['M1_judgment']['verdict'], 'BW_M1_Hz': m1['BW_Hz'],
               'BW_M2_Hz': bw['metrics'].get('BW_Hz', {}).get('value'),
               'UGF_M1_Hz': m1['UGF_Hz'], 'UGF_series_Hz': frequency['base']['crossing'].get('UGF_Hz'),
               'UGF_clamp_Hz': frequency['independent_clamp']['crossing'].get('UGF_Hz'),
               'PM_M1_deg': m1['PM_deg'], 'PM_series_deg': frequency['base']['crossing'].get('PM_deg'),
               'PM_clamp_deg': frequency['independent_clamp']['crossing'].get('PM_deg'),
               **contract['errors'], 'series_minus_clamp_UGF_relative': frequency['base']['crossing'].get('UGF_Hz', 0)/frequency['independent_clamp']['crossing'].get('UGF_Hz', 1)-1,
               'series_minus_clamp_PM_deg': frequency['base']['crossing'].get('PM_deg', 0)-frequency['independent_clamp']['crossing'].get('PM_deg', 0),
               'time_status': steps['status'], 'research_tags': '|'.join(contract['tags']),
               'formal_BW_status': next(x['status'] for x in bw['constraints'] if x['metric'] == 'BW_Hz'),
               'formal_output_frequency_status': 'UNKNOWN', 'formal_PM_status': 'UNKNOWN',
               'formal_UGF_status': 'UNKNOWN', 'formal_overall_status': bw['overall_status']}
        rows.append(row)
        for name, r in steps.get('results', {}).items():
            if r['status'] != 'MEASURED':
                timerows.append({'candidate_id': c['candidate_id'], 'variant': name, 'status': r['status']}); continue
            timerows.append({'candidate_id': c['candidate_id'], 'variant': name, 'status': r['status'],
                'peak_phase_deviation_rad': r['peak_phase_deviation_rad'],
                'overshoot_relative': r['M2']['overshoot_relative'], 'undershoot_relative': r['M2']['undershoot_relative'],
                'ringing_amplitude_relative': r['M2']['ringing_amplitude_relative'],
                'decay_status': r['M2']['decay']['status'], 'decay_rate_per_s': r['M2']['decay']['rate_per_s'],
                'ringing_period_s': r['M2']['decay']['period_s'], 'settling_s': r['M2']['settling_s'],
                'residual_phase_rad': r['raw_validity']['tail']['residual_phase_rad'],
                'clamps': r['raw_validity']['clamps'], 'cycle_slips': r['raw_validity']['cycle_slips'],
                'recovery': r['lock_retention_recovery'], **r['comparison']})
        p = parse_parameters(c['joint_block_spec'])
        for name, run in frequency.items():
            for pt in run['points']:
                truth = _response(p, pt['frequency_Hz'])[1]; got = complex(*pt['L_complex']) if 'L_complex' in pt else None
                frequencyrows.append({'candidate_id': c['candidate_id'], 'variant': name,
                    'frequency_Hz': pt['frequency_Hz'], 'status': pt['status'], 'reasons': '|'.join(pt.get('reasons', [])),
                    'M1_real': truth.real, 'M1_imag': truth.imag, 'M2_real': got.real if got else None,
                    'M2_imag': got.imag if got else None, 'complex_relative_error': abs(got/truth-1) if got else None,
                    'phase_error_deg': float(np.angle(got/truth, deg=True)) if got else None})
        records.append({'candidate_id': c['candidate_id'], 'parameter_sha256': c['parameter_sha256'],
            'joint_block_spec': c['joint_block_spec'], 'source_evidence': str(folder.resolve()),
            'step_analysis_path': str(stepfolder.resolve()), 'M1': m1doc, 'frequency_runs': frequency,
            'BW': bw, 'steps': steps, 'contract': contract})
    table(out/'candidate_validation_results.csv', rows); table(out/'closed_loop_response_metrics.csv', timerows)
    table(out/'frequency_response.csv', frequencyrows)
    contract = {'schema_version': 'pll-engineering-mapping-confidence-0.1',
        'status': 'RESEARCH_REVIEW_ONLY', 'source_bindings': bindings(), 'model_versions': registry['model_versions'],
        'block_space_sha256': registry['block_space_sha256'], 'system_spec_sha256': registry['system_spec_sha256'],
        'protocol': protocol(), 'validated_scope': 'exact enumerated SI candidates only; fixed 10MHz x8 ideal CP/PFD linear VCO C1-shunt/Rz-series-C2; local phase steps +/-0.01/0.02rad, rise0.5us, dt0.4/0.2ns, post windows80/160us',
        'not_validated': ['whole declared six-dimensional domain', 'arbitrary carrier/operating phase', 'nonideal/noisy/transistor/PVT behavior',
                          'large-signal global capture', 'full periodic scalar PM', 'microHz frequency certification'],
        'may_issue_behavioral_PASS': False, 'changes_formal_pipeline': False,
        'candidates': [{k: r[k] for k in ('candidate_id', 'parameter_sha256', 'joint_block_spec', 'contract')} for r in records]}
    write(out/'ENGINEERING_MAPPING_CONFIDENCE.json', contract); write(out/'full_results.json', records)
    if args.freeze:
        if args.holdout or len(records) != 8:
            raise ValueError('holdout lock requires development-only eight-candidate analysis')
        write(Path(args.freeze), {'development_complete': True, 'source_bindings': bindings(),
              'holdout_ids': [c['candidate_id'] for c in candidates[8:]], 'locked_unix': time.time(),
              'development_analysis_sha256': hashlib.sha256((out/'full_results.json').read_bytes()).hexdigest(),
              'thresholds_changed_after_first_M2': False, 'holdout_M2_used_for_tuning': False,
              'scope': 'fixed complete suite once, including predeclared refinements; no post-holdout method tuning'})
    print(json.dumps({'candidates': len(records), 'tags': {r['candidate_id']: r['contract']['tags'] for r in records}}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('anchors', 'development', 'refinements', 'analysis', 'out'):
        parser.add_argument('--'+name, required=True)
    parser.add_argument('--holdout'); parser.add_argument('--freeze')
    main(parser.parse_args())
