"""Conditional-domain derivations: strict tuning, joint emptiness and independent KCL."""
import math

import pytest

from tools.build_block_relation_atlas import (
    bandwidth_domain, product_split, tuning_interval, witness, kcl_response,
    relation_rows, variable_catalog, derived_ranges, build,
)
from pll_allocation.pipeline_contracts import load_inputs
from pll_allocation.block_space.contracts import check_parameters, make_candidate
from pll_allocation.allocation.core import values
from pll_allocation.physics_mapping.model import evaluate


@pytest.fixture(scope='module')
def inputs():
    _, model, spec, _ = load_inputs()
    return model, spec


def test_every_original_variable_has_relations_and_no_new_independent_axis(inputs):
    model, _ = inputs
    catalog = variable_catalog(model, relation_rows())
    assert len(catalog) == 41
    assert {v['id'] for v in catalog} == {v['id'] for v in model['variable_catalog']}
    assert {v['id'] for v in catalog if v['kind']=='free_allocation_parameter'} == {
        'Icp','Rz','C1','C2','f0','Kvco'}
    assert all(v['relation_ids'] for v in catalog)


def test_marginal_range_choices_do_not_turn_into_new_continuous_axes(inputs):
    model,_=inputs
    rows={r['id']:r for r in derived_ranges(model)}
    assert rows['q']['choices']==[3.5,6,11,21,41]
    assert len(rows['C_sum']['choices'])==9
    assert rows['Vctrl_required']['range']==[.1,2]
    assert rows['P']['range']==[500,8000]


def test_generator_refuses_existing_directory_before_any_model_call(tmp_path):
    with pytest.raises(FileExistsError):
        build(tmp_path)


def test_tuning_open_boundary_is_preserved(inputs):
    model, _ = inputs
    interval = tuning_interval(model, 10e6)
    assert interval == {'min':68e6,'max':76e6,'min_inclusive':False,
                         'max_inclusive':True,'empty':False,'unit':'Hz'}
    assert tuning_interval(model,20e6)['min_inclusive']
    rail = make_candidate(model,{'Kvco':10e6,'f0':68e6})
    assert check_parameters(model,rail)['model_validity']=='OUT_OF_DOMAIN'
    inside = make_candidate(model,{'Kvco':10e6,'f0':68e6+1})
    assert check_parameters(model,inside)['model_validity']=='VALID'


def test_fixed_f0_product_split_has_open_current_gain_boundary(inputs):
    model, _ = inputs
    # P=1000 permits 10–20 MHz/V from gain alone; f0=68MHz excludes exactly 10.
    result = product_split(model,1000,f0=68e6)
    assert result['min']==10e6 and result['max']==20e6
    assert not result['min_inclusive'] and not result['empty']
    # Lowest declared product forces Kvco=10MHz/V; same f0 gives an empty intersection.
    assert product_split(model,500,f0=68e6)['empty']
    assert not product_split(model,500,f0=70e6)['empty']


@pytest.mark.parametrize('c1,c2',[(100e-12,.5e-9),(200e-12,.5e-9),(200e-12,1e-9)])
def test_three_declared_pairs_have_no_PM50_shape(inputs,c1,c2):
    model,spec=inputs
    d=bandwidth_domain(model,spec,c1,c2,math.sqrt(1+c2/c1))
    assert d['status']=='EMPTY' and 'PM shape' in d['reason']
    # They remain legal model inputs: failure of SystemSpec is a separate layer.
    assert check_parameters(model,make_candidate(model,{'C1':c1,'C2':c2}))['model_validity']=='VALID'


def test_PM_admissible_shape_can_still_have_empty_R_gain_BW_intersection(inputs):
    model,spec=inputs
    d=bandwidth_domain(model,spec,50e-12,2e-9,1.5)
    assert d['status']=='EMPTY'
    assert d['BW_min_Hz']>d['BW_max_Hz']


def test_nonempty_band_reconstructs_distinct_complete_points_and_KCL_crossings(inputs):
    model,spec=inputs
    d=bandwidth_domain(model,spec,50e-12,2e-9,math.sqrt(41))
    assert d['status']=='NONEMPTY'
    assert d['BW_min_Hz']==150e3 and d['BW_max_Hz']==300e3
    for fraction in (.1,.9):
        candidate,target_bw=witness(model,d,50e-12,2e-9,fraction)
        domain=check_parameters(model,candidate)
        assert domain['declared_domain']=='IN_DECLARED_DOMAIN' and domain['model_validity']=='VALID'
        result=evaluate(candidate)
        assert result.status.value=='OK' and not result.verified_joint_block_spec
        assert result.metrics['BW_Hz']==pytest.approx(target_bw,rel=1e-9)
        assert result.metrics['PM_deg']>=50
        p=values(candidate)
        assert abs(kcl_response(p,result.metrics['BW_Hz'])[2])==pytest.approx(1/math.sqrt(2),rel=1e-9)
        assert abs(kcl_response(p,result.metrics['UGF_Hz'])[1])==pytest.approx(1,rel=1e-9)


@pytest.mark.parametrize('c1,c2,x',[(75e-12,1e-9,3),(50e-12,1e-9,float('nan')),
                                  (50e-12,1e-9,0)])
def test_interpolation_and_invalid_shape_cannot_gain_domain_claim(inputs,c1,c2,x):
    model,spec=inputs
    with pytest.raises(ValueError):
        bandwidth_domain(model,spec,c1,c2,x)
