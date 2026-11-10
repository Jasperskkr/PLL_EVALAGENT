"""Evidence-aware research constraints. No PLL equations or M2 measurements."""
from copy import deepcopy
import math
from .core import target_experiment
from ..block_space.contracts import check_parameters
from ..physics_mapping.model import fingerprint
from ..verification.verify import interval_judgment

SCHEMA='pll-multispec-problem-1.0'


def validate_problem(problem, config, model, frozen_spec, protocol):
    required={'schema_version','problem_id','version','scope','base_bindings','research_system_spec',
              'constraints','objective','budgets','search','problem_sha256'}
    if not isinstance(problem,dict) or set(problem)!=required or problem['schema_version']!=SCHEMA:
        raise ValueError('unsupported multispec problem contract')
    if problem['scope']!='RESEARCH_ONLY_NO_FULL_CERTIFICATION' or not problem['problem_id']:
        raise ValueError('explicit research identity/scope required')
    if problem['base_bindings']!=config['bindings'] or problem['problem_sha256']!=fingerprint({k:v for k,v in problem.items() if k!='problem_sha256'}):
        raise ValueError('multispec asset/problem binding mismatch')
    spec=problem['research_system_spec'];target_experiment(model,spec)
    restored=deepcopy(spec)
    if len(restored['metrics'])!=len(frozen_spec['metrics']):raise ValueError('original metrics required')
    for a,b in zip(restored['metrics'],frozen_spec['metrics']):
        if a['metric']!=b['metric']:raise ValueError('original metric order/identity required')
        if a['metric'] not in ('BW_Hz','PM_deg'):continue
        for key in ('min','max'):
            if key in b:a[key]=b[key]
    if restored!=frozen_spec:raise ValueError('only research BW/PM bounds may change')
    rows=problem['constraints'];by={r['metric_name']:r for r in rows}
    if len(rows)!=4 or set(by)!={'BW_Hz','PM_deg','Vctrl_required_V','lock_time_s'}:
        raise ValueError('complete BW/PM/tuning/capture constraints required')
    specs={r['metric']:r for r in spec['metrics']}
    expected={
        'BW_Hz':('M2',protocol['protocol_id'],'interval',specs['BW_Hz']['min'],specs['BW_Hz']['max'],False),
        'PM_deg':('M1',specs['PM_deg']['protocol'],'lower',specs['PM_deg']['min'],None,False),
        'Vctrl_required_V':('M1','linear_vco_static_tuning_solution','interval',0,1.2,True),
        'lock_time_s':('M2',protocol['protocol_id']+':fixed_capture_0.15V_160us','upper',None,40e-6,False)}
    keys={'metric_name','comparator','lower_bound','upper_bound','measurement_source','measurement_protocol','model_validity','normalization_scale','strict'}
    for name,r in by.items():
        if set(r)!=keys:raise ValueError('complete constraint contract required')
        source,proto,op,lo,hi,strict=expected[name]
        if (r['measurement_source'],r['measurement_protocol'],r['comparator'],r['lower_bound'],r['upper_bound'],r['strict'])!=(source,proto,op,lo,hi,strict):
            raise ValueError('constraint source/protocol/bounds mismatch: '+name)
        if r['model_validity']!='ORIGINAL_IDEAL_DECLARED_DOMAIN' or type(r['normalization_scale']) not in (int,float) or not math.isfinite(r['normalization_scale']) or r['normalization_scale']<=0:
            raise ValueError('valid finite normalization required')
    if problem['objective'] not in ('capture_then_margin','margin_then_capture'):
        raise ValueError('unsupported lexicographic objective')
    b=problem['budgets']
    if set(b)!={'M1_calls','cheap_calls','M2_candidate_slots'} or any(type(v)is not int or v<1 for v in b.values()) or b['M2_candidate_slots']>6:
        raise ValueError('bounded equal study budgets required')
    search=problem['search']
    if set(search)!={'log_step','voltage_step_V','minimum_log_step','minimum_voltage_step_V','max_no_improvement','poll_order','version'}:
        raise ValueError('explicit deterministic search settings required')
    for k in ('log_step','voltage_step_V','minimum_log_step','minimum_voltage_step_V'):
        if type(search[k])not in (int,float) or not math.isfinite(search[k]) or search[k]<=0:raise ValueError('positive finite step required')
    if search['poll_order']!=['Vreq_minus','Vreq_plus','Kvco_minus','Kvco_plus','region_switch'] or search['max_no_improvement']!=2:
        raise ValueError('unsupported frozen poll order/stop rule')
    return deepcopy(problem)


def _row(rule,value,interval,status,reason):
    result=deepcopy(rule);known=interval is not None
    margins=[]
    if known:
        if rule['lower_bound'] is not None:margins.append(interval[0]-rule['lower_bound'])
        if rule['upper_bound'] is not None:margins.append(rule['upper_bound']-interval[1])
    margin=min(margins) if margins else None
    result.update(measured_or_predicted_value=value,numerical_envelope=interval,
        normalized_violation=max(0.,-margin/rule['normalization_scale']) if margin is not None else None,
        margin=margin,normalized_margin=margin/rule['normalization_scale'] if margin is not None else None,
        verification_status=status,reason=reason)
    return result


def _finite(value):
    return type(value) in (int,float) and math.isfinite(value)


def _envelope(value):
    return isinstance(value,(list,tuple)) and len(value)==2 and all(_finite(v) for v in value) and value[0]<=value[1]


def evaluate_constraints(model,problem,candidate,assessment,measured=None):
    """Unknown never passes; M1 PM cannot fill the independent M2 PM slot."""
    domain=check_parameters(model,candidate)
    pred=assessment.get('prediction');valid=(domain['declared_domain']=='IN_DECLARED_DOMAIN' and domain['model_validity']=='VALID'
        and pred and pred['status']=='OK' and pred['parameter_sha256']==fingerprint(candidate))
    if measured is not None and measured.get('parameter_sha256')!=fingerprint(candidate):
        raise ValueError('M2 candidate binding mismatch')
    metrics=measured.get('metrics',{}) if measured else {};rows=[]
    for rule in problem['constraints']:
        name=rule['metric_name'];value=None;interval=None;status='UNKNOWN';reason='independent measurement pending'
        if rule['measurement_source']=='M1':
            if valid:
                value=pred['metrics'][name];interval=[value,value]
                target={k:v for k,v in [('min',rule['lower_bound']),('max',rule['upper_bound'])] if v is not None}
                status=interval_judgment(interval,target)
                if rule['strict'] and (value<=rule['lower_bound'] or value>=rule['upper_bound']):status='FAIL'
                reason='M1_PREDICTED_ONLY; ideal continuous locked model'
            else:reason='invalid declared/model domain or incomplete M1'
        elif name=='BW_Hz':
            bw=metrics.get(name,{})
            if (valid and bw.get('status')=='MEASURED_CONVERGED' and measured.get('reliability',{}).get('BW_converged')
                and _finite(bw.get('value')) and _envelope(bw.get('numerical_envelope'))
                and bw['numerical_envelope'][0]<=bw['value']<=bw['numerical_envelope'][1]):
                value=bw['value'];interval=bw.get('numerical_envelope')
                status=interval_judgment(interval,{'min':rule['lower_bound'],'max':rule['upper_bound']})
                reason='independently converged original M2 BW envelope'
        elif name=='lock_time_s':
            cap=metrics.get('capture',{});lock=metrics.get(name,{})
            reliable=measured and measured.get('reliability',{}).get('capture_step_converged')
            if valid and reliable and cap.get('initial_control_V')==.15 and cap.get('duration_s')==160e-6:
                if (cap.get('value')=='CAPTURED_WITHIN_WINDOW' and lock.get('status')=='MEASURED_WINDOW_CONDITIONAL'
                    and _finite(lock.get('value')) and 0<=lock['value']<=160e-6
                    and _finite(lock.get('step_difference_s')) and 0<=lock['step_difference_s']<=2e-6
                    and lock.get('resolution_s')==1e-6):
                    value=lock['value'];delta=lock['step_difference_s'];resolution=lock.get('resolution_s',1e-6)
                    # Fine time +/- paired difference contains both steps; plus block resolution.
                    interval=[max(0.,value-delta-resolution),value+delta+resolution]
                    status=interval_judgment(interval,{'max':rule['upper_bound']})
                    reason='fixed initial condition/window; paired difference + block resolution; not global lockability'
                elif cap.get('value') in ('NOT_CAPTURED_WITHIN_WINDOW','LOST_LOCK_WITHIN_WINDOW'):
                    status='FAIL';reason='reliable finite-window capture failure; not absolute nonlockability'
            elif measured:reason='capture convergence/initial conditions/time measurement unresolved'
        rows.append(_row(rule,value,interval,status,reason))
    statuses=[r['verification_status'] for r in rows]
    failed=[r for r in rows if r['verification_status']=='FAIL'];unknown=[r for r in rows if r['verification_status'] in ('UNKNOWN','UNSUPPORTED')]
    verdict='FAIL' if failed or not valid else 'UNKNOWN' if unknown else 'RESEARCH_JOINT_FEASIBLE'
    known_margins=[r['normalized_margin'] for r in rows if r['normalized_margin'] is not None]
    violation=max([r['normalized_violation'] for r in rows if r['normalized_violation'] is not None]+[0.])
    if any(r['verification_status']=='FAIL' and r['normalized_violation'] is None for r in rows):violation=max(violation,1.)
    return {'schema_version':'pll-multispec-evaluation-1.0','parameter_sha256':fingerprint(candidate),'problem_sha256':problem['problem_sha256'],
        'constraints':rows,'research_joint_status':verdict,'max_normalized_violation':violation,
        'minimum_normalized_margin':min(known_margins) if known_margins else None,'unresolved_constraints':len(unknown),
        'M1_predicted_feasible':bool(valid and all(r['verification_status']=='PASS' for r in rows if r['measurement_source']=='M1') and
            assessment['judgment']['verdict']=='M1_SPEC_PASS'),
        'FULL_SYSTEMSPEC_CERTIFIED':False,'original_M2_status':measured.get('overall_status') if measured else 'NOT_EVALUATED',
        'strict_periodic_PM_status':'UNKNOWN','strict_frequency_precision_status':'UNKNOWN'}


def objective_key(evaluation,objective):
    rows={r['metric_name']:r for r in evaluation['constraints']}
    capture=rows['lock_time_s']['numerical_envelope']
    upper=capture[1] if capture else 1e6
    margin=evaluation['minimum_normalized_margin']
    margin=margin if margin is not None else -1e6
    secondary=(upper,-margin) if objective=='capture_then_margin' else (-margin,upper)
    # Incomplete evidence is never preferred to a fully known feasible candidate.
    return (0 if evaluation['research_joint_status']=='RESEARCH_JOINT_FEASIBLE' else 1,
            evaluation['unresolved_constraints'],evaluation['max_normalized_violation'],*secondary)
