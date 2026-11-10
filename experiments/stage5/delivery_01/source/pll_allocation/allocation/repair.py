"""Post-submission feedback is isolated from all first-shot entry points."""
from __future__ import annotations
from copy import deepcopy
import math
from .allocate import analytical, generated, optimize
from .core import bounds, fingerprint, values

KINDS = {'BW', 'PM', 'TUNING_UNREACHABLE', 'COLD_START_CAPTURE', 'MODEL_OUT_OF_DOMAIN',
         'UNRELIABLE_MEASUREMENT', 'MULTIPLE'}


def interpret_feedback(candidate, feedback):
    if feedback.get('schema_version') != 'allocation-feedback-1.0':
        raise ValueError('versioned feedback required')
    if feedback.get('parameter_sha256') != fingerprint(candidate):
        raise ValueError('feedback candidate binding mismatch')
    if feedback.get('source') not in ('SIMULATED', 'M2') or feedback.get('kind') not in KINDS:
        raise ValueError('explicit feedback origin and known failure kind required')
    if feedback.get('verdict') not in ('FAIL', 'UNKNOWN'):
        raise ValueError('repair requires failure or unknown evidence')
    return {'kind': feedback['kind'], 'source': feedback['source'],
            'real_repair_success': 'NOT_MEASURED', 'remaining_M2_required': True}


def repair(model, system_spec, candidate, feedback, meter):
    decision = interpret_feedback(candidate, feedback)
    kind = decision['kind']
    p = values(candidate)
    new, meta = None, {}
    if kind == 'UNRELIABLE_MEASUREMENT':
        decision.update(action='REQUEST_REMEASUREMENT', reason='Inspect window, injection, numerical convergence and protocol before changing blocks.')
    elif kind == 'MODEL_OUT_OF_DOMAIN':
        decision.update(action='REQUEST_MODEL_DIAGNOSIS', reason='Do not optimize through unsupported effects; preserve domain and ask verifier for applicability evidence.')
    elif kind == 'BW':
        obs = feedback.get('measurements', {}).get('BW_Hz', {})
        if obs.get('unit') != 'Hz' or obs.get('reliable') is not True or type(obs.get('value')) not in (int, float) or not math.isfinite(obs['value']) or obs['value'] <= 0:
            raise ValueError('reliable positive Hz BW observation required')
        spec = next(s for s in system_spec['metrics'] if s['metric'] == 'BW_Hz')
        a = ((spec['min'] + spec['max'])/2)/obs['value']
        updates = {**p, 'Rz': p['Rz']/a, 'Icp': p['Icp']*a*a}
        try:
            new = generated(model, updates, meter)
            decision.update(action='COORDINATED_SCALE_REPAIR', reason='Measured BW ratio sets frequency scale; R inversely and gain product quadratically preserve ideal PM.')
        except ValueError:
            new, meta = optimize(model, system_spec, meter)
            decision.update(action='REALLOCATE_WITH_BOUNDS', reason='Direct scale repair exceeds declared R/current; solve full constrained allocation.')
    elif kind == 'PM':
        new, meta = analytical(model, system_spec, meter)
        decision.update(action='RESELECT_LF_RATIO_AND_SHAPE', reason='Check phase ceiling before gain tuning; peak lead needs C2/C1 and coordinated R/product.')
    elif kind in ('TUNING_UNREACHABLE', 'COLD_START_CAPTURE'):
        center = (p['Vctrl_min'] + p['Vctrl_max'])/2
        flo, fhi = bounds(model, 'f0')
        f0 = min(fhi, max(flo, p['N']*p['f_ref'] - p['Kvco']*center))
        new = generated(model, {**p, 'f0': f0}, meter)
        decision.update(action='RECENTER_TUNING' if kind == 'TUNING_UNREACHABLE' else 'CAPTURE_HYPOTHESIS_REQUIRES_M2',
            reason='Change VCO intercept to improve rail headroom; cold-start capture also needs initial states, duration and saturation trace from M2.')
    else:
        new, meta = optimize(model, system_spec, meter)
        decision.update(action='COUPLED_REALLOCATION', reason='Multiple failed metrics require constrained joint allocation, not independent random changes.')
    changed = {k: {'old': p[k], 'new': values(new)[k]} for k in p if new and p[k] != values(new)[k]}
    if new is not None and fingerprint(new) == fingerprint(candidate):
        new = None
        decision.update(action='NO_CHANGE_REQUEST_M2_DIAGNOSIS',
            reason='The proposed repair equals the previous candidate; inspect M1/M2 mismatch or capture evidence before spending another verification.')
    return new, {**decision, 'changes': changed, 'solver_metadata': meta,
                 'validation_level': 'REPAIR_PROPOSED_NOT_M2_VERIFIED' if new else 'DIAGNOSIS_REQUIRED', 'feedback': deepcopy(feedback)}
