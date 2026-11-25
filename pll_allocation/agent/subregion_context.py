"""Export existing PhysicsContext contract from actual shared executor evidence."""
from copy import deepcopy
from ..contract_names import current_label
import csv
import hashlib
import json
from pathlib import Path

from ..allocation.core import write_new
from ..allocation.physics import RELATIONS
from ..block_space.contracts import FREE_IDS
from ..exploration.engine import model_identity
from ..exploration.contracts import screen_problem
from ..exploration.regions import candidate_regions
from ..physics_mapping.model import fingerprint


def was_formal_call(row):
    """An evaluator exception is a charged call even without a MappingResult.

    Legacy M1 exploration evidence predates the explicit call flag. New executor rows
    always carry it, and that authoritative flag includes failed calls.
    """
    return bool(row.get('formal_M1_called', row.get('formal_M1_result')))


def export_context(problem,samples,out,*,cost,sensitivities=(),scope='SUBREGION_M1_EXPLORATION',llm_executed=False):
    scope=current_label(scope)
    root=Path(out);root.mkdir(parents=True,exist_ok=False)
    samples=deepcopy(samples);sensitivities=deepcopy(sensitivities)
    # Imported evidence must not collide with new regional M1 sample IDs.
    if scope in ('DETERMINISTIC_PHYSICS_EXPLORATION','LLM_GUIDED_SUBREGION_EXPLORATION'):
        ids={r['evidence_id']:'EXPLORATION:'+r['evidence_id'] for r in samples}
        for r in samples:
            r['source_pilot_evidence_id']=r['evidence_id'];r['evidence_id']=ids[r['evidence_id']]
            if r.get('duplicate_of'):r['duplicate_of']=ids.get(r['duplicate_of'],r['duplicate_of'])
        for derivative in sensitivities:
            for rep in derivative.get('representatives',[]):
                rep['center_evidence_id']=ids[rep['center_evidence_id']]
                for col in rep['columns'].values():col['evidence_ids']=[ids.get(i,i) for i in col['evidence_ids']]
        write_new(root/'evidence_aliases.json',{'pilot_to_exported':ids,'reason':'Avoid collisions with downstream regional execution request IDs; original evidence preserved'})
    model=model_identity()
    meta={'problem_schema_version':problem['schema_version'],'problem_sha256':problem['problem_sha256'],
        'model_fingerprint':model['model_sha256'],'scope':scope}
    common={'metadata':meta,'model':model,'cost':deepcopy(cost),'status':'EVIDENCE_EXPORTED'}
    # M1 exploration selects regions from actual sampled points with its original rule.
    usable=[r for r in samples if not r['origin'].startswith(('LOCAL_SENSITIVITY','SENSITIVITY:'))]
    regions=candidate_regions(problem,usable)
    derivatives={'representatives':[r for s in sensitivities for r in s.get('representatives',[])],
        'scope':'Actual original M1 exploration local stencils only; no global derivative theorem',
        'definition':'d(metric / metric_scale) / d(u)'}
    summary={'M1_feasible_sample_count':sum(r['judgment']['m1_feasibility']=='FEASIBLE' and bool(r.get('formal_M1_result')) for r in samples),
        'formal_M1_calls':sum(was_formal_call(r) for r in samples),'whole_regions_certified':False,
        'FULL_SYSTEMSPEC_CERTIFIED':False,'M2_status':'NOT_EVALUATED'}
    with (root/'m1_samples.jsonl').open('x',encoding='utf-8') as f:
        for row in samples:f.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n')
    with (root/'m1_samples.csv').open('x',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['evidence_id','origin',*FREE_IDS,'M1_status','m1_feasibility','minimum_normalized_margin','BW_Hz','PM_deg','formal_M1_called','parameter_sha256'])
        w.writeheader()
        for r in samples:w.writerow({'evidence_id':r['evidence_id'],'origin':r['origin'],
            **{k:r['parameters']['values'][k]['value'] for k in FREE_IDS},'M1_status':r['M1_status'],
            **{k:r['judgment'][k] for k in ('m1_feasibility','minimum_normalized_margin')},
            **{k:r['metrics'].get(k) for k in ('BW_Hz','PM_deg')},'formal_M1_called':was_formal_call(r),
            'parameter_sha256':r['parameter_sha256']})
    write_new(root/'problem_resolved.json',{'problem':problem,**common})
    write_new(root/'physics_screening.json',{**common,**screen_problem(problem)})
    write_new(root/'candidate_regions.json',{**common,**regions})
    write_new(root/'sensitivity.json',{**common,**derivatives})
    write_new(root/'feasible_candidates.json',{**common,'candidates':[deepcopy(r) for r in samples
        if r['judgment']['m1_feasibility']=='FEASIBLE' and r.get('formal_M1_result')]})
    names=('problem_resolved.json','m1_samples.jsonl','candidate_regions.json','sensitivity.json','feasible_candidates.json')
    context={**common,'schema_version':'pll-physics-context-1.0','problem':deepcopy(problem),'summary':summary,
        'relations':RELATIONS,'candidate_regions':regions['regions'],'sensitivity':derivatives,
        'evidence_artifacts':{n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},
        'evidence_ids':[r['evidence_id'] for r in samples],
        'capability_boundary':{'BW_PM_UGF':'Existing ideal continuous locked-point M1 only','tuning':'Static interior only',
            'lock_time_s':'PENDING_M2','jitter_s':'UNSUPPORTED','M2_executed':False,
            'LLM_executed':llm_executed,'whole_regions_certified':False},
        'exploration_source':scope}
    context['context_sha256']=fingerprint(context)
    write_new(root/'physics_context.json',context)
    with (root/'exploration_report.md').open('x',encoding='utf-8') as f:
        f.write('# M1 exploration evidence\n\n'+json.dumps(summary,ensure_ascii=False,indent=2)+
            '\n\nSource: '+scope+'. Regions are sample-supported suggestions; M2 NOT_EVALUATED.\n')
    return root/'physics_context.json'
