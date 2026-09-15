# V1 Framework Architecture Review and Revised Design

> 文档性质：对 initial_framework_architecture.md 的客观评审与 V1 修订方案  
> 目标：先验证可信的 SystemSpec → VCO Required Spec 映射，再逐步扩展到工程数据  
> 当前状态：架构已修订，仍未进入编码

## 1. 总体评价

原架构的总体方向是正确的，符合此前对项目的理解：

- Problem 1 负责构造 behavioral design space；
- Problem 2 负责在该空间中进行 specification allocation；
- simulator、sensitivity、feasibility 和 evaluator 属于 deterministic core；
- Agent 负责提出 hypothesis 和控制搜索空间；
- backend 与上层 workflow 解耦；
- 未来可以从 synthetic behavioral model 迁移到 circuit simulation 和 engineering data。

原架构的问题不是方向错误，而是三个语义边界没有足够突出，并且把长期平台模块过早放进了 V1 execution path：

1. Behavioral Contract、Contract Predictor 和 Ground-Truth/Oracle 的关系没有成为架构核心；
2. Block Spec Requirement 与 Realized Behavioral Instance 没有严格分离；
3. 输出目标写成了任意一个 feasible point，没有定义 Required Spec Boundary 和 Recommended Spec；
4. V1 的执行路径相对于“先证明 SystemSpec→VCO Spec 映射”而言过重；
5. MATLAB 被写成 V1 首选 backend，但 Python 应作为同等的实现和交叉验证 backend；
6. Calibration/Correlation 应保留为未来演进模块，而不是 V1 的隐含职责。

修订结论：

> 原架构适合作为长期平台蓝图；V1 应收缩为一个 simulator-first、最小 schema、deterministic allocation、可独立验证的 SystemSpec→VCO Required Spec Demo。

---

## 2. 三个必须切开的语义边界

### 2.1 Behavioral Contract ≠ Ground-Truth Model

Behavioral Contract 是 Agent 提出的、待验证的抽象假设。它规定：

- 暴露哪些 variables；
- 使用哪些 context；
- 存在哪些 dependencies；
- 在什么 validity envelope 内有效；
- 每个字段如何被测量或评估。

它不是仿真器内部的真实模型，也不是工程数据本身。

建议明确画成：

~~~text
Behavioral Contract v0
        ↓
Contract Predictor
        ↓
Predicted Behavior
        │
        │ compare
        ↓
Observed Behavior
        ↑
Simulation / Engineering-Data Oracle
~~~

例如：

~~~text
Contract v0:
  PN = constant

Oracle:
  PN = f(Vctrl, foffset, temperature)
~~~

Contract Predictor 根据 Contract 计算预测值；Oracle 提供独立观察值；诊断模块比较两者。

因此 Problem 1 的正确闭环是：

~~~text
Contract Hypothesis
        ↓
Contract Predictor
        ↓
Prediction
        ↓
independent comparison
        ↑
Observation from Oracle
        ↓
Mismatch Diagnosis
        ↓
Contract Refinement
~~~

如果 Contract 和 Oracle 共用完全相同的方程，就只能证明实现一致，不能证明 abstraction 足够。V1 必须让 Contract v0 与 Oracle 至少存在一个有意的表达能力差异，并使用 holdout context 验证 refinement 是否真的有效。

### 2.2 Block Spec Requirement ≠ Realized Behavioral Instance

Block Spec 是对 block 的要求，不是 block 的实际行为。

例如：

~~~text
VCO Required Spec:
  phase_noise_1MHz <= -112 dBc/Hz
~~~

它表达的是约束。

真正进入系统仿真的对象应是：

~~~text
VCO Behavioral Instance:
  PN_actual(f_offset, Vctrl, temperature)
  Kvco_actual(Vctrl, temperature)
  fosc_actual(Vctrl, temperature)
  power_actual(Vctrl, temperature)
~~~

推荐的语义链路：

~~~text
Block Spec Requirement
        ↓
Spec Interpreter / Constraint Compiler
        ↓
Candidate Selection or Instance Builder
        ↓
Realized Behavioral Instance
        ↓
SystemTB / BlockTB
~~~

这里需要区分两个输入：

- Block Spec Requirement：系统分配给 block 的要求；
- Candidate Source：可以产生 realized behavior 的对象。

V1 的 Candidate Source 可以是 synthetic VCO oracle；未来可以是：

- Python parameterized model；
- MATLAB/Simulink model；
- VCO characterization database；
- Spectre/SPICE candidate；
- engineering measurement；
- silicon measurement。

因此未来工程链路自然可以变成：

~~~text
VCO Required Spec
        ↓
Circuit / Database Search
        ↓
Real VCO Candidate
        ↓
Characterization
        ↓
Behavioral Instance
        ↓
System Validation
~~~

Spec Interpreter 的职责是把 requirement 转换为约束、筛选条件或候选生成条件；它不允许凭空制造实际性能数据。

### 2.3 Feasible Candidate ≠ Required Spec Boundary ≠ Recommended Spec

对于 SystemSpec，任意通过的 VCO spec 都不等于“系统真正需要的 VCO spec”。

需要区分：

~~~text
Feasible Candidate Requirement
Required Spec Boundary
Recommended Spec with Margin
~~~

对于“越小越好”的 upper-bound 指标，例如 phase noise：

~~~text
PN <= -110 dBc/Hz     PASS
PN <= -115 dBc/Hz     PASS
PN <= -120 dBc/Hz     PASS
~~~

如果 -110.8 dBc/Hz 已经是满足 SystemSpec 的最宽松边界，那么：

~~~text
Required Spec Boundary ≈ -110.8 dBc/Hz
Recommended Spec     = -112 dBc/Hz
~~~

其中：

- Required Spec Boundary：在给定 architecture、model、context、uncertainty 和 pass criteria 下，仍能满足 SystemSpec 的最小必要约束；
- Recommended Spec：在 boundary 基础上加入工程 margin 后的可执行要求；
- Feasible Candidate：某个实际 candidate 的 behavior 满足某个 requirement 的事实。

对 V1，建议将输出拆成：

~~~yaml
required_spec_boundary:
  phase_noise_1MHz:
    upper_bound: -110.8
    unit: dBc/Hz

selected_candidate:
  id: synthetic_vco_003

realized_behavior:
  evidence_id: block_tb_007

recommended_spec:
  phase_noise_1MHz:
    upper_bound: -112.0
    margin: 1.2
    unit: dBc/Hz
~~~

对于非单调或多变量情况，不能强行输出单一 scalar boundary，而应输出可行区域或 Pareto boundary。V1 可以先处理少量、方向明确的 VCO requirements，V2 再扩展到多 block Pareto allocation。

### 2.4 术语的精确定义

为了避免后续文档和代码再次混淆，固定以下定义：

- Contract：对如何描述 block behavior 的结构化假设，包含 variables、context、dependencies、validity 和 evaluation mapping；它可以由专家、规则或 Agent 提出，但必须经过验证。
- Contract Predictor：根据 Contract 对指定 context 生成 predicted behavior 的确定性组件。
- Oracle：V1 synthetic demo 中独立生成 reference behavior 的程序。Oracle 只表示实验真值来源，不代表真实工程中永远存在绝对真值。
- Observation：从 Oracle、circuit simulator 或 measurement backend 得到的实际观测结果。
- Block Spec Requirement：系统分配给 block 的能力要求或约束，例如 PN@1MHz 的上限。
- Behavioral Instance：某一个 synthetic candidate、circuit candidate 或 measured candidate 在 context 下的 realized behavior。
- Candidate Provider / Instance Builder：把 candidate source 转换成 Behavioral Instance 的组件；它不得把 requirement 直接当成 observation。
- Required Spec Boundary：在明确的 model、context、uncertainty 和 pass criteria 下仍可满足 SystemSpec 的最宽松 requirement 边界。
- Recommended Spec：在 Required Spec Boundary 上依据显式 margin policy 得到的工程建议值。

在真实工程数据场景中，Oracle 一词应改用 reference backend 或 observation source，避免把有测量误差和校准误差的工程数据误称为绝对 ground truth。

---

## 3. 修订后的总体架构

长期架构保留分层思想，但 V1 只实现最小核心：

~~~text
┌──────────────────────────────────────────────────────────────┐
│ Reports / CLI / Plots                                         │
├──────────────────────────────────────────────────────────────┤
│ Optional Agent Layer                                          │
│   Problem 1 Contract Reasoner                                 │
│   Problem 2 Allocation Reasoner                               │
├──────────────────────────────────────────────────────────────┤
│ Deterministic Core                                            │
│   Contract Predictor | Spec Interpreter                       │
│   SystemTB | BlockTB | Residual | Sensitivity | Allocator      │
│   Failure Rules | Trajectory                                 │
├──────────────────────────────────────────────────────────────┤
│ Backend Layer                                                  │
│   PythonBehavioralBackend                                     │
│   MatlabBehavioralBackend                                     │
│   Future: SPICE / Spectre / EngineeringData                  │
├──────────────────────────────────────────────────────────────┤
│ Domain Layer                                                   │
│   V1: domains/pll/vco                                          │
│   Future: multi-block PLL and other circuit domain packs       │
└──────────────────────────────────────────────────────────────┘
~~~

V1 的核心原则：

~~~text
Simulator and Data Interface First
~~~

Agent 可以暂时不接入 V1 主执行路径，但必须预留 action schema 和 hook，使 Problem 1/2 Agent 后续能够替换 deterministic heuristic，而不改变 simulator、evaluator 和 result schema。

---

## 4. V1 的最小可信执行路径

### 4.1 Allocation Path：从 SystemSpec 提取 Required VCO Spec

这一条路径回答：

> 在当前 behavioral system model 中，VCO 至少需要达到什么要求，系统才能满足 SystemSpec？

~~~text
System Spec
      ↓
Initial VCO Requirement
      ↓
Spec Interpreter / Requirement Compiler
      ↓
Abstract VCO Capability Envelope
      ↓
SystemTB
      ↓
System Metrics + Residual
      ↓
Finite-Difference Sensitivity
      ↓
Deterministic Spec Allocator
      ↓
New VCO Requirement
      ↓
Required Spec Boundary Search
      ↓
Required VCO Spec
~~~

这里的 Abstract VCO Capability Envelope 是 SystemTB 在分配阶段使用的抽象输入，不应被误称为 realized circuit behavior。

### 4.2 Validation Path：用独立 Candidate Oracle 验证 Requirement

这一条路径回答：

> 是否存在一个实际 VCO candidate，在 SystemTB 提取的 context envelope 中满足这个 requirement？

~~~text
Required VCO Spec
      ↓
Candidate Provider / Instance Builder
      ↓
Realized VCO Behavioral Instance
      ↓
VCO BlockTB
      ↓
Feasible / Infeasible + Margin
      ↓
SystemTB using Realized Instance
      ↓
Final System Metrics + PASS/FAIL
~~~

V1 可以使用 synthetic candidate provider。关键是：

- Contract Predictor 不等于 Oracle；
- Requirement 不等于 behavior；
- SystemTB 最终应能用 realized instance 重跑；
- BlockTB 必须覆盖 SystemTB 抽取的 operating context。

### 4.3 两条路径如何连接

~~~text
SystemSpec
   ↓
Allocation Path
   ↓
Required Spec Boundary
   ↓
Validation Path
   ↓
Candidate Feasibility
   ↓
Realized-Instance SystemTB
   ↓
Final verified mapping
~~~

如果 Validation Path 失败，需要区分：

- requirement 太宽松，candidate 不满足：Candidate/feasibility issue；
- realized behavior 与 Contract Predictor 不一致：Abstraction issue；
- system residual 仍未消除但 dependency 一致：Allocation/search issue。

---

## 5. V1 的模块范围

### 5.1 V1 必须实现

1. Minimal schema validator；
2. VCO domain pack；
3. PythonBehavioralBackend；
4. BehavioralSimulatorBackend 的统一接口，以及 MatlabBehavioralBackend 的可替换 adapter 约定；
5. 独立 VCO Oracle 或 reference backend；
6. Contract Predictor；
7. Spec Interpreter；
8. Simplified PLL SystemTB；
9. VCO BlockTB；
10. residual calculation；
11. finite-difference sensitivity；
12. deterministic spec allocator；
13. required-boundary search；
14. JSONL trajectory；
15. final mapping report。

V1.0 的 Contract 可以先固定为经过人工确认的 minimal contract，但必须与 Oracle/Observation 使用独立实现。这样不会把 Contract Refinement 作为 SystemSpec→VCO Spec 映射的前置阻塞条件。

### 5.2 V1 可以暂不实现

- 完整 Schema Registry；
- 通用 Domain Pack Registry；
- 复杂 Experiment Manager；
- 独立 Failure Router service；
- 多 Agent 通信；
- RAG、memory、knowledge graph；
- Bayesian Optimization；
- reinforcement learning；
- 多目标 Pareto engine；
- 自动 architecture decomposition；
- calibration / correlation；
- PVT/Monte Carlo 大规模管理。

Contract v0 → mismatch → refinement → holdout re-validation 可以作为 V1.0 的旁路实验，或作为 V1.1 的 Problem 1 验证项；它不应阻塞 V1.0 的主映射闭环。

这些模块在长期架构中合理，但不应阻塞 V1 的电气闭环。

### 5.3 V1 Agent 策略

V1 建议分两个层次。

#### 默认主路径：无 LLM 的 deterministic baseline

~~~text
SystemSpec
→ deterministic sensitivity
→ deterministic allocator
→ required-boundary search
→ realized-instance validation
~~~

#### 可选增强路径：Agent 替换 action proposer

~~~text
Deterministic evidence
→ Problem 1 or Problem 2 Agent
→ schema-constrained action
→ same validator / simulator / evaluator
~~~

先回答最重要的问题：

> 这个 SystemSpec→VCO Spec 映射在确定性方法下是否电气上成立？

之后再回答：

> Agent 是否能改善抽象发现、搜索效率或解释质量？

这样更容易归因，也更适合方法验证。

---

## 6. Contract、Oracle 和 Predictor 的 V1 设计

### 6.1 Contract v0

V1 可以故意从一个不足的 contract 开始，例如：

~~~yaml
contract_id: vco_contract_v0
representation:
  oscillation_frequency: function_of(Vctrl)
  phase_noise_1MHz: constant
dependencies:
  - Vctrl -> oscillation_frequency
validity:
  Vctrl: [0.35, 0.85]
  temperature: [-40, 125]
~~~

### 6.2 Oracle

Oracle 是独立的 synthetic ground-truth behavior：

~~~text
fosc = f0
     + K1(Vctrl - V0)
     + K2(Vctrl - V0)^2
     + temperature_shift

PN = g(Vctrl, foffset, temperature, power)

Kvco = ∂fosc/∂Vctrl
~~~

Oracle 的方程不能被 Contract v0 完整表达。

### 6.3 Contract Predictor

Predictor 使用 Contract v0 产生：

~~~text
PN_predicted = constant
fosc_predicted = f(Vctrl)
Kvco_predicted = scalar or local function
~~~

### 6.4 Refinement 证据

比较：

~~~text
Prediction(v0, context) vs Observation(oracle, context)
~~~

如果误差在 Vctrl、temperature 或 offset 上呈现结构性变化，则输出：

~~~text
missing_context
missing_dependency
invalid_representation
invalid_range
~~~

V1 最小要求：

~~~text
PN = constant
→ mismatch correlated with Vctrl
→ add Vctrl dependency
→ PN = PN(Vctrl, foffset)
→ holdout error decreases
~~~

---

## 7. Block Spec、Instance Builder 和 SystemTB 的职责

### 7.1 Spec Interpreter

输入：

- Required VCO Spec；
- current Contract；
- system context；
- candidate source metadata。

输出：

- constraints；
- capability envelope；
- candidate filtering query；
- SystemTB 可消费的 abstract requirement representation。

不输出 realized measurement。

### 7.2 Candidate Provider / Instance Builder

输入：

- candidate id 或 synthetic design parameters；
- domain；
- context；
- backend。

输出：

~~~text
RealizedBehavioralInstance
~~~

至少包含：

~~~text
fosc_actual(Vctrl, temperature)
Kvco_actual(Vctrl, temperature)
PN_actual(Vctrl, foffset, temperature)
power_actual(Vctrl, temperature)
~~~

### 7.3 SystemTB

SystemTB 允许两种输入模式，但必须标记模式：

~~~text
allocation_mode:
  使用 abstract capability envelope

validation_mode:
  使用 realized behavioral instance
~~~

V1 最终结果必须来自 validation_mode 的重跑，不能只依赖 allocation_mode。

### 7.4 BlockTB

BlockTB 检查：

~~~text
RealizedBehavioralInstance + OperatingContext
        ⊨ Required VCO Spec
~~~

输出：

- pass/fail；
- worst-case context；
- margin；
- violated fields；
- evidence id。

---

## 8. Python 与 MATLAB Backend 同级化

建议统一接口：

~~~text
BehavioralSimulatorBackend
├── PythonBehavioralBackend
└── MatlabBehavioralBackend
~~~

两者实现：

~~~text
evaluate_system(request)
characterize_block(request)
run_sweep(request)
validate_block_spec(request)
build_behavioral_instance(request)
~~~

### PythonBehavioralBackend

用途：

- 快速开发和单元测试；
- 直接集成 Python evaluator；
- 便于 CI 和结果 replay；
- 作为 V1 最小可运行 backend。

### MatlabBehavioralBackend

用途：

- MATLAB/Simulink behavioral PLL；
- 与控制系统分析工具衔接；
- 交叉验证 Python 模型；
- 为后续工程模型替换保留路径。

V1.0 不要求同时完成一套与 Python 完全等价的 MATLAB 实现。建议先把 MATLAB adapter 和 exchange contract 定义好；如果时间允许，再用 MATLAB/Simulink 对关键 tuning curve、jitter、lock time 和 context 做交叉验证。这样 Python 是 V1.0 的 canonical executable backend，MATLAB 是同级可替换 backend，而不会把“双 backend 完整一致”变成 V1 的前置阻塞条件。

### Backend 一致性测试

同一输入至少比较：

- output frequency；
- VCO tuning curve；
- Kvco；
- integrated jitter；
- lock time；
- context envelope；
- residual；
- tolerance 内的一致性。

若不能完全一致，需要记录：

- tolerance；
- model fidelity；
- known discrepancy；
- canonical backend。

---

## 9. Required Spec 的定义

### 9.1 V1 的目标

V1 不声称找到唯一最优 spec。V1 要输出：

~~~text
SystemSpec
→ Required VCO Spec Boundary
→ Recommended VCO Spec with Margin
→ Candidate Feasibility
→ Final Verified Mapping
~~~

### 9.2 Boundary 搜索

对单调、标量或少量 requirement，使用 deterministic boundary search：

1. 定义 requirement 参数；
2. 编译到 abstract capability envelope；
3. 运行 SystemTB；
4. 计算 residual；
5. 用 bisection 或 bracketed search 找到 pass/fail 边界；
6. 运行 realized-instance validation；
7. 加入 margin；
8. 输出 recommended spec。

对于 upper-bound 指标：

~~~text
least-stringent requirement
= 最大仍能使 SystemSpec PASS 的 upper bound
~~~

对于 lower-bound 指标：

~~~text
least-stringent requirement
= 最小仍能使 SystemSpec PASS 的 lower bound
~~~

对于 range、非单调或耦合变量：

~~~text
输出 feasible region / Pareto boundary
~~~

V1 可以暂不实现完整 Pareto engine。

### 9.3 Margin

Margin 不应由 Agent 随意决定。V1 使用显式配置：

~~~yaml
margin_policy:
  type: fixed_relative_or_absolute
  phase_noise_1MHz:
    absolute_margin_db: 1.2
~~~

未来再根据 model uncertainty、PVT variation、measurement uncertainty、yield target 和 engineering cost 推导 robust margin。

---

## 10. Future Extension：Calibration / Correlation

提前保留接口，但明确标记为 Future Extension：

~~~text
Circuit / Measurement Data
          ↓
Model Calibration / Correlation
          ↓
Calibrated Behavioral Model
          ↓
Fast System Exploration
          ↓
High-Fidelity Validation
~~~

长期多保真流程：

~~~text
Behavioral model
      ↓ large-scale search
Circuit simulation
      ↓ selected candidates
Silicon / measurement data
      ↓ calibration and final validation
Preferred engineering spec
~~~

V1 不做 circuit-to-behavior fitting、measurement calibration、silicon correlation、uncertainty calibration 或 production signoff。

schema 应预留 source、fidelity、calibration version、uncertainty、PVT/corner、measurement metadata 和 correlation status。

---

## 11. V1 推荐目录

~~~text
PLL_AGENT/
├── project_prompt.md
├── project_understanding_and_literature_review.md
├── initial_framework_architecture.md
├── v1_framework_architecture_reviewed.md
├── schemas/
│   ├── system_spec.schema.yaml
│   ├── vco_contract.schema.yaml
│   ├── vco_spec.schema.yaml
│   ├── behavioral_instance.schema.yaml
│   ├── agent_action.schema.yaml
│   └── evaluation.schema.yaml
├── v1/
│   ├── contracts/
│   ├── specs/
│   ├── cases/
│   ├── system_tb/
│   ├── block_tb/
│   ├── contract_predictor/
│   ├── spec_interpreter/
│   ├── oracle/
│   ├── allocator/
│   └── trajectory/
├── backends/
│   ├── python_behavioral/
│   └── matlab_behavioral/
├── tests/
├── results/
└── run_demo.py
~~~

长期模块如 domains、agents、calibration 可以在 V1 通过轻量接口预留，但不要求形成完整平台。

---

## 12. V1 执行命令与运行结果

目标命令：

~~~text
python run_demo.py --case vco_mapping_01
~~~

V1 运行步骤：

1. 读取 immutable SystemSpec；
2. 读取 VCO Contract v0；
3. 运行 Contract Predictor 与独立 VCO Oracle；
4. 检测 Contract deficiency；
5. 生成 refined Contract v1；
6. 读取 initial VCO requirement；
7. Spec Interpreter 生成 abstract capability envelope；
8. 运行 SystemTB allocation_mode；
9. 计算 residual；
10. 运行 finite-difference sensitivity；
11. Deterministic Allocator 搜索 required spec boundary；
12. 由 Candidate Provider / Instance Builder 生成 realized VCO instance；
13. 运行 context-aware VCO BlockTB；
14. 运行 SystemTB validation_mode；
15. 计算 final metrics、residuals、margins；
16. 输出 required boundary、recommended spec 和 selected candidate；
17. 写入 trajectory.jsonl 和 summary.md。

V1 最终输出建议：

~~~text
results/<run_id>/
├── system_spec.yaml
├── contract_v0.yaml
├── refined_vco_contract.yaml
├── initial_vco_requirement.yaml
├── required_vco_spec_boundary.yaml
├── recommended_vco_spec.yaml
├── realized_vco_instance.json
├── initial_system_evaluation.json
├── sensitivity.json
├── block_feasibility.json
├── final_system_evaluation.json
├── trajectory.jsonl
└── summary.md
~~~

---

## 13. V1 成功标准

V1 成功不以 Agent 是否复杂为标准，而以映射是否可信为标准。

这里需要明确一个范围变化：原始 project_prompt.md 把 Agent 驱动的 Contract Refinement 和 Spec Allocation 也列为 V1 演示内容；当前修订将 V1 拆成两个交付层次：

```text
V1.0：deterministic SystemSpec → VCO Required Spec mapping
V1.1：在相同 deterministic core 上接入 Problem 1 / Problem 2 Agent
```

V1.0 是进入 V1 的硬门槛。只有 V1.0 的 electrical mapping 可信，才有意义评估 Agent 是否改善 abstraction discovery、search efficiency 或 explanation quality。这样不是取消 Agent，而是把 Agent 从电气正确性的前置依赖改成可独立评价的增量能力。

必须证明：

1. 给定固定的 PLL SystemSpec，可以输出 Required VCO Spec Boundary；
2. Required Spec 能被 deterministic Spec Interpreter 转成可执行约束；
3. 独立 VCO Oracle 能产生 realized behavior；
4. BlockTB 能在 System Context envelope 中判断 candidate 是否满足 Required Spec；
5. SystemTB 能用 realized instance 重跑并判断系统 PASS/FAIL；
6. Required Spec 与 realized candidate 之间的关系可以追溯；
7. allocation_mode 与 validation_mode 的对象边界清楚，且 validation_mode 不把 requirement 当成 realized behavior；
8. initial requirement 与 final recommended requirement 的变化有 residual/sensitivity 依据；
9. 不修改 SystemSpec、不伪造 simulation result、不由 Agent 直接宣布 PASS。

以下属于 V1.0 旁路验证或 V1.1 的额外成功标准，而不是 V1.0 映射闭环的硬前置条件：

10. 至少一个 Contract v0 deficiency 能被 Oracle observation 发现；
11. refined Contract 在 holdout context 上比 v0 更准确。

V1 不要求：

- LLM 一开始就参与 V1.0 主闭环；
- 多 Agent；
- 完整自动 architecture decomposition；
- 多 block Pareto allocation；
- 真实 Spectre/SPICE；
- silicon-level correlation。

V1.1 的 Agent 接入必须复用 V1.0 的同一套：

- Contract Predictor；
- Spec Interpreter；
- Oracle / Observation；
- BlockTB / SystemTB；
- residual 和 sensitivity；
- evaluator；
- trajectory schema。

Agent 只替换 action proposer，不能替换事实来源或 PASS/FAIL 判定器。

---

## 14. 对六点修改意见的最终判断

### 14.1 Contract vs Oracle 分离

完全同意，而且这是必须提升到架构核心的语义边界。没有这一层，Problem 1 的 refinement loop 不能被可信地验证。

### 14.2 Block Spec vs Behavioral Instance 分离

完全同意，并进一步增加 Candidate Provider / Instance Builder。仅增加 Spec Interpreter 还不够，因为系统最终必须仿真实际 realized behavior，而不是 requirement 本身。

### 14.3 Required Spec Boundary

完全同意。项目输出应从“找到一个 feasible point”升级为“找到最低必要要求，并根据明确 margin policy 生成 recommended spec”。

但单一 boundary 只适用于单调、低维场景；多变量和非单调场景需要逐步扩展为 feasible region 或 Pareto boundary。

### 14.4 V1 大幅减重

完全同意。V1 首要目标是验证电气映射闭环，不是展示软件平台的模块数量。Schema Registry、Domain Pack、Experiment Manager、Failure Router、Provenance 等长期设计保留，但 V1 只实现 minimal version。

### 14.5 Python 与 MATLAB 同级

同意。Python 适合快速开发、CI、replay 和单元测试；MATLAB 适合控制系统/Simulink behavioral model 和交叉验证。两者应使用同一接口和 canonical result schema。

### 14.6 Calibration / Correlation 后置

同意。应画成 Future Extension，并预留 fidelity、uncertainty、calibration metadata；V1 不实现。

---

## 15. 最终客观结论

这份修订后的架构更符合项目当前真实目标：

~~~text
V1:
  验证 SystemSpec → Required VCO Spec → Realized VCO Validation
  这条链是否可信、可复现、可解释。

长期:
  扩展到多 block、Pareto allocation、真实 circuit simulation、
  engineering data、calibration 和多种电路领域。
~~~

最重要的修正不是增加模块，而是把下面四种对象分开：

~~~text
Contract:
  我们认为应该如何描述 behavior。

Oracle / Observation:
  仿真或工程数据实际显示了什么。

Block Spec:
  系统要求 block 至少达到什么能力。

Behavioral Instance:
  某个真实或合成 candidate 实际能做到什么。
~~~

V1 推荐优先级：

~~~text
1. 独立 Oracle / Observation
2. Contract Predictor
3. Spec Interpreter
4. Python/Matlab SystemTB
5. Realized VCO Instance Builder
6. BlockTB
7. Residual + Sensitivity
8. Required Boundary Search
9. Deterministic Allocator
10. Optional Agent hook
~~~

先建立可信的电气闭环，再测量 Agent 是否带来抽象发现、搜索效率或解释质量上的增益，实验结论会更清楚，也更容易发展成工程项目。
