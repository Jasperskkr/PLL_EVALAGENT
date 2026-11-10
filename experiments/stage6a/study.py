"""Research analysis/decisions using existing implementations; never an alternate pipeline."""
from copy import deepcopy
import csv
import hashlib
import itertools
import json
import math
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from pll_allocation.allocation.core import Meter, assess_m1, read, values, write_new
from pll_allocation.allocation.allocate import analytical, optimize, sensitivity
from pll_allocation.allocation.physics import phase_interval, pm_ceiling, raw_prediction
from pll_allocation.block_space.contracts import check_parameters, make_candidate
from pll_allocation.physics_mapping.model import evaluate, fingerprint
from pll_allocation.physics_mapping.registry import load_registry
from pll_allocation.pipeline_contracts import load_inputs
from pll_allocation.verification.verify import interval_judgment
from tools.build_block_relation_atlas import bandwidth_domain, witness


def csv_new(path, rows):
    with Path(path).open('x', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


def scenario(spec, bw, pm):
    result = deepcopy(spec)
    for row in result['metrics']:
        if row['metric'] == 'BW_Hz': row.update(min=bw[0], max=bw[1])
        if row['metric'] == 'PM_deg': row.update(min=pm)
    return result


def capture_judgment(pair, deadline_s):
    if not pair.get('numerical_converged'):
        return {'status':'UNKNOWN','reason':'paired convergence unresolved','interval_s':None}
    if pair.get('reliable_capture_status') != 'CAPTURED_WITHIN_WINDOW':
        return {'status':'FAIL','reason':'not captured under fixed conditions/window','interval_s':None}
    times = [pair[k].get('lock_time_s') for k in ('coarse','fine')]
    if any(type(v) not in (int,float) or not math.isfinite(v) or v < 0 for v in times):
        return {'status':'UNKNOWN','reason':'missing reliable lock time','interval_s':None}
    interval = [max(0.,min(times)-1e-6),max(times)+1e-6]
    status = 'PASS' if interval[1] <= deadline_s else 'FAIL' if interval[0] > deadline_s else 'UNKNOWN'
    return {'status':status,'reason':'paired lock-time hull plus 1 us block resolution',
        'interval_s':interval,'deadline_s':deadline_s,'margin_s':deadline_s-interval[1],
        'scope':'FIXED_INITIAL_CONDITIONS_AND_WINDOW_ONLY'}


def joint_judgment(candidate, spec, measured, capture_pair=None, deadline_s=None):
    _,model,_,_ = load_inputs()
    d = check_parameters(model,candidate); a = assess_m1(model,spec,candidate,Meter())
    valid = d['declared_domain']=='IN_DECLARED_DOMAIN' and d['model_validity']=='VALID'
    m1ok = valid and a['judgment']['verdict']=='M1_SPEC_PASS'
    if measured.get('parameter_sha256') != fingerprint(candidate):
        raise ValueError('measured candidate binding mismatch')
    bw = measured.get('metrics',{}).get('BW_Hz',{})
    target = next(s for s in spec['metrics'] if s['metric']=='BW_Hz')
    bs = interval_judgment(bw.get('numerical_envelope'),target) if bw.get('status')=='MEASURED_CONVERGED' else 'UNKNOWN'
    cap = capture_judgment(capture_pair,deadline_s) if deadline_s is not None and capture_pair is not None else None
    required = {'M1_joint':'PASS' if m1ok else 'FAIL' if valid and a['prediction'] else 'UNKNOWN','M2_BW':bs}
    if deadline_s is not None: required['M2_conditional_capture_deadline']=cap['status'] if cap else 'UNKNOWN'
    status = 'FAIL' if 'FAIL' in required.values() else 'UNKNOWN' if 'UNKNOWN' in required.values() else 'RESEARCH_JOINT_FEASIBLE'
    return {'M1_PREDICTED_FEASIBLE':m1ok,'M2_MEASURED_PASS':bs=='PASS','BW_status':bs,
        'M2_measured_pass_subset':['BW_Hz'] if bs=='PASS' else [],'capture_deadline':cap,
        'research_joint_status':status,'required_research_checks':required,'M1':a,
        'FULL_SYSTEMSPEC_CERTIFIED':False,'full_SystemSpec_status':'UNKNOWN',
        'scope':'MIXED_M1_PM_TUNING_AND_MEASURED_M2_SUBSET; NOT_PERIODIC_PM_CERTIFICATION'}


def analyze(out):
    out=Path(out); out.mkdir(parents=True,exist_ok=False)
    cfg,model,frozen,protocol=load_inputs()
    registry=load_registry(ROOT/'docs/stage4_2/PHYSICS_MAPPING_REGISTRY.json',root=ROOT)
    write_new(out/'registry_binding_checks.json',registry['runtime_binding_checks'])
    sources=['tools/build_block_relation_atlas.py','pll_allocation/scenarios.py','pll_allocation/verification/scenario.py',
        'pll_allocation/pipeline.py','pll_allocation/verification/run_suite.py','pll_allocation/verification/measure.py']
    sources += [r['path'] for r in registry['source_bindings']]
    write_new(out/'reuse_manifest.json',[{'path':p,'sha256':hashlib.sha256((ROOT/p).read_bytes()).hexdigest(),
        'domain':'original ideal model and frozen protocol','semantics':'reuse original implementation'} for p in sorted(set(sources))])
    specs={'E0':scenario(frozen,[150000,300000],50),'E1':scenario(frozen,[290000,300000],70)}
    rows=[];timer=time.perf_counter()
    axes=itertools.product(model['variables']['C1']['choices'],model['variables']['C2']['choices'],
        [50e-6,87.5e-6,125e-6,162.5e-6,200e-6],[2000,3000,4000,5000,6000,7000,8000],
        [10e6,17.5e6,25e6,32.5e6,40e6],[60e6,68e6,76e6])
    for c1,c2,icp,rz,kv,f0 in axes:
        c=make_candidate(model,{'Icp':icp,'Rz':rz,'C1':c1,'C2':c2,'Kvco':kv,'f0':f0})
        d=check_parameters(model,c);p=values(c)
        start=time.perf_counter();pred=raw_prediction(p);elapsed=time.perf_counter()-start
        r={**{k:p[k] for k in ('Icp','Rz','C1','C2','f0','Kvco')},'gain_product':icp*kv,
            'loop_gain':icp*kv/8,'tuning_valid':d['model_validity']=='VALID',**pred,'cheap_prediction_s':elapsed}
        for n,s in specs.items():
            by={a['metric']:a for a in s['metrics']}
            r[n+'_M1_equation_feasible']=bool(d['model_validity']=='VALID' and by['BW_Hz']['min']<=pred['BW_Hz']<=by['BW_Hz']['max'] and pred['PM_deg']>=by['PM_deg']['min'])
        rows.append(r)
    scan_wall=time.perf_counter()-timer;csv_new(out/'factorial_scan.csv',rows)
    shapes=[]
    for n,s in specs.items():
        pm=next(r['min'] for r in s['metrics'] if r['metric']=='PM_deg')
        for c1,c2 in itertools.product(model['variables']['C1']['choices'],model['variables']['C2']['choices']):
            interval=phase_interval(c1,c2,pm)
            if interval is None:
                shapes.append({'scenario':n,'C1':c1,'C2':c2,'PM_ceiling_deg':pm_ceiling(c1,c2),'x':None,'status':'EMPTY_PM_CEILING','BW_min_Hz':None,'BW_max_Hz':None});continue
            for i in range(81):
                f=1e-9+(1-2e-9)*i/80;x=math.exp(math.log(interval[0])+f*math.log(interval[1]/interval[0]))
                d=bandwidth_domain(model,s,c1,c2,x)
                shapes.append({'scenario':n,'C1':c1,'C2':c2,'PM_ceiling_deg':pm_ceiling(c1,c2),'x':x,'status':d['status'],'BW_min_Hz':d.get('BW_min_Hz'),'BW_max_Hz':d.get('BW_max_Hz')})
    csv_new(out/'conditional_shape_scan.csv',shapes)
    policies={};candidates={}
    for n,method in [('E0_analytical',analytical),('E0_slsqp',optimize),('E1_analytical',analytical)]:
        s=specs['E1' if n.startswith('E1') else 'E0'];meter=Meter();start=time.perf_counter();c,meta=method(model,s,meter)
        if c is None:raise RuntimeError('existing solver returned no candidate: '+n)
        candidates[n]=c;policies[n]={'elapsed_s':time.perf_counter()-start,'counts':meter.counts,'events':meter.events,'metadata':meta}
    c1,c2=50e-12,2e-9;phase=phase_interval(c1,c2,70)
    d=bandwidth_domain(model,specs['E1'],c1,c2,phase[1]*.995)
    candidates['E1_upper_shape'],_=witness(model,d,c1,c2,.95)
    write_new(out/'E1_competition.json',{'scenario':specs['E1'],
        'lower_PM_branch':bandwidth_domain(model,specs['E1'],c1,c2,phase[0]*1.005),'upper_PM_branch':d,
        'peak_shape':bandwidth_domain(model,specs['E1'],c1,c2,math.sqrt(41)),
        'tuning_conflict':'No unavoidable tuning conflict when f0 is free; each declared Kvco admits some interior f0.'})
    p=values(candidates['E0_analytical']);product=p['Icp']*p['Kvco'];kv=20e6/1.15
    alt=bandwidth_domain(model,specs['E0'],100e-12,1e-9,math.sqrt(11))
    candidates['E0_alternative_capacitors'],_=witness(model,alt,100e-12,1e-9,.5)
    candidates['E2_far_operating_point']=make_candidate(model,{**p,'Kvco':kv,'Icp':product/kv,'f0':60e6})
    candidates['E2_high_Kvco_center']=make_candidate(model,{**p,'Kvco':32e6,'Icp':product/32e6,'f0':60.8e6})
    candidates['E2_center_repair_reserve']=make_candidate(model,{**values(candidates['E2_far_operating_point']),'f0':80e6-kv*.6})
    times=[]
    for c in list(candidates.values())*3:
        start=time.perf_counter();res=evaluate(c);times.append(time.perf_counter()-start)
        if res.status.value!='OK':raise RuntimeError('representative M1 failure')
    checks={}
    for n,c in candidates.items():
        s=specs['E1' if n.startswith('E1') else 'E0'];start=time.perf_counter();a=assess_m1(model,s,c,Meter())
        if a['judgment']['verdict']!='M1_SPEC_PASS':raise RuntimeError('nonfeasible selection '+n)
        checks[n]={'assessment':a,'assessment_wall_s':time.perf_counter()-start,'parameter_sha256':fingerprint(c)}
    write_new(out/'sensitivities.json',sensitivity(model,specs['E0'],Meter(),candidates['E0_analytical']))
    write_new(out/'policies.json',policies);write_new(out/'candidate_M1_checks.json',checks);write_new(out/'complete_candidates.json',candidates)
    summary={'factorial_points':len(rows),'factorial_valid_tuning':sum(r['tuning_valid'] for r in rows),'factorial_wall_s':scan_wall,
        'factorial_cost_scope':'existing raw_prediction roots, not full evaluate, no M2',
        'factorial_E0_feasible':sum(r['E0_M1_equation_feasible'] for r in rows),'factorial_E1_feasible':sum(r['E1_M1_equation_feasible'] for r in rows),
        'conditional_shape_rows':len(shapes),'conditional_nonempty':{n:sum(r['scenario']==n and r['status']=='NONEMPTY' for r in shapes) for n in specs},
        'full_M1_timing':{'calls':len(times),'median_s':statistics.median(times),'min_s':min(times),'max_s':max(times),'all_s':times},
        'cheap_timing':{'calls':len(rows),'median_s':statistics.median(r['cheap_prediction_s'] for r in rows)},
        'sensitivity_M1_calls':9,'representative_assessment_M1_calls':len(candidates),'LLM_calls':0,'M2_calls':0,'discrete_pair_summary':[]}
    for c1,c2 in itertools.product(model['variables']['C1']['choices'],model['variables']['C2']['choices']):
        sub=[r for r in rows if r['C1']==c1 and r['C2']==c2];good=[r for r in sub if r['E0_M1_equation_feasible']]
        summary['discrete_pair_summary'].append({'C1':c1,'C2':c2,'PM_ceiling_deg':pm_ceiling(c1,c2),
            'E0_grid_feasible':len(good),'E1_grid_feasible':sum(r['E1_M1_equation_feasible'] for r in sub),
            'E0_gain_product_range':[min(r['gain_product'] for r in good),max(r['gain_product'] for r in good)] if good else None})
    write_new(out/'summary.json',summary);return summary


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--analyze',required=True,type=Path)
    args=p.parse_args();print(json.dumps(analyze(args.analyze),ensure_ascii=False,indent=2))
