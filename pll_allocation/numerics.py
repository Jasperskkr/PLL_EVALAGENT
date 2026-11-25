"""Bounded floating-point operations; numerical failure is never infeasibility."""
import math
import sys


class NumericalError(ArithmeticError):
    def __init__(self, reason_code, message, diagnostics=None):
        self.reason_code = reason_code
        self.diagnostics = diagnostics or {}
        super().__init__(reason_code + ': ' + message)


def polynomial_log_sign(coefficients, log_x):
    """Sign of the SAME polynomial, scaled in log space to avoid overflow.

    Only used outside the normal finite fast path. math.fsum limits cancellation;
    a zero means cancellation at floating precision, not an exact-root proof.
    """
    if not all(math.isfinite(c) for c in coefficients):
        raise NumericalError('COEFFICIENT_NONFINITE', 'polynomial coefficient not representable')
    degree = len(coefficients)-1
    terms = [(math.copysign(1., c), math.log(abs(c))+(degree-i)*log_x)
             for i, c in enumerate(coefficients) if c]
    if not terms:
        raise NumericalError('COEFFICIENT_UNDERFLOW', 'all coefficients zero')
    scale = max(t[1] for t in terms)
    return math.fsum(sign*math.exp(value-scale) for sign, value in terms)


def positive_root(function, *, log_function=None, diagnostics=None):
    """Positive root bracketed by signs, then bisected in ln(x).

    Retain the original [-14,14], 80-step fast path. Expand ONLY a missing side,
    with finite representation and explicit evaluation/expansion budgets. A
    generic nonfinite callback is rejected; polynomial callers can supply a
    scale-free sign evaluation of the identical equation.
    """
    # Keep the common finite bracket free of per-iteration dictionaries/counters.
    # Diagnostics opt in to the fully instrumented path below. Failed endpoints
    # are reused by the bounded fallback, so no uncounted retry is introduced.
    prefetched = {}
    if diagnostics is None:
        for endpoint in (-14., 14.):
            try:
                prefetched[endpoint] = function(math.exp(endpoint))
            except (OverflowError, ZeroDivisionError):
                prefetched[endpoint] = math.nan
        a, b = prefetched[-14.], prefetched[14.]
        if math.isfinite(a) and math.isfinite(b) and a < 0 < b:
            low, high = -14., 14.
            for _ in range(80):
                middle = (low+high)/2
                try:
                    value = function(math.exp(middle))
                except (OverflowError, ZeroDivisionError):
                    value = math.nan
                if not math.isfinite(value):
                    if log_function is None:
                        raise NumericalError('ROOT_NONFINITE_FUNCTION', 'nonfinite interior root residual')
                    value = log_function(middle)
                    if not math.isfinite(value):
                        raise NumericalError('ROOT_NONFINITE_FUNCTION', 'nonfinite scaled root sign')
                if value > 0:
                    high = middle
                else:
                    low = middle
            return math.exp((low+high)/2)
    info = diagnostics if diagnostics is not None else {}
    info.update(initial_log_interval=[-14., 14.], expansions=0, iterations=0,
                function_evaluations=0, log_sign_evaluations=0, max_expansions=32,
                max_function_evaluations=180)
    minimum = math.log(math.ulp(0.))
    maximum = math.log(sys.float_info.max)

    def fail(code, message):
        info['reason_code'] = code
        raise NumericalError(code, message, dict(info))

    def value(logx):
        if info['function_evaluations'] >= info['max_function_evaluations']:
            fail('ROOT_EVALUATION_BUDGET', 'positive root evaluation budget exhausted')
        info['function_evaluations'] += 1
        try:
            answer = prefetched.pop(logx) if logx in prefetched else function(math.exp(logx))
        except (OverflowError, ZeroDivisionError):
            answer = math.nan
        # Outside the original interval, sign scaling also prevents a rounded
        # underflow-to-zero from masquerading as a bracket endpoint/root.
        if log_function is not None and (not math.isfinite(answer) or answer == 0 or logx < -14 or logx > 14):
            info['log_sign_evaluations'] += 1
            answer = log_function(logx)
        if not math.isfinite(answer):
            fail('ROOT_NONFINITE_FUNCTION', 'nonfinite function value; no reliable sign')
        return answer

    lo, hi = -14., 14.
    flo, fhi = value(lo), value(hi)
    step = 14.
    while not flo < 0 < fhi:
        if flo == 0 or fhi == 0:
            fail('ROOT_ENDPOINT_UNRESOLVED', 'zero endpoint sign cannot establish a strict bracket')
        if info['expansions'] >= info['max_expansions']:
            fail('ROOT_NOT_BRACKETED', 'positive root not bracketed within expansion budget')
        if flo > 0:
            extended = max(minimum, lo-step)
            if extended == lo:
                fail('ROOT_UNREPRESENTABLE', 'root below positive floating-point range or no positive root')
            lo, flo = extended, value(extended)
        elif fhi < 0:
            extended = min(maximum, hi+step)
            if extended == hi:
                fail('ROOT_UNREPRESENTABLE', 'root above floating-point range or no positive root')
            hi, fhi = extended, value(extended)
        info['expansions'] += 1
        step *= 2
    info['bracket_log_interval'] = [lo, hi]
    for iteration in range(80):
        mid = (lo+hi)/2
        if value(mid) > 0:
            hi = mid
        else:
            lo = mid
        info['iterations'] = iteration+1
    root = math.exp((lo+hi)/2)
    if not math.isfinite(root) or root <= 0:
        fail('ROOT_UNREPRESENTABLE', 'positive root not representable')
    # At the subnormal floor, a log bracket can be narrower than one ULP in x
    # while its relative x uncertainty remains large. Do not claim convergence.
    if math.ulp(root)/root > 1e-12:
        fail('ROOT_PRECISION_LIMIT', 'insufficient relative precision at subnormal root')
    info.update(final_log_interval=[lo, hi], reason_code='OK')
    return root


def snap_closed_bound(value, lower, upper, *, max_ulps=8):
    """Snap only a generated value <=8 representable steps outside a CLOSED bound.

    This is not an input-validator tolerance and never applies to open tuning
    rails or SystemSpec. Return the original value if the discrepancy is larger.
    """
    if not math.isfinite(value) or lower <= value <= upper:
        return value, None
    edge = lower if value < lower else upper
    outside = -math.inf if value < lower else math.inf
    cursor = edge
    for steps in range(1, max_ulps+1):
        cursor = math.nextafter(cursor, outside)
        if (outside < 0 and value >= cursor) or (outside > 0 and value <= cursor):
            return edge, {'raw_value': value, 'corrected_value': edge,
                          'ulp_steps': steps, 'max_ulps': max_ulps, 'reason_code': 'BOUNDARY_ROUNDOFF_SNAP'}
    return value, None
