"""Validate saved run evidence and export reproducible, machine-readable acceptance."""
from pathlib import Path
import hashlib
import json
import xml.etree.ElementTree as ET
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from pll_allocation.contracts import digest
from pll_allocation.runner import source_snapshot

def read(path): return json.loads(path.read_text(encoding='utf-8'))
def main():
    suite=ROOT/'outputs/final_behavioral_suite'
    summary=read(suite/'suite_summary.json')
    runs=[]
    required=['input_system_spec.json','block_space_snapshot.json','topology_snapshot.json','initial_joint_block_spec.json',
              'final_joint_block_spec.json','constraint_checks.json','behavioral_tb_results.json','system_metrics.json',
              'allocation_trace.jsonl','run_manifest.json','report.md']
    for row in summary['rows']:
        folder=suite/(row['case']+'__'+row['policy']); manifest=read(folder/'run_manifest.json')
        assert all((folder/name).is_file() for name in required)
        assert manifest['source_sha256']==source_snapshot()
        p=read(folder/'input_system_spec.json'); assert digest(p)==manifest['input_sha256']
        previous='0'*64; evaluations=0
        for line in (folder/'allocation_trace.jsonl').read_text(encoding='utf-8').splitlines():
            event=json.loads(line); sha=event.pop('event_sha256')
            assert digest(event)==sha and event['previous_sha256']==previous; previous=sha
            a=event['attempt']; assert digest(a['candidate'])==a['candidate_sha256']
            evaluations+=a['cost']['behavioral_evaluations']
            if a['evaluation_index'] is not None:
                raw=read(folder/a['artifacts']/'behavioral_result.json')
                cycles=read(folder/a['artifacts']/'cycles.json')
                assert len(cycles)==raw['reference_cycles']==round(p['measurement']['duration_s']*p['operating_context']['fref_Hz'])
                assert raw['candidate_sha256']==a['candidate_sha256']
        assert evaluations==manifest['metrics']['behavioral_evaluations']<=manifest['evaluation_budget']
        assert previous==manifest['trace_head_sha256']
        runs.append({'case':row['case'],'policy':row['policy'],'status':manifest['status'],**manifest['metrics']})
    first=read(suite/'joint84__rule/run_manifest.json'); second=read(ROOT/'outputs/final_repro_joint84/run_manifest.json')
    assert first['decision_sha256']==second['decision_sha256']
    protection=read(ROOT/'docs/audit/source_inventory_after.json')['protection']
    assert not protection['changed_or_missing'] and not protection['new_source_paths']
    xml=ET.parse(ROOT/'docs/validation/tests.xml').getroot()
    suites=list(xml.iter('testsuite'))
    tests={k:sum(int(s.attrib.get(k,0)) for s in suites) for k in ('tests','failures','errors','skipped')}
    llm=[]
    for name in ('p3_live_initial','p3_live_bounded'):
        manifest=read(ROOT/'outputs'/name/'run_manifest.json')
        llm.append({'run':name,'status':manifest['status'],'reason':manifest['reason'],
                    'calls':manifest['llm_calls'],'behavioral_evaluations':manifest['metrics']['behavioral_evaluations']})
    aggregates={}
    for policy in sorted({r['policy'] for r in runs}):
        supported=[r for r in runs if r['policy']==policy and r['status']!='UNSUPPORTED_SYSTEM_SPEC']
        feasible_cases=[r for r in supported if r['case'] in {'regular80','tight80','joint84'}]
        aggregates[policy]={
            'supported_cases':len(supported),
            'first_pass_feasible_rate':sum(r['first_pass_feasible'] for r in supported)/len(supported),
            'success_within_budget_rate':sum(r['success_within_budget'] for r in supported)/len(supported),
            'feasible_case_subset':{'cases':[r['case'] for r in feasible_cases],
                'first_pass_feasible_rate':sum(r['first_pass_feasible'] for r in feasible_cases)/len(feasible_cases),
                'success_within_budget_rate':sum(r['success_within_budget'] for r in feasible_cases)/len(feasible_cases)},
            'total_behavioral_evaluations':sum(r['behavioral_evaluations'] for r in runs if r['policy']==policy),
            'strategy_runtime_s':sum(r['strategy_runtime_s'] for r in runs if r['policy']==policy),
            'evaluation_runtime_s':sum(r['evaluation_runtime_s'] for r in runs if r['policy']==policy),
            'statistical_status':'single fixed suite and random seed; not a general population estimate'}
    result={'stage_status':{'P0':'COMPLETE','P1':'COMPLETE_MINIMAL','P2':'COMPLETE_MINIMAL',
             'P3':'PARTIAL_REAL_LLM_ACCEPTANCE_INCOMPLETE','P4':'DETERMINISTIC_SMOKE_COMPLETE_LLM_COMPARISON_INCOMPLETE',
             'P5':'PARTIAL_DELIVERY_AUDITED'},
            'tests':tests,'run_count':len(runs),'behavioral_evaluations':sum(r['behavioral_evaluations'] for r in runs),
            'runs':runs,'strategy_aggregate_metrics':aggregates,
            'joint84_reproducible_decision_sha256':first['decision_sha256'],
            'old_source_protection':protection,'llm_runs':llm,
            'scope':'DECLARED_BEHAVIORAL_MODEL_ONLY; not transistor or physical qualification'}
    out=ROOT/'docs/validation/acceptance.json';out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# 策略对照报告','', '数据来源：outputs/final_behavioral_suite/suite_summary.json。固定seed=0；每案例/每策略最多30次完整TB，提议最多30次，首次完整候选在TB前保存。',
           '', '|案例|策略|首次通过|到首个可行的评价数|实际TB数|预算内成功|最小归一化裕量|最终状态|', '|---|---|---|---|---|---|---|---|']
    for r in runs:
        margin=r['minimum_normalized_margin']
        lines.append(f'|{r["case"]}|{r["policy"]}|{r["first_pass_feasible"]}|{r["evaluations_to_first_feasible"]}|{r["behavioral_evaluations"]}|{r["success_within_budget"]}|{margin:.6g}|' + r['status']+'|' if margin is not None else f'|{r["case"]}|{r["policy"]}|{r["first_pass_feasible"]}|{r["evaluations_to_first_feasible"]}|{r["behavioral_evaluations"]}|{r["success_within_budget"]}|UNKNOWN|{r["status"]}|')
    lines.extend(['', '## 对照边界', '',
       '规则策略按解析平衡相位、低电流、q0和调谐距离排序；网格按原声明顺序枚举；随机搜索固定seed；反馈基线从初点出发，使用真实违例及解析关系修复。这些均是非LLM策略。解析排序不偷偷运行动态TB，额外行为调用数为0。',
       '', '三组已找到可行解的案例上，规则首次通过3/3；网格/随机/反馈首次通过均0/3；四种方法预算内成功均3/3。这是固定案例与单seed的工程冒烟结果，不是统计可靠的算法排名，也不能说明LLM更好。',
       '', 'finite_domain80的30个声明点全部实际评价仍未通过，只能报告该离散域内未找到；不能证明连续域或真实PLL不可实现。unsupported_jitter80实际执行一次TB后明确停止，噪声模型缺失不能通过调参修复。',
       '', '## LLM验收未完成', '',
       '真实服务模型为deepseek-v4-pro；两次实际HTTP请求均在200响应后超时，未形成候选，行为评价0次。分别保存于outputs/p3_live_initial和outputs/p3_live_bounded。第二次采用60秒进程总期限并实际停止。没有用规则、mock或离线回放填补结果；首次LLM可行率与修复效果为NOT_EXECUTED，不写成0%性能结果。',
       '', '## 成本与指标', '',
       f'正式确定性套件20次运行，共{result["behavioral_evaluations"]}次完整行为评价。逐运行system_metrics.json保存最小裕量、归一化违例、解析预测相对TB误差、策略耗时与TB耗时。只有静态相位有可信解析预测，所以Predicted-vs-Verified只报告该项；动态项不填伪造预测。',
       '', '当前random仅seed=0、LLM没有成功响应；尚需多目标分布、多随机种子、稳定模型版本和重复LLM样本，才能比较First-pass Feasible Rate、评价成本与可行裕量。'])
    (ROOT/'POLICY_COMPARISON_REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'tests':tests,'runs':len(runs),'behavioral_evaluations':result['behavioral_evaluations'],
                      'reproducible':True,'old_sources_changed':len(protection['changed_or_missing']),
                      'llm_acceptance':'INCOMPLETE'},ensure_ascii=False))

if __name__=='__main__':main()
