"""Research integrity, judgment and lineage; fixtures are not new simulations."""
from copy import deepcopy
from pathlib import Path
import pytest
from pll_allocation.allocation.core import read, Meter, assess_m1, proposal
from pll_allocation.allocation.allocate import analytical
from pll_allocation.physics_mapping.model import fingerprint
from pll_allocation.pipeline_contracts import load_inputs, check_result
from pll_allocation.scenarios import load_scenario, validate_scenario
from pll_allocation.verification.scenario import measurement_proposal, rejudge
from pll_allocation.pipeline import run_pipeline

ROOT = Path(__file__).resolve().parents[1]


def scenario(sid='S1'):
    config, model, frozen, protocol = load_inputs()
    doc, spec, binding = load_scenario(ROOT/f'experiments/stage5/scenarios/{sid}.json', config, frozen)
    return config, model, frozen, protocol, doc, spec, binding


def item_for(sid='S1'):
    _, model, _, protocol, doc, spec, binding = scenario(sid)
    meter = Meter()
    c, meta = analytical(model, load_inputs()[2], meter)
    item = proposal(model, spec, c, 'analytical', assess_m1(model, spec, c, meter), meta, 'research-test')
    item.update(research_scenario=doc, scenario_binding=binding)
    return item, protocol


def measured_fixture(item):
    measured = read(ROOT/'tests/fixtures/verification/analytical_M2_stage3a.json')
    measured['candidate_id'] = item['candidate_id']
    return measured


def rehash(doc):
    doc['scenario_sha256'] = fingerprint({k: v for k, v in doc.items() if k != 'scenario_sha256'})


def test_only_three_effective_thresholds_change_and_original_not_mutated():
    _, _, frozen, _, _, spec, binding = scenario()
    restored = deepcopy(spec)
    for a, b in zip(restored['metrics'], frozen['metrics']):
        for key in ('min', 'max'):
            if key in b:
                a[key] = b[key]
    assert restored == frozen
    assert binding['effective_system_spec_sha256'] != binding['base_system_spec_sha256']
    assert spec['metrics'][0] == frozen['metrics'][0]
    assert load_inputs()[2] == frozen


@pytest.mark.parametrize('field,value', [('scenario_id',''),('version',''),('scope','FORMAL'),('schema_version','wrong')])
def test_invalid_scenario_identity_rejected(field, value):
    cfg, _, frozen, _, doc, _, _ = scenario()
    doc[field] = value; rehash(doc)
    with pytest.raises(ValueError): validate_scenario(doc, cfg, frozen)


@pytest.mark.parametrize('mutation', ['hash','base','extra','frequency','tolerance','boolean','inverted','nan'])
def test_hash_and_restricted_semantics_rejected(mutation):
    cfg, _, frozen, _, doc, _, _ = scenario()
    if mutation == 'hash': doc['scenario_sha256'] = '0'*64
    elif mutation == 'base': doc['base_bindings']['model_sha256'] = '0'*64
    elif mutation == 'extra': doc['f_ref'] = 12e6
    elif mutation == 'frequency': doc['overrides']['output_frequency_Hz'] = {'min':84e6}
    elif mutation == 'tolerance': doc['overrides']['BW_Hz']['tolerance'] = 100
    elif mutation == 'boolean': doc['overrides']['PM_deg']['min'] = True
    elif mutation == 'inverted': doc['overrides']['BW_Hz']['max'] = 1
    elif mutation == 'nan':
        doc['overrides']['PM_deg']['min'] = float('nan')
        with pytest.raises(ValueError): validate_scenario(doc,cfg,frozen)
        return
    if mutation != 'hash': rehash(doc)
    with pytest.raises(ValueError): validate_scenario(doc, cfg, frozen)


def test_projection_preserves_formal_verifier_without_accepting_unbound_custom_spec():
    item, _ = item_for()
    projected, binding = measurement_proposal(item)
    assert projected['joint_block_spec'] == item['joint_block_spec']
    assert projected['system_spec'] == load_inputs()[2]
    assert 'research_scenario' not in projected and binding == item['scenario_binding']
    from pll_allocation.verification.verify import validate_proposal
    with pytest.raises(ValueError): validate_proposal(item)
    validate_proposal(projected)


def test_same_measured_bw_has_different_scenario_judgment_and_unknowns_preserved():
    for sid, expected in [('S0','PASS'),('S2','FAIL')]:
        item, protocol = item_for(sid)
        # Use real historical fixture as adapter input only, not claimed as new M2.
        result = rejudge(item, measured_fixture(item))
        check_result(result, item, protocol)
        checks = {x['metric']:x['status'] for x in result['constraints']}
        assert checks == {'BW_Hz':expected,'PM_deg':'UNKNOWN','output_frequency_Hz':'UNKNOWN'}
        assert result['overall_status'] == ('FAIL' if expected=='FAIL' else 'UNKNOWN')
        assert result['verified_joint_block_spec'] is False


@pytest.mark.parametrize('corruption', ['binding','target','bw_status','pm_pass'])
def test_scene_bound_result_cannot_be_swapped_or_upgrade_unknown(corruption):
    item, protocol = item_for('S0')
    result = rejudge(item, measured_fixture(item))
    if corruption=='binding': result['scenario_binding']['scenario_id']='S9'
    elif corruption=='target': result['constraints'][1]['target']['max']=999
    elif corruption=='bw_status': next(c for c in result['constraints'] if c['metric']=='BW_Hz')['status']='FAIL'
    else: next(c for c in result['constraints'] if c['metric']=='PM_deg')['status']='PASS'
    with pytest.raises(ValueError): check_result(result,item,protocol)


@pytest.mark.parametrize('strategy', ['analytical','random','llm_agent'])
def test_m1_infeasible_preflight_skips_all_policy_and_tb(tmp_path, strategy):
    class ForbiddenPolicy:
        def propose(self,*args): raise AssertionError('infeasible must skip proposal')
    result=run_pipeline(tmp_path/strategy,strategy,scenario_path=ROOT/'experiments/stage5/scenarios/S4.json',policy=ForbiddenPolicy())
    assert result['status']=='INFEASIBLE_UNDER_M1_ASSUMPTIONS'
    assert result['cost']['M2_calls']==result['cost']['LLM_calls']==0
    assert result['attempts']==[]


def test_unknown_only_parent_cannot_start_feedback_repair(tmp_path):
    item, protocol = item_for('S0')
    from pll_allocation.allocation.core import write_new
    write_new(tmp_path/'AllocationProposal.json', item)
    write_new(tmp_path/'BehavioralVerificationResult.json',rejudge(item,measured_fixture(item)))
    with pytest.raises(ValueError,match='certified hard FAIL'):
        run_pipeline(tmp_path/'child',scenario_path=ROOT/'experiments/stage5/scenarios/S0.json',feedback_from=tmp_path)
