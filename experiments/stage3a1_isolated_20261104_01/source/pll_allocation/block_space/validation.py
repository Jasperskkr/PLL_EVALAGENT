"""Stage 1.5 forward-only domain characterization with independently labelled evidence."""
from __future__ import annotations
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import csv
import hashlib
import json
import math
from pathlib import Path
import platform
import sys
from .calibration import discrepancy_record
from .contracts import FREE_IDS, forward, load_model, make_candidate
from .event_reference import PROTOCOL, compare_event, load_existing_simulator
from .sampling import abnormal_cases, representative_cases
from pll_allocation.physics_mapping.model import fingerprint
from pll_allocation.physics_mapping.validation import compare, polynomial_reference


def write_new(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def summarize_sensitivity(rows, model):
    output = []
    for name in FREE_IDS:
        subset = [r for r in rows if r['case']['label'].startswith('local_'+name+'_')]
        kind = 'local_centered_log_derivative'
        if name in ('C1','C2'):
            subset = [r for r in rows if r['case']['label'].startswith('choice_'+name+'_') and r['case']['category']=='discrete_sensitivity']
            kind = 'discrete_choice_log_secant_not_local_derivative'
        subset = sorted([r for r in subset if r['forward']['prediction']],key=lambda r:r['case']['parameters']['values'][name]['value'])
        if len(subset) < 2:
            continue
        lower, upper = subset[0], subset[-1]
        delta = math.log(upper['case']['parameters']['values'][name]['value']/lower['case']['parameters']['values'][name]['value'])
        a, b = lower['forward']['prediction']['metrics'], upper['forward']['prediction']['metrics']
        output.append({'parameter':name,'method':kind,'case_ids':[lower['case']['case_id'],upper['case']['case_id']],
            'BW_log_elasticity':math.log(b['BW_Hz']/a['BW_Hz'])/delta,
            'UGF_log_elasticity':math.log(b['UGF_Hz']/a['UGF_Hz'])/delta,
            'PM_deg_per_one_percent':.01*(b['PM_deg']-a['PM_deg'])/delta,
            'Vreq_log_elasticity':math.log(b['Vctrl_required_V']/a['Vctrl_required_V'])/delta})
    return output


def write_csv(out, rows):
    param_names = list(rows[0]['case']['parameters']['values'])
    columns = ['case_id','label','category','in_declared_domain','model_validity','M1_spec_verdict','failure_reason']
    columns += [f'{k} [{rows[0]["case"]["parameters"]["values"][k]["unit"]}]' for k in param_names]
    columns += ['Vreq_V','UGF_Hz','BW_Hz','PM_deg','numerical_reference_source','UGF_relative_error','BW_relative_error',
                'PM_absolute_error_deg','Vreq_absolute_error_V','numerical_status','behavioral_status',
                'event_tail_frequency_Hz','event_vfinal_V','event_tracking_observed','event_step_converged',
                'event_frequency_error_ppm','event_control_endpoint_error_V','behavioral_reference_source','M2_system_verdict']
    with (out/'FORWARD_MODEL_VALIDATION.csv').open('x',newline='',encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream,fieldnames=columns)
        writer.writeheader()
        for row in rows:
            case, f = row['case'], row['forward']
            pred = (f['prediction'] or {}).get('metrics',{})
            event = row.get('event',{})
            fine = event.get('runs',[{}])[-1]
            comparison = row.get('numerical_comparisons',{})
            errors = event.get('errors',{})
            data = {'case_id':case['case_id'],'label':case['label'],'category':case['category'],
                'in_declared_domain':f['domain']['declared_domain'],'model_validity':f['domain']['model_validity'],
                'M1_spec_verdict':f['judgment']['verdict'],'failure_reason':'; '.join(f['domain']['issues']) or (
                    '; '.join(c['metric']+' constraint violated' for c in f['judgment']['checks'] if c['status']=='VIOLATED')),
                **{f'{k} [{x["unit"]}]':x['value'] for k,x in case['parameters']['values'].items()},
                'Vreq_V':pred.get('Vctrl_required_V'),'UGF_Hz':pred.get('UGF_Hz'),'BW_Hz':pred.get('BW_Hz'),'PM_deg':pred.get('PM_deg'),
                'numerical_reference_source':row.get('numerical_reference_source','NOT_APPLICABLE_OUTSIDE_M1_DOMAIN'),
                'UGF_relative_error':comparison.get('UGF_Hz',{}).get('error'),
                'BW_relative_error':comparison.get('BW_Hz',{}).get('error'),
                'PM_absolute_error_deg':comparison.get('PM_deg',{}).get('error'),
                'Vreq_absolute_error_V':comparison.get('Vctrl_required_V',{}).get('error'),
                'numerical_status':row.get('numerical_status','NOT_EVALUATED'),
                'behavioral_status':event.get('status','NOT_SELECTED'),
                'event_tail_frequency_Hz':fine.get('fout_avg'),'event_vfinal_V':fine.get('vfinal'),
                'event_tracking_observed':event.get('tail_tracking_observed'),
                'event_step_converged':event.get('step_refinement_converged'),
                'event_frequency_error_ppm':errors.get('frequency_prediction_error_ppm'),
                'event_control_endpoint_error_V':errors.get('Vctrl_endpoint_prediction_error_V'),
                'behavioral_reference_source':'audited byte-identical Python edge-interpolated simulate; two resolutions' if event.get('runs') else '',
                'M2_system_verdict':event.get('M2_system_verdict','NOT_EVALUATED')}
            writer.writerow(data)


def run_validation(model_path, out, *, event_tb=True):
    model_path, out = Path(model_path).resolve(), Path(out).resolve()
    model = load_model(model_path)
    root = Path(__file__).resolve().parents[2]
    cases = representative_cases(model)+abnormal_cases(model)
    out.mkdir(parents=True,exist_ok=False)
    (out/'cases').mkdir()
    write_new(out/'model_snapshot.json',model)
    write_new(out/'candidate_snapshots.json',cases)
    write_new(out/'validation_plan.json',{'sampling':'nominal; fixed OAT +/-2%; near edges; 16 corners; capacitor pairs; 48 Halton; fixed 17-point Icp/Rz slices; tuning rail +/-10kHz; anomalies',
        'declared_case_count':sum(c['category']!='out_of_declared_domain_anomaly' for c in cases),
        'event_selection':'predeclared event_selected flag before any M1 or TB evaluation',
        'event_protocol':PROTOCOL,'system_spec_unchanged':True,
        'numerical_acceptance':{'BW_UGF_relative_limit':.005,'PM_absolute_deg_limit':.2,'Vreq_absolute_V_limit':1e-6},
        'no_full_domain_accuracy_claim':True})
    simulator, provenance = None, None
    if event_tb:
        simulator, provenance = load_existing_simulator(root/'data/behavioral_space_v1/reference')
        write_new(out/'event_reference_provenance.json',provenance)
    rows, discrepancies = [], []
    for case in cases:
        folder = out/'cases'/case['case_id']
        folder.mkdir()
        write_new(folder/'parameters.json',case['parameters'])
        f = forward(model,case['parameters'])
        row = {'case':case,'forward':f}
        if f['prediction'] and f['prediction']['status']=='OK':
            oracle = polynomial_reference(case['parameters'])
            checks = compare(f['prediction']['metrics'],oracle)
            row.update(numerical_reference=oracle,numerical_comparisons=checks,
                       numerical_reference_source='Stage1 polynomial_reference: independent omega^2 magnitude root; SAME_EQUATIONS_NOT_BEHAVIORAL_TRUTH',
                       numerical_status='CONSISTENT' if all(x['satisfied'] for x in checks.values()) else 'INCONSISTENT')
        if case['event_selected']:
            if simulator is None:
                row['event']={'status':'NOT_EXECUTED','reason':'explicit --skip-event run', 'M2_system_verdict':'NOT_EVALUATED'}
            else:
                try:
                    row['event']=compare_event(case['parameters'],simulator)
                except Exception as error:
                    row['event']={'status':'EXCEPTION','reason':type(error).__name__+': '+str(error),
                                  'behavioral_calls':'UNKNOWN_IF_PARTIAL','M2_system_verdict':'NOT_EVALUATED'}
                event = row['event']
                if event.get('status')=='COMPLETED':
                    p = case['parameters']['values']
                    target = p['N']['value']*p['f_ref']['value']
                    # A conditional comparison never silently converts protocols or patches formulas.
                    comparable = bool(event['interior_tuning_predicted'] and event['tail_tracking_observed'] and event['step_refinement_converged'])
                    discrepancies.append(discrepancy_record(model,case['parameters'],metric='output_frequency_Hz',
                        prediction=target,reference=event['runs'][-1]['fout_avg'],unit='Hz',
                        prediction_protocol='conditional_locked_tuning_frequency',reference_protocol='edge_TB_last20pct_mean_frequency',
                        evidence=f'cases/{case["case_id"]}/result.json#event',classification='UNRESOLVED',
                        comparability='CONDITIONAL_LOCKED_COMPARISON' if comparable else 'UNESTABLISHED',
                        known_limitations=event['limitations'],
                        recommended_action='Retain raw formula; establish injection protocols for BW/PM and longer/third-step tracking checks for failed or clipped cases.'))
        write_new(folder/'result.json',row)
        rows.append(row)
        if len(rows)%20==0:
            print(f'Completed {len(rows)}/{len(cases)} predeclared cases',flush=True)
    sensitivity = summarize_sensitivity(rows,model)
    valid = [r for r in rows if r['forward']['prediction'] and r['forward']['prediction']['status']=='OK']
    events = [r for r in rows if r.get('event',{}).get('status')=='COMPLETED']
    numerical_failed = [r['case']['case_id'] for r in valid if r.get('numerical_status')!='CONSISTENT']
    reference = rows[0]
    nominal = reference['forward']['prediction']['metrics']
    # Reference stays the prechosen nominal; this is not an optimizer-selected recommendation.
    if reference['forward']['judgment']['verdict']!='M1_SPEC_PASS':
        raise ArithmeticError('frozen nominal does not satisfy SystemSpec; do not change bounds')
    write_new(out/'REFERENCE_BLOCKSPEC.json',{'schema_version':'reference-blockspec-1.0',
        'model_id':model['model_id'],**model['versions'],'model_sha256':fingerprint(model),
        'parameters':reference['case']['parameters'],'validation_status':'M1_VALIDATED',
        'M1_result':reference['forward'],'event_crosscheck':reference.get('event',{}),
        'evidence':'cases/C000/result.json','recommended':True,
        'selection_reason':'preselected Stage 1 nominal; not tuned to this scan',
        'constraint_margins':reference['forward']['judgment']['checks'],
        'M2_system_verdict':'NOT_EVALUATED','verified_joint_block_spec':False})
    write_new(out/'sensitivity.json',sensitivity)
    write_new(out/'calibration_records.json',discrepancies)
    write_csv(out,rows)
    summary = {'case_count':len(rows),'declared_cases':sum(r['case']['category']!='out_of_declared_domain_anomaly' for r in rows),
        'category_counts':dict(Counter(r['case']['category'] for r in rows)),
        'domain_counts':dict(Counter(r['forward']['domain']['model_validity'] for r in rows)),
        'M1_verdict_counts':dict(Counter(r['forward']['judgment']['verdict'] for r in rows)),
        'valid_M1_count':len(valid),'numerical_failed_ids':numerical_failed,
        'maximum_numerical_errors':{k:max((r['numerical_comparisons'][k]['error'] for r in valid),default=None)
            for k in ('UGF_Hz','BW_Hz','PM_deg','Vctrl_required_V')},
        'event_selected_count':sum(c['event_selected'] for c in cases),'event_completed_count':len(events),
        'event_conditional_agreement_ids':[r['case']['case_id'] for r in events if r['event']['conditional_frequency_control_agreement']],
        'event_nonagreement_ids':[r['case']['case_id'] for r in events if not r['event']['conditional_frequency_control_agreement']],
        'event_unconverged_ids':[r['case']['case_id'] for r in events if not r['event']['step_refinement_converged']],
        'event_clip_observed_ids':[r['case']['case_id'] for r in events if not r['event']['no_rail_samples_observed']],
        'event_errors_or_skips':[{'case_id':r['case']['case_id'],'event':r.get('event')} for r in rows
                                 if r['case']['event_selected'] and r.get('event',{}).get('status')!='COMPLETED'],
        'continuous_instability':'NONE_POSSIBLE_IN_POSITIVE_IDEAL_DECLARED_DOMAIN_BY_ROUTH_PROOF',
        'recommended_case_id':'C000','reference_metrics':nominal,
        'cost':{'M1_attempts':len(rows),'M1_evaluations':len(valid),'polynomial_reference_evaluations':len(valid),
                'Python_event_simulations':sum(r['event']['behavioral_calls'] for r in events),
                'Python_event_integration_points':sum(r['event']['integration_points'] for r in events),
                'MATLAB_runtime_calls':0,'LLM_calls':0},
        'numerical_acceptance':'PASS' if len(valid)>=50 and not numerical_failed else 'FAIL',
        'full_domain_behavioral_accuracy':'NOT_ESTABLISHED','M2_system_verdict':'NOT_EVALUATED',
        'stage2_started':False}
    write_new(out/'summary.json',summary)
    sources = [model_path]+sorted(Path(__file__).parent.glob('*.py'))+sorted((root/'pll_allocation/physics_mapping').glob('*.py'))
    write_new(out/'run_manifest.json',{'model_sha256':fingerprint(model),'created_utc':datetime.now(timezone.utc).isoformat(),
        'python':sys.version,'platform':platform.platform(),'command':sys.argv,
        'files':[{'path':str(p.resolve()),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sources],
        'experiment_sha256':model['experiment_freeze']['experiment_sha256'],'cost':summary['cost'],
        'evidence_scope':'M1_NUMERICAL_AND_SPARSE_FIXED_STEP_EVENT_SUMMARY_CROSSCHECK',
        'no_complete_M2_BW_PM_verification':True})
    return summary
