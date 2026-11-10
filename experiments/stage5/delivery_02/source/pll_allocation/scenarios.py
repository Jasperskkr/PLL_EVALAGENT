"""Versioned research thresholds over immutable formal pipeline assets."""
from copy import deepcopy
import hashlib
import math
from pathlib import Path
from .allocation.core import read
from .physics_mapping.model import fingerprint

SCHEMA = 'pll-research-scenario-1.0'
KEYS = {'schema_version', 'scenario_id', 'version', 'label', 'scope',
        'base_bindings', 'overrides', 'scenario_sha256'}


def validate_scenario(item, config, frozen_spec):
    if not isinstance(item, dict) or set(item) != KEYS or item.get('schema_version') != SCHEMA:
        raise ValueError('unsupported research scenario schema/fields')
    if any(not isinstance(item[k], str) or not item[k].strip() for k in ('scenario_id', 'version', 'label')):
        raise ValueError('scenario identity/version required')
    if item['scope'] != 'RESEARCH_SCENARIO_NOT_FORMAL_SPEC':
        raise ValueError('explicit research scenario scope required')
    if item['base_bindings'] != config['bindings']:
        raise ValueError('scenario base asset binding mismatch')
    if item['scenario_sha256'] != fingerprint({k: v for k, v in item.items() if k != 'scenario_sha256'}):
        raise ValueError('scenario hash mismatch')
    overrides = item['overrides']
    if (not isinstance(overrides, dict) or set(overrides) != {'BW_Hz', 'PM_deg'}
            or not isinstance(overrides['BW_Hz'], dict) or set(overrides['BW_Hz']) != {'min', 'max'}
            or not isinstance(overrides['PM_deg'], dict) or set(overrides['PM_deg']) != {'min'}):
        raise ValueError('only BW min/max and PM min may change')
    vals = [overrides['BW_Hz']['min'], overrides['BW_Hz']['max'], overrides['PM_deg']['min']]
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in vals):
        raise ValueError('finite numeric thresholds required')
    if not (0 < vals[0] < vals[1] and 0 <= vals[2] < 90):
        raise ValueError('invalid BW interval or PM threshold')
    spec = deepcopy(frozen_spec)
    for row in spec['metrics']:
        row.update(overrides.get(row['metric'], {}))
    binding = {'schema_version': SCHEMA, 'scenario_id': item['scenario_id'],
        'version': item['version'], 'scenario_sha256': item['scenario_sha256'],
        'effective_system_spec_sha256': fingerprint(spec), 'base_system_spec_sha256': fingerprint(frozen_spec)}
    return spec, binding


def load_scenario(path, config, frozen_spec):
    item = read(path)
    spec, binding = validate_scenario(item, config, frozen_spec)
    return item, spec, binding


def validate_proposal_scenario(item):
    # Re-use original asset verification; no alternate model/config registry.
    from .pipeline_contracts import load_inputs
    config, model, frozen_spec, protocol = load_inputs()
    scenario = item.get('research_scenario')
    spec, binding = validate_scenario(scenario, config, frozen_spec)
    if (item.get('scenario_binding') != binding or item.get('system_spec') != spec
            or item.get('system_spec_sha256') != fingerprint(spec)):
        raise ValueError('proposal scenario/SystemSpec binding mismatch')
    return config, model, frozen_spec, protocol, binding


def raw_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
