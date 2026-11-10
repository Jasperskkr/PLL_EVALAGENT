# Stage 1.5 — Establish a Trustworthy Behavioral PLL Block Space Model

## 1. 你的角色与最终目标

你是本项目的资深 PLL 系统建模专家、AMS Spec Allocation 研究工程师和科学计算架构师。

项目目前已经完成 Stage 1：

* MATLAB FactorGraph 中部分物理关系已迁移至 Python。
* 已建立 41 项 Variable Semantics Mapping。
* 已实现 M1 理想 PLL 锁定点频域模型。
* 已通过默认工作点、扰动点及异常条件的数值测试。
* 已有隔离的 SystemSpec v0 和 Block Space v2 Draft。

**本阶段的核心任务不是开发 Allocation Algorithm，而是确认后续 Allocation 究竟应该在什么 Block Space 内进行，以及这些 Block 参数到 System Performance 的映射有多可信。**

最终必须交付一套可实际使用、可执行、可验证、可持续修正的：

**Behavioral Block Space Model v1**

其用途是在后续研究中支持：

SystemSpec → Physics-guided BlockSpec Allocation → Behavioral Verification → Feedback。

### 研究边界

1. 只考虑行为级 PLL 系统建模及 Spec Allocation。
2. 不考虑 PDK、晶体管尺寸、版图或硅实现可行性。
3. 允许人工定义行为参数范围，不要求范围来自真实芯片表征。
4. 优先提高模型在声明实验域内的预测准确性，而不是无限扩展参数数量。
5. 允许模型存在近似误差，但必须显式记录误差和验证状态。
6. 暂时不开发 LLM Agent、BO、逆向分配器或新的 GUI。

---

## 2. Task A — 冻结研究问题与 SystemSpec

首先审查已有 SystemSpec v0、Block Space v2、Variable Mapping 和 PLL 拓扑定义。

以当前已冻结的实验配置为唯一依据，不得未经批准更换拓扑、设计频率、SystemSpec 指标或目标范围。

如果当前配置仍采用 Stage 1 的 Integer-N CPPLL、10 MHz Reference、N=8、80 MHz Output，以及 BW/PM 目标，则以这些配置开展实验。

若文档存在不同版本或冲突，明确记录冲突并指出优先采用的版本及理由，不要自行混合不同版本。

最终明确：

* 哪些是固定的系统条件。
* 哪些是必须满足的 SystemSpec。
* 哪些是诊断指标。
* 哪些指标已有正向映射。
* 哪些指标尚不能可信预测或验证。

**验收要求：必须能够明确回答，目前这套 Block Space 具体要服务于哪些 SystemSpec。**

不得将尚未实现的 Jitter、Lock Time、Static Phase Error 等指标默认为已受支持。

---

## 3. Task B — 建立正式的 Block Space Model

以现有 41 项 Variable Mapping 为基础，建立一份真正可被程序使用的 Block Space，而不只是变量对照表。

重点覆盖：

* PFD / Charge Pump
* Loop Filter
* VCO
* Divider

对每个 Block，至少明确以下信息：

### 3.1 变量定义

* Block 名称及变量 ID。
* 物理意义和单位。
* 变量类型：固定条件、自由分配参数、派生参数、模型假设、系统测量。
* 当前是否实际参与模型计算。
* 是否支持连续范围或离散 choices。

### 3.2 参数范围

每个可调参数必须具有明确的实验范围：

* Lower Bound
* Upper Bound 或 Choices
* Nominal Value
* 单位
* 范围来源
* 范围选择理由
* 适用条件

范围可以来自：

1. 现有 MATLAB / Python 实验。
2. PLL 解析公式推导。
3. 已完成的参数扫描。
4. 人工设定的合理行为模型实验范围。

**不得将人工设定的范围包装为已经验证的物理可实现范围。**

尤其要区分：

* 人工定义的搜索范围。
* 公式与数值模型的适用范围。
* 满足 SystemSpec 的联合可行域。

不要求搜索范围内所有参数组合都满足 SystemSpec。

### 3.3 参数耦合

明确不能被视为完全独立的变量，例如：

* Icp 与 Kvco 对环路增益的共同作用。
* Rz、C1、C2 对零极点及 BW/PM 的联合影响。
* VCO f0、Kvco 和控制电压对锁定点的共同约束。
* PFD/CP 非理想参数与静态误差的关系。

重点建立有意义的联合参数域，而不是只提供彼此独立的上下限。

---

## 4. Task C — 审核公式及正向映射的可信度

这是本阶段最重要的技术任务。

逐一审核当前 Block Space 所依赖的物理公式，检查是否能够在已定义参数范围内有效预测 System Performance。

重点包括：

1. Frequency Planning / VCO Tuning。
2. PFD / CP Small-signal Gain。
3. Loop Filter Impedance。
4. Open-loop Transfer Function。
5. Closed-loop Transfer Function。
6. Unity-gain Frequency。
7. Closed-loop −3 dB Bandwidth。
8. Phase Margin。

对每一项公式必须回答：

**What：公式描述的是什么关系？**

**How：由哪些 Block 参数计算得到，采用什么理论假设？**

**Domain：公式在哪些条件下适用？**

**Evidence：目前有什么证据支持其计算正确性？**

**Limitations：哪些影响尚未被模型覆盖？**

建立可追溯的 Equation Registry。每条公式至少包含：

* Equation ID
* 数学表达式
* 输入及输出变量
* 单位及单位转换
* 模型层级
* 公式来源
* 适用条件
* 代码实现位置
* 验证证据
* 已知局限

特别检查：

* Kvco 的 Hz/V 与 rad/s/V 转换。
* VCO f0 与锚点频率的区别。
* LF 网络拓扑与传递函数是否一致。
* 理想 CP 假设与非理想 CP 模型是否混用。
* BW 和 UGF 是否被正确区分。
* PM 是否在正确的单位增益交越点计算。
* 多交越点、非稳定情况或不存在有效 −3 dB 带宽时，数值程序是否正确处理。

不得因为默认点数值吻合，就认定公式在整个参数域都准确。

---

## 5. Task D — 基于参数扫描验证范围与模型表现

在人工确定的 Block Space 范围内，开展系统性正向实验。

目标是回答：

**给定不同的合法 Block 参数组合，当前模型是否能够稳定且合理地预测 PLL System Performance？**

实验至少覆盖：

1. Nominal operating point。
2. 单参数敏感度扰动。
3. 多参数耦合扰动。
4. 参数边界附近。
5. 具有明显性能折中的候选。
6. 不稳定或调谐不可达的组合。
7. 位于 SystemSpec PASS / FAIL 边界附近的组合。

建议至少形成 50 组具有明确采样策略的测试点，并保留全部记录。

不必进行昂贵的全面网格搜索，应根据敏感度、边界和参数耦合选择代表点。

### 必须完成两类验证

**第一类：数值与公式验证**

检查 M1 计算与独立数值路径、解析关系或已有 MATLAB Reference 是否一致。

重点确保公式实现没有错误。

**第二类：行为模型交叉验证**

尽可能复用现有 MATLAB 或 Python Event-driven PLL TB，对能够共同测量的指标进行验证。

例如：

* Frequency Tuning
* Steady-state Frequency
* Locking Behavior
* Control Voltage
* 可比较的稳态或动态响应

对于 BW/PM，如果没有可靠的时域注入测量机制，可以继续以频域模型作为当前评估方法，不要求强行用事件级 TB 提取。

必须说明：

**同一套线性公式的两个数值实现相符，只能证明数值一致，不能等同于独立行为模型验证。**

如果现有 TB 暂时无法对接，则交付明确的限制说明及后续最小验证方案，不允许伪造行为级 PASS。

---

## 6. Task E — 确立用于后续 Allocation 的正式实验域

根据公式审核、模型计算及扫描结果，形成最终推荐的 Block Space Model v1。

必须明确区分：

### A. Declared Parameter Domain

人工选定、允许搜索的行为参数范围。

### B. Model Validity Domain

现有公式和模型能够有效计算的区域。

### C. SystemSpec Feasible Region

在当前模型下满足系统约束的参数组合区域。

不要求精确求出整个高维可行域，但至少需要通过计算、解析约束及示例证明目标 SystemSpec 在所声明的实验空间内具有合理的可行候选。

至少提供：

* 一组满足当前 SystemSpec 的参考 Block 参数。
* 一组具有一定约束余量的推荐工作点（可以与上一组相同）。
* 若干不满足 SystemSpec 的候选及具体原因。
* 当前最敏感的参数与关键耦合关系。
* 约束最容易失效的边界。
* 尚未验证或可信度较低的区域。

注意：

**存在一个 PASS 参数点并不意味着整个参数范围都可信，也不意味着整个搜索空间已被证明可行。**

如果现有范围内找不到满足 SystemSpec 的候选，不得私自修改 SystemSpec 或放宽参数范围来制造成功。

应报告问题来源，提出建议修改，等待技术 Leader 决策。

---

## 7. Task F — 建立后续可持续校准机制

当前阶段允许存在模型误差，不要求一次实现全部非理想因素。

但 Block Space 必须能够支持后续根据行为验证结果逐步修正。

要求定义：

* Formula Version
* Parameter Domain Version
* Behavioral Model Version
* Validation Evidence
* Prediction Error
* Known Model Limitations
* Recommended Calibration Action

例如，当 M1 对某一参数区域的 BW 预测与更可信的行为测量存在明显偏差时，应能够记录偏差，并区分：

1. 数值实现错误。
2. 公式假设不适用。
3. 参数定义不一致。
4. 行为模型包含 M1 没有描述的效应。
5. 测量协议不一致。

允许后续建立经验校准或残差修正模型，但不能无记录地覆盖原始物理公式。

**本阶段重点是建立可校准的模型结构，不要求实现复杂的数据驱动校准算法。**

---

## 8. 必须交付的成果

### Deliverable 1 — `BLOCK_SPACE_MODEL_V1`

机器可读的正式 Block Space 配置。

必须能够直接被后续 Allocation Runner 加载，至少包含变量、范围、固定条件、联合约束、模型版本与来源。

### Deliverable 2 — `EQUATION_MAPPING_REPORT.md`

逐项说明：

System Performance ← Physical Equations ← Block Variables。

并说明模型适用范围和公式准确性证据。

### Deliverable 3 — `DOMAIN_VALIDATION_REPORT.md`

展示：

* 参数范围选择依据。
* 扫参策略。
* 参数敏感度及耦合。
* 典型 PASS / FAIL 工作点。
* 不稳定与模型失效区域。
* 尚未解决的问题。

### Deliverable 4 — `FORWARD_MODEL_VALIDATION.csv`

逐案例记录 Block 参数、预测系统指标、验证来源、误差、状态及失败原因。

### Deliverable 5 — `REFERENCE_BLOCKSPEC.json`

一组明确满足当前已支持 SystemSpec、具有可复现验证结果的参考 BlockSpec。

如果仅通过 M1，则明确标记 `M1_VALIDATED`，不得声称已通过完整 M2 Behavioral TB。

### Deliverable 6 — `BLOCK_SPACE_READINESS_REPORT.md`

回答以下问题：

1. 当前真正可分配的 Block 参数有哪些？
2. 每个参数的范围如何确定？
3. 哪些参数之间存在显著耦合？
4. 哪些系统指标已有可信的正向映射？
5. 哪些指标只获得了公式层面的数值一致性？
6. 当前是否已经找到满足 SystemSpec 的参考 BlockSpec？
7. 是否足以启动下一阶段逆向 Allocation 原型？
8. 还需要通过哪些行为验证逐步提高可信度？

---

## 9. 验收标准

本阶段是否完成，取决于以下实际结果，而非生成了多少文档。

**P0 — 必须完成**

* 当前研究的 SystemSpec 与 PLL 拓扑明确且没有被擅自修改。
* 每个可分配 Block 参数都有明确的单位、范围、角色和来源。
* 关键正向映射公式可执行、可追溯、前提条件明确。
* 参数耦合和联合有效域得到合理处理。
* 在声明域内完成代表性扫参及异常分析。
* 至少找到一组满足当前已支持 SystemSpec 的参考 BlockSpec；如客观不可行则提供证据和待决策建议。
* 交付后续 Allocation 可直接消费的机器可读模型。

**P1 — 尽可能完成**

* 与独立数值路径进行交叉验证。
* 尽可能对接现有 Event-driven TB。
* 形成初步模型误差与适用域评估。
* 明确未来需要校准的指标及参数区域。

**禁止事项**

* 不开展管级 sizing。
* 不新增 LLM/BO 搜索。
* 不把模型内部自洽当作行为级真实性证明。
* 不通过修改 SystemSpec 或放宽参数范围制造 PASS。
* 不将未经验证的参数域或公式宣称为高可信模型。
* 不破坏 Stage 1、原 Allocation 框架和历史测试。

---

## 10. 最终总结要求

最终报告必须使用以下结构：

**WHAT：最终得到了怎样的 Block Space Model？**

**HOW：变量范围如何建立，系统指标如何通过公式映射？**

**EVIDENCE：哪些计算和实验支持这套模型？**

**UNCERTAINTY：哪些范围、公式和指标仍不够准确？**

**READINESS：这套模型现在可以支持哪些 Spec Allocation 实验？**

**NEXT：下一阶段应该优先开发逆向分配器，还是进一步完善某一项关键行为模型？为什么？**

完成本阶段后停止，等待技术 Leader 审查，不自行启动 Stage 2。

所有代码、配置、测试与报告必须一并保留，支持独立复核。
