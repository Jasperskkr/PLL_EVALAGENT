"""Read-only study aggregation; writes new review artifacts, no solver/API calls."""
import argparse
from collections import Counter
import csv
import io
import json
import math
from pathlib import Path
import statistics
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def put(p,x):
    if Path(p).exists():
        if read(p)!=x:raise ValueError('refuse to replace different report artifact: '+str(p))
        return
    with Path(p).open('x',encoding='utf-8') as f:json.dump(x,f,ensure_ascii=False,indent=2,allow_nan=False)
def csv_new(path,rows):
    if not rows:return
    fields=list(dict.fromkeys(k for r in rows for k in r))
    stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
    writer.writerows({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in r.items()} for r in rows)
    data=stream.getvalue().encode('utf-8-sig')
    if path.exists():
        if path.read_bytes()!=data:raise ValueError('refuse to replace different CSV artifact: '+str(path))
    else:
        with path.open('xb') as handle:handle.write(data)
def median(values):
    v=[x for x in values if x is not None];return statistics.median(v) if v else None


def main(root):
    root=Path(root).resolve();results=[read(p) for p in sorted((root/'runs').glob('*/multi_region_result.json'))]
    metrics=[];regions=[];points=[];candidates=[];timings=[];plans=[];edges=[];decisions=[]
    for r in results:
        fields=['run_id','spec','policy','seed','status','stop_reason','initial_decision_legal','initial_region_count','actual_regions',
            'actual_searched_regions','first_region_hit','first_candidate_M1_pass','M1_to_first_pass','phase1_M1_calls','phase2_M1_calls',
            'total_M1_calls','time_to_first_pass_s','time_to_eight_s','incremental_expansion_to_eight_s','incremental_expansion_wall_s',
            'LLM_API_calls','LLM_attempts','LLM_first_decision_latency_s','physics_inverse_attempts','construction_attempts',
            'slsqp_calls','M1_evaluation_p50_s','M1_evaluation_p95_s','top8_count','top8_complete','cross_region_top8_count',
            'point_diversity_min_rms','point_diversity_max_rms','failure']
        row={k:r.get(k) for k in fields};row['LLM_total_latency_s']=sum(r['LLM_API_latency_s'])
        if r['first_pass'] is None:row['incremental_expansion_wall_s']=None
        row['failure_class']=r.get('execution_failure_class')
        row['remaining_hard_M1']=r.get('remaining_hard_M1');row['remaining_useful_search_M1']=r.get('remaining_useful_search_M1')
        row['wall_s']=r['timing']['wall'];row['M1_to_eight']=r['top8_points'][-1]['M1_call_index'] if r['top8_complete'] else None
        row['M1_return_time_to_first_s']=r['first_pass']['M1_return_elapsed_s'] if r['first_pass'] else None
        row['M1_return_time_to_eight_s']=r['top8_points'][-1]['M1_return_elapsed_s'] if r['top8_complete'] else None
        metrics.append(row)
        folder=root/'runs'/r['run_id']
        for obs in r['RegionObservations']:
            regions.append({'run_id':r['run_id'],'spec':r['spec'],'policy':r['policy'],**obs})
        for p in r['top8_points']:points.append({'run_id':r['run_id'],'spec':r['spec'],'policy':r['policy'],**p})
        for line in (folder/'all_candidates.jsonl').read_text(encoding='utf-8').splitlines() if (folder/'all_candidates.jsonl').exists() else []:
            c=json.loads(line);candidates.append({'run_id':r['run_id'],**c})
        for category,value in r['timing'].items():
            if isinstance(value,(int,float)):timings.append({'run_id':r['run_id'],'category':category,'wall_s':value,
                'overlap':'M1 contained in optimizer/sensitivity/search_tool; categories not additive'})
        for plan in r['actual_windows']:plans.append({'run_id':r['run_id'],**plan})
        for edge in r['local_connectivity']:edges.append({'run_id':r['run_id'],'spec':r['spec'],'policy':r['policy'],**edge})
        for val in sorted(folder.glob('**/validation_*.json')):
            data=read(val)
            decisions.append({'run_id':r['run_id'],'path':val.relative_to(root).as_posix(),
                'accepted':data['accepted'],'repair_attempt':data.get('repair_attempt'),'reason':data.get('message')})
    comparison=[]
    for spec in ['SW','SN','ST','ALL']:
        for policy in ['P1','P2']:
            group=[r for r in metrics if r['policy']==policy and (spec=='ALL' or r['spec']==spec)]
            n=len(group);passed=[r for r in group if r['M1_to_first_pass'] is not None];complete=[r for r in group if r['top8_complete']]
            evaluated=[r for r in group if r['first_candidate_M1_pass'] is not None]
            comparison.append({'spec':spec,'policy':policy,'runs':n,'initial_decision_legal':sum(bool(r['initial_decision_legal']) for r in group),
                'First_Region_Hit_Rate':sum(bool(r['first_region_hit']) for r in group)/n,
                'First_Candidate_M1_Pass_Rate_submitted':sum(bool(r['first_candidate_M1_pass']) for r in group)/n,
                'First_Candidate_M1_Pass_Rate_evaluated_only':sum(bool(r['first_candidate_M1_pass']) for r in evaluated)/len(evaluated) if evaluated else None,
                'runs_with_formal_M1':len(evaluated),
                'first_pass_successes':len(passed),'Top8_completions':len(complete),'Top8_Completion_Rate':len(complete)/n,
                'Time_to_First_PASS_median_s_success_only':median([r['time_to_first_pass_s'] for r in passed]),
                'M1_to_First_PASS_median_success_only':median([r['M1_to_first_pass'] for r in passed]),
                'Time_to_Eight_median_s_success_only':median([r['time_to_eight_s'] for r in complete]),
                'M1_to_Eight_median_success_only':median([r['M1_to_eight'] for r in complete]),
                'Incremental_to_Eight_median_s_success_only':median([r['incremental_expansion_to_eight_s'] for r in complete]),
                'LLM_initial_latency_median_s':median([r['LLM_first_decision_latency_s'] for r in group]),
                'LLM_total_latency_median_s':median([r['LLM_total_latency_s'] for r in group]),
                'formal_M1_total':sum(r['total_M1_calls'] for r in group),'execution_failures':sum(r['status']=='EXECUTION_FAILED' for r in group),
                'NOT_FOUND':sum(r['status']=='NOT_FOUND' for r in group)})
    csv_new(root/'RUN_METRICS.csv',metrics);csv_new(root/'STRATEGY_COMPARISON.csv',comparison);put(root/'STRATEGY_COMPARISON.json',comparison)
    csv_new(root/'REGION_EXECUTION.csv',regions);csv_new(root/'ALL_TOP8_POINTS.csv',points)
    csv_new(root/'ALL_CANDIDATES.csv',candidates);csv_new(root/'PHASE_TIMINGS.csv',timings);csv_new(root/'ACTUAL_SUBSPACES.csv',plans)
    csv_new(root/'LOCAL_CONNECTIVITY.csv',edges);csv_new(root/'DECISION_LEGALITY.csv',decisions)
    put(root/'POINT_COVERAGE.json',{'normalization':'COMMON frozen guard: log except f0 linear, RMS Euclidean',
        'distance_threshold':.02,'minimum_normalized_margin':.01,'minimum_tuning_margin_V':.01,
        'coverage':'Only point distances, regional membership and finite samples. No continuous feasible volume or full SystemSpec certification.',
        'runs':[{k:r[k] for k in ('run_id','top8_count','cross_region_top8_count','point_diversity_min_rms','point_diversity_max_rms')} for r in results]})
    legal={'raw_validations':len(decisions),'raw_accepted':sum(d['accepted'] for d in decisions),
        'raw_acceptance_rate':sum(d['accepted'] for d in decisions)/len(decisions) if decisions else None,
        'correction_responses':sum(d['repair_attempt']==1 for d in decisions),
        'initial_final_legal_P2':sum(r['initial_decision_legal'] for r in metrics if r['policy']=='P2')}
    put(root/'DECISION_LEGALITY.json',legal)
    audit=[]
    for r in results:
        planpath=root/'runs'/r['run_id']/'MULTI_REGION_PLAN.json'
        if not planpath.exists():
            rawpath=root/'runs'/r['run_id']/'initial_decision/raw_decision_0.json'
            audit.append({'run_id':r['run_id'],'accepted':False,'failure':r['failure'],
                'raw_proposed_plan':read(rawpath) if rawpath.exists() else None,
                'actual_regions_executed':0,'LLM_claims_are_not_tools_or_evidence':True})
            continue
        plan=read(planpath);obs=r['RegionObservations'][:len(plan['regions'])]
        hashes=[o['seed_hashes'][0] for o in obs if o['seed_hashes']]
        audit.append({'run_id':r['run_id'],'accepted':True,'planned_hypotheses':plan['regions'],'controller_observations':obs,
            'unique_initial_seed_count':len(set(hashes)),'initial_regions_with_actual_M1':sum(o['formal_M1_calls']>0 for o in obs),
            'LLM_scope':'physical hypothesis, geometry intent, priority, tool permissions and budgets' if r['policy']=='P2' else 'deterministic rule',
            'numeric_seed_owner':'original PhysicsRegionBuilder','feedback_actions':r['region_feedback']})
    put(root/'LLM_PHYSICS_CLAIM_AUDIT.json',audit)
    # Point membership is distinct from the region that generated the evidence.
    from pll_allocation.region_explorer.assessment import contains_parameters
    membership=[];spread=[]
    for r in results:
        problem=read(root/'frozen'/(r['spec']+'.json'))
        plans=r['actual_windows']
        for point in r['top8_points']:
            membership.append({'run_id':r['run_id'],'point_id':point['id'],'origin_region_index':point['window'],
                'contained_in_actual_search_regions':[p['region_id'] for p in plans if contains_parameters(problem,p['actual_normalized_bounds'],point['parameters'])],
                'scope':'Point membership only; overlap of envelopes is not feasible volume'})
        from pll_allocation.region_explorer.assessment import normalized_point
        coords=[normalized_point(problem,p['parameters']) for p in r['top8_points']]
        if coords:
            for axis in problem['parameters']:
                values=[p[axis] for p in coords]
                spread.append({'run_id':r['run_id'],'axis':axis,'point_count':len(values),
                    'normalized_point_min':min(values),'normalized_point_max':max(values),
                    'normalized_point_span':max(values)-min(values),
                    'scope':'Observed point spread only; enclosing interval not certified feasible'})
    put(root/'POINT_REGION_MEMBERSHIP.json',membership);csv_new(root/'OBSERVED_POINT_SPREAD.csv',spread)
    import numpy as np
    timing_summary=[]
    for policy in ('P1','P2'):
        for spec in ('SW','SN','ST','ALL'):
            latency=[c['M1_wall_s'] for c in candidates if c['formal_M1_called'] and c['M1_wall_s'] is not None and
                f'_{policy}_' in c['run_id'] and (spec=='ALL' or c['run_id'].startswith(spec+'_'))]
            timing_summary.append({'policy':policy,'spec':spec,'M1_calls':len(latency),
                'M1_wall_total_s':sum(latency),'M1_p50_s':float(np.percentile(latency,50)) if latency else None,
                'M1_p95_s':float(np.percentile(latency,95)) if latency else None})
    put(root/'M1_TIMING_SUMMARY.json',timing_summary)
    usage=[{'run_id':r['run_id'],**m} for r in results for m in r['LLM_metadata']]
    put(root/'LLM_API_USAGE.json',{'calls':usage,'real_network_calls':sum(bool(m.get('real_network_call')) for m in usage),
        'total_latency_s':sum(m.get('elapsed_s',0) for m in usage),'currency_cost':None,
        'currency_note':'No verified provider tariff applied; usage and actual latency retained'})
    allrow={r['policy']:r for r in comparison if r['spec']=='ALL'}
    lines=['# Stage 7–8 窗口修复与多物理区域研究','',
        'Phase 0 先通过独立/集成回归，A+ 三条单位或尺度失败重放接受。重放为零新 API/零 M1；物理非法仍拒绝。',
        '','正式研究使用原 SW/SN/ST、USER_UNBOUNDED、三个固定种子、原硬 guard/Builder/反解/SLSQP/M1。A+ 保持为 SINGLE_WINDOW 历史基线。',
        '','|Spec|策略|首点|八点|首点中位秒*|八点中位秒*|首点 M1*|八点 M1*|',
        '|---|---|---:|---:|---:|---:|---:|---:|']
    def f(x):return '—' if x is None else f'{x:.4f}'
    for r in comparison:
        lines.append(f"|{r['spec']}|{r['policy']}|{r['first_pass_successes']}/{r['runs']}|{r['Top8_completions']}/{r['runs']}|{f(r['Time_to_First_PASS_median_s_success_only'])}|{f(r['Time_to_Eight_median_s_success_only'])}|{f(r['M1_to_First_PASS_median_success_only'])}|{f(r['M1_to_Eight_median_success_only'])}|")
    lines.extend(['','*时间与调用中位数仅对成功运行计算；失败单列 RUN_METRICS，不用成功均值掩盖拒绝。',
        '','计时起点是每轮 submission 写盘前的 perf_counter；含适配、规划、真实 API、构造、正式 M1 和执行开销，不含开发、回归、人工授权等待。',
        '首点/八点时间取 Controller 实际收录时间，并提供 M1 返回时间。八点时间不包含之后的 STOP API 和连接抽查；总 wall 计入。',
        'LLM 总延迟、首次决策延迟、Physics、Optimizer、M1 p50/p95 在 CSV 中分别列出。优化/敏感度/搜索耗时包含 M1，不能直接相加。',
        '',f"实际主研究：{sum(r['total_M1_calls'] for r in results)} 次正式 M1，{sum(r['LLM_API_calls'] for r in results)} 次真实 API，0 M2。",
        f"连接证据：{len(edges)} 条边，{sum(e['sampled_connection_pass'] for e in edges)} 条三内部样本全 PASS。未测段仍未知。",'',
        'LLM 的自主输出是多个物理意图及反馈动作；六参数 Seed 和最终局部数值盒由原 Builder 计算。不得把工具数值称为 LLM 自主设计。',
        '多区域真实搜索、候选差异、物理假设及各轮反馈/执行对照见 LLM_PHYSICS_CLAIM_AUDIT.json。',
        '', '这是一轮三种规格、每策略三次的受控小样本研究。跨 SINGLE_WINDOW 与 MULTI_REGION 的变化同时包含接口修复和规划合同变化，不能单独归因于单位修复。',
        '八点是具有指定裕量和参数距离的离散正式 M1 PASS；参数 Min/Max、盒体重叠和连接抽查均不证明整个区域可行。',
        '', '代码修改前后 Diff、冻结源码、原始 PlannerState/Response、标准化与校验、每候选来源和预算都已保存。未改物理模型；未创建分支/Worktree、未 Commit/Push。研究结束后停止。'])
    p2=[r for r in results if r['policy']=='P2'];accepted=[r for r in p2 if r['initial_decision_legal']]
    active=sum(any(x['actual_tools_executed'] for x in r['region_feedback']) for r in accepted)
    conclusions=['','## 研究结论','',
        f"P2 初始计划合法 {len(accepted)}/{len(p2)}；实际发生反馈后工具动作的运行 {active}。格式与物理合法性分别由原始校验记录核查。"]
    if not accepted:
        conclusions.extend(['本轮未形成可执行的真实 LLM 多区域计划，因此没有验证 LLM 多假设搜索和基于 M1 反馈选区的能力。接口回归通过并不等于物理规划通过。',
            'P2 零 M1 的拒绝不能解释为调用效率优势，也不能解释为模型不可行。主研究只能得出当前提示/合同下的规划合法性失败；不支持 LLM 与规则在合法区域内搜索效率的因果比较。'])
    else:
        conclusions.append(f"真实 LLM 已对 {len(accepted)} 次合法计划运行原物理工具；其实际区域、Seed、调用、裕量和反馈动作均可核查。LLM 的物理描述本身不作为正确性或工具执行证据。")
        conclusions.append('本轮结果用于判断当前合同下的成功率与实际成本；只有三次重复，不足以宣称普遍优于规则。失败运行与成功运行应合并阅读。')
    conclusions.extend(['原始 P2 失败按具体物理范围、耦合、证据、格式、Provider 或执行错误分类，见 RUN_METRICS.csv 与 DECISION_LEGALITY.csv。',
        '初始 LF 意图由 Controller 编译成满足比例关系的有限计算子域；实际编译收缩与 LLM 原意图分别记录。编译冲突不是整个耦合空间不可行的证明。',
        '部分运行在预留连接成本或低于24次最小反馈动作预算时停止；remaining_hard_M1 与 remaining_useful_search_M1 单列，不能一概称为用尽硬预算。',
        '不追加调参补跑，不放宽规格/物理守卫，不进入 M2 反馈或新算法阶段。'])
    lines.extend(conclusions)
    (root/'FINAL_REPORT.md').open('x',encoding='utf-8').write('\n'.join(lines)+'\n')
    print(json.dumps({'runs':len(results),'M1':sum(r['total_M1_calls'] for r in results),'API':sum(r['LLM_API_calls'] for r in results),'legal':legal},ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',required=True);main(parser.parse_args().out)
