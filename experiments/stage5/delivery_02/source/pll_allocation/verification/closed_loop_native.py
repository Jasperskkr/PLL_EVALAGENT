"""Actual event-loop smooth reference phase steps. No M1 response calculations."""
import ctypes
import hashlib
import json
import math
from pathlib import Path
import time
import numpy as np

HERE = Path(__file__).resolve().parent
BUILD = HERE/'build_stage4_1_r2'
MODEL = 'edge_euler_reference_phase_step_stage4_1_0.1'
COLUMNS = ['time_s', 'divided_phase_offset_rad', 'reference_phase_offset_rad', 'vctrl_V',
           'vc2_V', 'clamps', 'PFD_up', 'PFD_down', 'CP_cumulative_charge_C',
           'reference_unwrapped_rad', 'divided_unwrapped_rad', 'phase_error_unwrapped_rad',
           'instantaneous_output_frequency_Hz', 'cycle_slips', 'near_rail_samples',
           'wrap_branch', 'reference_edge_count', 'divided_edge_count']


def identity(build=BUILD):
    return {name: hashlib.sha256((HERE/name).read_bytes()).hexdigest()
            for name in ('kernel.cpp', 'closed_loop_kernel.cpp')} | {
                'closed_loop.dll': hashlib.sha256((Path(build)/'closed_loop.dll').read_bytes()).hexdigest()}


def simulate_step(parameters, *, amplitude_rad=.01, dt_s=.4e-9, onset_s=40e-6,
                  rise_s=.5e-6, duration_s=120e-6, record_interval_s=10e-9, original_export=False):
    from .simulator import validate_parameters
    from .resources import CONFIGS
    from pll_allocation.block_space.contracts import check_parameters, load_model
    p = validate_parameters(parameters)
    domain = check_parameters(load_model(CONFIGS/'BLOCK_SPACE_MODEL_V1.json'), parameters)
    if domain['declared_domain'] != 'IN_DECLARED_DOMAIN' or domain['model_validity'] != 'VALID':
        raise ValueError('OUT_OF_DOMAIN: frozen Block Space')
    settings = dict(amplitude_rad=amplitude_rad, dt_s=dt_s, onset_s=onset_s, rise_s=rise_s,
                    duration_s=duration_s, record_interval_s=record_interval_s)
    if not all(type(v) in (int, float) and math.isfinite(v) for v in settings.values()):
        raise ValueError('finite phase-step settings required')
    if not (abs(amplitude_rad) <= .02 and 0 < dt_s <= .4e-9 and dt_s <= record_interval_s <= 10e-9
            and 0 < rise_s and 0 <= onset_s < onset_s+rise_s < duration_s
            and abs(amplitude_rad)/(4*rise_s) < p['f_ref']):
        raise ValueError('OUT_OF_DOMAIN: phase-step stimulus/time domain')
    if original_export and amplitude_rad != 0:
        raise ValueError('original export supports only zero stimulus equivalence')
    initial = (p['N']*p['f_ref']-p['f0'])/p['Kvco']
    if not 0 < initial < 1.2 or (p['f_ref'], p['N'], p['Vctrl_min'], p['Vctrl_max']) != (10e6, 8, 0, 1.2):
        raise ValueError('OUT_OF_DOMAIN: fixed timing/rails/interior tuning')
    fmax = p['f0']+1.2*p['Kvco']
    if dt_s*(p['C1']+p['C2'])/(p['Rz']*p['C1']*p['C2']) > .05 or dt_s*max(p['f_ref'], fmax/p['N']) > .02:
        raise ValueError('OUT_OF_DOMAIN: integration resolution')
    saved = json.loads((BUILD/'identity.json').read_text(encoding='utf-8'))
    if identity() != saved['sha256']:
        raise RuntimeError('STAGE41_NATIVE_SOURCE_OR_BINARY_MISMATCH')
    n = math.ceil(duration_s/dt_s)+1
    if n > 200000000:
        raise ValueError('OUT_OF_DOMAIN: integration budget')
    stride = max(1, int(record_interval_s/(duration_s/(n-1))))
    count = (n-1)//stride+2; edgecap = math.ceil(duration_s*max(p['f_ref'], fmax/p['N']))+100
    trace = np.empty((count, 6 if original_export else len(COLUMNS)), dtype=np.float64)
    ref = np.empty(edgecap); div = np.empty(edgecap); stats = np.empty(15)
    eventcap = 20000; events = np.empty((eventcap, 3))
    values = np.array([p['f_ref'], p['N'], p['Icp'], p['Rz'], p['C1'], p['C2'], p['f0'], p['Kvco'],
                       0., 1.2, initial, duration_s, dt_s, amplitude_rad, 0., onset_s, record_interval_s,
                       rise_s], dtype=np.float64)
    lib = ctypes.CDLL(str(BUILD/'closed_loop.dll'))
    fn = lib.simulate if original_export else lib.simulate_closed_loop
    ptr = ctypes.POINTER(ctypes.c_double)
    fn.argtypes = [ptr, ptr, ctypes.c_longlong, ptr, ptr, ctypes.c_longlong, ptr]
    if not original_export:
        fn.argtypes += [ptr, ctypes.c_longlong]
    fn.restype = ctypes.c_int
    args = [values.ctypes.data_as(ptr), trace.ctypes.data_as(ptr), count, ref.ctypes.data_as(ptr),
            div.ctypes.data_as(ptr), edgecap, stats.ctypes.data_as(ptr)]
    if not original_export:
        args += [events.ctypes.data_as(ptr), eventcap]
    start = time.perf_counter(); code = fn(*args); elapsed = time.perf_counter()-start
    if code:
        raise RuntimeError('STAGE41_NATIVE_FAILURE:'+str(code))
    return {'trace': trace[:int(stats[2])].copy(), 'ref_edges': ref[:int(stats[10])].copy(),
            'div_edges': div[:int(stats[11])].copy(),
            'events': events[:int(stats[14])].copy() if not original_export else np.empty((0, 3)),
            'settings': settings | {'initial_control_V': initial, 'actual_dt_s': float(stats[1]),
                                    'phase_units': 'divided_reference_rate_rad'},
            'summary': {'integration_points': int(stats[0]), 'clamps': int(stats[3]),
                        'near_rail_samples': int(stats[4]), 'slips': int(stats[13]) if not original_export else None,
                        'native_elapsed_s': elapsed, 'source_hashes': saved['sha256'], 'model_version': MODEL},
            'columns': COLUMNS if not original_export else COLUMNS[:6],
            'event_columns': ['time_s', 'kind_1_clamp_2_near_rail_3_slip', 'unclamped_voltage_or_branch_delta']}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(); parser.add_argument('--record-build', type=Path, required=True)
    args = parser.parse_args()
    with (args.record_build/'identity.json').open('x', encoding='utf-8') as stream:
        json.dump({'sha256': identity(args.record_build), 'model_version': MODEL,
                   'compiler': 'MSVC2022 x64 C++17 /O2 /EHsc /LD'}, stream, indent=2)
