"""Render factual prose/tables from audited study evidence, without simulation."""
from pathlib import Path
import argparse
import csv
import json
import sys
from collections import Counter

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from pll_allocation.allocation.core import read,write_new


def main():
    p=argparse.ArgumentParser();p.add_argument('--summary',required=True,type=Path);a=p.parse_args()
    summary=read(a.summary/'summary.json')
    with (a.summary/'scenario_results.csv').open(encoding='utf-8-sig') as f:rows=list(csv.DictReader(f))
    first=[r for r in rows if r['phase']=='FIRST_SHOT' and r['scenario_id']!='S4']
    repair=[r for r in rows if r['phase']=='FEEDBACK_REPAIR']
    def write(name,lines):
        with (ROOT/'docs/stage5'/name).open('x',encoding='utf-8') as f:f.write('\n'.join(lines)+'\n')
    lines=['# Strategy comparison — Stage 5','',
        '本轮为冻结五场景、三个配对随机种子的探索性比较。所有首发先完成后才进入反馈修复，不作统计普遍性推断。完整数据见 '+a.summary.as_posix()+'，失败调用和局部后处理错误均保留。','',
        '|Scenario|Strategy|Seed|M1 first-shot|M2 BW (kHz)|BW judgment|Overall|',
        '|---|---|---:|---|---:|---|---|']
    for r in first:
        bw=f'{float(r["BW_M2_Hz"])/1000:.6f}' if r.get('BW_M2_Hz') else '—'
        lines.append(f'|{r["scenario_id"]}|{r["strategy"]}|{r.get("seed") or "—"}|{r["m1_status"]}|{bw}|{r.get("BW_spec_status") or "NOT_EVALUATED"}|{r.get("full_systemspec")}|')
    lines += ['', '解析：4/4首发M1满足，4/4独立M2 BW通过；每场景1次完整M2。首发BW分别225/205/260/295kHz，产生4个不同JointBlockSpec。原求解器枚举离散C、选择峰值lead形状、数值求BW/UGF比，再条件反解R及增益并分配Icp/Kvco与调谐点；不是纯闭式解析。',
        '', 'Random：12/12首发M1失败，12/12测得BW失败；每场景3种子。三组完整参数跨场景配对复用，BW实测约416.781/713.784/326.828kHz，均超各场景上限。无事前M1筛选或随机重抽；所有首次合法且调谐可达，0个因域非法被排除，0个用隐藏解析解替代。M1廉价评价已能识别这些首次无效分配，但实验为保持纯Random对照仍执行M2。',
        '', '真实LLM：S0/S1/S3成功，各3次deepseek-v4-pro调用，均选择 SolveInverseAllocation → EvaluateM1 → SubmitCandidateForM2；候选与对应解析基线完全相同。S2一次HTTP200响应达到1500输出token预算后JSON解析失败，无候选/无M2，记录REAL_LLM_NOT_EXECUTED（allocation未执行），实际失败网络请求及token已计入。S4预检跳过，不算LLM失败。合计10次真实API，9次有效动作、1次解析失败，无自动重试。',
        '', '现有Agent提示词明确要求选择确定性工具、避免自行高精度计算，且四次调用预算优先求解后提交。因此本轮证据仅支持受限工具编排，不是对LLM所有潜在数值设计能力的否定。没有观察到不同候选、额外数值质量、成本优势或真正LLM反馈修复。',
        '', 'S4所有5个arm均先得到INFEASIBLE_UNDER_M1_ASSUMPTIONS：73°超过声明C集合的理想PM上界72.247209838°，0候选/0M2/0LLM。不能外推为真实CPPLL绝对不可行。',
        '', '|Scenario|Seed|Repair action|M1 BW (kHz)|M1 PM (deg)|M2 BW (kHz)|BW status|',
        '|---|---:|---|---:|---:|---:|---|']
    repair_actions=Counter()
    for r in repair:
        meta=read(Path(r['evidence']).parent/'allocation_metadata.json');repair_actions[meta.get('action')]+=1
        lines.append(f'|{r["scenario_id"]}|{r["seed"]}|{meta.get("action")}|{float(r["BW_M1_Hz"])/1000:.6f}|{float(r["PM_M1_deg"]):.6f}|{float(r["BW_M2_Hz"])/1000:.6f}|{r["BW_spec_status"]}|')
    lines += ['',f'12/12真实BW失败生成不同完整候选并各用1次新增M2复验，BW全部改为PASS；每arm到首次受支持BW候选共2次M2，在≤3预算内。修复动作计数：{dict(repair_actions)}。其中S3 seed11 M1 PM=45.661369°低于50°，虽然BW实测PASS，完整联合规格仍未预测可行；正式M2 PM UNKNOWN，不能遮蔽这一预测失败。',
        '', '未知指标未触发强制修复；解析和成功LLM只收到UNKNOWN精度/PM反馈后停止。无新LLM修复算法，不能把上述确定性修复归于LLM或原纯Random首发成功。',
        '', '|Phase|M2 complete calls|Native runs|M1 formal|M1 posthoc|Cheap calls|Process wall sum (s)|',
        '|---|---:|---:|---:|---:|---:|---:|']
    with (a.summary/'run_costs.csv').open(encoding='utf-8-sig') as f:costs=list(csv.DictReader(f))
    for phase in ('FIRST_SHOT','FEEDBACK_REPAIR'):
        group=[r for r in costs if r['phase']==phase]
        val=lambda key:sum(float(r[key] or 0) for r in group)
        lines.append(f'|{phase}|{val("M2_calls"):.0f}|{val("native_completed_runs"):.0f}|{val("M1_calls"):.0f}|{val("M1_posthoc_calls"):.0f}|{val("analytic_calls"):.0f}|{val("process_wall_s"):.3f}|')
    totals=summary['totals']
    lines += ['',f'主策略实验合计{totals["M2_calls"]}次完整M2、{totals["native_completed_runs"]}次native、{totals["integration_points"]:,}积分点；原生{totals["native_elapsed_s"]:.3f}s，Pipeline总{totals["total_elapsed_s"]:.3f}s，子进程总{totals["process_wall_s"]:.3f}s。实际数值反解根工具次数{totals["numerical_inverse_root_calls"]}、有记录SLSQP求解器调用{totals["SLSQP_invocations"]}，详情见run_costs.csv与cost_events。',
        '',f'LLM实际usage：`{json.dumps(summary["LLM_usage"],ensure_ascii=False)}`。input_tokens与cache_read_input_tokens按提供商分别累计，不能只报未缓存输入。无已审计价格配置，API货币成本null，不能误报免费。所有墙钟包含Python、工具、网络、测量及搜索；没有仅报原生积分时间。',
        '', '首次有效BW候选：解析及成功LLM=1次M2；Random首发未找到，接入确定性修复后=2次。S2 LLM未形成候选，无首次成功成本值。所有31次主策略完整M2中BW均获得收敛测量；每次正式3硬指标中2项UNKNOWN，硬指标UNKNOWN率=2/3。UGF为诊断且无周期认证，不加入硬约束分母。完整SystemSpec认证PASS=0。']
    write('STRATEGY_COMPARISON_REPORT.md',lines)
    errors=[abs(float(r['BW_error_percent'])) for r in rows if r.get('BW_error_percent')]
    local=summary['local_evidence']
    lines=['# End-to-end feasibility — Stage 5','',
        '结论：当前正式Pipeline已支持研究场景中不同BW/PM目标的完整分配和独立BW测量。简单固定CPPLL在本轮四个M1预测可行且BW子集通过的场景主要由现有物理解析/数值分配器完成；真实LLM成功案例全部转发同一确定性解。本轮没有完整SystemSpec认证通过，且有一个修复候选保留M1 PM失败。','',
        '## Research Question 1 — Block Space and Physics Mapping','',
        '频率计划固定80MHz；调谐通过Vreq=(80MHz−f0)/Kvco条件反推。BW/PM联合分配使用原连续锁定小信号公式、离散LF形状枚举与标量数值求根，M1 PM上界可先排除S4。频率条件静态一致不证明严格瞬态精度，调谐存在不证明冷启动捕获。',
        '', '四个解析候选M1 BW=225/205/260/295kHz，对应真实M2 BW=226.403934/206.058498/262.123340/296.839212kHz，误差约0.624%/0.516%/0.817%/0.623%。本轮S2误差超过Stage4.1历史有限样本最大0.624%，说明历史最大值不是全域误差界。',
        '',f'全部已测候选的BW绝对相对误差最大{max(errors):.6f}%。本轮31次主实验的BW规格判断未发现M1/M2 PASS↔FAIL反转；S3 BW范围290–300kHz，解析实测包络[296724.106907,296987.195924]Hz仍在范围内。此压力点通过不能证明更贴近边界的目标必然通过，也不能依据结果改选新场景。',
        '', '纯Random的12次首发（3个独特参数点×4场景）均M1预测失败、均M2 BW失败；域合法/数学有效点全部保留，无域拒绝。解析预传播排除不满足目标PM的LF电容形状：S0/S2/S3各排除3/9组合，S1排除6/9，S4排除9/9；这些是必要条件排除次数，不是独立无效电路数量。S4五arm均经预检后未进入M2，实际完整TB调用0。',
        '', '人工声明六轴域足以覆盖S0–S3至少一组满足M1的联合规格，不能宣称为实测器件实现域；S4只证明当前M1及离散C域不支持。Registry的条件解析/数值逆解、capture仅行为、严格PM/频率边界仍成立；本阶段不升级confidence或非理想能力。','',
        '## Research Question 2 — Allocation Strategy and Agent','',
        '在预声明的相同最大3次M2/arm预算中，解析4/4首次BW通过，Random0/12首次通过；后者加入既有确定性修复后12/12第二次BW通过。该比较支持本轮目标导向物理分配比所选均匀采样更有效，不能声称统计普遍优势。三个随机种子跨场景配对，不是12个独立设计点。',
        '', '真实deepseek-v4-pro在S0/S1/S3均求解析解→官方M1→提交，完整参数哈希等同解析基线；S2因JSON失败无候选。实际价值仅观察到工具选择、约束核验及合规提交；没有不同物理解、反馈决策或数值裕量增益，且增加API/墙钟成本。现有prompt及预算偏向这一路径，结论受限于该工具型Agent。',
        '', 'S0–S3都无需新复杂搜索；原求解器本身已包含9种LF形状枚举、数值求根和有界增益分解。多数随机修复因直接缩放越界转向已有SLSQP，这是本轮真正用到多参数有界搜索的场景。没有BO/RL或新LLM修复。','',
        '## Research Question 3 — Behavioral Verification and Feedback','',
        '完整M2独立执行冷启动0.15V/160µs捕获和暖启动四套BW扫频/数值复核；31次均获得可信BW测量，所有31次条件捕获均在窗口内建立。冷捕获与暖小信号不是同一次实验，后者不证明前者。1µHz频率精度、周期PM继续UNKNOWN，局部UGF/PM也不能替代该认证。','',
        '|Scenario|Local Series UGF (kHz)|Local Clamp UGF (kHz)|Series PM (deg)|Clamp PM (deg)|Frequency gate|Step evidence|',
        '|---|---:|---:|---:|---:|---|---|']
    for row in local:
        s,c=row['series'],row['clamp']
        lines.append(f'|{row["scenario"]}|{s.get("UGF_Hz",0)/1000:.6f}|{c.get("UGF_Hz",0)/1000:.6f}|{s.get("PM_deg",0):.6f}|{c.get("PM_deg",0):.6f}|{row["frequency_gate"]["passed"]}|{row["step_status"]}|')
    local_cost=summary['local_phase_cost'];local_runs=sum(j['cost']['native_runs'] for j in local_cost['jobs']);local_native=sum(j['cost']['native_s'] for j in local_cost['jobs'])
    lines += ['',f'预声明两个局部工程套件共{local_runs}次native（含pilot），原生{local_native:.3f}s；S0已完成后出现成本字段汇总异常，保留失败进程，再只跑S3并显式引用S0，没有重复计仿真。频响门和时域收敛支持这两个点的局部映射，不外推到其余候选。小振铃不足识别可靠衰减率时保持UNKNOWN。',
        '', '12个真实BW违规均正确生成结构化FAIL反馈并调用原修复，全部复验BW改善；S3 seed11原低PM在频率缩放下不变，形成BW子集通过但M1 PM仍失败的直接边界案例。说明“测得受支持指标通过”远小于联合完整规格通过，不能用UNKNOWN掩盖预测违例，也不能把M1失败当未经测量的M2 PM FAIL。','',
        '## Required seven answers','',
        '1. 是：独立研究场景合同允许BW min/max、PM min经过同一正式链路，原规格不变。',
        '2. 是：四个解析场景产生不同JointBlockSpec；Random三个种子亦不同，修复产生新完整候选。',
        '3. 解析四组/成功LLM三组BW通过，Random12组首发BW失败，修复12组BW通过；完整认证均未通过。',
        '4. 有：M1识别全部随机首发不满足、反推四个有效解，并用LF PM上界跳过S4；但没有全域M1/M2误差界。',
        '5. 本轮未观察到区别于确定性Solver的数值设计决策；成功Agent仅工具编排与提交，S2服务输出解析失败。',
        '6. 当前等级为独立BW实测与条件捕获/频率观测、有限点局部工程稳定性；正式PM和严格频率UNKNOWN，无法FULL_SYSTEMSPEC_VERIFIED_PASS。',
        '7. 下一阶段优先研究问题3（验证覆盖与可信度），尤其周期PM解释/认证及严格频率不确定度；这是所有策略共用的验收瓶颈。待能力明确，再设计能检验Agent增量、需权衡/搜索的任务。该建议不启动后续阶段。','',
        f'实际主策略总成本见strategy报告；包含局部套件后原生调用合计{totals["native_completed_runs"]+local_runs}，原生时间{totals["native_elapsed_s"]+local_native:.3f}s。开发/兼容Baseline、测试和失败后处理另列总成本账，不冒充策略样本。有限实验不声称一般算法优越性。','',
        '本阶段完成后停止，等待技术Leader审阅；不进入Stage5.1或6。']
    write('END_TO_END_FEASIBILITY_REPORT.md',lines)
    write_new(ROOT/'docs/stage5/RESULT_INDEX.json',{'summary':str(a.summary.resolve()),'candidate_rows':len(rows),
        'totals':totals,'local_native_calls':local_runs,'local_native_s':local_native,'review_status':'PENDING_TECHNICAL_LEADER_REVIEW'})


if __name__=='__main__':main()
