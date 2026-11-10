"""Stage4 supplemental raw-signal checks and conservative research evidence adapter."""
from pathlib import Path
import hashlib
import numpy as np
from .experiments import read, write
from .return_ratio import phasor_fit
from .resources import CONFIGS
from .verify import validate_proposal
from pll_allocation.physics_mapping.model import fingerprint


def classify_feedback(metrics, predictions, constraints, *, validity='VALID', unsupported=(), numerical_ok=True, doc=None):
    """Diagnostic categories compose; an unreliable metric is never a spec violation."""
    doc = doc or read(CONFIGS/'verification/return_ratio_stage4_v0_2.json')
    if validity != 'VALID':
        return [{'category': 'OUT_OF_DOMAIN', 'reason': validity}]
    tags = []
    if unsupported:
        tags.append({'category': 'UNSUPPORTED_METRIC', 'metrics': list(unsupported),
            'reason': 'periodic scalar interpretation not established by current measurement evidence'})
    if not numerical_ok:
        tags.append({'category': 'MEASUREMENT_UNRELIABLE', 'reason': 'numerical or raw-signal gate failed'})
    for name, metric in metrics.items():
        reliable = bool(numerical_ok and name not in unsupported and metric.get('value') is not None
                        and metric.get('status', '').startswith('MEASURED'))
        if not reliable:
            continue
        for check in constraints:
            if check['metric'] == name and check['status'] == 'FAIL':
                tags.append({'category': 'SPEC_VIOLATION', 'metric': name, 'reason': check.get('reason', 'reliable measured violation')})
        if name in predictions:
            difference = metric['value']-predictions[name]
            disagreed = (name == 'UGF_Hz' and abs(difference/predictions[name]) > doc['model_disagreement']['UGF_relative']) or (
                name == 'PM_deg' and abs(difference) > doc['model_disagreement']['PM_absolute_deg'])
            if disagreed:
                tags.append({'category': 'MODEL_DISAGREEMENT', 'metric': name, 'difference': difference,
                    'causes_to_check': ['physical_approximation', 'sampling_switching', 'measurement_definition',
                                        'numerical_integration', 'parameter_units'], 'cause_confirmed': False})
    return tags


def raw_diagnostics(folder, doc):
    rows = []
    for path in sorted(Path(folder).glob('raw/*/*/measurement.json')):
        measurement = read(path); begin, end = measurement['measurement_window_s']
        f = measurement['frequency_Hz']
        for sign in (0, 1):
            with np.load(path.parent/f'trajectory_{sign}.npz') as source:
                z = source['trace']; z = z[(z[:, 0] >= begin)&(z[:, 0] < end)]
                ph, residual, dc = phasor_fit(z[:, 0], z[:, [1, 7]], f)
                thd = np.linalg.norm(ph[1:3], axis=0)/np.abs(ph[0])
                rem = residual/np.abs(ph[0])
                row = {'variant': path.parents[1].name, 'frequency_Hz': f, 'sign_index': sign,
                    'raw_return_THD': float(thd[0]), 'raw_feedback_THD': float(thd[1]),
                    'raw_return_residual_relative': float(rem[0]), 'raw_feedback_residual_relative': float(rem[1]),
                    'window_phase_slope_rad_s': float(dc[1, 0]/(z[-1, 0]-z[0, 0]))}
                row['passed'] = bool(max(thd) <= doc['limits']['THD'] and max(rem) <= doc['limits']['residual_relative'])
                rows.append(row)
    return {'all_raw_signals_passed': all(r['passed'] for r in rows), 'rows': rows,
        'max_raw_THD': max(r['raw_return_THD'] for r in rows),
        'max_raw_residual_relative': max(r['raw_return_residual_relative'] for r in rows),
        'scope': 'raw positive/negative runs, not only odd differential; pilots retained separately for DC failure diagnosis'}


def make_extension(folder, harmonic_rows, raw):
    folder = Path(folder); proposal = read(folder/'AllocationProposal.json'); validate_proposal(proposal)
    rr = read(folder/'return_ratio_result.json'); doc = read(folder/'protocol.json')
    m1 = read(folder/'M1_posthoc.json'); bw = read(folder/'BW_result.json')
    series = rr['runs']['base']['crossing']; clamp = rr['runs']['independent_clamp']['crossing']
    comparisons = rr['measurement_gate']['comparisons']
    variants = [r['crossing'] for r in rr['runs'].values()]
    numerical_ok = rr['measurement_gate']['passed'] and raw['all_raw_signals_passed']
    measured = {}
    for name, unit in [('UGF_Hz', 'Hz'), ('PM_deg', 'deg')]:
        values = [v[name] for v in variants if name in v]
        measured[name] = {'value': None, 'unit': unit, 'status': 'UNKNOWN',
            'reason': 'PERIODIC_SCALAR_RETURN_RATIO_NOT_VALIDATED: reverse harmonic transfer near unity; finite harmonic probes do not establish generalized Nyquist/Floquet stability',
            'diagnostic_series_value': series.get(name), 'diagnostic_direct_clamp_value': clamp.get(name),
            'empirical_diagnostic_range': [min(values), max(values)] if values else None,
            'numerical_converged': bool(numerical_ok), 'independent_event_measurement': True,
            'certified_as_frozen_SystemSpec_metric': False}
    measured['BW_Hz'] = bw['metrics']['BW_Hz']
    feedback = classify_feedback(measured, m1['metrics'], bw['constraints'],
        unsupported=['UGF_Hz', 'PM_deg'], numerical_ok=numerical_ok, doc=doc)
    feedback[0]['required_action'] = 'measure a bounded harmonic return matrix and compare periodic stability criterion before promoting scalar PM'
    errors = {}
    for name in ('UGF_Hz', 'PM_deg'):
        pred = m1['metrics'][name]; local = series.get(name)
        errors[name] = {'M1_prediction': pred, 'M2_certified_measurement': None,
            'diagnostic_series_difference': local-pred if local is not None else None,
            'diagnostic_series_relative_difference': local/pred-1 if local is not None else None,
            'diagnostic_direct_clamp_difference': clamp[name]-pred if name in clamp else None,
            'MODEL_DISAGREEMENT_asserted': False,
            'reason': 'do not label uncertified stability definition as reliable model error'}
    sources = {name: hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest()
        for name in ('kernel.cpp', 'return_ratio_kernel.cpp', 'return_ratio_native.py', 'return_ratio.py', 'return_ratio_validity.py')}
    return {'schema_version': 'pll-stage4-measurement-extension-1.0',
        'candidate_id': proposal['candidate_id'], 'parameter_sha256': proposal['parameter_sha256'],
        'block_space_sha256': proposal['block_space_sha256'], 'system_spec_sha256': proposal['system_spec_sha256'],
        'proposal_versions': proposal['versions'], 'protocol_id': doc['protocol_id'], 'protocol_sha256': fingerprint(doc),
        'base_protocol_id': 'track_b_metrics_1.1', 'source_hashes': sources,
        'metrics': measured, 'constraints': bw['constraints'], 'overall_status': bw['overall_status'],
        'verified_joint_block_spec': False, 'scientific_status': 'UGF / PM M2 MEASUREMENT NOT YET VALIDATED',
        'local_measurement_status': 'NUMERICALLY_CONVERGED_PHASE_PORT_DIAGNOSTIC' if numerical_ok else 'MEASUREMENT_UNRELIABLE',
        'structured_feedback': feedback, 'prediction_errors': errors,
        'possible_error_sources': {'physical_approximation': 'continuous ideal M1 vs switched periodic event response; not isolated as the error cause',
            'sampling_switching': 'reverse fref±f to f conversion independently measured; scalar topology-dependent UGF observed',
            'definition_mismatch': 'series effective scalar return vs direct open-port L00; neither alone certifies periodic stability',
            'numerical_integration': 'step half differences recorded; not a certified global error bound',
            'parameter_units': 'proposal versions/complete SI envelope/frozen hashes validated; no detected mismatch'},
        'evidence': {'measurement_gate': rr['measurement_gate'],
            'raw_signal_checks': {k: v for k, v in raw.items() if k != 'rows'},
            'reverse_harmonic_probes': harmonic_rows,
            'partial_return_matrix_only': True, 'original_Protocol1_1_unchanged': True}}


def load_extension(path, proposal):
    item = read(path)
    validate_proposal(proposal)
    if item.get('schema_version') != 'pll-stage4-measurement-extension-1.0':
        raise ValueError('unsupported Stage4 extension schema')
    for key in ('parameter_sha256', 'block_space_sha256', 'system_spec_sha256', 'proposal_versions'):
        expected = proposal['versions'] if key == 'proposal_versions' else proposal[key]
        if item.get(key) != expected:
            raise ValueError('Stage4 evidence binding mismatch: '+key)
    doc = read(CONFIGS/'verification/return_ratio_stage4_v0_2.json')
    if item.get('protocol_id') != doc['protocol_id'] or item.get('protocol_sha256') != fingerprint(doc):
        raise ValueError('Stage4 protocol mismatch')
    if set(item['source_hashes']) != {'kernel.cpp', 'return_ratio_kernel.cpp', 'return_ratio_native.py', 'return_ratio.py', 'return_ratio_validity.py'}:
        raise ValueError('incomplete Stage4 source bindings')
    for name, sha in item['source_hashes'].items():
        if hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest() != sha:
            raise ValueError('Stage4 source mismatch: '+name)
    if (any(item['metrics'][k]['value'] is not None or item['metrics'][k]['status'] != 'UNKNOWN' for k in ('PM_deg', 'UGF_Hz'))
            or item.get('verified_joint_block_spec') is not False):
        raise ValueError('Stage4 research extension cannot silently certify periodic PM/UGF')
    return item
