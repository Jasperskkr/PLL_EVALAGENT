"""Draft SystemSpec v0 and unit-bearing Block Space v2, without v1 imports."""
from __future__ import annotations
from copy import deepcopy
import json
import math
from pathlib import Path
from .model import (CONVENTIONS, METRIC_PROTOCOLS, METRIC_UNITS, MODEL_ID, PARAMETERS,
                    SCHEMA, ModelError, Status, finite, fingerprint, parse_parameters)

EXPERIMENT_SCHEMA = 'pll-physics-experiment-2.0'


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _inside(value, rule):
    if 'fixed' in rule:
        return value == rule['fixed']
    if 'choices' in rule:
        return value in rule['choices']
    return rule['range']['min'] <= value <= rule['range']['max']


def parameters_from_experiment(experiment, overrides=None):
    overrides = overrides or {}
    axes = experiment['block_space']['variables']
    _require(not set(overrides)-set(axes), 'unknown candidate variable')
    values = {}
    for name, rule in axes.items():
        value = finite(overrides.get(name, rule['default']), name)
        _require(_inside(value, rule), name + ': outside declared block space')
        values[name] = {'value': value, 'unit': rule['unit']}
    return {'schema_version': SCHEMA, 'conventions': deepcopy(CONVENTIONS), 'values': values}


def validate_experiment(raw):
    _require(isinstance(raw, dict) and raw.get('schema_version') == EXPERIMENT_SCHEMA,
             'independent physics experiment v2 required')
    exp = deepcopy(raw)
    _require(exp.get('topology') == 'integer_n_cppll', 'only integer-N CPPLL supported')
    _require(exp.get('conventions') == CONVENTIONS, 'explicit conventions required')
    system = exp.get('system_spec', {})
    _require(system.get('version') == '0' and system.get('draft') is True and system.get('source'),
             'SystemSpec v0 must remain a sourced research draft')
    axes = exp.get('block_space', {}).get('variables', {})
    _require(set(axes) == set(PARAMETERS), 'all unit-bearing variables required')
    _require(exp['block_space'].get('version') == '2' and exp['block_space'].get('capability_claim') == 'BEHAVIORAL_DECLARED_DOMAIN_ONLY',
             'Block Space v2 domain claim required')
    for name, (unit, block, role) in PARAMETERS.items():
        rule = axes[name]
        _require(rule.get('unit') == unit and rule.get('block') == block and rule.get('role') == role,
                 name + ': unit/block/role mismatch')
        _require(bool(rule.get('source')) and bool(rule.get('validity')), name + ': source/validity required')
        modes = set(rule) & {'fixed', 'range', 'choices'}
        _require(len(modes) == 1, name + ': exactly one fixed/range/choices required')
        if 'fixed' in rule:
            domain_values = [rule['fixed']]
        elif 'choices' in rule:
            domain_values = rule['choices']
            _require(isinstance(domain_values, list) and bool(domain_values), name + ': nonempty choices required')
            for value in domain_values:
                finite(value, name)
            _require(len(set(domain_values)) == len(domain_values), name + ': duplicate choices')
        else:
            bounds = rule['range']
            _require(isinstance(bounds, dict) and set(bounds) == {'min', 'max'}, name + ': min/max range required')
            domain_values = [finite(bounds['min'], name), finite(bounds['max'], name)]
            _require(domain_values[0] < domain_values[1], name + ': strict range ordering required')
            _require(name != 'N', 'integer N must use fixed/choices')
        for value in domain_values:
            finite(value, name)
            if name in {'f_ref', 'Icp', 'Rz', 'C1', 'C2', 'Kvco'}:
                _require(value > 0, name + ': positive domain required')
            if name in {'PFD_reset_delay', 'Cload', 'Gload'}:
                _require(value >= 0, name + ': nonnegative domain required')
            if name == 'CP_mismatch':
                _require(abs(value) < 2, 'positive UP/DOWN current domain required')
            if name == 'N':
                _require(type(value) is int and value >= 1, 'positive integer N required')
        finite(rule.get('default'), name + '.default')
        _require(_inside(rule['default'], rule), name + ': default outside domain')
    # Full defaults must define an executable M1 point, rather than a fake valid draft.
    try:
        parse_parameters(parameters_from_experiment(exp))
    except ModelError as error:
        raise ValueError('default model domain: ' + error.reason) from error
    seen = set()
    specs = system.get('metrics', [])
    _require(isinstance(specs, list) and bool(specs), 'nonempty SystemSpec metrics required')
    for s in specs:
        name = s.get('metric')
        _require(name in METRIC_UNITS and name not in seen, 'unsupported or duplicate spec metric')
        seen.add(name)
        _require(s.get('unit') == METRIC_UNITS[name] and s.get('protocol') == METRIC_PROTOCOLS[name]
                 and s.get('evaluator') == 'M1' and s.get('source'), 'metric semantics/evaluator mismatch')
        bounds = set(s) & {'min', 'max'}
        _require(bool(bounds), 'metric bound required')
        for bound in bounds:
            finite(s[bound], name + '.' + bound)
        _require(not {'min', 'max'} <= bounds or s['min'] <= s['max'], 'metric limits inverted')
        _require(finite(s.get('tolerance', 0), name + '.tolerance') >= 0, 'nonnegative tolerance required')
    _require({'output_frequency_Hz', 'BW_Hz', 'PM_deg'} <= seen, 'Stage 1 frequency/BW/PM targets required')
    _require(exp.get('diagnostic_metrics') == ['UGF_Hz'], 'UGF remains diagnostic')
    return exp


def load_experiment(path):
    return validate_experiment(json.loads(Path(path).read_text(encoding='utf-8')))


def judge_experiment(experiment, parameters, result):
    """Sourced draft bounds; never emits full-TB PASS or VerifiedJointBlockSpec."""
    exp = validate_experiment(experiment)
    reasons = []
    # Recheck candidate completeness and membership independently of the evaluator.
    try:
        parse_parameters(parameters)
        expected = parameters_from_experiment(exp, {k: v['value'] for k, v in parameters['values'].items()})
        if expected != parameters:
            reasons.append('candidate envelope mismatch')
    except (ModelError, ValueError, KeyError, TypeError):
        reasons.append('invalid or out-of-space candidate')
    try:
        bound = result.parameter_sha256 == fingerprint(parameters)
    except (ValueError, TypeError):
        bound = False
    if result.status != Status.OK or result.model_level != 'M1' or result.model_id != MODEL_ID or not bound:
        reasons.append('incomplete, unsupported or unbound M1 result')
    checks = []
    for s in exp['system_spec']['metrics']:
        name = s['metric']
        actual = result.metrics.get(name)
        known = (not reasons and type(actual) in (int, float) and math.isfinite(actual)
                 and result.units.get(name) == s['unit'] and result.protocols.get(name) == s['protocol'])
        margin = min([actual-s['min'] for _ in [0] if 'min' in s] +
                     [s['max']-actual for _ in [0] if 'max' in s]) + s.get('tolerance', 0) if known else None
        checks.append({'metric': name, 'actual': actual, 'unit': s['unit'], 'margin': margin,
                       'status': 'UNKNOWN' if not known else 'SATISFIED' if margin >= 0 else 'VIOLATED'})
    verdict = 'UNKNOWN' if reasons or any(c['status'] == 'UNKNOWN' for c in checks) else (
        'M1_SPEC_FAIL' if any(c['status'] == 'VIOLATED' for c in checks) else 'M1_SPEC_PASS')
    return {'verdict': verdict, 'checks': checks, 'issues': reasons,
            'scope': 'RESEARCH_DRAFT_CONTINUOUS_M1_ONLY', 'verified_joint_block_spec': False,
            'M2_behavioral_verdict': 'NOT_EVALUATED'}
