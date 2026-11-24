"""Public input, result selection and portable handoff invariants."""
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from pll_allocation import pipeline
from pll_allocation.agent.feedback import load_handoff
from pll_allocation.agent.handoff import validate_handoff
from pll_allocation.agent.spec_allocation import run_spec_allocation
from pll_allocation.delivery import validate_recorded_protocol, validate_sizing_handoff
from pll_allocation.exploration.contracts import load_problem
from pll_allocation.io_contracts import read_json
from pll_allocation.physics_mapping.model import fingerprint
from pll_allocation.vco_sizing.contract import validate_source

ROOT = Path(__file__).resolve().parents[1]
NOMINAL = ROOT / 'configs/problems/nominal.json'


@pytest.fixture(scope='module')
def allocation(tmp_path_factory):
    out = tmp_path_factory.mktemp('io_boundaries') / 'run'
    result = run_spec_allocation(NOMINAL, out, config={
        'schema_version': 'pll-spec-allocation-1.0', 'target_count': 3,
        'm1_budget': 24, 'm2_budget': 0})
    return out, result


@pytest.mark.parametrize('payload', ['{"a":1,"a":2}', '{"a":{"b":1,"b":2}}',
                                   '{"a":NaN}', '{"a":Infinity}', '{"a":-Infinity}', '{"a":1e999}'])
def test_ambiguous_or_nonfinite_json_is_rejected(tmp_path, payload):
    path = tmp_path / 'input.json'
    path.write_text(payload, encoding='utf-8-sig')
    with pytest.raises(ValueError, match='duplicate|non-finite'):
        read_json(path)


def test_problem_duplicate_is_rejected_before_resolution(tmp_path):
    path = tmp_path / 'problem.json'
    path.write_text('{"problem_id":"silently overridden",' + NOMINAL.read_text(encoding='utf-8').lstrip()[1:], encoding='utf-8')
    with pytest.raises(ValueError, match='duplicate JSON key: problem_id'):
        load_problem(path)


def test_cli_input_errors_are_structured_and_leave_no_output(tmp_path, capsys):
    out = tmp_path / 'out'
    assert pipeline.main(['--problem', str(tmp_path / 'missing.json'), '--out', str(out)]) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.out)['status'] == 'INPUT_OR_OUTPUT_ERROR'
    assert 'Traceback' not in captured.err and not out.exists()
    config = tmp_path / 'config.json'
    config.write_text('{"mode":"DETERMINISTIC","mode":"AUTO_HYBRID"}', encoding='utf-8')
    assert pipeline.main(['--problem', str(NOMINAL), '--allocator-config', str(config), '--out', str(out)]) == 2
    assert 'duplicate JSON key: mode' in capsys.readouterr().out and not out.exists()


@pytest.mark.parametrize('payload', ['null', '[]', '1'])
def test_external_object_contracts_reject_other_json_types(tmp_path, capsys, payload):
    config = tmp_path / 'config.json'
    config.write_text(payload, encoding='utf-8')
    out = tmp_path / 'out'
    assert pipeline.main(['--problem', str(NOMINAL), '--allocator-config', str(config), '--out', str(out)]) == 2
    assert json.loads(capsys.readouterr().out)['status'] == 'INPUT_OR_OUTPUT_ERROR'
    assert not out.exists()
    for validator in (validate_handoff, validate_source):
        with pytest.raises(ValueError):
            validator(json.loads(payload))


@pytest.mark.parametrize('updates', [{'gate_status': 'BLOCKED'}, {'gate_reasons': ['not ready']}])
def test_nominal_gate_cannot_disagree_even_after_rehash(allocation, updates):
    out, _ = allocation
    handoff = read_json(out / 'initial/verification_handoff.json')
    handoff.update(updates)
    handoff['handoff_sha256'] = fingerprint({k: v for k, v in handoff.items() if k != 'handoff_sha256'})
    with pytest.raises(ValueError, match='gate status/reasons'):
        validate_handoff(handoff)


@pytest.mark.parametrize('updates', [
    {'joint_target_reached': True}, {'joint_status': 'TARGET_REACHED'},
    {'recommended_candidate_sha256': '0' * 64}, {'candidate_count': True}, {'m2_target_count': 0},
])
def test_delivery_summary_is_checked_by_the_same_consumer_gate(allocation, updates):
    out, _ = allocation
    handoff = read_json(out / 'sizing_handoff.json')
    handoff.update(updates)
    for validator in (validate_sizing_handoff, validate_source):
        with pytest.raises(ValueError):
            validator(handoff)


def test_manifest_points_to_one_authoritative_delivery_and_bound_outputs(allocation):
    out, result = allocation
    manifest = read_json(out / 'run_manifest.json')
    assert manifest['delivery']['candidate_count'] == 0
    assert not manifest['delivery']['target_reached']
    assert manifest['delivery']['candidate_set'] == 'sizing_handoff.json#/candidates'
    assert manifest['delivery']['recommended_candidate'].endswith('#/recommended_M2_supported')
    assert result['recommended'] is not None and result['recommended_M2_supported'] is None
    assert manifest['problem_source']['sha256'] == hashlib.sha256(NOMINAL.read_bytes()).hexdigest()
    for record in manifest['artifacts'].values():
        assert not Path(record['path']).is_absolute() and 'stage9' not in record['path']
        assert hashlib.sha256((out / record['path']).read_bytes()).hexdigest() == record['sha256']
    validate_sizing_handoff(read_json(out / 'sizing_handoff.json'))


def test_complete_run_relocates_without_original_and_never_falls_back_on_invalid_context(allocation, tmp_path, monkeypatch):
    out, _ = allocation
    moved = tmp_path / 'moved'
    shutil.copytree(out, moved)
    path = moved / 'initial/verification_handoff.json'
    original_read = Path.read_text
    def forbid_original(path, *args, **kwargs):
        if path.resolve().is_relative_to(out.resolve()):
            raise AssertionError('relocated handoff read original run')
        return original_read(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'read_text', forbid_original)
    handoff, context = load_handoff(path, NOMINAL)
    assert context.is_relative_to(moved)
    assert validate_handoff(handoff) == handoff['recommended_nominal']['parameters']
    context.write_text('{}', encoding='utf-8')
    with pytest.raises((ValueError, KeyError)):
        load_handoff(path, NOMINAL)


def test_old_absolute_context_contract_still_loads(allocation, tmp_path):
    out, _ = allocation
    handoff = read_json(out / 'initial/verification_handoff.json')
    handoff['source_context_binding'].pop('relative_path')
    handoff['handoff_sha256'] = fingerprint({k: v for k, v in handoff.items() if k != 'handoff_sha256'})
    path = tmp_path / 'old_handoff.json'
    path.write_text(json.dumps(handoff), encoding='utf-8')
    loaded, context = load_handoff(path, NOMINAL)
    assert context == Path(loaded['source_context_binding']['path'])


def test_external_context_on_another_drive_preserves_absolute_binding(allocation, tmp_path, monkeypatch):
    from pll_allocation.agent.handoff import build_handoff
    from pll_allocation.agent.candidates import CandidateArchive
    from pll_allocation.region_explorer import RegionExplorer
    out, _ = allocation
    source = read_json(out / 'initial/verification_handoff.json')
    ex = RegionExplorer(source['source_context_binding']['path'], tmp_path / 'executor', m1_budget=3)
    archive = CandidateArchive(ex, tmp_path / 'archive.jsonl')
    def other_drive(*args):
        raise ValueError('path is on another Windows drive')
    monkeypatch.setattr('pll_allocation.agent.handoff.os.path.relpath', other_drive)
    handoff = build_handoff(ex, archive, source['recommended_nominal'], source['recommendation_recheck'],
                            source['run_state'], ex.cost(), handoff_dir=tmp_path)
    ex.close()
    assert 'relative_path' not in handoff['source_context_binding']
    assert validate_handoff(handoff) == source['recommended_nominal']['parameters']


@pytest.mark.parametrize('version', ['pll-continuous-m2-1.0', 'pll-continuous-m2-1.1'])
def test_recorded_protocol_supports_both_versions_without_native_build(allocation, monkeypatch, version):
    from pll_allocation.verification import continuous
    from pll_allocation.verification.experiments import protocol
    from copy import deepcopy
    out, _ = allocation
    handoff = read_json(out / 'initial/verification_handoff.json')
    current = continuous.verification_request(handoff, run_id='TEST:IO', observation_id='TEST:PROTOCOL', timeout_s=30)
    request = deepcopy(current)
    if version == 'pll-continuous-m2-1.0':
        request['protocol'] = protocol()
        request['protocol_id'] = request['protocol']['protocol_id']
        request['protocol_sha256'] = fingerprint(request['protocol'])
    request['M2_model']['adapter_version'] = version
    def unavailable(*args):
        raise AssertionError('reading a recorded protocol must not require a native build')
    monkeypatch.setattr(continuous, 'check_build', unavailable)
    validate_recorded_protocol(request)
    if version.endswith('1.1'):
        request['protocol']['frequency_plan']['N'] += 1
    else:
        request['parameters']['values']['N']['value'] = 10
    request['protocol_sha256'] = fingerprint(request['protocol'])
    with pytest.raises(ValueError, match='protocol|binding'):
        validate_recorded_protocol(request)
