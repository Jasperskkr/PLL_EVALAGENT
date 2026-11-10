# Track A 接口、Agent 与修复

官方入口：`python -m pll_allocation.track_a run --strategy analytical --out <不存在目录>`。批量入口为同模块的 `benchmark`。原 Runner、Policy、M1、Block Space 与 Track B 代码不修改。

## AllocationProposal → Track B

文件名 `AllocationProposal.json`，schema_version=`allocation-proposal-1.0`。`joint_block_spec` 直接保存既有 `pll-physics-mapping-2.0` envelope：schema_version、conventions、values；values完整17输入，逐项value/unit。`f0` 是0V截距，`Kvco` 单位Hz/V，`C1`为对地并联电容、`C2`为Rz串联支路；所有非理想项显式为零。`blocks`仅为权威变量到Block的索引，不复制第二份数值。N保留int。

`versions` 保存既有公式/域/模型版本及Track A基线版本；候选、SystemSpec、完整Block Space各有SHA256。`topology`、`operating_conditions`、约束/调谐裕量、独立M1预测、判决与置信度、分配元数据/Agent trace引用完整保存。M1_VALIDATED表示M1已成功计算，不等同M1_SPEC_PASS；M2_status=NOT_EVALUATED且verified_joint_block_spec=false。

接入示例（消费同一字段，无隐式单位换算）：

```python
from pll_allocation.track_a.core import load_model, read, validate_proposal
from pll_allocation.physics_mapping.model import MetricRequest
model = load_model('configs/BLOCK_SPACE_MODEL_V1.json')
item = read('path/to/AllocationProposal.json')
parameters = validate_proposal(model, item)
request = MetricRequest(parameters)
# request交由Track B独立实现的 evaluator.evaluate(request)，不在Track A签发M2结果。
```

实际Track B验收需自行核对其M2指标定义与协议；本轮仅证明现有MetricRequest直接消费17参数，无声称已联调未知Track B后端。

## Tool Action / Observation / Decision

`run_agent` 接收可插拔 `policy.decide(context)`；策略返回 `{tool,args,reason}`，执行器白名单校验并控制预算、候选句柄和停止。每步JSONL含action/observation/decision/elapsed_s/cost_to_date，LLM请求、原始响应、usage、HTTP状态及失败记录独立保存。政策不能更改目标/域、提供PASS或跳过Runner最终独立M1。候选生成是确定性工具的完整17参数输出。

工具包括 ReadSystemSpec、InspectBlockSpace、QueryPhysicalRelations、PropagateConstraints、AnalyzeSensitivity、SolveInverseAllocation、OptimizeCandidate、EvaluateM1、SubmitCandidateForM2、InterpretVerificationFeedback、Stop。上下文已含初始系统/域/公式，真实LLM可以跳过冗余读取，选择求解路径和候选。Submit只向Runner暂存完整候选；M2_budget=0时始终DEFERRED_TO_TRACK_B。每次正式run只允许一份首发候选，在最终独立M1前落盘。

真实LLM可控制工具选择/顺序与候选选择；当前数值候选策略限制在已有工具库，尚未实现自主生成新目标函数、模型校准、任意变量自由度选择。MockPolicy明确标MOCK_TOOL_POLICY_NOT_LLM，其确定性路径仅验收工具编排。真实LLM成绩与mock分开，回放不记新调用。

## 独立Feedback / Repair

`repair(model, system_spec, candidate, feedback, meter)` 不被first-shot入口调用；返回新完整候选或明确诊断请求。反馈schema=`allocation-feedback-1.0`，包含 parameter_sha256、source=SIMULATED/M2、kind、verdict=FAIL/UNKNOWN、measurements。BW观测必须有可靠标记、正有限Hz值；不直接接受反馈自称的PASS。

|kind|路径|证据边界|
|---|---|---|
|BW|按目标/实测带宽比协同缩放R和增益乘积，越界转联合优化|PM保持仅为理想M1关系；须新M2|
|PM|先检查电容比上界，再选LF形状及增益|不是无方向扰动|
|TUNING_UNREACHABLE|调整f0改善内部调谐|必须新检查并测量|
|COLD_START_CAPTURE|调谐中心作为可检验假设，请求初值/时窗/限幅轨迹|不得由M1预测捕获成功|
|MODEL_OUT_OF_DOMAIN|请求适用性诊断|不通过改公式绕过|
|UNRELIABLE_MEASUREMENT|请求窗口/注入/步长重测|测量未知不归罪Block|
|MULTIPLE|多指标联合重分配|保持已满足指标也需新验证|

七类模拟反馈有独立实验输出；real_repair_success_rate=null。真实LLM反馈后修复、真实M2修复率均未验收。除真实LLM策略选择外，修复原型目前为确定性路由，可由未来policy结合该接口选择路径；不能把固定路由称为真实LLM学习。

修复若新旧参数哈希相同，则返回None和NO_CHANGE_REQUEST_M2_DIAGNOSIS，不将重复候选算新修复。推荐解析首发已处于最高电容比/相位峰值及调谐中心，此时实测PM或捕获失败更需要M1/M2差异或初值轨迹证据。

`feedback_agent.run_repair_agent` 为独立后反馈工具循环，不被first-shot入口导入。可插拔policy.decide(context)在InterpretVerificationFeedback、RepairCandidate、OptimizeCandidate、SubmitRepairForM2、RequestDiagnosis、Stop间选择；未知测量/超域反馈禁止盲目优化。MockRepairPolicy按失败类别选择修复或诊断，七类模拟案例保存action/observation/decision、候选、独立M1和延后M2状态。该mock未计作真实LLM修复；真实策略可实现同一协议后另行验收。
