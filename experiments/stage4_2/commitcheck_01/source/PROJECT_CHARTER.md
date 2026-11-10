# PLLAgent — 行为级联合 BlockSpec 分配主线重构与自动化实现

## 一、任务背景与新的研究定位

本项目此前已经进行了多阶段研究，包括：

* PLL_AGENT2 的 Agent 设计与编排探索；
* PLL_BASELINE 的 PLL 系统规格、模块性能空间、物理关系、行为级仿真与联合分配工作；
* Legacy Phase 2 的候选搜索、模型反馈、实现重选及有限规格重分配；
* M0.5 的 Workflow Runner；
* M0.6 的模型校准反馈；
* M0.7 的物理证据接入；
* G1/G1.1 的 ngspice 混合级 PLL 电路验证。

经过重新明确课题目标，现阶段不再研究真实晶体管实现与物理验证。

**新的唯一研究主线是：**

给定 SystemSpec、固定 PLL 拓扑和各 Block Space Model，研究一种以 LLM 为核心、受物理关系和约束指导的联合 BlockSpec 分配策略，尽可能在首次或极少数次尝试中得到高质量、可行的模块性能分配，并由完整 PLL 行为级 Testbench 最终验证。

最终交付为：

**SystemSpec → Joint BlockSpec Allocation → Behavioral Verification → Verified Joint BlockSpec**

如果首次分配未通过，则利用行为级违例诊断和参数敏感性，有依据地修复或重新联合分配。

本轮不是简单迁移旧代码，而是从已有项目中提炼符合这一主线的最小、清晰、可扩展的研究系统，并实现至少一条端到端可运行的自动化流程。

## 二、总体要求

### 1. 不推倒重来，也不保留不必要的复杂度

先检查已有源码、接口、模型、实验和正式运行记录，再决定哪些直接复用、哪些适配、哪些隔离归档。

优先复用成熟的：

* SystemSpec 数据定义；
* 固定 PLL 拓扑描述；
* Block Space Model；
* PLL 系统与模块物理关系；
* 联合 BlockSpec 候选生成及搜索；
* MATLAB/Python 行为级模型；
* Testbench 测量与 Pass/Fail 判定；
* Workflow 运行、状态跟踪及结果导出。

不要因为当前工程已有大量反馈、证据、物理验证接口，就把它们继续引入新主线。

### 2. 保留 LLM 的真实决策作用

不能把所有参数、分配顺序和调整规则写死，再让 LLM 只负责解释结果。

应该允许 LLM 根据 SystemSpec、Block Space、物理耦合关系及行为级评价结果，决定：

* 如何形成初始联合分配；
* 哪些模块参数优先确定；
* 如何协调跨模块性能折中；
* 首次失败后调整哪些参数；
* 何时局部修复、何时重新联合搜索；
* 何时停止并报告未找到可行解。

同时，LLM 不能绕过物理约束检查，也不能自行宣布行为级仿真通过。

### 3. 新系统只验证行为级可行性

本轮不需要：

* ngspice；
* MOS 晶体管模型；
* PDK；
* CP/VCO 真实器件能力表征；
* 物理 Evidence Adapter；
* 电路实现重选或 sizing；
* 全晶体管 PLL 验证。

原有成果可以归档保留，但不能成为新自动化流程的前置依赖。

### 4. 保护历史项目

不得直接在冻结的 PLL_BASELINE 上进行破坏性修改。

先确认各 Git 仓库、Worktree、分支和正式运行记录，再建立一个新的、唯一明确的行为级研究主线工作区。

不删除旧源码、不覆盖旧实验、不修改已冻结的原始结果。

---

# 阶段 P0：审计已有工程并提炼可复用能力

## P0.1 核对来源

重点检查：

1. PLL_AGENT2 的 Agent 架构、Prompt、规划方法、工具接口、策略与状态编排。
2. PLL_BASELINE 的 SystemSpec、Block Space、物理关系、联合候选生成、MATLAB/Python 行为模型和 TB。
3. Legacy Phase 2 的候选搜索、要求重新分配与行为反馈逻辑。
4. M0.5 的 Policy / Runner / Guard / Executor。
5. M0.6、M0.7 的新增模块与依赖关系。

对上述内容必须以实际可访问的源码和运行记录为准。

如果某个工程不存在或源码不完整，明确列出缺失内容，不允许根据名称猜测它已经具备的功能。

## P0.2 输出模块取舍表

对每个已有重要模块给出：

* 原始文件路径；
* 当前功能；
* 新主线是否需要；
* 直接复用、适配、隔离或暂不使用；
* 保留或不保留的理由；
* 与其他模块的依赖关系。

特别检查旧项目是否已有能够真实执行的联合候选搜索和规格重新分配逻辑，避免重新开发已有能力。

## P0.3 确定主线架构

输出新的模块设计、唯一入口、数据流和最小依赖图。

**阶段产物：**

* `P0_EXISTING_SYSTEM_AUDIT.md`
* `P0_MODULE_REUSE_MATRIX.md`
* `P0_TARGET_ARCHITECTURE.md`
* `P0_MIGRATION_PLAN.md`

要求明确指出哪些旧项目成果会进入新主线，哪些只保留为历史参考。

完成审计后继续实施，不能仅提交架构建议就停止。

---

# 阶段 P1：重新定义统一的规格分配问题和模块接口

## P1.1 统一数据合同

至少定义以下数据对象：

**SystemSpec**

整机目标和约束，包括指标名称、单位、目标值、比较方向、允差、测量条件及其来源。

**FixedTopology**

PLL 固定模块与连接关系，例如：

PFD → CP → LF → VCO → Divider → PFD。

**BlockSpaceModel**

每个 Block 的可分配性能参数、范围、约束、单位、适用域，以及跨模块耦合条件。

**JointBlockSpec**

一次完整的联合模块规格分配，必须包含所有必需 Block 的参数和共同条件。

**BehavioralEvaluation**

联合候选经过行为级预测或仿真后得到的系统指标、合法性、约束违例、裕量和状态。

**AllocationAttempt**

每一次候选提议及其来源、策略、验证结果、评价成本和修改理由。

**AllocationResult**

最终候选、行为级验收结论、完整轨迹、首次分配结果以及运行环境。

需要区分：

* 分配的 BlockSpec；
* 策略预测的系统性能；
* 行为级 TB 实际测量的系统性能。

不能将预测值直接当作独立 TB 的测量值。

## P1.2 建立系统与模块物理映射

尽量复用 PLL_BASELINE 的物理关系和已有模型，不重写另一套不一致的公式。

明确：

* 哪些 SystemSpec 由哪些模块参数共同影响；
* 哪些关系可以通过解析近似快速计算；
* 哪些指标必须由行为级瞬态或频域验证获得；
* 哪些模块参数是独立变量；
* 哪些参数受到共同约束；
* 模型有效域和单位约定。

尤其避免 Hz/V 与 rad/s/V、相位与频率、反馈频率与 VCO 频率等概念混用。

若某项 SystemSpec 当前没有可信的行为级测量实现，明确标记为 UNSUPPORTED，不得假装验证通过。

## P1.3 建立统一约束检查

开发独立于 LLM 的 Constraint Checker，检查：

* 所有必需 Block 的分配是否完整；
* 参数与单位是否合法；
* 是否位于 Block Space；
* 跨 Block 关系是否满足；
* 模型是否处于有效域；
* 是否存在明显的物理或系统约束冲突。

**阶段产物：**

* 统一数据接口；
* 物理映射与 Block Space 适配模块；
* 确定性约束检查器；
* 数据合同及单元测试。

---

# 阶段 P2：建立新的最小自动化编排主线

建议采用以下结构，具体文件布局根据 P0 的复用审计确定：

```text
SystemSpec + Topology + BlockSpace
               |
               v
      Problem / Mapping Builder
               |
               v
       Allocation Policy
               |
               v
       JointBlockSpec
               |
               v
       Constraint Checker
               |
               v
     Fast Behavioral Screening
               |
               v
     Full Behavioral PLL TB
               |
               v
       Feasibility Scoring
               |
        +------+------+
        |             |
       PASS          FAIL
        |             |
        v             v
   Final Result   Failure Diagnosis
                      |
                      v
               Repair / Reallocation
                      |
                      +----> Allocation Policy
```

## P2.1 最小模块职责

建议形成以下职责边界：

1. **Problem Builder**：将输入转为规范化的联合分配问题。
2. **Physics Mapping / Block Space**：保存物理关系、合法域和跨模块约束。
3. **Allocation Policy**：生成完整联合候选，支持不同策略替换。
4. **Constraint Checker**：快速检查候选合法性。
5. **Behavioral TB Adapter**：调用已有 MATLAB/Python 行为级 PLL Testbench。
6. **Metrics & Scoring**：测量 SystemSpec 及裕量，产生明确的 PASS/FAIL/UNKNOWN。
7. **Failure Diagnosis**：识别违例指标和可能需要调整的模块参数。
8. **Orchestrator**：控制候选、验证、反馈、预算和停止。
9. **Reporter**：输出联合规格、验证报告和完整执行轨迹。

以职责为主，不要求机械创建九个类或九个文件。优先最小实现，不构建多余的 Agent 框架。

## P2.2 确定性流程与动态策略的分界

**Orchestrator 固定执行安全和验收步骤：**

* 输入检查；
* 候选结构检查；
* 真实 TB 调用；
* 结果保存；
* 预算限制；
* 停止条件；
* 报告生成。

**Allocation Policy 决定设计内容：**

* 初始联合规格；
* 参数选择依据；
* 反馈后的调整方向；
* 局部修复或整体重新分配；
* 候选探索优先级。

不能让 Policy 决定是否跳过必须执行的验证。

## P2.3 行为级 TB 是唯一最终验收依据

优先复用已有且可运行的行为级验证器。

如果已有 MATLAB Testbench 是主实现，则通过稳定接口调用它；不应为了统一 Python 项目而无必要地重写整个 MATLAB 模型。

如果 Python 已有等价且通过回归验证的实现，可以选择适合自动化的后端。

必要时提供 Backend Adapter，但不要求同时维护两套新的行为模型。

验证应根据 SystemSpec 实际支持的指标运行相应测试，例如：

* 输出频率与反馈关系；
* 锁定状态、锁定时间；
* 相位误差；
* 环路带宽、相位裕度；
* Vctrl 有效范围；
* 其他已有且可信的行为级指标。

必须区分瞬态验证和频域验证。不能用频率最终达到目标代替全部动态约束检查。

## P2.4 自动化停止条件

允许：

* 行为级 PASS，完成交付；
* 行为级 FAIL，分析后继续有限次数尝试；
* 输入非法或模型超域，给出明确错误；
* 仿真异常，输出 UNKNOWN；
* 预算用尽且未找到可行候选，如实报告。

不允许无限循环、隐式放宽 SystemSpec、以快速预测结果代替完整 TB。

**阶段产物：**

* 可运行的统一主入口；
* 一条无需人工修改代码的端到端流程；
* 明确的策略接口；
* 行为级 TB 的真实执行记录；
* 完整候选轨迹。

---

# 阶段 P3：实现可以比较的 LLM 联合分配策略

这是新课题的核心研究部分，不能仅让 LLM 负责解释已有答案。

## P3.1 必须保留一次性分配能力

首先实现一种 **Physics-informed LLM Initial Allocation** 策略。

提供给 LLM：

* SystemSpec；
* 固定拓扑；
* Block Space；
* 关键物理关系；
* 联合约束；
* 参数单位；
* 必要的解析设计先验。

让 LLM 提出完整的 JointBlockSpec，并简要说明参数选择依据。

**必须在第一次调用 TB 之前完整保存首次候选。**

该候选不得使用本次任务中后续仿真的失败信息进行事后修正。

## P3.2 实现反馈后的有限修复策略

当完整行为级验证 FAIL 时，将结构化反馈提供给 LLM：

* 哪项 SystemSpec 未满足；
* 偏离目标多少；
* 哪些指标已经满足；
* 关键参数与指标之间的关系；
* 当前候选的约束裕量；
* 当前剩余预算；
* 既有尝试及失败原因。

允许 LLM 提议：

* 调整某个 Block 的目标；
* 协调 CP/LF/VCO 等模块之间的参数折中；
* 生成新的完整联合分配；
* 放弃当前候选并探索其他合法区域。

但每次修改都必须通过 Constraint Checker 和完整行为级验证。

不要写死“锁定时间不达标就固定增加某个电流”等唯一规则。

LLM 应能基于物理信息提出方案，而程序负责验证是否有效。

## P3.3 同时保留非 LLM 基线

至少保留：

* 原有解析或规则式分配方法；
* 一种合理的常规搜索或优化方法；
* LLM 首次分配策略；
* LLM + 有限反馈修复策略。

所有方法通过相同的 Policy 接口运行，并使用相同输入、Block Space、行为验证器和评价预算。

如果 LLM 调用接口不可用，必须明确标记该策略未执行；不得用固定规则或 mock 输出伪装成真实 LLM 分配。

## P3.4 记录 LLM 的真实作用

记录：

* 使用的模型与策略版本；
* 结构化输入与输出；
* 首次提出的 BlockSpec；
* 每次修改理由；
* 实际调用次数和可用的 token/成本信息；
* 每次行为级验证结果。

保证未来能够区分：

“LLM 自己首次提出可行候选”

与

“LLM 在多次行为级反馈后找到可行候选”。

**阶段产物：**

* 可替换的 Allocation Policy；
* LLM 首次分配；
* 失败诊断与有限修复；
* 非 LLM 对照策略；
* 完整分配与验证轨迹。

---

# 阶段 P4：建立行为级端到端验收实验

不要只用一个容易通过的 80 MHz 案例证明系统有效。

## P4.1 最小验收案例

至少准备三类实际可执行的 SystemSpec：

1. 已知可行的常规目标；
2. 约束更紧但存在可行解的目标；
3. 已知不可行，或者模型有效域不足的目标。

如果当前无法证明某个目标不可行，必须标记为“未找到或未知”，不能臆造不可行证明。

可以复用既有 80 MHz/84 MHz 行为级案例，但必须保持原 SystemSpec 不变，并确认适用域及行为验证支持。

## P4.2 验收指标

必须自动输出：

* First-pass Feasible Rate；
* Evaluations to First Feasible；
* Success Within Budget；
* Constraint Violation；
* Minimum Normalized Margin；
* Predicted vs Verified Metric Error；
* Strategy Runtime / Evaluation Cost。

这些指标需要在不同 SystemSpec 和不同策略之间可比较。

## P4.3 完整输出

成功案例至少导出：

```text
outputs/<run_id>/
  input_system_spec.json
  block_space_snapshot.json
  topology_snapshot.json
  initial_joint_block_spec.json
  final_joint_block_spec.json
  constraint_checks.json
  behavioral_tb_results.json
  system_metrics.json
  allocation_trace.jsonl
  run_manifest.json
  report.md
```

若已有行为级模型能够生成波形，可附加相位、频率、Vctrl 等主要曲线。

最终报告应明确：

* 系统要求是什么；
* 各 Block 最终分配了什么；
* 首次分配是否通过；
* 若失败，如何有依据地调整；
* 最终哪个候选通过了 TB；
* 哪些指标满足；
* 是否存在尚未验证的 SystemSpec；
* 一共消耗了多少次行为级评价。

## P4.4 回归与可复现性

要求：

* 不破坏旧工程；
* 核心接口有单元测试；
* 同输入、同确定性配置可复现；
* LLM 结果可以通过保存的实际提议进行离线回放，但不得将回放冒充新的 LLM 调用；
* 真实行为级 TB 必须实际执行；
* 不能仅用 Python 模拟一个 PASS 响应作为端到端验收。

**阶段产物：**

* 自动化端到端演示；
* 多种 SystemSpec 实验；
* 各策略的公平对照；
* 输出文件及可复现命令；
* 回归测试报告。

---

# 阶段 P5：项目收束与正式交付

完成上述阶段后，对新主线进行一次最终审计。

## 应重点检查

1. 是否存在唯一清晰的主入口。
2. 是否可以从 SystemSpec 自动得到经过行为级 TB 验证的 Joint BlockSpec。
3. Block Space 与物理映射是否真正影响候选生成。
4. LLM 是否实际决定候选和调整方案，而不是仅写解释。
5. 是否能够识别首次分配失败并进行有限修复。
6. 是否保留首次分配结果和全部评价成本。
7. 是否有非 LLM 基线，能够衡量 LLM 的贡献。
8. 是否仍然依赖不必要的 ngspice、物理反馈或历史 G1 结果。
9. 是否误把行为级 PASS 宣称为晶体管级实现可行。
10. 是否保留旧项目并能追溯复用来源。

输出：

* `MAINLINE_ARCHITECTURE.md`
* `MODULE_REUSE_REPORT.md`
* `BEHAVIORAL_ALLOCATION_WORKFLOW.md`
* `POLICY_COMPARISON_REPORT.md`
* `END_TO_END_ACCEPTANCE.md`
* `LEGACY_ARCHIVE_PLAN.md`

最后给出：

* 新主线的目录结构；
* 修改文件与新增文件；
* 实际复用的 PLL_AGENT2 / PLL_BASELINE 能力；
* 真实执行命令；
* 测试结果；
* 已完成的自动化能力；
* 尚待研究的 LLM 策略问题；
* 推荐的下一阶段研究实验。

## 六、最终验收标准

本轮必须至少完成一条真正可运行的纵向流程：

**输入一份 SystemSpec 和给定的 Block Space → 自动产生联合 BlockSpec → 通过真实行为级 PLL TB 计算系统性能 → 按冻结 SystemSpec 判断 → 输出验证报告。**

在此基础上，验证至少一种真实 LLM 提议策略和一种非 LLM 基线；若 LLM 外部服务不可用，应先完成可运行的非 LLM 纵向流程，并明确将真实 LLM 验收列为未完成，不得伪报完成。

对于首次 FAIL 的案例，应能够根据真实行为级评价结果产生下一组有依据的联合候选，并完成有限复验。

**完成标准是获得一个真正服务于研究问题的最小自动化系统，而不是增加多少个模块、多少个 Agent 或多少个工具。**

## 七、执行纪律

* 每个阶段必须先交付可检查产物，再继续下一阶段。
* 优先实现端到端纵向流程，避免只完成大量基础框架却不能运行。
* 先审查再复用；不凭文件名推断旧工程能力。
* 禁止覆盖冻结规格、历史数据及旧代码。
* 禁止为了让 TB PASS 而放宽 SystemSpec。
* 禁止使用模拟的 LLM 回复或虚构行为仿真结果冒充正式实验。
* 若资源有限，优先完成 P0、P1、P2 的可运行最小系统，再实现 P3 的 LLM 策略和 P4 的比较实验。
* 不启动晶体管级验证、M0.7 物理证据反馈、G1/G2 或其他非主线开发。

**请将全部工作收束到一个目标：让 PLLAgent 的研究重点真正变成“LLM 如何更准确、更高效地完成行为级联合 BlockSpec 分配”，并通过真实行为级 TB 与公平基线验证这一能力。**
