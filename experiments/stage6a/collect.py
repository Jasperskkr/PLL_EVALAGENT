"""Immutable measurement collection. No simulation, new model or allocation."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'experiments/stage6a'))
from study import read,write_new,csv_new,joint_judgment,load_inputs,values,fingerprint
from pll_allocation.pipeline_contracts import check_result


def collect(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    plan=read(ROOT/'experiments/stage6a/frozen_01/experiment_plan.json')
    protocol=load_inputs()[3];names=list(plan['candidate_order']);rows=[];details=[];started=time.perf_counter()
    repair=ROOT/'experiments/stage6a/repair_01/repair_decision.json'
    if repair.is_file() and read(repair).get('executed_candidate_name'):
        names.append(read(repair)['executed_candidate_name'])
    for name in names:
        base=ROOT/'experiments/stage6a/m2_01/runs'/name
        if not base.exists():base=ROOT/'experiments/stage6a/repair_01/runs'/name
        item=read(base/'attempt_001/AllocationProposal.json');measured=read(base/'attempt_001/BehavioralVerificationResult.json')
        result=read(base/'result.json');check_result(measured,item,protocol)
        c=item['joint_block_spec'];p=values(c);cap=read(base/'raw/attempt_001/capture/comparison.json')
        rd=base.parents[1]/'receipts';rp=rd/(name+'_receipt.json');tp=rd/(name+'_timing.json')
        receipt=read(rp) if rp.is_file() else {};timing=read(tp) if tp.is_file() else {}
        exp='E1' if name.startswith('E1') else 'E2' if name.startswith('E2') else 'E0'
        judgment=joint_judgment(c,plan['specs'][exp],measured,cap,plan['E2_deadline_s'] if exp=='E2' else None)
        m=judgment['M1']['prediction']['metrics'];bw=measured['metrics']['BW_Hz'];env=bw.get('numerical_envelope')
        target=next(s for s in plan['specs'][exp]['metrics'] if s['metric']=='BW_Hz')
        components=receipt.get('native_components',{})
        detail={'candidate':name,'experiment':exp,'research_SystemSpec':plan['specs'][exp],
            'additional_constraints':{'interior_tuning_V':[0,1.2],'strict_endpoints':True,'capture_deadline_s':plan['E2_deadline_s'] if exp=='E2' else None},
            'original_SystemSpec':item['system_spec'],'JointBlockSpec':c,'parameter_sha256':fingerprint(c),
            'judgment':judgment,'M2_metrics':measured['metrics'],'original_M2_constraints':measured['constraints'],
            'original_M2_status':measured['overall_status'],'capture_pair':cap,
            'margins':{'BW_lower_measured_Hz':env[0]-target['min'] if env else None,'BW_upper_measured_Hz':target['max']-env[1] if env else None,
                'PM_M1_deg':m['PM_deg']-next(s['min'] for s in plan['specs'][exp]['metrics'] if s['metric']=='PM_deg'),
                'tuning_rail_V':min(m['Vctrl_required_V'],1.2-m['Vctrl_required_V'])},
            'cost':{'pipeline':result['cost'],'process_wall_s':receipt.get('process_wall_s'),'native_components':components,'timed_components':timing.get('events',[])},
            'evidence_directory':str(base.relative_to(ROOT)),
            'source_sha256':{f:hashlib.sha256((base/'attempt_001'/f).read_bytes()).hexdigest() for f in ['AllocationProposal.json','BehavioralVerificationResult.json','M1_prediction.json']}}
        write_new(out/(name+'.json'),detail);details.append(detail)
        rows.append({'candidate':name,'experiment':exp,**{k:p[k] for k in ('Icp','Rz','C1','C2','f0','Kvco')},
            'M1_BW_Hz':m['BW_Hz'],'M1_PM_deg':m['PM_deg'],'M1_UGF_Hz':m['UGF_Hz'],'M1_Vreq_V':m['Vctrl_required_V'],
            'M1_PREDICTED_FEASIBLE':judgment['M1_PREDICTED_FEASIBLE'],'M2_BW_Hz':bw['value'],
            'M2_BW_lower_Hz':env[0] if env else None,'M2_BW_upper_Hz':env[1] if env else None,'BW_status':judgment['BW_status'],
            'BW_error_pct':100*(bw['value']/m['BW_Hz']-1) if bw['value'] else None,
            'capture_status':cap['reliable_capture_status'],
            'lock_coarse_us':cap['coarse']['lock_time_s']*1e6 if cap['coarse']['lock_time_s'] is not None else None,
            'lock_fine_us':cap['fine']['lock_time_s']*1e6 if cap['fine']['lock_time_s'] is not None else None,
            'capture_deadline_status':judgment['capture_deadline']['status'] if judgment['capture_deadline'] else 'NOT_REQUIRED',
            'research_joint_status':judgment['research_joint_status'],'FULL_SYSTEMSPEC_CERTIFIED':False,
            'native_runs':result['cost']['native_completed_runs'],'native_s':result['cost']['native_elapsed_s'],
            'pipeline_wall_s':result['cost']['total_elapsed_s'],'process_wall_s':receipt.get('process_wall_s'),
            'capture_native_s':components.get('capture',{}).get('elapsed_s'),'BW_sweeps_native_s':components.get('BW_response',{}).get('elapsed_s'),
            'evidence_directory':str(base.relative_to(ROOT))})
    center=details[0];measured=read(ROOT/center['evidence_directory']/'attempt_001/BehavioralVerificationResult.json')
    j=joint_judgment(center['JointBlockSpec'],plan['specs']['E2'],measured,center['capture_pair'],plan['E2_deadline_s'])
    write_new(out/'E2_centered_comparator_reused.json',{'judgment':j,'source_candidate':center['candidate'],'new_M2_calls':0,'new_native_runs':0,'scope':'reuse E0 measurement, not a fresh sample'})
    h=ROOT/'experiments/stage5/repair_01/runs/S3__random__11/attempt_001';hp=read(h/'AllocationProposal.json');hm=read(h/'BehavioralVerificationResult.json')
    hj=joint_judgment(hp['joint_block_spec'],hp['system_spec'],hm)
    assert hj['BW_status']=='PASS' and hj['research_joint_status']=='FAIL'
    write_new(out/'Stage5_S3_random11_regression.json',{'origin':'HISTORICAL_REJUDGMENT_NO_NEW_TB','new_M2_calls':0,'judgment':hj,'evidence_directory':str(h.relative_to(ROOT)),'M2_BW_Hz':hm['metrics']['BW_Hz']['value']})
    csv_new(out/'candidate_results.csv',rows)
    errors=[r['BW_error_pct'] for r in rows if r['BW_error_pct'] is not None]
    summary={'complete_M2_calls':len(rows),'native_runs':sum(r['native_runs'] for r in rows),'native_elapsed_s':sum(r['native_s'] for r in rows),
        'pipeline_wall_s':sum(r['pipeline_wall_s'] for r in rows),'process_wall_s':sum(r['process_wall_s'] or 0 for r in rows),
        'M1_predicted_feasible':sum(r['M1_PREDICTED_FEASIBLE'] for r in rows),'M2_BW_pass':sum(r['BW_status']=='PASS' for r in rows),
        'M2_BW_fail':sum(r['BW_status']=='FAIL' for r in rows),'M2_BW_unknown':sum(r['BW_status']=='UNKNOWN' for r in rows),
        'research_joint_feasible':sum(r['research_joint_status']=='RESEARCH_JOINT_FEASIBLE' for r in rows),'full_SystemSpec_certified':0,
        'strict_periodic_PM':'UNKNOWN','strict_1microHz_frequency':'UNKNOWN','LLM_calls':0,'BW_error_pct_range':[min(errors),max(errors)],
        'source_plan_sha256':plan['plan_sha256'],'collection_formal_M1_calls':len(rows)+2,'collection_wall_s':time.perf_counter()-started,
        'extra_repeat_capture':'capture_repeat_01 separately; not a new candidate/full-M2 sample','tests_and_builds':'separate receipts; test-native calls not comprehensively metered','monetary_cost':None}
    write_new(out/'summary.json',summary);return summary


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path);a=p.parse_args()
    print(json.dumps(collect(a.out),indent=2))
