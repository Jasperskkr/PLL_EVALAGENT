# P0 模块取舍表

路径前缀：B=`F:/LJP/概伦AI/PLL_SPEC_ALLOC_BASELINE`；A=`F:/LJP/概伦AI/PLL_AGENTV2/PLL_AGENT`；M5/M6/M7=`F:/LJP/概伦AI/PLL_SPEC_ALLOC_M05/M06/M07_WORKTREE`（实际目录为 PLL_SPEC_ALLOC_M05_WORKTREE 等）。全部实际绝对路径及 SHA 见审计 JSON。这里的“直接复用”表示字节复制后有来源记录；“适配”表示新合同/边界有改动，不冒称原件。

|原始文件（相对上述前缀）|当前功能|新主线取舍|依赖、理由及适配事项|
|---|---|---|---|
|B/src/pll_spec_alloc/evaluation/python_behavioral.py|完整窗口闭环积分和周期测量|直接复用|依赖 cp、lf、schemas.limits；保存原字节；外层独立验收|
|B/src/pll_spec_alloc/physics/cp.py|符号电荷/平衡/相位时序换算|直接复用|q0 已含代理负载；单位为 A、C、s、Hz|
|B/src/pll_spec_alloc/physics/lf.py|精确 RC 算子和阻抗|直接复用|理想 RC；增量 Rload 未进入传播|
|B/src/pll_spec_alloc/schemas.py、units.py|冻结80 MHz校验、三指标定义|兼容依赖复制；新入口适配|旧 validate_request 固定80 MHz，不作为新 ProblemBuilder；仅核心调用 limits|
|B/configs/system_80m_phase.yaml、suite.yaml|原规格、声明域和非零q0案例|冻结副本+显式适配|不改旧门限；扩展为独立输入和来源记录|
|B/configs/triplet_84m_comparison.yaml|84 MHz五轴联合域和对照|适配行为部分|去除 ngspice/历史 release 前置依赖；保留其目标和测量窗口|
|B/src/pll_spec_alloc/allocation/candidates.py|CP/LF笛卡尔候选|适配|新表示覆盖 CP/LF/VCO；不重写物理公式|
|B/src/pll_spec_alloc/experiments/triplet.py::targets/vco_target|现成五轴联合搜索|适配参数结构与目标语义|参考变量轴和产品枚举；不导入其模块证据执行器|
|B/src/pll_spec_alloc/allocation/ranker.py|原先验排序|适配为规则基线|新策略不得提前偷用完整 TB 结果；完整搜索成本全部记录|
|B/src/pll_spec_alloc/allocation/specs.py|五Block要求和sizing请求|参考五Block完整性|新主线输出规格，不生成 sizing 前置任务|
|B/src/pll_spec_alloc/feedback/controller.py::FeedbackReplay/reallocate_targets|真实候选重评/要求重分配|参考，暂不接入|依赖证据服务、模型注册和holdout；新反馈对象是行为违例|
|B/src/pll_spec_alloc/feedback/models.py|CP局部拟合与验证|历史模型来源参考|本轮不需要动态校准，不引入主链|
|M5/src/pll_spec_alloc/feedback/controller.py::WorkflowRunner/ActionGuard/ActionExecutor|固定执行与可替换策略|架构参考，最小适配实现|执行层强制检查/TB/预算；避免继承模块购买动作|
|M5/src/pll_spec_alloc/agents/interfaces.py|状态、工具返回、策略协议|接口参考|新 Policy 直接给完整 JointBlockSpec，不要求九类Agent|
|M6/src/pll_spec_alloc/feedback/controller.py::CPFeedbackTools|CP校准/发布/原候选重评|隔离|偏离本轮分配研究对象；保留源码及正式记录|
|M7/src/pll_spec_alloc/evidence/physical.py|G1证据读取、资格和请求|隔离|不是新行为TB，不能带入依赖|
|B/src/pll_spec_alloc/integrations/system_tb_stub.py|NOT_AVAILABLE占位|不复用执行能力|新 Backend 必须真实执行或明确 UNKNOWN|
|A/pll_agent/agent_runtime/orchestrator.py、state.py|策略注入、预算、trace、冻结|架构参考|保留有用原则，不带入realizer/region/证据图|
|A/pll_agent/problem2/decision/policy.py|有限观测邻域搜索|搜索基线参考|其设计点合同与新 JointBlockSpec 不同|
|A/pll_agent/problem1/llm_formulator.py|真实LLM、JSON及原始响应|接口/日志/提示词原则参考|用途为Problem1；新Policy必须实际选择完整分配|
|A/pll_agent/tools/backends/command.py|隔离目录、argv执行和解析|外部模拟器接口参考|保留超时、返回码、stdout/stderr、来源身份；不引入旧Task合同|
|A/pll_agent/problem2/allocation/sensitivity.py|参数扫描|后续敏感度实验参考|有限差分必须计额外真实TB成本；不伪造因果证据|
|A/docs/model_cards/*.md、results/p1_block_space_20261028/model_space_release/*|五Block模型卡和注册|数据目录索引、有效域继承|公共锚点与隐藏校准/留出分开；不全量塞给LLM|
|A/simulation/matlab/cppll_run.m、cppll_small_signal.m|MATLAB瞬态/连续小信号近似|参考后端，保留原件|旧stage7近似和corrected轨迹须区分；PM/BW不能直接冒充采样环路测量|
|F:/LJP/概伦AI/PLLngspice_vs_matlab/matlab/stage7/*|上述模型原来源|历史参考与MATLAB接入候选|与A副本用SHA核对，不按名称默认等价|
|F:/LJP/概伦AI/PLL_Physics_FactorGraph_MATLAB/PLL_Physics_FactorGraph_MATLAB/model/*、factors/*|物理关系、关系图、扫参|架构参考、暂不迁入|新课题固定拓扑；不再构建多余图框架|
|B/physical_g1*、F:/LJP/概伦AI/PLLngspice_vs_matlab/spice/*|电路、TB、RAW、数值诊断|原地保留/只读索引|不丢弃电路价值；不成为本轮运行依赖|

审计明确：旧联合搜索和 Legacy 重分配是真实能力；新工作重点是统一合同、真实可替换 Policy 与行为 TB 注入、公平记录首次结果及成本，而非重建物理积分器。
