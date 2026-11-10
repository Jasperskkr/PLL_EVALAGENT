# Stage 3A.1 — PLL Allocation Mainline Consolidation & Release Freeze

## 1. 你的角色与核心目标

你是资深 Python 软件架构师、PLL 系统建模专家、Agent 工作流工程师。

当前项目已经完成以下研发阶段：

* Stage 1：PLL Physics Mapping M1。
* Stage 1.5：Behavioral Block Space Model v1。
* Track A：Physics-guided Allocation、Sensitivity Optimization、LLM Agent。
* Track B：独立 Behavioral Verification、BW Measurement、Capture/Lock。
* Stage 3A：初步统一 Pipeline，已经实现真实的 Allocation → M1 → M2 → Structured Feedback 调用。

上一轮独立源码审核确认：

1. 统一 Pipeline 已经能够调用真实分配策略和行为验证器。
2. Track A 的算法仍位于 `pll_allocation/track_a/`。
3. `pll_allocation/allocation/` 仍然主要通过导入 Track A 实现功能。
4. 正式 M2 验证代码已经迁移至 `pll_allocation/verification/`，但部分测试仍依赖历史 `track_b/`。
5. 原 `runner.py` 与新 `pipeline.py` 并存。
6. Stage 3A 集成代码尚未形成清晰、完整的正式 Git 版本。
7. 真实 LLM Agent 已支持首次分配，但真实 LLM 根据 M2 反馈自主修复尚未实现。
8. PM 与严格频率精度的 M2 验证仍为 UNKNOWN。

**本次任务唯一目标：将现有功能整理为一个结构清晰、接口统一、测试完整、可复现、可以长期迭代的 PLL Spec Allocation 主项目。**

本次不开发新的 PLL 模型、Agent 算法或验证方法。

---

## 2. 必须遵守的核心原则

### 2.1 不改变现有研究结果

以下内容必须冻结：

* SystemSpec。
* Behavioral Block Space Model v1。
* 六个可分配参数及其范围。
* Stage 1 M1 物理公式。
* Track A 解析反解、优化算法与既有决策策略。
* Track B 事件仿真物理方程。
* Track B Measurement Protocol 1.1。
* 既有正式测试案例与历史实验结果。

任何代码迁移都必须保持原来的数学计算与行为语义。

不得通过改变模型、参数、测试阈值或验证协议制造新的 PASS。

### 2.2 优先迁移，不要重写

优先采用：

1. 原代码迁移。
2. 更新 Import 路径。
3. 必要的接口适配。
4. 向后兼容。
5. 回归验证。

不为了目录美观重写已经验证的数值算法。

### 2.3 保护历史证据

Track A、Track B 中的大规模历史实验数据具有研究价值。

**禁止直接删除整个 `track_a/`、`track_b/`、历史 `outputs/` 或嵌套 `.git`。**

必须先确认所有正式运行依赖已被迁移或隔离，再提出历史目录归档方案。

原始实验数据可以继续存储在现有位置，不要求全部迁入正式项目。

---

## 3. Task A — 审查当前真实项目结构

开始修改之前，首先检查：

* `git status`
* 当前 Git 分支与提交。
* 未提交及未跟踪文件。
* Track B 的独立 Git 仓库。
* 正式 Pipeline 的所有 Import 依赖。
* Stage 3A 的测试和运行入口。
* 现有配置的引用关系。
* 原生 C++ / DLL 后端构建及加载方式。

生成一份简明的结构审计：

| 模块 | 当前路径 | 最终路径 | 是否迁移 | 理由 |
| -- | ---- | ---- | ---- | -- |

特别识别共享父目录中可能存在的并行外部修改。

不得使用 `git reset --hard`、`git clean -fd` 或其他可能丢失历史成果的清理操作。

对未提交的重要代码先建立可复核的备份或 Git 保护提交，再开展迁移。

---

## 4. Task B — 真正完成 Track A 的代码收敛

当前：

`pll_allocation/allocation/`

仍然依赖：

`pll_allocation/track_a/`

本次必须将正式算法实现迁移到 `allocation/`。

建议目标职责：

```text
pll_allocation/
├── block_space/
├── physics_mapping/
├── allocation/
│   ├── inverse.py
│   ├── optimizer.py
│   ├── agent.py
│   ├── feedback.py
│   ├── contracts.py
│   └── ...
├── verification/
│   ├── simulator.py
│   ├── measurement.py
│   ├── verify.py
│   └── ...
├── pipeline.py
└── ...
```

以上是建议职责，不强制采用完全相同的文件名。

必须实现：

1. 解析反解、敏感度优化与 Agent 的正式实现归属于 `allocation/`。
2. 正式 Pipeline 不再通过 `track_a/` 导入核心算法。
3. `track_a/` 不再作为正式生产代码的必要依赖。
4. 原 Agent 工具调用、提示词、模型配置和决策日志保持兼容。
5. 原有基线策略的输出结果保持一致。

可以保留旧路径的轻量兼容适配层，避免破坏历史脚本。

但适配方向必须是：

`legacy track_a → allocation`

不能是：

`allocation → legacy track_a`

如果存在无法安全迁移的模块，必须明确报告，而不能以空包装模块冒充迁移完成。

---

## 5. Task C — 整理 Track B 与正式 Verification

目前正式验证代码已部分迁入：

`pll_allocation/verification/`

本次重点是确认其已经成为唯一正式执行入口。

要求：

1. 正式 Pipeline 不依赖 `track_b/` 历史研发目录。
2. Verification 能独立接收正式 `AllocationProposal`。
3. Verification 能真实执行事件级仿真和指标测量。
4. 不通过导入 Track A 的优化代码实现任何测量。
5. 继续输出 `BehavioralVerificationResult`。
6. 保留 PASS / FAIL / UNKNOWN 的原始语义。
7. PM、UGF、严格频率精度继续按现有证据返回 UNKNOWN。

对于历史 Track B 测试：

* 将正式回归所必需的小型数据或参考结果迁入统一测试夹具。
* 大规模波形、频响扫描和旧报告继续保留为历史实验数据。
* 不让正式测试套件必须依赖整个历史 Track B 文件夹。

检查 Windows 原生 DLL 的编译、路径、加载和版本记录。

如果无法跨平台运行原生后端，必须明确报告平台要求，不得伪称已完成跨平台验证。

---

## 6. Task D — 统一正式 Pipeline 与 CLI

最终项目应提供一个明确的正式执行入口：

```powershell
python -m pll_allocation pipeline --strategy analytical --out experiments/run_01
```

并支持既有的：

* Analytical Allocation。
* Sensitivity Optimization。
* Random Baseline。
* LLM Agent Allocation。
* M1 Prediction。
* M2 Behavioral Verification。
* Structured Feedback。
* 现有确定性 Feedback Repair。

不要求本阶段新增真实 LLM 自动反馈修复能力。

保留原有 v1 Runner 的兼容性，但在文档中明确：

* 哪个是当前正式研究入口。
* 哪个是历史 Legacy 入口。
* 新实验应该使用什么命令。

不得存在两套具有不同默认 SystemSpec、Block Space 或模型定义的正式入口。

Pipeline 必须清晰区分：

* `FIRST_SHOT`
* `FEEDBACK_REPAIR`
* `M1_VALIDATED`
* `M2_PARTIAL_PASS`
* `M2_FAIL`
* `M2_UNKNOWN`

不能把部分指标 PASS 汇总成完整 SystemSpec PASS。

---

## 7. Task E — 统一配置与实验数据管理

正式系统中必须明确配置的单一权威来源。

包括：

* SystemSpec。
* Block Space Model。
* Physics Model。
* Behavioral Verification Protocol。
* Agent / LLM Configuration。

历史配置可以保留，但不能在正式执行中被静默混用。

每次实验必须保存：

1. SystemSpec 和 Block Space 的版本及 Hash。
2. 分配策略。
3. LLM 模型和配置元数据（不能保存 API Key）。
4. Agent 工具调用与决策过程。
5. First-shot BlockSpec。
6. M1 预测性能。
7. M2 实测性能。
8. M1/M2 误差。
9. Verification Feedback。
10. 仿真及搜索成本。
11. 失败原因和最终状态。

统一实验输出目录规范，避免正式实验继续散落在 Track A/B 历史目录。

历史实验不需要重新生成，也不允许覆盖。

---

## 8. Task F — 独立回归与正式验收

这是最重要的任务之一。

完成迁移后，必须重新运行真实代码，不能只依赖历史报告。

### F1. Python 回归

运行已有全部可运行测试，包括：

* Stage 1 / Stage 1.5。
* Track A。
* Track B。
* Stage 3A。
* 本次新增迁移测试。

记录实际执行数量、PASS / FAIL / SKIP。

### F2. M1 数值不变性

至少对比：

* Nominal。
* Analytical。
* Sensitivity Optimization。
* Random。

要求相同输入产生相同候选参数或在明确数值容差内相等的结果，BW、PM、UGF、Vctrl 与迁移前一致。

### F3. M2 行为结果不变性

在支持原生后端的 Windows 环境下，至少执行：

* Nominal 行为验证。
* 解析分配的行为验证。
* 优化分配的行为验证。
* 一组明确 BW FAIL 的行为验证。

与 Stage 3A 正式记录对比。

不能为了让结果一致而改变测量协议。

### F4. Agent 调用链

确认：

* 真实 Agent 的模型接口仍可使用。
* 工具调用仍能触发真正的分配器。
* LLM API 不可用时返回明确错误，不伪造响应。
* Agent 调用记录不泄露 API Key。
* 真实 LLM 修复尚未实现的状态被明确保留。

如果没有可用 LLM API，允许完成 Mock / Transport 测试，但不得声称本次运行了真实 LLM。

### F5. 代码依赖审计

必须自动检查：

* `pipeline.py` 不导入旧 `track_a/` 算法。
* 正式 `allocation/` 不依赖旧 Track A。
* 正式 `verification/` 不依赖旧 Track B。
* 正式代码不使用历史输出文件作为计算真值。
* 不存在两套不一致的正式 Block Space 定义。

---

## 9. Task G — Git 版本冻结及历史归档建议

完成测试后，建立一个清晰的主线集成版本。

要求：

1. 保留当前工作区重要未提交修改。
2. 只提交经过审计的授权代码、配置、测试和文档。
3. 不提交大规模历史仿真轨迹。
4. 不提交 API Key、Token 或本地密钥文件。
5. 不意外提交或修改 Track B 嵌套 Git 的内部数据。
6. 生成正式 Commit ID 与清晰的变更清单。

如果安全提交受到共享工作区或 Git 状态阻碍，应停止相关危险操作，报告具体阻碍，不能强行重置或清理。

旧 Track A/B 目录暂时可以保留。

但必须生成清单：

* 可以直接归档的内容。
* 必须继续保留的历史证据。
* 已被正式模块替代的代码。
* 尚不能删除的目录及原因。

**本阶段不要求物理删除历史 Track A/B。**

---

## 10. 必须交付的结果

### Deliverable 1 — 正式主线代码

完成 `allocation/`、`verification/` 与 Pipeline 的结构收敛。

### Deliverable 2 — `MAINLINE_ARCHITECTURE.md`

简明说明：

* 最终项目目录结构。
* 各模块唯一职责。
* 数据在模块间如何流动。
* 正式执行入口。
* Legacy 模块和历史目录的处理方式。

### Deliverable 3 — `INTEGRATION_VALIDATION.md`

记录实际运行的测试、候选、M1/M2 对照、调用路径与所有失败。

### Deliverable 4 — `RELEASE_MANIFEST.json`

包括：

* Git Commit。
* 关键源码 Hash。
* SystemSpec / Block Space / Protocol Hash。
* 依赖和运行环境。
* 正式配置与入口。
* 测试结果。
* 已知未实现功能。

### Deliverable 5 — `ARCHIVE_PLAN.md`

明确旧 Track A/B 哪些内容应保留、哪些可以在未来安全移除。

### Deliverable 6 — 轻量源码审查包

由于整个 PLL 项目包含大型 Track B 波形数据，不适合直接压缩，请自动生成：

`stage3a1_review_bundle.zip`

仅包含：

* 正式 `allocation/` 源码。
* 正式 `verification/` 源码。
* `pipeline.py` 与相关合同。
* 必要的 `physics_mapping/`、`block_space/` 接口及配置。
* 关键测试源码。
* 版本清单。
* 最终报告。
* 少量具有代表性的实验 JSON/CSV。
* 脱敏的 Agent Trace。

不得包含：

* 大规模仿真波形。
* 历史 Track B 全量输出。
* 原生构建缓存。
* 虚拟环境。
* API Key、Token 或其他凭据。

审查包内的文件必须与最终冻结版本保持一致，并提供文件 SHA256 清单。

---

## 11. 最终验收标准

请用以下项目判断是否真正完成。

* [ ] 正式 Pipeline 可以完整运行。
* [ ] `allocation/` 真正拥有分配算法，不再依赖 `track_a/`。
* [ ] `verification/` 真正拥有行为验证实现，不再依赖 `track_b/`。
* [ ] SystemSpec、Block Space 和模型配置具有唯一正式来源。
* [ ] 原 M1 数值结果保持一致。
* [ ] M2 行为验证结果保持一致。
* [ ] 原有测试全部运行并报告真实结果。
* [ ] Agent 工具调用和分配接口保持可用。
* [ ] 已知功能缺口没有被伪装成已实现。
* [ ] 正式 Git 版本已冻结，或明确记录安全冻结的阻碍。
* [ ] 已生成可供外部审查的轻量源码包。

如果部分内容受环境限制无法验证，必须标记 NOT_VERIFIED，并说明原因。

不能为了得到全部勾选而伪造执行或降低原有验收要求。

---

## 12. 最终汇报格式

请只回答以下六个问题：

**WHAT：** 本次真正迁移并整理了哪些模块？

**HOW：** 新主线如何执行 SystemSpec → Allocation → M1 → M2 → Feedback？

**EQUIVALENCE：** 迁移前后的参数、物理计算和行为验证结果是否一致？

**STRUCTURE：** 正式项目结构是否真正收敛？是否还依赖 Track A/B？

**RELEASE：** Git 版本、测试及可复现审计是否完成？

**NEXT：** 主线冻结后，三个研究核心问题分别还有什么缺口？

完成后停止。

不要自动开展新的 PLL 建模、BO、LLM 搜索策略或行为验证方法研究。等待技术 Leader 审查。
