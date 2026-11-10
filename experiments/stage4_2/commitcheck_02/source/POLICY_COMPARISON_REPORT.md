# 策略对照报告

数据来源：outputs/final_behavioral_suite/suite_summary.json。固定seed=0；每案例/每策略最多30次完整TB，提议最多30次，首次完整候选在TB前保存。

|案例|策略|首次通过|到首个可行的评价数|实际TB数|预算内成功|最小归一化裕量|最终状态|
|---|---|---|---|---|---|---|---|
|regular80|rule|True|1|1|True|0.017817|VERIFIED_BEHAVIORAL_PASS|
|regular80|grid|False|19|19|True|0.017817|VERIFIED_BEHAVIORAL_PASS|
|regular80|random|False|3|3|True|0.017817|VERIFIED_BEHAVIORAL_PASS|
|regular80|feedback|False|2|2|True|0.017817|VERIFIED_BEHAVIORAL_PASS|
|tight80|rule|True|1|1|True|0.052271|VERIFIED_BEHAVIORAL_PASS|
|tight80|grid|False|25|25|True|0.052271|VERIFIED_BEHAVIORAL_PASS|
|tight80|random|False|12|12|True|0.0494996|VERIFIED_BEHAVIORAL_PASS|
|tight80|feedback|False|2|2|True|0.052271|VERIFIED_BEHAVIORAL_PASS|
|finite_domain80|rule|False|None|30|False|-3.50849|BUDGET_EXHAUSTED|
|finite_domain80|grid|False|None|30|False|-2.00596|BUDGET_EXHAUSTED|
|finite_domain80|random|False|None|30|False|-1.40596|BUDGET_EXHAUSTED|
|finite_domain80|feedback|False|None|30|False|-3.50849|BUDGET_EXHAUSTED|
|joint84|rule|True|1|1|True|0.527397|VERIFIED_BEHAVIORAL_PASS|
|joint84|grid|False|3|3|True|0.532208|VERIFIED_BEHAVIORAL_PASS|
|joint84|random|False|3|3|True|0.0521089|VERIFIED_BEHAVIORAL_PASS|
|joint84|feedback|False|2|2|True|0.530771|VERIFIED_BEHAVIORAL_PASS|
|unsupported_jitter80|rule|False|None|1|False|0.017817|UNSUPPORTED_SYSTEM_SPEC|
|unsupported_jitter80|grid|False|None|1|False|-0.350448|UNSUPPORTED_SYSTEM_SPEC|
|unsupported_jitter80|random|False|None|1|False|-0.804241|UNSUPPORTED_SYSTEM_SPEC|
|unsupported_jitter80|feedback|False|None|1|False|-0.350448|UNSUPPORTED_SYSTEM_SPEC|

## 对照边界

规则策略按解析平衡相位、低电流、q0和调谐距离排序；网格按原声明顺序枚举；随机搜索固定seed；反馈基线从初点出发，使用真实违例及解析关系修复。这些均是非LLM策略。解析排序不偷偷运行动态TB，额外行为调用数为0。

三组已找到可行解的案例上，规则首次通过3/3；网格/随机/反馈首次通过均0/3；四种方法预算内成功均3/3。这是固定案例与单seed的工程冒烟结果，不是统计可靠的算法排名，也不能说明LLM更好。

finite_domain80的30个声明点全部实际评价仍未通过，只能报告该离散域内未找到；不能证明连续域或真实PLL不可实现。unsupported_jitter80实际执行一次TB后明确停止，噪声模型缺失不能通过调参修复。

## LLM验收未完成

真实服务模型为deepseek-v4-pro；两次实际HTTP请求均在200响应后超时，未形成候选，行为评价0次。分别保存于outputs/p3_live_initial和outputs/p3_live_bounded。第二次采用60秒进程总期限并实际停止。没有用规则、mock或离线回放填补结果；首次LLM可行率与修复效果为NOT_EXECUTED，不写成0%性能结果。

## 成本与指标

正式确定性套件20次运行，共198次完整行为评价。逐运行system_metrics.json保存最小裕量、归一化违例、解析预测相对TB误差、策略耗时与TB耗时。只有静态相位有可信解析预测，所以Predicted-vs-Verified只报告该项；动态项不填伪造预测。

当前random仅seed=0、LLM没有成功响应；尚需多目标分布、多随机种子、稳定模型版本和重复LLM样本，才能比较First-pass Feasible Rate、评价成本与可行裕量。
