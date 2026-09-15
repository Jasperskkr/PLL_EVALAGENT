# SystemSpec-to-BlockSpec Agent 初步架构设计

> 文档状态：长期架构蓝图 / 历史设计稿。本文描述的完整平台并未全部实现；V1 的有效执行路径以 [v1_framework_architecture_reviewed.md](v1_framework_architecture_reviewed.md) 和当前代码为准。

> 文档状态：初步 Framework Design Draft  
> 适用阶段：V1 方法验证，可逐步扩展到 V2/V3 和真实工程数据  
> 当前原则：先设计稳定的数据与验证接口，再实现 Agent 能力  
> 本文不包含实现代码，提交后等待框架审核。

> 修订说明：本文保留为长期架构蓝图。针对 V1 的语义边界和最小 execution path，请以 [v1_framework_architecture_reviewed.md](v1_framework_architecture_reviewed.md) 为准。

## 1. 设计目标

项目要解决的核心任务是：

~~~text
System Specification
        ↓
Behavioral Design Space
        ↓
Block Specification Allocation
        ↓
System / Block Validation
        ↓
Validated Block Specifications
~~~

这里的输出不是唯一的 Block Spec，而是经过验证的 preferred feasible solution：

~~~text
C* ∈ { C | System(C) satisfies SystemSpec
          and every block is feasible in its system context }
~~~

架构需要同时支持两个核心问题：

- Problem 1：如何构造一个最小但足够的 behavioral design space；
- Problem 2：如何在这个 design space 中搜索满足系统要求的 block-spec allocation。

架构还需要满足以下长期要求：

1. V1 可在两周级别完成最小闭环；
2. Agent 的推理与 simulator、optimizer、evaluator 解耦；
3. 可以把 MATLAB synthetic backend 替换为 Spectre、SPICE 或工程数据；
4. 可以从单个 VCO 扩展到多个 PLL blocks；
5. 可以从 PLL domain pack 扩展到其他模拟/混合信号电路；
6. 所有关键结论可追溯、可复现、可独立重放。

---

## 2. 非目标

V1 不做：

- 自动发现任意 PLL architecture；
- transistor sizing；
- layout；
- transistor-level accuracy 承诺；
- 大规模 multi-agent framework；
- 让 LLM 直接计算 sensitivity；
- 让 Agent 修改 System Spec 或 pass criteria；
- 只依靠 LLM 判断 PASS/FAIL。

V1 的 Agent 只是 search-space controller 和 behavioral-contract reasoner，不是 simulator、numerical optimizer 或 signoff tool。

---

## 3. 总体分层架构

建议采用四层结构。

~~~text
┌──────────────────────────────────────────────────────────────┐
│ Layer 4: User / CLI / Report / Visualization                 │
├──────────────────────────────────────────────────────────────┤
│ Layer 3: Agent Reasoning and Workflow Orchestration           │
│   Problem 1 Agent | Problem 2 Agent | Failure Router          │
├──────────────────────────────────────────────────────────────┤
│ Layer 2: Deterministic Experiment and Evaluation Core         │
│   SystemTB | BlockTB | Sweep | Sensitivity | Feasibility      │
├──────────────────────────────────────────────────────────────┤
│ Layer 1: Data Contracts and Backend Adapters                  │
│   Schemas | Units | Provenance | MATLAB | SPICE | Engineering  │
├──────────────────────────────────────────────────────────────┤
│ Layer 0: Domain Pack                                            │
│   PLL architecture | VCO | CP/LF | Divider | Metric semantics │
└──────────────────────────────────────────────────────────────┘
~~~

其中：

- Layer 0 描述领域知识；
- Layer 1 定义统一数据和 backend 协议；
- Layer 2 产生所有可验证的数值事实；
- Layer 3 根据事实提出结构化动作；
- Layer 4 展示结果、轨迹和报告。

最重要的依赖方向是：

~~~text
Agent → Orchestrator → Deterministic Core → Backend
                         ↓
                      Evaluator
~~~

Agent 不应直接修改 backend 或绕过 evaluator。

---

## 4. 核心模块架构

### 4.1 Schema Registry and Validator

职责：

- 定义所有跨模块数据结构；
- 校验单位、类型、范围、枚举值和引用关系；
- 检查 Contract dependency 是否指向存在的 Field；
- 检查 Block Spec 是否落在 Contract validity 内；
- 为每次运行记录 schema version；
- 拒绝非法 Agent action。

输入：

- YAML/JSON 文件；
- Agent action；
- backend result；
- evaluation result。

输出：

- validated object；
- validation errors；
- warnings；
- schema version。

这一层必须与 LLM 无关，并且可以独立运行。

### 4.2 Domain Pack Registry

Domain Pack 是把通用框架映射到特定电路领域的插件。

PLL domain pack 初始包含：

- Integer-N CPPLL architecture；
- PFD/CP block；
- Loop Filter block；
- VCO block；
- Divider block；
- PLL system metrics；
- VCO context definitions；
- PLL-specific residual semantics；
- PLL-specific BlockTB checks。

未来可增加：

- Fractional-N PLL；
- ADPLL；
- CDR；
- ADC；
- LDO；
- SerDes；
- bandgap；
- operational amplifier。

通用 core 不应依赖具体 PLL 字段；具体字段应由 domain pack 提供。

### 4.3 Architecture Model

V1 中 architecture model 是固定的，不由 Agent 自动生成。

建议表示为：

~~~text
Architecture
  ├── blocks
  │     ├── PFD_CP
  │     ├── LoopFilter
  │     ├── VCO
  │     └── Divider
  ├── connections
  ├── feedback_paths
  ├── fixed_parameters
  └── assumptions
~~~

Architecture model 负责说明：

- 有哪些 blocks；
- block 之间的 signal path；
- feedback path；
- 哪些参数固定；
- 哪些 block 暴露 behavioral variables；
- 哪些 block 之间存在潜在 coupling。

### 4.4 Behavioral Contract Store

保存 Contract 的版本化对象：

~~~text
contract_v0
contract_v1
contract_v2
...
~~~

每次修改都记录：

- previous contract id；
- action；
- evidence ids；
- agent role；
- validator result；
- prediction error before/after；
- validity changes；
- dependency graph changes。

Contract 不只是字段列表，还包括：

- variables；
- contexts；
- dependencies；
- valid operating envelope；
- evaluation methods；
- calibration metadata；
- uncertainty；
- fidelity level。

### 4.5 Block Specification Store

保存候选 Block Specs 和最终 Block Spec：

~~~text
initial_vco_spec
candidate_vco_spec_001
candidate_vco_spec_002
final_vco_spec
~~~

每个候选规格都必须关联：

- originating system evaluation；
- residual；
- sensitivity；
- allocation action；
- BlockTB result；
- system re-evaluation；
- feasibility margin。

### 4.6 Backend Adapter Layer

所有仿真和工程数据通过统一 backend interface 接入。

初始 backend：

~~~text
MatlabBehavioralBackend
~~~

未来 backend：

~~~text
PythonAnalyticalBackend
SpectreBackend
SPICEBackend
VerilogABackend
EngineeringDataBackend
SiliconMeasurementBackend
~~~

backend 只负责执行和返回事实，不负责决定 Contract 是否合理，也不负责选择下一步规格。

### 4.7 Experiment Manager

职责：

- 创建 characterization、system evaluation、sweep 和 validation job；
- 分配 run id、experiment id、seed 和 budget；
- 记录输入快照；
- 调用 backend；
- 保存原始输出；
- 触发 post-processing；
- 支持重放和失败恢复。

建议所有实验都使用统一结构：

~~~text
ExperimentRequest
  → Backend execution
  → RawArtifact
  → NormalizedResult
  → Evaluator
  → Evidence
~~~

### 4.8 SystemTB

输入：

- SystemSpec；
- Architecture Model；
- current Block Specs；
- Behavioral Contracts；
- backend configuration；
- initial condition；
- simulation budget。

输出：

- system metrics；
- residuals；
- pass/fail；
- block operating context；
- raw waveform or spectrum references；
- warnings；
- run metadata。

V1 至少输出：

~~~yaml
metrics:
  output_frequency: ...
  integrated_jitter: ...
  lock_time: ...
  power: ...

residuals:
  output_frequency: ...
  integrated_jitter: ...
  lock_time: ...
  power: ...

context:
  VCO:
    vctrl_min: ...
    vctrl_max: ...
    fosc_min: ...
    fosc_max: ...
~~~

### 4.9 Block Characterization / BlockTB

Block Characterization 的目标是得到可用于 Contract 的 raw behavioral data。

VCO V1 至少支持：

- DC / static sweep：fosc、Kvco、power；
- TRAN：锁定前后控制电压和瞬态；
- PSS-like steady-state characterization；
- PNOISE-like behavioral phase-noise evaluation。

BlockTB 的目标不同于 characterization：

> 给定 Candidate BlockSpec 和 System Context，判断这个 spec 是否在整个 operating envelope 中成立。

输出：

- measured fields；
- envelope coverage；
- constraint results；
- margin；
- feasible / infeasible；
- failure locations；
- evidence references。

### 4.10 Sweep and Sensitivity Engine

职责：

- deterministic parameter sweep；
- finite difference；
- DOE；
- local/global sensitivity；
- contribution approximation；
- uncertainty propagation；
- simulation budget accounting。

约束：

- sensitivity 不由 Agent 猜测；
- sweep 点、步长、seed 和版本必须记录；
- 不允许只用 nominal point 代替 operating envelope；
- 需要输出 metric 对 block variable 的方向和数值。

### 4.11 Residual and Feasibility Evaluator

职责：

- 根据只读 SystemSpec 计算 residual；
- 计算 pass/fail；
- 判断 BlockTB feasibility；
- 计算 margin；
- 检查 context coverage；
- 生成独立 validation report。

建议 residual 统一采用带方向的规范：

~~~text
upper_bound metric:
  residual = observed - target

lower_bound metric:
  residual = target - observed

range metric:
  residual = distance_to_valid_interval
~~~

最终 PASS/FAIL 只能由该模块或其受控子模块生成。

### 4.12 Failure Router

Failure Router 不是替代 Agent 的第三个设计 Agent，而是一个先确定性、后可解释的路由模块。

输入：

- residual；
- sensitivity；
- contract prediction error；
- block feasibility；
- dependency consistency；
- iteration history；
- simulation errors；
- context coverage。

输出：

~~~text
continue_optimization
refine_abstraction
invalid_candidate
backend_failure
budget_exhausted
system_pass
~~~

V1 可以先使用规则：

- 有改善方向、有可行 block range、prediction 一致：continue_optimization；
- system mismatch 与 context/dependency 强相关：refine_abstraction；
- candidate 超出 validity 或 BlockTB fail：invalid_candidate；
- backend 无结果：backend_failure；
- budget 用尽：budget_exhausted。

后续再让 Agent 对 router 的证据进行解释，但不能绕过确定性分类。

### 4.13 Trajectory and Provenance Store

每次动作都记录 JSONL event：

~~~text
run_started
contract_created
characterization_completed
contract_mismatch_detected
contract_action_proposed
contract_action_validated
contract_refined
system_evaluated
sensitivity_completed
allocation_action_proposed
candidate_spec_validated
block_tb_completed
system_re_evaluated
failure_routed
run_finished
~~~

每个 event 记录：

- timestamp；
- run id；
- parent event；
- input artifact ids；
- output artifact ids；
- agent role；
- action；
- evidence ids；
- deterministic result；
- model/backend version；
- simulation count。

---

## 5. 两个 Agent 的设计

### 5.1 Problem 1 Agent：Behavioral Contract Agent

职责：

- 发现候选 variables；
- 分类 field role；
- 选择必要 context；
- 提出 dependency；
- 选择 evaluation method；
- 判断 scalar、function、profile；
- 提出 Contract Refinement；
- 解释 prediction/observation discrepancy。

输入：

~~~text
SystemSpec
ArchitectureModel
CurrentBehavioralContract
BlockCharacterizationSummary
PredictionVsObservation
ContextCoverage
DependencyGraph
ValidityViolations
History
~~~

输出不是任意文本，而是结构化 ContractAction：

~~~yaml
action_type: add_context
target: VCO.phase_noise
value: Vctrl
reason: prediction_error_correlates_with_vctrl
evidence_ids:
  - characterization_run_017
confidence: medium
requires_revalidation: true
~~~

支持的 action：

~~~text
add_variable
remove_variable
add_context
remove_context
add_dependency
remove_dependency
modify_dependency
modify_validity
change_representation
split_block
merge_block
request_more_characterization
~~~

它不能：

- 修改 System Spec；
- 修改 evaluator；
- 直接写入 Contract Store；
- 直接宣布 refinement 成功；
- 伪造 observation。

真正的流程是：

~~~text
Agent proposes action
        ↓
Schema validator
        ↓
Action policy checker
        ↓
Contract candidate generated
        ↓
Characterization / validation
        ↓
Evaluator accepts or rejects
        ↓
Contract version committed
~~~

### 5.2 Problem 2 Agent：Specification Allocation Agent

职责：

- 根据 residual 识别失败指标；
- 结合 sensitivity 判断杠杆变量；
- 结合 contribution 判断 block bottleneck；
- 结合 block feasibility 和 margin 分配规格；
- 选择下一搜索区域；
- 提议 tighten、relax、keep 或 adjust_range。

输入：

~~~text
SystemSpec
BehavioralContracts
CurrentBlockSpecs
SystemMetrics
Residuals
Sensitivity
Contribution
Margins
BlockFeasibility
History
SimulationBudget
~~~

输出：

~~~yaml
action_type: adjust_range
target_block: VCO
target_field: phase_noise_1MHz
new_range:
  upper_bound: -112
reason: jitter_residual_positive_and_vco_pn_has_high_sensitivity
evidence_ids:
  - system_eval_004
  - sensitivity_004
  - block_tb_003
confidence: medium
~~~

支持的 action：

~~~text
tighten
relax
keep
adjust_range
select_next_search_region
request_more_sensitivity
request_more_block_characterization
~~~

它不能：

- 改 System Spec；
- 改 pass criteria；
- 直接宣称 candidate 可行；
- 代替 numerical optimizer；
- 把 BlockTB 未验证的 spec 作为最终输出。

### 5.3 V1 的 Agent 运行形态

V1 不需要两个独立的复杂服务。建议：

~~~text
One Agent Runtime
  ├── Problem1 task context
  └── Problem2 task context
~~~

两种 task context 使用不同：

- system prompt；
- allowed actions；
- input schema；
- output schema；
- validation policy；
- evidence requirements。

这样既验证两个 Agent 角色，又避免 V1 过早引入 multi-agent 通信复杂度。

V2 可以拆成独立 services；V3 再研究 architecture agent 和 adaptive partition agent。

---

## 6. Orchestrator 设计

Orchestrator 是整个闭环的状态机，不负责替代领域 Agent。

### 6.1 状态机

~~~text
INIT
  ↓
LOAD_SYSTEM_SPEC
  ↓
LOAD_ARCHITECTURE
  ↓
CREATE_OR_LOAD_CONTRACT
  ↓
PROBLEM1_CHARACTERIZATION
  ↓
CONTRACT_VALIDATION
  ├── insufficient → PROBLEM1_REFINE
  └── sufficient   → PROBLEM2_EVALUATION
                         ↓
                   SYSTEM_EVALUATION
                         ↓
                   SENSITIVITY
                         ↓
                   PROBLEM2_ALLOCATE
                         ↓
                   BLOCK_FEASIBILITY
                    ├── fail → PROBLEM2_REVISE
                    └── pass → SYSTEM_RE_EVALUATION
                                      ↓
                                FAILURE_ROUTER
                              ├── optimize
                              ├── refine abstraction
                              ├── stop pass
                              └── stop budget
~~~

### 6.2 Orchestrator 的职责

- 加载和冻结 run configuration；
- 调用 Agent；
- 验证 Agent action；
- 调用 deterministic tools；
- 维护 simulation budget；
- 写入 trajectory；
- 处理重试和失败；
- 将 Failure Router 的结果转换为下一状态；
- 生成最终 report。

### 6.3 Orchestrator 不做的事

- 不直接决定某个 circuit metric 的真假；
- 不修改 System Spec；
- 不允许 Agent 跳过 BlockTB；
- 不把自然语言解释作为 PASS 证据；
- 不把一次 nominal simulation 当成 robust feasibility。

---

## 7. 统一数据流

### 7.1 Problem 1 数据流

~~~text
SystemSpec + Architecture + Initial Contract
                     ↓
          Characterization Planner
                     ↓
                Backend
                     ↓
          Raw Characterization Data
                     ↓
        Normalization / Unit Conversion
                     ↓
          Contract Prediction Engine
                     ↓
      Prediction vs Observation Diagnostics
                     ↓
           Problem 1 Contract Agent
                     ↓
              Contract Action
                     ↓
        Validator + Re-characterization
                     ↓
             Validated Contract
~~~

### 7.2 Problem 2 数据流

~~~text
SystemSpec + Validated Contract + Current BlockSpec
                         ↓
                      SystemTB
                         ↓
              Metrics + Residuals + Context
                         ↓
                 Sensitivity / Contribution
                         ↓
                Problem 2 Allocation Agent
                         ↓
                    Candidate Spec
                         ↓
                     BlockTB
                         ↓
                    Feasible / Infeasible
                         ↓
                    SystemTB Re-run
                         ↓
                     Failure Router
~~~

### 7.3 外层双闭环

~~~text
Problem 1 Contract
        ↓
Problem 2 Allocation
        ↓
System / Block Evaluation
        ↓
Evidence
        ↓
Failure Router
   ┌────┴────┐
   ↓         ↓
Problem 2  Problem 1
continue   refine
~~~

---

## 8. Backend 接口设计

推荐统一抽象接口：

~~~text
characterize_block(request) -> CharacterizationResult
evaluate_system(request) -> SystemEvaluationResult
extract_context(system_result) -> OperatingContext
run_sweep(request) -> SweepResult
validate_block_spec(request) -> BlockFeasibilityResult
~~~

所有 backend 必须返回：

- normalized metrics；
- raw artifact references；
- units；
- context；
- status；
- warnings；
- fidelity level；
- backend version；
- provenance；
- reproducibility metadata。

### 8.1 MatlabBehavioralBackend

V1 首选。

职责：

- 执行 MATLAB function/script；
- 读取 JSON/CSV/MAT 配置；
- 生成 raw simulation output；
- 返回结构化 result；
- 不包含 Agent 逻辑。

### 8.2 EngineeringDataBackend

未来用于：

- measured VCO curves；
- phase-noise tables；
- PVT characterization；
- silicon measurement；
- lab data。

需要额外支持：

- data source id；
- instrument metadata；
- calibration version；
- uncertainty；
- missing data；
- interpolation policy；
- outlier policy。

### 8.3 Circuit Simulator Backend

未来用于：

- Spectre/SpectreRF；
- SPICE；
- Verilog-A/AMS；
- other EDA tools。

上层 Agent、SystemTB、BlockTB、Evaluator 应尽量不感知具体 simulator 命令，只看到统一结果协议。

### 8.4 Multi-fidelity

backend result 应标记：

~~~text
synthetic
analytical
behavioral
circuit_simulation
engineering_measurement
silicon_measurement
~~~

同一个 Contract 可以记录不同 fidelity 的 evidence，但不能混淆证据等级。

---

## 9. 通用 Schema 设计

建议最小 schema 集合：

~~~text
system_spec.yaml
architecture.yaml
behavioral_contract.yaml
block_spec.yaml
operating_context.yaml
experiment_request.json
experiment_result.json
system_evaluation.json
block_feasibility.json
sensitivity.json
agent_action.json
trajectory.jsonl
run_manifest.json
~~~

### 9.1 SystemSpec

字段：

- spec id；
- architecture；
- metrics；
- direction；
- target；
- tolerance；
- integration band；
- pass criteria；
- immutable flag；
- source/provenance。

### 9.2 BehavioralContract

字段：

- contract id；
- version；
- block id；
- fields；
- contexts；
- dependency graph；
- validity envelope；
- evaluation taxonomy；
- fidelity；
- calibration metadata；
- parent contract；
- evidence ids。

### 9.3 BlockSpec

字段：

- spec id；
- block id；
- requirement fields；
- range；
- target；
- context scope；
- hard/soft flag；
- source evaluation；
- feasibility evidence；
- margin。

### 9.4 OperatingContext

字段：

- context id；
- block id；
- variable ranges；
- joint distribution or correlated envelope；
- extraction method；
- system run id；
- coverage confidence。

不能只保存各个变量的独立 min/max；如果存在相关性，需要保留 joint samples 或 correlated envelope。

### 9.5 AgentAction

字段：

- action id；
- agent role；
- action type；
- target；
- proposed change；
- reason；
- evidence ids；
- confidence；
- requested validation；
- policy result；
- final acceptance。

### 9.6 Evidence

每个结论都应能追溯到 evidence：

- raw artifact；
- normalized result；
- experiment id；
- evaluator version；
- input snapshot；
- output metric；
- uncertainty；
- source fidelity。

---

## 10. 面向未来多电路扩展的设计

### 10.1 通用核心和 Domain Pack 分离

通用 core 处理：

- schemas；
- units；
- orchestration；
- experiment execution；
- residual；
- sensitivity；
- feasibility；
- trajectory；
- provenance；
- agent action policy。

Domain pack 处理：

- architecture；
- block library；
- field vocabulary；
- metric semantics；
- context extraction；
- behavioral equations；
- validation rules；
- common dependencies。

### 10.2 新电路接入流程

未来接入 ADC、LDO 或 SerDes 时，不应重写整个 Agent framework，而应新增：

~~~text
domains/<domain_name>/
  architecture definitions
  block definitions
  metric definitions
  context definitions
  backend mappings
  domain validators
  benchmark cases
~~~

### 10.3 跨领域 Agent 能力

Problem 1 的通用动作可以保持不变：

~~~text
add/remove variable
add/remove context
modify dependency
modify validity
change representation
~~~

Problem 2 的通用动作也可以保持不变：

~~~text
tighten
relax
keep
adjust_range
select_next_search_region
~~~

变化主要来自 domain pack 的 field vocabulary、metric semantics 和 backend mapping。

---

## 11. 面向真实工程数据的扩展

### 11.1 上层可保持不变的模块

使用统一 schema 和 backend 协议后，下列模块原则上可以保持：

- SystemSpec schema；
- BehavioralContract schema；
- BlockSpec schema；
- Agent action schema；
- Orchestrator；
- Residual engine；
- Sensitivity interface；
- Failure Router；
- Trajectory and provenance；
- Report generation；
- Independent evaluator。

### 11.2 需要替换或扩展的模块

- MatlabBehavioralBackend；
- raw data normalization；
- calibration；
- uncertainty model；
- PVT/corner management；
- measurement data ingestion；
- runtime and license management；
- simulator-specific failure handling；
- model validation and correlation。

### 11.3 工程数据的额外要求

真实工程数据必须包含：

- source；
- timestamp；
- process/corner；
- temperature；
- supply；
- instrument or simulator version；
- calibration status；
- uncertainty；
- data quality；
- extrapolation policy；
- confidentiality/provenance label。

不能把 synthetic data 和 silicon data 在报告中混为同一等级。

---

## 12. V1 范围和执行流程

### 12.1 V1 固定范围

- Architecture：Integer-N CPPLL；
- Target Block：VCO；
- PFD/CP、Loop Filter、Divider：固定参数或简化模型；
- Backend：MatlabBehavioralBackend；
- Agent runtime：一个 runtime，两个 task context；
- Optimizer：deterministic heuristic baseline；
- Sensitivity：finite difference；
- Output：YAML/JSON/CSV/MAT、plots、trajectory。

### 12.2 V1 执行命令目标

~~~text
python run_demo.py --case vco_demo_01
~~~

### 12.3 V1 运行过程

1. 加载 SystemSpec；
2. 加载 fixed Integer-N architecture；
3. 生成 Contract v0；
4. VCO characterization；
5. 验证 Contract v0；
6. 发现至少一次 deficiency；
7. Problem 1 Agent 提出 refinement；
8. evaluator 接受或拒绝 refinement；
9. 得到 validated VCO Contract；
10. 使用 initial VCO Spec 运行 SystemTB；
11. 输出 metrics、residuals、context；
12. 运行 deterministic sensitivity；
13. Problem 2 Agent 提出新的 VCO Spec；
14. 运行 context-aware VCO BlockTB；
15. 重新运行 SystemTB；
16. Failure Router 决定继续优化、返回 Problem 1 或结束；
17. 输出 final_vco_contract.yaml、final_vco_spec.yaml 和 report。

---

## 13. 推荐的仓库布局

建议后续采用：

~~~text
PLL_AGENT/
├── project_prompt.md
├── project_understanding_and_literature_review.md
├── docs/
│   ├── v1_framework_design.md
│   ├── benchmark_contract.md
│   └── research_notes/
├── schemas/
│   ├── system_spec.schema.yaml
│   ├── architecture.schema.yaml
│   ├── behavioral_contract.schema.yaml
│   ├── block_spec.schema.yaml
│   ├── agent_action.schema.yaml
│   └── evaluation.schema.yaml
├── core/
│   ├── schema_validation/
│   ├── orchestration/
│   ├── residuals/
│   ├── sensitivity/
│   ├── feasibility/
│   └── provenance/
├── agents/
│   ├── abstraction_agent/
│   ├── allocation_agent/
│   └── prompts/
├── backends/
│   ├── matlab_behavioral/
│   ├── python_analytical/
│   ├── spectre/
│   ├── spice/
│   └── engineering_data/
├── domains/
│   └── pll/
│       ├── architecture/
│       ├── blocks/
│       ├── metrics/
│       ├── contexts/
│       └── validators/
├── matlab/
│   └── vco_behavioral/
├── experiments/
│   ├── cases/
│   └── runners/
├── tests/
│   ├── schema/
│   ├── backend/
│   ├── evaluator/
│   ├── contract_refinement/
│   ├── allocation/
│   └── integration/
├── results/
└── run_demo.py
~~~

V1 可以只实现其中一部分，但接口命名和目录边界建议尽量保持。

---

## 14. 实现顺序建议

严格按以下顺序：

1. Data schemas；
2. Schema validator；
3. MATLAB VCO behavioral model；
4. VCO characterization / BlockTB；
5. Simplified PLL SystemTB；
6. Python simulator adapter；
7. Residual、sensitivity 和 feasibility；
8. Deterministic heuristic baseline；
9. Problem 1 Agent interface；
10. Problem 2 Agent interface；
11. Orchestrator；
12. Complete closed loop；
13. trajectory、plots 和 report；
14. replay tests 和 failure tests。

原则：

~~~text
Simulator and Data Interface First
~~~

不要先实现大型 Agent framework。

---

## 15. 测试与评价计划

### 15.1 Schema tests

- 缺失字段；
- 错误单位；
- 反向范围；
- 非法 dependency；
- 未知 action；
- 只读 System Spec 被修改；
- Contract version 不连续。

### 15.2 Backend tests

- 固定输入得到固定输出；
- 单位转换；
- timeout；
- simulator error；
- output missing；
- raw artifact 可重放；
- backend capability 正确声明。

### 15.3 Contract Refinement tests

- Contract v0 的 prediction error 可复现；
- context dependency 能被识别；
- refinement action 被正确校验；
- refinement 后 holdout error 下降；
- 错误 refinement 被 evaluator 拒绝。

### 15.4 Allocation tests

- residual 方向正确；
- sensitivity 符号正确；
- candidate spec 不越界；
- BlockTB 能拒绝 infeasible spec；
- System Spec 不被修改；
- allocation trajectory 可重放。

### 15.5 Integration tests

- 完成一次 SystemTB → Agent Update → BlockTB → SystemTB；
- 触发 optimization failure；
- 触发 abstraction failure；
- 触发 budget exhausted；
- backend failure 后状态可恢复；
- final report 与 raw result 一致。

### 15.6 对照基线

至少比较：

~~~text
Random / Latin-hypercube search
Deterministic heuristic allocation
Numerical optimizer without Agent
Problem 1 Agent + deterministic Problem 2
Problem 2 Agent + fixed Contract
Full two-role workflow
~~~

至少报告：

- System pass rate；
- Block feasibility pass rate；
- best residual；
- contract prediction error；
- simulation count；
- runtime；
- robustness margin；
- failure classification accuracy；
- repeated seed variance。

---

## 16. 关键治理规则

1. SystemSpec 和 pass criteria 只读；
2. Agent 只能输出 schema 允许的 action；
3. Agent action 必须引用 evidence；
4. 所有 sensitivity 由 deterministic tools 生成；
5. 所有 PASS/FAIL 由 evaluator 生成；
6. BlockTB 必须覆盖 SystemTB 抽取的 context envelope；
7. simulation budget 必须硬限制；
8. 每个结果必须带 provenance；
9. synthetic、behavioral、circuit、measurement evidence 必须标注 fidelity；
10. 最终输出必须附 trajectory 和 replay information；
11. 任何 backend 替换都必须通过相同 contract tests；
12. 不允许为了得到 PASS 而修改 SystemSpec。

---

## 17. 需要在正式 Framework Design 中进一步冻结的决策

当前仍有以下设计选择需要在下一轮确认：

### 17.1 Agent 形式

建议 V1：

~~~text
one runtime + two task contexts
~~~

而不是两个独立的长期记忆 Agent。

### 17.2 Optimizer 形式

建议 V1：

~~~text
deterministic heuristic + finite-difference sensitivity
~~~

Bayesian Optimization、RL 或 surrogate model 放到 V2/V3。

### 17.3 Contract 表示

建议 V1 使用：

~~~text
YAML schema + dependency graph + evaluator mapping
~~~

不要第一版就引入复杂 ontology 或知识图谱。

### 17.4 Context 表示

建议同时保存：

- range；
- operating envelope；
- sampled points；
- correlation information；
- extraction source。

不要只保存独立 min/max。

### 17.5 Failure Router

建议 V1 先使用 deterministic rule-based router，再让 Agent 解释和提议 refinement；不要第一版把“失败分类”完全交给 LLM。

### 17.6 Backend 数据交换

建议统一使用：

~~~text
JSON：结构化控制与结果摘要
CSV：sweep table 和 tabular engineering data
MAT：MATLAB 专用复杂数组或 waveform
YAML：人可读的 spec、contract、run config
~~~

---

## 18. 初步结论

这套架构将项目定位为：

~~~text
A simulator-grounded, contract-driven, agent-assisted
system-to-block specification allocation framework.
~~~

它的核心不是“用 Agent 直接设计电路”，而是：

~~~text
Problem 1 Agent:
  determine what must be modeled

Problem 2 Agent:
  determine what should be searched or modified

Deterministic tools:
  determine what is actually true

Evaluator:
  determine whether the result is acceptable
~~~

这样做有三个好处：

1. V1 足够小，可以真实验证；
2. Agent 的错误不会直接变成工程事实；
3. MATLAB synthetic backend 未来可以替换成真实 simulator 或 engineering data，而上层 workflow 尽量保持不变。

当前建议下一步不是立即编码，而是把本文进一步压缩成正式的 V1 Framework Design，冻结：

- module interfaces；
- exact schemas；
- V1 benchmark；
- MATLAB/Python exchange format；
- Agent action policy；
- evaluator pass criteria；
- repository layout；
- integration test cases。

正式 Framework Design 提交后，应再次等待审核。
