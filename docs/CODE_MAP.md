# 逐文件代码导读

更新于2026-11-17。覆盖当前共享 Python/C++/CMD 源码，包括明确标注的兼容入口；不枚举构建目录、缓存和实验源码副本。模块职责命名规则及旧名称映射见 [NAMING](NAMING.md)。

建议先读：`pipeline.py` → `agent/initial_allocation.py` → `physics_tool_policy.py` → `search_loop.py` → `exploration/physics_region_builder.py` → `allocation/physics.py` → `region_explorer/explorer.py` → `agent/handoff.py` → `agent/feedback.py` → `verification/continuous.py`。

正式主线、可选研究、旧数值参考与兼容入口分别列出。保留模块不代表各入口支持相同的Agent反馈能力；实际范围见 [项目章程](../PROJECT_CHARTER.md)。

## 入口与旧基础框架

|文件|基本职责|阅读入口|
|---|---|---|
|[pll_allocation/__init__.py](../pll_allocation/__init__.py)|包版本与公开模块标识；声明验证结论限于行为模型。|模块初始化/转发|
|[pll_allocation/__main__.py](../pll_allocation/__main__.py)|将 python -m pll_allocation 转发给 CLI。|模块初始化/转发|
|[pll_allocation/behavioral.py](../pll_allocation/behavioral.py)|旧行为内核的输入映射、后端调用和指标判决适配；不是新M2测量公式。|`legacy_inputs` / `screen`|
|[pll_allocation/cli.py](../pll_allocation/cli.py)|识别 pipeline 并进入正式入口；旧 v1 run/suite 需显式 --legacy-v1。|`read` / `make_policy`|
|[pll_allocation/contracts.py](../pll_allocation/contracts.py)|旧 v1 问题、拓扑、候选与单位合同；不等同于新的 ResearchProblemV2。|`ContractError` / `canonical`|
|[pll_allocation/llm_transport.py](../pll_allocation/llm_transport.py)|隔离的 Messages HTTP 子进程，保存真实响应/状态，使外层能执行总超时。|`save` / `main`|
|[pll_allocation/pipeline.py](../pll_allocation/pipeline.py)|默认连续域多候选，统一路由/参数消费校验；Handoff/M2反馈、显式冻结兼容与研究扩展。|`_execution_route` / `main`|
|[pll_allocation/pipeline_contracts.py](../pll_allocation/pipeline_contracts.py)|加载并核对冻结模型/Spec/协议绑定，校验M2返回，形成反馈；不计算物理公式。|`load_inputs` / `check_result`|
|[pll_allocation/policies.py](../pll_allocation/policies.py)|旧 v1 Rule/Grid/Random/Feedback/Replay/LLM候选策略；保留兼容和基线。|`RulePolicy` / `GridPolicy`|
|[pll_allocation/runner.py](../pll_allocation/runner.py)|旧 v1 的独立候选/TB验收循环，负责写盘、预算、失败与诊断。|`diagnosis` / `source_snapshot`|
|[pll_allocation/scenarios.py](../pll_allocation/scenarios.py)|在冻结资产上绑定研究规格阈值，校验候选与场景来源。|`validate_scenario` / `load_scenario`|

## Agent与反馈

2026-11-18 多候选适配：`agent/spec_allocation.py` 是正式 Pipeline 的多策略配置/结果适配，并导出原生联合通过的 `sizing_handoff.json`；`candidate_pool.py` 管理质量、距离去重、通过子集和 M2 候选选择；`feedback.py` 按独立联合目标持续验证，支持成功补点及失败修复；`pool_search.py` 在原搜索执行器上补多点停止、Cold Start 后按需校准、确定性/LLM/Auto Policy；`deterministic_feedback.py` 保留 V2 反馈规则。没有新增物理求解器或验证器。回归为 `tests/test_spec_allocation.py`。

|文件|基本职责|阅读入口|
|---|---|---|
|[pll_allocation/agent/__init__.py](../pll_allocation/agent/__init__.py)|Agent策略适配包说明。|模块初始化/转发|
|[pll_allocation/agent/calibration.py](../pll_allocation/agent/calibration.py)|把兼容的已存M1数值按当前Spec重新判决，或显式重新校准；不能偷换模型。|`raw_problem` / `prepare_context`|
|[pll_allocation/agent/candidates.py](../pll_allocation/agent/candidates.py)|追加式候选证据账本；域与问题绑定、去重、可行优先及裕量排序。|`material_change` / `rank`|
|[pll_allocation/agent/computational_window.py](../pll_allocation/agent/computational_window.py)|无用户六轴界时的有限计算窗口适配；真实LLM提窗口，任意尺度锚点不冒充物理能力边界。|`WindowDecisionError` / `observation_evidence`|
|[pll_allocation/agent/decision_adapter.py](../pll_allocation/agent/decision_adapter.py)|将不可信LLM提案转换为既有SearchDecision；校验失败保留明确错误。|`DecisionValidationError` / `adapt_decision`|
|[pll_allocation/agent/feedback.py](../pll_allocation/agent/feedback.py)|正式连续域M2控制器；执行真实验证、保存反馈，在总预算内重分配并复验。|`read` / `validate_config`|
|[pll_allocation/agent/handoff.py](../pll_allocation/agent/handoff.py)|生成/校验完整候选、问题与独立复核的版本化交接；本文件不运行M2。|`validate_handoff` / `build_handoff`|
|[pll_allocation/agent/initial_allocation.py](../pll_allocation/agent/initial_allocation.py)|连续域首次分配入口；把物理工具策略接入现有 AgentSearchLoop。|`PhysicsToolSearchLoop` / `run_initial_allocation`|
|[pll_allocation/agent/physics_tool_policy.py](../pll_allocation/agent/physics_tool_policy.py)|构造真实观察状态，验证策略配置与物理动作，提供确定性/真实LLM Policy。|`validate_config` / `validate_feedback`|
|[pll_allocation/agent/planner_state.py](../pll_allocation/agent/planner_state.py)|把当前问题的采样、敏感度与冲突证据压缩为Planner可读状态。|`compact_sample` / `representative_rows`|
|[pll_allocation/agent/region_policy.py](../pll_allocation/agent/region_policy.py)|真实 Messages Policy、严格JSON解析和Provider错误；保存调用metadata。|`ProviderError` / `InvalidResponse`|
|[pll_allocation/agent/run_state.py](../pll_allocation/agent/run_state.py)|从真实决策/观察推导求解、可行性、反馈与质量等独立状态，避免混成PASS。|`optimization_executed` / `quality_state`|
|[pll_allocation/agent/search_loop.py](../pll_allocation/agent/search_loop.py)|观察→决策→校验→工具执行循环；累计预算、候选账本和独立最终复核。|`validate_config` / `source_manifest`|
|[pll_allocation/agent/subregion_context.py](../pll_allocation/agent/subregion_context.py)|从执行器实际证据导出 PhysicsContext，区分正式新评价与缓存。|`was_formal_call` / `export_context`|
|[pll_allocation/agent/subregion_contracts.py](../pll_allocation/agent/subregion_contracts.py)|校验区域几何、意图、多区域计划和体积；区域合法不等于区域已认证。|`validate_config` / `volume`|
|[pll_allocation/agent/subregion_loop.py](../pll_allocation/agent/subregion_loop.py)|小样本初始化、确定性或多区域提案编排；共用原M1执行器，不另写求解器。|`source_manifest` / `execute_multi_region_plan`|
|[pll_allocation/agent/subregion_prior.py](../pll_allocation/agent/subregion_prior.py)|把冻结方程、当前样本和敏感度组织成带来源的物理先验。|`physics_relations` / `build_prior`|
|[pll_allocation/agent/subregion_tools.py](../pll_allocation/agent/subregion_tools.py)|把原物理反解、局部敏感度请求适配为执行器任务并保留证据。|`envelope` / `inverse_proposals`|
|[pll_allocation/agent/window_contract.py](../pll_allocation/agent/window_contract.py)|不可信规划边界的单位/SI、坐标和窗口合同，处理结构纠错及物理拒绝。|`ContractError` / `si_factor`|

## 分配与原物理求解

|文件|基本职责|阅读入口|
|---|---|---|
|[pll_allocation/allocation/__init__.py](../pll_allocation/allocation/__init__.py)|冻结兼容链的 AllocationPolicy/策略适配；旧llm_agent反馈仍明确未实现，区别于连续域feedback。|`AllocationPolicy` / `AllocationStrategyPolicy`|
|[pll_allocation/allocation/__main__.py](../pll_allocation/allocation/__main__.py)|冻结分配基线CLI；正式主线仍使用pipeline。|`main`|
|[pll_allocation/allocation/agent.py](../pll_allocation/allocation/agent.py)|原工具驱动Agent与MessagesPolicy，分离工具数值、策略与日志；MockPolicy仅用于测试。|`MockPolicy` / `MessagesPolicy`|
|[pll_allocation/allocation/allocate.py](../pll_allocation/allocation/allocate.py)|原确定性nominal/analytical/敏感度优化/random方案，生成完整参数并作M1评价。|`generated` / `analytical`|
|[pll_allocation/allocation/core.py](../pll_allocation/allocation/core.py)|原分配公共合同、SI值/范围、Meter计费、正式M1评价与提案封装。|`write_new` / `read`|
|[pll_allocation/allocation/feedback_agent.py](../pll_allocation/allocation/feedback_agent.py)|独立的工具修复循环及显式MockRepairPolicy；其测试不代表真实LLM研究。|`MockRepairPolicy` / `run_repair_agent`|
|[pll_allocation/allocation/first_allocation.py](../pll_allocation/allocation/first_allocation.py)|冻结问题首次分配执行，候选先写盘并独立复核M1。|`run_first`|
|[pll_allocation/allocation/multispec_constraints.py](../pll_allocation/allocation/multispec_constraints.py)|联合指标的证据来源、统计与硬约束判决适配，不新增物理模型。|`validate_problem` / `evaluate_constraints`|
|[pll_allocation/allocation/multispec_search.py](../pll_allocation/allocation/multispec_search.py)|显式联合研究的确定性候选控制器；M2与最终判决仍由Runner管理。|`SearchController`|
|[pll_allocation/allocation/noise_optimization.py](../pll_allocation/allocation/noise_optimization.py)|可选噪声硬裕量接入原SLSQP，通过受控源码生成保留原求解行为。|`generated_source` / `optimize_with_noise`|
|[pll_allocation/allocation/physics.py](../pll_allocation/allocation/physics.py)|当前拓扑的PM上界、形状/带宽数值根、逆向构造及廉价预测；不运行M2。|`pm_ceiling` / `phase_interval`|
|[pll_allocation/allocation/repair.py](../pll_allocation/allocation/repair.py)|读取违例诊断并执行原确定性反馈修复，与首次分配逻辑隔离。|`interpret_feedback` / `repair`|

## 连续域探索与执行器

|文件|基本职责|阅读入口|
|---|---|---|
|[pll_allocation/exploration/__init__.py](../pll_allocation/exploration/__init__.py)|导出探索/PhysicsContext入口，不在此执行LLM或M2。|`run_exploration` / `load_physics_context`|
|[pll_allocation/exploration/contracts.py](../pll_allocation/exploration/contracts.py)|ResearchProblemV2、Spec启用项、六轴单位/范围、参数检查与按来源M1判决。|`require` / `number`|
|[pll_allocation/exploration/engine.py](../pll_allocation/exploration/engine.py)|原M1上的物理引导Sobol校准/探索、必要条件、模型身份和Context读写。|`source_identity` / `model_identity`|
|[pll_allocation/exploration/physics_region_builder.py](../pll_allocation/exploration/physics_region_builder.py)|把策略目标经原反解构造合法完整种子与局部盒，检查增益/调谐交集；不是评价器。|`PhysicsRequestError` / `validate_request`|
|[pll_allocation/exploration/regions.py](../pll_allocation/exploration/regions.py)|由真实点证据给出候选区域、局部有限差分矩阵和弹性；不认证整个区域。|`point` / `candidate_regions`|
|[pll_allocation/region_explorer/__init__.py](../pll_allocation/region_explorer/__init__.py)|公开区域执行器入口与延迟导出。|`run_region_exploration`|
|[pll_allocation/region_explorer/assessment.py](../pll_allocation/region_explorer/assessment.py)|只读整理已有点证据和区域摘要；不额外消耗M1，不认证全域。|`normalized_point` / `contains`|
|[pll_allocation/region_explorer/contracts.py](../pll_allocation/region_explorer/contracts.py)|独立校验SearchDecision动作、区域、活动轴与预算，策略不能指定验证结论。|`decision_signature` / `validate_decision`|
|[pll_allocation/region_explorer/explorer.py](../pll_allocation/region_explorer/explorer.py)|正式M1上的Sobol/SLSQP执行、缓存、边界/预算、停止钩子和记录。|`BudgetExhausted` / `SearchTargetReached`|

## 物理模型与模块合同

|文件|基本职责|阅读入口|
|---|---|---|
|[pll_allocation/block_space/__init__.py](../pll_allocation/block_space/__init__.py)|导出行为级Block Space的合同和前向接口。|模块初始化/转发|
|[pll_allocation/block_space/__main__.py](../pll_allocation/block_space/__main__.py)|Block Space表征/检查命令入口，不是新分配主线。|`main`|
|[pll_allocation/block_space/calibration.py](../pll_allocation/block_space/calibration.py)|生成追加式预测/测量偏差记录；不静默改写原公式。|`discrepancy_record`|
|[pll_allocation/block_space/contracts.py](../pll_allocation/block_space/contracts.py)|加载冻结模型、构造完整候选、检查声明域并调用原M1。|`validate_model` / `load_model`|
|[pll_allocation/block_space/event_reference.py](../pll_allocation/block_space/event_reference.py)|原Python边沿TB适配与比较，与连续M1明确分开。|`load_existing_simulator` / `clean_summary`|
|[pll_allocation/block_space/profiles.py](../pll_allocation/block_space/profiles.py)|可选外部噪声/非理想profile的单位、参数及适用域校验。|`number` / `validate_noise`|
|[pll_allocation/block_space/sampling.py](../pll_allocation/block_space/sampling.py)|确定性的前向代表点/异常点计划，用于域表征而非自适应求解。|`representative_cases` / `abnormal_cases`|
|[pll_allocation/block_space/validation.py](../pll_allocation/block_space/validation.py)|执行前向域表征、敏感度摘要与来源分类，输出数值/事件证据。|`write_new` / `summarize_sensitivity`|
|[pll_allocation/physics_mapping/__init__.py](../pll_allocation/physics_mapping/__init__.py)|独立物理映射包，与旧v1候选语义分开。|模块初始化/转发|
|[pll_allocation/physics_mapping/__main__.py](../pll_allocation/physics_mapping/__main__.py)|物理映射数值验证的模块命令入口，不取代正式分配Pipeline。|`main`|
|[pll_allocation/physics_mapping/experiment.py](../pll_allocation/physics_mapping/experiment.py)|M1实验Spec和变量模型合同，构造参数并对受支持指标判决。|`parameters_from_experiment` / `validate_experiment`|
|[pll_allocation/physics_mapping/model.py](../pll_allocation/physics_mapping/model.py)|正式M1：SI参数解析、适用域、静态调谐、环路传递/扫描、BW/UGF/PM及状态。|`Status` / `fingerprint`|
|[pll_allocation/physics_mapping/noise.py](../pll_allocation/physics_mapping/noise.py)|可选连续M1噪声传递、积分及敏感度；不是独立时域测量。|`transfers` / `optimizer_noise_estimate`|
|[pll_allocation/physics_mapping/registry.py](../pll_allocation/physics_mapping/registry.py)|读取/核对物理关系索引与源身份，按来源/适用域查询；不执行新求解。|`load_registry` / `query`|
|[pll_allocation/physics_mapping/validation.py](../pll_allocation/physics_mapping/validation.py)|独立多项式/KCL等数值比较与异常检查；不能称为MATLAB或行为TB精度认证。|`polynomial_reference` / `compare`|

## 行为验证与原生后端

|文件|基本职责|阅读入口|
|---|---|---|
|[pll_allocation/verification/__init__.py](../pll_allocation/verification/__init__.py)|正式独立事件验证包说明。|模块初始化/转发|
|[pll_allocation/verification/build_identity.py](../pll_allocation/verification/build_identity.py)|校验理想原生库、源码和适配器的精确身份；缺库/不匹配时拒绝。|`identities` / `check_build`|
|[pll_allocation/verification/build_kernel.cmd](../pll_allocation/verification/build_kernel.cmd)|编译理想内核到全新build目录，再生成源/二进制身份。|构建脚本|
|[pll_allocation/verification/build_nonideal.cmd](../pll_allocation/verification/build_nonideal.cmd)|在全新build_nonideal目录编译噪声/非理想扩展并生成身份，拒绝覆盖旧构建。|构建脚本|
|[pll_allocation/verification/build_phase_step.cmd](../pll_allocation/verification/build_phase_step.cmd)|在全新目录编译相位阶跃扩展。|构建脚本|
|[pll_allocation/verification/build_return_ratio.cmd](../pll_allocation/verification/build_return_ratio.cmd)|在全新目录编译返回比扩展。|构建脚本|
|[pll_allocation/verification/continuous.py](../pll_allocation/verification/continuous.py)|连续域Handoff→真实原生TB的正式适配，进程超时隔离、部分证据、独立M2判决。|`measurement_suite` / `model_identity`|
|[pll_allocation/verification/experiments.py](../pll_allocation/verification/experiments.py)|保存真实运行、频响点/扫描与测量协议；文件写入拒绝覆盖。|`read` / `write`|
|[pll_allocation/verification/kernel.cpp](../pll_allocation/verification/kernel.cpp)|原理想PFD/CP/LF/VCO/Divider边沿与Euler积分内核；行为闭环数值来源。|原生源码|
|[pll_allocation/verification/measure.py](../pll_allocation/verification/measure.py)|由轨迹/边沿提取捕获、复传递、BW和可靠性；PM原型不等于周期PM认证。|`capture_metrics` / `response_metrics`|
|[pll_allocation/verification/noise.py](../pll_allocation/verification/noise.py)|独立稳态相位PSD/jitter测量、种子统计/区间和验证，不复用M1传递当测量。|`validate_protocol` / `band_integral`|
|[pll_allocation/verification/noise_tracking.py](../pll_allocation/verification/noise_tracking.py)|稳态随机跟踪诊断，与冷启动条件捕获分开。|`terminal_capture` / `steady_tracking`|
|[pll_allocation/verification/nonideal.py](../pll_allocation/verification/nonideal.py)|可选非理想/噪声验证适配，复用原扫描/捕获/收敛链；按职责命名；旧版本标识保留于兼容合同。|`deterministic_measure` / `validate_extension`|
|[pll_allocation/verification/nonideal_noise_identity.py](../pll_allocation/verification/nonideal_noise_identity.py)|可选内核/生成器/适配器/库身份；默认build_nonideal，保留旧显式环境变量。|`default_build` / `identities`|
|[pll_allocation/verification/nonideal_noise_kernel.cpp](../pll_allocation/verification/nonideal_noise_kernel.cpp)|原内核的生成式可选噪声/非理想扩展，包含确定性RNG及电荷/事件记录。|原生源码|
|[pll_allocation/verification/nonideal_noise_native.py](../pll_allocation/verification/nonideal_noise_native.py)|可选噪声/非理想原生扩展适配、噪声强度和输入域校验。|`noise_levels` / `simulate`|
|[pll_allocation/verification/phase_step.py](../pll_allocation/verification/phase_step.py)|相位阶跃的周期平均、衰减/形状及有效性分析，不替代主链捕获协议。|`protocol` / `cycle_average`|
|[pll_allocation/verification/phase_step_kernel.cpp](../pll_allocation/verification/phase_step_kernel.cpp)|由理想内核生成的平滑相位阶跃和事件观测扩展。|原生源码|
|[pll_allocation/verification/phase_step_native.py](../pll_allocation/verification/phase_step_native.py)|可选真实平滑相位阶跃事件后端，Python到ctypes的适配。|`identity` / `simulate_step`|
|[pll_allocation/verification/resources.py](../pll_allocation/verification/resources.py)|查找源码树或安装位置中的唯一活动configs目录。|模块初始化/转发|
|[pll_allocation/verification/return_ratio.py](../pll_allocation/verification/return_ratio.py)|从相位端口注入测得返回比、边带与交叉，保留多交叉/未定状态。|`protocol` / `phasor_fit`|
|[pll_allocation/verification/return_ratio_kernel.cpp](../pll_allocation/verification/return_ratio_kernel.cpp)|保留原动力学的相位端口注入原生扩展。|原生源码|
|[pll_allocation/verification/return_ratio_native.py](../pll_allocation/verification/return_ratio_native.py)|返回比注入的真实事件后端调用与身份校验。|`identity` / `simulate_port`|
|[pll_allocation/verification/return_ratio_validity.py](../pll_allocation/verification/return_ratio_validity.py)|原始信号/反馈分类和返回比证据有效性，保守适配研究结论。|`classify_feedback` / `raw_diagnostics`|
|[pll_allocation/verification/run_suite.py](../pll_allocation/verification/run_suite.py)|复用原成对步长捕获和频响收敛比较，不读取历史suite结果冒充新运行。|`comparison_after_measurement` / `capture_pair`|
|[pll_allocation/verification/scenario.py](../pll_allocation/verification/scenario.py)|冻结研究阈值到原验证器的适配，测量投影与研究Spec重判分别绑定。|`measurement_proposal` / `validate_research_proposal`|
|[pll_allocation/verification/simulator.py](../pll_allocation/verification/simulator.py)|Python/ctypes输入、激励/观测适配及原生执行；不导入M1传递公式。|`validate_parameters` / `simulate`|
|[pll_allocation/verification/verify.py](../pll_allocation/verification/verify.py)|冻结AllocationProposal的独立原M2验收：提案门禁、测量、包络判决和结果。|`frozen_model` / `validate_proposal`|

## 可选研究编排

|文件|基本职责|阅读入口|
|---|---|---|
|[pll_allocation/studies/__init__.py](../pll_allocation/studies/__init__.py)|可选冻结研究编排包，不是生产分配入口。|模块初始化/转发|
|[pll_allocation/studies/ablation.py](../pll_allocation/studies/ablation.py)|M1层反解/尺度/区域消融研究的冻结与执行；不自动启动M2或付费研究。|`utc` / `raw_problem`|
|[pll_allocation/studies/ablation_report.py](../pll_allocation/studies/ablation_report.py)|只读汇总已存消融证据，生成统计表；不执行评价或API。|`median` / `percentile`|
|[pll_allocation/studies/allocation_baselines.py](../pll_allocation/studies/allocation_baselines.py)|冻结目标和等预算首次分配对照，部分保护检查依赖历史材料。|`build_targets` / `benchmark`|
|[pll_allocation/studies/initial_allocation.py](../pll_allocation/studies/initial_allocation.py)|首次分配对照研究的冻结、调度与计时适配，仍使用原执行器，依赖研究输入。|`read` / `sha`|
|[pll_allocation/studies/multi_region.py](../pll_allocation/studies/multi_region.py)|可选单/多区域计划与观察反馈对照编排，使用原Builder/Explorer。|`response` / `deterministic_plan`|
|[pll_allocation/studies/simulated_repairs.py](../pll_allocation/studies/simulated_repairs.py)|显式模拟反馈的修复练习，不能计作真实M2/LLM研究成果。|`simulated_repairs`|

## 旧数值参考与归档工具

|文件|基本职责|阅读入口|
|---|---|---|
|[data/behavioral_space_v1/reference/python_crosscheck.py](../data/behavioral_space_v1/reference/python_crosscheck.py)|独立Python参考数值实现，供已有回归核对；不等于运行MATLAB或PDK。|`simulate` / `kernel`|
|[pll_allocation/_legacy/__init__.py](../pll_allocation/_legacy/__init__.py)|保留旧v1行为兼容/数值回归包。|模块初始化/转发|
|[pll_allocation/_legacy/archive_audit.py](../pll_allocation/_legacy/archive_audit.py)|依赖旧实验资料的交付审计，不属于默认链。|`audit`|
|[pll_allocation/_legacy/archive_report.py](../pll_allocation/_legacy/archive_report.py)|读取历史材料生成归档报告，不产生新验证结论。|`build_report`|
|[pll_allocation/_legacy/evaluation/__init__.py](../pll_allocation/_legacy/evaluation/__init__.py)|旧行为评价器子包。|模块初始化/转发|
|[pll_allocation/_legacy/evaluation/python_behavioral.py](../pll_allocation/_legacy/evaluation/python_behavioral.py)|保留的原Python行为评价器与周期测量，供旧链/独立回归使用。|`measure_cycles` / `PythonBehavioralEvaluator`|
|[pll_allocation/_legacy/physics/__init__.py](../pll_allocation/_legacy/physics/__init__.py)|旧物理辅助子包。|模块初始化/转发|
|[pll_allocation/_legacy/physics/cp.py](../pll_allocation/_legacy/physics/cp.py)|旧相位到时序、充电窗和有符号电荷关系；不作为新事件内核替代。|`phase_to_timing` / `charge_window`|
|[pll_allocation/_legacy/physics/lf.py](../pll_allocation/_legacy/physics/lf.py)|旧环路滤波器算子、阻抗与要求的辅助实现。|`operators` / `impedance`|
|[pll_allocation/_legacy/schemas.py](../pll_allocation/_legacy/schemas.py)|旧行为输入/限制合同校验，供v1适配使用。|`validate_request` / `limits`|
|[pll_allocation/_legacy/units.py](../pll_allocation/_legacy/units.py)|旧有限数值、单位和指标合同错误定义。|`ContractError` / `finite`|

## 兼容入口

|文件|基本职责|阅读入口|
|---|---|---|
|[pll_allocation/agent/experiment_a_plus.py](../pll_allocation/agent/experiment_a_plus.py)|旧调用兼容入口，转发职责模块；不保留独立算法。|模块转发/CLI兼容|
|[pll_allocation/agent/multi_region_study.py](../pll_allocation/agent/multi_region_study.py)|旧调用兼容入口，转发职责模块；不保留独立算法。|模块转发/CLI兼容|
|[pll_allocation/agent/spec_allocation_ablation.py](../pll_allocation/agent/spec_allocation_ablation.py)|旧调用兼容入口，转发职责模块；不保留独立算法。|模块转发/CLI兼容|
|[pll_allocation/agent/spec_allocation_ablation_report.py](../pll_allocation/agent/spec_allocation_ablation_report.py)|旧调用兼容入口，转发职责模块；不保留独立算法。|模块转发/CLI兼容|
|[pll_allocation/agent/stage9.py](../pll_allocation/agent/stage9.py)|旧调用兼容入口，转发职责模块；不保留独立算法。|模块转发/CLI兼容|
|[pll_allocation/block_space/extensions.py](../pll_allocation/block_space/extensions.py)|旧调用兼容入口，转发职责模块；不保留独立算法。|模块转发/CLI兼容|
|[pll_allocation/track_a/__init__.py](../pll_allocation/track_a/__init__.py)|旧调用兼容入口，转发职责模块；不保留独立算法。|模块转发/CLI兼容|
|[pll_allocation/track_a/__main__.py](../pll_allocation/track_a/__main__.py)|旧调用兼容入口，转发职责模块；不保留独立算法。|模块转发/CLI兼容|
|[pll_allocation/track_a/agent.py](../pll_allocation/track_a/agent.py)|旧调用兼容入口，转发职责模块；不保留独立算法。|模块转发/CLI兼容|
|[pll_allocation/track_a/allocate.py](../pll_allocation/track_a/allocate.py)|旧调用兼容入口，转发职责模块；不保留独立算法。|模块转发/CLI兼容|
|[pll_allocation/track_a/audit.py](../pll_allocation/track_a/audit.py)|旧调用兼容入口，转发职责模块；不保留独立算法。|模块转发/CLI兼容|
|[pll_allocation/track_a/benchmark.py](../pll_allocation/track_a/benchmark.py)|旧调用兼容入口，转发职责模块；不保留独立算法。|模块转发/CLI兼容|
|[pll_allocation/track_a/core.py](../pll_allocation/track_a/core.py)|旧调用兼容入口，转发职责模块；不保留独立算法。|模块转发/CLI兼容|
|[pll_allocation/track_a/experiments.py](../pll_allocation/track_a/experiments.py)|旧调用兼容入口，转发职责模块；不保留独立算法。|模块转发/CLI兼容|
|[pll_allocation/track_a/feedback_agent.py](../pll_allocation/track_a/feedback_agent.py)|旧调用兼容入口，转发职责模块；不保留独立算法。|模块转发/CLI兼容|
|[pll_allocation/track_a/physics.py](../pll_allocation/track_a/physics.py)|旧调用兼容入口，转发职责模块；不保留独立算法。|模块转发/CLI兼容|
|[pll_allocation/track_a/repair.py](../pll_allocation/track_a/repair.py)|旧调用兼容入口，转发职责模块；不保留独立算法。|模块转发/CLI兼容|
|[pll_allocation/track_a/report.py](../pll_allocation/track_a/report.py)|旧调用兼容入口，转发职责模块；不保留独立算法。|模块转发/CLI兼容|
|[pll_allocation/track_a/runner.py](../pll_allocation/track_a/runner.py)|旧调用兼容入口，转发职责模块；不保留独立算法。|模块转发/CLI兼容|
|[pll_allocation/verification/build_closed_loop.cmd](../pll_allocation/verification/build_closed_loop.cmd)|旧调用兼容入口，转发职责模块；不保留独立算法。|模块转发/CLI兼容|
|[pll_allocation/verification/closed_loop.py](../pll_allocation/verification/closed_loop.py)|旧调用兼容入口，转发职责模块；不保留独立算法。|模块转发/CLI兼容|
|[pll_allocation/verification/closed_loop_native.py](../pll_allocation/verification/closed_loop_native.py)|旧调用兼容入口，转发职责模块；不保留独立算法。|模块转发/CLI兼容|
|[pll_allocation/verification/research.py](../pll_allocation/verification/research.py)|旧调用兼容入口，转发职责模块；不保留独立算法。|模块转发/CLI兼容|
|[pll_allocation/verification/stage6c.py](../pll_allocation/verification/stage6c.py)|旧调用兼容入口，转发职责模块；不保留独立算法。|模块转发/CLI兼容|
|[pll_allocation/verification/stage6c_identity.py](../pll_allocation/verification/stage6c_identity.py)|旧调用兼容入口，转发职责模块；不保留独立算法。|模块转发/CLI兼容|
|[pll_allocation/verification/stage6c_native.py](../pll_allocation/verification/stage6c_native.py)|旧调用兼容入口，转发职责模块；不保留独立算法。|模块转发/CLI兼容|

## 维护工具

|文件|基本职责|阅读入口|
|---|---|---|
|[tools/audit_architecture.py](../tools/audit_architecture.py)|只读核对正式依赖方向及六份原分配算法的SHA，输出审计JSON。|`audit`|
|[tools/run_allocation_examples.py](../tools/run_allocation_examples.py)|读取公开输入，生成配置并子进程调用正式 Pipeline；汇总联合交付状态和首点/目标时间，真实 API 需显式授权，不依赖历史结果。|`run_cases` / `main`|
|[tests/test_allocation_examples.py](../tests/test_allocation_examples.py)|复现输入有效性、唯一 CLI、授权/环境预检、防覆盖和失败保留。|`test_all_public_examples_use_valid_current_inputs`|
|[tools/build_block_relation_atlas.py](../tools/build_block_relation_atlas.py)|由原反解/M1整理变量关系、条件域及数值核对，输出JSON/CSV/HTML；无M2/LLM。|`read` / `write`|
|[tools/create_verification_profiles.py](../tools/create_verification_profiles.py)|向显式全新目录生成17份预声明profile/协议及manifest，不修改活动配置。|`documents`|
|[tools/generate_nonideal_noise_kernel.py](../tools/generate_nonideal_noise_kernel.py)|由同一理想kernel生成可选噪声/非理想C++源码；拒绝覆盖已有生成文件。|`source`|
|[tools/generate_phase_step_kernel.py](../tools/generate_phase_step_kernel.py)|由理想kernel生成相位阶跃观测C++扩展；正常编译无需重新生成。|`source`|

## 维护测试与测试参考

|文件|基本职责|阅读入口|
|---|---|---|
|[tests/fixtures/verification/python_crosscheck.py](../tests/fixtures/verification/python_crosscheck.py)|明确标为测试参考的独立Python数值核对实现，不是新仿真产物。|`simulate` / `kernel`|
|[tests/test_agent_handoff.py](../tests/test_agent_handoff.py)|预算、停止和交接不变量；Policy明确标为TEST。|`context` / `config`|
|[tests/test_agent_state.py](../tests/test_agent_state.py)|Planner/候选选择/状态不变量及可选历史回放；缺档案显式跳过。|`histories` / `context`|
|[tests/test_allocation_baselines.py](../tests/test_allocation_baselines.py)|反解、必要条件证书、确定性基线与原M1一致性。|`model` / `spec`|
|[tests/test_architecture.py](../tests/test_architecture.py)|正式依赖、旧导入等价、数值源保护、构建拒覆盖及超时计费。|`test_legacy_import_is_same_formal_module` / `test_dependency_direction_and_frozen_numerical_implementations`|
|[tests/test_behavioral.py](../tests/test_behavioral.py)|旧行为内核的字节保护、独立数值锚点及不合格结果不得PASS。|`test_independent_corrected_matlab_anchors` / `test_extracted_files_remain_byte_identical`|
|[tests/test_block_relation_atlas.py](../tests/test_block_relation_atlas.py)|关系图谱的条件域、严格调谐边界、KCL核对和防覆盖。|`inputs` / `test_every_original_variable_has_relations_and_no_new_independent_axis`|
|[tests/test_block_space_v1.py](../tests/test_block_space_v1.py)|冻结Block Space合同、域/异常和真实短事件执行检查。|`model` / `test_experiment_and_domain_exactly_preserve_stage1`|
|[tests/test_computational_window.py](../tests/test_computational_window.py)|计算窗口、尺度来源、域扩展和真实证据注册；测试不发真实API。|`template` / `decision_state`|
|[tests/test_config_layout.py](../tests/test_config_layout.py)|活动配置安装目录、迁移/profile身份和生成器拒覆盖。|`test_all_active_json_configs_are_installed_in_their_own_directory` / `test_relocated_configs_and_profiles_match_recorded_identity`|
|[tests/test_contracts.py](../tests/test_contracts.py)|旧v1问题/完整候选合同、非法输入拒绝。|`problem` / `test_declared_spaces_and_full_candidates`|
|[tests/test_exploration.py](../tests/test_exploration.py)|连续Spec/变量域更改、正式M1校准与未支持状态。|`raw` / `small`|
|[tests/test_initial_allocation.py](../tests/test_initial_allocation.py)|物理区域/种子、六轴边界、增益调谐交集和正式M1预算。|`config` / `problem`|
|[tests/test_joint_allocation.py](../tests/test_joint_allocation.py)|联合指标的来源/边界/失败及UNKNOWN处理；合成M2夹具不作研究证据。|`problem` / `initial`|
|[tests/test_llm_planning.py](../tests/test_llm_planning.py)|真实接口周边的Planner状态、动作与错误合同；单测Policy均为TEST。|`contexts` / `config`|
|[tests/test_m1.py](../tests/test_m1.py)|M1物理/数值性质、独立多项式和KCL、增益等价及适用域门禁。|`exp` / `parameters`|
|[tests/test_noise_mapping.py](../tests/test_noise_mapping.py)|连续M1噪声的单位、独立KCL、极限、积分与不可外推边界。|`inputs` / `test_transfer_limits_and_units`|
|[tests/test_nonideal_allocation.py](../tests/test_nonideal_allocation.py)|可选联合噪声/非理想约束、统计来源、优化和未知判决。|`inputs` / `synthetic`|
|[tests/test_physics_registry.py](../tests/test_physics_registry.py)|关系索引、源/版本绑定、证据不可混用及有限数值扫描的结论边界。|`test_index_only_enables_exact_formal_constraints_and_never_executes` / `test_registry_rejects_source_version_semantic_or_scope_changes`|
|[tests/test_pipeline.py](../tests/test_pipeline.py)|冻结兼容链资产、版本、M2反馈和失败状态；夹具不冒充新M2。|`fixture_result` / `test_frozen_assets_and_packaged_kernel_are_identical`|
|[tests/test_execution_routes.py](../tests/test_execution_routes.py)|新版默认/显式兼容分流、参数误用、部分结果失败退出及嵌套策略一致性。|`test_default_and_problem_only_dispatch_new_multi_candidate`|
|[tests/test_region_executor.py](../tests/test_region_executor.py)|真实M1的区域探测/SLSQP、缓存、预算、非法提案和停止。|`contexts` / `decision`|
|[tests/test_region_planning.py](../tests/test_region_planning.py)|多区域/工具提案校验与真实M1执行；TEST Policy不计为LLM成果。|`config` / `initial`|
|[tests/test_release_interfaces.py](../tests/test_release_interfaces.py)|职责名称与旧模块/CLI参数转发同一实现。|`test_module_compatibility` / `test_initial_cli_dispatches_unchanged_arguments`|
|[tests/test_runner.py](../tests/test_runner.py)|旧Runner先写候选、失败再分配、预算/异常计费及禁止覆盖。|`SavingProbe` / `test_first_proposal_saved_before_tb`|
|[tests/test_study_contracts.py](../tests/test_study_contracts.py)|可选对照编排的停止钩子、共享guard、距离和预算不变量。|`test_stop_records_and_caches_before_ending_stream` / `test_stop_during_slsqp_does_not_spend_independent_recheck`|
|[tests/test_verification_feedback.py](../tests/test_verification_feedback.py)|Handoff/M2/策略故障注入、反馈重分配预算；TEST M2不作真实研究证据。|`saved` / `config`|
|[tests/verification/test_measurements.py](../tests/verification/test_measurements.py)|真实原生内核/边沿、独立复响应拟合和测量不可伪造。|`protocol` / `test_native_unmodulated_equations_regress_existing_python`|
|[tests/verification/test_noise.py](../tests/verification/test_noise.py)|原生噪声统计、源独立性、RNG重复性、置信区间和推断边界。|`samples` / `test_physical_source_variances_dt_repeatability_and_independence`|
|[tests/verification/test_nonideal.py](../tests/verification/test_nonideal.py)|生成/身份绑定、零扩展回归、非理想电荷/边沿及步长机制。|`data` / `test_generated_reproducible_and_build_bound`|
|[tests/verification/test_phase_response.py](../tests/verification/test_phase_response.py)|真实相位阶跃、原更新源保持、响应有效性与衰减UNKNOWN门禁。|`test_zero_step_original_three_paths_are_identical` / `test_generated_extension_preserves_frozen_update_source`|
|[tests/verification/test_return_ratio.py](../tests/verification/test_return_ratio.py)|真实端口注入、拟合/交叉和不能虚报认证的边界。|`test_zero_injection_preserves_original_event_path_exactly` / `test_complex_fit_retains_phase_sign_and_dc_trend`|
|[tests/verification/test_tracking.py](../tests/verification/test_tracking.py)|合成/已存轨迹的稳态跟踪协议判决，区别于冷捕获。|`fixture` / `test_zero_tracking_and_white_frequency_is_not_coldcapture`|
|[tests/verification/test_verification.py](../tests/verification/test_verification.py)|正式M2提案门禁、原生验证、测量包络和不可靠轨迹不能PASS。|`protocol` / `test_integer_startup_slips_do_not_preclude_terminal_lock`|

## 仅本地交互层与档案测试

以下文件保留在本地工作区，未纳入本次GitHub共享源码；名字用代码文字展示，避免给远端读者提供不存在的链接。

|本地文件|作用/为什么不随核心发布|
|---|---|
|`streamlit_app.py`|Streamlit页面、输入、状态、真实结果/轨迹展示与下载；不实现求解器|
|`pll_allocation/ui_adapter.py`|显示单位到SI、表单校验、后端合同转换和按来源结果展示|
|`pll_allocation/ui_runner.py`|单击单运行、独立run目录、正式CLI子进程调度、状态与日志加载|
|`tests/test_gui.py`|本地GUI输入、边界、状态和调度兼容；本轮20项通过|
|`tests/test_matlab_trajectories.py`|历史MATLAB轨迹对照，依赖未发布轨迹|
|`tests/test_scenarios_stage5.py`|旧冻结场景/实验验收，依赖历史材料|
|`tests/test_joint_verification.py`|旧联合M2执行记录回归，依赖历史档案|
|`tests/test_multi_region_planning.py`|历史多区域研究冻结输入/轨迹验收|
|`tests/test_spec_allocation_ablation.py`|已冻结消融研究输入和产物回归|
|`tests/test_window_contract_fix.py`|旧窗口合同修复场景/档案重放|

不包含 `.venv`、构建目录、缓存、历史实验中的源码副本和本地审计/发布辅助脚本。它们不是当前需审查的维护代码清单。

## 非代码入口

`pyproject.toml` 定义依赖、CLI与安装资源；四个原生构建脚本已在上表逐项说明。活动 JSON 按 [configs说明](../configs/README.md) 分类，包括问题、策略、Provider、复现输入、冻结模型/协议、基线和来源收据。运行结果均应写入全新 experiments 目录，不是活动配置。

历史共享版回归750项通过、10项缺历史档案明确跳过；本次命名迁移验收见RUNNING。单测中TEST/mock、夹具和旧回放都不能算真实API或新行为仿真。验收命令、真实M1/M2与能力限制见 [RUNNING](RUNNING.md)。
