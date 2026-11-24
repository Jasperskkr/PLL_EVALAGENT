"""Independent polynomial and compatibility checks for conditional descriptors."""
from copy import deepcopy
import math
import numpy as np
import pytest

from pll_allocation.exploration.contracts import load_problem, make_parameters
from pll_allocation.physics_mapping.analytic_features import analytic_features
from pll_allocation.physics_mapping.predictors import predict_rms_jitter, resolve_noise_profile
from pll_allocation.physics_mapping.noise import noise_mapping
from pll_allocation.physics_mapping.model import evaluate, parse_parameters


def candidate():
    return make_parameters(load_problem('configs/problems/nominal.json'))


def test_natural_frequency_damping_and_independent_pole_residual():
    c = candidate(); p = parse_parameters(c); f = analytic_features(c)
    gain = p['Icp']*p['Kvco']/p['N']
    assert f['omega_n_rad_s'] == pytest.approx(math.sqrt(gain/(p['C1']+p['C2'])))
    assert f['zeta_approx'] == pytest.approx(f['omega_n_rad_s']*p['Rz']*p['C2']/2)
    for pole in f['closed_loop_poles']:
        s = complex(pole['real_rad_s'], pole['imag_rad_s'])
        terms = [p['Rz']*p['C1']*p['C2']*s**3, (p['C1']+p['C2'])*s*s,
                 gain*p['Rz']*p['C2']*s, gain]
        assert abs(sum(terms))/sum(map(abs, terms)) < 1e-12
    assert f['predicted_lock_time_s'] is None


def test_noise_prediction_reuses_mapping_numerically():
    c = candidate(); p = predict_rms_jitter(c)
    ref = noise_mapping(c, resolve_noise_profile(), [1e4, 1e6])
    assert p['predicted_jitter_s'] == pytest.approx(ref['integrated_jitter_s'], rel=2e-14)
    assert p['noise_source_fractions'] == pytest.approx(ref['source_fractions'], rel=2e-14)
    assert p['noise_profile_identity']['sha256'] == ref['noise_profile_sha256']
    assert p['formal_M2_status'] == 'UNKNOWN'


def test_f0_invariance_and_startup_sensitivity():
    a = candidate(); b = deepcopy(a); b['values']['f0']['value'] = 75e6
    assert evaluate(a).metrics['BW_Hz'] == evaluate(b).metrics['BW_Hz']
    assert evaluate(a).metrics['PM_deg'] == evaluate(b).metrics['PM_deg']
    assert predict_rms_jitter(a)['predicted_jitter_s'] == predict_rms_jitter(b)['predicted_jitter_s']
    assert analytic_features(a)['initial_frequency_error_Hz'] != analytic_features(b)['initial_frequency_error_Hz']


def test_invalid_inputs_remain_unknown():
    c = candidate(); c['values']['Kvco2']['value'] = 1
    assert analytic_features(c)['slip_risk'] == 'UNKNOWN'
    assert predict_rms_jitter(c)['predicted_jitter_s'] is None
    assert predict_rms_jitter(candidate(), band_Hz=(1e6, 1e4))['predicted_jitter_s'] is None
