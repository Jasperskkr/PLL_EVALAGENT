"""Deterministic forward-only representative design; no adaptive allocation/search."""
from __future__ import annotations
from copy import deepcopy
import itertools
from .contracts import FREE_IDS, make_candidate
from pll_allocation.physics_mapping.model import fingerprint


def _radical_inverse(index, base):
    value, weight = 0., 1./base
    while index:
        index, digit = divmod(index, base)
        value += digit*weight
        weight /= base
    return value


def representative_cases(model):
    cases, by_digest = [], {}
    def add(label, category, overrides=None, event=False):
        p = make_candidate(model, overrides)
        digest = fingerprint(p)
        if digest in by_digest:
            old = by_digest[digest]
            old['aliases'].append(label)
            old['event_selected'] |= event
            return
        case = {'case_id': f'C{len(cases):03d}', 'label': label, 'category': category,
                'aliases': [], 'event_selected': event, 'parameters': p}
        cases.append(case)
        by_digest[digest] = case
    add('nominal', 'nominal', event=True)
    # Local derivative points are fixed before prediction; no feedback selection.
    for name in FREE_IDS:
        axis = model['variables'][name]
        if 'range' in axis:
            for scale in (.98, 1.02):
                add(f'local_{name}_{scale}', 'local_sensitivity', {name: axis['default']*scale})
            lo, hi = axis['range']['min'], axis['range']['max']
            for i, f in enumerate((0., .01, .99, 1.)):
                add(f'boundary_{name}_{f}', 'single_parameter_boundary', {name: lo+(hi-lo)*f}, event=i in (0,3))
        else:
            for choice in axis['choices']:
                add(f'choice_{name}_{choice}', 'discrete_sensitivity', {name: choice}, event=choice != axis['default'])
    # Continuous corners at nominal capacitors; cover reachable and unreachable tuning.
    for i, bits in enumerate(itertools.product((0,1), repeat=4)):
        updates = {name: model['variables'][name]['range'][('min','max')[bit]]
                   for name, bit in zip(('Icp','Rz','f0','Kvco'), bits)}
        add(f'continuous_corner_{i:02}', 'coupled_boundary', updates, event=i in (0,3,12,15))
    for i, (c1, c2) in enumerate(itertools.product(model['variables']['C1']['choices'], model['variables']['C2']['choices'])):
        add(f'cap_ratio_{i}', 'capacitor_coupling', {'C1': c1, 'C2': c2}, event=i in (0,2,6,8))
    # 48 fixed low-discrepancy points. Linear range mapping intentionally matches declared coordinates.
    primes = (2,3,5,7,11,13)
    for i in range(1,49):
        update = {}
        for name, base in zip(FREE_IDS, primes):
            axis = model['variables'][name]
            q = _radical_inverse(i,base)
            update[name] = (axis['range']['min']+q*(axis['range']['max']-axis['range']['min']) if 'range' in axis
                            else axis['choices'][min(int(q*len(axis['choices'])),len(axis['choices'])-1)])
        add(f'halton_{i:02}', 'low_discrepancy', update, event=i in (1,12,24,36,48))
    # Fixed forward slices bracket specification boundaries without solving an inverse problem.
    for i in range(17):
        add(f'Icp_spec_slice_{i:02}', 'system_boundary_slice', {'Icp': 50e-6+i*150e-6/16})
    for i in range(17):
        add(f'Rz_spec_slice_{i:02}', 'system_boundary_slice', {'Rz': 2000+i*6000/16})
    # Explicit rail neighborhood within declared ranges; f0=68MHz and Kvco=10MHz/V gives Vreq=1.2V.
    for f0 in (67.99e6,68e6,68.01e6):
        add(f'tuning_rail_{f0}', 'tuning_boundary', {'f0': f0,'Kvco':10e6}, event=True)
    for name, changes in [('gain_product', {'Icp':140e-6,'Kvco':20e6/1.4}),
                          ('high_gain_tradeoff', {'Icp':200e-6,'Kvco':40e6,'Rz':8000}),
                          ('low_gain_tradeoff', {'Icp':50e-6,'Kvco':10e6,'Rz':2000})]:
        add(name,'explicit_coupling',changes,event=True)
    return cases


def abnormal_cases(model):
    cases = []
    for label, name, value in [('negative_R_unstable_extension','Rz',-3820),
                             ('negative_gain_extension','Kvco',-20e6),
                             ('nonideal_CP','CP_mismatch',.1),
                             ('reset_delay','PFD_reset_delay',1e-9),
                             ('leakage','CP_leakage',1e-9)]:
        p = deepcopy(make_candidate(model))
        p['values'][name]['value'] = value
        cases.append({'case_id': 'X'+str(len(cases)).zfill(3), 'label': label,
            'category': 'out_of_declared_domain_anomaly', 'aliases': [], 'event_selected': False, 'parameters': p})
    return cases
