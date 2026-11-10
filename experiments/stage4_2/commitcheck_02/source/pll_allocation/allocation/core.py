"""Runner-owned contracts, metering and M1 decisions using existing SI semantics."""
from __future__ import annotations
from copy import deepcopy
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import time
from pll_allocation.block_space.contracts import FREE_IDS, check_parameters, load_model, make_candidate
from pll_allocation.physics_mapping.experiment import judge_experiment, validate_experiment
from pll_allocation.physics_mapping.model import MappingResult, Status, evaluate, fingerprint


def write_new(path, obj):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(obj, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def bounds(model, name):
    a = model['variables'][name]
    if 'range' in a:
        return a['range']['min'], a['range']['max']
    if 'choices' in a:
        return min(a['choices']), max(a['choices'])
    return a['fixed'], a['fixed']


def values(candidate):
    return {k: v['value'] for k, v in candidate['values'].items()}


@dataclass
class Meter:
    cheap_limit: int = 2000
    m1_limit: int = 16
    events: list = field(default_factory=list)
    counts: dict = field(default_factory=lambda: {
        'analytic_calls': 0, 'M1_calls': 0, 'candidate_generations': 0, 'M2_calls': 0, 'LLM_calls': 0})

    def charge(self, kind, **details):
        limit = self.cheap_limit if kind == 'analytic_calls' else self.m1_limit if kind == 'M1_calls' else None
        if limit is not None and self.counts[kind] >= limit:
            raise RuntimeError('BUDGET_EXHAUSTED:' + kind)
        self.counts[kind] += 1
        self.events.append({'index': len(self.events) + 1, 'kind': kind, **details})

    def timed(self, kind, function, *args, **kwargs):
        self.charge(kind)
        event = self.events[-1]
        start = time.perf_counter()
        try:
            result = function(*args, **kwargs)
            event['status'] = 'RETURNED'
            if args:
                event['input'] = args[0] if len(args) == 1 else args
            event['output'] = result.as_dict() if hasattr(result, 'as_dict') else result
            return result
        except Exception as error:
            event.update(status='ERROR', error_type=type(error).__name__)
            raise
        finally:
            event['elapsed_s'] = time.perf_counter() - start


def target_experiment(model, system_spec=None):
    exp = deepcopy(model['experiment'])
    if system_spec is not None:
        exp['system_spec'] = deepcopy(system_spec)
    return validate_experiment(exp)


def assess_m1(model, system_spec, candidate, meter):
    domain = check_parameters(model, candidate)
    if domain['declared_domain'] != 'IN_DECLARED_DOMAIN' or domain['model_validity'] != 'VALID':
        return {'domain': domain, 'prediction': None, 'judgment': {'verdict': 'UNKNOWN', 'checks': []},
                'validation_level': 'NOT_VALIDATED', 'verified_joint_block_spec': False}
    result = meter.timed('M1_calls', evaluate, candidate)
    judgment = judge_experiment(target_experiment(model, system_spec), candidate, result)
    return {'domain': domain, 'prediction': result.as_dict(), 'judgment': judgment,
            'validation_level': 'M1_VALIDATED' if result.status.value == 'OK' else 'NOT_VALIDATED',
            'verified_joint_block_spec': False}


def margin_details(model, system_spec, candidate, metrics):
    """Engineering normalization; equality residual is not a quality objective."""
    margins, physical = {}, {}
    for spec in system_spec['metrics']:
        name = spec['metric']
        if name not in metrics:
            raise ValueError('missing prediction: ' + name)
        if spec.get('min') == spec.get('max') and 'min' in spec:
            physical[name] = {'residual': metrics[name] - spec['min'], 'tolerance': spec.get('tolerance', 0)}
            continue
        scale = (spec['max'] - spec['min']) / 2 if {'min', 'max'} <= set(spec) else max(abs(spec.get('min', spec.get('max'))), 1.)
        for side in ('min', 'max'):
            if side in spec:
                m = metrics[name] - spec[side] if side == 'min' else spec[side] - metrics[name]
                physical[name + ':' + side] = {'margin': m, 'unit': spec['unit'], 'normalization_scale': scale}
                margins[name + ':' + side] = (m + spec.get('tolerance', 0)) / scale
    p = values(candidate)
    for name in FREE_IDS:
        if 'range' in model['variables'][name]:
            lo, hi = bounds(model, name)
            margins['parameter:' + name] = 2 * min(p[name] - lo, hi - p[name]) / (hi - lo)
    v = (p['N'] * p['f_ref'] - p['f0']) / p['Kvco']
    margins['tuning'] = 2 * min(v - p['Vctrl_min'], p['Vctrl_max'] - v) / (p['Vctrl_max'] - p['Vctrl_min'])
    return {'normalized': margins, 'physical': physical, 'minimum_normalized_margin': min(margins.values()),
            'discrete_choices': 'categorical choices; no fictitious continuous boundary margin'}


def proposal(model, system_spec, candidate, strategy, assessment, metadata, candidate_id):
    prediction = assessment.get('prediction')
    margins = margin_details(model, system_spec, candidate, prediction['metrics']) if prediction and prediction['status'] == 'OK' else None
    return {'schema_version': 'allocation-proposal-1.0', 'candidate_id': candidate_id,
        'parameter_sha256': fingerprint(candidate), 'allocation_strategy': strategy,
        'versions': {**model['versions'], 'baseline': 'track-a-1.0',
                     'block_space_schema': model['schema_version'], 'system_spec': system_spec['version']},
        'block_space_sha256': fingerprint(model), 'system_spec_sha256': fingerprint(system_spec),
        'system_spec': deepcopy(system_spec), 'topology': deepcopy(model['topology']),
        'operating_conditions': {k: v for k, v in candidate['values'].items() if k not in FREE_IDS},
        'joint_block_spec': deepcopy(candidate),
        'blocks': {b: [n for n, a in model['variables'].items() if a['block'] == b] for b in model['topology']['blocks']},
        'M1': assessment, 'constraint_margins': margins, 'allocation_metadata': metadata,
        'validation_level': assessment['validation_level'], 'verified_joint_block_spec': False,
        'M2_status': 'NOT_EVALUATED',
        'prediction_confidence': {'numerical_consistency': 'STAGE1_5_EVIDENCE',
            'behavioral_BW_PM_error': 'NOT_ESTABLISHED', 'capture': 'NOT_EVALUATED',
            'domain_wide_reliability': 'NOT_ESTABLISHED'}}


def validate_proposal(model, item):
    if item.get('schema_version') != 'allocation-proposal-1.0':
        raise ValueError('AllocationProposal schema required')
    candidate = item['joint_block_spec']
    domain = check_parameters(model, candidate)
    if domain['declared_domain'] != 'IN_DECLARED_DOMAIN':
        raise ValueError('proposal outside declared domain')
    if item['parameter_sha256'] != fingerprint(candidate):
        raise ValueError('candidate hash mismatch')
    if item['block_space_sha256'] != fingerprint(model) or item['topology'] != model['topology']:
        raise ValueError('block space or topology binding mismatch')
    target_experiment(model, item['system_spec'])
    if item['system_spec_sha256'] != fingerprint(item['system_spec']):
        raise ValueError('SystemSpec binding mismatch')
    if item.get('verified_joint_block_spec') is not False or item.get('M2_status') != 'NOT_EVALUATED':
        raise ValueError('Track A cannot issue M2 certification')
    conditions = {k: v for k, v in candidate['values'].items() if k not in FREE_IDS}
    block_index = {b: [n for n, a in model['variables'].items() if a['block'] == b] for b in model['topology']['blocks']}
    if item.get('operating_conditions') != conditions or item.get('blocks') != block_index:
        raise ValueError('fixed conditions or block index mismatch')
    assessment = item['M1']
    if assessment['domain'] != domain:
        raise ValueError('domain assessment mismatch')
    prediction = assessment.get('prediction')
    if prediction:
        reconstructed = MappingResult(**{**prediction, 'status': Status(prediction['status'])})
        judged = judge_experiment(target_experiment(model, item['system_spec']), candidate, reconstructed)
        if assessment['judgment'] != judged or prediction['parameter_sha256'] != fingerprint(candidate):
            raise ValueError('M1 result binding or judgment mismatch')
        if judged['verdict'] == 'UNKNOWN' and item['validation_level'] == 'M1_VALIDATED':
            raise ValueError('unknown result cannot certify M1 validation')
        expected_margins = margin_details(model, item['system_spec'], candidate, prediction['metrics']) if prediction['status'] == 'OK' else None
        if item.get('constraint_margins') != expected_margins:
            raise ValueError('constraint margin binding mismatch')
        if prediction.get('verified_joint_block_spec') is not False:
            raise ValueError('M1 prediction cannot certify M2')
        expected_level = 'M1_VALIDATED' if prediction['status'] == 'OK' else 'NOT_VALIDATED'
        if item['validation_level'] != expected_level:
            raise ValueError('prediction status and validation level mismatch')
    elif (prediction is not None or item['validation_level'] != 'NOT_VALIDATED'
          or assessment['judgment'] != {'verdict': 'UNKNOWN', 'checks': []}
          or item.get('constraint_margins') is not None):
        raise ValueError('missing M1 prediction cannot support a validation claim')
    if assessment['verified_joint_block_spec'] is not False or assessment['validation_level'] != item['validation_level']:
        raise ValueError('M1 validation metadata mismatch')
    return candidate


def file_manifest(paths, purpose):
    return [{'path': str(Path(p).resolve()), 'sha256': hashlib.sha256(Path(p).read_bytes()).hexdigest(),
             'purpose': purpose, 'domain': 'ideal interior-locked continuous M1; SI and original conventions'} for p in paths]
