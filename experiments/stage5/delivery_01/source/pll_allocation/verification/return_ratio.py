"""Measured phase-port return ratios, sidebands and crossings; no M1 calculations."""
from copy import deepcopy
import math
from pathlib import Path
import time
import numpy as np
from .experiments import read, write
from .resources import CONFIGS
from .return_ratio_native import simulate_port


def protocol():
    return read(CONFIGS/'verification/return_ratio_stage4_v0_2.json')


def phasor_fit(t, signals, frequency, *, sidebands=True):
    """exp(+jwt) phasors; DC/trend retained explicitly, never forced to match M1."""
    freqs = [frequency*h for h in (1, 2, 3)]
    if sidebands:
        freqs += [k*10e6+sign*frequency for k in (1, 2) for sign in (-1, 1)]
    matrix = np.column_stack([np.ones(len(t)), (t-np.mean(t))/np.ptp(t)] +
        [v for f in freqs for v in (np.cos(2*np.pi*f*t), np.sin(2*np.pi*f*t))])
    coeff, _, rank, _ = np.linalg.lstsq(matrix, signals, rcond=None)
    if rank != matrix.shape[1]:
        raise ValueError('rank deficient frequency/harmonic fit')
    phasors = coeff[2::2]-1j*coeff[3::2]
    residual = np.sqrt(np.mean((signals-matrix@coeff)**2, axis=0))
    return phasors, residual, coeff[:2]


def extract_pair(positive, negative, doc):
    cfg = doc['limits']
    a, b = positive['trace'], negative['trace']
    if a.shape != b.shape or not np.array_equal(a[:, 0], b[:, 0]):
        raise ValueError('positive/negative trajectories have different time grids')
    settings = positive['settings']; f = settings['frequency_Hz']
    begin = settings['onset_s']+max(doc['minimum_discard_s'], doc['discard_cycles']/f)
    keep = (a[:, 0] >= begin)&(a[:, 0] < settings['duration_s'])
    t = a[keep, 0]
    if len(t) < 100 or np.ptp(t)*f < doc['measurement_cycles']-.1:
        raise ValueError('insufficient measurement samples or cycles')
    if not np.isfinite(a).all() or not np.isfinite(b).all() or np.any(np.diff(t) <= 0):
        raise ValueError('nonfinite or unordered phase-port observations')
    if (2*10e6+f)*np.max(np.diff(t)) >= .5:
        raise ValueError('carrier sideband observation violates Nyquist')
    # Columns: y raw divider phase, x actual feedback/PFD phase, independent d.
    odd = (a[keep][:, [1, 7, 6]]-b[keep][:, [1, 7, 6]])/2
    ph, residual, trend = phasor_fit(t, odd, f)
    Y, X, D = ph[0]
    if min(abs(X), abs(D)) < 1e-8:
        return {'status': 'UNKNOWN', 'frequency_Hz': f, 'reasons': ['unobservable phase-port denominator']}
    L = -Y/X
    halves = []
    for select in (slice(0, len(t)//2), slice(len(t)//2, len(t))):
        h, _, _ = phasor_fit(t[select], odd[select], f)
        halves.append(-h[0, 0]/h[0, 1])
    thd = float(np.linalg.norm(ph[1:3, 0])/abs(Y))
    sideband = float(np.linalg.norm(ph[3:, 0])/abs(Y))
    drift = []; offset = []; freqerr = []; maxerror = []; charge = []; edgecounts = []
    for run in (positive, negative):
        z = run['trace'][keep]; time_span = z[-1, 0]-z[0, 0]
        voltage, _, dc = phasor_fit(t, z[:, 3:4], f)
        offset.append(float(dc[0, 0]-settings.get('linearization_control_V', settings['initial_control_V'])))
        drift.append(float(dc[1, 0]))
        freqerr.append(float((z[-1, 1]-z[0, 1])/(2*np.pi*time_span*10e6)*1e6))
        maxerror.append(float(np.max(np.abs(z[:, 7]))))
        charge.append(float(z[-1, 10]-z[0, 10]))
        edgecounts.append({'ref': len(run['ref_edges']), 'feedback': len(run['div_edges'])})
    quality = {'THD': thd, 'sideband_RSS_relative': sideband,
        'residual_relative': float(residual[0]/abs(Y)),
        'half_window_complex': abs(halves[1]-halves[0])/abs(L),
        'loop_error_peak_rad': max(maxerror), 'mean_control_offset_V': max(abs(x) for x in offset),
        'control_drift_V': max(abs(x) for x in drift), 'frequency_error_ppm': max(abs(x) for x in freqerr),
        'clamp_events': sum(r['summary']['clamps'] for r in (positive, negative))}
    reasons = [k for k in ('THD', 'half_window_complex', 'residual_relative', 'loop_error_peak_rad',
        'mean_control_offset_V', 'control_drift_V', 'frequency_error_ppm') if quality[k] > cfg[k]]
    if quality['clamp_events']:
        reasons.append('clamp_events')
    # Sidebands are independently reported, never silently assumed negligible.
    if sideband > cfg['sideband_RSS_relative']:
        reasons.append('sideband_coupling')
    encode = lambda z: [float(z.real), float(z.imag)]
    return {'status': 'MEASURED' if not reasons else 'UNKNOWN', 'reasons': reasons, 'frequency_Hz': f,
        'L_complex': encode(L), 'magnitude': abs(L), 'phase_deg': float(np.angle(L, deg=True)),
        'phasors': {'return_Y': encode(Y), 'actual_feedback_X': encode(X), 'disturbance_D': encode(D)},
        'quality': quality, 'settings': settings, 'measurement_window_s': [begin, settings['duration_s']],
        'raw_DC_diagnostics': {'voltage_offset_V': offset, 'voltage_drift_V': drift,
            'frequency_offset_ppm': freqerr, 'CP_charge_C': charge, 'phase_trend_rad': trend[1].tolist(),
            'edge_counts': edgecounts},
        'return_sidebands': [encode(x) for x in ph[3:, 0]],
        'sideband_frequencies_Hz': [k*10e6+s*f for k in (1, 2) for s in (-1, 1)],
        'definition': '-raw_return_Y / actual_PFD_feedback_X; exp(+jwt), reference-rate rad',
        'method': settings['mode'], 'M1_used_for_measurement': False}


def crossings(points, *, require_valid=True):
    """Never bridge an invalid frequency or silently select one of multiple crossings."""
    points = sorted(points, key=lambda p: p['frequency_Hz'])
    if len(points) < 2:
        return {'status': 'UNKNOWN', 'reason': 'insufficient frequencies'}
    phases = np.unwrap(np.radians([p.get('phase_deg', 0.) for p in points]))
    candidates = []
    for i, (a, b) in enumerate(zip(points, points[1:])):
        if require_valid and (a['status'] != 'MEASURED' or b['status'] != 'MEASURED'):
            continue
        down = a.get('magnitude', 0) >= 1 > b.get('magnitude', 2)
        up = a.get('magnitude', 0) < 1 <= b.get('magnitude', 2)
        if down or up:
            alpha = -math.log(a['magnitude'])/math.log(b['magnitude']/a['magnitude'])
            freq = a['frequency_Hz']*(b['frequency_Hz']/a['frequency_Hz'])**alpha
            phase = math.degrees(phases[i]+alpha*(phases[i+1]-phases[i]))
            candidates.append({'UGF_Hz': freq, 'PM_deg': 180+phase,
                'phase_deg': phase, 'bracket_Hz': [a['frequency_Hz'], b['frequency_Hz']],
                'bracket_relative_width': b['frequency_Hz']/a['frequency_Hz']-1,
                'direction': 'downward' if down else 'upward'})
    if len(candidates) != 1 or candidates[0]['direction'] != 'downward':
        return {'status': 'UNKNOWN', 'reason': 'no unique valid downward unity crossing', 'crossings': candidates}
    return {'status': 'MEASURED_BRACKETED', **candidates[0], 'crossings_found': 1,
            'interpretation': 'fundamental phase-port ratio; not a Floquet stability certificate'}


def point(folder, parameters, frequency, *, mode='series', amplitude=.01, dt=.4e-9, cycles=12, doc=None):
    doc = deepcopy(doc or protocol()); folder = Path(folder)
    if not 0 < frequency <= doc['maximum_frequency_Hz']:
        raise ValueError('OUT_OF_DOMAIN: phase-port sweep frequency exceeds research protocol; high-frequency probes use a separate plan')
    folder.mkdir(parents=True, exist_ok=False)
    settings = {'frequency_Hz': frequency, 'mode': mode, 'dt_s': dt, 'onset_s': doc['onset_s'],
        'record_interval_s': doc['record_interval_s'],
        'duration_s': doc['onset_s']+max(doc['minimum_discard_s'], doc['discard_cycles']/frequency)+cycles/frequency}
    write(folder/'request.json', {'parameters': parameters, 'settings': settings, 'paired_amplitudes_rad': [amplitude, -amplitude]})
    start = time.perf_counter(); runs = []
    try:
        for i, sign in enumerate((1, -1)):
            run = simulate_port(parameters, amplitude_rad=sign*amplitude, **settings)
            if mode == 'clamp' and doc.get('measured_DC_initialization', False):
                np.savez_compressed(folder/f'pilot_{i}.npz', **{k: run[k] for k in ('trace', 'ref_edges', 'div_edges')})
                write(folder/f'pilot_summary_{i}.json', {'summary': run['summary'], 'settings': run['settings']})
                begin = settings['onset_s']+max(doc['minimum_discard_s'], doc['discard_cycles']/frequency)
                z = run['trace']; z = z[(z[:, 0] >= begin)&(z[:, 0] < settings['duration_s'])]
                _, _, dc = phasor_fit(z[:, 0], z[:, 3:4], frequency)
                corrected = run['settings']['initial_control_V']-(float(dc[0, 0])-run['settings']['linearization_control_V'])
                write(folder/f'DC_initialization_{i}.json', {'method': 'pilot measured mean control offset subtracted from initial v/u; original equations unchanged',
                    'pilot_mean_control_V': float(dc[0, 0]), 'corrected_initial_control_V': corrected,
                    'M1_response_used': False, 'no_iterative_threshold_tuning': True})
                run = simulate_port(parameters, amplitude_rad=sign*amplitude, initial_control_V=corrected, **settings)
            runs.append(run)
            np.savez_compressed(folder/f'trajectory_{i}.npz', **{k: run[k] for k in ('trace', 'ref_edges', 'div_edges')})
            write(folder/f'summary_{i}.json', {'summary': run['summary'], 'settings': run['settings']})
        result = extract_pair(*runs, doc)
        write(folder/'measurement.json', result)
        return result
    except Exception as error:
        write(folder/'failure.json', {'status': 'UNKNOWN', 'error_type': type(error).__name__,
            'reason': str(error), 'elapsed_s': time.perf_counter()-start, 'completed_native_runs': len(runs)})
        raise


def sweep(folder, parameters, *, mode='series', amplitude=.01, dt=.4e-9, cycles=12, grid=None, doc=None):
    doc = deepcopy(doc or protocol()); folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    grid = grid if grid is not None else doc['grid_Hz']
    write(folder/'plan.json', {'protocol': doc, 'parameters': parameters, 'mode': mode,
        'amplitude': amplitude, 'dt': dt, 'cycles': cycles, 'grid_Hz': grid,
        'refinement': 'measured unity crossing only; no M1 imports'})
    points = [point(folder/f'grid_{i:02d}', parameters, f, mode=mode, amplitude=amplitude,
        dt=dt, cycles=cycles, doc=doc) for i, f in enumerate(grid)]
    crossing = crossings(points)
    for i in range(doc['max_refinements']):
        if crossing['status'] != 'MEASURED_BRACKETED' or crossing['bracket_relative_width'] <= doc['crossing_bracket_relative_width']:
            break
        lo, hi = crossing['bracket_Hz']; f = math.sqrt(lo*hi)
        points.append(point(folder/f'refine_{i:02d}', parameters, f, mode=mode, amplitude=amplitude,
            dt=dt, cycles=cycles, doc=doc))
        crossing = crossings(points)
    result = {'points': sorted(points, key=lambda p: p['frequency_Hz']), 'crossing': crossing,
        'M1_used_for_measurement': False}
    write(folder/'result.json', result)
    return result
