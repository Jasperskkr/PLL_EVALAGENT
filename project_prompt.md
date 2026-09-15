你将协助我设计和开发一个面向 PLL 的行为级 System-to-Block Specification Decomposition Agent。
当前项目仍处于方法验证和早期 Demo 阶段。
收到本 Prompt 后不要立即开始编码。
首先需要充分理解：
- 项目最终要解决什么问题；
- Problem 1 和 Problem 2 分别是什么；
- 两者如何形成闭环；
- V1 / V2 / V3 的递进关系；
- Agent、Simulator、Optimizer、Evaluator 分别承担什么角色。
第一次输出必须先提交 Project Understanding Review，等待我的审核。
只有我明确批准后，才能进入框架设计和代码实现。
项目最终目标是完成：
[
\boxed{
System\ Specification
\rightarrow
Block\ Specification
}
]
例如给定 PLL System Spec：
```text
Output Frequency
Reference Frequency
Integrated Jitter
Phase Noise
Lock Time
Spur
Power
Stability Requirements
```
希望最终得到：
```text
PFD/CP Spec
Loop Filter Spec
VCO Spec
Divider Spec
...
```
这里不假定：
[
SystemSpec
\rightarrow
Unique\ BlockSpec
]
而是认为存在一个满足 System Spec 的 block-spec feasible space：
{
C:
PLL(C)\ satisfies\ SystemSpec
}
]
项目最终需要：
1. 构造一个适合 system-level optimization 的 behavioral design space；
2. 在这个 design space 中寻找满足 system requirements 的 block-spec allocation；
3. 用 simulation / engineering data 验证最终结果；
4. 输出一组可验证的 preferred block specifications。
因此整体任务是：
[
\boxed{
SystemSpec
\rightarrow
Build\ Behavioral\ Abstraction
\rightarrow
Search\ Specification\ Space
\rightarrow
Validate
\rightarrow
BlockSpecs
}
]
已有 Claw-Analog 的核心闭环是：
```text
Understand
   ↓
Act
   ↓
Simulation / EDA
   ↓
Observe Feedback
   ↓
Modify
   ↓
Re-evaluate
   ↓
Independent Grader
```
也就是：
[
\boxed{
Think
\rightarrow
Act
\rightarrow
Observe
\rightarrow
Refine
}
]
新 PLL 项目继承：
- simulation-grounded reasoning；
- iterative feedback；
- deterministic evaluation；
- structured diagnostics；
- simulation budget；
- trajectory；
- independent validation。
但两个项目的核心区别是：
通常已经给定：
DesignSpace
]
Agent 解决：
[
\boxed{
Given\ the\ design\ space,
how\ to\ search\ it?
}
]
首先还需要解决：
[
\boxed{
How\ to\ construct\ the\ design\ space?
}
]
然后才解决：
[
\boxed{
How\ to\ search\ the\ design\ space?
}
]
这分别对应 Problem 1 和 Problem 2。
Problem 1 的核心目标是：
把一个 PLL architecture / block 从“功能名称”转化成一个机器可读、可测试、可优化的 behavioral abstraction。
最终得到：
{
Blocks,
Variables,
Context,
Dependencies,
Validity
}
]
即：
将 PLL architecture 分解为功能结构。
例如：
```text
Integer-N CPPLL

PFD/CP
   ↓
Loop Filter
   ↓
VCO
   ↓
Divider
   └────→ feedback
```
早期版本可以使用 expert/common architecture。
未来再研究 Agent 自动 architecture decomposition。
决定 behavioral abstraction 的粒度。
例如：
```text
PFD + CP
```
作为一个 block，
还是：
```text
PFD
CP
```
分别建模。
目标是在：
[
Low\ Dimensionality
]
和：
[
Behavioral\ Sufficiency
]
之间取得平衡。
对于每一个 Block，需要建立完整的数据模型。
每个 Field 至少描述：
```text
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
```
Field Role 至少支持：
```text
system_context
design_variable
intermediate_variable
performance_metric
hard_constraint
objective
validity_condition
```
Problem 1 真正重要的问题不是：
这是一个 VCO 吗？
而是：
为了完成 System-to-Block Spec Mapping，VCO 应该暴露哪些 behavioral variables？
Context 表示：
[
System\rightarrow Block
]
的 operating condition。
例如：
{
V_{ctrl},
f_{osc},
load,
VDD,
temperature
}
]
Block performance 应在真实 System Context 下定义，而不是脱离 system 独立定义。
建立：
[
BlockVariable
\rightarrow
SystemMetric
]
之间的 dependency。
例如：
[
PN_{VCO}
\rightarrow
SystemJitter
]
[
K_{VCO}
\rightarrow
LoopBandwidth
\rightarrow
LockTime
]
Problem 1 主要建立 dependency structure。
Problem 2 再通过 sensitivity 判断 dependency 当前有多强。
Agent 生成的 abstraction 只是 hypothesis。
必须经过 simulator / engineering data 验证。
如果：
[
Prediction
\neq
ObservedBehavior
]
则检查：
```text
Missing variable?
Missing context?
Missing dependency?
Invalid range?
Incorrect abstraction?
Strong unmodeled coupling?
```
Agent 可以进行：
```text
add/remove variable
add/remove context
modify dependency
modify validity
change scalar → function/profile
split/merge block
```
最终目标是：
[
\boxed{
Minimal\ Sufficient\ Behavioral\ Contract
}
]
Problem 1 可以概括为：
[
\boxed{
Build\ the\ Design\ Space
}
]
Problem 2 的输入是：
[
SystemSpec+\mathcal A
]
其中 (\mathcal A) 来自 Problem 1。
目标是在这个 behavioral design space 中找到：
[
C^*
]
使得：
[
PLL(C^*)\ satisfies\ SystemSpec
]
核心闭环：
```text
System Spec
     ↓
Candidate Block Specs
     ↓
System TB
     ↓
System Evaluation
     ↓
Metric + Residual + Context
     ↓
Sensitivity / Contribution
     ↓
Spec Allocator
     ↓
New Candidate Block Specs
     ↓
Context-aware Block TB
     ↓
Feasible?
  /          \
 No           Yes
 ↓             ↓
Allocator    System TB
                ↓
              repeat
```
SystemTB 实际测得的 system performance，例如：
```text
Jitter = 180 fs
Lock Time = 7 us
```
表示实际结果与 System Spec 的距离。
例如：
[
JitterTarget<150fs
]
而：
[
Jitter=180fs
]
则：
[
Residual=+30fs
]
Residual 回答：
哪个 System Spec 没满足，以及差多少？
SystemTB 同时输出 block 当前真实 operating conditions，例如：
```text
VCO.Vctrl = 0.45–0.72 V
VCO.fosc  = 4.9–5.1 GHz
```
Context 主要用于配置 BlockTB。
Residual 不能直接回答：
应该修改哪个 Block Spec？
因此分析：
\frac{\partial Metric_i}
{\partial BlockSpec_j}
]
Sensitivity 回答：
修改哪个 Block Spec 对当前失败指标最有效？
Contribution 回答：
当前 System Metric 主要由哪些 block 导致？
输入：
```text
Current Block Specs
Metrics
Residuals
Sensitivity
Contribution
Margins
Block Feasibility
History
```
输出：
```text
tighten
relax
keep
adjust range
next search region
```
Agent 更适合作为：
[
\boxed{
Search\text{-}Space\ Controller
}
]
而不是完全替代 numerical optimizer。
新的 Block Spec 必须在 System Context 下进行验证：
[
CandidateBlockSpec
+
Context
\rightarrow
BlockTB
]
例如：
```text
VCO requirement:
PN@1MHz < -112 dBc/Hz

System Context:
Vctrl = 0.45–0.72 V
```
BlockTB 检查：
该 Spec 是否在整个实际 operating envelope 中成立？
最终需要同时满足：
[
SystemSpec\ PASS
]
和：
[
BlockSpec\ Feasible
]
才能输出最终 block specifications。
Problem 2 可以概括为：
[
\boxed{
Search\ the\ Design\ Space
}
]
Problem 1 和 Problem 2 构成双层闭环。
[
\boxed{
Block\ Spec\ Allocation
}
]
即：
Problem 2 不断调整 block specs。
[
\boxed{
Behavioral\ Abstraction\ Refinement
}
]
如果 Problem 2 中出现：
```text
Repeated optimization failure
System behavior cannot be explained
Large abstraction-to-system discrepancy
Sensitivity inconsistent with dependency model
```
需要判断：
Design space 本身合理，只是数值还没找到。
则：
```text
Continue Problem 2
```
Variables / Context / Dependencies 本身定义不充分。
则：
```text
Problem 2
   ↓
Return to Problem 1
   ↓
Refine Behavioral Contract
```
Agent 最终需要具备一个关键判断能力：
当前应该继续调 Block Spec，还是应该修改 Behavioral Abstraction？
Agent 不应该取代 simulator。
推荐职责分工：
负责：
```text
Behavioral abstraction reasoning
Variable/context/dependency proposal
Contract refinement
Bottleneck reasoning
Spec budgeting
Search-region control
```
负责：
```text
System evaluation
Block characterization
Context extraction
Performance measurement
```
负责：
```text
Residual calculation
Sensitivity calculation
DOE / sweep
Numerical optimization
Constraint checking
```
负责：
```text
Contract validation
Block feasibility
System pass/fail
Final result verification
```
核心原则：
[
\boxed{
Agent\ proposes,
tools\ validate
}
]
V1 是当前两周内首先实现的 Demo。
目标不是完成整个 PLL，而是第一次真实验证：
[
\boxed{
SystemSpec
\rightarrow
VCO\ Behavioral\ Abstraction
\rightarrow
VCO\ BlockSpec
}
]
固定：
```text
Architecture:
Integer-N CPPLL

Target Block:
VCO
```
PFD/CP、Loop Filter、Divider 第一版使用：
```text
fixed behavioral parameters
or
simplified analytical models
```
暂时不做自动 spec decomposition。
首先把：
```text
VCO
```
构造成一张 Behavioral Contract 数据模型。
第一版建议包含：
```text
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
```
每个字段必须包含：
```text
role
unit
datatype
range
depends_on
evaluation_method
validity
```
Agent 第一版负责：
```text
Field discovery
Role classification
Dependency proposal
Context selection
Evaluation-method mapping
Contract refinement
```
例如初始：
[
PN_{VCO}=constant
]
而 behavioral simulator 中真实设置：
[
PN_{VCO}=PN(V_{ctrl},f_{offset})
]
仿真发现：
```text
PN prediction error increases with Vctrl
```
Agent 应能够提出：
```text
Add Vctrl as context
```
使：
[
PN
\rightarrow
PN(V_{ctrl},f_{offset})
]
然后重新验证。
这用于证明：
[
\boxed{
Problem\ 1\ Refinement\ Loop
}
]
能够工作。
Validated VCO Contract 建立以后，执行最小版：
[
SystemSpec
\rightarrow
VCOSpec
]
System requirements 第一版优先使用：
```text
Output Frequency
Integrated Jitter
Lock Time
```
必要时再加入 Power。
Agent / Optimizer 调整少量 VCO specifications，例如：
```text
Phase Noise Requirement
Kvco Range
Tuning Range
Power Budget
```
完整演示至少包含：
```text
Initial VCO Spec
      ↓
SystemTB
      ↓
Jitter / Lock-Time Evaluation
      ↓
Residual
      ↓
Sensitivity
      ↓
Spec Allocator
      ↓
Updated VCO Spec
      ↓
Context-aware VCO BlockTB
      ↓
SystemTB Re-evaluation
      ↓
Final VCO Spec
```
V1 跑通以后扩展到：
```text
PFD/CP
Loop Filter
VCO
Divider
```
Architecture 仍固定。
Problem 1 扩展成：
```text
Multi-block behavioral contracts
Cross-block context
Dependencies
Coupling
```
Problem 2 扩展成：
[
SystemSpec
\rightarrow
Joint\ BlockSpec\ Allocation
]
主要研究：
```text
multi-block spec budgeting
coupled sensitivity
feasible-space search
```
V3 才逐渐释放 Problem 1 前半部分：
```text
Architecture decomposition
Block partition
Block split / merge
Contract construction
```
未来可以进一步支持：
```text
Integer-N CPPLL
Fractional-N PLL
ADPLL
```
最终接近：
[
SystemSpec
\rightarrow
Architecture
\rightarrow
BehavioralAbstraction
\rightarrow
BlockSpecAllocation
]
V3 是长期目标，不应阻塞 V1/V2。
V1 的目标是：
用 behavioral simulation 先证明 workflow，而不是马上追求真实工程模型精度。
未来项目成熟后，应能够把 simulation backend 替换成真实 circuit simulation 或 engineering data，而尽量不修改上层 Agent workflow。
当前主要负责：
```text
Behavioral VCO model
Simplified PLL model
SystemTB
VCO BlockTB
Parameter sweep
Context extraction
Raw simulation generation
```
优先使用可 batch execution 的 MATLAB functions/scripts。
Simulink 只有在明显改善 PLL modeling 时再使用。
作为 orchestration layer：
```text
Schema validation
MATLAB invocation
Data exchange
Residual calculation
Sensitivity analysis
Agent loop
Iteration control
Trajectory logging
Result generation
Visualization
```
MATLAB 与 Python 之间优先使用：
```text
JSON
CSV
MAT
```
进行结构化通信。
V1 不需要复杂 multi-agent framework。
可以先使用一个 Agent，通过不同 task context 承担两个角色：
```text
Problem 1:
Abstraction Reasoner

Problem 2:
Spec Allocator / Search-Space Controller
```
从第一版开始将：
```text
Agent Logic
```
与：
```text
Simulation / Engineering Data Backend
```
解耦。
建议设计统一接口：
```text
characterize_block(...)
evaluate_system(...)
extract_context(...)
run_sweep(...)
```
当前实现：
```text
MatlabBehavioralBackend
```
未来可以替换为：
```text
Spectre / SpectreRF Backend
SPICE Backend
Verilog-A Backend
Engineering Data Backend
Silicon Measurement Backend
```
核心思想：
[
\boxed{
Synthetic\ Simulation\ Today
\rightarrow
Real\ Engineering\ Data\ Later
}
]
而：
[
SystemSpec
\rightarrow
BlockSpec
]
这一 workflow 尽量保持不变。
V1 不要求 transistor-level accuracy。
但 behavioral model 必须能够表现：
```text
nonlinearity
context dependency
trade-off
```
例如：
f_0
+
K_1(V_{ctrl}-V_0)
+
K_2(V_{ctrl}-V_0)^2
]
从而：
\frac{\partial f_{osc}}
{\partial V_{ctrl}}
]
不是严格常量。
Phase Noise 可以建模为：
g(
V_{ctrl},
f_{osc},
Power,
f_{offset}
)
]
重点是让 Demo 中能够真实出现：
```text
Contract insufficient
→ Simulation detects mismatch
→ Agent refines abstraction
```
VCO Contract 中保留：
```text
DC
TRAN
PSS
PNOISE
```
作为 evaluation taxonomy。
当前 MATLAB backend 可分别映射为：
```text
DC
→ static sweep

TRAN
→ time-domain simulation

PSS
→ steady-state characterization

PNOISE
→ behavioral noise / PSD evaluation
```
未来接入真实 circuit simulator 时，可以保持 schema 不变，只替换 backend。
SystemTB 至少输出：
```text
Metrics
Residuals
Context
```
例如：
```yaml
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
```
Sensitivity 必须由 deterministic sweep / finite difference 产生，不由 LLM 猜测。
例如：
[
\frac{\partial Jitter}{\partial PN_{VCO}}
]
[
\frac{\partial Jitter}{\partial K_{VCO}}
]
[
\frac{\partial LockTime}{\partial K_{VCO}}
]
Problem 1 Agent 的动作限制为：
```text
add/remove variable
add/remove context
modify dependency
modify validity
change representation
```
Problem 2 Agent 的动作限制为：
```text
tighten
relax
keep
adjust_range
select_next_search_region
```
Agent 不允许：
```text
modify System Spec
modify pass criteria
invent simulation results
declare final PASS
```
最终应能够运行类似：
```bash
python run_demo.py --case vco_demo_01
```
并清楚展示：
```text
PLL System Spec
```
展示 VCO behavioral data model。
展示：
```text
Contract v0
→ validation failure
→ missing context/dependency identified
```
例如：
[
PN
\rightarrow
PN(V_{ctrl},f_{offset})
]
得到：
```text
Validated VCO Contract
```
例如：
```text
Jitter FAIL
Lock Time PASS
```
同时输出：
```text
Residual
System Context
```
展示哪些 VCO variables 最影响失败 metric。
Agent 根据：
```text
Residual
Sensitivity
Context
History
```
提出新的 VCO specification。
检查新的 VCO spec 在真实 system operating envelope 中是否成立。
重新运行 SystemTB。
最终必须产生：
```text
Before optimization
vs.
After optimization
```
最重要的最终产物：
```text
final_vco_contract.yaml
final_vco_spec.yaml
```
最终 Demo 应能明确回答：
[
\boxed{
Given\ this\ PLL\ SystemSpec,
what\ VCO\ BlockSpec\ is\ required?
}
]
每次运行建议产生：
```text
results/<run_id>/

system_spec.yaml

contract_v0.yaml
final_vco_contract.yaml

initial_system_evaluation.json
sensitivity.json
final_system_evaluation.json

final_vco_spec.yaml

trajectory.jsonl
summary.md

plots/
    tuning_curve.png
    phase_noise_vs_context.png
    optimization_trajectory.png
    sensitivity.png
```
图表保持科研表达，不追求复杂 UI。
至少展示：
```text
VCO tuning curve
PN vs Vctrl
System residual vs iteration
Sensitivity
```
V1 不要求完整 PLL 自动设计。
只有以下四件事真实跑通即可认为 Demo 成功：
Agent 能够生成机器可读：
```text
VCO Behavioral Contract
```
Simulation 能够发现至少一次 contract deficiency，并驱动：
```text
Contract Refinement
```
SystemTB 能够产生：
```text
Metric
Residual
Context
Sensitivity
```
并驱动 Spec Allocator。
系统至少完成一次：
```text
SystemTB
→ Agent Update
→ VCO BlockTB
→ SystemTB
```
最终输出一组经过 simulation validation 的：
[
\boxed{
VCO\ BlockSpec
}
]
Agent 负责提出 hypothesis。
Simulator / engineering data 负责判断实际表现。
多个 Block Spec allocation 可能同时满足 System Spec。
最终结果根据：
```text
System satisfaction
Block feasibility
Margin
Robustness
Engineering cost
```
选择 preferred solution。
SystemTB 的 metric definition 和 pass criteria 来自 System Spec。
优化过程中不能为了当前 candidate 而修改 target。
BlockTB 必须考虑：
[
SystemTB
\rightarrow
Context
\rightarrow
BlockTB
]
而不是只在 arbitrary nominal point 下验证。
Agent 重点负责：
```text
what to model
what to modify
where to search
```
numerical tools 负责：
```text
simulation
measurement
sensitivity
optimization
```
优先让：
[
VCO\ V1
]
完整跑通。
不要在第一阶段同时实现：
```text
full PLL
automatic architecture generation
transistor sizing
layout
large multi-agent framework
```
整个开发严格分阶段推进。
第一次回复只提交：
必须回答：
1. 项目的最终 System-to-Block Spec 目标；
2. Problem 1 的输入、输出和核心难点；
3. Problem 2 的输入、输出和核心闭环；
4. Problem 1 与 Problem 2 如何连接；
5. 什么是 Optimization Failure；
6. 什么是 Abstraction Failure；
7. Agent 与 deterministic tools 的职责边界；
8. V1 / V2 / V3 的递进关系；
9. 为什么 V1 选择 VCO；
10. V1 最终要证明什么。
此阶段：
```text
Do NOT write implementation code.
Do NOT create repository files.
```
提交后停止。
只有我明确回复：
```text
Project understanding approved.
Proceed to V1 framework design.
```
才能进入这一阶段。
需要提交：
```text
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
```
重点说明：
每个模块吃什么数据、输出什么数据、谁调用谁。
不要立即进行大规模实现。
提交框架后再次等待审核。
只有我明确批准 Framework Design 后，才能开始编码。
实现顺序优先为：
```text
1. Data schemas

2. MATLAB VCO behavioral model

3. VCO BlockTB / characterization

4. Simplified PLL SystemTB

5. Python simulator adapter

6. Residual + sensitivity analysis

7. Deterministic heuristic baseline

8. Problem 1 Agent

9. Problem 2 Agent

10. Complete closed loop

11. Demo output / trajectory / plots
```
原则：
[
\boxed{
Simulator\ and\ Data\ Interface\ First
}
]
不要先搭大型 Agent framework。
V1 完成后不要直接进入 V2。
首先提交：
```text
What was implemented
Which assumptions are synthetic
Which parts are deterministic
Which parts use Agent reasoning

Problem 1 trajectory
Problem 2 trajectory

Initial vs final System metrics
Initial vs refined VCO contract
Final VCO Spec

Simulation count
Failure cases
Known limitations
```
同时必须说明：
如果未来将 MATLAB behavioral data 替换成真实工程数据，哪些模块可以保持不变，哪些模块需要替换。
等待我审核 V1。
只有 V1 workflow 被确认有效后，再开始 V2。
整个项目始终围绕一个核心目标：
[
\boxed{
System\ Specification
\rightarrow
Validated\ Behavioral\ Block\ Specification
}
]
V1 通过 VCO 证明这条链可以成立；
V2 将其扩展到多个固定 PLL Blocks；
V3 再研究 Architecture Decomposition 和 Adaptive Block Partition。
不要因为最终目标很大而过度设计第一版。