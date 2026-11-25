"""Versioned naming migration: evidence identity, execution gates and public IO."""
from copy import deepcopy
import json
from pathlib import Path
import re

import pytest

from pll_allocation.agent.feedback import validate_config
from pll_allocation.agent.handoff import validate_handoff
from pll_allocation.agent.spec_allocation import run_spec_allocation
from pll_allocation.contract_names import (
    HANDOFF_SCHEMA, LEGACY_HANDOFF_SCHEMA, FEEDBACK_SCHEMA, LEGACY_FEEDBACK_SCHEMA,
    handoff_ready, problem_matches_handoff,
)
from pll_allocation.delivery import validate_recorded_protocol
from pll_allocation.io_contracts import read_json
from pll_allocation.physics_mapping.model import fingerprint, parse_parameters
from pll_allocation.vco_sizing.contract import build_guidance
from pll_allocation.verification.metric_protocols import integer_n_protocol

ROOT = Path(__file__).resolve().parents[1]


def test_agent_config_sources_use_shared_installed_location(tmp_path, monkeypatch):
    from pll_allocation.agent import planner_state, subregion_prior, search_loop
    from pll_allocation.verification import resources
    import hashlib
    assert planner_state.REGISTRY == subregion_prior.REGISTRY == resources.CONFIGS/'model/equations.json'
    config = tmp_path/'configs'
    (config/'model').mkdir(parents=True)
    content = b'{"TEST":"separate installed config source"}'
    (config/'model/equations.json').write_bytes(content)
    monkeypatch.setattr(resources, 'CONFIGS', config)
    manifest = search_loop.source_manifest()
    assert manifest['configs/model/equations.json'] == hashlib.sha256(content).hexdigest()


@pytest.fixture(scope='module')
def current(tmp_path_factory):
    out = tmp_path_factory.mktemp('naming_contracts')/'run'
    run_spec_allocation(ROOT/'configs/problems/nominal.json', out, config={
        'schema_version': 'pll-spec-allocation-1.0', 'target_count': 3,
        'm1_budget': 24, 'm2_budget': 0})
    return out, read_json(out/'initial/verification_handoff.json')


def signed(item):
    item['handoff_sha256'] = fingerprint({k: v for k, v in item.items() if k != 'handoff_sha256'})
    return item


def legacy_handoff(item):
    item = deepcopy(item)
    item['schema_version'] = LEGACY_HANDOFF_SCHEMA
    item['ready_for_stage9'] = item.pop('ready_for_verification')
    item['legacy_fields_not_for_stage9'] = item.pop('legacy_fields_not_for_verification')
    return signed(item)


def test_current_outputs_have_one_authoritative_name(current):
    out, handoff = current
    assert handoff['schema_version'] == HANDOFF_SCHEMA and handoff_ready(handoff)
    validate_handoff(handoff)
    phase = re.compile(r'stage[_-]?\d|track[_-]?[ab](?:[_.-]|$)', re.I)
    assert not any(phase.search(p.name) for p in out.rglob('*'))
    manifest = read_json(out/'run_manifest.json')
    assert manifest['inputs']['problem']['resolved'] == 'problem_resolved.json'
    assert manifest['inputs']['allocator']['resolved'] == 'allocation_config.json'
    assert manifest['handoffs']['m1_to_verification']['ready_field'] == 'ready_for_verification'
    assert manifest['delivery']['candidate_count'] == 0  # M1-ready is not delivery.


def test_legacy_handoff_is_read_without_mutating_record_or_digest(current):
    _, current_handoff = current
    old = legacy_handoff(current_handoff)
    before = deepcopy(old)
    assert validate_handoff(old) == current_handoff['recommended_nominal']['parameters']
    guidance = build_guidance(old, source_uri='TEST:old-handoff')
    assert guidance['source_handoff_sha256'] == old['handoff_sha256']
    assert old == before


@pytest.mark.parametrize('version', [HANDOFF_SCHEMA, LEGACY_HANDOFF_SCHEMA])
def test_mixed_contract_versions_are_rejected_even_after_rehash(current, version):
    _, handoff = current
    item = deepcopy(handoff) if version == HANDOFF_SCHEMA else legacy_handoff(handoff)
    item['ready_for_stage9' if version == HANDOFF_SCHEMA else 'ready_for_verification'] = True
    with pytest.raises(ValueError, match='legacy|mixed'):
        validate_handoff(signed(item))


def test_old_model_record_can_be_read_but_cannot_resume_execution(current):
    _, handoff = current
    item = legacy_handoff(handoff)
    item['model_fingerprint'] = item['source_context_binding']['model_fingerprint'] = '0'*64
    item['recommended_nominal']['model_fingerprint'] = '0'*64
    item['recommendation_recheck']['row']['model_fingerprint'] = '0'*64
    signed(item)
    with pytest.raises(ValueError, match='installed M1'):
        validate_handoff(item)
    assert validate_handoff(item, require_current_model=False) == item['recommended_nominal']['parameters']
    assert build_guidance(item, source_uri='TEST:historical-model')['candidates']


def test_legacy_generated_problem_label_matches_only_legacy_contract(current):
    _, handoff = current
    old = legacy_handoff(handoff)
    p = old['problem']; p.pop('problem_sha256')
    for spec in p['specs']:
        if spec['protocol'] == 'NOT_EVALUATED_BY_M1':
            spec['protocol'] = 'NOT_EVALUATED_IN_STAGE7'
    p['problem_sha256'] = fingerprint(p)
    assert problem_matches_handoff(handoff['problem'], old)
    old['schema_version'] = HANDOFF_SCHEMA
    assert not problem_matches_handoff(handoff['problem'], old)
    old['schema_version'] = LEGACY_HANDOFF_SCHEMA
    old['problem']['fixed_parameters']['N']['value'] += 1
    assert not problem_matches_handoff(handoff['problem'], old)


def test_old_unsigned_feedback_config_normalizes_to_current_schema():
    config = read_json(ROOT/'configs/verification/verify_only.json')
    config['schema_version'] = LEGACY_FEEDBACK_SCHEMA
    normalized = validate_config(config)
    assert normalized['schema_version'] == FEEDBACK_SCHEMA
    assert config['schema_version'] == LEGACY_FEEDBACK_SCHEMA


@pytest.mark.parametrize('legacy', [True, False])
def test_protocol_reader_checks_version_and_frequency_plan_without_native(current, legacy):
    _, handoff = current
    p = parse_parameters(handoff['recommended_nominal']['parameters'])
    protocol = integer_n_protocol(p, legacy=legacy)
    request = {'parameters': handoff['recommended_nominal']['parameters'],
               'M2_model': {'adapter_version': 'pll-continuous-m2-1.1' if legacy else 'pll-continuous-m2-1.2'},
               'protocol': protocol, 'protocol_id': protocol['protocol_id'],
               'protocol_sha256': fingerprint(protocol)}
    validate_recorded_protocol(request)
    assert not re.search(r'stage\d|track_[ab]', json.dumps(protocol), re.I) if not legacy else True
    request['protocol']['frequency_plan']['N'] += 1
    request['protocol_sha256'] = fingerprint(request['protocol'])
    with pytest.raises(ValueError, match='protocol/frequency binding'):
        validate_recorded_protocol(request)
