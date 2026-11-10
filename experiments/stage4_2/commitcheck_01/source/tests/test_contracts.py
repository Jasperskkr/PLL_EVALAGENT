from copy import deepcopy
import json
from pathlib import Path
import pytest
from pll_allocation.contracts import build_problem, candidate_grid, check_candidate, ContractError

ROOT=Path(__file__).resolve().parents[1]
def problem(name='regular80'):
    return build_problem(json.loads((ROOT/'examples'/f'{name}.json').read_text(encoding='utf-8')))

@pytest.mark.parametrize('case,count',[('regular80',30),('tight80',30),('finite_domain80',30),('frozen80',110),('joint84',450)])
def test_declared_spaces_and_full_candidates(case,count):
    p=problem(case); grid=list(candidate_grid(p))
    assert len(grid)==count
    assert all(check_candidate(p,c)['status']=='VALID' for c in grid)

@pytest.mark.parametrize('mutation',[
    lambda c:c['blocks'].pop('PFD'),
    lambda c:c['blocks']['CP']['I_up_A'].update(unit='uA'),
    lambda c:c['blocks']['VCO']['Kvco_Hz_per_V'].update(unit='rad/s/V'),
    lambda c:c['blocks']['CP']['q0_C'].update(value=float('nan')),
    lambda c:c['blocks']['CP']['I_up_A'].update(value=1.0),
    lambda c:c['blocks']['CP']['I_down_A'].update(value=1.2e-4),
    lambda c:c['common_conditions'].update(fref_Hz=1.1e7),
    lambda c:c['blocks']['Divider']['N'].update(value=9),
])
def test_rejects_invalid_candidate(mutation):
    p=problem(); c=next(candidate_grid(p)); mutation(c)
    assert check_candidate(p,c)['status']=='INVALID'

@pytest.mark.parametrize('mutation',[
    lambda p:p['system_spec'][0].update(unit='rad'),
    lambda p:p['system_spec'][0].update(measurement='last_instant'),
    lambda p:p['system_spec'][0].update(source=''),
    lambda p:p['system_spec'].append(deepcopy(p['system_spec'][0])),
    lambda p:p['measurement'].update(duration_s=1e-6),
    lambda p:p['operating_context'].update(fout_target_Hz=81e6),
    lambda p:p['operating_context'].update(N=True),
    lambda p:p['operating_context'].update(phase_convention='reference_minus_feedback'),
    lambda p:p['operating_context'].update(temperature_C=85),
    lambda p:p['block_space']['validity'].update(load_model='different'),
])
def test_problem_contract_failures(mutation):
    p=problem(); mutation(p)
    with pytest.raises(ContractError): build_problem(p)
