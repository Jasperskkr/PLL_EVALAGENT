"""Extracted Track B convergence comparison and paired capture; no suite/history reads."""
from pathlib import Path
from .experiments import compare_sweeps, protocol, save_run, write

def comparison_after_measurement(p,measurements,*,protocol_document=None):
    # Sole M1 use: occurs after every event response measurement has completed.
    from pll_allocation.physics_mapping.model import evaluate
    result=evaluate(p).as_dict()
    base=measurements['base']; bw=base['bandwidth']; m=result['metrics']
    differences={key:compare_sweeps(base,value) for key,value in measurements.items() if key!='base'}
    cfg=(protocol_document or protocol())['frequency_response']
    converged=bool('BW_Hz' in bw and len(differences)==3
        and all(x['bandwidth']['status']=='MEASURED_BRACKETED' and all(p['status']=='MEASURED' for p in x['points']) for x in measurements.values()) and
        all(x['BW_relative_difference'] is not None and x['BW_relative_difference']<=cfg['max_BW_refinement_relative_difference']
            and x['max_complex_transfer_relative_difference'] is not None
            and x['max_complex_transfer_relative_difference']<=cfg['max_transfer_refinement_relative_difference']
            and x['max_transfer_phase_difference_deg'] is not None
            and x['max_transfer_phase_difference_deg']<=cfg['max_transfer_refinement_phase_deg']
            and x['compared_frequencies']>=3 for x in differences.values()))
    interval=None
    if converged:
        brackets=[x['bandwidth']['bracket_Hz'] for x in measurements.values()]
        # Conservative numerical envelope: include all run brackets and between-variant BW variation.
        spread=max(x['bandwidth']['BW_Hz'] for x in measurements.values())-min(x['bandwidth']['BW_Hz'] for x in measurements.values())
        interval=[min(x[0] for x in brackets)-spread,max(x[1] for x in brackets)+spread]
    return {'M1_prediction':result,'M2_BW_measurement':bw,
        'BW_absolute_error_Hz':bw.get('BW_Hz',0)-m.get('BW_Hz',0) if 'BW_Hz' in bw and m else None,
        'BW_relative_error':bw['BW_Hz']/m['BW_Hz']-1 if 'BW_Hz' in bw and m else None,
        'convergence_checks':differences,'numerical_converged':converged,'BW_numerical_envelope_Hz':interval,
        'measurement_confidence':'CONVERGED_SAMPLED_POINTS_ONLY' if converged else 'UNKNOWN_UNRESOLVED_QUALITY_OR_CONVERGENCE',
        'PM_M2_status':'PM_M2_UNKNOWN','PM_M2_deg':None,
        'conditional_PM_prototype':base['PM']['prototype_estimate'],
        'model_error_is_not_numerical_error':True}



def capture_pair(folder,p,initial,duration,*,protocol_document=None):
    folder=Path(folder); folder.mkdir(parents=True,exist_ok=False)
    runs=[]
    for name,dt in [('coarse',.4e-9),('fine',.2e-9)]:
        settings={'duration_s':duration,'dt_s':dt,'initial_control_V':initial,
                  'record_interval_s':20e-9,'onset_s':duration}
        runs.append(save_run(folder/name,p,settings,'capture',protocol_document=protocol_document))
    a,b=runs
    comparisons={'frequency_difference_ppm':abs(b['output_frequency_Hz']-a['output_frequency_Hz'])/80e6*1e6,
                 'control_difference_V':abs(b['steady_control_V']-a['steady_control_V']),
                 'same_status':a['status']==b['status'],
                 'lock_time_difference_s':abs(a['lock_time_s']-b['lock_time_s']) if a['lock_time_s'] is not None and b['lock_time_s'] is not None else None}
    cfg=(protocol_document or protocol())['capture']
    good=bool(comparisons['same_status'] and comparisons['frequency_difference_ppm']<=cfg['step_frequency_difference_limit_ppm']
        and comparisons['control_difference_V']<=cfg['step_control_difference_limit_V']
        and (comparisons['lock_time_difference_s'] is None or comparisons['lock_time_difference_s']<=cfg['step_lock_time_difference_limit_s']))
    result={'coarse':a,'fine':b,'step_comparison':comparisons,'numerical_converged':good,
        'reliable_capture_status':b['status'] if good else 'UNKNOWN_NUMERICAL_CONVERGENCE',
        'initial_control_V':initial,'duration_s':duration}
    write(folder/'comparison.json',result)
    return result

