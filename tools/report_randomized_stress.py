"""Read-only analysis of real randomized stress artifacts, no solver/API calls."""
from collections import Counter
import argparse
import csv
import json
from pathlib import Path

from tools.randomized_stress import read,all_usage,AXES
from pll_allocation.agent.candidates import rank


def jsonl(p):return [json.loads(s) for s in p.read_text(encoding='utf-8').splitlines() if s.strip()] if p.exists() else []


def rel(p,root):
    try:return Path(p).relative_to(root).as_posix()
    except ValueError:return str(p)


def decisions(case):
    out=[]
    for p in sorted(case.rglob('proposal_*.json')):
        if not p.parent.name.startswith('round_'):continue
        raw=read(p);rejection=p.parent/('validation_error_'+p.stem.split('_')[-1]+'.json')
        accepted=p.parent/'search_decision.json'
        out.append({'path':str(p),'raw':raw,'accepted':not rejection.exists() and accepted.exists(),
            'rejection':read(rejection) if rejection.exists() else None,
            'execution_decision':read(accepted) if not rejection.exists() and accepted.exists() else None})
    return out


def violations(obs):
    margins=[c['margin']/c['spec']['normalization_scale'] for c in obs['constraints']
        if c['spec']['enabled'] and c['metric'] in ('BW_Hz','lock_time_s') and c['margin'] is not None]
    return min(margins,default=None)


def analyze_case(root,entry,phase='formal'):
    case=root/phase/entry['case_id'];p=case/'case_result.json'
    if not p.exists():return {'case_id':entry['case_id'],'classification':'NOT_EXECUTED','domain_mode':entry['domain_mode'],
        'evidence_path':str(case),'no_result_reason':'global safety stop or not yet executed'}
    result=read(p);m2=[];handoffs=[];contexts=[];solver=[];stage9_results=[];calibration_samples=[];initial_results=[]
    for w in result['windows']:
        d=Path(w['path']);h=d/'stage8/stage9_handoff.json'
        if (d/'stage8/result.json').exists():initial_results.append(read(d/'stage8/result.json'))
        if h.exists():handoffs.append((h,read(h)))
        c=d/'stage8_calibration/initial_context/physics_context.json'
        if c.exists():
            contexts.append((c,read(c)))
            calibration_samples+=jsonl(c.parent/'m1_samples.jsonl')
        if w.get('stage9_path'):
            folder=Path(w['stage9_path'])
            stage9_results.append(read(folder/'stage9_final_result.json'))
            for p2 in sorted(folder.glob('verification_*_request.json')):
                req=read(p2);num=p2.stem.split('_')[1];o=folder/f'm2_{num}/execution_result.json'
                if o.exists():m2.append({'request':req,'observation':read(o),'path':str(o)})
        sources=[d/'stage8']+(sorted(Path(w['stage9_path']).glob('reallocation_*')) if w.get('stage9_path') else [])
        for source in sources:
            for r in source.glob('round_*/region_observation.json'):
                for o in read(r).get('observations',[]):
                    for s in o.get('solver_runs',[]):
                        # Real continuous numerical solves have a seed_id and
                        # solver convergence/iteration record, not mere tool evals.
                        if s.get('solver')=='scipy.optimize.SLSQP':solver.append({'path':str(r),'record':s})
    ds=decisions(case);initial=next((h['recommended_nominal'] for _,h in handoffs if h['ready_for_stage9']),None)
    supported=[x for x in m2 if x['observation']['supported_metrics_status']=='PASS']
    # Report actual best-known recommendations; never attach another point's M2.
    known=[s['best_known_M1'] for s in stage9_results if s.get('best_known_M1')]
    known += [h['recommended_nominal'] for _,h in handoffs if h['ready_for_stage9']]
    passes=[s['recommended_M2_supported'] for s in stage9_results if s.get('recommended_M2_supported')]
    final=min(passes or known,key=rank,default=None)
    chosen=next((x for x in reversed(m2) if final and x['request']['candidate_sha256']==final['parameter_sha256']),None)
    measurements=chosen['observation'] if chosen else None
    user=read(case/'input_user_spec_and_domain.json');specs={s['metric']:s for s in user['specs']}
    checks={c['metric']:c for c in measurements['constraints']} if measurements else {}
    fe=next((c for c in final['judgment']['constraints'] if c['metric']=='PM_deg'),None) if final else None
    first_failure=next((x for x in m2 if x['observation']['overall_status']=='FAIL'),None)
    improvements=[]
    for a,b in zip(m2,m2[1:]):
        va,vb=violations(a['observation']),violations(b['observation'])
        known_a={c['metric'] for c in a['observation']['constraints'] if c['margin'] is not None and c['metric'] in ('BW_Hz','lock_time_s')}
        known_b={c['metric'] for c in b['observation']['constraints'] if c['margin'] is not None and c['metric'] in ('BW_Hz','lock_time_s')}
        comparable=bool(known_a) and known_a==known_b
        improvements.append({'from':a['observation']['observation_id'],'to':b['observation']['observation_id'],
            'same_problem':a['request']['problem_sha256']==b['request']['problem_sha256'],
            'different_candidate':a['request']['candidate_sha256']!=b['request']['candidate_sha256'],
            'previous_min_normalized_margin':va,'new_min_normalized_margin':vb,
            'comparable_measured_metrics':sorted(known_a) if comparable else [],
            'improved':vb>va+1e-6 if comparable and va is not None and vb is not None else None})
    core={'case_id':entry['case_id'],'spec_id':entry['spec_id'],'domain_id':entry['domain_id'],
        'domain_mode':entry['domain_mode'],'classification':result['classification'],'failure':result['failure'],
        'SystemSpec':user['specs'],'user_bounds':user['domain'].get('parameters'),
        'actual_windows':[read(Path(w['path'])/'domain_provenance.json') for w in result['windows']],
        'initial_M1_feasible':initial is not None,'initial_candidate':initial,'final_recommended':final,
        'final_M1_metrics':final['metrics'] if final else None,'final_M2':measurements,
        'last_measured_candidate':m2[-1]['request']['handoff']['recommended_nominal'] if m2 else None,
        'last_M2':m2[-1]['observation'] if m2 else None,'final_candidate_M2_measured':chosen is not None,
        'M1_PM_status':('PASS' if fe and fe['status']=='SATISFIED' else 'FAIL' if fe and fe['status']=='VIOLATED' else 'NOT_EVALUATED'),
        'M2_PM_status':'M2_PM_UNKNOWN' if measurements else 'NOT_EVALUATED',
        'M2_verifications':m2,'reallocation_count':sum(1 for x in improvements if x['different_candidate']),
        'M2_FAIL_seen':first_failure is not None,
        'first_M2_failed_constraints':[c['metric'] for c in first_failure['observation']['constraints'] if c['status']=='FAIL'] if first_failure else [],
        'real_feedback_reallocation':any(x['different_candidate'] and a['observation']['overall_status']=='FAIL'
            for x,a in zip(improvements,m2)),'stage9_results':stage9_results,
        'improvements':improvements,'decisions':ds,'solver_records':solver,
        'cost':result['cost'],'wall_time_s':result['wall_time_s'],'stage_execution':result['windows'],
        'feedback_search_runs':result['reallocations'],
        'initial_controller_status':[s['status'] for s in initial_results],
        'M1_physics_certificate_stop':any(s['status']=='PROVEN_M1_INFEASIBLE' for s in initial_results),
        'stage7_source_counts':dict(Counter(s['origin'].split(':')[0] for s in calibration_samples)),
        'stage7_failed_constraints':dict(Counter(c['metric'] for s in calibration_samples
            for c in (s.get('judgment') or {}).get('constraints',[]) if c['status']=='VIOLATED')),
        'stage7_screen_reasons':dict(Counter(s['reason'] for s in calibration_samples if not s.get('formal_M1_called'))),
        'evidence_path':str(case),'FULL_SYSTEMSPEC_CERTIFIED':False,
        'Stage7_formal_calls':sum(c['summary']['formal_M1_calls'] for _,c in contexts),
        'Stage7_feasible_samples':sum(c['summary']['M1_feasible_sample_count'] for _,c in contexts),
        'stage7_context_paths':[str(p) for p,c in contexts]}
    core['flat']={'case_id':entry['case_id'],'spec_id':entry['spec_id'],'domain_id':entry['domain_id'],
        'domain_mode':entry['domain_mode'],'BW_min_Hz':specs['BW_Hz']['min'],'BW_max_Hz':specs['BW_Hz']['max'],
        'PM_min_deg':specs['PM_deg']['min'],'Lock_max_s':specs['lock_time_s']['max']}
    for k in AXES:
        u=user['domain'].get('parameters',{}).get(k,{})
        core['flat'].update({k+'_unit':PARAM_UNIT[k],k+'_user_min':u.get('min'),k+'_user_max':u.get('max'),
            k+'_initial_value':initial['parameters']['values'][k]['value'] if initial else None,
            k+'_final_value':final['parameters']['values'][k]['value'] if final else None})
        for j,w in enumerate(core['actual_windows'],1):
            core['flat'][k+f'_window{j}_min']=w['computational_window'][k]['min'];core['flat'][k+f'_window{j}_max']=w['computational_window'][k]['max']
    core['flat'].update(initial_M1_feasible=initial is not None,
        final_M1_BW_Hz=final['metrics']['BW_Hz'] if final else None,final_M1_PM_deg=final['metrics']['PM_deg'] if final else None,
        final_M1_BW_status=next((c['status'] for c in final['judgment']['constraints'] if c['metric']=='BW_Hz'),None) if final else None,
        final_M1_PM_status=core['M1_PM_status'],final_M2_BW_Hz=checks.get('BW_Hz',{}).get('value'),
        final_M2_BW_status=checks.get('BW_Hz',{}).get('status','NOT_EVALUATED'),
        final_M2_Lock_s=checks.get('lock_time_s',{}).get('value'),final_M2_Lock_status=checks.get('lock_time_s',{}).get('status','NOT_EVALUATED'),
        final_M2_PM_status=core['M2_PM_status'],M2_verifications=len(m2),reallocations=core['reallocation_count'],
        final_candidate_M2_measured=chosen is not None,
        last_measured_M2_BW_Hz=m2[-1]['observation']['metrics']['BW_Hz']['value'] if m2 else None,
        last_measured_M2_Lock_s=m2[-1]['observation']['metrics']['lock_time_s']['value'] if m2 else None,
        LLM_requests=result['cost']['LLM_requests'],M1_calls=result['cost']['M1_calls'],wall_time_s=result['wall_time_s'],
        termination=result['classification'],raw_termination=';'.join(str(w.get('stage9_status') or w['initial_status']) for w in result['windows']),
        initial_controller_status=';'.join(core['initial_controller_status']),
        M1_physics_certificate_stop=core['M1_physics_certificate_stop'],
        stage9_termination_reason=';'.join(s['termination_reason'] for s in stage9_results),
        stage9_m1_status=';'.join(s['m1_allocation_status'] for s in stage9_results),
        stage9_supported_m2_status=';'.join(s['supported_M2_status'] for s in stage9_results),
        stage9_feedback_status=';'.join(s['feedback_loop_status'] for s in stage9_results),
        evidence_path=str(case))
    return core


PARAM_UNIT={'Icp':'A','Rz':'Ohm','C1':'F','C2':'F','f0':'Hz','Kvco':'Hz/V'}


def study(root,cases):
    candidates=[c for c in cases if c.get('real_feedback_reallocation')]
    if not candidates:candidates=[c for c in cases if c.get('M2_verifications')]
    if not candidates:return '# Detailed Agent Case Study\n\nNo case reached real M2; no fictional trace supplied.\n'
    chosen=max(candidates,key=lambda c:(len(c['M2_verifications']),len({d['raw'].get('action') for d in c['decisions'] if d['accepted']}),len(c['decisions'])))
    case=Path(chosen['evidence_path']);lines=['# Detailed Agent Case Study — '+chosen['case_id'],
        'Selection rule: most real M2 rounds, then diversity of accepted actions, then proposal count; success not used for selection.',
        '## Original problem','```json',json.dumps(read(case/'input_user_spec_and_domain.json'),ensure_ascii=False,indent=2),'```',
        'Original fixed ideal integer-N 10MHz×8, rails0..1.2V, protocol track_b_metrics_1.1. Budgets in budget_config.json.',
        'Initial and feedback budgets:','```json',json.dumps(read(root/'budget_config.json'),indent=2),'```',
        '## Stage7 fresh exploration',f"Formal smallSobol calls={chosen['Stage7_formal_calls']}, feasible sample count={chosen['Stage7_feasible_samples']}. No old Handoff used.",
        'Observed source/failure counts: '+json.dumps({k:chosen[k] for k in ('stage7_source_counts','stage7_failed_constraints','stage7_screen_reasons')}),
        'Saved contexts: '+', '.join(rel(p,root) for p in chosen['stage7_context_paths']),
        'The LLM receives original Spec/domain, actual smallSobol samples, original physics relations, exact normalized seeds, costs and capability limits. No hidden reasoning reconstructed.']
    lines+=['## Chronological decisions and observations']
    for w in chosen['stage_execution']:
        wd=Path(w['path']);lines+=['### Window '+str(w['window']),'```json',json.dumps(read(wd/'domain_provenance.json'),ensure_ascii=False,indent=2),'```']
        directories=[wd/'stage8']
        if w.get('stage9_path'):directories+=sorted(Path(w['stage9_path']).glob('reallocation_*'))
        for directory in directories:
            lines+=['#### '+rel(directory,root)]
            if (directory/'external_feedback.json').exists():
                fb=read(directory/'external_feedback.json')
                if fb:
                    compact_feedback={'problem_sha256':fb.get('problem_sha256'),
                        'historical_failure_ids':fb.get('historical_failure_ids'),
                        'observations':[{'evidence_id':x['evidence_id'],'candidate_sha256':x['candidate_sha256'],
                            'parameters':{k:x['parameters']['values'][k] for k in AXES},
                            'failed_constraints':x.get('failed_constraints'),
                            'measurements':{k:v for k,v in x['measurements'].items() if k in ('M1','M2','constraints',
                                'M2_status','supported_metrics_status','execution_status','remaining_budgets','measurement_validity')}}
                            for x in fb.get('observations',[])]}
                    lines+=['Actual M2 FeedbackSummary supplied to LLM (full file: '+rel(directory/'external_feedback.json',root)+'):','```json',json.dumps(compact_feedback,ensure_ascii=False,indent=2),'```']
            for d in [q for q in chosen['decisions'] if Path(q['path']).is_relative_to(directory)]:
                lines+=['Provider proposal '+rel(d['path'],root),
                    'Raw actual structured decision/reason (no retrospective rewrite):','```json',json.dumps(d['raw'],ensure_ascii=False,indent=2),'```',
                    'Controller: '+('ACCEPTED' if d['accepted'] else 'REJECTED: '+json.dumps(d['rejection'],ensure_ascii=False))]
                parent=Path(d['path']).parent;raw=parent/('llm_call_'+Path(d['path']).stem.split('_')[-1])
                lines+=['Raw request/response: '+rel(raw,root)+'; PlannerState: '+rel(parent/('planner_state_'+Path(d['path']).stem.split('_')[-1]+'.json'),root)]
                obs=parent/'region_observation.json'
                if d['accepted'] and obs.exists():
                    o=read(obs)
                    compact={'execution_decisions':o.get('execution_decisions'),
                        'observations':[{k:v for k,v in item.items() if k in ('observation_id','decision_id','action',
                            'status','normalized_bounds','physical_bounds','active_variables','new_candidates',
                            'original_minimum_normalized_margin','latest_minimum_normalized_margin',
                            'best_evidence_id','new_candidate_summaries','new_positive_evidence_ids',
                            'new_negative_evidence_ids','failures_and_unknowns','budget_exhausted',
                            'solver_runs','cost','failure')}
                            for item in o.get('observations',[])]}
                    lines+=['Actual tool execution/M1; complete records: '+rel(obs,root),'```json',json.dumps(compact,ensure_ascii=False,indent=2),'```']
    lines+=['## Candidate and real M2 round table',
        '|Round|Candidate six-axis SI|M1 BW / PM|Real M2 BW / Lock|Failures|Change and direction|',
        '|---|---|---|---|---|---|']
    previous=None
    for i,item in enumerate(chosen['M2_verifications'],1):
        req,o=item['request'],item['observation'];values={k:req['parameters']['values'][k]['value'] for k in AXES}
        delta={k:values[k]-previous[k] for k in AXES} if previous else None
        failed=[c['metric'] for c in o['constraints'] if c['status']=='FAIL']
        lines.append(f"|{i}|{json.dumps(values)}|{req['M1_metrics'].get('BW_Hz')} / {req['M1_metrics'].get('PM_deg')}|{o['metrics']['BW_Hz']['value']} / {o['metrics']['lock_time_s']['value']}|{failed}|{json.dumps(delta)}|")
        previous=values
    lines+=['## Actual progress and stop','```json',json.dumps(chosen['improvements'],indent=2),'```',
        'Termination: '+chosen['classification']+'. See raw per-window termination in allocation_summary.json. M2 PM remains UNKNOWN.',
        '## Compact end-to-end trace',
        '|Round|LLM input / feedback|Decision and real tool|BlockSpec change|M1 result|M2 result|',
        '|---|---|---|---|---|---|']
    previous=None
    for i,item in enumerate(chosen['M2_verifications'],1):
        req,o=item['request'],item['observation'];v={k:req['parameters']['values'][k]['value'] for k in AXES}
        producer=None
        for w in chosen['stage_execution']:
            for h in [Path(w['path'])/'stage8/stage9_handoff.json',*sorted(Path(w['stage9_path']).glob('reallocation_*/stage9_handoff.json'))] if w.get('stage9_path') else []:
                if h.exists():
                    nominal=read(h).get('recommended_nominal')
                    if nominal and nominal['parameter_sha256']==req['candidate_sha256']:producer=h.parent
        dd=[d for d in chosen['decisions'] if d['accepted'] and producer and Path(d['path']).is_relative_to(producer)]
        actions='; '.join(str(d['raw'].get('action'))+':'+str((d['raw'].get('request') or {}).get('strategy','')) for d in dd)
        delta={k:v[k]-previous[k] for k in AXES} if previous else 'initial'
        failed=[c['metric'] for c in o['constraints'] if c['status']=='FAIL']
        input_desc='current Spec/domain + fresh Sobol + relations' if i==1 else 'actual previous M2 FeedbackSummary + history + remaining budgets'
        lines.append(f"|{i}|{input_desc}|{actions or 'explicit verification/reverification; see request'}|{json.dumps(delta)}|BW={req['M1_metrics'].get('BW_Hz')}, PM={req['M1_metrics'].get('PM_deg')}|BW={o['metrics']['BW_Hz']['value']}, Lock={o['metrics']['lock_time_s']['value']}; {o['supported_metrics_status']}; failures={failed}|")
        previous=v
    lines += [
        'All case evidence: '+rel(case,root)]
    return markdown(lines)


def markdown(lines):
    """Keep table rows contiguous while separating prose and code blocks."""
    out=[]
    for i,line in enumerate(lines):
        if i and not (line.startswith('|') and lines[i-1].startswith('|')):out.append('')
        out.append(line)
    return '\n'.join(out)+'\n'


def research_answers(cases,stats):
    full=[c for c in cases if c.get('cost')]
    observed=[o for c in full for o in c['M2_verifications']]
    bw_unknown=sum(not o['observation']['metrics']['BW_Hz']['valid'] for o in observed)
    supported_unknown=sum(o['observation']['supported_metrics_status']=='UNKNOWN' for o in observed)
    fail=sum(o['observation']['supported_metrics_status']=='FAIL' for o in observed)
    completed=sum(o['observation']['execution_status']=='COMPLETED' for o in observed)
    feedback_after_fail=[]
    for c in full:
        fail_ids={o['observation']['evidence_id'] for o in c['M2_verifications'] if o['observation']['overall_status']=='FAIL'}
        if any(s.get('feedback_evidence_id') in fail_ids for r in c['stage9_results'] for s in r['searches']):feedback_after_fail.append(c['case_id'])
    opened=[c for c in full if c['domain_mode']=='USER_UNBOUNDED'];finite=[c for c in full if c['domain_mode']!='USER_UNBOUNDED']
    kinds=stats['all_M2_fail_types']
    initial_tries=sum(any('reallocation_' not in d['path'] for d in c['decisions']) for c in full)
    section=['# 随机 Stage 7–9 实验：研究问题逐项回答',
        '本节只统计冻结后的正式矩阵；Pilot 另计成本。PASS 指 M2 BW/指定条件 Lock Time 与 M1 PM 的分来源组合，不是完整 M2 认证。',
        f"1. **执行覆盖（真实证据）**：完成 {stats['executed']}/18 个案例；{stats['reached_M2']} 个到达 M2，{len(observed)} 次 M2 请求中 {completed} 次产生完整执行记录。其余可能在输入、物理证书或 M1 搜索处结束，逐案原因见汇总表。{initial_tries} 个案例发生初始分配 LLM 调用。",
        f"2. **M1 可行（真实证据）**：{stats['M1_feasible']} 个案例产生 READY 的当前问题 M1 候选。{len(stats['physics_certificate_cases'])} 个案例至少有一个窗口被既有物理证书拒绝：{stats['physics_certificate_cases']}。这些有限域证书和预算内未找到分别保留，不据此推断开放域无解。",
        f"3. **支持指标（真实证据）**：{stats['supported_pass']} 个案例最终支持指标 PASS；全部 {len(observed)} 次 M2 观察中 FAIL={fail}、UNKNOWN={supported_unknown}。M2 PM 始终 UNKNOWN。",
        f"4. **FAIL 后重分配（真实证据）**：{len(feedback_after_fail)} 个案例在 FAIL 后实际调用反馈搜索：{feedback_after_fail}；{stats['real_FAIL_reallocated_cases']} 个产生不同候选并完成真实 M2 复验。两种覆盖率分开统计，提出动作不等于产生新分配。",
        f"5. **修复效果（数值事实）**：有真实新候选复验的 FAIL 案例中，{stats['improved_reallocated_cases']} 个至少一次改善，{stats['not_improved_reallocated_cases']} 个没有可比较的实质改善。比较只在同一问题、相同已测指标集合上按最小归一化裕量进行；若只有 Lock 可测，则仅代表 Lock 改善，不能称整体修复成功。各轮差值见 allocation_summary.json 的 improvements。",
        f"6. **失败类型与策略（真实证据/覆盖限制）**：所有 M2 观察的违例组合为 {kinds}。公开 reason、物理工具 request 和后续实测保存在详细案例及各 PlannerState。未出现的 BW-only、Lock-only 或同时 FAIL 类型不能据此声称已验证区分能力。",
        f"7. **无效决策（真实证据）**：正式分配共 {stats['proposal_count']} 份结构化提议，{stats['rejected_proposals']} 份被拒绝；接受动作分布 {stats['accepted_actions']}。拒绝记录保留原始响应和逐项原因，未静默改换区域。开放域窗口提议单列于 USER_UNBOUNDED_ANALYSIS.md，不混入此数。",
        f"8. **停止（真实证据）**：终态分布 {stats['status_counts']}。终止原因、M1 状态、求解器状态、反馈状态分别保存；无候选、物理必要条件不满足、测量 UNKNOWN、LLM 错误与预算耗尽均不自动变为物理 FAIL。有限预算终止不构成有解/无解证明。",
        '9. **开放域能力（真实证据/限制）**：'+json.dumps({'open_cases':len(opened),'open_M1_ready':sum(c['initial_M1_feasible'] for c in opened),
            'open_supported_pass':sum(c['classification']=='SUPPORTED_METRICS_PASS' for c in opened),
            'open_windows':sum(len(c['actual_windows']) for c in opened),'open_LLM_requests':sum(c['cost']['LLM_requests'] for c in opened),
            'open_M1_calls':sum(c['cost']['M1_calls'] for c in opened),'finite_cases':len(finite),
            'finite_LLM_requests':sum(c['cost']['LLM_requests'] for c in finite),'finite_M1_calls':sum(c['cost']['M1_calls'] for c in finite)},ensure_ascii=False)+
            '。开放域由真实 LLM 选择显式有限计算窗口，另付窗口 API 成本；绝对尺度采用公开任意 1 kΩ gauge 与 ±3 decade 资源 guard。可能错过窗口外的解；没有无限域覆盖结论。',
        '10. **总成本（真实证据）**：正式矩阵 '+json.dumps(stats['formal_only_cost'],ensure_ascii=False)+
            '；含 Pilot '+json.dumps(stats['total_research_cost_including_pilots'],ensure_ascii=False)+
            f"。正式案例 wall time 合计 {sum(c['wall_time_s'] for c in full):.3f} s。原生积分子运行数不同于完整 M2 验证次数。Provider 未返回货币费用，monetary_cost=null，不按未知计价估算费用。",
        f"11. **瓶颈（研究者推断）**：{bw_unknown}/{len(observed)} 次 M2 请求没有有效 BW；{stats['rejected_proposals']}/{stats['proposal_count']} 份分配提议被合同拒绝。已证有限域受限案例不能归咎于初探不够。应结合这些失效率与真实反馈是否产生可测新候选判断，不能把 M1 可行直接视为 M2 成功。",
        '12. **下一步优先项（研究者建议，尚未实施）**：优先审查 Stage 9 的反馈证据使用与候选选择：把测量有效性、数值适用域、已失败候选和未测候选的关系传递清楚，减少无效/重复工具尝试；其次按拒绝日志改善结构化决策合同使用。依据是本次 M2 未知/失败和提议拒绝的实际记录。此建议不包含修改 M1/M2 判决阈值，也未在本轮开发新优化器。',
        '## 具体剩余问题（真实证据）',
        'C_USER_UNBOUNDED 的三个 M1 可行点全部在原生积分前被数值适用域拒绝，保持 M2 UNKNOWN。第二窗口确实引用了真实 M2 证据，说明 Pilot 的 ID 注册修复生效；但 C1 下界恰好比资源 guard 少 1 ULP（相对约1.98e-16），触发严格拒绝。这是剩余的序列化边界鲁棒性问题，不是实质物理越界。冻结后未修复/重跑。正式三组开放域只执行了各自首窗口，尚无成功执行的扩窗证据。',
        'B_USER_UNBOUNDED 中公开理由把 lower f0 解释为 reduced Vctrl，在固定正 Kvco 下与 Vreq=(N*fref-f0)/Kvco 相反。后续候选实测 PASS 不替这个理由背书。逐轮原文和公式核对见 PHYSICS_CLAIM_AUDIT.md；完整独立审计见 verifier/VERIFIER_FINDINGS.md。',
        '## 尚未验证',
        '只有一次预注册的分层随机抽样，不能估计所有任意问题上的成功概率，不能证明 LLM 胜过非 LLM 路径，也不保证有限预算内发现存在的解。局部导数和 LLM 的 reason 仅是局部证据/搜索假设。模型不具备噪声/PDK/晶体管级认证；Lock 仅限固定初值和捕获窗口。原始失败、UNKNOWN 和 Pilot 均保留。']
    return markdown(section)


def main(root):
    root=Path(root).resolve();manifest=read(root/'experiment_manifest.json')
    cases=[analyze_case(root,e) for e in manifest['case_matrix']]
    # Reports are derived data and may be regenerated; immutable raw evidence is never rewritten.
    (root/'allocation_summary.json').write_text(json.dumps(cases,ensure_ascii=False,indent=2),encoding='utf-8')
    rows=[c.get('flat',{'case_id':c['case_id'],'termination':c['classification'],'evidence_path':c['evidence_path']}) for c in cases]
    fields=list(dict.fromkeys(k for c in rows for k in c))
    with (root/'allocation_summary.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    lines=['# Allocation summary — all18 preregistered cases',
        'M1/M2 final metrics always refer to the same candidate. Units: BW Hz, PM deg, Lock s. M2 PM UNKNOWN where executed.',
        'Recommendation rule: use saved supported-M2 recommendation when present; otherwise retain best-known M1 nominal using the existing CandidateArchive rank. This fallback is NOT a verified M2 recommendation. Its M2 is shown only if the exact parameter SHA was measured; the separate last_measured_* CSV/JSON fields retain later failed/unknown trial results.',
        'M1_NOT_FOUND is the driver grouping; initial_controller_status/M1_physics_certificate_stop distinguish proven necessary-condition exclusions from search failure. Independent stage9_* status fields preserve feasibility, termination and feedback separately.',
        '|Case|Status|M1 BW / PM|M2 BW / Lock|M2 count / reallocations|API / M1|',
        '|---|---|---|---|---|---|']
    for c in rows:
        lines.append(f"|{c['case_id']}|{c['termination']}|{c.get('final_M1_BW_Hz')} / {c.get('final_M1_PM_deg')}|{c.get('final_M2_BW_Hz')} / {c.get('final_M2_Lock_s')}|{c.get('M2_verifications',0)} / {c.get('reallocations',0)}|{c.get('LLM_requests',0)} / {c.get('M1_calls',0)}|")
    (root/'allocation_summary.md').write_text(markdown(lines),encoding='utf-8')
    (root/'DETAILED_AGENT_CASE_STUDY.md').write_text(study(root,cases),encoding='utf-8')
    full=[c for c in cases if c.get('cost')];statuses=Counter(c['classification'] for c in cases)
    stage9=[c for c in full if c['M2_verifications']];repaired=[c for c in full if c['real_feedback_reallocation']]
    stats={'cases':18,'executed':len(full),'reached_M2':len(stage9),'M1_feasible':sum(c['initial_M1_feasible'] for c in full),
        'supported_pass':statuses['SUPPORTED_METRICS_PASS'],'real_FAIL_reallocated_cases':len(repaired),
        'improved_reallocated_cases':sum(any(p['improved'] for p in c['improvements']) for c in repaired),
        'not_improved_reallocated_cases':sum(not any(p['improved'] for p in c['improvements']) for c in repaired),
        'status_counts':dict(statuses),'proposal_count':sum(len(c['decisions']) for c in full),
        'rejected_proposals':sum(not d['accepted'] for c in full for d in c['decisions']),
        'accepted_actions':dict(Counter(d['raw']['action'] for c in full for d in c['decisions'] if d['accepted'])),
        'initial_M2_fail_types':dict(Counter('+'.join(c['first_M2_failed_constraints']) or 'NONE' for c in stage9)),
        'all_M2_fail_types':dict(Counter('+'.join(x['metric'] for x in o['observation']['constraints'] if x['status']=='FAIL') or 'NO_FAIL'
            for c in stage9 for o in c['M2_verifications'])),
        'M2_attempts':sum(len(c['M2_verifications']) for c in full),
        'M2_completed_observations':sum(o['observation']['execution_status']=='COMPLETED' for c in full for o in c['M2_verifications']),
        'physics_certificate_cases':[c['case_id'] for c in full if c['M1_physics_certificate_stop']],
        'no_initial_LLM_cases':[c['case_id'] for c in full if not any('reallocation_' not in d['path'] for d in c['decisions'])],
        'SLSQP_started':sum(s['record'].get('started',False) for c in full for s in c['solver_records']),
        'SLSQP_converged':sum(s['record'].get('status')=='CONVERGED' for c in full for s in c['solver_records']),
        'SLSQP_budget_skipped':sum(s['record'].get('status')=='SKIPPED_BUDGET' for c in full for s in c['solver_records']),
        'feedback_search_runs':sum(c['feedback_search_runs'] for c in full),
        'total_research_cost_including_pilots':all_usage(root),
        'formal_only_cost':all_usage(root/'formal'),'pilot_only_cost':all_usage(root/'pilots')}
    (root/'STRESS_STATISTICS.json').write_text(json.dumps(stats,indent=2),encoding='utf-8')
    answers=research_answers(cases,stats)
    (root/'FINAL_RESEARCH_REPORT.md').write_text(answers,encoding='utf-8')
    open_cases=[c for c in full if c['domain_mode']=='USER_UNBOUNDED']
    open_lines=['# USER_UNBOUNDED analysis',
        'The user supplied NO min/max. Initial finite windows were proposed by a real separate input-window LLM, not copied Wide/Narrow.',
        'Original inverse relations expose a1000Ohm arbitrary impedance scale gauge and the current BW/PM-derived LF shape. Absolute scale is underdetermined; the numerical +/-3decade guard is explicit and is NOT a physical/user global bound.',
        'The window LLM sees gain product/Icp-Kvco coupling, PM ceiling, Vreq tuning and native resolution restrictions. Its raw judgment/reason is in window_plan_*/. The original allocation Prompt is unchanged.',
        'A second window can expand/switch only after real observations, sharing all per-case budgets. New domain -> new problem/context; no old PASS reused.',
        '## Actual cases']
    for c in open_cases:
        directory=Path(c['evidence_path']);plans=[]
        for p in sorted(directory.glob('window_plan_*/raw_window_decision.json')):
            state=read(p.parent/'planner_state.json')
            plans.append({'path':rel(p,root),'decision':read(p),
                'validation':read(p.parent/'controller_validation.json'),
                'actual_observation_supplied':state['actual_observation'] is not None,
                'registered_observation_evidence':state.get('observation_evidence_catalog',[])})
        open_lines+=['### '+c['case_id'],'```json',json.dumps({'status':c['classification'],'windows':c['actual_windows'],
            'window_plans':plans,'cost':c['cost']},ensure_ascii=False,indent=2),'```']
    open_lines+=['## Ten explicit scope questions',
        '1. Start: current SystemSpec, fixed10MHz×8/rails, original inverse-derived scale anchors, then a real window-selection API; no candidate is claimed before formal M1.',
        '2. Hidden bounds: no copied Narrow/Wide. There IS an explicit finite resource guard (anchors×1e-3..1e3; f0 positive below target). The arbitrary1kOhm gauge constrains computational coverage and is not a physical global limit.',
        '3. Window source: all six intervals are real LLM proposal values, preserved above with controller acceptance/rejection. The tool supplies anchor relations, not final intervals.',
        '4. Physical judgments: quote the actual reason/request above. Those texts are hypotheses; M1/M2 observations, not fluent explanations, decide validity.',
        '5. Icp/Kvco: original inverse_at_shape derives one gain product at chosen BW/LF shape. Its split is underdetermined; actual intervals allow LLM/tools to explore that split and tuning compatibility.',
        '6. LF/tuning: original q=1+C2/C1, phase_ceiling, inverse_gain and Vreq relations are supplied. No reliable M1 lock-time map is introduced. Native timestep/resolution restrictions are supplied separately and actual UNKNOWN is preserved.',
        '7. Expansion: inspect round2 action and validation above. A proposal counts as expansion only if accepted and executed; rejected proposals/STOP are explicit. No case was forced to expand after supported PASS.',
        '8. Basis: second-window state contains actual first-window allocation, native observations and remaining budgets. The registered M2 IDs include source path/candidate SHA. No old experiment evidence substitutes for these results.',
        '9. Missed solutions: possible. Neither the window nor the numerical resource guard is complete; finite Sobol/LLM/SLSQP cannot prove absence outside evaluated points.',
        '10. Achieved capability: explicit LLM-chosen first-window exploration, original M1/tools/native M2, actual feedback and stop/error evidence. This formal matrix executed no accepted second window; its only second-window proposal was rejected. Successful window expansion is NOT demonstrated by these results. This is a pilot for open user input, not infinite-domain optimization.',
        '## Remaining formal window-interface failure',
        'C_USER_UNBOUNDED round2 references all three real M2 IDs correctly, so evidence registration works. Its C1.min=1.591549430918953e-14F is one ULP below guard.min=1.5915494309189532e-14F, triggering strict rejection. This numerical serialization fragility is retained without tolerance waiver/rerun; it is not evidence of meaningful physical-domain violation. Window1 still retains three M1 candidates and three M2 EXCEPTION/UNKNOWN observations. See verifier/VERIFIER_FINDINGS.md.',
        '## Preserved pilot failure',
        'Pilot B_USER_UNBOUNDED round2 cited a real M2 evidence ID omitted from the original window allowlist; that rejection remains on disk. The generic registration fix preceded formal source freeze. The pilot reason also said lower q raises PM headroom, contradicting the supplied phase_ceiling relation; no prompt was retuned to conceal or correct that response.',
        '## Limitations',
        'Only finite windows were evaluated. Solutions may exist outside them or outside the resource guard. Failed search cannot certify open-domain infeasibility. Window selection is genuine LLM input adaptation, not a proof of global coverage; the1000Ohm gauge is a declared engineering assumption.',
        'Finite-vs-open comparisons are descriptive: finite cases supply user domains, open cases spend additionalAPI and may split initial resources across windows. No causal superiority claim.']
    (root/'USER_UNBOUNDED_ANALYSIS.md').write_text(markdown(open_lines),encoding='utf-8')
    stability=['# Agent stability / research results','## Actual execution facts','```json',json.dumps(stats,indent=2),'```',
        'All18 preregistered cases remain in the table including no-candidate, certificate, invalid decisions, unsupported measurement and failed repairs.',
        '## Failure-specific planning evidence']
    for c in repaired:
        stability+=['### '+c['case_id']+' — first failed constraints: '+str(c['first_M2_failed_constraints'])]
        for d in c['decisions']:
            if 'reallocation_' in d['path']:
                stability.append(json.dumps({'path':rel(d['path'],root),'accepted':d['accepted'],'action':d['raw'].get('action'),
                    'reason':d['raw'].get('reason'),'request':d['raw'].get('request'),'rejection':d['rejection']},ensure_ascii=False))
    stability+=['## Evidence boundaries and interpretation',
        'Numbers above are real persisted measurements/Provider activity. Numerical margin differences are computed facts; they are not a proof of globally monotone physics. Differences in planning quality and any proposed bottleneck are researcher inferences, not hidden model reasoning.',
        'This is one randomized draw per stratum/domain, with pilots separate. No claim that LLM outperforms deterministic search or that infinite domains have been covered. M2 PM remains UNKNOWN; supported BW/lock and M1 PM are separate evidence levels.',
        'Inspect actual rejected decisions, no-candidate distribution and per-stage costs before choosing next work. No algorithm was tuned on these results.']
    (root/'AGENT_STABILITY_REPORT.md').write_text(markdown(stability)+'\n'+answers,encoding='utf-8')
    print(json.dumps({k:v for k,v in stats.items() if not k.endswith('cost')},ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args();main(a.out)
