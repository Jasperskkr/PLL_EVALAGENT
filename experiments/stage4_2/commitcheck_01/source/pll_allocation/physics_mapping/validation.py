"""Reproducible Stage 1 numerical comparisons, never a transient TB or MATLAB run."""
from __future__ import annotations
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import sys
from .experiment import judge_experiment, load_experiment, parameters_from_experiment
from .model import FrequencyScan, Status, evaluate, fingerprint

HISTORICAL_ANCHOR = {
    'Vctrl_required_V': 0.4, 'UGF_Hz': 138176.4411317168,
    'BW_Hz': 222379.18349260243, 'PM_deg': 56.44269021253223,
}
ANCHOR_SOURCE = ('MATLAB v3.4 results/python_crosscheck_results.json; historical '
                 'INDEPENDENT_PYTHON_REPRODUCTION_ONLY; MATLAB_RUNTIME_NOT_EXECUTED; '
                 'source SHA in docs/physics_mapping_stage1/audit/source_manifest.json')


def _positive_root(coefficients):
    """Single positive root in omega^2, linear bisection; independent of M1 scan."""
    def polynomial(x):
        total = 0
        for coefficient in coefficients:
            total = total*x+coefficient
        return total
    low, high = 0., 1.
    for _ in range(100):
        if polynomial(high) > 0:
            break
        high *= 10
    else:
        raise ArithmeticError('oracle could not bracket polynomial root')
    for _ in range(160):
        middle = (low+high)/2
        if polynomial(middle) > 0:
            high = middle
        else:
            low = middle
    return (low+high)/2


def polynomial_reference(parameters):
    """Independent magnitude equations, not a second physics ground truth.

    For x=w² and L=K0*(1+s/wz)/(s²*(1+s/wp)), solve:
    unity: x³/wp²+x²-K0²*x/wz²-K0²=0
    -3dB: x³/wp²+(1-2K0/(wz*wp))*x²-(2K0+K0²/wz²)*x-K0²=0.
    Both have one positive root (one coefficient sign change). No model imports.
    """
    p = {name: item['value'] for name, item in parameters['values'].items()}
    wz = 1/(p['Rz']*p['C2'])
    wp = (p['C1']+p['C2'])/(p['Rz']*p['C1']*p['C2'])
    k0 = p['Icp']*p['Kvco']/(p['N']*(p['C1']+p['C2']))
    wu = math.sqrt(_positive_root([1/wp**2, 1, -k0**2/wz**2, -k0**2]))
    wb = math.sqrt(_positive_root([1/wp**2, 1-2*k0/(wz*wp), -2*k0-k0**2/wz**2, -k0**2]))
    return {'UGF_Hz': wu/(2*math.pi), 'BW_Hz': wb/(2*math.pi),
            'PM_deg': math.degrees(math.atan(wu/wz)-math.atan(wu/wp)),
            'Vctrl_required_V': (p['N']*p['f_ref']-p['f0'])/p['Kvco']}


def compare(actual, reference):
    checks = {}
    for name, expected in reference.items():
        delta = abs(actual[name]-expected)
        error = delta/abs(expected) if name in {'UGF_Hz', 'BW_Hz'} else delta
        limit = .005 if name in {'UGF_Hz', 'BW_Hz'} else .2 if name == 'PM_deg' else 1e-6
        checks[name] = {'actual': actual[name], 'reference': expected, 'error': error,
                        'error_kind': 'relative' if name in {'UGF_Hz', 'BW_Hz'} else 'absolute',
                        'limit': limit, 'satisfied': error <= limit}
    return checks


def write_new(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def run_stage1(config, out):
    exp = load_experiment(config)
    initial = parameters_from_experiment(exp)
    # All default and perturbation candidates are written before any model evaluation.
    candidates = {'default': initial}
    perturbations = {'Icp_up_20pct': {'Icp': 120e-6}, 'Rz_up_to_4500': {'Rz': 4500},
                     'Kvco_up_25pct': {'Kvco': 25e6},
                     'Icp_Kvco_product_invariant': {'Icp': 140e-6, 'Kvco': 20e6/1.4}}
    candidates.update({name: parameters_from_experiment(exp, changes) for name, changes in perturbations.items()})
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    write_new(out/'experiment_snapshot.json', exp)
    write_new(out/'candidate_snapshots.json', candidates)
    comparisons, results = {}, {}
    all_checks = []
    for name, candidate in candidates.items():
        result = evaluate(candidate, response_frequencies_Hz=(1e3, 1e4, 1e5, 1e6, 1e7))
        results[name] = result.as_dict()
        if result.status != Status.OK:
            raise ArithmeticError(name + ': ' + result.reason)
        oracle = polynomial_reference(candidate)
        checks = compare(result.metrics, oracle)
        record = {'parameters': candidate, 'result': result.as_dict(), 'reference': oracle,
                  'reference_source': 'independent omega-squared magnitude polynomial; validation.polynomial_reference',
                  'comparisons': checks, 'draft_judgment': judge_experiment(exp, candidate, result)}
        if name == 'default':
            record['historical_source'] = ANCHOR_SOURCE
            record['historical_comparisons'] = compare(result.metrics, HISTORICAL_ANCHOR)
            all_checks += [x['satisfied'] for x in record['historical_comparisons'].values()]
        comparisons[name] = record
        all_checks += [x['satisfied'] for x in checks.values()]
    baseline = results['default']['metrics']
    invariant = results['Icp_Kvco_product_invariant']['metrics']
    propagation = {
        'Icp_changes_BW_and_UGF': all(results['Icp_up_20pct']['metrics'][k] > baseline[k] for k in ('BW_Hz', 'UGF_Hz')),
        'Rz_changes_all_loop_metrics': all(abs(results['Rz_up_to_4500']['metrics'][k]-baseline[k]) > 1e-6 for k in ('BW_Hz', 'UGF_Hz', 'PM_deg')),
        'Kvco_changes_BW_UGF_and_tuning': all(results['Kvco_up_25pct']['metrics'][k] > baseline[k] for k in ('BW_Hz', 'UGF_Hz')) and results['Kvco_up_25pct']['metrics']['Vctrl_required_V'] < baseline['Vctrl_required_V'],
        'Icp_Kvco_product_preserves_loop_metrics': all(math.isclose(invariant[k], baseline[k], rel_tol=1e-10) for k in ('BW_Hz', 'UGF_Hz', 'PM_deg')),
    }
    all_checks += list(propagation.values())
    # Invalid tests deliberately bypass the declared space to exercise model gates.
    failures = {}
    cases = [
        ('no_tuning_point', {'f0': 40e6}, None, Status.OUT_OF_DOMAIN),
        ('rail_tuning_point', {'f0': 80e6}, None, Status.OUT_OF_DOMAIN),
        ('negative_Icp', {'Icp': -100e-6}, None, Status.OUT_OF_DOMAIN),
        ('wrong_Kvco_unit', {}, 'unit', Status.OUT_OF_DOMAIN),
        ('cp_mismatch', {'CP_mismatch': .1}, None, Status.UNSUPPORTED),
        ('cp_leakage', {'CP_leakage': 1e-9}, None, Status.UNSUPPORTED),
        ('pfd_reset', {'PFD_reset_delay': 1e-9}, None, Status.UNSUPPORTED),
        ('q0_balance', {'q0': 1e-15}, None, Status.UNSUPPORTED),
        ('vco_curvature', {'Kvco2': 1e6}, None, Status.UNSUPPORTED),
        ('no_UGF_crossing', {}, 'ugf_scan', Status.NUMERICAL_FAILURE),
        ('no_BW_crossing', {}, 'bw_scan', Status.NUMERICAL_FAILURE),
    ]
    for name, changes, special, expected in cases:
        candidate = deepcopy(initial)
        for key, value in changes.items():
            candidate['values'][key]['value'] = value
        if special == 'unit':
            candidate['values']['Kvco']['unit'] = 'rad/s/V'
        scan = FrequencyScan(1e6, 1e7, 64) if special == 'ugf_scan' else FrequencyScan(1e3, 180e3, 256) if special == 'bw_scan' else FrequencyScan()
        result = evaluate(candidate, scan=scan)
        judged = judge_experiment(exp, candidate, result)
        ok = result.status == expected and not result.metrics and judged['verdict'] == 'UNKNOWN'
        all_checks.append(ok)
        failures[name] = {'parameters': candidate, 'scan': asdict(scan), 'expected_status': expected.value,
                          'result': result.as_dict(), 'draft_judgment': judged, 'satisfied': ok}
    write_new(out/'numerical_comparisons.json', comparisons)
    write_new(out/'failure_cases.json', failures)
    write_new(out/'propagation_checks.json', propagation)
    sources = [Path(config)] + sorted(Path(__file__).parent.glob('*.py'))
    manifest = {'scope': 'PYTHON_M1_NUMERICAL_ACCEPTANCE_ONLY', 'created_utc': datetime.now(timezone.utc).isoformat(),
        'python': sys.version, 'platform': platform.platform(), 'executable': sys.executable,
        'command': sys.argv, 'config_sha256': fingerprint(exp),
        'files': [{'path': str(p.resolve()), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in sources],
        'cost': {'M1_evaluations': len(candidates)+len(cases), 'polynomial_reference_evaluations': len(candidates),
                 'MATLAB_runtime_calls': 0, 'M2_behavioral_TB_calls': 0, 'LLM_calls': 0},
        'numerical_acceptance': 'PASS' if all(all_checks) else 'FAIL', 'verified_joint_block_spec': False}
    write_new(out/'run_manifest.json', manifest)
    lines = ['# Physics Mapping Stage 1 数值验收', '',
             f"数值验收：{manifest['numerical_acceptance']}。仅 Python M1；MATLAB Runtime=0、M2 TB=0、LLM=0。", '',
             '|点|Vreq / V|UGF / Hz|BW / Hz|PM / deg|草案 M1 规格|', '|---|---:|---:|---:|---:|---|']
    for name, row in comparisons.items():
        m = row['result']['metrics']
        lines.append(f"|{name}|{m['Vctrl_required_V']:.9f}|{m['UGF_Hz']:.6f}|{m['BW_Hz']:.6f}|{m['PM_deg']:.8f}|{row['draft_judgment']['verdict']}|")
    lines += ['', '默认点对照为历史 Python 交叉校验记录；扰动点对照为本次独立幅度多项式求根。',
              '参数、电压点、公式对照来源、逐指标误差、失败状态、传播检查见相邻 JSON。',
              '参考误差要求：BW/UGF≤0.5%，PM≤0.2°，Vreq≤1e-6 V。', '',
              '所有异常均无系统指标且草案判决为 UNKNOWN；M1_SPEC_PASS 不等于完整行为 TB PASS。',
              'M0/M2 接口尚未实现；未产生 Verified JointBlockSpec。']
    with (out/'report.md').open('x', encoding='utf-8') as stream:
        stream.write('\n'.join(lines)+'\n')
    if not all(all_checks):
        raise ArithmeticError('Stage 1 numerical acceptance failed; inspect output')
    return manifest
