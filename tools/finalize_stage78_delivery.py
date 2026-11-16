"""Read-only delivery synthesis; never evaluates a candidate or calls a provider."""
from pathlib import Path
import json
from collections import Counter

ROOT=Path(__file__).resolve().parents[1]
ONE=ROOT/'experiments/stage7_8_multiregion_20261113_01'
TWO=ROOT/'experiments/stage7_8_multiregion_20261113_02'


def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def put(path,value):
    with path.open('x',encoding='utf-8') as handle:json.dump(value,handle,ensure_ascii=False,indent=2,allow_nan=False)


def main():
    rows=[read(p) for p in sorted((TWO/'runs').glob('*/multi_region_result.json'))]
    one=read(ONE/'execution_summary.json');two=read(TWO/'execution_summary.json')
    receipt1=read(ONE/'verifier/MAIN_EXECUTION_RECEIPT.json');receipt2=read(TWO/'verifier/MAIN_EXECUTION_RECEIPT.json')
    usage=read(TWO/'LLM_API_USAGE.json');margins=read(TWO/'CONSTRAINT_MARGIN_SUMMARY.json')
    semantics=read(TWO/'PHYSICAL_INTENT_AND_FEEDBACK_AUDIT_v3.json')
    all_feedback=[(r['run_id'],f) for r in semantics['runs'] if r['policy']=='P2' for f in r['feedback']]
    feedback_counts=Counter(f['action'] for _,f in all_feedback)
    tokens={k:sum((c.get('usage') or {}).get(k,0) for c in usage['calls']) for k in
        ('input_tokens','cache_creation_input_tokens','cache_read_input_tokens','output_tokens')}
    cost={'main_batches':[
        {'name':'01 conservative full-envelope compiler','runs':18,'M1':one['main_M1_calls'],'API':one['main_LLM_API_calls'],
         'inner_wall_s':one['wall_s'],'outer_cli_s':receipt1['outer_cli_wall_s'],'P2_core_feedback_exercised':False},
        {'name':'02 contained coupled-intent compiler','runs':18,'M1':two['main_M1_calls'],'API':two['main_LLM_API_calls'],
         'inner_wall_s':two['wall_s'],'outer_cli_s':receipt2['outer_cli_wall_s'],'P2_core_feedback_exercised':True}],
        'new_main_total':{'runs':36,'M1':one['main_M1_calls']+two['main_M1_calls'],
            'API':one['main_LLM_API_calls']+two['main_LLM_API_calls'],
            'inner_wall_s':one['wall_s']+two['wall_s'],'outer_cli_s':receipt1['outer_cli_wall_s']+receipt2['outer_cli_wall_s']},
        'v2_provider':{'requests':20,'HTTP_failures':0,'latency_s':usage['total_latency_s'],'tokens_as_reported':tokens,
            'currency_cost':None,'token_semantics':'Provider-reported fields retained separately; no unverified tariff or token billing assumption'},
        'known_separate_verification':{'v1_smokes_M1':320,'v2_smoke_M1':111,
            'v1_test_attributed_formal_M1':1917,'v2_prefreeze_test_attributed_formal_M1':192,
            'note':'Test ledger flags do not cover direct unit evaluate calls. See verifier final ledgers; never pooled into main success/cost.'},
        'historical_A_plus':{'M1':955,'API':9,'status':'separate original SINGLE_WINDOW baseline; excluded from new main total'},
        'M2_in_main':0,'clock_scope':'Runtime per submission; development, human authorization waiting and regression are separately recorded'}
    put(TWO/'CROSS_ROUND_COST_SUMMARY.json',cost)
    validation={'P2_initial_plans_legal':6,'P2_initial_submissions':9,'all_raw_decisions':20,
        'all_raw_accepted':15,'structured_correction_calls':1,'provider_failures':0,
        'initial_rejected_physics':3,'post_first_feedback_schema_failure':1,
        'raw_legality_fraction':.75,'accepted_feedback_action_counts':dict(feedback_counts),
        'feedback_actual_search_actions':sum(f['actual_tools_executed'] for _,f in all_feedback),
        'early_STOP_actual_counts':[{ 'run_id':name,'top8_count':f['actual_prior_top8_count'],
            'remaining_search_M1':f['actual_prior_available_M1'],'reason':f['reason']}
            for name,f in all_feedback if f['action']=='STOP'],
        'interpretation':'Count real Controller actions. LLM claims about sufficiency/optimizer are not performance evidence.'}
    put(TWO/'ACCEPTANCE_SUMMARY.json',validation)
    lines=['# Stage 7–8 最终交付','',
        '窗口接口修复、多物理区域真实规划与 M1 反馈链路均已执行验证。第二轮18次已全部完成，结果不支持真实LLM优于确定性物理规则的效率结论。没有补跑失败、放宽Spec或修改M1/M2模型；本任务到此停止。',
        '', '|第二轮策略|初始合法|首个M1 PASS|八点完成|首点中位时间*|首点M1*|八点中位时间*|八点M1*|',
        '|---|---:|---:|---:|---:|---:|---:|---:|',
        '|P1 确定性物理规则|9/9|9/9|5/9|0.1465秒|1|4.0880秒|83|',
        '|P2 真实LLM|6/9|6/9|0/9|17.5789秒|1|未达到|未达到|',
        '', '*时间及调用中位数仅对成功运行计算。P2有一条找到首点后反馈格式失败，该首点仍计入首点成功。初始拒绝未执行M1，首候选PASS率按已执行运行计算为P1 9/9、P2 6/6；按全部提交计算为9/9、6/9。',
        '', '|Spec|P1首点/八点|P2首点/八点|P1首点中位秒*|P2首点中位秒*|P2最终点数（种子1301/2603/3907）|',
        '|---|---|---|---:|---:|---|',
        '|SW 180–410kHz / PM≥50°|3/3、3/3|2/3、0/3|0.1465|17.2486|4 / 0 / 7|',
        '|SN 260–330kHz / PM≥60°|3/3、2/3|1/3、0/3|0.1459|16.7723|4 / 0 / 0|',
        '|ST 290–300kHz / PM≥70°|3/3、0/3|3/3、0/3|0.1480|18.8802|5 / 3 / 3|',
        '', 'N=8、fref=10MHz，六参数均USER_UNBOUNDED，数值guard沿用A+并标明任意尺度资源边界，不能称为用户约束或电路能力。Lock Time/M2与Jitter不参与正式M1判定。',
        '', 'Phase 0：A+三条HTTP200后接口失败被旧合同准确复现，新适配层接受等价ohm/Ohm与Controller固定scale，六个数值区间不变。SI前缀换算、紧耦合/guard/非有限/Evidence拒绝、旧格式兼容、一次结构纠错上限及修正轮状态哈希都有回归。原Response、标准化、差异、校验和执行参数分开存档。',
        '', '第一轮01的18次结果完整保留：943M1/9API，P2初始合法0/9。事后只读复核发现27个意图中24个被保守全C1包络角点矩形编译排空，而非实际C2硬guard冲突。02采用通用包含切片编译：在合法耦合意图内部选有限C1子间隔，并保持全部比例角点和guard；原意图/实际切片/收缩程度明确归Controller。这个修正没有改Builder、Explorer或物理公式。',
        '', '第二轮P2优先两个仔细核查的假设，P1固定三个；合同对两者允许2–3、工具池和硬预算相同。这是策略处理差异，不是相同区域数量的配对比较。LLM与物理规则都使用原Builder、原反解、SLSQP、Sensitivity、Sobol和正式8000点M1。',
        '', '真实多区域证据：六个合法P2初始计划各搜索两个区域，初始Seed哈希跨区域不同；Controller生成的实际构造域和局部盒分别保存。六次实际后续搜索包括五次CONTINUE_REGION和一次EXPLORE_ANOTHER；没有发生REFINE_REGION，不能把未执行分支称为真实验证。',
        '', '可核查示例：SN_P2_1301的第一假设选低电压调谐、C2/C1=14–21与较小C1；第二假设选内侧调谐、比例16–29及另一增益/绝对尺度。两区真实M1后，LLM引用OBS证据探索第三个较低Kvco、上侧BW目标区域，并真实构造/搜索；下一轮再选第二个区域继续。原始决策和实际执行均在runs/SN_P2_1301/。',
        '', '执行审计发现LLM理由有时声称将运行SLSQP，而选中区域的许可工具未包含SLSQP；Controller遵守许可，实际执行原耦合构造/Sobol，不能按LLM描述计一次优化。原始actions及PHYSICAL_INTENT_AND_FEEDBACK_AUDIT_v3.json可逐项核对。',
        '', 'P2初始失败三次为必要物理条件拒绝，0M1；另一条ST_P2_3907在首点之后反馈结构错误，一次真实纠错后仍不合法。全部20次HTTP200，无Provider/传输故障。原始决策合法率15/20=75%，初始最终合法率6/9。',
        '', '停止行为是本轮主要限制之一：SW1301、SW3907、ST2603分别在4、7、3点时选择STOP，当时可用搜索预算为78、38、62次。Controller如实接受策略停止并报告未完成八点，LLM的“已足够”自述不替代八点验收。其余未完成运行保留预算预留/最小动作阈值/反馈轮数限制；不能一概称为硬预算耗尽。',
        '', '首点后所有其他初始区域诊断、反馈搜索和连通样本都计入追加最多128次M1；总预算以前128、首点后128控制。初始小探测没有隐藏；每个区域的Builder、反解、正式Seed、Sobol及Sensitivity调用单列。八点扩展器相同，区域/预算/许可由策略决定。',
        '', '本轮共92个选中可行点（含不足8的实际点集）。去重用共同guard对数坐标（f0线性）的六维RMS距离≥0.02；最小实际距离0.02042，归一化约束裕量最小0.04746，静态调谐余量最小0.04078V，均超过冻结阈值。逐点与每轴观测覆盖/区域成员关系单列，不能把独立Min/Max矩形宣布为可行区域。',
        '', '局部连接75条边、225次正式M1，三内部样本全PASS的边为75条。仅证明这些样本；连续线段、盒内其余点与全系统认证保持未知。P1的点集来自三个实际区域，P2来自两个或三个；见POINT_REGION_MEMBERSHIP.json。',
        '', '|第二轮成本|实际值|',
        '|---|---:|',
        '|正式M1|1,355（P1 943；P2 412）|',
        '|真实API|20|',
        '|主循环实际墙钟|332.9865秒|',
        '|外层CLI墙钟|336.0215秒|',
        '|LLM总API延迟|253.6091秒|',
        '|Physics工具累计墙钟|0.4353秒|',
        '|Optimizer包含M1 / 扣除其中M1|13.6408 / 1.9163秒|',
        '|Sensitivity包含M1|15.6982秒|',
        '|M1累计墙钟|47.6373秒|',
        '|P1 M1 p50/p95|0.03434 / 0.03653秒|',
        '|P2 M1 p50/p95|0.03448 / 0.04147秒|',
        '|反解调用 / 实际SLSQP启动|205 / 11|',
        '|主研究M2|0|',
        '', 'Optimizer、Sensitivity、搜索包含M1，耗时类别不能直接相加。首点/八点计时始于每轮submission落盘前，包含实际规划/API/构造/搜索，分别记录Controller收录与M1返回时刻。八点耗时不含其后STOP/API或连接抽查，总wall包含。开发、测试、人工授权等待及历史基线单列。API费用未套用未核实价格，Provider token原字段留存。',
        '', f"两轮新主研究合计36次、{cost['new_main_total']['M1']:,} M1、{cost['new_main_total']['API']} API，内部{cost['new_main_total']['inner_wall_s']:.4f}秒、CLI {cost['new_main_total']['outer_cli_s']:.4f}秒；A+原基线955M1/9API另列。回归和smoke消耗与主研究严格分账，见CROSS_ROUND_COST_SUMMARY.json与verifier成本账。",
        '', '验证：第一轮主套件856PASS/1项开工已知Stage4.2历史summary缺失FAIL；第二轮变更相关86项PASS，ST预验收111M1/六点，审计0违规。最终主账本审计与源保护以verifier最终报告为准。没有为无关历史缺失重建数据。',
        '', '交付索引：',
        '', '- FINAL_REPORT.md / STRATEGY_COMPARISON.csv / RUN_METRICS.csv：完整比较与逐轮成本。',
        '- CODE_CHANGES.patch及最终Diff补充：相对开工源码的修改；frozen/、source_snapshot/保留真实运行版本。',
        '- PHASE0_EVIDENCE_INDEX.json：三条失败重放与接口回归。',
        '- runs/*/：PlannerState、原始HTTP/JSON/Text、标准化/校验/修正差异、实际数值、候选/来源/时序/工具反馈。',
        '- REGION_EXECUTION.csv / ACTUAL_SUBSPACES.csv / LLM_PHYSICS_CLAIM_AUDIT.json：每区构造、执行和物理假设。',
        '- ALL_TOP8_POINTS.csv / CONSTRAINT_MARGIN_SUMMARY.json / POINT_COVERAGE.json / OBSERVED_POINT_SPREAD.csv：实际点数、裕量与参数差异。',
        '- LOCAL_CONNECTIVITY.csv / PHASE_TIMINGS.csv / M1_TIMING_SUMMARY.json / LLM_API_USAGE.json：连接、时延与API账。',
        '- PHYSICAL_INTENT_AND_FEEDBACK_AUDIT_v3.json：原意图/编译收缩/不同Seed/实际反馈动作的只读审计。',
        '- verifier/：独立审查、命令回执、主实验与单列验证成本。',
        '', '当前结论：真实LLM已超出单六维矩形输出，能提出不同物理假设并据实际M1观测选择继续或新区域；这只证明权限和执行链路可核查。本轮首点调用数没有优势，API导致实际时间更长；Top8完成率低于确定性基线。样本小且策略区域数不同，不能外推普遍最优。所有运行已完成，不再追加API、算法重构或M2研究。']
    with (TWO/'DELIVERY_REPORT.md').open('x',encoding='utf-8') as handle:handle.write('\n'.join(lines)+'\n')
    print(json.dumps({'main_batches':len(cost['main_batches']),'new_main':cost['new_main_total'],
        'P2_feedback':dict(feedback_counts),'token_fields':tokens},ensure_ascii=False))


if __name__=='__main__':main()
