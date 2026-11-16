"""Read-only provenance/intent audit; no new predictions, M1, or API calls."""
import argparse
import itertools
import json
import math
from pathlib import Path


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def main(root):
    root=Path(root).resolve();findings=[];rows=[]
    for path in sorted((root/'runs').glob('*/multi_region_result.json')):
        result=read(path);folder=path.parent
        state=read(folder/'PlannerState.json') if (folder/'PlannerState.json').exists() else {}
        plans=result['actual_windows'];spec=result['spec'];initial=read(folder/'MULTI_REGION_PLAN.json') if (folder/'MULTI_REGION_PLAN.json').exists() else None
        local=[]
        for plan in plans:
            data=plan['intent_compilation'];intent=data['original_physics_intent'];axes=plan['parameters'];ratio=intent['c2_c1_ratio']
            actual_ratio=[axes['C2']['min']/axes['C1']['max'],axes['C2']['max']/axes['C1']['min']]
            request_C1=data['requested_C1_F'];compiled=data['executed_construction_C1_F']
            tolerance=1e-12
            valid=(request_C1[0]*(1-tolerance)<=compiled[0]<compiled[1]<=request_C1[1]*(1+tolerance)
                   and ratio[0]*(1-tolerance)<=actual_ratio[0]<=actual_ratio[1]<=ratio[1]*(1+tolerance))
            if not valid:findings.append({'run_id':result['run_id'],'region':plan['region_id'],'issue':'compiled region not inside requested physics intent'})
            local.append({'region_id':plan['region_id'],'hypothesis':intent['hypothesis'],'evidence_ids':intent['evidence_ids'],
                'target_bw_fraction':intent['target_bw_fraction'],'reserved_bw_margin_fraction':intent['reserved_bw_margin_fraction'],
                'requested_C1_F':request_C1,'compiled_C1_F':compiled,'C1_log_width_fraction':data['compiled_C1_log_width_fraction'],
                'requested_ratio':ratio,'compiled_all_corner_ratio':actual_ratio,'inside_requested_intent':valid,
                'seed_hashes':plan['builder_seed_hashes'],'priority':intent['priority'],'strategy':intent['strategy'],
                'tuning_preference':intent['tuning_preference'],'search_tools':intent['search_tools'],'initial_budget':intent['m1_budget']})
        pairwise=[]
        for a,b in itertools.combinations(local,2):
            ah,bh=set(a['seed_hashes']),set(b['seed_hashes'])
            pairwise.append({'a':a['region_id'],'b':b['region_id'],'shared_seed_hashes':sorted(ah&bh),
                'different_C1_compilation':a['compiled_C1_F']!=b['compiled_C1_F'],
                'different_ratio_intent':a['requested_ratio']!=b['requested_ratio'],
                'different_BW_target':a['target_bw_fraction']!=b['target_bw_fraction'],
                'different_tuning':a['tuning_preference']!=b['tuning_preference']})
            if ah&bh:findings.append({'run_id':result['run_id'],'issue':'initial regions shared Builder seed','pair':[a['region_id'],b['region_id']]})
        feedback=[]
        actions=[json.loads(line) for line in (folder/'actions.jsonl').read_text(encoding='utf-8').splitlines()] if (folder/'actions.jsonl').exists() else []
        for f in sorted(folder.glob('feedback_*/decision.json')):
            decision=read(f);prior=read(f.parent/'PlannerState.json');execution=read(f.parent/'execution.json') if (f.parent/'execution.json').exists() else None
            feedback.append({'path':f.relative_to(root).as_posix(),'action':decision['action'],'region_id':decision['region_id'],
                'reason':decision['reason'],'cited_evidence':decision['evidence_ids'],
                'actual_prior_top8_count':prior['top8_count'],'actual_prior_first_in_top8':prior['first_in_top8'],
                'actual_prior_available_M1':prior['available_search_M1'],
                'actual_tools_executed':execution['actual_tools_executed'] if execution else False,
                'actual_new_M1':(execution.get('observation') or {}).get('formal_M1_calls',0) if execution else 0,
                'interpretation':'STOP reason is planner prose; controller point count and execution are authoritative'})
        invalid=[]
        for v in sorted(folder.glob('**/validation_*.json')):
            record=read(v)
            if not record['accepted']:invalid.append({'path':v.relative_to(root).as_posix(),'repair_attempt':record['repair_attempt'],
                'error':record.get('message'),'repairable':record.get('repairable_structure')})
        rows.append({'run_id':result['run_id'],'policy':result['policy'],'initial_plan_legal':initial is not None,
            'initial_proposed_count':len(initial['regions']) if initial else None,'actual_regions':local,'pairwise_physical_distinction':pairwise,
            'feedback':feedback,'invalid_decisions':invalid,'source_ownership':{'LLM':'hypotheses/intent envelopes/priority/permissions/budgets/feedback',
                'Controller':'SI coordinates/contained compilation/contracts/budget/evidence registration',
                'original_Builder':'actual numerical seeds and local boxes','original_Explorer':'formal M1, SLSQP, sensitivity budget/cache'},
            'actual_action_tools':[{'phase':a['phase'],'method':a['decision']['search_method'],
                'actual_tool_method':a['observation'].get('tool_method') or next((s['solver'] for s in a['observation'].get('solver_runs',[]) if s.get('solver')),a['decision']['search_method']),
                'decision_id':a['decision']['decision_id'],'M1_calls':a['observation']['cost']['M1_calls'],
                'solver_runs':a['observation'].get('solver_runs',[])} for a in actions],
            'no_reference_point_in_state':not any(k in state for k in ('reference_only','reference_witness','known_feasible_point'))})
    summary={'scope':'POSTHOC_READ_ONLY_NO_API_NO_M1','violations':findings,'runs':rows,
        'P2_legal_initial':sum(r['policy']=='P2' and r['initial_plan_legal'] for r in rows),
        'P2_feedback_actual_actions':sum(f['actual_tools_executed'] for r in rows if r['policy']=='P2' for f in r['feedback']),
        'P2_feedback_STOP':sum(f['action']=='STOP' for r in rows if r['policy']=='P2' for f in r['feedback']),
        'notice':'Distinct envelopes and seeds evidence distinct hypotheses/execution; neither physical prose nor corner bounds certify a feasible region.'}
    with (root/'PHYSICAL_INTENT_AND_FEEDBACK_AUDIT_v3.json').open('x',encoding='utf-8') as handle:
        json.dump(summary,handle,ensure_ascii=False,indent=2,allow_nan=False)
    print(json.dumps({k:v for k,v in summary.items() if k!='runs'},ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',required=True);main(parser.parse_args().out)
