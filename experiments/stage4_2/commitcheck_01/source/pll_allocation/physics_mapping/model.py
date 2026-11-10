"""Isolated M1 continuous locked PLL model. All public input quantities use SI.

Equations are adapted from the audited MATLAB v3.4 reference, not its runtime.
No v1 module, transient backend, optimizer, or external simulator is imported.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
from enum import Enum
import cmath
import hashlib
import json
import math
from typing import Protocol

SCHEMA = 'pll-physics-mapping-2.0'
MODEL_ID = 'ideal_cppll_locked_continuous_m1_v1'
CONVENTIONS = {
    'vco_f0': 'frequency_at_zero_volts',
    'phase_error': 'reference_minus_feedback_rad',
    'lf_topology': 'C1_shunt_Rz_series_C2',
    'cp_leakage': 'positive_injected_into_lf',
}
# ID -> (unit, block, role). Context/nonideal switches remain explicit quantities.
PARAMETERS = {
    'f_ref': ('Hz', 'Reference', 'Context'), 'N': ('1', 'Divider', 'BlockSpec'),
    'Icp': ('A', 'CP', 'BlockSpec'), 'Rz': ('Ohm', 'LF', 'BlockSpec'),
    'C1': ('F', 'LF', 'BlockSpec'), 'C2': ('F', 'LF', 'BlockSpec'),
    'f0': ('Hz', 'VCO', 'BlockSpec'), 'Kvco': ('Hz/V', 'VCO', 'BlockSpec'),
    'Vctrl_min': ('V', 'VCO', 'BlockSpec'), 'Vctrl_max': ('V', 'VCO', 'BlockSpec'),
    'Kvco2': ('Hz/V^2', 'VCO', 'Context'), 'CP_mismatch': ('1', 'CP', 'Context'),
    'CP_leakage': ('A', 'CP', 'Context'), 'q0': ('C', 'CP', 'Context'),
    'PFD_reset_delay': ('s', 'PFD', 'Context'), 'Cload': ('F', 'LF', 'Context'),
    'Gload': ('S', 'LF', 'Context'),
}
METRIC_UNITS = {
    'output_frequency_Hz': 'Hz', 'Vctrl_required_V': 'V',
    'Kvco_local_Hz_per_V': 'Hz/V', 'UGF_Hz': 'Hz', 'BW_Hz': 'Hz', 'PM_deg': 'deg',
}
METRIC_PROTOCOLS = {
    'output_frequency_Hz': 'conditional_locked_tuning_frequency',
    'Vctrl_required_V': 'linear_vco_static_tuning_solution',
    'Kvco_local_Hz_per_V': 'vco_derivative_at_tuning_point',
    'UGF_Hz': 'continuous_L_first_downward_unity_crossing',
    'BW_Hz': 'continuous_normalized_T_first_downward_minus3dB',
    'PM_deg': '180_plus_continuous_L_phase_at_UGF',
}


class Status(str, Enum):
    OK = 'OK'
    UNSUPPORTED = 'UNSUPPORTED'
    OUT_OF_DOMAIN = 'OUT_OF_DOMAIN'
    NUMERICAL_FAILURE = 'NUMERICAL_FAILURE'


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode('utf-8')).hexdigest()


class ModelError(ValueError):
    def __init__(self, status, reason):
        super().__init__(reason)
        self.status, self.reason = status, reason


def finite(value, name):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ModelError(Status.OUT_OF_DOMAIN, name + ': finite number required')
    return value


def parse_parameters(parameters):
    if not isinstance(parameters, dict) or set(parameters) != {'schema_version', 'conventions', 'values'}:
        raise ModelError(Status.OUT_OF_DOMAIN, 'complete v2 parameter envelope required')
    if parameters['schema_version'] != SCHEMA or parameters['conventions'] != CONVENTIONS:
        raise ModelError(Status.UNSUPPORTED, 'schema or physical convention not supported')
    values = parameters['values']
    if not isinstance(values, dict) or set(values) != set(PARAMETERS):
        raise ModelError(Status.OUT_OF_DOMAIN, 'all and only declared parameter IDs required')
    p = {}
    for name, (unit, _, _) in PARAMETERS.items():
        item = values[name]
        if not isinstance(item, dict) or set(item) != {'value', 'unit'} or item['unit'] != unit:
            raise ModelError(Status.OUT_OF_DOMAIN, f'{name}: explicit canonical unit {unit} required')
        p[name] = finite(item['value'], name)
    for name in ('f_ref', 'Icp', 'Rz', 'C1', 'C2', 'Kvco'):
        if p[name] <= 0:
            raise ModelError(Status.OUT_OF_DOMAIN, name + ': must be > 0')
    if type(p['N']) is not int or p['N'] < 1:
        raise ModelError(Status.OUT_OF_DOMAIN, 'N: positive integer required')
    if p['Vctrl_min'] >= p['Vctrl_max']:
        raise ModelError(Status.OUT_OF_DOMAIN, 'ordered Vctrl limits required')
    if abs(p['CP_mismatch']) >= 2:
        raise ModelError(Status.OUT_OF_DOMAIN, 'positive UP and DOWN currents required')
    for name in ('PFD_reset_delay', 'Cload', 'Gload'):
        if p[name] < 0:
            raise ModelError(Status.OUT_OF_DOMAIN, name + ': must be >= 0')
    if p['PFD_reset_delay'] >= 1/p['f_ref']:
        raise ModelError(Status.OUT_OF_DOMAIN, 'reset delay must be shorter than reference period')
    unsupported = [k for k in ('Kvco2', 'CP_mismatch', 'CP_leakage', 'q0', 'PFD_reset_delay', 'Cload', 'Gload') if p[k] != 0]
    if unsupported:
        raise ModelError(Status.UNSUPPORTED, 'M1 has no validated linearization for nonzero: ' + ', '.join(unsupported))
    for v in (p['Vctrl_min'], p['Vctrl_max']):
        f = p['f0'] + p['Kvco']*v
        if not math.isfinite(f) or f <= 0:
            raise ModelError(Status.OUT_OF_DOMAIN, 'VCO frequency must be positive throughout voltage domain')
    return p


@dataclass(frozen=True)
class FrequencyScan:
    """None boundaries reproduce MATLAB's fz/fp/fref based default window."""
    minimum_Hz: float | None = None
    maximum_Hz: float | None = None
    points: int = 8000


@dataclass(frozen=True)
class MetricRequest:
    parameters: dict
    metrics: tuple[str, ...] = tuple(METRIC_UNITS)
    scan: FrequencyScan = field(default_factory=FrequencyScan)
    response_frequencies_Hz: tuple[float, ...] = ()


@dataclass
class MappingResult:
    status: Status
    reason: str = ''
    model_level: str = 'M1'
    model_id: str = MODEL_ID
    parameter_sha256: str | None = None
    metrics: dict = field(default_factory=dict)
    units: dict = field(default_factory=dict)
    protocols: dict = field(default_factory=dict)
    factors: dict = field(default_factory=dict)
    diagnostics: dict = field(default_factory=dict)
    response: list = field(default_factory=list)
    scope: str = 'CONDITIONAL_LOCKED_CONTINUOUS_SMALL_SIGNAL_ONLY'
    verified_joint_block_spec: bool = False

    def as_dict(self):
        result = asdict(self)
        result['status'] = self.status.value
        return result


class MetricEvaluator(Protocol):
    """Future evaluators share quantities but explicitly declare level and protocols."""
    model_level: str
    def evaluate(self, request: MetricRequest) -> MappingResult: ...


class UnavailableEvaluator:
    def __init__(self, level):
        if level not in ('M0', 'M2'):
            raise ValueError('only reserved M0/M2 levels accepted')
        self.model_level = level

    def evaluate(self, request):
        return MappingResult(Status.UNSUPPORTED, f'{self.model_level} evaluator not implemented',
                             model_level=self.model_level, model_id='unimplemented')


def _response(p, frequency):
    finite(frequency, 'frequency_Hz')
    if frequency <= 0:
        raise ModelError(Status.OUT_OF_DOMAIN, 'frequency_Hz must be > 0')
    s = 2j*math.pi*frequency
    z = (1+s*p['Rz']*p['C2'])/(s*(p['C1']+p['C2'])+s*s*p['Rz']*p['C1']*p['C2'])
    l = (p['Icp']/(2*math.pi))*(2*math.pi*p['Kvco'])*z/(p['N']*s)
    t = l/(1+l)
    if not all(math.isfinite(x) for v in (z, l, t) for x in (v.real, v.imag)):
        raise ModelError(Status.NUMERICAL_FAILURE, 'nonfinite transfer function')
    return z, l, t


def _crossing(frequencies, residual, label):
    values = [residual(f) for f in frequencies]
    if not all(math.isfinite(v) for v in values):
        raise ModelError(Status.NUMERICAL_FAILURE, label + ': nonfinite scan')
    brackets = [(a, b) for a, b, ya, yb in zip(frequencies, frequencies[1:], values, values[1:]) if ya > 0 >= yb]
    if len(brackets) != 1:
        raise ModelError(Status.NUMERICAL_FAILURE, f'{label}: expected one bracketed downward crossing; found {len(brackets)}')
    low, high = map(math.log10, brackets[0])
    for _ in range(70):
        mid = (low+high)/2
        if residual(10**mid) > 0:
            low = mid
        else:
            high = mid
        if high-low < 1e-12:
            return 10**((low+high)/2)
    raise ModelError(Status.NUMERICAL_FAILURE, label + ': crossing did not converge')


class M1Evaluator:
    model_level = 'M1'

    def evaluate(self, request):
        result = MappingResult(Status.OK)
        try:
            if not isinstance(request, MetricRequest) or not isinstance(request.scan, FrequencyScan):
                raise ModelError(Status.OUT_OF_DOMAIN, 'MetricRequest and FrequencyScan required')
            if (not isinstance(request.metrics, (tuple, list)) or not request.metrics
                    or not all(isinstance(name, str) for name in request.metrics)):
                raise ModelError(Status.UNSUPPORTED, 'nonempty sequence of metric names required')
            if len(set(request.metrics)) != len(request.metrics) or set(request.metrics)-set(METRIC_UNITS):
                raise ModelError(Status.UNSUPPORTED, 'unknown, duplicate or empty metric request')
            if not isinstance(request.response_frequencies_Hz, (tuple, list)):
                raise ModelError(Status.OUT_OF_DOMAIN, 'response frequencies must be a sequence')
            p = parse_parameters(request.parameters)
            result.parameter_sha256 = fingerprint(request.parameters)
            target = p['N']*p['f_ref']
            finite(target, 'f_target')
            result.factors['F_FREQ_PLAN'] = {'f_target_Hz': target, 'source': 'model/solve_tuning_point.m'}
            vreq = (target-p['f0'])/p['Kvco']
            margin = min(vreq-p['Vctrl_min'], p['Vctrl_max']-vreq)
            finite(vreq, 'Vctrl_required')
            result.factors['F_TUNING'] = {
                'Vctrl_required_V': vreq, 'Kvco_local_Hz_per_V': p['Kvco'],
                'feasible': margin >= 0, 'voltage_margin_V': margin,
                'tuning_frequency_min_Hz': p['f0']+p['Kvco']*p['Vctrl_min'],
                'tuning_frequency_max_Hz': p['f0']+p['Kvco']*p['Vctrl_max'],
                'source': 'model/solve_tuning_point.m; model/vco_model.m',
            }
            if margin <= 0:
                raise ModelError(Status.OUT_OF_DOMAIN, 'no interior VCO lock point' if margin == 0 else 'no VCO lock point in declared range')
            kpfd = p['Icp']/(2*math.pi)
            result.factors['F_KPFD'] = {'Kpfd_A_per_rad': kpfd, 'Iup_A': p['Icp'], 'Idown_A': p['Icp'],
                                          'source': 'model/pll_linear_kernel.m'}
            fz = 1/(2*math.pi*p['Rz']*p['C2'])
            fp = (p['C1']+p['C2'])/(2*math.pi*p['Rz']*p['C1']*p['C2'])
            if not all(math.isfinite(x) and x > 0 for x in (fz, fp, 2*math.pi*fp)):
                raise ModelError(Status.NUMERICAL_FAILURE, 'unrepresentable LF zero or pole')
            result.factors['F_LF_TF'] = {'zero_Hz': fz, 'poles_rad_per_s': [0, -2*math.pi*fp],
                                          'nonzero_pole_Hz': fp, 'source': 'model/pll_linear_kernel.m'}
            # a*s^3+b*s^2+c*s+d: Routh stability without approximate pole roots.
            gain = p['Icp']*p['Kvco']/p['N']
            a, b, c, d = p['Rz']*p['C1']*p['C2'], p['C1']+p['C2'], gain*p['Rz']*p['C2'], gain
            terms = [a, b, c, d, b*c, a*d, fz, fp, kpfd]
            if not all(math.isfinite(x) and x > 0 for x in terms):
                raise ModelError(Status.NUMERICAL_FAILURE, 'underflow/overflow in characteristic coefficients')
            if b*c <= a*d:
                raise ModelError(Status.OUT_OF_DOMAIN, 'closed loop does not meet strict Routh stability condition')
            scan = request.scan
            low = max(min(fz, fp)*1e-4, 1) if scan.minimum_Hz is None else finite(scan.minimum_Hz, 'scan minimum')
            high = max(fz, fp, p['f_ref'])*100 if scan.maximum_Hz is None else finite(scan.maximum_Hz, 'scan maximum')
            if type(scan.points) is not int or not 32 <= scan.points <= 100000 or not 0 < low < high or not math.isfinite(high):
                raise ModelError(Status.OUT_OF_DOMAIN, 'bounded positive ordered frequency scan with 32..100000 points required')
            frequencies = [10**(math.log10(low)+(math.log10(high)-math.log10(low))*i/(scan.points-1)) for i in range(scan.points)]
            ugf = _crossing(frequencies, lambda f: abs(_response(p, f)[1])-1, 'UGF')
            bw = _crossing(frequencies, lambda f: abs(_response(p, f)[2])-2**-.5, 'BW')
            pm = 180+math.degrees(cmath.phase(_response(p, ugf)[1]))
            result.factors['F_LOOP'] = {'UGF_Hz': ugf, 'BW_Hz': bw, 'PM_deg': pm,
                'characteristic_descending': [a, b, c, d], 'routh_stable': True,
                'T_definition': 'L/(1+L); normalized reference phase response; H_ref=N*T',
                'source': 'model/pll_linear_kernel.m; characterization/characterize_loop.m'}
            result.diagnostics = {'scan': {'minimum_Hz': low, 'maximum_Hz': high, 'points': scan.points},
                                  'UGF_over_fref': ugf/p['f_ref'], 'BW_over_fref': bw/p['f_ref'],
                                  'sampling_equivalence': 'NOT_ESTABLISHED', 'transient_lock': 'NOT_EVALUATED',
                                  'MATLAB_runtime_calls': 0, 'behavioral_TB_calls': 0}
            for f in request.response_frequencies_Hz:
                z, l, t = _response(p, f)
                result.response.append({'frequency_Hz': f, 'Zlf_Ohm': [z.real, z.imag],
                                        'L': [l.real, l.imag], 'T': [t.real, t.imag]})
            metrics = dict(output_frequency_Hz=target, Vctrl_required_V=vreq,
                           Kvco_local_Hz_per_V=p['Kvco'], UGF_Hz=ugf, BW_Hz=bw, PM_deg=pm)
            if not all(math.isfinite(x) for x in metrics.values()):
                raise ModelError(Status.NUMERICAL_FAILURE, 'nonfinite derived metric')
            result.metrics = {k: metrics[k] for k in request.metrics}
            result.units = {k: METRIC_UNITS[k] for k in request.metrics}
            result.protocols = {k: METRIC_PROTOCOLS[k] for k in request.metrics}
        except ModelError as error:
            result.status, result.reason = error.status, error.reason
            result.metrics, result.units, result.protocols, result.response = {}, {}, {}, []
        except (ArithmeticError, ValueError) as error:
            result.status, result.reason = Status.NUMERICAL_FAILURE, str(error)
            result.metrics, result.units, result.protocols, result.response = {}, {}, {}, []
        return result


def evaluate(parameters, *, scan=None, response_frequencies_Hz=()):
    return M1Evaluator().evaluate(MetricRequest(parameters, scan=scan or FrequencyScan(),
                                               response_frequencies_Hz=tuple(response_frequencies_Hz)))
