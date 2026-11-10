"""Predeclared reference-period observations and independent time-response metrics."""
from pathlib import Path
import numpy as np
from scipy.integrate import cumulative_trapezoid
from scipy.signal import find_peaks, lsim, TransferFunction
from .experiments import read
from .resources import CONFIGS


def protocol():
    doc = read(CONFIGS/'verification/closed_loop_stage4_1_v0_1.json')
    if (doc.get('schema_version') != 'pll-closed-loop-perturbation-0.1'
            or doc.get('protocol_id') != 'stage4_1_phase_step_0.1'
            or doc.get('base_protocol_id') != 'track_b_metrics_1.1'
            or doc.get('formal_UGF_PM_certification') is not False
            or doc.get('new_SystemSpec_constraints') is not False):
        raise ValueError('phase-step protocol version/certification mismatch')
    return doc


def cycle_average(t, signals, edges):
    """Integral of actual piecewise-linear sampled traces, no hidden phase alignment."""
    if np.any(np.diff(t) <= 0) or edges[0] < t[0] or edges[-1] > t[-1]+1e-15:
        raise ValueError('invalid cycle averaging support')
    x = np.asarray(signals)
    if x.ndim == 1:
        x = x[:, None]
    integ = cumulative_trapezoid(x, t, axis=0, initial=0.)
    index = np.minimum(np.searchsorted(t, edges, side='right')-1, len(t)-2)
    dx = edges-t[index]
    slope = (x[index+1]-x[index])/(t[index+1]-t[index])[:, None]
    vals = integ[index]+dx[:, None]*x[index]+.5*dx[:, None]**2*slope
    return np.diff(vals, axis=0)/np.diff(edges)[:, None]


def decay_fit(t, z, limits):
    err = z-1
    idx, _ = find_peaks(np.abs(err), distance=3, prominence=limits['decay_peak_floor']/2)
    idx = idx[np.abs(err[idx]) >= limits['decay_peak_floor']]
    result = {'status': 'UNKNOWN', 'rate_per_s': None, 'period_s': None,
              'peak_count': len(idx), 'reason': 'insufficient stable ringing envelope'}
    if len(idx) >= limits['decay_min_peaks'] and np.max(np.abs(err[idx]))/np.min(np.abs(err[idx])) >= limits['decay_min_amplitude_ratio']:
        def fit(ii):
            x = t[ii]-t[ii[0]]; y = np.log(np.abs(err[ii]))
            c = np.polyfit(x, y, 1); estimate = np.polyval(c, x)
            r2 = 1-np.sum((y-estimate)**2)/max(np.sum((y-y.mean())**2), 1e-30)
            return -float(c[0]), float(r2)
        rate, r2 = fit(idx)
        variants = [fit(idx[1:])[0], fit(idx[:-1])[0]]
        spread = max(abs(v/rate-1) for v in variants) if rate > 0 else None
        result.update(R2=r2, trim_rates_per_s=variants, trim_relative_spread=spread)
        if rate > 0 and r2 >= limits['decay_min_R2'] and spread <= limits['decay_refinement_relative']:
            result.update(status='MEASURED', rate_per_s=rate, reason='log envelope and trim stability passed')
    peaks, _ = find_peaks(z, distance=3, prominence=limits['decay_peak_floor']/2)
    peaks = peaks[z[peaks]-1 >= limits['decay_peak_floor']]
    if len(peaks) >= 3:
        periods = np.diff(t[peaks]); cv = float(np.std(periods)/np.mean(periods))
        result['period_CV'] = cv
        if cv <= limits['period_max_CV']:
            result['period_s'] = float(np.mean(periods))
    return result


def shape_metrics(t, z, rise, limits):
    after = t >= rise; tt = t[after]; zz = z[after]
    outside = np.where(np.abs(zz-1) > limits['settling_relative'])[0]
    start = int(outside[-1]+1) if len(outside) else 0
    settling = float(tt[start]-rise) if start < len(tt) else None
    peaks, _ = find_peaks(zz, distance=3, prominence=limits['decay_peak_floor']/2)
    peaks = peaks[zz[peaks] > 1+limits['decay_peak_floor']]
    ring = float(np.ptp(zz[peaks[0]:])) if len(peaks) else None
    return {'overshoot_relative': max(0., float(np.max(z)-1)), 'undershoot_relative': min(0., float(np.min(z))),
            'ringing_amplitude_relative': ring, 'settling_s': settling,
            'decay': decay_fit(tt, zz, limits)}


def raw_validity(run, doc, *, baseline=False):
    a = run['trace']; settings = run['settings']; cfg = doc['limits']
    onset = settings['onset_s']; end = settings['duration_s']
    pre = a[(a[:, 0] >= doc['steady_start_s']) & (a[:, 0] < onset)]
    tail = a[a[:, 0] >= end-doc['tail_window_s']]
    def window(x):
        span = np.ptp(x[:, 0]); centered = (x[:, 0]-x[:, 0].mean())/span
        drift = np.polyfit(centered, x[:, 3], 1)[0]
        return {'mean_control_offset_V': float(np.mean(x[:, 3])-settings['initial_control_V']),
                'control_drift_V': float(drift),
                'frequency_error_ppm': float((np.mean(x[:, 12])/80e6-1)*1e6),
                'residual_phase_rad': float(np.mean(x[:, 11])),
                'phase_peak_rad': float(np.max(np.abs(x[:, 11])))}
    if not np.isfinite(a).all() or len(pre) < 100 or len(tail) < 100:
        return {'valid': False, 'reasons': ['nonfinite_or_short_observations']}
    p, q = window(pre), window(tail); reasons = []
    for k in ('mean_control_offset_V', 'control_drift_V', 'frequency_error_ppm'):
        if abs(p[k]) > cfg[k]:
            reasons.append('pre_'+k)
    if p['phase_peak_rad'] > cfg['baseline_phase_peak_rad']:
        reasons.append('pre_phase_peak')
    for k in ('control_drift_V', 'frequency_error_ppm'):
        if abs(q[k]) > cfg[k]:
            reasons.append('tail_'+k)
    residual_limit = max(cfg['settling_relative']*abs(settings['amplitude_rad']), cfg['absolute_phase_floor_rad'])
    if abs(q['residual_phase_rad']) > residual_limit:
        reasons.append('tail_residual_phase')
    if np.max(np.abs(a[:, 11])) > (cfg['baseline_phase_peak_rad'] if baseline else cfg['phase_peak_rad']):
        reasons.append('phase_peak')
    for key in ('clamps', 'near_rail_samples', 'slips'):
        if run['summary'][key]:
            reasons.append(key)
    return {'valid': not reasons, 'reasons': reasons, 'pre': p, 'tail': q,
            'clamps': run['summary']['clamps'], 'near_rail_samples': run['summary']['near_rail_samples'],
            'cycle_slips': run['summary']['slips'], 'residual_limit_rad': residual_limit}


def m1_actual_input(parameters, run):
    """M1 only in posthoc comparator; uses existing model coefficients, actual input."""
    from pll_allocation.physics_mapping.model import evaluate
    result = evaluate(parameters).as_dict()
    if result['status'] != 'OK':
        raise ValueError('M1 invalid for posthoc response')
    a, b, c, d = result['factors']['F_LOOP']['characteristic_descending']
    scale = 1e-6
    trace = run['trace']; delta = trace[1, 0]-trace[0, 0]
    times = np.arange(int(np.floor(trace[-1, 0]/delta))+1)*delta
    input_phase = np.interp(times, trace[:, 0], trace[:, 2])
    _, y, _ = lsim(TransferFunction([c/scale, d], [a/scale**3, b/scale**2, c/scale, d]),
                   U=input_phase, T=times/scale, interp=True)
    return times, y


def analyze(parameters, run, zero, doc):
    valid = raw_validity(run, doc); base = raw_validity(zero, doc, baseline=True)
    if not valid['valid'] or not base['valid']:
        return {'status': 'UNKNOWN', 'raw_validity': valid, 'baseline_validity': base}, None
    a = run['trace']; b = zero['trace']; settings = run['settings']; amp = settings['amplitude_rad']
    if not np.array_equal(a[:, 0], b[:, 0]):
        raise ValueError('baseline time grid mismatch')
    onset = settings['onset_s']; cycle = doc['cycle_s']
    n = int(np.floor((a[-1, 0]-onset)/cycle+1e-9)); edges = onset+np.arange(n+1)*cycle
    t = (edges[:-1]+edges[1:])/2-onset
    y = cycle_average(a[:, 0], a[:, 1]-b[:, 1], edges)[:, 0]/amp
    r = cycle_average(a[:, 0], a[:, 2], edges)[:, 0]/amp
    mt, my = m1_actual_input(parameters, run)
    # Last output edge can exceed FOH grid only by one record interval; restrict equally.
    keep = edges <= mt[-1]+1e-15; edges = edges[keep]; t = t[:len(edges)-1]
    y = y[:len(t)]; r = r[:len(t)]
    m1 = cycle_average(mt, my, edges)[:, 0]/amp
    cfg = doc['limits']; m2metrics = shape_metrics(t, y, settings['rise_s'], cfg)
    m1metrics = shape_metrics(t, m1, settings['rise_s'], cfg)
    delta = y-m1
    sd = None if m2metrics['settling_s'] is None or m1metrics['settling_s'] is None else abs(m2metrics['settling_s']-m1metrics['settling_s'])
    compare = {'normalized_RMSE': float(np.sqrt(np.mean(delta**2))), 'max_normalized_error': float(np.max(np.abs(delta))),
               'overshoot_absolute_difference': abs(m2metrics['overshoot_relative']-m1metrics['overshoot_relative']),
               'settling_absolute_difference_s': sd}
    compare['supported'] = bool(compare['normalized_RMSE'] <= cfg['M1_time_RMSE']
        and compare['max_normalized_error'] <= cfg['M1_time_max_error']
        and compare['overshoot_absolute_difference'] <= cfg['M1_overshoot_absolute']
        and sd is not None and sd <= max(cfg['M1_settling_floor_s'], cfg['M1_settling_relative']*m1metrics['settling_s']))
    phase_peak = float(np.max(np.abs((a[:, 11]-b[:, 11]))))
    result = {'status': 'MEASURED', 'raw_validity': valid, 'baseline_validity': base,
              'peak_phase_deviation_rad': phase_peak, 'M2': m2metrics, 'M1_posthoc': m1metrics,
              'comparison': compare, 'lock_retention_recovery': 'RECOVERED_WITHIN_LOCAL_WINDOW' if m2metrics['settling_s'] is not None else 'NOT_ESTABLISHED',
              'scope': 'local phase-step recovery, not cold-start lock time or independent PM measurement'}
    return result, np.column_stack([t, r, y, m1])


def compare_refinements(results, curves, doc):
    base = results['plus']; reference = curves['plus']; rows = []; cfg = doc['limits']
    for key, result in results.items():
        if key == 'plus':
            continue
        if result['status'] != 'MEASURED' or base['status'] != 'MEASURED':
            rows.append({'variant': key, 'converged': False, 'reason': 'invalid measurements'}); continue
        t = reference[:, 0]; mask = t <= curves[key][-1, 0]
        delta = np.interp(t[mask], curves[key][:, 0], curves[key][:, 2])-reference[mask, 2]
        rmse = float(np.sqrt(np.mean(delta**2))); maximum = float(np.max(np.abs(delta)))
        overshoot = abs(result['M2']['overshoot_relative']-base['M2']['overshoot_relative'])
        sa, sb = base['M2']['settling_s'], result['M2']['settling_s']
        sd = abs(sa-sb) if sa is not None and sb is not None else None
        rate_a, rate_b = base['M2']['decay']['rate_per_s'], result['M2']['decay']['rate_per_s']
        rate_diff = abs(rate_a/rate_b-1) if rate_a and rate_b else None
        ok = (rmse <= cfg['refinement_RMSE'] and maximum <= cfg['refinement_max_error']
              and overshoot <= cfg['refinement_overshoot'] and sd is not None
              and sd <= max(cfg['refinement_settling_floor_s'], cfg['refinement_settling_relative']*sa)
              and (rate_diff is None or rate_diff <= cfg['decay_refinement_relative']))
        rows.append({'variant': key, 'normalized_RMSE': rmse, 'max_error': maximum,
                     'overshoot_difference': overshoot, 'settling_difference_s': sd,
                     'decay_relative_difference': rate_diff, 'converged': bool(ok)})
    return {'converged': all(r['converged'] for r in rows), 'checks': rows,
            'decay_not_identifiable': [k for k, r in results.items() if r.get('M2', {}).get('decay', {}).get('status') != 'MEASURED']}
