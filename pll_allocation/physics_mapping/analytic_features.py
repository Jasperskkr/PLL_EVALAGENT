"""Conditional ideal CPPLL descriptors, never a capture certificate or verdict."""
import math
import numpy as np

from .model import CONVENTIONS, PARAMETERS, SCHEMA, parse_parameters


def parameter_envelope(params, fixed_params=None):
    """Accept the canonical envelope or six SI values plus explicit fixed context."""
    if isinstance(params, dict) and 'schema_version' in params:
        return params
    values = dict(fixed_params or {}) | dict(params)
    return {'schema_version': SCHEMA, 'conventions': dict(CONVENTIONS), 'values': {
        k: (values[k] if isinstance(values.get(k), dict) else
            {'value': values.get(k, 0.), 'unit': unit})
        for k, (unit, _, _) in PARAMETERS.items()}}


def analytic_features(params, fixed_params=None, *, initial_control_V=.15):
    result = {'omega_n_rad_s': None, 'zeta_approx': None, 'closed_loop_poles': [],
        'initial_frequency_error_Hz': None, 'tuning_rail_margin_V': None,
        'slip_risk': 'UNKNOWN', 'predicted_lock_time_s': None,
        'prediction_validity': {'status': 'UNKNOWN', 'capture_certified': False}}
    try:
        p = parse_parameters(parameter_envelope(params, fixed_params))
        if not math.isfinite(initial_control_V) or not p['Vctrl_min'] <= initial_control_V <= p['Vctrl_max']:
            raise ValueError('initial control voltage outside rails')
        # Kpd=Icp/(2*pi) A/rad and K0=2*pi*Kvco rad/s/V cancel.
        gain = p['Icp']*p['Kvco']/p['N']
        total = p['C1']+p['C2']; wn = math.sqrt(gain/total)
        # D(s)=R*C1*C2*s^3+(C1+C2)*s^2+gain*R*C2*s+gain.
        # Solve in s/wn to avoid dimensional polynomial conditioning.
        coefficients = [p['Rz']*p['C1']*p['C2']*wn/total, 1., p['Rz']*p['C2']*wn, 1.]
        poles = sorted(np.roots(coefficients)*wn, key=lambda x: (float(x.real), float(x.imag)))
        target = p['N']*p['f_ref']; required = (target-p['f0'])/p['Kvco']
        margin = min(required-p['Vctrl_min'], p['Vctrl_max']-required)
        error = p['f0']+p['Kvco']*initial_control_V-target
        stable = all(x.real < 0 for x in poles)
        ratio = abs(error)/(p['N']*wn/(2*math.pi))
        valid = stable and margin > 0
        result.update(omega_n_rad_s=wn, zeta_approx=wn*p['Rz']*p['C2']/2,
            closed_loop_poles=[{'real_rad_s': float(x.real), 'imag_rad_s': float(x.imag)} for x in poles],
            initial_frequency_error_Hz=error, tuning_rail_margin_V=margin,
            slip_risk=('LOW' if ratio <= .1 else 'MEDIUM' if ratio <= 1 else 'HIGH') if valid else 'UNKNOWN',
            prediction_validity={'status': 'CONDITIONAL_IDEAL_LINEAR' if valid else 'OUTSIDE_LOCKED_DOMAIN',
                'stable': stable, 'capture_certified': False, 'initial_control_V': initial_control_V,
                'slip_indicator': ratio,
                'slip_rule': '|initial output frequency error| / (N*omega_n/(2*pi)): LOW<=0.1, MEDIUM<=1; heuristic only',
                'lock_time_reason': 'No validated nonlinear capture estimate, phase initial state or lock tolerance; left null',
                'scope': 'Exact ideal linear poles; approximate second-order damping; no strict capture-range inference'})
    except (ValueError, TypeError, KeyError, ArithmeticError, np.linalg.LinAlgError) as error:
        result['prediction_validity']['reason'] = str(error)
    return result
