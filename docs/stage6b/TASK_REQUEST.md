# Stage 6B — Sensitivity-Guided Multi-Spec Allocation with Behavioral Feedback

## 0. 项目背景与本阶段目标

当前项目已完成 Stage 1–6A，针对固定 Integer-N CPPLL，已建立：

* 六参数 Block Space Model；
* M1 Physics Mapping，包括 BW、PM、UGF、VCO Tuning 等物理映射；
* Analytical Solver、SLSQP 敏感度优化及确定性 Repair；
* M2 Event-Driven Behavioral Testbench；
* SystemSpec → Joint BlockSpec → M1/M2 Verification 的统一 Pipeline；
* Stage 6A 多指标联合可行性实验。

已有实验表明：

1. M1 可以对 BW、PM 和 VCO 调谐条件进行联合预测与反解。
2. M1 预测可行的候选可能在 M2 中发生 BW 越界。
3. 相同 M1 BW/PM/UGF 的参数组合可能具有不同的 M2 捕获表现。
4. 目前的反馈修复仍主要依赖预定义的物理缩放公式，尚未建立通用的多指标反馈优化机制。

**本阶段目标：实现一个最小可运行的确定性多指标联合分配原型，将物理敏感度分析、联合约束优化和 M2 行为反馈结合起来，验证是否能够在不同 SystemSpec 下自动寻找合理的 Joint BlockSpec。**

本阶段不开发 LLM Agent、不接入真实 LLM API、不引入 BO/TuRBO。

这次的成果应成为后续自适应 Agent 的确定性算法基线。

---

## 1. 主线保护与代码审查（P0）

首先只读检查：

* 当前 Git 分支、HEAD、工作树状态；
* `master`、Stage 5、Stage 6A 的提交关系；
* Stage 6A 的实际源码、实验配置和数据是否存在；
* `block_space/`、`physics_mapping/`、`allocation/`、`verification/`、`pipeline.py`；
* 已有 Sensitivity Optimization、SLSQP、Analytical Solver 和 Repair 的具体实现。

注意：Stage 6A 之前存在未完全提交的工作树成果，不能假设当前 master 已包含所有 Stage 5/6A 功能。

要求：

1. 不得执行 reset --hard、git clean、force push 等破坏性操作。
2. 不得覆盖、清理、stash 或擅自提交原工作树修改。
3. 在确认完整研究基线之后，使用独立工作树或研究分支，例如 `codex/stage6b-sensitivity-allocation`。
4. 如果无法安全隔离当前基线，停止有风险的写入并报告。
5. 保留全部原有 M1/M2 公式、测试协议、Block Space 和历史实验结果。
6. 不得创建第二套独立的 PLL 模型、M2 Verifier 或 Pipeline。
7. 暂不合并 master。

先输出一份简短 Implementation Design，说明计划复用的模块、需要增加的接口、候选搜索方法和测试方案，然后继续执行。不要仅停留在设计文档。

---

## 2. 定义统一多指标分配问题

沿用现有六参数：

x = [Icp, Rz, C1, C2, f0, Kvco]

保持原有参数范围、离散电容组合、PLL 拓扑及物理单位合同。

希望支持的初始指标：

* BW：M1 预测，M2 测量；
* PM：M1 研究级约束，M2 局部工程证据；
* VCO Tuning：物理工作点合法性约束；
* Conditional Capture Time：M2 指定协议下的行为指标；
* UGF：保留作为预测、诊断及未来可扩展指标。

### 2.1 统一 Spec Constraint 接口

请设计一种最小、可扩展的 Spec Constraint 表征。

每项指标至少具有：

* metric_name；
* comparator / lower_bound / upper_bound；
* measurement_source；
* measurement_protocol；
* model_validity；
* measured_or_predicted_value；
* normalized_violation；
* margin；
* verification_status。

所有指标可以进入统一的联合判决机制，但必须区分评价来源和证据等级。

例如：

BW 由 M2 测量判断。

PM 由 M1 预测参与研究级约束。

Conditional Capture Time 由 M2 测量。

尚无法可靠评价的指标必须返回 UNKNOWN / UNSUPPORTED。

不得因为 M1 和 M2 的局部指标通过，就直接标记 FULL_SYSTEMSPEC_CERTIFIED。

### 2.2 统一分配目标

首先寻找满足全部已声明研究约束的候选：

minimize max(0, normalized_constraint_violations)

找到研究级可行候选后，再考虑改善：

* Conditional Capture Time；
* 最小约束裕量；
* 或实验预先指定的次级目标。

优先采用约束可行性判决和词典序目标，不要通过任意加权平均让一个指标的改善抵消另一个硬约束的失败。

所有参数变化之后，都必须重新检查完整联合约束。

---

## 3. 实现最小确定性联合分配流程（核心任务）

设计以下闭环：

SystemSpec
→ Physics Mapping
→ Initial Joint Allocation
→ M1 Sensitivity Analysis
→ Joint Candidate Improvement
→ M2 Behavioral Verification
→ Feedback-guided Local Reallocation
→ Joint Recheck
→ Final Candidate / Failure Report

### Step A：初始物理分配

复用已有 Analytical Solver、物理约束传播和 SLSQP。

通过：

* C1/C2 离散组合枚举；
* BW/PM 物理映射；
* VCO Tuning 合法性检查；
* 约束裕量优化；

生成多组 M1 预测可行的 Joint BlockSpec。

不要永远只保留一组最大 PM 候选。

应优先保留具有代表性的不同电容组合、环路增益分摊方式和调谐工作点的候选。

### Step B：M1 敏感度分析

复用当前 Sensitivity 模块。

检查哪些性能对哪些参数敏感。

优先采用归一化或对数敏感度，避免不同单位造成错误比较。

需要回答：

* 哪些变量主要影响 BW？
* 哪些变量主要影响 PM？
* 哪些变量影响 VCO 调谐？
* 哪些变量存在强耦合或等效性？
* 哪些参数变化会改善一个指标、却损害另一个指标？
* 当前设计最接近失败的是哪个约束？

允许采用已有解析导数或数值差分，但必须记录变量尺度和有效扰动范围。

重点利用物理耦合关系：

* Icp × Kvco 对环路动态的影响；
* Rz、C1、C2 对频域特性的影响；
* f0、Kvco、Vreq 的调谐关系。

必要时使用具有物理意义的派生坐标进行搜索，而不是在原始六维空间内盲目扰动。

所有派生坐标必须正确转换回合法的原始 BlockSpec。

### Step C：M1 联合约束优化

使用现有 SLSQP 或其他已经实现的确定性方法，改善候选的联合约束裕量。

要求：

* 同时考虑所有 M1 可评价的硬约束；
* 不允许只优化 BW；
* 记录调整前后的各项 Spec；
* 保留不同物理区域的候选；
* 不允许通过放宽冻结参数域或规格制造 PASS。

### Step D：M2 Behavioral Verification

对于筛选后的少量候选，调用现有 M2。

至少记录：

* M1 BW、PM、UGF；
* M2 BW；
* Conditional Capture Time；
* VCO 控制电压与有效工作点；
* 捕获过程中的异常状态（如测量协议已有支持）；
* 每项约束的 PASS / FAIL / UNKNOWN；
* 测量包络及收敛状态；
* M2 调用次数和耗时。

不得修改 M2 数值内核或测量协议来配合分配算法。

### Step E：M2 反馈与敏感度引导微调

这是本阶段最重要的新功能。

如果 M2 验证失败，或候选已可行但行为性能仍有改善空间，则利用 M2 反馈继续调整候选。

保留已有 Physics Repair 作为基线方法。

新增一个尽量通用的确定性反馈优化流程：

1. 分析未满足约束及现有约束裕量；
2. 利用 M1 敏感度判断可以调整的变量及预期副作用；
3. 根据 M2 反馈选择少量合理的局部扰动方向；
4. 对不能可靠解析的行为指标，允许用少量成对 M2 扰动估计局部改善趋势；
5. 若 M2 响应非光滑、测量分辨率不足或存在突变，不得把差分结果误当成精确梯度；
6. 采用小规模确定性 Pattern Search / Trust Region 风格的局部搜索；
7. 每次调整后重新检查全部联合约束；
8. 若当前区域无法改善，允许选择另一组已有 M1 预测可行区域；
9. 达到预算或明确停止条件后退出。

不要求实现完整 MADS/NOMAD，也不要引入大型优化库。

优先实现一个简单、可解释、可复现、能够记录每次决策依据的局部搜索器。

**特别要求：不要将某一个 BW 缩放公式硬编码为所有多指标失败的修复方法。**

现有 BW 比例缩放只作为可选的 Physics Repair Baseline。

本阶段希望检验敏感度分析和行为反馈能否指导更一般的联合参数调整。

---

## 4. 三组对照分配策略

请在同一套 SystemSpec、M1/M2 模型、参数范围、测量协议和预算下，比较：

### Method A：Analytical Baseline

Analytical Solver 生成初始候选，M2 验证。

不进行新的联合敏感度优化或行为反馈搜索。

### Method B：M1 Sensitivity-Guided Allocation

Analytical 初始分配
→ M1 敏感度分析
→ SLSQP 联合约束优化
→ M2 验证。

用于评估 M1 敏感度和约束优化是否改善首次候选。

### Method C：M1 + M2 Feedback-Guided Allocation

Method B
→ M2 Verification
→ M2 反馈分析
→ 敏感度引导的确定性局部搜索
→ M1/M2 联合复验。

用于检验行为反馈是否进一步改善候选。

保留原有确定性 BW Repair，必要时作为附加参考对照，但不要将它混同于 Method C 的通用搜索策略。

三种方法需要共用统一评价和判决接口。

---

## 5. 实验场景

先完成两组最小实验，不要盲目扩大场景数量。

### B1：多指标联合分配与捕获性能优化

研究约束：

* BW：150–300 kHz；
* M1 PM ≥ 50°；
* VCO Tuning 合法；
* Conditional Capture Time 按 Stage 6A 已冻结的初始条件和 40 µs 研究上限。

在满足以上研究约束后，尝试最小化 M2 捕获时间。

重点研究：

在 M1 BW/PM 相近甚至相同的情况下，能否通过参数分摊、调谐点或电容组合调整，改善捕获表现？

### B2：紧边界多指标联合分配

研究约束：

* BW：290–300 kHz；
* M1 PM ≥ 70°；
* VCO Tuning 合法；
* Conditional Capture Time 按已有冻结协议进行测量，并作为预先声明的研究约束或次级目标。

重点研究：

当 BW、PM 和参数合法域相互竞争时，敏感度分析与反馈优化能否获得具有更好约束裕量的候选？

不要为了使 Method C 表现更好而选择特定失败点或修改阈值。

如果 E1 中已有边界失败候选，可以用于回归验证和算法调试，但正式算法对照必须使用预先声明的测试场景与公平预算。

### B3：可选预分析，不必完整执行

检查现有 M2 是否支持不同启动初态的版本化测量。

只报告可行性和预期修改范围，不要在本阶段擅自改变正式捕获协议。

---

## 6. 预算、计时与公平性

本阶段为小规模原型实验，不要进行大规模随机搜索。

建议初始预算：

* 每种方法、每个场景最多 6 次新的完整 M2 候选验证，包含最终复验；
* 可以利用 M1 进行较多的廉价筛选，但需统一并记录 M1 预算；
* 使用固定的候选生成规则与确定性搜索顺序；
* 对重复候选使用统一缓存，并报告缓存命中；
* 不要求算法耗尽预算，提前找到满足目标的候选可以停止；
* 如果需要扩大 M2 预算，先记录原因和新增实验的独立结果。

需要分别报告：

1. First-shot Joint Feasibility；
2. Final Joint Feasibility；
3. BW 预测偏差；
4. M1 PM 裕量；
5. M2 Capture Time；
6. 最小归一化约束裕量；
7. M1 评估次数；
8. M2 调用次数；
9. 总运行时间。

注意区分“研究级联合可行”与“完整 SystemSpec 认证”。

不要把 M1 PM 预测 PASS 写成 M2 严格周期 PM 认证。

---

## 7. 软件工程约束与测试

优先复用现有代码。

新增模块应遵守现有架构，不创建另一套独立 Pipeline。

建议按照现有代码结构，最小增量实现：

* 统一多指标 Constraint Evaluation；
* Sensitivity-Guided Candidate Improvement；
* Feedback-Guided Deterministic Local Search；
* 分配过程记录和研究结果输出。

具体模块路径以实际代码审查为准，不必机械照搬建议名称。

新增测试至少覆盖：

* 多指标约束联合判决；
* BW PASS、PM FAIL 不得误报成功；
* M2 BW FAIL 时的反馈处理；
* 捕获失败及 UNKNOWN 状态；
* 参数调整后的全约束重检；
* 参数越界和非法 VCO Tuning；
* 离散 C1/C2 组合切换；
* 敏感度退化、非光滑响应及预算耗尽；
* 与 Stage 5、Stage 6A 结果的回归兼容性。

不能删除历史失败记录、降低原有测试标准或覆盖冻结实验配置。

本阶段禁止真实 LLM API 调用。

---

## 8. 最终交付要求

请交付可执行代码、测试、实验配置、原始结果和总结报告。

### A. Architecture & Implementation Report

说明实际复用了哪些现有模块，新增了哪些模块。

给出完整分配流程图，明确敏感度分析如何影响参数选择，M2 反馈如何影响下一轮搜索。

### B. Algorithm Description

说明：

* 初始可行域如何生成；
* 敏感度如何计算；
* 哪些变量被激活或冻结；
* 联合优化目标如何构造；
* M2 反馈怎样转化成参数调整；
* 局部搜索的步长与停止条件；
* 什么时候切换物理子区域。

要求记录实际执行的算法，不要仅输出概念描述。

### C. B1/B2 Results

每个候选至少保存：

* 输入 SystemSpec；
* 完整六参数 Joint BlockSpec；
* M1 预测；
* M2 测量；
* 全部约束判决；
* 参数修改历史；
* 敏感度结果；
* M2 调用成本。

保留失败候选、历史反馈与搜索轨迹。

### D. Method Comparison

比较 Method A / B / C。

必须回答：

1. M1 敏感度分析是否改善首次分配质量？
2. M2 反馈是否改善联合可行性或捕获表现？
3. 通用确定性局部搜索是否优于已有单指标 Repair？
4. 哪些场景中 Analytical 已经足够？
5. 哪些场景真正需要行为反馈搜索？
6. 哪些复杂度目前仍无法通过六参数 Block Space 表达？

如果 Method C 未优于 A/B，必须如实报告，不要通过额外预算或事后调整规格制造优势。

### E. 下一阶段 Agent 接口建议

最后单独说明：

如果未来接入外层 LLM，哪些决策目前是固定规则，哪些可以开放给 Agent？

例如：

* 候选物理区域选择；
* 参数敏感度解释和变量激活；
* Analytical / SLSQP / Local Search 策略选择；
* M2 验证预算与候选优先级；
* 失败后的区域调整与停止决策。

本阶段只需设计接口和说明决策边界，不实现 LLM。

---

## 9. 最终验收标准

本阶段重点不是追求新优化器一定优于旧算法，而是：

**验证当前 Block Space、M1、M2 和 Sensitivity 模块能否共同构成一种可复用、可解释、可进行行为反馈调整的确定性多指标联合分配方法。**

验收至少要求：

1. B1/B2 可以从 SystemSpec 输入启动完整分配流程；
2. A/B/C 使用可比较的配置和评价合同；
3. 敏感度分析实际参与候选选择或优化，而非只生成报告；
4. M2 反馈能够影响下一轮参数调整，而非仅保存测量结果；
5. 每次调整都重新检查所有参与研究的联合约束；
6. 保留真实失败结果，不得修改 M2 迎合算法；
7. 清楚区分可预测、可测量和未认证的指标；
8. 历史主线测试保持通过，新增研究成果不自动合并 master。

如果本轮发现确定性解析分配已经足够，或者敏感度与 M2 反馈没有带来增量收益，也应明确给出这个结果。

**最终希望形成的不是针对某个 BW 公式的专用修复器，而是一套能够根据不同 Spec 和验证反馈进行联合参数调整的确定性分配基线，为后续 LLM 自适应区域规划及策略选择研究提供依据。**
