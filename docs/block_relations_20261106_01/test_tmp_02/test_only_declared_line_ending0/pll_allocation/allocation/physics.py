"""Inverse algebra and dimensionless numerical roots; prediction, never M2."""
from __future__ import annotations
import itertools
import math
from .core import bounds, values

RELATIONS = {
    'frequency': 'F=N*f_ref; Vreq=(F-f0)/Kvco; f0 is the zero-volt intercept',
    'CP': 'Kpfd=Icp/(2*pi) A/rad; angular VCO gain=2*pi*Kvco',
    'LF': 'Z=(1+s*Rz*C2)/(s*(C1+C2)+s*s*Rz*C1*C2)',
    'loop': 'K=Icp*Kvco/N; L=K*Z/s; T=L/(1+L)',
    'shape': 'q=1+C2/C1; x=omega_u*Rz*C2; PM=atan(x)-atan(x/q)',
    'phase_ceiling': 'PMmax=asin((q-1)/(q+1)) at x=sqrt(q)',
    'inverse_gain': 'K=(C1+C2)*omega_u^2*sqrt((1+(x/q)^2)/(1+x^2))',
    'scaling': 'fixed C: Rz_new=Rz/a; product_new=a^2*Icp*Kvco; UGF,BW multiply by a, PM fixed',
    'stability': 'bc-ad=(Icp*Kvco/N)*Rz*C2^2>0; does not prove capture or event stability',
}


def pm_ceiling(c1, c2):
    q = 1 + c2/c1
    return math.degrees(math.asin((q - 1)/(q + 1)))


def phase_interval(c1, c2, pm_deg):
    q = 1 + c2/c1
    if pm_deg > pm_ceiling(c1, c2):
        return None
    if pm_deg <= 0:
        return [0., None]
    t = math.tan(math.radians(pm_deg))
    d = max(0., (q - 1)**2 - 4*q*t*t)
    low = 2*q*t/(q - 1 + math.sqrt(d))
    return [low, q/low]


def propagate(model, system_spec):
    axes = model['variables']
    specs = {s['metric']: s for s in system_spec['metrics']}
    target = axes['N']['fixed'] * axes['f_ref']['fixed']
    certificates = []
    freq = specs['output_frequency_Hz']
    if target < freq.get('min', -math.inf) - freq.get('tolerance', 0) or target > freq.get('max', math.inf) + freq.get('tolerance', 0):
        certificates.append({'kind': 'FIXED_FREQUENCY_PLAN', 'fixed_output_Hz': target, 'target': freq})
    required = specs['PM_deg'].get('min', 0) - specs['PM_deg'].get('tolerance', 0)
    pairs = [{'C1': a, 'C2': b, 'PM_ceiling_deg': pm_ceiling(a, b), 'x_interval': phase_interval(a, b, required)}
             for a, b in itertools.product(axes['C1']['choices'], axes['C2']['choices'])]
    if all(p['x_interval'] is None for p in pairs):
        certificates.append({'kind': 'CAPACITOR_RATIO_PHASE_CEILING', 'required_PM_deg': required,
                             'global_ceiling_deg': max(p['PM_ceiling_deg'] for p in pairs)})
    return {'status': 'PROVEN_INFEASIBLE' if certificates else 'NECESSARY_CONDITIONS_ONLY',
            'certificates': certificates, 'capacitor_pairs': pairs,
            'gain_product_interval': [bounds(model, 'Icp')[i]*bounds(model, 'Kvco')[i] for i in (0, 1)],
            'not_proven': 'BW/gain/R/tuning intersection needs solving; no certificate is not proof of feasibility'}


def _bisect_positive(function):
    lo, hi = -14., 14.
    if not function(math.exp(lo)) < 0 < function(math.exp(hi)):
        raise ArithmeticError('positive root not bracketed')
    for _ in range(80):
        mid = (lo + hi)/2
        if function(math.exp(mid)) > 0:
            hi = mid
        else:
            lo = mid
    return math.exp((lo + hi)/2)


def bandwidth_ratio(q, x):
    """Numerical root, NOT a closed form. y=(omega_BW/omega_u)^2."""
    h = math.sqrt((1 + (x/q)**2)/(1 + x*x))
    y = _bisect_positive(lambda y: (x/q)**2*y**3 + (1 - 2*h*x*x/q)*y*y - (2*h + h*h*x*x)*y - h*h)
    return math.sqrt(y)


def raw_prediction(p):
    """Dimensionless magnitude roots, same physics as M1, no TB or M1 call."""
    wz = 1/(p['Rz']*p['C2'])
    q = 1 + p['C2']/p['C1']
    g = p['Icp']*p['Kvco']/(p['N']*(p['C1'] + p['C2'])*wz*wz)
    xu2 = _bisect_positive(lambda y: y**3/(q*q) + y*y - g*g*y - g*g)
    xb2 = _bisect_positive(lambda y: y**3/(q*q) + (1 - 2*g/q)*y*y - (2*g + g*g)*y - g*g)
    xu = math.sqrt(xu2)
    return {'output_frequency_Hz': p['N']*p['f_ref'],
            'Vctrl_required_V': (p['N']*p['f_ref'] - p['f0'])/p['Kvco'],
            'Kvco_local_Hz_per_V': p['Kvco'], 'UGF_Hz': wz*xu/(2*math.pi),
            'BW_Hz': wz*math.sqrt(xb2)/(2*math.pi),
            'PM_deg': math.degrees(math.atan(xu) - math.atan(xu/q))}


def cheap_predict(model, candidate, meter):
    from pll_allocation.block_space.contracts import check_parameters
    domain = check_parameters(model, candidate)
    if domain['declared_domain'] != 'IN_DECLARED_DOMAIN' or domain['model_validity'] != 'VALID':
        raise ValueError('cheap predictor outside valid declared domain')
    return meter.timed('analytic_calls', raw_prediction, values(candidate))


def inverse_at_shape(model, c1, c2, target_bw, x, meter):
    """Analytical gain/R/tuning reconstruction; beta is a numerical scalar root."""
    q = 1 + c2/c1
    beta = meter.timed('analytic_calls', bandwidth_ratio, q, x)
    wu = 2*math.pi*target_bw/beta
    rz = x/(wu*c2)
    gain = (c1 + c2)*wu*wu*math.sqrt((1 + (x/q)**2)/(1 + x*x))
    product = gain*model['variables']['N']['fixed']
    ilo, ihi = bounds(model, 'Icp')
    klo, khi = bounds(model, 'Kvco')
    klo, khi = max(klo, product/ihi), min(khi, product/ilo)
    if klo > khi:
        return None
    kv = (klo + khi)/2
    vlo, vhi = bounds(model, 'Vctrl_min')[0], bounds(model, 'Vctrl_max')[0]
    ftarget = model['variables']['N']['fixed']*model['variables']['f_ref']['fixed']
    flo, fhi = bounds(model, 'f0')
    f0 = min(fhi, max(flo, ftarget - kv*(vlo + vhi)/2))
    return {'Icp': product/kv, 'Rz': rz, 'C1': c1, 'C2': c2, 'f0': f0, 'Kvco': kv}

# substantive edit
