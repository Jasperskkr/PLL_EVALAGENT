"""Read-only A+ analysis: consumes real frozen artifacts, no M1 or API calls."""
from collections import Counter
import argparse
import csv
import hashlib
import json
from pathlib import Path
import statistics
import math

def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def rows(p):return [json.loads(s) for s in Path(p).read_text(encoding='utf-8').splitlines() if s.strip()] if Path(p).exists() else []
def write(p,obj):
    with Path(p).open('x',encoding='utf-8') as f:json.dump(obj,f,indent=2,ensure_ascii=False,allow_nan=False); f.write('\n')
def med(x):return statistics.median(x) if x else None
def fmt(x):return '—' if x is None else f'{x:.3f}' if isinstance(x,float) else str(x)
def csvout(p,data):
    if not data:return
    with p.open('x',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(data[0])); w.writeheader(); w.writerows(data)

def main(root):
    root=root.resolve(); cfg=read(root/'frozen/config.json'); results=[read(root/'runs'/e['run_id']/'result.json') for e in cfg['run_order']]
    aggregate=[]; details=[]; checks=[]; allformal=[]; sourcecounts=Counter(); errors=[]; phase_times=[]; coverage=[]; anomalies=[]
    for r in results:
        folder=root/'runs'/r['run_id']; samples=rows(folder/'all_candidates.jsonl'); formal=[s for s in samples if s['formal_M1_called']]
        raw=[s for p in sorted(folder.glob('window_*/executor/m1_samples.jsonl')) for s in rows(p)]
        formal_raw=[s for s in raw if s['formal_M1_called']]; allformal+=formal
        sourcecounts.update(s['source'] for s in formal)
        check={'run_id':r['run_id'],'ledger_matches':len(formal)==len(formal_raw)==r['total_M1_calls'],
            'phase1_budget_ok':r['phase1_M1_calls']<=128,'phase2_budget_ok':r['phase2_M1_calls']<=128,
            'top8_all_formal':all(s['formal_M1_called'] for s in r['top8_points']),
            'top8_all_pass':all(s['M1_status']=='OK' and s['judgment']['m1_feasibility']=='FEASIBLE' for s in r['top8_points']),
            'top8_margin_ok':all(s['judgment']['minimum_normalized_margin']>=.01 and s['tuning_margin_V']>=.01 for s in r['top8_points']),
            'distance_ok':r['point_diversity_min_rms'] is None or r['point_diversity_min_rms']>=.02,
            'complete_contains_first':not r['top8_complete'] or r['first_pass_in_top8'],
            'M2_zero':r['M2_calls']==0,'source_failure':r['failure']}
        if r['first_pass']:
            f=r['first_pass']; check['first_exact_call']=f['M1_call_index']==r['phase1_M1_calls']
            check['no_late_phase1_formal']=not any(s['phase']=='PHASE1' and s['M1_call_index']>f['M1_call_index'] for s in formal)
        for key,value in check.items():
            if value is False:errors.append({'run_id':r['run_id'],'invariant':key})
        checks.append(check)
        if r['incremental_expansion_wall_s']<0:
            anomalies.append({'run_id':r['run_id'],'field':'incremental_expansion_wall_s',
                'raw_value':r['incremental_expansion_wall_s'],'interpretation':'No Phase2 ran; sub-microsecond negative fallback timer artifact. Derived Phase2 time is null; raw record preserved.'})
        statuses=Counter(s['M1_status'] for s in formal)
        covers={k:max(s['parameters']['values'][k]['value'] for s in r['top8_points'])/min(s['parameters']['values'][k]['value'] for s in r['top8_points']) for k in cfg['hard_numerical_resource_guard']} if r['top8_points'] else {}
        def normalized(k,x):
            a=cfg['hard_numerical_resource_guard'][k]
            return (x-a['min'])/(a['max']-a['min']) if a['scale']=='linear' else math.log(x/a['min'])/math.log(a['max']/a['min'])
        points=[{'id':s['id'],'common_guard_normalized':{k:normalized(k,s['parameters']['values'][k]['value']) for k in cfg['hard_numerical_resource_guard']}} for s in r['top8_points']]
        spans={k:[min(s['common_guard_normalized'][k] for s in points),max(s['common_guard_normalized'][k] for s in points)] for k in cfg['hard_numerical_resource_guard']} if points else {}
        coverage.append({'run_id':r['run_id'],'points':points,'observed_coordinate_spans':spans,
            'pairwise_RMS_distances':r['pairwise_distances'],'coverage_claim':'Only these discrete formally evaluated points; spans do not certify any interior',
            'local_connections':r['local_connectivity']})
        events=rows(folder/'timing_events.jsonl')
        for phase in ('PHASE1','PHASE2_SEARCH','CONNECTIVITY'):
            cs=[c for c in formal if c['phase']==phase]; ts=[t for t in events if t['phase']==phase]
            phase_times.append({'run_id':r['run_id'],'phase':phase,'M1_calls':len(cs),'M1_s':sum(c['M1_wall_s'] or 0 for c in cs),
                **{k+'_inclusive_s':sum(t['inclusive_wall_s'] for t in ts if t['category']==k) for k in ('llm','physics','optimizer','sensitivity','search_tool','setup','planner')}})
        eighth=r['top8_points'][-1] if r['top8_complete'] else None
        details.append({'run_id':r['run_id'],'spec':r['spec'],'policy':r['policy'],'seed':r['seed'],'status':r['status'],
            'first_region_hit':r['first_region_hit'],'first_candidate_pass':r['first_candidate_M1_pass'],
            'M1_to_first':r['M1_to_first_pass'],'first_s':r['time_to_first_pass_s'],'top8_count':r['top8_count'],
            'top8_complete':r['top8_complete'],'to_eight_s':r['time_to_eight_s'],'incremental_to_eight_s':r['incremental_expansion_to_eight_s'],
            'M1_to_eight':eighth['M1_call_index'] if eighth else None,
            'M1_first_to_eight':eighth['M1_call_index']-r['M1_to_first_pass'] if eighth else None,
            'incremental_expansion_wall_s':r['incremental_expansion_wall_s'] if r['first_pass'] else None,
            'phase1_M1':r['phase1_M1_calls'],'phase2_M1':r['phase2_M1_calls'],'total_M1':r['total_M1_calls'],
            'API_calls':r['LLM_API_calls'],'API_latency_s':sum(r['LLM_API_latency_s']),
            'inverse_attempts':r['physics_inverse_attempts'],'SLSQP_calls':r['slsqp_calls'],
            'M1_p50_s':r['M1_evaluation_p50_s'],'M1_p95_s':r['M1_evaluation_p95_s'],
            'physics_s':r['timing']['physics'],'optimizer_inclusive_s':r['timing']['optimizer'],'optimizer_exclusive_s':r['timing']['optimizer_exclusive'],
            'M1_s':r['timing']['M1'],'wall_s':r['timing']['wall'],'min_point_distance_rms':r['point_diversity_min_rms'],
            'connection_edges_pass':sum(c['sampled_connection_pass'] for c in r['local_connectivity']),
            'connection_edges_total':len(r['local_connectivity']),'M1_statuses':json.dumps(statuses),
            'axis_max_min_ratios':json.dumps(covers),'stop_reason':r['stop_reason']})
    for spec in ('SW','SN','ST'):
        for policy in ('P1','P2'):
            group=[r for r in results if r['spec']==spec and r['policy']==policy]; executed=[r for r in group if r['actual_windows']]
            candidate=[r for r in group if r['first_candidate_M1_pass'] is not None]; successes=[r for r in group if r['first_pass']]
            complete=[r for r in group if r['top8_complete']]
            aggregate.append({'spec':spec,'policy':policy,'planned_runs':len(group),'executed_valid_window_runs':len(executed),
                'execution_failures':sum(r['status']=='EXECUTION_FAILED' for r in group),'first_region_hits':sum(r['first_region_hit'] for r in group),
                'first_region_hit_rate_planned':sum(r['first_region_hit'] for r in group)/len(group),
                'first_region_hit_rate_valid_window':sum(r['first_region_hit'] for r in group)/len(executed) if executed else None,
                'first_candidate_passes':sum(bool(r['first_candidate_M1_pass']) for r in group),
                'first_candidate_pass_rate_evaluated':sum(bool(r['first_candidate_M1_pass']) for r in group)/len(candidate) if candidate else None,
                'first_pass_successes':len(successes),'median_first_s':med([r['time_to_first_pass_s'] for r in successes]),
                'median_M1_to_first':med([r['M1_to_first_pass'] for r in successes]),'top8_completions':len(complete),
                'top8_completion_rate':len(complete)/len(group),'median_eight_s':med([r['time_to_eight_s'] for r in complete]),
                'median_incremental_eight_s':med([r['incremental_expansion_to_eight_s'] for r in complete]),
                'median_M1_to_eight':med([r['top8_points'][-1]['M1_call_index'] for r in complete]),
                'median_M1_first_to_eight':med([r['top8_points'][-1]['M1_call_index']-r['M1_to_first_pass'] for r in complete]),
                'total_M1_calls':sum(r['total_M1_calls'] for r in group),'total_API_calls':sum(r['LLM_API_calls'] for r in group),
                'unique_first_points':len({r['first_pass']['parameter_sha256'] for r in successes})})
    csvout(root/'STRATEGY_COMPARISON.csv',aggregate); csvout(root/'RUN_METRICS.csv',details); csvout(root/'PHASE_TIMINGS.csv',phase_times)
    write(root/'POINT_COVERAGE.json',coverage)
    write(root/'INVARIANT_AUDIT.json',{'checks':checks,'violations':errors,'reported_field_anomalies':anomalies,'formal_source_counts':dict(sourcecounts),
        'M1_total':len(allformal),'reference_cost':read(root/'reference_only/summary.json'),'main_execution':read(root/'execution_summary.json')})
    write(root/'STRATEGY_COMPARISON.json',aggregate)
    frozen=read(root/'frozen/source_manifest.json')
    reuse={n:{'absolute_path':str(root.parents[1]/n),'sha256':frozen[n],
        'scope':'unchanged ideal locked M1 / existing inverse, coordinate contracts and search tools; no circuit or M2 claim'} for n in (
        'pll_allocation/physics_mapping/model.py','pll_allocation/allocation/physics.py','pll_allocation/exploration/contracts.py',
        'pll_allocation/exploration/physics_region_builder.py','pll_allocation/agent/subregion_tools.py','tools/stress_open_domain.py')}
    write(root/'REUSE_MANIFEST.json',reuse)
    p1=[r for r in results if r['policy']=='P1']; p2=[r for r in results if r['policy']=='P2']
    lines=['# Experiment A+ 研究报告','',
        '所有18次主实验均使用冻结SW/SN/ST、USER_UNBOUNDED、N=8/fref=10MHz。P1规则与P2真实LLM仅在六轴数值计算窗口决策上不同，后续工具池与调度相同。',
        '',f'实际主实验：{len(allformal)} 次正式M1，{sum(r["LLM_API_calls"] for r in results)} 次真实API；M2=0。执行失败{sum(r["status"]=="EXECUTION_FAILED" for r in results)}次；首PASS成功{sum(bool(r["first_pass"]) for r in results)}/18；核心Top8完成{sum(r["top8_complete"] for r in results)}/18。',
        '', '## 策略对照','', '|Spec|策略|首区域命中/计划|首候选PASS/实际M1运行|首点M1中位数|首点秒中位数|八点完成|八点秒中位数|增量秒中位数|',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for g in aggregate:
        candidate_runs=sum(r['first_candidate_M1_pass'] is not None for r in results if r['spec']==g['spec'] and r['policy']==g['policy'])
        lines.append(f'|{g["spec"]}|{g["policy"]}|{g["first_region_hits"]}/3|{g["first_candidate_passes"]}/{candidate_runs}|{fmt(g["median_M1_to_first"])}|{fmt(g["median_first_s"])}|{g["top8_completions"]}/3|{fmt(g["median_eight_s"])}|{fmt(g["median_incremental_eight_s"])}|')
    lines+=['','## 每次真实运行','', '|运行|状态|首点M1|首点s|八点数|八点s|Phase2 M1|总M1|LLM s|Wall s|', '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for d in details:lines.append(f'|{d["run_id"]}|{d["status"]}|{fmt(d["M1_to_first"])}|{fmt(d["first_s"])}|{d["top8_count"]}|{fmt(d["to_eight_s"])}|{d["phase2_M1"]}|{d["total_M1"]}|{fmt(d["API_latency_s"])}|{fmt(d["wall_s"])}|')
    lines+=['','## 解释与适用边界','',
        f'P1首点成功{sum(bool(r["first_pass"]) for r in p1)}/9，P2 {sum(bool(r["first_pass"]) for r in p2)}/9；P1八点完成{sum(r["top8_complete"] for r in p1)}/9，P2 {sum(r["top8_complete"] for r in p2)}/9。每Spec每策略仅3次，结果为本次固定实验的描述性证据，不能据此建立总体统计优越性。',
        '真实LLM通过已有USER_UNBOUNDED适配器直接提交六个数值区间；不是把PhysicsRegionBuilder数值窗口冒记为LLM自主决定。初始规划后使用固定HIGH_PM_LF_SHAPE与同一搜索池，LLM不选择不同优化器。',
        '两策略共享一次新计算的解析尺度先验，包含原inverse_at_shape导出的未验证尺度锚点。这比仅给文本公式更强；结论限定于该共享工具先验条件。可行性参考是另一份独立新计算证据，保存在reference_only，未传入PlannerState。',
        '本实验显式空bootstrap，Stage7自动初探=0 M1。默认历史入口不变。数值guard由共同拓扑尺度与任意1000Ω基准冻结，不是人指定的六轴用户上下界、器件能力或无界空间证明。',
        '时间起点为每次Trial接收冻结SystemSpec、写submission前的perf_counter，包含共享物理先验、LLM请求、窗口校验、上下文建立、搜索、M1与中途落盘；不含本轮代码实施、测试、离线冻结和隔离参考。time_to_eight记录第八个合格且不同的点完成M1及判决后的回调时刻，原始M1返回时刻另存M1_return_elapsed_s；wall还含之后的连通抽查与导出。',
        'optimizer_inclusive包含其正式M1；optimizer_exclusive扣除了对应M1。physics包含共享尺度反解、Builder及残余Analytical Inverse。search_tool/sensitivity也可能嵌套M1，因此分项inclusive不可直接相加。',
        'Top8是按时间顺序选择、共同guard坐标RMS距离≥.02、全部正式M1通过、归一化最小约束裕量≥.01且调谐余量≥.01V的八点集；核心完成要求包括首PASS。它不是全局最优Top8，也不等于连续区域认证。',
        '局部连通证据只在首点到其余点的规范坐标连线上检查25%/50%/75%三个内部点；全部收费且包含在Phase2。失败和UNKNOWN保留，不证明整条曲线或六维盒可行。独立六轴Min/Max仅作观测覆盖描述。',
        '独立种子控制Sobol/Builder与下游工具；Provider无可控随机种子。规则路径首个边界构造可能跨种子完全相同，unique_first_points在对照CSV中公开。',
        '全部结论仅限原8000频点、理想锁定连续M1的BW/PM与静态调谐；Lock/Jitter未判决，完整系统认证仍为false。',
        f'3次失败均为HTTP200后窗口单位/scale合同拒绝，属于规划输出接口失败，不能记为物理NOT_FOUND或Provider故障。本次没有物理未命中Case。失败result中的未执行Phase2 fallback计时出现{len(anomalies)}个极小负值，原样保留，派生表统一记null；这不影响首点/八点、M1或API时间。',
        '', '## 验收与索引','',f'逐候选/预算/首PASS/裕量/距离审计违反数：{len(errors)}。具体见INVARIANT_AUDIT.json。',
        '冻结配置：frozen/config.json；逐轮状态与真实请求响应：runs/<run>/window_*/；全部候选：all_candidates.jsonl及executor/m1_samples.jsonl；来源与动作：actions.jsonl；计时：timing_events.jsonl；点集/连通：expansion/；18次表：RUN_METRICS.csv；策略表：STRATEGY_COMPARISON.csv。',
        '主命令：python -B -m pll_allocation pipeline --experiment-a-plus freeze/reference/run --out experiments/initial_allocation_a_plus（分别执行，所有命令cwd固定F盘工作区）。',
        '测试、原有工作树保护与最终源码校验见test_evidence/和FINAL_PROTECTION_AUDIT.json。没有新建分支/Worktree，没有Commit/Push，实验结束即停止。','']
    with (root/'FINAL_REPORT.md').open('x',encoding='utf-8') as f:f.write('\n'.join(lines))
    write(root/'ARTIFACT_INDEX.json',{'files':{p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file() and 'tmp' not in p.parts and not any('tmp' in part for part in p.relative_to(root).parts)}})
    print(json.dumps({'runs':len(results),'M1':len(allformal),'invariant_violations':errors,'P1_top8':sum(r['top8_complete'] for r in p1),'P2_top8':sum(r['top8_complete'] for r in p2)}))
    if errors:raise SystemExit(1)

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--root',type=Path,required=True); args=parser.parse_args(); main(args.root)
