"""Integration boundaries; fixture cases are not reported as executed M2 experiments."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import pytest
from pll_allocation import pipeline
from pll_allocation.allocation import TrackAPolicy
from pll_allocation.pipeline_contracts import check_result, load_inputs, make_feedback, m2_label
from pll_allocation.allocation.core import Meter, assess_m1, proposal, read, write_new
from pll_allocation.block_space.contracts import make_candidate
from pll_allocation.physics_mapping.model import fingerprint
from pll_allocation.verification.verify import assemble_result
from pll_allocation.verification import simulator

ROOT = Path(__file__).resolve().parents[1]


def fixture_result():
    config, model, spec, doc = load_inputs()
    c = make_candidate(model)
    item = proposal(model, spec, c, 'nominal', assess_m1(model, spec, c, Meter()), {}, 'fixture')
    evidence = read(ROOT/'tests/fixtures/stage3a_nominal_measured.json')
    result = assemble_result(item, doc, {}, evidence['capture'], {}, evidence['comparison'])
    return item, doc, result


def test_frozen_assets_and_packaged_kernel_are_identical():
    config, model, spec, doc = load_inputs()
    assert spec == model['experiment']['system_spec']
    assert spec['draft'] is True
    frozen = read(ROOT/'tests/fixtures/verification/frozen_bindings.json')
    assert fingerprint(model) == frozen['model_sha256']
    assert hashlib.sha256((ROOT/'pll_allocation/verification/kernel.cpp').read_bytes()).hexdigest() == frozen['kernel_sha256']
    assert fingerprint(doc) == frozen['protocol_sha256']


@pytest.mark.parametrize('name', ['model', 'system_spec', 'protocol', 'equations', 'versions', 'kernel'])
def test_mixed_version_config_is_rejected(tmp_path, name):
    cfg, *_ = load_inputs()
    for key in ('model', 'system_spec', 'protocol', 'equations'):
        cfg[key] = str(ROOT/'configs'/cfg[key])
    if name == 'versions':
        cfg['bindings']['versions']['formula_version'] = 'different'
    else:
        cfg['bindings'][name+'_sha256'] = 'different'
    path = tmp_path/'config.json'
    write_new(path, cfg)
    with pytest.raises(ValueError, match='binding|version'):
        load_inputs(path)


@pytest.mark.parametrize('field', ['candidate_id', 'parameter_sha256', 'proposal_versions', 'model_version', 'protocol_sha256', 'fixed_system_spec_sha256'])
def test_mismatched_result_never_accepted(field):
    item, doc, result = fixture_result()
    result[field] = 'wrong'
    with pytest.raises(ValueError, match='binding'):
        check_result(result, item, doc)


@pytest.mark.parametrize('name', ['model', 'kernel.cpp'])
def test_result_source_identity_cannot_be_mixed(name):
    item, doc, result = fixture_result()
    result['source_hashes'][name] = 'wrong'
    with pytest.raises(ValueError, match='source binding'):
        check_result(result, item, doc)


@pytest.mark.parametrize('metric', ['PM_deg', 'output_frequency_Hz'])
def test_unknown_metrics_cannot_be_upgraded_to_pass(metric):
    item, doc, result = fixture_result()
    next(c for c in result['constraints'] if c['metric'] == metric)['status'] = 'PASS'
    with pytest.raises(ValueError, match='cannot pass'):
        check_result(result, item, doc)


def test_partial_fail_unknown_and_feedback_reach_existing_agent():
    item, doc, result = fixture_result()
    check_result(result, item, doc)
    assert result['overall_status'] == 'UNKNOWN' and m2_label(result) == 'M2_PARTIAL_PASS'
    fb = make_feedback(item, result, doc, {'M2_verifications': 0})
    receipt = TrackAPolicy('analytical', {}).receive_feedback(item['joint_block_spec'], fb)
    assert receipt['status'] == 'RECEIVED_BY_ALLOCATION_AGENT'
    assert fb['source'] == 'M2' and fb['kind'] == 'UNRELIABLE_MEASUREMENT'
    assert fb['unknown_metrics'] == ['output_frequency_Hz', 'PM_deg']
    bw = next(c for c in result['constraints'] if c['metric'] == 'BW_Hz')
    bw['status'], result['overall_status'] = 'FAIL', 'FAIL'
    fb = make_feedback(item, result, doc, {'M2_verifications': 1})
    assert fb['kind'] == 'BW' and fb['measurements']['BW_Hz']['reliable']
    assert m2_label(result) == 'M2_FAIL'
    for c in result['constraints']:
        c['status'] = 'UNKNOWN'
    result['overall_status'] = 'UNKNOWN'
    assert m2_label(result) == 'M2_UNKNOWN'


def test_real_runner_saves_first_candidate_before_any_tb_and_receives_feedback(tmp_path, monkeypatch):
    original = pipeline.verify
    root = tmp_path/'real'
    def observed(item, out):
        assert read(root/'initial_joint_block_spec.json') == item['joint_block_spec']
        assert read(root/'attempt_001/AllocationProposal.json') == item
        assert not (root/'attempt_001/structured_feedback.json').exists()
        return original(item, out)  # real full Track B; no fabricated metrics
    monkeypatch.setattr(pipeline, 'verify', observed)
    result = pipeline.run_pipeline(root, 'analytical')
    assert result['status'] == 'M2_PARTIAL_PASS'
    assert result['cost']['native_completed_runs'] == 106
    assert result['cost']['M2_calls'] == 1 and result['cost']['M1_posthoc_calls'] == 1
    assert result['feedback_received_by_agent'] and not result['full_behavioral_pass']
    old = (root/'result.json').read_bytes()
    with pytest.raises(FileExistsError):
        pipeline.run_pipeline(root)
    assert (root/'result.json').read_bytes() == old


def test_verifier_exception_is_costed_and_cannot_pass(tmp_path, monkeypatch):
    def broken(*args):
        raise TimeoutError('test injected backend exception')
    monkeypatch.setattr(pipeline, 'verify', broken)
    result = pipeline.run_pipeline(tmp_path/'broken')
    assert result['status'] == 'PIPELINE_ERROR'
    assert result['cost']['M2_calls'] == 1
    assert result['attempts'][0]['M2_status'] == 'M2_UNKNOWN'
    assert not result['full_behavioral_pass']


def test_missing_real_llm_has_no_candidate_or_fallback(tmp_path, monkeypatch):
    for key in ('ANTHROPIC_MODEL', 'ANTHROPIC_BASE_URL', 'ANTHROPIC_AUTH_TOKEN'):
        monkeypatch.delenv(key, raising=False)
    result = pipeline.run_pipeline(tmp_path/'missing', 'llm_agent')
    assert result['status'] == 'POLICY_OR_TOOL_FAILED'
    assert result['cost']['LLM_calls'] == result['cost']['M2_calls'] == 0
    assert not (tmp_path/'missing/initial_joint_block_spec.json').exists()


def test_budget_must_cover_all_permitted_submissions(tmp_path):
    with pytest.raises(ValueError, match='budget'):
        pipeline.run_pipeline(tmp_path/'budget', m2_budget=1, repair_budget=1)


def test_native_identity_mismatch_is_not_silently_loaded(tmp_path, monkeypatch):
    from pll_allocation.verification import build_identity
    root = tmp_path/'native'
    (root/'build').mkdir(parents=True)
    (root/'kernel.cpp').write_bytes(b'source')
    (root/'build/kernel.dll').write_bytes(b'changed')
    write_new(root/'build/identity.json', {'sha256': {'kernel.cpp': 'old', 'build/kernel.dll': 'old'}})
    monkeypatch.setattr(build_identity, 'HERE', root)
    with pytest.raises(RuntimeError, match='BINDING_MISMATCH'):
        build_identity.check_build()


def test_missing_native_backend_produces_no_fabricated_trace(tmp_path, monkeypatch):
    monkeypatch.setattr(simulator, 'HERE', tmp_path)
    _, model, *_ = load_inputs()
    with pytest.raises(RuntimeError, match='unavailable'):
        simulator.simulate(make_candidate(model), duration_s=1e-6, onset_s=1e-6)


def test_real_verifier_missing_backend_records_unknown_failure_cost_and_feedback(tmp_path, monkeypatch):
    monkeypatch.setattr(simulator, 'HERE', tmp_path/'missing_native')
    result = pipeline.run_pipeline(tmp_path/'missing_backend')
    assert result['status'] == 'M2_UNKNOWN'
    assert result['cost']['M2_calls'] == result['cost']['native_failed_attempts'] == 1
    assert result['cost']['native_completed_runs'] == 0
    assert result['feedback_received_by_agent'] and not result['full_behavioral_pass']


def test_existing_proposal_m1_is_bit_identical():
    _, model, spec, _ = load_inputs()
    original = read(ROOT/'tests/fixtures/verification/analytical_proposal_stage3a.json')
    actual = assess_m1(model, spec, original['joint_block_spec'], Meter())
    assert actual == original['M1']
