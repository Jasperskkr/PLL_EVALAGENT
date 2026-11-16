"""Post hoc interpretation of saved M1 ablations; no solver/provider/evaluator."""
from pathlib import Path
from itertools import combinations
from collections import Counter
import csv
import json
import math
import statistics as stats

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'experiments/spec_allocation_ablation'


def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def rows(path):return [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines()] if path.exists() else []
def put(path,value):
    with path.open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False)
def csvout(path,data):
    with path.open('x',encoding='utf-8-sig',newline='') as f:
        keys=list(dict.fromkeys(k for r in data for k in r));w=csv.DictWriter(f,fieldnames=keys);w.writeheader()
        for r in data:w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v for k,v in r.items()})
def med(values):return stats.median(values) if values else None
def fmt(value):return '未达到' if value is None else f'{value:.5g}'
def signature(v):return [v['C2']/v['C1'],v['Rz']*v['C2'],v['Icp']*v['Kvco']/(8*(v['C1']+v['C2']))]
def equiv(a,b,tolerance=1e-6):return all(abs(math.log(x/y))<=tolerance for x,y in zip(a,b))


def main():
    cfg=read(OUT/'frozen/config.json');summary=read(OUT/'SUMMARY.json')
    results=[read(OUT/task/e['run_id']/'result.json') for task in ('task1','task2','task3') for e in cfg['matrices'][task]]
    def group(task,arm,spec='ALL'):
        return next(r for r in summary['aggregates'] if r['task']==task and r['arm']==arm and r['spec']==spec)
    e3=[];seeds=[]
    for arm in ('S0','S1','S2'):
        rs=[r for r in results if r['task']=='task1' and r['arm']==arm]
        attempts=[];firsts=[]
        for r in rs:
            folder=OUT/'task1'/r['run_id'];attempts+=rows(folder/'region_REGION/inverse_attempts.jsonl')
            if (folder/'first_PASS.json').exists():firsts.append(read(folder/'first_PASS.json'))
            for a in rows(folder/'region_REGION/inverse_attempts.jsonl'):
                if a['parameters']:
                    seeds.append({'run_id':r['run_id'],'arm':arm,'attempt':a['attempt'],
                        'corner_priority':a['corner_priority'],'shape_x':a['shape_x'],
                        'C2_C1':a['C2_F']/a['C1_F'],'phase_ceiling_deg':a['PM_ceiling_deg'],
                        'ideal_phase_at_shape_deg':math.degrees(math.atan(a['shape_x'])-math.atan(a['shape_x']/(1+a['C2_F']/a['C1_F']))),
                        'target_BW_Hz':a['target_BW_Hz'],'loop_signature':signature({k:a['parameters']['values'][k]['value'] for k in cfg['global_domain']})})
        called=[a for a in attempts if a['inverse_called']]
        e3.append({'arm':arm,'construction_attempts':len(attempts),'inverse_called':len(called),
            'construction_status_counts':dict(Counter(a['status'] for a in attempts)),
            'preinverse_phase_ceiling_rejections':sum(a['status']=='LF_PHASE_CEILING_REJECTED' for a in attempts),
            'invalid_called_inverse':sum(a['status']!='SEED_CONSTRUCTED' for a in called),
            'invalid_called_inverse_fraction':sum(a['status']!='SEED_CONSTRUCTED' for a in called)/len(called) if called else None,
            'first_PM_median_deg':med([r['metrics']['PM_deg'] for r in firsts]),
            'first_margin_median':med([r['judgment']['minimum_normalized_margin'] for r in firsts]),
            'first_BW_median_Hz':med([r['metrics']['BW_Hz'] for r in firsts]),
            'inverse_wall_s':sum(a['wall_s'] for a in attempts),
            'solver_status_counts':dict(Counter(s['status'] for r in rs
                for p in (OUT/'task1'/r['run_id']).glob('region_*/executor/region_observations.json')
                for o in read(p)['observations'] for s in o['solver_runs'] if s.get('started')))})
    put(OUT/'E3_CAUSAL_DETAIL.json',e3);csvout(OUT/'E3_CONSTRUCTED_SHAPES.csv',seeds)
    residuals=[]
    for r in results:
        folder=OUT/r['task']/r['run_id']
        formal={x['parameter_sha256']:x for x in rows(folder/'all_candidates.jsonl') if x['formal_M1_called']}
        for path in folder.glob('region_*/inverse_attempts.jsonl'):
            for attempt in rows(path):
                point=formal.get(attempt.get('parameter_sha256'))
                if point is None or point['M1_status']!='OK':continue
                q=1+attempt['C2_F']/attempt['C1_F'];x=attempt['shape_x']
                ideal_pm=math.degrees(math.atan(x)-math.atan(x/q));bw=point['metrics']['BW_Hz']
                residuals.append({'task':r['task'],'run_id':r['run_id'],'arm':r['arm'],
                    'corner_priority':attempt['corner_priority'],'target_BW_Hz':attempt['target_BW_Hz'],
                    'formal_BW_Hz':bw,'BW_relative_error':(bw-attempt['target_BW_Hz'])/attempt['target_BW_Hz'],
                    'predicted_PM_deg':ideal_pm,'formal_PM_deg':point['metrics']['PM_deg'],
                    'PM_error_deg':point['metrics']['PM_deg']-ideal_pm,
                    'formal_PASS':point['judgment']['m1_feasibility']=='FEASIBLE',
                    'scope':'agreement of inverse and formal M1 within SAME ideal model, not independent physical accuracy'})
    csvout(OUT/'INVERSE_VS_FORMAL_M1_RESIDUALS.csv',residuals)
    put(OUT/'INVERSE_ACCURACY_SCOPE.json',{'matched_seed_count':len(residuals),
        'maximum_abs_relative_BW_error':max((abs(r['BW_relative_error']) for r in residuals),default=None),
        'maximum_abs_PM_error_deg':max((abs(r['PM_error_deg']) for r in residuals),default=None),
        'independent_physical_model_validation':False})

    gauges=[];anchors={}
    for r in results:
        if r['task']!='task2':continue
        folder=OUT/'task2'/r['run_id'];p=folder/'physics_context.json'
        context=read(p) if p.exists() else None
        region=r['actual_region_contracts'][0] if r['actual_region_contracts'] else None
        clipping={}
        if context:
            v=context['scale_anchors_SI'];anchors[(r['spec'],r['seed'],r['arm'])]=signature(v)
            for k,a in cfg['global_domain'].items():
                if k=='f0':continue
                requested=[v[k]/10,v[k]*10];actual=[region['executed_region'][k][x] for x in ('min','max')]
                clipping[k]={'unclipped_rule_interval':requested,'actual_interval':actual,
                    'lower_clipped_by_frozen_guard':requested[0]<a['min'],
                    'upper_clipped_by_frozen_guard':requested[1]>a['max']}
        gauges.append({'run_id':r['run_id'],'spec':r['spec'],'arm':r['arm'],'seed':r['seed'],
            'gauge_Ohm':context['impedance_gauge_Ohm'] if context else None,
            'anchor_response_signature':signature(context['scale_anchors_SI']) if context else None,
            'guard_clipping':clipping,'global_guard_unchanged':True,
            'first_PASS':r['first_PASS'],'first_M1':r['M1_to_first_PASS'],'first_time_s':r['time_to_first_PASS_s'],
            'first_margin':r['first_margin'],'full_wall_s':r['total_wall_s']})
    anchor_equivalence=[]
    for spec in ('SN','ST'):
        for seed in cfg['seeds']:
            for a,b in combinations(('G1','G2','G3'),2):
                sa=anchors[(spec,seed,a)];sb=anchors[(spec,seed,b)]
                anchor_equivalence.append({'spec':spec,'seed':seed,'a':a,'b':b,'same_transfer_function_at_1e_6':equiv(sa,sb),
                    'max_abs_log_difference':max(abs(math.log(x/y)) for x,y in zip(sa,sb))})
    put(OUT/'E1_GAUGE_CLIPPING_AND_EQUIVALENCE.json',{'runs':gauges,'anchor_equivalence':anchor_equivalence,
        'not_a_claim_of_equivalent_entire_windows':True})

    plan=[];failure_taxonomy=[]
    for r in results:
        if r['task']!='task3':continue
        folder=OUT/'task3'/r['run_id'];decisions=[]
        for p in (folder/'planner').glob('validation_*.json'):decisions.append(read(p))
        error=r['failure'] or {};reason=error.get('reason','')
        if not error:category='FORMAL_SEARCH_COMPLETED'
        elif error.get('type')=='ProviderError':category='PROVIDER_OR_TRANSPORT_FAILURE'
        elif not r['actual_regions']:
            category='INITIAL_PLANNER_REJECTED_CONTRACT_OR_PHYSICS'
        else:category='EXECUTOR_OR_POST_PLAN_FAILURE'
        failure_taxonomy.append({'run_id':r['run_id'],'category':category,
            'original_umbrella_status':r['status'],'failure_type':error.get('type'),
            'reason':reason,'actual_regions':r['actual_regions'],'M1':r['M1_calls'],
            'API':r['API_calls'],'is_physical_NOT_FOUND':r['status']=='NOT_FOUND',
            'scope':'Rejected proposal is not physical-search NOT_FOUND or automatic Provider failure'})
        plan.append({'run_id':r['run_id'],'spec':r['spec'],'arm':r['arm'],'actual_regions':r['actual_regions'],
            'final_initial_legal':r['proposal_legal'],'raw_validations':decisions,
            'failure':r['failure'],'first_PASS':r['first_PASS'],'M1_to_first':r['M1_to_first_PASS'],
            'first_time_s':r['time_to_first_PASS_s'],'SLSQP_starts':r['SLSQP_starts'],
            'inverse_calls':r['inverse_calls'],'scale_prior_inverse_calls':r['scale_prior_inverse_calls'],
            'API_calls':r['API_calls'],'API_latency_s':r['API_latency_s']})
    put(OUT/'E2_PLANNER_LEGALITY_DETAIL.json',plan)
    put(OUT/'FAILURE_TAXONOMY.json',failure_taxonomy)
    failures=[{'task':r['task'],'run_id':r['run_id'],'status':r['status'],'error':r['failure'],
        'actual_M1':r['M1_calls'],'wall_s':r['total_wall_s'],'right_censored':r['time_censored'],
        'formal_budget_exhausted':r['formal_budget_exhausted'],'solver_failures':r['solver_failures']}
        for r in results if r['status']!='PASS_FOUND' or r['solver_failures']]
    put(OUT/'REPRESENTATIVE_FAILURE_ANALYSIS.json',failures)

    lines=['# 消融实测解释补充','',
        '这是对已保存日志的只读分析，没有新增M1、API或Solver执行。冻结后未修改模型、边界、Prompt、算法或原始实验。',
        '', '## 反解与最大PM角点','',
        '|组|首点命中|首候选PASS|首点M1中位*|首点秒*|构造尝试|真正反解|反解后非法|首点PM中位°*|',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for x in e3:
        r=group('task1',x['arm'])
        lines.append(f"|{x['arm']}|{r['success_count']}/{r['n']}|{r['first_candidate_PASS']}/{r['n']}|{fmt(r['first_M1_median_success_only'])}|{fmt(r['first_time_median_success_only_s'])}|{x['construction_attempts']}|{x['inverse_called']}|{x['invalid_called_inverse']}|{fmt(x['first_PM_median_deg'])}|")
    s0,s1,s2=[group('task1',a) for a in ('S0','S1','S2')]
    lines+=['',f"在本轮固定子域/预算内，无反解S0仍可成功{s0['success_count']}/{s0['n']}，所以反解不是得到M1可行点的逻辑必要条件。一般反解S1与角点优先S2均{s1['success_count']}/{s1['n']}和{s2['success_count']}/{s2['n']}；二者首正式候选PASS差为{s2['first_candidate_PASS']-s1['first_candidate_PASS']}次。这里没有角点提高首点成功率的证据。",
        '', 'S1并非盲目随机六参数：先在合法LF相位区间采样x，再使用同一理想模型关系的原反解数值根精确瞄准BW，并做联合调谐/增益预检。其首候选高通过率主要由这个构造链解释；正式M1是独立调用和判决，却不是独立物理模型。S2极端比例可能获得更大PM裕量、较少无效构造，但也可能落在相同BW边缘或收紧增益/电阻可用域，需同时查看表中成本和裕量。',
        '', f"corner带来的本轮代数调用总差S2−S1={e3[2]['inverse_called']-e3[1]['inverse_called']}，构造尝试差={e3[2]['construction_attempts']-e3[1]['construction_attempts']}。它与首点成功率是不同的贡献。S0的{9-s0['success_count']}次未命中保留128预算及实际删失时间，不给零时间。",
        '', '## 任意尺度的依赖','',
        '|组|首点命中|首点M1中位*|首点秒*|全部提交wall中位秒|',
        '|---|---:|---:|---:|---:|']
    for a in ('G1','G2','G3','G4'):
        r=group('task2',a);lines.append(f"|{a}|{r['success_count']}/{r['n']}|{fmt(r['first_M1_median_success_only'])}|{fmt(r['first_time_median_success_only_s'])}|{fmt(r['all_submission_wall_median_s'])}|")
    clips=sum(any(x['lower_clipped_by_frozen_guard'] or x['upper_clipped_by_frozen_guard'] for x in r['guard_clipping'].values()) for r in gauges)
    lines+=['',f"三gauge的尺度锚点在{sum(r['same_transfer_function_at_1e_6'] for r in anchor_equivalence)}/{len(anchor_equivalence)}对中响应等价（log容差1e-6）。但{clips}/18个有gauge运行的规则窗口至少一轴被共同guard截断，完整窗口未必尺度等价。不同绝对R/C/I不能直接算独立物理设计族。",
        '', 'BW/PM限定LF比值、时间常数和增益组合，不能唯一确定绝对电阻、电容和电流尺度。1000Ω不是从SystemSpec识别出的器件能力；它确实移动初始窗口，因此可靠性应理解为冻结guard内选域启发式的敏感性。G4移除窗口同时扩大实际执行域，单独报告，不能把其差异全部归因于数值gauge。',
        '', '## 初始区域规划的独立作用','',
        '|组|初始合法|首点命中|首点M1中位*|首点秒*|全部提交wall中位秒|API总秒|',
        '|---|---:|---:|---:|---:|---:|---:|']
    for a in ('P0','P1','P2'):
        r=group('task3',a);lines.append(f"|{a}|{r['proposal_legal']}/{r['n']}|{r['success_count']}/{r['n']}|{fmt(r['first_M1_median_success_only'])}|{fmt(r['first_time_median_success_only_s'])}|{fmt(r['all_submission_wall_median_s'])}|{fmt(r['API_latency_s'])}|")
    p0,p1,p2=[group('task3',a) for a in ('P0','P1','P2')]
    lines+=['',f"同等三个区域/同求解器下，P2相对P1首点命中差{p2['success_count']-p1['success_count']}/9；P1相对单宽域P0差{p1['success_count']-p0['success_count']}/9。区域重叠、物理差别、编译C1保留比例和所有原提案另表，不将Controller切片当成LLM自己生成的数字窗口。",
        '', '预算一致不代表实际相同工作量：非法规划可能0M1；物理筛选、反解失败、未能启动优化都具有真实成本。三组全预算路径与首点路径同时保留，API开销纳入端到端首点与全部提交耗时。无需将成功条件中位数当成包含失败的整体速度。',
        '', '## 适用边界与下一步','',
        '建议保留原反解、合法性预检、正式M1和透明Controller账本；corner优先可作低成本启发式，不能据本轮声称成功率必然提高。任意尺度应显式参数化并做guard敏感性检查。LLM是否保留在初始规划主路径，应依据本表增益与API成本，而不是理由文本；优先减少非法提案、错误物理范围和不透明编译收缩。',
        '', '下一轮Solver消融应固定相同候选域/Seed后分别禁用SLSQP、禁用尾Sobol、仅反解，并匹配真实调用上限与代数成本；另预登记合法phase筛选消融，以区分形状先验和数值反解。M1/M2联合验证应在冻结候选上调用现有原生M2 BW/指定条件捕获协议，报告来源差异和UNKNOWN。两者仅建议，本次Task4/5均未实施。',
        '', '*仅成功运行。完整失败、预算用尽、优化未收敛及删失在RUN_METRICS.csv、REPRESENTATIVE_FAILURE_ANALYSIS.json、STRATEGY_COMPARISON.csv。没有做一般优越性显著性结论；三seed及共享确定性构造不等于独立物理问题样本。']
    with (OUT/'MEASURED_INTERPRETATION.md').open('x',encoding='utf-8') as f:f.write('\n'.join(lines)+'\n')
    print(json.dumps({'read_only':True,'E3_groups':len(e3),'gauge_pairs':len(anchor_equivalence),'planner_runs':len(plan),
        'failures_or_solver_issues':len(failures),'new_API_M1_M2':0},ensure_ascii=False))


if __name__=='__main__':main()
