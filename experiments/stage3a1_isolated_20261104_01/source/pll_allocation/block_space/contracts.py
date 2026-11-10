"""Executable Behavioral Block Space v1; no changes to the old Runner contract."""
from __future__ import annotations
from copy import deepcopy
import json
import math
from pathlib import Path
from pll_allocation.physics_mapping.model import (
    ModelError, Status, evaluate, fingerprint, parse_parameters,
)
from pll_allocation.physics_mapping.experiment import (
    judge_experiment, parameters_from_experiment, validate_experiment,
)

JOINT_IDS = {'J_FREQ','J_TUNING','J_GAIN','J_LF','J_STABILITY','J_IDEAL','J_SYSTEM'}
FREE_IDS = ('Icp', 'Rz', 'C1', 'C2', 'f0', 'Kvco')


def validate_model(raw):
    if not isinstance(raw, dict) or raw.get('schema_version') != 'behavioral-block-space-1.0':
        raise ValueError('Behavioral Block Space v1 required')
    model = deepcopy(raw)
    exp = validate_experiment(model['experiment'])
    if fingerprint(exp) != model['experiment_freeze']['experiment_sha256']:
        raise ValueError('frozen experiment digest mismatch')
    if model['topology'] != {'id': 'integer_n_cppll', 'blocks': ['PFD','CP','LF','VCO','Divider'],
            'connections': [['PFD','CP'],['CP','LF'],['LF','VCO'],['VCO','Divider'],['Divider','PFD']]}:
        raise ValueError('frozen topology changed')
    if set(model['variables']) != set(exp['block_space']['variables']):
        raise ValueError('variable completeness mismatch')
    for name, axis in exp['block_space']['variables'].items():
        entry = model['variables'][name]
        if any(entry.get(key) != value for key, value in axis.items()):
            raise ValueError('domain or units changed: ' + name)
        if not entry.get('range_rationale') or not entry.get('range_provenance'):
            raise ValueError('sourced range rationale required: ' + name)
    if {x['id'] for x in model['joint_constraints']} != JOINT_IDS:
        raise ValueError('executable joint constraint set mismatch')
    if len(model['variable_catalog']) != 41 or len({x['id'] for x in model['variable_catalog']}) != 41:
        raise ValueError('complete Stage 1 variable semantics required')
    if not {'formula_version','parameter_domain_version','behavioral_model_version'} <= set(model['versions']):
        raise ValueError('formula/domain/behavioral version identities required')
    evidence = model.get('validation_evidence', {})
    if evidence.get('status') == 'M1_DOMAIN_SCAN_COMPLETE_SPARSE_EVENT_CHECKS':
        if evidence.get('validated_experiment_sha256') != fingerprint(exp):
            raise ValueError('validation evidence belongs to a different experiment/domain')
    return model


def load_model(path):
    return validate_model(json.loads(Path(path).read_text(encoding='utf-8')))


def make_candidate(model, overrides=None):
    """Return a complete unit-bearing candidate; accepts all three domain modes."""
    return parameters_from_experiment(model['experiment'], overrides)


def check_parameters(model, candidate):
    """Declared membership, mathematical validity, SystemSpec feasibility stay separate."""
    declared, valid, issues, derived = 'IN_DECLARED_DOMAIN', 'VALID', [], {}
    try:
        values = {k: x['value'] for k, x in candidate['values'].items()}
        expected = make_candidate(model, values)
        if expected != candidate:
            raise ValueError('unit, completeness or convention mismatch')
    except (ValueError, KeyError, TypeError, AttributeError):
        declared = 'OUT_OF_DECLARED_DOMAIN'
        issues.append('candidate is not a complete member of the declared SI space')
    try:
        p = parse_parameters(candidate)
        target = p['N']*p['f_ref']
        vreq = (target-p['f0'])/p['Kvco']
        gain = p['Icp']*p['Kvco']/p['N']
        a, b = p['Rz']*p['C1']*p['C2'], p['C1']+p['C2']
        c, d = gain*p['Rz']*p['C2'], gain
        derived = {'f_target_Hz': target, 'Vctrl_required_V': vreq,
            'voltage_margin_V': min(vreq-p['Vctrl_min'],p['Vctrl_max']-vreq),
            'Icp_Kvco_over_N': gain, 'Routh_bc_minus_ad': b*c-a*d,
            'wz_rad_s': 1/(p['Rz']*p['C2']), 'wp_rad_s': b/a}
        if not all(math.isfinite(x) for x in derived.values()):
            raise ModelError(Status.NUMERICAL_FAILURE, 'nonfinite derived domain quantity')
        if derived['voltage_margin_V'] <= 0:
            valid = 'OUT_OF_DOMAIN'
            issues.append('VCO tuning is unreachable or on a rail; M1 needs interior lock point')
        if derived['Routh_bc_minus_ad'] <= 0:
            valid = 'OUT_OF_DOMAIN'
            issues.append('strict Routh stability not met')
        if (target != 80e6 or p['f_ref'] != 10e6 or p['N'] != 8):
            declared = 'OUT_OF_DECLARED_DOMAIN'
            issues.append('fixed frequency plan changed')
    except ModelError as error:
        valid = error.status.value
        issues.append(error.reason)
    except (ArithmeticError, ValueError, KeyError, TypeError) as error:
        valid = 'NUMERICAL_FAILURE'
        issues.append(str(error))
    return {'declared_domain': declared, 'model_validity': valid, 'derived': derived, 'issues': issues,
            'system_feasibility': 'NOT_EVALUATED'}


def forward(model, candidate):
    domain = check_parameters(model, candidate)
    if domain['declared_domain'] != 'IN_DECLARED_DOMAIN' or domain['model_validity'] != 'VALID':
        return {'domain': domain, 'prediction': None, 'judgment': {'verdict': 'UNKNOWN', 'checks': []},
                'validation_level': 'NOT_VALIDATED', 'verified_joint_block_spec': False}
    result = evaluate(candidate)
    judged = judge_experiment(model['experiment'], candidate, result)
    return {'domain': domain, 'prediction': result.as_dict(), 'judgment': judged,
            'validation_level': 'M1_VALIDATED' if result.status == Status.OK else 'NOT_VALIDATED',
            'verified_joint_block_spec': False}
