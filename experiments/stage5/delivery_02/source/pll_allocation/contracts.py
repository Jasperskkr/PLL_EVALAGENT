"""Versioned JSON contracts and deterministic constraints, independent of policies."""
from __future__ import annotations
from copy import deepcopy
import hashlib
import itertools
import json
import math
from typing import Protocol

SCHEMA = 'pll-allocation-1.0'
BLOCKS = ('PFD', 'CP', 'LF', 'VCO', 'Divider')
PARAMETERS = {
 'PFD': {'reset_s':'s'},
 'CP': {'I_up_A':'A','I_down_A':'A','q0_C':'C'},
 'LF': {'Rz_Ohm':'Ohm','C1_F':'F','C2_F':'F','Cload_F':'F','Rload_Ohm':'Ohm'},
 'VCO': {'V0_V':'V','f0_Hz':'Hz','Kvco_Hz_per_V':'Hz/V','voltage_min_V':'V','voltage_max_V':'V'},
 'Divider': {'N':'1'},
}
METRICS = {
 'mean_phase_abs_deg': ('deg','<=','final_50_complete_reference_cycles'),
 'tail_max_abs_frequency_error_ppm': ('ppm','<=','final_50_complete_reference_cycles'),
 'lock_status': ('1','==','frozen_lock_protocol_v1'),
 'lock_time_s': ('s','<=','frozen_lock_protocol_v1'),
 'output_frequency_Hz': ('Hz','==','tail_mean_complete_reference_cycles'),
 'vctrl_min_V': ('V','>=','full_trajectory_extrema'),
 'vctrl_max_V': ('V','<=','full_trajectory_extrema'),
}

class ContractError(ValueError):
    pass

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)

def digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()

def number(value, name, positive=False):
    if type(value) not in (int, float) or not math.isfinite(value) or (positive and value <= 0):
        raise ContractError(f'{name}: finite numeric value required' + (' > 0' if positive else ''))
    return value

def build_problem(raw):
    if not isinstance(raw, dict) or raw.get('schema_version') != SCHEMA:
        raise ContractError('unsupported problem schema')
    p = deepcopy(raw)
    if not isinstance(p.get('task_id'),str) or not p['task_id'].strip():
        raise ContractError('task_id required')
    top = p.get('topology',{})
    if top.get('id') != 'integer_n_cppll' or top.get('blocks') != list(BLOCKS) or top.get('connections') != [
        ['PFD','CP'],['CP','LF'],['LF','VCO'],['VCO','Divider'],['Divider','PFD']]:
        raise ContractError('unsupported fixed topology')
    c = p.get('operating_context',{})
    for k in ('fref_Hz','fout_target_Hz','VDD_V'):
        number(c.get(k),k,True)
    number(c.get('temperature_C'),'temperature_C')
    if type(c.get('N')) is not int or c['N'] < 1 or not math.isclose(c['fout_target_Hz'],c['N']*c['fref_Hz'],rel_tol=1e-12):
        raise ContractError('fout=N*fref and integer N required')
    if c['VDD_V'] != 1.8 or c['temperature_C'] != 27:
        raise ContractError('backend operating-domain: only 1.8V, 27C supported')
    if c.get('charge_definition') != 'net_balance_charge_including_local_proxy_demand':
        raise ContractError('explicit q0 including local proxy demand required')
    if c.get('phase_convention') != 'feedback_minus_reference':
        raise ContractError('phase convention mismatch')
    for k in ('Vctrl_V','Vc2_V','feedback_error_cycles'):
        number(p.get('initialization',{}).get(k),k)
    m = p.get('measurement',{})
    if m != {'duration_s':4e-5,'tail_cycles':50,'lock_phase_deg':5.0,'lock_frequency_ppm':100.0,'lock_hold_cycles':20}:
        raise ContractError('preserve frozen 40us/tail50/hold20 measurement protocol')
    cycles = c['fref_Hz']*m['duration_s']
    if not math.isclose(cycles,round(cycles),abs_tol=1e-8) or not 50 <= cycles <= 10000:
        raise ContractError('bounded complete reference cycles required')
    if not 1e7 <= c['fref_Hz'] <= 1.05e7 or c['N'] != 8:
        raise ContractError('backend version domain: 10-10.5MHz, N=8')
    specs = p.get('system_spec',[])
    if not isinstance(specs,list) or not specs:
        raise ContractError('nonempty system_spec required')
    seen=set()
    for spec in specs:
        name=spec.get('metric')
        if not isinstance(name,str) or name in seen:
            raise ContractError('duplicate/invalid metric')
        seen.add(name)
        if not spec.get('source') or not spec.get('measurement') or not spec.get('unit'):
            raise ContractError('metric source/unit/measurement required')
        if spec.get('operator') not in {'<=','>=','=='}:
            raise ContractError('invalid comparator')
        if name in METRICS and (spec['unit'],spec['operator'],spec['measurement']) != METRICS[name]:
            raise ContractError('metric protocol mismatch: '+name)
        if name == 'lock_status':
            if spec.get('value') != 'LOCKED': raise ContractError('LOCKED target required')
        else:
            number(spec.get('value'),name)
        number(spec.get('tolerance'),name+'.tolerance')
        if spec['tolerance'] < 0: raise ContractError('nonnegative tolerance required')
        if name in {'mean_phase_abs_deg','tail_max_abs_frequency_error_ppm'} and spec['value'] <= 0:
            raise ContractError('positive phase/frequency bound required')
    if not {'mean_phase_abs_deg','tail_max_abs_frequency_error_ppm','lock_status'} <= seen:
        raise ContractError('three legacy measurements required')
    space=p.get('block_space',{})
    if space.get('parameter_role') != 'DECLARED_TARGET' or not space.get('source'):
        raise ContractError('declared space source required')
    domain=space.get('validity',{})
    if domain != {'model_id':'signed_charge_exact_ideal_rc_linear_vco_v1',
                   'empirical_accuracy':'NOT_ESTABLISHED_FOR_NEW_TARGETS',
                   'load_model':'local_proxy_dc_in_q0_incremental_conductance_omitted'}:
        raise ContractError('model domain/assumptions mismatch')
    if set(space.get('blocks',{})) != set(BLOCKS): raise ContractError('all space blocks required')
    count=1
    for block,params in PARAMETERS.items():
        if set(space['blocks'][block]) != set(params): raise ContractError('space parameter mismatch: '+block)
        for name,unit in params.items():
            rule=space['blocks'][block][name]
            choices=rule.get('choices')
            if rule.get('unit') != unit or not isinstance(choices,list) or not choices:
                raise ContractError(f'invalid space axis: {block}.{name}')
            for v in choices: number(v,block+'.'+name, name not in {'q0_C','V0_V'})
            if len(set(choices)) != len(choices): raise ContractError('duplicate axis value')
            count *= len(choices)
    if count > 100000: raise ContractError('space too large for bounded finite baseline')
    if space.get('couplings') != [{'type':'equal','left':'CP.I_up_A','right':'CP.I_down_A'}]:
        raise ContractError('version1 requires declared equal directional CP target slopes')
    return p

def candidate_from_values(p, values, rationale=''):
    blocks = {b:{k:{'value':values[b+'.'+k], 'unit':u} for k,u in params.items()} for b,params in PARAMETERS.items()}
    return {'schema_version':'joint-block-spec-1.0','blocks':blocks,
            'common_conditions':deepcopy(p['operating_context']), 'parameter_role':'DECLARED_TARGET',
            'rationale':rationale}

def values_of(candidate):
    return {b+'.'+k:item['value'] for b,params in candidate['blocks'].items() for k,item in params.items()}

def check_candidate(p, candidate):
    errors=[]
    try:
        if candidate.get('schema_version') != 'joint-block-spec-1.0' or candidate.get('parameter_role') != 'DECLARED_TARGET':
            raise ContractError('candidate schema/role mismatch')
        if candidate.get('common_conditions') != p['operating_context']:
            raise ContractError('frozen common conditions changed')
        if set(candidate.get('blocks',{})) != set(BLOCKS): raise ContractError('all five blocks required')
        for b,params in PARAMETERS.items():
            if set(candidate['blocks'][b]) != set(params): raise ContractError('parameter completeness: '+b)
            for name,unit in params.items():
                item=candidate['blocks'][b][name]; value=item.get('value')
                if item.get('unit') != unit: raise ContractError('unit mismatch: '+b+'.'+name)
                number(value,b+'.'+name)
                if value not in p['block_space']['blocks'][b][name]['choices']:
                    raise ContractError('outside BlockSpace: '+b+'.'+name)
        v=values_of(candidate); c=p['operating_context']
        if v['CP.I_up_A'] != v['CP.I_down_A']: raise ContractError('coupled CP slopes mismatch')
        if v['Divider.N'] != c['N']: raise ContractError('divider context mismatch')
        if not 0 < v['PFD.reset_s'] < 1/c['fref_Hz']: raise ContractError('invalid PFD reset')
        veq=v['VCO.V0_V']+(c['fout_target_Hz']-v['VCO.f0_Hz'])/v['VCO.Kvco_Hz_per_V']
        lo,hi=v['VCO.voltage_min_V'],v['VCO.voltage_max_V']
        if not 0 < lo < hi < c['VDD_V']: raise ContractError('invalid voltage domain')
        if not lo <= veq <= hi: raise ContractError('equilibrium outside VCO model domain')
        if not all(lo <= p['initialization'][k] <= hi for k in ('Vctrl_V','Vc2_V')):
            raise ContractError('initial voltage outside model domain')
    except (ContractError,KeyError,TypeError,AttributeError) as e:
        errors.append(str(e))
    try:
        fingerprint=digest(candidate)
    except (ValueError,TypeError):
        fingerprint=None
        if not errors: errors.append('candidate is not finite JSON')
    return {'status':'VALID' if not errors else 'INVALID','errors':errors,'candidate_sha256':fingerprint}

def candidate_grid(p):
    axes=[(b+'.'+k,p['block_space']['blocks'][b][k]['choices']) for b,params in PARAMETERS.items() for k in params]
    for row in itertools.product(*(v for _,v in axes)):
        values=dict(zip((k for k,_ in axes),row))
        if values['CP.I_up_A'] == values['CP.I_down_A']:
            yield candidate_from_values(p,values)

class AllocationPolicy(Protocol):
    policy_id: str
    def propose(self, problem: dict, history: list[dict], remaining: dict) -> dict | None: ...

class BehavioralBackend(Protocol):
    backend_id: str
    def capabilities(self) -> dict: ...
    def run(self, problem: dict, candidate: dict, workdir) -> dict: ...

class BehavioralVerifier(Protocol):
    def judge(self, problem: dict, candidate: dict, evaluation: dict) -> dict: ...
