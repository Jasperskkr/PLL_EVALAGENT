# PLL System-to-Block Specification 项目总评

> 文档性质：Project Understanding Review + Literature Feasibility Review  
> 项目阶段：方法验证 / V1 设计前  
> 生成日期：2026-09-11  
> 当前结论：方向可行；V1 可以进入框架设计，但尚未进入编码阶段。

## 0. 审核范围与门禁

本文件合并：

1. 对 project_prompt.md 的完整理解；
2. 对 PLL 行为级建模、规格分配、设计空间探索、敏感度分析、模拟电路优化和 LLM-for-EDA 相关工作的调研。

当前仍处于“理解和研究评审”阶段：

- 不编写实现代码；
- 不创建 V1 框架模块；
- 不把 LLM 建议当成仿真事实；
- 只有项目负责人明确批准后，才进入 V1 framework design；
- Framework Design 再次批准后，才开始编码。

建议的批准口令：

~~~text
Project understanding approved.
Proceed to V1 framework design.
~~~

---

## 1. 项目最终目标

项目要建立一条可验证的 System-to-Block Specification 链路：

~~~text
PLL System Specification
        ↓
Behavioral Abstraction
        ↓
Search / Specification Allocation
        ↓
Simulation or Engineering-Data Validation
        ↓
Validated Block Specifications
~~~

系统级输入可以包括：

~~~text
Output Frequency
Reference Frequency
Integrated Jitter
Phase Noise
Lock Time
Spur
Power
Stability
~~~

最终输出包括：

~~~text
PFD/CP Specification
Loop Filter Specification
VCO Specification
Divider Specification
...
~~~

不假设 SystemSpec 对应唯一 BlockSpec，而是定义可行解空间：

~~~text
C = { candidate block specifications | PLL(C) satisfies SystemSpec }
~~~

最终选择要同时考虑：

- System Spec 满足情况；
- Block Spec 可行性；
- 性能裕量；
- operating-envelope 鲁棒性；
- 仿真成本；
- 工程实现代价。

核心目标：

~~~text
SystemSpec
→ Build Behavioral Abstraction
→ Search Specification Space
→ Validate
→ Validated BlockSpecs
~~~

---

## 2. Problem 1：构造 Behavioral Design Space

### 2.1 输入

- PLL architecture，例如 Integer-N CPPLL；
- 当前关注的 block，例如 VCO；
- System-level operating context；
- expert/common architecture knowledge；
- behavioral simulation 或 engineering data；
- block 的功能和性能先验认识。

V1 固定：

~~~text
Architecture: Integer-N CPPLL
Target Block: VCO
~~~

### 2.2 输出

Problem 1 输出机器可读 Behavioral Contract：

~~~text
Blocks
Variables
Context
Dependencies
Validity
~~~

每个 Field 至少包含：

~~~text
name
role
unit
datatype
lower_bound
upper_bound
depends_on
evaluation_method
validity
description
~~~

Field Role 至少包括：

~~~text
system_context
design_variable
intermediate_variable
performance_metric
hard_constraint
objective
validity_condition
~~~

V1 的 VCO 初始字段候选：

~~~text
Vctrl
VDD
temperature
load

oscillation_frequency
Kvco
phase_noise_100kHz
phase_noise_1MHz
phase_noise_10MHz
tuning_range
power
~~~

### 2.3 核心难点

核心不是识别“这是一个 VCO”，而是回答：

> 为了完成 System-to-Block Spec Mapping，这个 VCO 必须暴露哪些 behavioral variables、system context 和 dependencies？

主要难点：

1. 决定 behavioral abstraction 的粒度；
2. 在低维度和 behavioral sufficiency 之间取平衡；
3. 确定 block performance 的 operating envelope；
4. 找到影响 system metrics 的变量；
5. 区分设计变量、中间变量、指标和硬约束；
6. 判断变量应表示为 scalar、function 还是 profile；
7. 识别遗漏的变量、context 或 dependency；
8. 让抽象能被 deterministic simulator 或 engineering data 验证。

Problem 1 产生的是 hypothesis，不是事实。可执行的 refinement 动作：

~~~text
add/remove variable
add/remove context
modify dependency
modify validity
change scalar → function/profile
split/merge block
~~~

例如：

~~~text
Initial: PN_VCO = constant
Observed: PN depends on Vctrl and offset
Refined: PN_VCO = PN(Vctrl, f_offset, temperature)
~~~

---

## 3. Problem 2：在 Behavioral Design Space 中搜索

### 3.1 输入

~~~text
SystemSpec + Behavioral Abstraction
~~~

还需要：

- 当前 Block Specs；
- SystemTB metrics；
- residuals；
- sensitivity；
- contribution；
- margins；
- block feasibility；
- 历史 trajectory。

### 3.2 输出

输出候选配置 C*：

~~~text
PLL(C*) satisfies SystemSpec
~~~

并且：

~~~text
Candidate BlockSpec + System Context → BlockTB PASS
~~~

只有 SystemTB PASS 与 BlockTB Feasible 同时成立，才能输出最终 Block Spec。

### 3.3 核心闭环

~~~text
System Spec
     ↓
Candidate Block Specs
     ↓
SystemTB
     ↓
Metrics + Residuals + Context
     ↓
Sensitivity / Contribution
     ↓
Spec Allocator
     ↓
New Candidate Block Specs
     ↓
Context-aware BlockTB
     ↓
Feasible?
  /          \
 No           Yes
 ↓             ↓
Allocator    SystemTB
                ↓
              repeat
~~~

SystemTB 至少输出：

~~~yaml
metrics:
  integrated_jitter: ...
  lock_time: ...
  output_frequency: ...

residuals:
  integrated_jitter: ...
  lock_time: ...

context:
  VCO:
    vctrl_min: ...
    vctrl_max: ...
    fosc_min: ...
    fosc_max: ...
~~~

Residual 回答“哪个 system metric 没满足，以及差多少”。

Sensitivity 回答“修改哪个 Block Spec 对失败指标最有效”。它必须通过 deterministic sweep 或 finite difference 得到，不能由 LLM 猜测。

Problem 2 Agent 只能执行：

~~~text
tighten
relax
keep
adjust_range
select_next_search_region
~~~

Agent 不得：

~~~text
modify System Spec
modify pass criteria
invent simulation results
declare final PASS
~~~

---

## 4. Problem 1 与 Problem 2 的连接

两者构成双层闭环：

~~~text
Problem 1: Build the Design Space
Problem 2: Search the Design Space
~~~

如果 design space 合理，只是尚未找到数值解，则继续 Problem 2。

如果反复出现：

~~~text
Repeated optimization failure
System behavior cannot be explained
Large abstraction-to-system discrepancy
Sensitivity inconsistent with dependency model
~~~

则返回 Problem 1：

~~~text
Problem 2
   ↓
Abstraction judged insufficient
   ↓
Problem 1 Contract Refinement
   ↓
Problem 2 re-run
~~~

关键判断：

> 当前应该继续调 Block Spec，还是应该修改 Behavioral Abstraction？

---

## 5. Optimization Failure 与 Abstraction Failure

### 5.1 Optimization Failure

定义：

> behavioral design space 仍合理，但在当前搜索范围或数值条件下尚未找到满足 System Spec 的 Block Spec。

证据：

- metric 没达到目标，residual 仍存在；
- sensitivity 表明某些变量确实能改善失败指标；
- block feasibility 仍存在；
- simulator 观测与 dependency model 基本一致；
- 改变搜索区域后有希望找到可行解。

处理：

~~~text
tighten
relax
adjust_range
select_next_search_region
~~~

### 5.2 Abstraction Failure

定义：

> behavioral design space 本身不足以表达真实系统行为，继续调 Block Spec 不能可靠解决问题。

证据：

- contract prediction 与 observation 存在系统性偏差；
- 误差随 context 变化；
- 当前 dependency 无法解释 system metric；
- sensitivity 与 dependency model 不一致；
- 关键 operating condition 没有建模；
- 变量错误地被表示为 constant；
- 需要 scalar → function/profile；
- 多次优化无稳定改善。

处理：返回 Problem 1 进行 Contract Refinement。

---

## 6. Agent 与 deterministic tools 的边界

核心原则：

~~~text
Agent proposes,
tools validate.
~~~

### Agent

Problem 1 Agent：

~~~text
Field discovery
Role classification
Context selection
Dependency proposal
Evaluation-method mapping
Contract refinement
~~~

Problem 2 Agent：

~~~text
Bottleneck reasoning
Spec budgeting
Search-region control
根据 residual、sensitivity、contribution 选择下一步方向
~~~

### Simulator / Backend

~~~text
System evaluation
Block characterization
Context extraction
Performance measurement
Raw simulation generation
~~~

### Numerical Tools

~~~text
Residual calculation
Sensitivity calculation
DOE / sweep
Finite difference
Numerical optimization
Constraint checking
~~~

### Evaluator

~~~text
Contract validation
Block feasibility
System pass/fail
Final result verification
~~~

所有 PASS/FAIL 必须来自 deterministic evaluator。

---

## 7. V1 / V2 / V3

### V1：VCO 单 Block 闭环

~~~text
SystemSpec
→ VCO Behavioral Abstraction
→ VCO BlockSpec
~~~

固定 Integer-N CPPLL 和 VCO。其他 block 使用固定 behavioral parameters 或简化 analytical models。

必须展示：

~~~text
Contract v0
→ validation failure
→ missing context/dependency
→ refined contract
→ SystemTB
→ residual/sensitivity
→ VCO spec allocation
→ context-aware VCO BlockTB
→ SystemTB re-evaluation
~~~

### V2：多 Block 联合分配

扩展到：

~~~text
PFD/CP
Loop Filter
VCO
Divider
~~~

研究 multi-block contracts、cross-block context、coupling、joint allocation 和 coupled sensitivity。

### V3：Architecture Decomposition

研究：

~~~text
Architecture decomposition
Block partition
Block split / merge
Contract construction
~~~

长期目标：

~~~text
SystemSpec
→ Architecture
→ BehavioralAbstraction
→ BlockSpecAllocation
~~~

V3 不应阻塞 V1/V2。

---

## 8. 为什么 V1 选择 VCO

VCO 同时具备：

1. 直接影响输出频率；
2. 相位噪声直接影响系统 jitter；
3. Kvco 影响 loop bandwidth、动态响应和 lock time；
4. 行为依赖 Vctrl、VDD、temperature、load；
5. 容易构造非线性 tuning curve；
6. 容易产生 context-dependent phase noise；
7. 能体现 frequency、noise、power、tuning range trade-off；
8. 能在小模型中覆盖两个 Problem。

建议 tuning curve：

~~~text
fosc = f0 + K1(Vctrl - V0) + K2(Vctrl - V0)^2
Kvco = ∂fosc / ∂Vctrl
~~~

相位噪声可以表示为：

~~~text
PN = g(Vctrl, fosc, Power, f_offset, temperature)
~~~

---

## 9. V1 的最低成功标准

V1 不要求完整 PLL 自动设计、自动 architecture generation、transistor sizing、layout 或大型 multi-agent framework。

必须真实跑通：

### 9.1 机器可读 Contract

~~~text
final_vco_contract.yaml
final_vco_spec.yaml
~~~

### 9.2 Contract deficiency

~~~text
Contract v0
→ prediction/observation mismatch
→ missing context/dependency
→ Contract refinement
→ re-validation
~~~

### 9.3 SystemTB 诊断输出

~~~text
Metrics
Residuals
Context
Sensitivity
~~~

### 9.4 一次完整闭环

~~~text
SystemTB
→ Agent Update
→ VCO BlockTB
→ SystemTB Re-evaluation
~~~

最终要比较：

~~~text
Before optimization vs. After optimization
Initial contract vs. refined contract
Initial VCO spec vs. final VCO spec
Simulation count
Failure cases
Known limitations
~~~

---

## 10. 文献调研结论

### 10.1 PLL 行为级建模已有充分先例

Manganaro 等人使用 MATLAB/Simulink 建立分层 PLL 行为模型：先用粗粒度模型快速分析，再加入非线性和噪声，并把 transistor-level 与实测结果回标到行为模型中。这支持本项目的“粗模型 → 仿真反馈 → 抽象修正 → 后端替换”路线。[Manganaro et al., IEEE TCSII, 2003](https://doi.org/10.1109/TCSII.2003.819134)

Bizjak 等人建立了模块化、非线性的 PLL 时域行为模型，覆盖噪声、非理想效应、phase noise 和 spur，并与线性模型及测量结果比较。[Bizjak et al., IEEE TCSI, 2008](https://doi.org/10.1109/TCSI.2008.916700)

Acco 等人比较了离散线性、离散非线性和 event-driven CPPLL 模型，说明行为模型可以降低 transistor-level 仿真的成本，同时必须明确有效范围。[Acco et al., ISCAS, 1999](https://doi.org/10.1109/ISCAS.1999.777881)

VCO 方面，saturating-integrator ring-oscillator model 可以在 transistor-level 设计前引入 white/flicker jitter，用于高效 phase-noise 评估。[Xu and Kawahara, IEICE, 2017](https://doi.org/10.1587/transele.E100.C.370)

### 10.2 PLL 指标存在真实 trade-off

研究表明，PLL jitter 与 loop bandwidth、VCO noise 和 external/reference noise 存在相互制约关系，支持 V1 至少同时观察 jitter 和 lock time。[Lim et al., IEICE, 1997](https://globals.ieice.org/en_transactions/fundamentals/10.1587/e80-a_10_1979/_p)

低噪声 PLL 研究使用 phase-domain behavioral model 优化 loop bandwidth，并通过 resistor 或 charge-pump current 调节系统表现。[Bai et al., Journal of Semiconductors, 2009](https://doi.org/10.1088/1674-4926/30/8/085011)

Settling time、jitter 和 power 的冲突也被行为仿真研究过，因此不能只优化单一 system metric。[Paliwal et al., 2012](https://arxiv.org/abs/1210.5624)

### 10.3 与 Problem 2 最接近的工作

Zou 等人在 DAC 2006 研究了 CPPLL hierarchical optimization：

- behavior model 评估 jitter、power、locking time 和 stability；
- CP、VCO、loop filter 使用 behavioral-level parameters；
- performance-space exploration 产生 block feasible regions；
- 多维 Pareto-optimal fronts 支持 top-down optimization。

[Zou et al., DAC 2006](https://doi.org/10.1145/1146909.1146919)

因此不能声称“首次提出 PLL 层次化规格分配”。准确差异应是：

~~~text
已有工作：给定行为模型和行为参数，搜索/优化性能空间。

本项目：先构造、验证和修正 behavioral contract，
        再在 contract 定义的 design space 中分配 block specs。
~~~

### 10.4 设计空间探索与数值优化

已有工作使用多目标优化、约束处理、敏感度、Pareto 前沿、鲁棒性分析和 surrogate model，支持本项目的职责划分：Agent 控制假设和搜索空间，数值工具负责计算，simulator 提供事实，evaluator 做独立判定。[PareDA](https://doi.org/10.1016/j.engappai.2016.08.010)

并行约束多目标 Bayesian Optimization 也被用于模拟电路 sizing，说明 simulation budget、并行执行和约束可行性应显式纳入设计。[ABCMOBO](https://doi.org/10.1109/ASP-DAC58780.2024.10473892)

Derivative-aware Bayesian Optimization 进一步把 sensitivity information 纳入低仿真次数搜索。[DarBO, ICCAD 2024](https://doi.org/10.1145/3676536.3676736)

### 10.5 LLM-for-EDA 的相关先例与边界

AnalogCoder 使用 training-free LLM、Python 代码生成和执行反馈，证明 LLM 可以参与模拟电路设计流程。[AnalogCoder](https://arxiv.org/abs/2405.14918)

ADO-LLM 将 LLM 与 Gaussian-process Bayesian Optimization 和 HSPICE simulator 结合，用 LLM 提供先验、BO 扩展搜索、simulation 更新上下文。[ADO-LLM](https://arxiv.org/abs/2406.18770)

AnalogCoder-Pro 和 AnalogAgent 进一步使用多模态反馈、诊断、记忆和多 Agent，但主要任务是 topology/netlist generation、transistor sizing 或代码修正，而不是 PLL-specific behavioral contract construction。[AnalogCoder-Pro](https://arxiv.org/abs/2508.02518) [AnalogAgent](https://arxiv.org/abs/2603.23910)

因此合理的项目定位是：

~~~text
simulation-grounded behavioral-contract construction and refinement
for PLL system-to-block specification allocation
~~~

不是：

~~~text
LLM replaces circuit simulator
LLM replaces numerical optimizer
LLM automatically completes transistor-level PLL design
~~~

---

## 11. 可行性、风险和潜在贡献

### 技术可行性

V1 可行，因为：

- VCO model 可用 MATLAB 或 Python 快速实现；
- Integer-N CPPLL 可先用 analytical / behavioral model；
- SystemTB 和 BlockTB 可通过 JSON/YAML 解耦；
- residual 和 finite-difference sensitivity 可完全 deterministic；
- Agent 只需输出有限结构化动作；
- V1 维度小，适合方法验证。

### 工程可复现性要求

必须：

- 固定 benchmark；
- 固定 simulator seed 和 simulation budget；
- 记录完整 trajectory；
- 使用独立 evaluator replay；
- 所有 PASS/FAIL 都可由 raw result 复算；
- 使用 holdout contexts 检查泛化；
- 区分 synthetic model、engineering data、circuit simulation 和 silicon measurement 的证据等级。

### 潜在研究贡献

不能把“PLL behavioral modeling”“PLL hierarchical optimization”或“LLM + simulator”本身作为创新。潜在贡献应聚焦于：

1. 显式 behavioral Contract schema；
2. Context、dependency、validity 的结构化表示；
3. system observation 驱动的 contract refinement；
4. optimization failure 与 abstraction failure 的区分；
5. context-aware block feasibility 下的 specification allocation；
6. deterministic tools 对 Agent hypothesis 的独立验证。

---

## 12. 当前 Prompt 是否足够明确

结论：

> 作为项目总纲，当前 Prompt 正确且清晰；作为可立即执行的 V1 工程规格，还需要补一份 V1 Benchmark and Evaluation Contract。

Prompt 已经明确：

- 最终目标；
- Problem 1 / Problem 2；
- 双层闭环；
- Agent 与 deterministic tools 边界；
- V1/V2/V3 阶段边界；
- 先 backend/interface、后 Agent framework；
- V1 最低成功条件；
- 进入设计和编码前的审核门禁。

在 Framework Design 前需要冻结：

### 12.1 V1 数值 benchmark

~~~text
f_ref
division ratio N
target output frequency
VDD
temperature range
load
Vctrl range
phase-noise offset range
jitter integration band
lock-time definition
power definition
all pass thresholds
~~~

### 12.2 Ground truth 与隐藏 oracle

如果 Contract 和 simulator 使用完全相同的方程，simulator 不能发现真正的 abstraction deficiency。建议：

~~~text
Initial Contract:
  PN = constant

Hidden Oracle:
  PN = PN(Vctrl, foffset, temperature)
~~~

用未参与 Contract v0 拟合的 holdout contexts 验证 refinement 是否真的降低误差。

### 12.3 Contract 形式语义

需要定义：

- range 是硬边界还是经验范围；
- depends_on 是图、公式还是函数接口；
- validity 是单点、区间还是 envelope；
- scalar 何时升级为 function/profile；
- contract version 如何比较；
- prediction error 如何计算。

### 12.4 Agent 结构化 I/O

Agent 不应返回任意自然语言修改，而应返回 schema 约束的 action，例如：

~~~json
{
  "action": "add_context",
  "target": "VCO.phase_noise",
  "value": "Vctrl",
  "reason": "prediction error increases with Vctrl",
  "evidence": ["sweep_017"]
}
~~~

### 12.5 基线和指标

至少设置：

~~~text
manual/expert heuristic baseline
random or Latin-hypercube baseline
deterministic optimizer baseline
Agent-controlled baseline
~~~

至少报告：

~~~text
system pass rate
block feasibility pass rate
simulation count
best residual
robustness margin
contract prediction error
wall-clock time
~~~

---

## 13. 推荐的最小验证实验

### Pilot A：Contract Refinement

~~~text
Contract v0: PN = constant
        ↓
VCO characterization sweep
        ↓
不同 Vctrl / offset / temperature 下测得 PN
        ↓
发现 prediction error 与 Vctrl 相关
        ↓
Agent 提议 add_context(Vctrl)
        ↓
Contract v1: PN = PN(Vctrl, foffset, temperature)
        ↓
holdout context re-validation
~~~

成功标准：

- v1 在 holdout context 上误差显著低于 v0；
- refinement action 可追溯到 sweep evidence；
- schema validator 接受 action；
- evaluator 可独立复算。

### Pilot B：VCO Spec Allocation

~~~text
Initial VCO Spec
        ↓
SystemTB
        ↓
metrics + residuals + context
        ↓
finite-difference sensitivity
        ↓
Spec Allocator
        ↓
Updated VCO Spec
        ↓
context-aware VCO BlockTB
        ↓
SystemTB re-evaluation
~~~

成功标准：

- 至少一次完整闭环；
- SystemTB 结果由 evaluator 判定；
- BlockTB 覆盖 SystemTB 抽取的 operating envelope；
- 输出 metrics、residuals、sensitivity 和 trajectory；
- 仿真次数受预算约束。

### Pilot C：Failure Classification

构造两类案例：

1. design space 正确但搜索范围不足，验证 Optimization Failure；
2. Contract 缺失 context/dependency，验证 Abstraction Failure。

Agent 必须给出带 evidence 的分类，而不是笼统地说“继续优化”。

---

## 14. 主要风险和控制规则

### 风险 1：预设演示被误当成真实发现

控制：隐藏 oracle、holdout contexts、独立 evaluator。

### 风险 2：Agent 自己计算 sensitivity

控制：sensitivity 只能来自 deterministic sweep 或 finite difference。

### 风险 3：修改 System Spec 以获得 PASS

控制：System Spec 和 pass criteria 只读。

### 风险 4：只验证 nominal point

控制：BlockTB 必须使用 SystemTB 提取的实际 operating envelope。

### 风险 5：只展示成功案例

控制：保留 optimization failure、abstraction failure、invalid candidate、out-of-range 和 simulation error 轨迹。

### 风险 6：过早搭建大型 multi-agent framework

控制：V1 使用单 Agent，通过 task context 区分两个角色；先完成 schemas、backend 和 evaluator。

### 风险 7：行为模型过于理想化

控制：V1 至少包含 nonlinearity、context dependency 和 trade-off，但不宣称 transistor-level accuracy。

### 风险 8：把 V1 Demo 当作芯片 signoff

控制：明确不同证据等级，synthetic simulation 不能替代 circuit simulation 或 silicon measurement。

---

## 15. 对项目可落地性的判断

### 高信心

~~~text
V1 MATLAB/Python behavioral VCO Demo
VCO Contract schema
Contract deficiency detection
Residual/sensitivity calculation
Context-aware BlockTB
Deterministic heuristic spec allocation
Trajectory and plots
~~~

### 中高信心

~~~text
V2 多固定 PLL Blocks 的联合 specification allocation
~~~

前提：V1 的 contract、context、dependency、backend 和 evaluator 接口先冻结。

### 需要谨慎承诺

~~~text
真实 Spectre/SPICE 替换
工程数据校准
跨 PVT / Monte Carlo 的鲁棒规格分配
自动 architecture decomposition
transistor-level PLL design
~~~

我的信心不是“LLM 可以自动设计任何 PLL”，而是：

> 通过严格的数据接口、行为级仿真、确定性评估和阶段化验证，可以把 SystemSpec → Validated Behavioral BlockSpec 工作流做成一个可运行、可审计、可逐步替换后端的项目。

---

## 16. 总体评审结论

~~~text
方向：正确
V1：可落地
技术先例：充分
直接研究空白：存在，但需要实验定义
当前 Prompt：适合作为总纲
立即编码：暂不建议
下一步：冻结 V1 framework design 和 benchmark contract
~~~

Framework Design 应提交：

~~~text
Module Architecture
Data Flow
Schemas
MATLAB/Python Interface
Simulator Backend Interface
Agent Interface
Evaluator Interface
Repository Layout
V1 Demo Execution Flow
Testing Plan
~~~

提交 Framework Design 后应再次等待审核，批准后才开始实现。

