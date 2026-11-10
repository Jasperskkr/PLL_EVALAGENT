# Stage 5 — End-to-End Physics-Guided PLL Spec Allocation Feasibility Experiment

## 0. 研究目标

你是资深 PLL 系统设计专家、Spec Allocation 算法研究员、LLM Agent 工程师和科学计算验证专家。

当前项目已完成：

* Stage 1 / 1.5：Block Space Model v1，六参数空间和 M1 物理映射。
* Stage 3A.1：统一 Allocation → M1 → M2 Pipeline。
* Stage 4：M2 Series / Direct Port 局部 UGF/PM 测量。
* Stage 4.2：Physics Mapping Registry、映射能力审查和实验工作点。
* Stage 4.1：闭环扰动、映射工程可信度以及有限参数域验证。

现在暂停扩展模型，开展第一轮真正的端到端 Spec Allocation 对照实验。

### 核心科学问题

给定不同的 SystemSpec：

1. 现有物理映射能否指导 BlockSpec 分配？
2. 分配出的 Joint BlockSpec 是否满足 M1 预测约束？
3. 将 BlockSpec 回代 M2 后，已支持的系统指标是否满足要求？
4. M1/M2 预测误差是否会影响可行性判断？
5. LLM Agent 是否提供了区别于确定性物理求解器的实际价值？
6. 整个流程的时间成本和 M2 调用成本如何？

本阶段要求形成真实实验结果，不只是架构图、模拟日志或测试脚本。

**最重要的验收目标不是所有候选 PASS，而是获得可复现、可比较、能够说明当前研究能力与局限的端到端证据。**

---

## 1. 首先审计当前主线并建立实验基线

开始开发前：

1. 检查 Git HEAD、分支和工作树。
2. 识别实际可运行的统一 Pipeline 入口。
3. 检查 Stage 4、4.1、4.2 的源码是否完整存在。
4. 检查正式 SystemSpec、Block Space、M1、M2 及 Measurement Protocol 的版本。
5. 检查真实 LLM Agent、Analytical Solver、随机/优化策略和反馈修复接口。
6. 确认已有 Stage 4.1 实验成果未被覆盖。

不得因为新实验而执行破坏性的 Git reset、clean 或覆盖已有未提交代码。

优先复用正式 `pll_allocation/` 模块，不建立 `track_c/` 或另一套 Allocation 工程。

### Baseline Smoke Test

首先真实运行当前冻结 SystemSpec：

* fref = 10 MHz。
* N = 8。
* fout = 80 MHz。
* BW 150–300 kHz。
* PM ≥ 50°。
* 保留原始频率容差及其 UNKNOWN 认证边界。

通过现有 Analytical Allocation 生成候选，运行 M1 和 M2。

以前已复现的参考值为：

* M1 BW ≈ 225.000 kHz。
* M2 BW ≈ 226.404 kHz。
* M1 PM ≈ 72.247°。
* M2 严格周期 PM：UNKNOWN。

这些参考值只用于回归检查，不得直接复制进本轮实验结果。

记录实际运行命令、完整参数、源码版本、模型哈希和仿真成本。

若 Baseline 不能复现，先定位故障，不继续开展策略比较。

---

## 2. 最小实现：可变 SystemSpec 实验入口

目前统一 Pipeline 绑定冻结的 SystemSpec。

本阶段允许增加一个**隔离的研究场景输入机制**，使得不同 BW/PM 要求能够通过正式分配链路运行。

建议接口形式：

`python -m pll_allocation pipeline --strategy analytical --scenario experiments/stage5/scenarios/scenario_a.json --out experiments/stage5/runs/a_analytical`

注意：这是期望实现的接口，不得假定当前 CLI 已支持 `--scenario`。

### 必须满足

1. 原冻结 SystemSpec 文件保持不变。
2. 研究场景必须具有独立 ID、版本和 SHA256。
3. 第一版只允许调整：

   * BW 最小值。
   * BW 最大值。
   * PM 最小值。
4. 不允许改变 fref、N、PLL 拓扑、LF 结构或 Block Space 六参数范围。
5. 不允许绕过原有模型版本和测量协议的完整性检查。
6. 必须明确区分正式冻结运行与 Research Scenario。
7. 所有预测和测量结果必须绑定实际使用的 Scenario ID 和 Hash。
8. 修改场景后，所有相应的 M1 约束判断必须随之更新。
9. 禁止改变原有 M2 核心物理模型来适配某个 Scenario。
10. 不修改原始正式规格的语义和验收门限。

特别注意，原先的 M2 Verifier 可能同时依赖 Spec Hash。应该建立显式、版本化的研究场景合同，而不是简单删除哈希校验。

对研究场景执行实际的 M2 BW 测量，并根据该场景阈值判断对应指标。

---

## 3. 冻结实验场景

先使用以下五组实验。

| Scenario            | BW Requirement | PM Requirement | 研究目的                |
| ------------------- | -------------- | -------------- | ------------------- |
| S0 Baseline         | 150–300 kHz    | ≥50°           | 原始能力复现              |
| S1 Moderate         | 180–230 kHz    | ≥60°           | 验证较严格约束的重新分配        |
| S2 Shifted          | 240–280 kHz    | ≥55°           | 验证性能目标移动后的重新分配      |
| S3 Boundary         | 290–300 kHz    | ≥50°           | 测试靠近 BW 上边界的预测风险    |
| S4 Model-Infeasible | 150–300 kHz    | ≥73°           | 测试理想 M1 模型对不可行约束的识别 |

所有场景的输出频率仍为 80 MHz。

### 场景设计要求

S0–S2 已存在一定历史实验依据，但本轮仍需以当前源码重新运行。

S3 是有意设置的边界压力测试。不能为了保证成功而事后修改门限，也不预设该场景必然有 M2 可行候选。

S4 在当前理想 LF 模型下超过已知 PM 上界，预期应得到 M1 模型域内的不可行性结论。

但要严格区分：

* `INFEASIBLE_UNDER_M1_ASSUMPTIONS`
* 真实 CPPLL 物理上绝对不可行

不得将前者夸大为后者。

若系统在 S4 无法生成候选，应返回结构化不可行原因，而不是强行运行 M2 或制造随机候选。

不得根据实验结果重新挑选场景。

---

## 4. 比较三种分配策略

本阶段不新增复杂算法。

优先比较现有能力。

### Strategy A：Physics Analytical Allocation

使用当前确定性物理反解和数值求解器：

SystemSpec → M1 Physics Constraints → Joint BlockSpec

这是主要工程基线。

要求记录：

* 使用的物理公式与求解工具。
* 候选 BlockSpec。
* M1 预测结果。
* 是否满足 M1 约束。
* 求解时间。
* 是否触发确定性 Repair。

### Strategy B：Random / Space-filling Baseline

使用统一 Block Space v1，按预先定义的参数采样规则生成合法候选。

要求：

* 不改变参数域。
* 离散电容只能从声明集合取值。
* 连续变量采样方式和随机种子必须固定。
* 只排除非法参数组合和明确的物理域无效点。
* 不允许偷偷调用 Analytical Allocator 再称为 Random。
* 保留所有尝试和失败原因。

用于回答：

**物理映射是否真正比没有目标导向物理反解的搜索更有效？**

为控制成本，允许先生成一批候选并用 M1 进行廉价评估，但必须记录每个候选的 M1 调用次数，并明确使用该筛选后的策略名称。

不要将 Physics-screened Random 与完全无物理引导的 Random 混为一谈。

### Strategy C：Real LLM + Physics Tools

使用项目现有的真实 LLM Agent 接口。

Agent 可以：

* 查询可用 SystemSpec 及正式模型约束。
* 查询当前 Mapping Registry 中已批准的物理关系。
* 调用 Analytical / Numerical Allocation Tools。
* 查看工具返回的候选和约束残差。
* 选择并提交 Joint BlockSpec。

必须记录：

* 实际 LLM 服务是否调用成功。
* 模型名称。
* 工具调用顺序。
* 工具输入输出。
* Agent 最终候选。
* 是否与 Analytical Baseline 相同。
* Token / API / 墙钟时间成本。
* LLM 是否真正做出了选择，还是直接接受确定性 Solver 的结果。

若缺乏可用 API 配置或调用失败：

1. 明确报告 `REAL_LLM_NOT_EXECUTED`。
2. 仍完成 A/B 两组可运行实验。
3. 可以用 Mock 进行接口回归，但不能称为真实 LLM 实验。

不得把确定性 Repair 伪称为 LLM 自主修复。

### 实验预算

第一轮采用受控的小规模实验：

* S0–S3：每种方法至少产生首个候选或明确的失败结果。
* Random：使用预先冻结的 3 组种子。
* Analytical：记录确定性首个候选。
* Real LLM：有真实 API 条件时，每个适用场景至少尝试一次实际调用。
* 每组实验限制 M2 调用次数，初始建议最多 3 个候选进入完整 M2 验证。
* S4：首先执行不可行性判断，不为凑齐次数强行跑仿真。

对不同策略统一记录预算，明确首个候选与反馈后候选的区别。

如果实际资源不足，优先完成 S0–S2 的三种策略，再扩展 S3/S4。

不要为了追求统计显著性而无限增加仿真次数。本阶段只做可复现的探索性比较，不声称已证明普遍算法优势。

---

## 5. 每个候选都必须执行相同的评估

每次 Candidate Evaluation 分成四层。

### Layer 1：Block Space Validity

检查：

* 六个参数是否在声明域内。
* 离散电容是否合法。
* SI 单位和参数语义是否正确。
* VCO 理论调谐工作点是否有效。
* 是否符合当前固定拓扑。

### Layer 2：M1 Prediction

记录：

* Output Frequency / Vctrl Required。
* BW_M1。
* UGF_M1。
* PM_M1。
* 各项 Spec Margin。
* M1 Prediction Status。
* 可行性及模型适用条件。

### Layer 3：M2 Behavioral Evaluation

运行当前已有行为级 TB。

至少保留：

* 独立 M2 BW 测量。
* M2 BW Measurement Validity。
* 指定初始条件下的 Capture / Lock 观察。
* 输出频率观测及测量精度状态。
* Stage 4/4.1 已有局部 UGF/PM 和工程稳定性证据（在适用且预算允许时）。
* 无法认证的指标及 UNKNOWN 原因。

不要将冷启动捕获实验和暖启动小信号 BW 实验混为同一次测试。

不要通过 M1 公式回填 M2 缺失指标。

### Layer 4：Spec Evaluation

每个指标分别记录：

* Requirement。
* M1 Prediction。
* M2 Measurement。
* Measurement Validity。
* PASS / FAIL / UNKNOWN。
* Error。
* Evidence Reference。

必须明确区分三种结果：

**M1_PREDICTED_FEASIBLE**

表示在 M1 假设下，候选满足当前场景的预测约束。

**M2_MEASURED_SUBSET_PASS**

表示当前 M2 已完成可信测量的受测硬指标满足要求。

必须显式列出实际受测指标集合，不能让该名称暗示完整 SystemSpec 通过。

**FULL_SYSTEMSPEC_VERIFIED_PASS**

仅当全部正式硬约束都存在有效、达到要求的 M2 认证结果时才允许出现。

在现有 PM 和严格频率精度仍为 UNKNOWN 的情况下，不得输出完整 PASS。

另外，只要存在已认证的硬约束 FAIL，就应将该指标记录为 FAIL，而不是因为其他指标 UNKNOWN 就掩盖真实失败。

---

## 6. 首次分配与反馈修复必须分开统计

本轮尤其要分析首次候选质量。

定义两个独立实验阶段。

### Phase A：First-shot Allocation

不使用当前 Scenario 的 M2 验证结果进行候选修改。

记录每种策略提交的第一个候选及其 M1/M2 表现。

其中：

* Analytical 的初次候选是 Solver 第一次正式提交的候选。
* Random 的初次候选按预声明随机顺序确定。
* LLM 的初次候选是实际 LLM 工具编排结束后正式提交的候选。

如 LLM 在提交之前调用确定性 Solver，应标记为 `LLM_TOOL_ASSISTED_FIRST_SHOT`。

不能将“Solver 求解后 LLM 接受结果”称作 LLM 独立完成物理反推。

### Phase B：Feedback-assisted Repair

第一阶段完成后，再研究现有确定性 Repair 能否根据真实 M2 反馈改进候选。

要求：

* 只使用现有已实现的 Repair。
* 不开发新的 LLM Repair 算法。
* 记录真实 M2 Feedback。
* 记录是否生成新候选。
* 对比修复前后 BlockSpec。
* 必须再次运行 M2，才能判定修复效果。
* 如只是收到 Feedback 但未改变候选，应显式记录。

若本轮反馈只有 UNKNOWN 而没有已认证的 FAIL，不应强制进行没有依据的 Repair。

---

## 7. 核心评价指标

要求统一比较：

| Evaluation Metric                     | 研究意义                   |
| ------------------------------------- | ---------------------- |
| First-shot M1 Predicted Feasible      | 分配器能否找到满足预测约束的候选       |
| First-shot M2 Measured BW Pass        | 候选是否满足可可靠测量的 BW 要求     |
| M2 Local Mapping Evidence             | 局部 UGF/PM 与工程动态是否支持 M1 |
| Full SystemSpec Certification         | 完整硬约束是否已认证             |
| M1/M2 BW Prediction Error             | 物理模型的预测误差              |
| M2 Calls to First Supported Candidate | 寻找受支持候选的仿真成本           |
| Wall-clock Time                       | 端到端实际执行时间              |
| Solver / LLM / M2 Call Count          | 区分计算来源                 |
| Feedback Repair Outcome               | 失败反馈是否真正改进候选           |
| Unsupported / UNKNOWN Rate            | 验证覆盖率和可信度缺口            |

注意：

* 不得把 M1 预测 PASS 当作 M2 PASS。
* 不得把工程局部 PM 接受状态当作严格周期 PM 认证。
* 不得只比较成功案例而隐藏失败案例。
* 不得只计算 M2 原生积分时间，而忽略 Python、LLM、测量和搜索开销。
* 不得将有限探索性实验宣称为统计意义上的普遍性能优势。

---

## 8. 结果解释必须回到最初三个研究问题

最终报告不能只给数值表。

必须分别回答：

### Research Question 1：Block Space & Physics Mapping

* 哪些 Spec 具有有效的物理反推关系？
* M1 预测与 M2 实测的差异如何？
* 物理约束实际排除了多少无效候选？
* 当前人工参数域是否足以支持这些研究场景？
* 哪些区域的预测误差较大？
* 结果是否支持当前 Stage 4.2 Mapping Registry 的能力分类？

### Research Question 2：Allocation Strategy & Agent

* 解析求解是否明显优于无目标导向的随机采样？
* LLM 是否生成了不同于确定性 Solver 的候选？
* LLM 的具体价值是工具选择、约束理解、反馈决策还是仅转发工具结果？
* 在相同 M2 预算下，不同策略表现如何？
* 哪些场景需要真正的搜索，而不仅是一次公式反解？

### Research Question 3：Behavioral Verification & Feedback

* M2 是否能够可靠测量分配后的 BW？
* PM/UGF 工程证据是否具有适用域限制？
* 哪些规格仍 UNKNOWN？
* 真实违规候选能否触发正确反馈和修复？
* 预测偏差是否会在临界 BW 场景导致错误判决？

每项研究结论都必须对应实际实验数据。

---

## 9. 最小交付

将全部新增研究文件放入主线：

`experiments/stage5/`

`docs/stage5/`

仅在需要时对现有 `pll_allocation/` 做小范围接口扩展。

必须交付：

1. `STAGE5_EXPERIMENT_PLAN.md`

   * 场景、策略、预算、预声明判据。

2. `SPEC_SCENARIO_CONTRACT.md`

   * 可变 SystemSpec 输入、字段限制、哈希和版本语义。

3. `scenario_results.csv`

   * 各场景、各策略、各候选的 M1/M2 指标和判断。

4. `candidate_trace.jsonl`

   * 每次候选生成、工具调用、M2 运行及反馈记录。

5. `STRATEGY_COMPARISON_REPORT.md`

   * Analytical / Random / Real LLM 的实际结果和成本。

6. `END_TO_END_FEASIBILITY_REPORT.md`

   * 回答三个核心研究问题，并明确成功和失败边界。

7. 必要的新测试。

   * Baseline 回归。
   * 研究场景解析。
   * 场景哈希校验。
   * 不可行目标。
   * 指标级 UNKNOWN/FAIL 传播。
   * 真实 M2 结果绑定。
   * 既有 Pipeline 兼容性。

8. 精简源码审查包与 SHA256 清单。

图表统一使用英文标题、坐标轴及图例。

不得提交密钥、Token、原始大规模波形或无关缓存。

必须记录：

* Git HEAD / 工作树状态。
* Python、编译器和平台环境。
* M1/M2 版本。
* 每组 Scenario Hash。
* 实际执行次数。
* 总仿真成本和墙钟时间。
* 测试通过和失败摘要。

若新接口需要发布到安装包，需明确是否完成源码运行和 wheel 安装验证；不得把二者混为一谈。

---

## 10. 工作范围限制和停止条件

本阶段禁止：

* 扩展 PLL 拓扑。
* 改变 Block Space 六参数范围。
* 修改 M1 核心公式。
* 修改 M2 事件动力学。
* 新增 Jitter、Power、Static Phase Error 模型。
* 实现复杂新型 BO 或强化学习框架。
* 重新开发 Stage 4.1。
* 为实验结果好看而改变 SystemSpec、阈值或协议。
* 擅自将 Mapping Confidence 结论升级为完整系统认证。

### 推荐执行顺序

**P0：实验前准备**

冻结场景、预算、代码版本，复现原 Baseline。

**P1：可变 SystemSpec**

最小化实现研究场景输入，使 S0/S1/S2 能经统一链路运行。

**P2：端到端对照**

运行 Analytical / Random / Real LLM 策略，逐项执行 M1 和 M2，保存完整数据。

**P3：边界与失败实验**

完成 S3、S4，检验边界误差、不可行性判断和反馈传播。

**P4：结果审计**

进行回归，汇总三个研究问题的证据与局限。

不要在未完成 P0/P1 时先开发复杂 Agent 功能。

### 最终必须明确回答

1. 当前系统是否真的支持不同 BW/PM SystemSpec 的分配？
2. 是否能生成不同的 Joint BlockSpec，而非始终重放同一候选？
3. 不同候选在 M2 中表现如何？
4. M1 的物理预测是否具有实际筛选价值？
5. LLM 是否表现出区别于确定性 Solver 的决策行为？
6. 当前 M2 能验证到什么等级？
7. 下一阶段应该优先改进三个研究问题中的哪一个，理由是什么？

如果结果表明当前简单 CPPLL 主要依靠解析物理分配器即可完成任务，也必须如实报告。

**不要求证明 LLM 优于确定性 Solver。**

如果所有策略都只能获得 M2_PARTIAL_PASS，也必须真实报告，而不是降低验证标准。

完成 Stage 5 后停止，不自行进入 Stage 5.1 或 Stage 6，等待技术 Leader 审读。
