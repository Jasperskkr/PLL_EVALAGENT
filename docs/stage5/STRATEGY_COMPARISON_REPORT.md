# Strategy comparison — Stage 5

本轮为冻结五场景、三个配对随机种子的探索性比较。所有首发先完成后才进入反馈修复，不作统计普遍性推断。完整数据见 experiments/stage5/summary_02，失败调用和局部后处理错误均保留。

|Scenario|Strategy|Seed|M1 first-shot|M2 BW (kHz)|BW judgment|Overall|
|---|---|---:|---|---:|---|---|
|S0|analytical|—|M1_SPEC_PASS|226.403934|PASS|UNKNOWN|
|S0|random|11|M1_SPEC_FAIL|416.781139|FAIL|FAIL|
|S0|random|23|M1_SPEC_FAIL|713.783792|FAIL|FAIL|
|S0|random|47|M1_SPEC_FAIL|326.827895|FAIL|FAIL|
|S0|llm_agent|—|M1_SPEC_PASS|226.403934|PASS|UNKNOWN|
|S1|analytical|—|M1_SPEC_PASS|206.058498|PASS|UNKNOWN|
|S1|random|11|M1_SPEC_FAIL|416.781139|FAIL|FAIL|
|S1|random|23|M1_SPEC_FAIL|713.783792|FAIL|FAIL|
|S1|random|47|M1_SPEC_FAIL|326.827895|FAIL|FAIL|
|S1|llm_agent|—|M1_SPEC_PASS|206.058498|PASS|UNKNOWN|
|S2|analytical|—|M1_SPEC_PASS|262.123340|PASS|UNKNOWN|
|S2|random|11|M1_SPEC_FAIL|416.781139|FAIL|FAIL|
|S2|random|23|M1_SPEC_FAIL|713.783792|FAIL|FAIL|
|S2|random|47|M1_SPEC_FAIL|326.827895|FAIL|FAIL|
|S2|llm_agent|—|NOT_EVALUATED|—|NOT_EVALUATED|NOT_VERIFIED|
|S3|analytical|—|M1_SPEC_PASS|296.839212|PASS|UNKNOWN|
|S3|random|11|M1_SPEC_FAIL|416.781139|FAIL|FAIL|
|S3|random|23|M1_SPEC_FAIL|713.783792|FAIL|FAIL|
|S3|random|47|M1_SPEC_FAIL|326.827895|FAIL|FAIL|
|S3|llm_agent|—|M1_SPEC_PASS|296.839212|PASS|UNKNOWN|

解析：4/4首发M1满足，4/4独立M2 BW通过；每场景1次完整M2。首发BW分别225/205/260/295kHz，产生4个不同JointBlockSpec。原求解器枚举离散C、选择峰值lead形状、数值求BW/UGF比，再条件反解R及增益并分配Icp/Kvco与调谐点；不是纯闭式解析。

Random：12/12首发M1失败，12/12测得BW失败；每场景3种子。三组完整参数跨场景配对复用，BW实测约416.781/713.784/326.828kHz，均超各场景上限。无事前M1筛选或随机重抽；所有首次合法且调谐可达，0个因域非法被排除，0个用隐藏解析解替代。M1廉价评价已能识别这些首次无效分配，但实验为保持纯Random对照仍执行M2。

真实LLM：S0/S1/S3成功，各3次deepseek-v4-pro调用，均选择 SolveInverseAllocation → EvaluateM1 → SubmitCandidateForM2；候选与对应解析基线完全相同。S2一次HTTP200响应达到1500输出token预算后JSON解析失败，无候选/无M2，记录REAL_LLM_NOT_EXECUTED（allocation未执行），实际失败网络请求及token已计入。S4预检跳过，不算LLM失败。合计10次真实API，9次有效动作、1次解析失败，无自动重试。

现有Agent提示词明确要求选择确定性工具、避免自行高精度计算，且四次调用预算优先求解后提交。因此本轮证据仅支持受限工具编排，不是对LLM所有潜在数值设计能力的否定。没有观察到不同候选、额外数值质量、成本优势或真正LLM反馈修复。

S4所有5个arm均先得到INFEASIBLE_UNDER_M1_ASSUMPTIONS：73°超过声明C集合的理想PM上界72.247209838°，0候选/0M2/0LLM。不能外推为真实CPPLL绝对不可行。

|Scenario|Seed|Repair action|M1 BW (kHz)|M1 PM (deg)|M2 BW (kHz)|BW status|
|---|---:|---|---:|---:|---:|---|
|S0|11|REALLOCATE_WITH_BOUNDS|204.356651|72.247210|205.385568|PASS|
|S0|23|REALLOCATE_WITH_BOUNDS|204.356651|72.247210|205.385568|PASS|
|S0|47|REALLOCATE_WITH_BOUNDS|204.356651|72.247210|205.385568|PASS|
|S1|11|REALLOCATE_WITH_BOUNDS|204.998523|72.247210|206.057005|PASS|
|S1|23|REALLOCATE_WITH_BOUNDS|204.998523|72.247210|206.057005|PASS|
|S1|47|REALLOCATE_WITH_BOUNDS|204.998523|72.247210|206.057005|PASS|
|S2|11|REALLOCATE_WITH_BOUNDS|253.300019|72.199687|255.177946|PASS|
|S2|23|REALLOCATE_WITH_BOUNDS|253.300019|72.199687|255.177946|PASS|
|S2|47|COORDINATED_SCALE_REPAIR|259.324458|56.361690|259.762741|PASS|
|S3|11|COORDINATED_SCALE_REPAIR|294.221229|45.661369|294.644315|PASS|
|S3|23|REALLOCATE_WITH_BOUNDS|295.000000|56.442690|296.071758|PASS|
|S3|47|COORDINATED_SCALE_REPAIR|294.233520|56.361690|294.872412|PASS|

12/12真实BW失败生成不同完整候选并各用1次新增M2复验，BW全部改为PASS；每arm到首次受支持BW候选共2次M2，在≤3预算内。修复动作计数：{'REALLOCATE_WITH_BOUNDS': 9, 'COORDINATED_SCALE_REPAIR': 3}。其中S3 seed11 M1 PM=45.661369°低于50°，虽然BW实测PASS，完整联合规格仍未预测可行；正式M2 PM UNKNOWN，不能遮蔽这一预测失败。

未知指标未触发强制修复；解析和成功LLM只收到UNKNOWN精度/PM反馈后停止。无新LLM修复算法，不能把上述确定性修复归于LLM或原纯Random首发成功。

|Phase|M2 complete calls|Native runs|M1 formal|M1 posthoc|Cheap calls|Process wall sum (s)|
|---|---:|---:|---:|---:|---:|---:|
|FIRST_SHOT|19|2078|22|19|65|364.408|
|FEEDBACK_REPAIR|12|1272|93|12|921|137.336|

主策略实验合计31次完整M2、3350次native、2,930,851,649积分点；原生89.356s，Pipeline总470.540s，子进程总501.744s。实际数值反解根工具次数81、有记录SLSQP求解器调用45，详情见run_costs.csv与cost_events。

LLM实际usage：`{"input_tokens": 12368, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 11392, "output_tokens": 9111}`。input_tokens与cache_read_input_tokens按提供商分别累计，不能只报未缓存输入。无已审计价格配置，API货币成本null，不能误报免费。所有墙钟包含Python、工具、网络、测量及搜索；没有仅报原生积分时间。

首次有效BW候选：解析及成功LLM=1次M2；Random首发未找到，接入确定性修复后=2次。S2 LLM未形成候选，无首次成功成本值。所有31次主策略完整M2中BW均获得收敛测量；每次正式3硬指标中2项UNKNOWN，硬指标UNKNOWN率=2/3。UGF为诊断且无周期认证，不加入硬约束分母。完整SystemSpec认证PASS=0。
