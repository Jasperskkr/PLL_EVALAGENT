# P1 数据合同和预留接口

所有公开JSON有 schema_version；`pll_allocation/contracts.py`、`behavioral.py` 是可执行合同。原始schema不兼容则拒绝，不猜单位。数值只接收有限 int/float；参数单位固定为 Hz、Hz/V、A、C、F、Ohm、V、s、deg、ppm、无量纲1。

|对象|版本/位置|主要字段|
|---|---|---|
|SystemSpec|problem.system_spec|metric/unit/value/operator/tolerance/measurement/source；每次输入有SHA|
|FixedTopology|problem.topology|固定id、五Block、五条有向连接；操作条件单独显式保存|
|BlockSpaceModel|problem.block_space|每Block每参数的unit/choices；声明角色、来源、validity、couplings|
|JointBlockSpec|joint-block-spec-1.0|五Block所有参数的value/unit、common_conditions、parameter_role|
|ScreeningPrediction|ANALYTIC_EQUILIBRIUM_PREDICTION|解析平衡相位/Veq；不产生动态PASS|
|BehavioralEvaluation|behavioral-evaluation-1.0|problem/candidate SHA、backend_id、实际测量、单位、协议、完成状态、域、证据和成本|
|AllocationAttempt|allocation-attempt-1.0|序号、提议、策略来源/理由、约束、预测、测量、独立判决、诊断和成本|
|AllocationResult|allocation-result-1.0|状态、首次/最终结果、输入/源码/trace SHA、预算、环境、LLM元数据和metrics|

主入口 `run` 接收独立文件；SystemSpec/Topology/BlockSpace在同一Problem信封内分别冻结，输出仍拆成标准快照。首版有限离散域明确可分配对象；未声称连续域、任意拓扑或PVT支持。域内范围扩大属于模型版本变更，不能由Policy提出。

## Policy / Agent 接入

`AllocationPolicy.propose(problem, history, remaining) -> {candidate, rationale} | None`。

problem/history传深拷贝，remaining分别给完整行为评价与提议预算。Policy可决定所有候选及修复策略，不能修改原输入、选择跳过TB或授予PASS。LLM输入含物理关系、单位、合法域、历史真实违例与已满足项、剩余预算。首次调用看不到后续反馈。额外有限差分敏感度必须通过Runner计费；当前仅提供解析关系，并明确不是数值敏感度实测。

## Simulator / Verifier 接入

`BehavioralBackend.capabilities() -> {backend_id, metrics:{name:{unit,measurement}},scope,...}`。

`BehavioralBackend.run(problem,candidate,workdir) -> BehavioralEvaluation`。

`BehavioralVerifier.judge(problem,candidate,evaluation) -> {verdict, checks, issues, margins,...}`。

正式生产HTTP适配器目前为已配置的Messages协议；OpenAI-compatible/Responses等提供商可另行实现同一Policy协议，当前没有伪称已接入所有厂商。`llm_transport.py`以独立进程实施总时间预算，保留连接/读取/超时状态；隐藏凭证只由子进程从环境读取，配置和结果不含密钥。

独立后端注入 `run(..., backend=..., verifier=...)`；原Python后端已真实实现。外部命令桥为 `CommandBehavioralBackend(argv, capabilities, timeout_s)`；不使用shell。执行目录内读取 `request.json`，写 `response.json`；stdout/stderr保留；非零退出/超时/无文件转换UNKNOWN且消耗一次评价。MATLAB可以用 -batch 运行其桥接函数，不需重写整个模型。**外部命令桥有测试；MATLAB实际进程/许可证/结果映射尚待验收，不能把桥等同已连接MATLAB。**

请求信封为behavioral-request-1.0，含problem、candidate、两者SHA。响应必须含schema_version、backend_id、kind=FULL_BEHAVIORAL_TB_MEASUREMENT、problem_sha256、candidate_sha256、completed、reference_cycles、measurement、metric_measurements、metrics、units、domain_status及artifacts/cost。phase/frequency/voltage方向与协议须一致；原始波形与测量定义应可审计。外部模拟器报告的自称PASS被忽略；Verifier按冻结SystemSpec重新比较。

Python首版能力：尾相位、尾最大频差、锁定状态/诊断锁定时间、尾均输出频率、全轨迹Vctrl极值。它是参考周期电荷脉冲的完整窗口行为TB，不能称边沿级/晶体管级。phase_noise、jitter、spur、采样闭环BW/PM返回UNSUPPORTED→UNKNOWN。连续时间小信号公式仅保留参考，不能替代这类测量。

## 生命周期和可追溯性

候选提议 → 首次文件落盘 → 独立约束 → 解析预测 → 真实TB → 冻结指标判决 → 保存轨迹 → 反馈/停止。失败调用计费；有限提议和评价预算双重限制；输出目录存在即拒绝。首次无提议（如服务不可用）保留输入和失败原因，不伪造initial_joint_block_spec。

source_snapshot记录运行代码SHA；legacy_manifest记录提取来源及原字节SHA；JSONL事件含前序/自身SHA。API密钥仅从明确配置的环境变量读取，不保存请求头。离线回放显式标记saved_proposal_replay_v1，真实网络调用数为0。
