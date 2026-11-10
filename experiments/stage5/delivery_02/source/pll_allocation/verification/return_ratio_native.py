"""Independent Stage4 phase-port event backend. No M1 response or allocator imports."""
import ctypes
import hashlib
import json
import math
from pathlib import Path
import time
import numpy as np

HERE = Path(__file__).resolve().parent
BUILD = HERE/'build_stage4'
MODEL = 'edge_euler_phase_port_stage4_0.1'


def identity(build=BUILD):
    return {str(p.relative_to(HERE)) if p.parent == HERE else 'return_ratio.dll': hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (HERE/'kernel.cpp', HERE/'return_ratio_kernel.cpp', Path(build)/'return_ratio.dll')}


def simulate_port(parameters, *, frequency_Hz, amplitude_rad=.01, mode='series', dt_s=.4e-9,
                  onset_s=20e-6, duration_s=200e-6, record_interval_s=10e-9, original_export=False,
                  initial_control_V=None):
    from .simulator import validate_parameters
    from .resources import CONFIGS
    from pll_allocation.block_space.contracts import check_parameters, load_model
    domain = check_parameters(load_model(CONFIGS/'BLOCK_SPACE_MODEL_V1.json'), parameters)
    if domain['declared_domain'] != 'IN_DECLARED_DOMAIN' or domain['model_validity'] != 'VALID':
        raise ValueError('OUT_OF_DOMAIN: candidate outside frozen Stage1.5 model')
    p = validate_parameters(parameters)
    if mode not in ('series', 'clamp'):
        raise ValueError('unsupported phase-port mode')
    if (p['f_ref'], p['N'], p['Vctrl_min'], p['Vctrl_max']) != (10e6, 8, 0, 1.2):
        raise ValueError('OUT_OF_DOMAIN: fixed phase-port timing/rails')
    if not all(type(x) in (float, int) and math.isfinite(x) for x in
               (frequency_Hz, amplitude_rad, dt_s, onset_s, duration_s, record_interval_s)):
        raise ValueError('finite phase-port settings required')
    if not (0 < frequency_Hz < 30e6 and abs(amplitude_rad)*frequency_Hz < p['f_ref']
            and 0 < dt_s <= .4e-9 and 0 <= onset_s < duration_s and dt_s <= record_interval_s):
        raise ValueError('OUT_OF_DOMAIN: nonmonotonic drive or invalid time settings')
    vreq = (p['N']*p['f_ref']-p['f0'])/p['Kvco']
    if not 0 < vreq < 1.2:
        raise ValueError('OUT_OF_DOMAIN: no interior static tuning point')
    initial = vreq if initial_control_V is None else initial_control_V
    if not math.isfinite(initial) or not 0 < initial < 1.2 or (initial_control_V is not None and mode != 'clamp'):
        raise ValueError('OUT_OF_DOMAIN: observed DC restoration is only supported for open clamp')
    if dt_s*(p['C1']+p['C2'])/(p['Rz']*p['C1']*p['C2']) > .05:
        raise ValueError('OUT_OF_DOMAIN: LF resolution')
    saved = json.loads((BUILD/'identity.json').read_text(encoding='utf-8'))
    if identity() != saved['sha256']:
        raise RuntimeError('STAGE4_NATIVE_SOURCE_OR_BINARY_MISMATCH')
    n = math.ceil(duration_s/dt_s)+1
    stride = max(1, int(record_interval_s/(duration_s/(n-1))))
    count = (n-1)//stride+2
    edgecap = math.ceil(duration_s*max(p['f_ref'], (p['f0']+p['Kvco']*1.2)/p['N']))+100
    columns = 6 if original_export else 12
    trace = np.empty((count, columns), dtype=np.float64)
    ref = np.empty(edgecap); div = np.empty(edgecap); stats = np.empty(13)
    values = np.array([p['f_ref'], p['N'], p['Icp'], p['Rz'], p['C1'], p['C2'], p['f0'], p['Kvco'],
        0, 1.2, initial, duration_s, dt_s, 0., frequency_Hz, onset_s, record_interval_s,
        amplitude_rad, 0. if mode == 'series' else 1.], dtype=np.float64)
    library = ctypes.CDLL(str(BUILD/'return_ratio.dll'))
    fn = library.simulate if original_export else library.simulate_return_ratio
    ptr = ctypes.POINTER(ctypes.c_double)
    fn.argtypes = [ptr, ptr, ctypes.c_longlong, ptr, ptr, ctypes.c_longlong, ptr]
    fn.restype = ctypes.c_int
    start = time.perf_counter()
    code = fn(values.ctypes.data_as(ptr), trace.ctypes.data_as(ptr), count,
        ref.ctypes.data_as(ptr), div.ctypes.data_as(ptr), edgecap, stats.ctypes.data_as(ptr))
    if code:
        raise RuntimeError('STAGE4_NATIVE_FAILURE:'+str(code))
    return {'trace': trace[:int(stats[2])].copy(), 'ref_edges': ref[:int(stats[10])].copy(),
        'div_edges': div[:int(stats[11])].copy(), 'summary': {'integration_points': int(stats[0]),
        'actual_dt_s': float(stats[1]), 'clamps': int(stats[3]), 'vfinal_V': float(stats[8]),
        'elapsed_s': time.perf_counter()-start, 'model_version': MODEL, 'source_hashes': saved['sha256']},
        'settings': {'frequency_Hz': frequency_Hz, 'amplitude_rad': amplitude_rad, 'mode': mode,
            'dt_s': dt_s, 'onset_s': onset_s, 'duration_s': duration_s, 'record_interval_s': record_interval_s,
            'initial_control_V': initial, 'linearization_control_V': vreq,
            'phase_normalization': 'divided_reference_rate_rad'}}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--record-build', type=Path, required=True)
    args = parser.parse_args()
    with (args.record_build/'identity.json').open('x', encoding='utf-8') as stream:
        json.dump({'sha256': identity(args.record_build), 'compiler': 'MSVC2022 x64 C++17 /O2 /EHsc /LD',
                   'model_version': MODEL}, stream, indent=2)
