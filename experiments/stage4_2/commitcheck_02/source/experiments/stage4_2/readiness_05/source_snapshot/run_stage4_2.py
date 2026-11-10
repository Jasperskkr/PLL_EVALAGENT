"""Stage4.2 finite numerical audit and frozen future-M2 candidate selection. No M2/LLM."""
from collections import Counter
from copy import deepcopy
import argparse
import csv
import hashlib
import itertools
import json
import math
from pathlib import Path
import platform
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pll_allocation.block_space.contracts import load_model, make_candidate, check_parameters
from pll_allocation.physics_mapping.model import evaluate, fingerprint
from pll_allocation.physics_mapping.validation import polynomial_reference
from pll_allocation.physics_mapping.experiment import judge_experiment
from pll_allocation.allocation.physics import raw_prediction, pm_ceiling, phase_interval, propagate

DOC = ROOT/'docs/stage4_2'
BINDINGS = ['configs/BLOCK_SPACE_MODEL_V1.json','configs/SYSTEM_SPEC_STAGE1_5.json',
 'configs/PLL_EQUATION_REGISTRY_V1.json','configs/verification/protocol_v1_1.json',
 'pll_allocation/physics_mapping/model.py','pll_allocation/physics_mapping/validation.py',
 'pll_allocation/block_space/contracts.py','pll_allocation/allocation/physics.py',
 'pll_allocation/allocation/allocate.py','pll_allocation/allocation/core.py',
 'pll_allocation/verification/verify.py','pll_allocation/verification/kernel.cpp',
 'pll_allocation/verification/simulator.py','pll_allocation/_legacy/physics/cp.py']


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, item):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(item, stream, ensure_ascii=False, indent=2, allow_nan=False);stream.write('\n')


def file_record(path):
    content = Path(path).read_bytes()
    return {'path':Path(path).relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(content).hexdigest(),'bytes':len(content),
        'normalized_lf_sha256':hashlib.sha256(content.replace(b'\r\n',b'\n')).hexdigest(),
        'byte_policy':'EXACT_OR_CRLF_LF_EQUIVALENT'}


def evidence_path(original, snapshot):
    path=ROOT/original
    return path if path.is_file() else DOC/'evidence'/snapshot


def scalar(p):
    return {k:v['value'] for k,v in p['values'].items()}


def shape_candidate(model, ugf, pm, c1, c2, branch=1, kv=20e6):
    """Audit design-point construction from already implemented phase interval; no policy change."""
    interval = phase_interval(c1,c2,pm)
    if interval is None: raise ValueError('shape unavailable')
    x=interval[branch]; q=1+c2/c1; w=2*math.pi*ugf
    product=8*(c1+c2)*w*w*math.sqrt((1+(x/q)**2)/(1+x*x))
    return make_candidate(model, {'C1':c1,'C2':c2,'Rz':x/(w*c2),'Kvco':kv,
        'Icp':product/kv,'f0':80e6-kv*.6})


def make_registry(model, evidence_catalog):
    common_domain = ['unchanged Stage1.5 complete SI envelope and six-variable declared space',
        'fixed f_ref=10MHz, integer N=8; ideal symmetric CP; zero nonideal context',
        'interior tuning; continuous M1 is locked small-signal only']
    mappings=[]
    def add(mid,unit,definition,variables,equations,forward,capability,propagation,m1,m2,tools,limitations,evidence):
        mappings.append({'system_metric_id':mid,'unit':unit,'definition':definition,
            'enabled_in_frozen_SystemSpec':mid in {'output_frequency_Hz','BW_Hz','PM_deg'},
            'related_block_variables':variables,'equation_ids':equations,'forward_model':forward,
            'inverse_capability':capability,'constraint_propagation_method':propagation,
            'supported_domain':common_domain,'verification_evidence':evidence,'model_limitations':limitations,
            'available_solver_tool':tools,'M1_support':m1,'M2_support':m2,
            'confidence_status':{'mathematical_definition':'DEFINED_IN_SCOPE' if mid!='RUR' else 'UNDEFINED',
                'numerical_implementation':m1,'behavioral_support':m2,
                'validated_parameter_domain':'finite evidence points only; no full-domain behavioral certificate',
                'unvalidated_generalization':'devices, nonidealities, global capture, periodic stability and noise remain excluded'}})
    dynamics=['Icp','Kvco','Rz','C1','C2','N']
    m1tool='pll_allocation.physics_mapping.model.evaluate'
    m2tool='pll_allocation.verification.verify.verify (complete saved AllocationProposal, new output directory)'
    add('output_frequency_Hz','Hz','conditional locked f_out=N*f_ref, not proof of capture or 1e-6Hz finite-window accuracy',
        ['f_ref','N','f0','Kvco','Vctrl_min','Vctrl_max'],['E_FREQ_PLAN','E_TUNING'],m1tool,
        'ANALYTICAL_INVERSE','fixed frequency plan check; Vmin<(N*f_ref-f0)/Kvco<Vmax; f0=F-Kvco*Vreq',
        'IMPLEMENTED_CONDITIONAL','tracking/control measured; frozen microHz equality UNKNOWN',
        ['block_space.contracts.check_parameters',m1tool,m2tool],
        ['fixed N/f_ref are not allocation degrees of freedom','static tuning does not establish acquisition'],['S15','S4'])
    add('Vctrl_required_V','V','(N*f_ref-f0)/Kvco; f0 is zero-volt intercept',
        ['f0','Kvco','f_ref','N','Vctrl_min','Vctrl_max'],['E_TUNING'],m1tool,'ANALYTICAL_INVERSE',
        'f0=F-Kvco*V; Kvco=(F-f0)/V for V>0; intersect original f0/Kvco bounds and strict rails',
        'IMPLEMENTED','steady control supported at sparse points',[m1tool,'block_space.contracts.check_parameters'],
        ['Kvco positive and linear; no curvature or PVT','no new voltage margin constraint is enabled'],['S15','S4'])
    add('BW_Hz','Hz','unique downward |T(j2pi f)|=1/sqrt(2), T=L/(1+L), normalized divided-phase response',
        dynamics,['E_KPFD','E_LF','E_OPEN','E_CLOSED','E_BW','R_SHAPE','R_SCALE'],m1tool,'NUMERICAL_INVERSE',
        'enumerate C1/C2; phase ceiling screening; solve BW/UGF scalar root then reconstruct R/gain and check bounded intersection',
        'IMPLEMENTED_NUMERIC_CROSSING','Protocol1.1 converged local measured BW; observable-dependent',
        ['allocation.physics.propagate','allocation.physics.inverse_at_shape','allocation.allocate.analytical',
         'allocation.allocate.optimize',m1tool,m2tool],
        ['analytical strategy contains bandwidth_ratio numerical root','not equivalent to UGF','local M2 evidence is not domain-wide'],['S15','S4','CURRENT_SCAN'])
    add('PM_deg','deg','180+arg L at valid unity crossing; ideal phase lead atan(x)-atan(x/q)',
        dynamics,['E_PM','E_UGF','R_SHAPE','R_PM_CEILING'],m1tool,'NUMERICAL_INVERSE',
        'analytic capacitor ratio ceiling and x interval; remaining BW/gain/R/tuning intersection requires existing bounded solver',
        'IMPLEMENTED_CONTINUOUS_ONLY','Stage4 numerical phase-port diagnostics converge; formal periodic PM UNKNOWN',
        ['allocation.physics.pm_ceiling','allocation.physics.phase_interval','allocation.physics.propagate',
         'allocation.allocate.optimize',m1tool],
        ['analytic x interval is a necessary shape condition, not complete allocation','no sampled/harmonic stability certificate'],['S15','S4','CURRENT_SCAN'])
    add('UGF_Hz','Hz','unique downward |L(j2pi f)|=1; diagnostic only in current frozen SystemSpec',
        dynamics,['E_UGF','R_SHAPE'],m1tool,'NUMERICAL_INVERSE',
        'conditional closed-form product/R at fixed legal C and x; full constrained allocation numerical; existing official solver has no UGF target field',
        'IMPLEMENTED_CONTINUOUS_ONLY','Stage4 local Series/Clamp crossings; formal UGF UNKNOWN',
        [m1tool,'allocation.physics.raw_prediction','allocation.physics.phase_interval'],
        ['forward query is not an exposed official UGF-target policy','do not replace BW by UGF or silently enable a constraint'],['S4','CURRENT_SCAN'])
    add('RUR','1','not defined in formal config/code; no assumed orientation or threshold',[],[],None,
        'UNSUPPORTED','request an approved definition; UGF/f_ref and f_ref/UGF may be separate diagnostics only',
        'NOT_IMPLEMENTED','NOT_IMPLEMENTED',[],['no authoritative definition; not a constraint','ratio is not proof of sampled equivalence'],['SOURCE_AUDIT'])
    add('static_phase_error_deg','deg','wrapped reference-minus-divided-output steady phase; supplemental charge relation phi=-2pi*f_ref*q0/Icp when assumptions hold',
        ['Icp','CP_leakage','q0','CP_mismatch','PFD_reset_delay','f_ref'],['R_CHARGE_BALANCE'],
        'legacy CP equilibrium_timing; not an enabled M1 metric','PHYSICS_SCREENING',
        'q0+I_branch*delta_t=0; phi_deg=360*f_ref*delta_t; bound signed charge if phase budget is approved',
        'NO_FORMAL_METRIC; ideal zero bias only','raw tail wrapped phase observable, no independent enabled static spec',
        ['_legacy.physics.cp.equilibrium_timing','_legacy.physics.cp.charge_window'],
        ['q0/leakage/reset/mismatch fixed zero; cannot claim nonzero-bias allocation readiness',
         'legacy q0 includes proxy load; do not transfer to Stage1.5 without sign/charge semantics audit'],['LEGACY_CP','SOURCE_AUDIT'])
    for mid,unit,definition in [('lock_time_s','s','earliest beginning of terminal sustained valid blocks under Protocol1.1 initial-condition/window definition'),
                               ('capture','1','CAPTURED_WITHIN_WINDOW or NOT_CAPTURED_WITHIN_WINDOW; not global nonlockability')]:
        add(mid,unit,definition,dynamics+['f0','Vctrl_min','Vctrl_max'],['E_TUNING','E_STABILITY'],
            'Protocol1.1 capture measurement only','BEHAVIORAL_ONLY','tuning/rail necessary screening then full M2; PM or RC constants cannot guarantee acquisition time',
            'NOT_IMPLEMENTED','IMPLEMENTED_WINDOW_CONDITIONAL',[m2tool],
            ['initial state/window and cycle-slip interpretation required','no enabled hard lock-time constraint','no validated analytical inverse'],['S15','S4','SOURCE_AUDIT'])
    add('jitter_s','s','needs explicit integration band, source PSD/correlation and timing observable',[],[],None,
        'UNSUPPORTED','no trusted allocation without noise sources/band/protocol','NOT_IMPLEMENTED','NOT_IMPLEMENTED',[],
        ['noise-free event model has no reference/CP/VCO/divider PSD model'],['SOURCE_AUDIT'])
    add('power_W','W','needs declared supplies and per-block static/dynamic power model',[],[],None,
        'UNSUPPORTED','no trusted allocation from CP current alone','NOT_IMPLEMENTED','NOT_IMPLEMENTED',[],
        ['Icp is pulse magnitude; not total DC supply current or VCO/divider power'],['SOURCE_AUDIT'])
    equations=[{'equation_id':key,'expression':expression,'status':'RESEARCH_DERIVATION_NOT_FORMAL_REGISTRY_REPLACEMENT',
        'source':source,'domain':'ideal locked continuous positive RC; same units as existing model'}
        for key,expression,source in [
          ('R_SHAPE','q=1+C2/C1; x=wu*Rz*C2; PM=atan(x)-atan(x/q); Icp*Kvco=N*(C1+C2)*wu^2*sqrt((1+(x/q)^2)/(1+x^2))','allocation/physics.py RELATIONS'),
          ('R_PM_CEILING','PMmax=asin((q-1)/(q+1)); x_peak=sqrt(q); tan(PM)*x^2-(q-1)*x+q*tan(PM)<=0','allocation/physics.py pm_ceiling, phase_interval'),
          ('R_SCALE','fixed C: Rnew=R/a; (Icp*Kvco)new=a^2*(Icp*Kvco); UGF/BW scale by a and PM unchanged','allocation/physics.py RELATIONS scaling'),
          ('R_CHARGE_BALANCE','q0+I_branch*delta_t=0; phi_rad=2*pi*f_ref*delta_t; q_cycle=I_leak/f_ref if explicitly defined','_legacy/physics/cp.py equilibrium_timing; supplemental charge conservation')]]
    return {'schema_version':'pll-physics-mapping-registry-0.1','status':'RESEARCH_REVIEW_ONLY',
        'replaces_formal_model':False,'baseline_commit':'47afcb72011636e838b03d81cf91bcec49744a77',
        'block_space_sha256':fingerprint(model),'system_spec_sha256':fingerprint(model['experiment']['system_spec']),
        'model_versions':model['versions'],'source_bindings':[file_record(ROOT/p) for p in BINDINGS],
        'evidence_catalog':evidence_catalog,'research_relations':equations,'mappings':mappings,
        'trust_policy':'M1 inverse produces a prediction candidate only; Runner owns domain/budgets/M2/PASS; registry never executes solver or enables spec'}


def main(out):
    start=time.perf_counter();out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    model=load_model(ROOT/'configs/BLOCK_SPACE_MODEL_V1.json');spec=model['experiment']['system_spec']
    write(out/'input_snapshot.json',{'model':model,'SystemSpec':spec,'plan_sha256':file_record(DOC/'AUDIT_AND_PLAN.md')['sha256']})
    costs=Counter();formal=[]
    def m1(p,purpose):
        costs['formal_M1_calls']+=1; result=evaluate(p).as_dict()
        formal.append({'purpose':purpose,'parameter_sha256':fingerprint(p),'parameters':p,'result':result})
        return result
    axes={'Icp':[50e-6,100e-6,200e-6],'Rz':[2000,3820,6000,8000],
          'f0':[60e6,64e6,72e6,76e6],'Kvco':[10e6,20e6,30e6,40e6]}
    write(out/'scan_plan.json',{'axes':axes,'C1':model['variables']['C1']['choices'],'C2':model['variables']['C2']['choices'],
          'declared_points':1728,'M1_crosscheck_rule':'global row index modulo 23 == 0 and valid',
          'acceptance_numerical_consistency':{'BW_UGF_relative':1e-8,'PM_absolute_deg':1e-7},
          'not_a_probability_sample':True,'M2_selection_feedback_used':False})
    rows=[];max_errors=Counter();passes=True
    for index, values in enumerate(itertools.product(model['variables']['C1']['choices'],model['variables']['C2']['choices'],*axes.values())):
        c1,c2,*rest=values;p=make_candidate(model,{'C1':c1,'C2':c2,**dict(zip(axes,rest))})
        domain=check_parameters(model,p);costs['domain_checks']+=1
        row={'index':index,**{k:scalar(p)[k] for k in ('Icp','Rz','C1','C2','f0','Kvco')},
             'parameter_sha256':fingerprint(p),'domain':domain['model_validity'],
             'Vreq_V':domain['derived']['Vctrl_required_V'],'declared_domain':domain['declared_domain']}
        if domain['model_validity']=='VALID':
            pred=raw_prediction(scalar(p));costs['cheap_prediction_calls']+=1
            ref=polynomial_reference(p);costs['polynomial_reference_calls']+=1
            row.update({k:pred[k] for k in ('BW_Hz','UGF_Hz','PM_deg')})
            row['M1_SPEC_STATUS']='M1_SPEC_PASS' if 150e3<=pred['BW_Hz']<=300e3 and pred['PM_deg']>=50 else 'M1_SPEC_FAIL'
            for k in ('BW_Hz','UGF_Hz','PM_deg'):
                err=abs(pred[k]-ref[k])/(abs(ref[k]) if k!='PM_deg' else 1)
                max_errors['cheap_vs_polynomial_'+k]=max(max_errors['cheap_vs_polynomial_'+k],err)
                passes &= err <= (1e-7 if k=='PM_deg' else 1e-8)
            if index%23==0:
                official=m1(p,'scan_fixed_mod23');row['formal_M1_crosschecked']=True
                for k in ('BW_Hz','UGF_Hz','PM_deg'):
                    err=abs(pred[k]-official['metrics'][k])/(abs(pred[k]) if k!='PM_deg' else 1)
                    max_errors['cheap_vs_formal_'+k]=max(max_errors['cheap_vs_formal_'+k],err)
                    passes &= err <= (1e-7 if k=='PM_deg' else 1e-8)
        else:row['M1_SPEC_STATUS']='UNKNOWN'
        rows.append(row)
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with (out/'domain_scan.csv').open('x',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    pair_rows=[]
    for pair in propagate(model,spec)['capacitor_pairs']:
        pair_rows.append({**pair,'C2_over_C1':pair['C2']/pair['C1'],
            'can_reach_PM50_in_unbounded_gain_shape':pair['x_interval'] is not None})
    write(out/'constraint_propagation.json',{'existing_propagate_result':propagate(model,spec),'capacitor_pairs':pair_rows,
          'tuning_inequality':'Kvco>(80e6-f0)/1.2 with fixed positive zero lower rail',
          'tuning_uniform_rectangle_fraction':17/18,'fraction_derivation':'rejected triangle area .5*(8e6)*(20e6/3) divided by (16e6*30e6); assumes uniform independent continuous f0,Kvco, not capability probability',
          'formal_domain_unchanged':True})
    nominal=make_candidate(model)
    saved_path=evidence_path('experiments/stage3a1_llm_retry_20261104_01/AllocationProposal.json','saved_agent_Proposal.json')
    agent=read(saved_path)['joint_block_spec']
    boundary_path=evidence_path('experiments/stage4_study_20261105_02/pm_boundary/AllocationProposal.json','saved_boundary_Proposal.json')
    boundary=read(boundary_path)['joint_block_spec']
    definitions=[('C01_nominal',nominal,'existing model defaults','ANCHOR','nominal baseline'),
        ('C02_real_agent',agent,'saved full real Agent Proposal, never a new LLM call','ANCHOR','existing inverse-policy candidate'),
        ('C03_pm_boundary',boundary,'Stage4 boundary selected with M1 within frozen range','ANCHOR','existing PM50 boundary'),
        *[(f'C0{i}_matched_pm{pm}',shape_candidate(model,140e3,pm,100e-12,2e-9),
           'M1 shape algebra, high-x branch, fixed 140kHz and identical C1/C2','PAIRED_DEVELOPMENT',
           'matched UGF and C; vary PM via R and gain, Kvco/f0 held fixed') for i,pm in zip((4,5,6),(55,60,65))],
        ('C07_low_pm',shape_candidate(model,140e3,35,100e-12,500e-12,branch=0),
           'M1 shape algebra; low-x branch','DEVELOPMENT','legal PM35 negative control; deliberately fails PM50'),
        ('C08_gain_split',make_candidate(model,{'Icp':160e-6,'Kvco':12.5e6}),
           'predeclared Icp*Kvco invariant with nominal RC/f0','PAIRED_DEVELOPMENT',
           'same M1 dynamics as C01; different CP/VCO gain split and Vreq .64V'),
        ('C09_holdout',make_candidate(model,{'Icp':73.4e-6,'Rz':5870,'C1':100e-12,'C2':500e-12,'f0':67.3e6,'Kvco':17.1e6}),
           'predeclared unique SI tuple; no M2 or tuning based on measured response','HOLDOUT',
           'unseen moderate gain/RC/tuning combination; characterization only'),
        ('C10_holdout',make_candidate(model,{'Icp':163e-6,'Rz':2670,'C1':200e-12,'C2':2e-9,'f0':61.9e6,'Kvco':33.2e6}),
           'predeclared unique SI tuple; no M2 or tuning based on measured response','HOLDOUT',
           'unseen high gain with larger capacitance; retain regardless of M1 PASS')]
    selected=[]
    write(out/'candidate_selection_before_prediction.json',[{'id':cid,'parameters':p,'source':src,'role':role,'reason':reason}
          for cid,p,src,role,reason in definitions])
    def find_envelopes(value):
        if isinstance(value,dict):
            if {'schema_version','conventions','values'} == set(value):yield value
            else:
                for child in value.values():yield from find_envelopes(child)
        elif isinstance(value,list):
            for child in value:yield from find_envelopes(child)
    old_candidate_path=ROOT/'outputs/block_space_v1_20261104_01/candidate_snapshots.json'
    if old_candidate_path.is_file():
        historical_index={'source':file_record(old_candidate_path),
            'parameter_hashes':sorted({fingerprint(p) for p in find_envelopes(read(old_candidate_path))})}
    else:
        historical_index=read(DOC/'evidence/historical_candidate_hashes.json')
    old_hashes=set(historical_index['parameter_hashes']) | {fingerprint(x) for x in (nominal,agent,boundary)}
    for cid,p,src,role,reason in definitions:
        domain=check_parameters(model,p);costs['domain_checks']+=1
        if domain['declared_domain']!='IN_DECLARED_DOMAIN' or domain['model_validity']!='VALID':raise ValueError(cid+': illegal')
        result=m1(p,'candidate_registration_only' if role=='HOLDOUT' else 'candidate')
        selected.append({'candidate_id':cid,'joint_block_spec':p,'parameter_sha256':fingerprint(p),
            'fixed_operating_conditions':{k:v for k,v in p['values'].items() if k not in ('Icp','Rz','C1','C2','f0','Kvco')},
            'source':src,'source_proposal':file_record(saved_path) if cid=='C02_real_agent' else None,
            'role':role,'selection_reason':reason,'physical_hypothesis':reason,'domain':domain,
            'M1_prediction':result,'M1_judgment':judge_experiment(model['experiment'],p,_mapping_result(result)),
            'M2_status':'NOT_RUN_STAGE4_2','verified_joint_block_spec':False,
            'independence':{'exact_match_to_reviewed_historical_anchor_set':fingerprint(p) in old_hashes,
                'M2_used_for_selection':False,'used_for_method_tuning':role!='HOLDOUT',
                'holdout_scope':'no new M2 yet; exact novelty against recorded Stage1.5 and Stage4 anchors only, not a statistical blinded guarantee'}})
    candidates={'schema_version':'pll-m2-candidate-plan-0.1','model_versions':model['versions'],
        'block_space_sha256':fingerprint(model),'system_spec_sha256':fingerprint(spec),'candidates':selected,
        'selection_protocol':'fixed predeclared M1 geometry and two holdouts; no future M2 leakage',
        'matched_comparison':'C04/C05/C06 same C1/C2/Kvco/f0/UGF; R/Icp necessarily covary, not a causal PM intervention',
        'M2_new_calls':0,'LLM_new_calls':0,'formal_domain_unchanged':True}
    write(out/'M2_VALIDATION_CANDIDATES.json',candidates)
    npred=m1(nominal,'coupling_center')['metrics'];coupling=[]
    for name,update in [('equal_gain_product',{'Icp':160e-6,'Kvco':12.5e6}),('f0_only',{'f0':68e6}),
                        ('scale_0.9',{'Rz':3820/.9,'Icp':100e-6*.9**2}),
                        ('scale_1.1',{'Rz':3820/1.1,'Icp':100e-6*1.1**2})]:
        p=make_candidate(model,update);pred=m1(p,name)['metrics']
        factor=float(name.split('_')[1]) if name.startswith('scale_') else 1.
        checked={k:abs(pred[k]/npred[k]/factor-1) if k!='PM_deg' else abs(pred[k]-npred[k]) for k in ('BW_Hz','UGF_Hz','PM_deg')}
        coupling.append({'name':name,'parameters':p,'prediction':pred,'normalized_errors':checked})
        passes &= max(checked.values())<1e-7
    derivatives={}
    for name in ('Icp','Rz','f0','Kvco'):
        p=scalar(nominal); a=m1(make_candidate(model,{name:p[name]*.99}),'local_derivative')['metrics']
        b=m1(make_candidate(model,{name:p[name]*1.01}),'local_derivative')['metrics'];delta=math.log(1.01/.99)
        derivatives[name]={k:(b[k]-a[k])/delta if k=='PM_deg' else math.log(b[k]/a[k])/delta
                          for k in ('BW_Hz','UGF_Hz','PM_deg','Vctrl_required_V')}
    discrete=[]
    for name,choices in [('C1',[50e-12,200e-12]),('C2',[500e-12,2e-9])]:
        for value in choices:discrete.append({'parameter':name,'value':value,'metrics':m1(make_candidate(model,{name:value}),'discrete_C_jump')['metrics']})
    write(out/'coupling_and_sensitivity.json',{'invariance_and_scale':coupling,'nominal_log_derivatives':derivatives,
        'derivative_units':'elasticity except PM_deg per ln(parameter); C is categorical','discrete_C_jumps':discrete,
        'holdouts_included':False,'causality_claim':False})
    write(out/'formal_M1_evaluations.json',formal)
    evidence_dir=out/'evidence';evidence_dir.mkdir();evidence=[]
    source_evidence=[('S15','outputs/block_space_v1_20261104_01/summary.json'),
        ('S4_nominal','experiments/stage4_summary_20261105_05/nominal_extension.json'),
        ('S4_agent','experiments/stage4_summary_20261105_05/real_agent_extension.json'),
        ('S4_boundary','experiments/stage4_summary_20261105_05/pm_boundary_extension.json')]
    for key,name in source_evidence:
        origin=evidence_path(name,key+'.json');target=evidence_dir/(key+'.json');target.write_bytes(origin.read_bytes())
        evidence.append({'evidence_id':key,'source':file_record(origin),'snapshot':file_record(target),
            'interpretation':'historical read-only evidence; not a new Stage4.2 simulation'})
    write(evidence_dir/'saved_agent_Proposal.json',read(saved_path))
    write(evidence_dir/'saved_boundary_Proposal.json',read(boundary_path))
    write(evidence_dir/'historical_candidate_hashes.json',historical_index)
    write(out/'evidence_manifest.json',evidence)
    summary={'scan_points':len(rows),'domain_counts':dict(Counter(r['domain'] for r in rows)),
        'M1_spec_counts':dict(Counter(r['M1_SPEC_STATUS'] for r in rows)),
        'formal_scan_crosschecks':sum(r.get('formal_M1_crosschecked',False) for r in rows),
        'maximum_numerical_errors':dict(max_errors),'candidate_count':len(selected),'holdouts':2,
        'numerical_consistency_passed':bool(passes),'cost':dict(costs),'research_M2_calls':0,'research_LLM_calls':0,
        'elapsed_s':time.perf_counter()-start,'claim':'finite numerical equation consistency only; not behavioral accuracy or feasible-volume estimate'}
    write(out/'summary.json',summary)
    catalog={'S15':evidence[0],'S4':{'records':evidence[1:],'scope':'three local points; UGF/PM UNKNOWN'},
        'CURRENT_SCAN':file_record(out/'summary.json'),'SOURCE_AUDIT':{'report':'docs/stage4_2/EQUATION_AND_DOMAIN_AUDIT.md'},
        'LEGACY_CP':{'source':file_record(ROOT/'pll_allocation/_legacy/physics/cp.py'),'scope':'charge algebra only; incompatible contexts must not be mixed'}}
    registry=make_registry(model,catalog);write(out/'PHYSICS_MAPPING_REGISTRY.json',registry)
    from pll_allocation.physics_mapping.registry import load_registry,route
    index=load_registry(out/'PHYSICS_MAPPING_REGISTRY.json')
    write(out/'agent_query_examples.json',[route(index,k) for k in ('Vctrl_required_V','BW_Hz','capture','RUR')])
    snapshots=out/'source_snapshot';snapshots.mkdir()
    for path in (Path(__file__),ROOT/'pll_allocation/physics_mapping/registry.py'):
        (snapshots/path.name).write_bytes(path.read_bytes())
    write(out/'run_manifest.json',{'command':sys.argv,'Python':sys.version,'platform':platform.platform(),
        'baseline_commit':'47afcb72011636e838b03d81cf91bcec49744a77','model_versions':model['versions'],
        'source_bindings':registry['source_bindings']+[file_record(Path(__file__)),file_record(ROOT/'pll_allocation/physics_mapping/registry.py')],
        'output_file_hashes':[file_record(p) for p in sorted(out.rglob('*')) if p.is_file()],
        'registry':file_record(out/'PHYSICS_MAPPING_REGISTRY.json'),'candidates':file_record(out/'M2_VALIDATION_CANDIDATES.json'),
        'cost':dict(costs),'M2_calls':0,'LLM_calls':0,'verified_joint_block_spec':False})
    print(json.dumps(summary,ensure_ascii=False));return 0 if passes else 1


def _mapping_result(item):
    from pll_allocation.physics_mapping.model import MappingResult,Status
    return MappingResult(**{**item,'status':Status(item['status'])})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args();raise SystemExit(main(a.out))
