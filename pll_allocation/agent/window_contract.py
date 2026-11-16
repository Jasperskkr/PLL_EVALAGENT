"""Deterministic units/coordinates adapter at the untrusted planner boundary.

No physical value is clipped, expanded, or replaced. Old metadata is accepted
only as input: the controller owns the optimization coordinate convention.
"""
from copy import deepcopy
from decimal import Decimal
from ..exploration.contracts import number, require
from ..physics_mapping.model import PARAMETERS

LEGACY = 'pll-computational-window-decision-1.0'
COMPACT = 'pll-computational-window-decision-2.0'
SCALES = {k: 'linear' if k == 'f0' else 'log' for k in ('Icp','Rz','C1','C2','f0','Kvco')}


class ContractError(ValueError):
    def __init__(self, message, *, repairable=False):
        self.repairable = repairable
        super().__init__(message)


def si_factor(axis, unit):
    """Explicit dimension-preserving aliases; prefix case is significant."""
    canonical = PARAMETERS[axis][0]
    aliases = {'Ohm': 'Ohm', 'ohm': 'Ohm', 'Ω': 'Ohm', 'Ω': 'Ohm',
               'kOhm':'kOhm','kohm':'kOhm','kΩ':'kOhm','MOhm':'MOhm','Mohm':'MOhm','MΩ':'MOhm'}
    unit = unit.replace('µ','u').replace('μ','u') if isinstance(unit,str) else unit
    unit = aliases.get(unit,unit)
    maps = {'A':{'A':'1','mA':'1e-3','uA':'1e-6','nA':'1e-9','pA':'1e-12'},
        'F':{'F':'1','mF':'1e-3','uF':'1e-6','nF':'1e-9','pF':'1e-12','fF':'1e-15'},
        'Ohm':{'Ohm':'1','kOhm':'1e3','MOhm':'1e6'},
        'Hz':{'Hz':'1','kHz':'1e3','MHz':'1e6','GHz':'1e9'},
        'Hz/V':{'Hz/V':'1','kHz/V':'1e3','MHz/V':'1e6','GHz/V':'1e9'}}
    if unit not in maps[canonical]:
        raise ContractError(axis+': unsupported/dimensionally incorrect unit')
    return Decimal(maps[canonical][unit])


def normalize_window(raw, state):
    """Return canonical legacy object plus a lossless, reviewable adaptation log."""
    if not isinstance(raw,dict):raise ContractError('JSON decision object required',repairable=True)
    compact = raw.get('schema_version') == COMPACT
    fields={'schema_version','action','reason','evidence_ids','parameters'} | (set() if compact else {'state_sha256'})
    if set(raw)!=fields or raw.get('schema_version') not in (LEGACY,COMPACT):
        raise ContractError('window decision structure/schema mismatch',repairable=True)
    out=deepcopy(raw);changes=[]
    out.update(schema_version=LEGACY)
    if compact:
        out['state_sha256']=state['state_sha256']
        changes.append({'path':'state_sha256','before':None,'after':state['state_sha256'],'basis':'controller current request binding'})
    params=out['parameters']
    if params is not None:
        if not isinstance(params,dict) or set(params)!=set(SCALES):
            raise ContractError('six complete axes required',repairable=True)
        for k,a in params.items():
            if not isinstance(a,dict) or not {'min','max'}<=set(a) or set(a)-{'min','max','unit','scale'}:
                raise ContractError(k+': min/max and optional unit required',repairable=True)
            before=deepcopy(a);unit=a.get('unit',PARAMETERS[k][0]);factor=si_factor(k,unit)
            for bound in ('min','max'):
                value=number(a[bound],k+':'+bound)
                # Decimal avoids introducing gratuitous conversion error at hard endpoints.
                a[bound]=value if factor==1 else float(Decimal(str(value))*factor)
            a.update(unit=PARAMETERS[k][0],scale=SCALES[k])
            if before!=a:changes.append({'path':'parameters.'+k,'before':before,'after':deepcopy(a),
                'basis':'equivalent SI units; controller fixed coordinates','SI_multiplier':str(factor)})
    return out,{'raw':deepcopy(raw),'normalized':deepcopy(out),'changes':changes,
        'numerical_clipping':False,'controller_coordinate_scales':deepcopy(SCALES)}


def check_physical_window(problem):
    from ..exploration.contracts import resolve_problem, screen_problem
    if problem is not None:
        require(not screen_problem(resolve_problem(problem))['certificates'],
                'window violates physical necessary conditions')
    return problem


def contract_decision(policy, state, directory, *, normalize, validate, existing_directory=False, raw_alias=None):
    """Isolated bounded repair adapter; no tool execution or physical fallback."""
    from pathlib import Path
    from ..allocation.core import write_new
    from .region_policy import InvalidResponse
    directory=Path(directory)
    if not existing_directory:directory.mkdir(parents=True,exist_ok=False)
    current=deepcopy(state); previous=None
    for attempt in range(2):
        raw=None
        write_new(directory/f'PlannerState_{attempt}.json',current)
        try:
            raw=policy.decide(deepcopy(current),directory/('llm_call' if attempt==0 else 'llm_correction'))
            write_new(directory/f'raw_decision_{attempt}.json',raw)
            if raw_alias and attempt==0:write_new(directory/raw_alias,raw)
            normalized,trace=normalize(raw,current)
            write_new(directory/f'normalization_{attempt}.json',trace)
            value=validate(normalized,current)
            write_new(directory/f'validation_{attempt}.json',{'accepted':True,'repair_attempt':attempt,
                'actual_execution_contract':value})
            write_new(directory/'decision_diff.json',{'before':previous,'after':raw,
                'correction_calls':attempt,'normalization_changes':trace.get('changes',[])})
            return value
        except (ValueError,KeyError,TypeError) as error:
            repairable=(isinstance(error,InvalidResponse) and getattr(error,'repairable_structure',True)) or (isinstance(error,ContractError) and error.repairable)
            feedback={'accepted':False,'error_type':type(error).__name__,'message':str(error),
                'repairable_structure':repairable,'repair_attempt':attempt,'tools_executed':False}
            write_new(directory/f'validation_{attempt}.json',feedback)
            if not repairable or attempt==1:raise
            previous=deepcopy(raw)
            current=deepcopy(state)|{'validation_feedback':feedback,'rejected_decision':raw}
            if 'state_sha256' in current:
                from ..physics_mapping.model import fingerprint
                current.pop('state_sha256')
                current['state_sha256']=fingerprint(current)
    raise AssertionError('bounded correction exhausted')
