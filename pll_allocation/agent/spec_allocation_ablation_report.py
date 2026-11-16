"""Read-only aggregation of frozen Task0-3 ablations; no evaluation or API."""
from collections import Counter
from itertools import combinations
from pathlib import Path
import csv
import math
import statistics as stats
import json
from .experiment_a_plus import read
from .spec_allocation_ablation import equivalent_signature, response, check_freeze
from ..allocation.core import write_new
from ..block_space.contracts import FREE_IDS


def median(values):
    return stats.median(values) if values else None


def percentile(values, fraction):
    if not values:return None
    values=sorted(values);pos=(len(values)-1)*fraction;lo=int(pos);hi=min(lo+1,len(values)-1)
    return values[lo]+(values[hi]-values[lo])*(pos-lo)


def dump_csv(path, rows):
    with path.open('x',encoding='utf-8-sig',newline='') as handle:
        keys=list(dict.fromkeys(k for r in rows for k in r))
        writer=csv.DictWriter(handle,fieldnames=keys);writer.writeheader()
        for r in rows:writer.writerow({k:json.dumps(v,ensure_ascii=False,allow_nan=False) if isinstance(v,(dict,list)) else v for k,v in r.items()})


def report(root):
    cfg=check_freeze(root)
    assert read(root/'TASK3_GATE.json')['accepted']
    runs=[];points=[];geometry=[];equiv=[];usage=[];errors=[];checkpoints=[];spreads=[]
    for task in ('task1','task2','task3'):
        for entry in cfg['matrices'][task]:
            folder=root/task/entry['run_id'];result=read(folder/'result.json');runs.append(result)
            candidates=[json.loads(line) for line in (folder/'all_candidates.jsonl').read_text(encoding='utf-8').splitlines()] if (folder/'all_candidates.jsonl').exists() else []
            for row in candidates:
                if row['formal_M1_called']:
                    points.append({'task':task,'run_id':entry['run_id'],'arm':entry['arm'],'spec':entry['spec'],'seed':entry['seed'],
                        'region_id':row['region_id'],'M1_call':row['global_M1_call_index'],'source':row['source'],
                        'feasible':row['judgment']['m1_feasibility'],'margin':row['judgment']['minimum_normalized_margin'],
                        'M1_wall_s':row['cost']['evaluation_timing']['wall_time_s'],'elapsed_s':row['M1_return_elapsed_s'],
                        'loop_signature':row['loop_signature'],**{k:row['parameters']['values'][k]['value'] for k in FREE_IDS},
                        **{k:row['metrics'].get(k) for k in ('BW_Hz','PM_deg','Vctrl_required_V')}})
            formal=[r for r in candidates if r['formal_M1_called']]
            for checkpoint in (1,8,32,64,128):
                seen=[r for r in formal if r['global_M1_call_index']<=checkpoint]
                checkpoints.append({'task':task,'run_id':entry['run_id'],'checkpoint_M1':checkpoint,
                    'actual_evaluations':len(seen),'checkpoint_reached':len(formal)>=checkpoint,
                    'feasible_count':sum(r['judgment']['m1_feasibility']=='FEASIBLE' for r in seen),
                    'best_margin':max((r['judgment']['minimum_normalized_margin'] for r in seen
                        if r['judgment']['minimum_normalized_margin'] is not None),default=None)})
            feasible=[r for r in formal if r['judgment']['m1_feasibility']=='FEASIBLE']
            for k in FREE_IDS:
                values=[r['parameters']['values'][k]['value'] for r in feasible]
                spreads.append({'task':task,'run_id':entry['run_id'],'axis':k,'feasible_min':min(values,default=None),
                    'feasible_max':max(values,default=None),'span_decades':math.log10(max(values)/min(values)) if values else None,
                    'scope':'observed finite points, not feasible rectangle or independent physical families'})
            if result['failure']:errors.append({'task':task,'run_id':entry['run_id'],**result['failure']})
            for call in result['LLM_calls']:usage.append({'run_id':entry['run_id'],**call})
            regions=result['actual_region_contracts']
            for r in regions:
                geometry.append({'task':task,'run_id':entry['run_id'],'region_id':r['region_id'],
                    'executed_region':r['executed_region'],'global_normalized_bounds':r['global_normalized_bounds'],
                    'global_hypervolume_fraction':math.prod(hi-lo for lo,hi in r['global_normalized_bounds'].values()),
                    'axis_span_decades':{k:math.log10(a['max']/a['min']) for k,a in r['executed_region'].items()}})
    aggregates=[]
    for task in ('task1','task2','task3'):
        for spec in [*cfg['task_definitions'][task]['specs'],'ALL']:
            for arm in cfg['task_definitions'][task]['arms']:
                selected=[r for r in runs if r['task']==task and r['arm']==arm and (r['spec']==spec or spec=='ALL')]
                successful=[r for r in selected if r['first_PASS']]
                aggregates.append({'task':task,'spec':spec,'arm':arm,'n':len(selected),
                    'success_count':len(successful),'success_rate':len(successful)/len(selected),
                    'first_candidate_PASS':sum(r['first_candidate_PASS'] for r in selected),
                    'proposal_legal':sum(bool(r['proposal_legal']) for r in selected),
                    'execution_failures':sum(r['status']=='EXECUTION_FAILURE' for r in selected),
                    'NOT_FOUND':sum(r['status']=='NOT_FOUND' for r in selected),
                    'first_M1_median_success_only':median([r['M1_to_first_PASS'] for r in successful]),
                    'first_time_median_success_only_s':median([r['time_to_first_PASS_s'] for r in successful]),
                    'all_submission_wall_median_s':median([r['total_wall_s'] for r in selected]),
                    'all_submission_wall_total_s':sum(r['total_wall_s'] for r in selected),
                    'actual_M1_total':sum(r['M1_calls'] for r in selected),
                    'success_penalized_effort_mean_at128':stats.mean(r['M1_to_first_PASS'] if r['first_PASS'] else 128 for r in selected),
                    'inverse_calls':sum(r['inverse_calls'] for r in selected),
                    'scale_prior_inverse_calls':sum(r['scale_prior_inverse_calls'] for r in selected),
                    'construction_attempts':sum(r['construction_attempts'] for r in selected),
                    'invalid_inverse_attempts':sum(r['invalid_inverse_attempts'] for r in selected),
                    'SLSQP_starts':sum(r['SLSQP_starts'] for r in selected),
                    'API_calls':sum(r['API_calls'] for r in selected),'API_latency_s':sum(r['API_latency_s'] for r in selected),
                    'best_margin_median_success_only':median([r['best_margin'] for r in successful]),
                    'unique_feasible_total':sum(r['unique_feasible_candidates'] for r in selected),
                    'response_families_1e_6_sum':sum(r['response_families_at_log_tolerance_1e_6'] for r in selected),
                    **{'attained_by_M1_'+str(n):sum(r['first_PASS'] and r['M1_to_first_PASS']<=n for r in selected) for n in (1,8,32,128)},
                    **{'attained_by_s_'+str(n):sum(r['first_PASS'] and r['time_to_first_PASS_s']<=n for r in selected) for n in (1,5,30,60)}})
    overlap=[];compile_changes=[]
    for r in runs:
        for a,b in combinations(r['actual_region_contracts'],2):
            aa=a['global_normalized_bounds'];bb=b['global_normalized_bounds']
            intersection=math.prod(max(0,min(aa[k][1],bb[k][1])-max(aa[k][0],bb[k][0])) for k in FREE_IDS)
            va=math.prod(hi-lo for lo,hi in aa.values());vb=math.prod(hi-lo for lo,hi in bb.values())
            overlap.append({'run_id':r['run_id'],'a':a['region_id'],'b':b['region_id'],
                'intersection_over_smaller':intersection/min(va,vb),'Jaccard':intersection/(va+vb-intersection),
                'scope':'computational boxes, not feasible coverage'})
        folder=root/r['task']/r['run_id']
        for p in folder.glob('*_compiled.json'):
            c=read(p);lo,hi=c['requested_C1_F'];a=c['compiled_region']['C1']
            compile_changes.append({'run_id':r['run_id'],'region_id':c['proposed_region']['region_id'],
                'requested_C1_F':[lo,hi],'compiled_C1_F':[a['min'],a['max']],
                'C1_log_width_retained':math.log(a['max']/a['min'])/math.log(hi/lo),
                'owner':'Controller; not LLM numeric output'})
    for spec in ('SN','ST'):
        for seed in cfg['seeds']:
            choices=[r for r in runs if r['task']=='task2' and r['spec']==spec and r['seed']==seed]
            for a,b in combinations(choices,2):
                fa=root/'task2'/a['run_id']/'first_PASS.json';fb=root/'task2'/b['run_id']/'first_PASS.json'
                ra=read(fa) if fa.exists() else None;rb=read(fb) if fb.exists() else None
                equiv.append({'spec':spec,'seed':seed,'a':a['arm'],'b':b['arm'],
                    'both_first_PASS':bool(ra and rb),
                    'equivalent_first_transfer_function':equivalent_signature(ra['loop_signature'],rb['loop_signature']) if ra and rb else None,
                    'signature_a':ra['loop_signature'] if ra else None,'signature_b':rb['loop_signature'] if rb else None,
                    'scope':'ideal closed/open-loop rational response; static f0/tuning may differ'})
    dump_csv(root/'RUN_METRICS.csv',runs);dump_csv(root/'STRATEGY_COMPARISON.csv',aggregates)
    dump_csv(root/'FORMAL_M1_CANDIDATES.csv',points);dump_csv(root/'REGION_GEOMETRY.csv',geometry)
    dump_csv(root/'REGION_OVERLAP.csv',overlap);dump_csv(root/'COMPILATION_CHANGES.csv',compile_changes)
    dump_csv(root/'SCALE_EQUIVALENCE.csv',equiv);write_new(root/'LLM_API_USAGE.json',{'calls':usage})
    dump_csv(root/'BUDGET_CHECKPOINTS.csv',checkpoints);dump_csv(root/'OBSERVED_PARAMETER_SPANS.csv',spreads)
    timing=[]
    for task in ('task1','task2','task3'):
        for arm in cfg['task_definitions'][task]['arms']:
            selected=[r for r in runs if r['task']==task and r['arm']==arm]
            mt=[p['M1_wall_s'] for p in points if p['task']==task and p['arm']==arm]
            categories=Counter()
            for r in selected:
                for event in r['timings']:categories[event['category']]+=event['inclusive_wall_s']
            timing.append({'task':task,'arm':arm,'M1_count':len(mt),'M1_total_wall_s':sum(mt),
                'M1_p50_s':percentile(mt,.5),'M1_p95_s':percentile(mt,.95),
                'inclusive_categories_s':dict(categories),
                'wall_s':sum(r['total_wall_s'] for r in selected),
                'scope':'categories overlap formal M1; never directly sum categories'})
    write_new(root/'TIMING_SUMMARY.json',{'rows':timing})
    token_fields=Counter()
    for call in usage:
        for key,value in (call.get('usage') or {}).items():
            if isinstance(value,(int,float)):token_fields[key]+=value
    write_new(root/'PROVIDER_COST.json',{'reported_token_fields':dict(token_fields),
        'currency_cost':None,'reason':'No unverified tariff or billing-semantics assumption',
        'actual_call_count':len(usage),'API_wall_s':sum(c['elapsed_s'] for c in usage)})
    write_new(root/'FAILURE_CASES.json',errors)
    write_new(root/'SUMMARY.json',{'aggregates':aggregates,'run_count':len(runs),'M1':sum(r['M1_calls'] for r in runs),
        'API':sum(r['API_calls'] for r in runs),'M2':0,'failures':errors,'scale_equivalence':equiv})
    lines=['# Spec Allocation 消融实验 Task 0–3','',
        '以下为冻结协议内的M1方法学实验。三次固定种子是有限计算重复，不代表一般电路或LLM分布认证。成功、失败、非法提案和删失全部保留。',
        '', '|阶段|策略|首点成功|首点M1中位数*|首点秒*|全部提交wall中位秒|M1总数|最佳裕量中位*|',
        '|---|---|---:|---:|---:|---:|---:|---:|']
    def fmt(x):return '未达到' if x is None else f'{x:.4g}'
    for r in aggregates:
        if r['spec']=='ALL':lines.append(f"|{r['task']}|{r['arm']}|{r['success_count']}/{r['n']}|{fmt(r['first_M1_median_success_only'])}|{fmt(r['first_time_median_success_only_s'])}|{fmt(r['all_submission_wall_median_s'])}|{r['actual_M1_total']}|{fmt(r['best_margin_median_success_only'])}|")
    lines+=['','*仅成功运行计算；全部运行耗时、成功惩罚128调用指标、未命中删失时刻和固定调用/秒阈值命中率在STRATEGY_COMPARISON.csv、RUN_METRICS.csv。非法提案与NOT_FOUND分列；不是将失败时间填零。',
        '', 'Task0记录原流程与任意1000Ω尺度的来源；正式M1/判断/Builder/Explorer/inverse公式不变。Task1子域来自预冻结共同guard坐标[.1,.9]，不使用反解Seed缩域；S0连尺度反解也不调用。S1/S2除首个LF/x选择外共用Sobol序列、合法相位区间和原增益/调谐反解。S2保留当前优先corner，其余draw不增加HIGH_PM半盒偏置，因此是corner优先的定向消融。',
        '', 'Task2全局guard始终相同，100/1000/10000Ω只改变尺度参考和由同一规则产生的初始窗口。G4没有尺度先验直接搜索全域，是尺度窗口存在性的附加对照，不能作纯gauge单因素比较。',
        '', 'Task3 P1/P2各严格三个假设、优先级预算43/43/42，P0总预算128。三者同一反解9槽/63构造尝试、初探24M1、最多三次原六轴SLSQP及尾Sobol。区域几何导致筛选、实际优化调用及预算使用的差异如实记录。没有反馈修复或Top8扩展，也不依正式结果改Prompt。',
        '', '编译后的C1切片/C2角点窗口属于Controller；LLM原始提案及其拒绝原样保留。执行整个compiled_region，Builder式Seed局部盒只作日志，不用于提前缩小其他组域。全局域→提案→编译→执行→反解→M1分别落盘。',
        '', '理想响应用[C2/C1,Rz*C2,Icp*Kvco/(N*(C1+C2))]识别，逐项log差≤1e-6归同一响应簇；f0调谐独立报告。响应簇不是器件设计族，微小数值差也不能证明物理独立性。SCALE_EQUIVALENCE.csv给跨gauge首点配对。',
        '', f"主实验共{len(runs)}次，{sum(r['M1_calls'] for r in runs)}正式M1，{sum(r['API_calls'] for r in runs)}真实API，0M2。测试、Smoke及独立复查另列；各inclusive类别含M1不能相加。",
        '', '## 研究问题的实测回答','']
    def agg(task,arm):return next(r for r in aggregates if r['task']==task and r['arm']==arm and r['spec']=='ALL')
    a,b,c=[agg('task1',arm) for arm in ('S0','S1','S2')]
    lines += [f"- 物理反解是否必要：S0无反解得到{a['success_count']}/{a['n']}首点，S1={b['success_count']}/{b['n']}、S2={c['success_count']}/{c['n']}。反解不是数学上必需的结论不能仅凭有限失败推导；本表显示其在冻结预算内的贡献。",
        f"- 最大PM角点：S1/S2首个正式候选PASS分别{b['first_candidate_PASS']}/{b['n']}、{c['first_candidate_PASS']}/{c['n']}，首点M1中位{fmt(b['first_M1_median_success_only'])}/{fmt(c['first_M1_median_success_only'])}。结合反解尝试/非法比例判断corner节省构造成本还是提高正式命中，不把先筛合法LF等同盲采样。",
        '- 初始尺度可靠性：1000Ω是任意尺度锚点，不能由BW/PM独立识别。三gauge与G4的实际窗口、跨度、命中和尺度等价配对见表；全局域没有随gauge改变。即使成功率相同也不能宣称绝对模块尺度由SystemSpec唯一决定。']
    p0,p1,p2=[agg('task3',arm) for arm in ('P0','P1','P2')]
    lines += [f"- LLM初始选域独立收益：P0/P1/P2首点成功{p0['success_count']}/{p0['n']}、{p1['success_count']}/{p1['n']}、{p2['success_count']}/{p2['n']}；成功首点秒{fmt(p0['first_time_median_success_only_s'])}/{fmt(p1['first_time_median_success_only_s'])}/{fmt(p2['first_time_median_success_only_s'])}。等三个区域控制消除了上轮2vs3差异，但样本量小，结论仅限当前合同与预算，不预设优胜。",
        '- 保留原正式M1独立判决、完整边界/单位合同、原反解和预算账本。对角点优先、尺度参考和区域规划按本轮命中/成本证据选用，不把无认证矩形当作可行域；优先改善提案合法性和Controller编译透明度。',
        '', '## 下一轮建议（本次不实施）','',
        '建议Task4预登记Solver消融：固定相同Seed/区域，分离Sobol-only、inverse-only、SLSQP-only与组合，匹配正式M1总预算、前置代数成本和并行资源；多次独立采样并报告未命中删失。应特别分离S1合法相位筛选与裸LF采样的贡献。',
        '', '建议Task5冻结同一候选集，按既有协议做真实M2 BW与指定条件捕获复核，检验M1→M2偏差和排序一致性；PM及未支持指标按来源保持UNKNOWN，禁止将M1成功直接升级为联合认证。本次M2=0，没有实施Task4/5。',
        '', '完成后停止，无Push、Commit、新分支/Worktree。独立阶段门禁及最终审计见verifier/。']
    with (root/'ablation_summary.md').open('x',encoding='utf-8') as handle:handle.write('\n'.join(lines)+'\n')
    return response('ABLATION_REPORT_COMPLETE',{'main_M1':sum(r['M1_calls'] for r in runs),'main_API':sum(r['API_calls'] for r in runs),'M2':0})
