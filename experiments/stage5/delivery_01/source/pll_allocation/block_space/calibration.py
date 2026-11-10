"""Append-only discrepancy records; never silently correct the raw formulas."""
from __future__ import annotations
import math
from .contracts import check_parameters
from pll_allocation.physics_mapping.model import fingerprint

CLASSIFICATIONS = {'NUMERICAL_IMPLEMENTATION_ERROR','FORMULA_ASSUMPTION_INVALID',
                   'PARAMETER_SEMANTICS_MISMATCH','MISSING_BEHAVIORAL_EFFECT',
                   'MEASUREMENT_PROTOCOL_MISMATCH','UNRESOLVED'}


def discrepancy_record(model, parameters, *, metric, prediction, reference, unit,
                       prediction_protocol, reference_protocol, evidence, classification,
                       recommended_action, known_limitations, comparability='UNESTABLISHED'):
    if classification not in CLASSIFICATIONS or not evidence or not recommended_action or not known_limitations:
        raise ValueError('classified, sourced discrepancy with action and limitations required')
    if comparability not in {'SAME_PROTOCOL','CONDITIONAL_LOCKED_COMPARISON','UNESTABLISHED'}:
        raise ValueError('explicit comparability required')
    if prediction_protocol != reference_protocol and comparability == 'SAME_PROTOCOL':
        raise ValueError('different protocols cannot claim same-protocol error')
    if not prediction_protocol or not reference_protocol or not unit or not metric:
        raise ValueError('metric, unit and measurement protocols required')
    if any(type(x) not in (int,float) or not math.isfinite(x) for x in (prediction,reference)):
        raise ValueError('finite raw prediction and observation required')
    return {'schema_version': 'prediction-discrepancy-1.0', **model['versions'],
        'parameter_sha256': fingerprint(parameters), 'domain': check_parameters(model,parameters),
        'metric': metric, 'prediction': prediction, 'reference': reference, 'unit': unit,
        'prediction_protocol': prediction_protocol, 'reference_protocol': reference_protocol,
        'comparability': comparability, 'validation_evidence': evidence,
        'prediction_error': {'reference_minus_prediction': reference-prediction,
                             'relative': (reference-prediction)/abs(prediction) if prediction else None,
                             'interpretation': 'CONDITIONAL' if comparability == 'CONDITIONAL_LOCKED_COMPARISON' else comparability},
        'classification': classification, 'known_limitations': known_limitations,
        'recommended_calibration_action': recommended_action, 'raw_formula_modified': False}
