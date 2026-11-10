"""Optional nonideal adapter over original sweep/capture/convergence verifier."""
import json
from pathlib import Path
import time
from .experiments import write as write_new
from ..physics_mapping.model import fingerprint
from .stage6c_native import simulate
from .experiments import save_run,response_sweep
from .run_suite import comparison_after_measurement


def deterministic_measure(candidate,nonideal,out,protocol):
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    calls=[]
    def native(c,**kw):
        began=time.perf_counter();record={'settings':kw,'started_index':len(calls)+1};calls.append(record)
        try:
            r=simulate(c,nonideal,**kw);record.update(status='COMPLETED',summary=r['summary'],extension=r['extension']);return r
        except Exception as e:record.update(status='FAILED',reason=type(e).__name__+': '+str(e));raise
        finally:
            record['wall_s']=time.perf_counter()-began
            # Crash journal, append-only native calls; completed snapshot is written separately.
            with (out/'native_call_events.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(record,allow_nan=False)+'\n')
    write_new(out/'request.json',dict(candidate=candidate,nonideal=nonideal,protocol=protocol))
    cap=[]
    for name,dt in [('coarse',.4e-9),('fine',.2e-9)]:
        cap.append(save_run(out/('capture_'+name),candidate,dict(duration_s=160e-6,dt_s=dt,
            initial_control_V=.15,record_interval_s=20e-9,onset_s=160e-6),'capture',protocol_document=protocol,simulate_fn=native))
    a,b=cap;cfg=protocol['capture']
    lockdiff=abs(a['lock_time_s']-b['lock_time_s']) if a['lock_time_s']is not None and b['lock_time_s']is not None else None
    converged=(a['status']==b['status'] and abs(a['output_frequency_Hz']-b['output_frequency_Hz'])/80e6*1e6<=cfg['step_frequency_difference_limit_ppm']
        and abs(a['steady_control_V']-b['steady_control_V'])<=cfg['step_control_difference_limit_V']
        and (lockdiff is None or lockdiff<=cfg['step_lock_time_difference_limit_s']))
    capture={'coarse':a,'fine':b,'step_converged':bool(converged),'lock_time_difference_s':lockdiff,
        'status':b['status'] if converged else 'UNKNOWN','lock_time_envelope_s':
            [max(0.,b['lock_time_s']-lockdiff-1e-6),b['lock_time_s']+lockdiff+1e-6] if converged and lockdiff is not None else None}
    sweeps={}
    for name,amp,dt,cycles in [('base',.01,.4e-9,12),('halfamp',.005,.4e-9,12),('halfstep',.01,.2e-9,12),('doublewindow',.01,.4e-9,24)]:
        sweeps[name]=response_sweep(out/name,candidate,amplitude=amp,dt=dt,cycles=cycles,protocol_document=protocol,simulate_fn=native)
    comparison=comparison_after_measurement(candidate,sweeps,protocol_document=protocol)
    recovery=[];v=candidate['values'];vreq=(8*v['f_ref']['value']-v['f0']['value'])/v['Kvco']['value']
    for label,dt in [('coarse',.4e-9),('fine',.2e-9)]:
        recovery.append(save_run(out/('recovery_'+label),candidate,dict(duration_s=200e-6,dt_s=dt,
            initial_control_V=vreq,phase_amplitude_rad=.4,modulation_Hz=1e5,onset_s=50e-6,
            phase_end_s=100e-6,record_interval_s=20e-9),'capture',protocol_document=protocol,simulate_fn=native))
    recovery_ok=all(r['status']=='CAPTURED_WITHIN_WINDOW' and
        all(b['valid_tracking_block'] for b in r['blocks'] if b['start_s']>=180e-6) for r in recovery)
    recovery_dt=abs(recovery[0]['output_frequency_Hz']-recovery[1]['output_frequency_Hz'])/80e6*1e6
    recovery_ok=recovery_ok and recovery_dt<=cfg['step_frequency_difference_limit_ppm']
    result={'candidate_sha256':fingerprint(candidate),'nonideal_profile_id':nonideal['profile_id'],
        'capture':capture,'BW':comparison,'nominal_M1':comparison['M1_prediction'],
        'nonlinear_recovery_status':'PASS_CONDITIONAL_FINITE_WINDOW' if recovery_ok else 'UNKNOWN',
        'recovery':recovery,'recovery_step_frequency_difference_ppm':recovery_dt,'strict_periodic_PM_status':'UNKNOWN',
        'cost':{'native_calls':len(calls),'native_completed':sum(c['status']=='COMPLETED' for c in calls),
                'native_failed':sum(c['status']=='FAILED' for c in calls),
                'native_elapsed_s':sum(c.get('summary',{}).get('elapsed_s',0.) for c in calls),
                'integration_points':sum(c.get('summary',{}).get('integration_points',0) for c in calls)},
        'FULL_SYSTEMSPEC_CERTIFIED':False}
    write_new(out/'result.json',result);return result


def validate_extension(ext):
    from ..block_space.extensions import validate_noise
    from .noise import validate_protocol
    required={'extension_id','noise_profile','nonideal_profile','noise_protocol','jitter_limit_s','source_profile_hashes'}
    if not isinstance(ext,dict) or set(ext)!=required or ext['extension_id']!='stage6c-joint-behavioral-1.0':
        raise ValueError('UNSUPPORTED: behavioral extension')
    validate_noise(ext['noise_profile']);validate_protocol(ext['noise_protocol'])
    if type(ext['jitter_limit_s'])not in (int,float) or not 0<ext['jitter_limit_s']<1e-6:
        raise ValueError('OUT_OF_DOMAIN: positive research jitter limit')
    expected={k:fingerprint(ext[k]) for k in ('noise_profile','nonideal_profile','noise_protocol')}
    if ext['source_profile_hashes']!=expected:raise ValueError('extension profile binding mismatch')
    return ext


def verify_extended(item,out):
    """Used only by original pipeline. Original formal metric schema preserved."""
    from copy import deepcopy
    from .verify import validate_proposal,assemble_result
    from .experiments import protocol as original_protocol,read
    from .noise import verify_noise
    from .stage6c_native import MODEL_ID
    from ..block_space.extensions import validate_nonideal
    ext=validate_extension(item['behavioral_extension']);model,candidate,domain=validate_proposal(item)
    derived=validate_nonideal(ext['nonideal_profile'],candidate)
    out=Path(out);out.mkdir(parents=True,exist_ok=False);write_new(out/'proposal.json',item)
    proto=original_protocol();write_new(out/'protocol.json',proto)
    start=time.perf_counter();failure=None;det=None;noise=None
    try:
        det=deterministic_measure(candidate,ext['nonideal_profile'],out/'deterministic',proto)
        cap=det['capture'];a,b=cap['coarse'],cap['fine']
        old_capture={'fine':b,'coarse':a,'numerical_converged':cap['step_converged'],
            'reliable_capture_status':cap['status'],'initial_control_V':.15,'duration_s':160e-6,
            'step_comparison':{'frequency_difference_ppm':abs(a['output_frequency_Hz']-b['output_frequency_Hz'])/80,
                'control_difference_V':abs(a['steady_control_V']-b['steady_control_V']),
                'lock_time_difference_s':cap['lock_time_difference_s']}}
        result=assemble_result(item,proto,domain,old_capture,{},det['BW'])
        if cap['step_converged'] and cap['status']=='CAPTURED_WITHIN_WINDOW':
            noise=verify_noise(candidate,ext['nonideal_profile'],ext['noise_profile'],ext['noise_protocol'],proto,
                out/'noise',limit_s=ext['jitter_limit_s'])
        result['model_version']=MODEL_ID
        result['extension']={'extension_id':ext['extension_id'],'profile_hashes':ext['source_profile_hashes'],
            'noise_profile_id':ext['noise_profile']['profile_id'],'nonideal_profile_id':ext['nonideal_profile']['profile_id'],
            'noise_protocol_id':ext['noise_protocol']['protocol_id'],'derived':derived,
            'noise_result':noise,'deterministic_result':'deterministic/result.json',
            'nonlinear_recovery_status':det['nonlinear_recovery_status'],
            'M1_ignores_nonideality':derived['ignored_by_ideal_M1'],'FULL_SYSTEMSPEC_CERTIFIED':False}
        from .stage6c_identity import check_build
        result['extension']['native_build_identity']=check_build()
        result['metrics']['integrated_jitter_s']={'value':noise.get('integrated_jitter_s') if noise else None,'unit':'s',
            'status':noise['status'] if noise else 'UNKNOWN','statistical_interval_s':noise.get('jitter_interval_s') if noise else None,
            'constraint_status':noise['jitter_constraint_status'] if noise else 'UNKNOWN'}
        result['metrics']['nonlinear_recovery_status']={'value':det['nonlinear_recovery_status'],'unit':'1','status':'CONDITIONAL_FINITE_WINDOW'}
        m=det['nominal_M1'];coeff=m['factors']['F_LOOP']['characteristic_descending']
        import numpy as np
        poles=np.roots(coeff)
        result['metrics']['stability_diagnostic']={'value':bool(m['factors']['F_LOOP']['routh_stable']),
            'source':'M1_CONTINUOUS_NOMINAL_ONLY','unit':'1','poles_rad_per_s':[[float(p.real),float(p.imag)] for p in poles],
            'strict_periodic_PM_status':'UNKNOWN'}
    except Exception as error:
        failure={'type':type(error).__name__,'reason':str(error)}
        result={'schema_version':'behavioral-verification-result-1.0','overall_status':'UNKNOWN',
            'verified_joint_block_spec':False,'validation_level':'NOT_VALIDATED','failure_reasons':[str(failure)],'metrics':{}}
    # Make original runner cost collector see every real native summary, without a
    # second simulation or double-counting. Original deterministic summaries exist.
    for path in out.rglob('native_summary.json'):
        doc=read(path);write_new(path.parent/'summary.json',{'summary':doc['summary'],'actual_settings':doc['settings']})
    summaries=[read(p)['summary'] for p in out.rglob('summary.json')]
    events=[json.loads(line) for p in out.rglob('*events.jsonl') for line in p.read_text(encoding='utf-8').splitlines()]
    failures=[e for e in events if e.get('status')=='FAILED']
    result['execution_cost']={'completed_native_runs':len(summaries),
        'integration_points':sum(s['integration_points'] for s in summaries),'native_elapsed_s':sum(s['elapsed_s'] for s in summaries),
        'failed_attempts':len(failures),'failure_elapsed_s':sum(e.get('wall_s',0.) for e in failures),'total_wall_s':time.perf_counter()-start}
    result['extension_failure']=failure
    write_new(out/'result.json',result);return result

