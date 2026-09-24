# PLL_EVALAGENT

面向 PLL 的行为级 **SystemSpec → BlockSpec** 分配与验证项目。

项目的核心问题不是“给定一个 VCO 参数后能不能模拟 PLL”，而是：

> 给定不可修改的 PLL SystemSpec，如何构造可测试的行为级 Block abstraction，在其中搜索可行的 BlockSpec，并用确定性仿真证明这组规格确实能满足系统指标。

当前仓库先用固定 Integer-N CPPLL 和 VCO 完成 V1.0 最小闭环，并保留了已落地的 V1.5 `PN × Kvco` 多参数分配代码。长期目标是扩展到多个 PLL Block，再研究由 Agent 协助构建 behavioral design space 和执行规格分配。

## 当前状态

当前 Git 基线为 [`v1.0-baseline`](https://github.com/Jasperskkr/PLL_EVALAGENT/releases/tag/v1.0-baseline)。

V1.0 已经真实运行并验证，主干现在明确拆成两个方向：

```text
正向：SystemSpec → BlockSpec allocation
  → deterministic boundary search
  → frozen-context block measurement
  → allocated VCO requirement

反向：BlockSpec + realized instance → spec verification
  → BlockTB
  → same-instance SystemTB
  → context coverage / final verdict
```

V1.0 的正式 deterministic case 仍是一维；V1.5 已有独立的二维 PN anchor × k1 / measured Kvco 行为级 runner。两条路径的命名已经拆开：

```text
target_system_metric:   integrated_jitter_s
search_knob:            pn_anchor_1mhz_dbc_hz
allocated_block_metric: worst_phase_noise_1mhz_dbc_hz
```

`pn_anchor_1mhz_dbc_hz` 是 synthetic VCO model 的 internal knob，不是 Block Requirement。VCO requirement 由 frozen `VCOBlockContext.v1` 下测得的 `worst_phase_noise_1mhz_dbc_hz` 推导。

在 V1.0 主路径中，`Kvco`、VCO tuning curve、Vctrl envelope、power 和 lock-time sensitivity 仍主要作为 characterization/prove evidence 输出。

V1.5 已部分实现 `PN × Kvco` 二维 design space、逐点 BlockTB/SystemTB 评估、可行域和候选选择；它是更高维的 allocation/search runner，尚未成为通用多 Block allocation service。

## V1.0 已验证的结果

固定 benchmark：[`v1/cases/vco_mapping_01.json`](v1/cases/vco_mapping_01.json)

| 项目 | 结果 |
|---|---:|
| System jitter limit | 80 fs |
| Initial jitter | 83.367 fs，FAIL |
| PN anchor boundary (`pn_anchor_1mhz_dbc_hz`) | -116.358121 dBc/Hz |
| Worst measured PN at boundary | -113.511151 dBc/Hz |
| Required VCO PN requirement | -113.511151 dBc/Hz |
| Recommended VCO PN requirement（含 1.5 dB margin） | -115.011151 dBc/Hz |
| Selected candidate | `candidate_low_noise` |
| Final jitter | 41.783 fs |
| Final lock time | 36.520 us |
| Final frequency | 5.000 GHz |
| Final SystemTB | PASS |

V1.0 和 V1.5 的历史回归已完成并用于冻结当前实现。仓库保留已有的
`results/v1_vco_mapping_01` 历史基线；新的本地运行产物默认由 Git 忽略，
可重复的数值与 artifact 摘要断言保存在 `tests/`。当前主干以模块化
round-trip、V1.0/V1.5 确定性 runner 和 `v1/` 包中的实现为准。

## 快速运行

项目统一使用 Python 3.13。首次使用时，从仓库根目录创建并安装项目环境：

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
```

后续直接使用项目环境运行，避免调用系统中其他版本的 Python：

```powershell
.\.venv\Scripts\python.exe run_jitter_pn_roundtrip_demo.py
.\.venv\Scripts\python.exe run_v1_prove.py --case v1\cases\vco_mapping_01.json
.\.venv\Scripts\python.exe run_v1_5_allocate.py --case v1\cases\vco_multidim_01.json
.\.venv\Scripts\python.exe -m pytest -q
```

运行结果默认写入被 Git 忽略的 `results/` 目录；也可以通过 `--output-dir`
指定目录。除已有 V1.0 历史基线外，仓库不新增 raw trace 或临时运行目录。

V1.0 runner 的主要输出包括：

```text
summary.md                         # before/after 和最终判定
sensitivity.json                   # 确定性 sweep 与局部导数
required_vco_spec_boundary.json   # PN boundary search 证据
required_vco_spec.json             # 无 margin 的 required spec
recommended_vco_spec.json         # 加 margin 后的推荐 spec
spec_allocation_report.json       # 正向 SystemSpec -> BlockSpec allocation report
block_feasibility.json             # BlockTB + SystemTB candidate 结果
final_system_evaluation.json      # 最终 SystemTB 结果
vco_pll_graph.json                 # 当前图结构和 sensitivity evidence
vco_pll_graph_v2.json              # architecture/behavior/influence/evidence typed graph artifact
vco_block_meta_v1.json             # VCO 的四部分 BlockMetaSchema 实例
trajectory.jsonl                   # 可回放执行轨迹
```

`initial_system_raw.json` 和 `system_raw_*.json` 等逐周期 raw trace 很大；它们和摘要、关键证据一样，都由 runner 在运行时重新生成。

这些输出都是运行时 evidence，不是源码的一部分。

## 当前实现如何分工

```text
v1/model/pll_behavioral.py
    averaged reference-cycle Integer-N CPPLL + nonlinear/context-aware VCO

v1/evaluation/
    纯数值测量：SystemTB、VCO characterization、sensitivity、scalar boundary search

v1/verification/
    BlockSpec 判定、约束解析、BlockTB/SystemTB 编排、context coverage

v1/allocation/
    正向分配、二维 design space、边界、区域、候选选择和 replay evidence

v1/backends/
    可替换测量/仿真适配器；包入口只公开 protocol，不隐式加载实现

v1/pipeline.py
    旧 API 的兼容 facade；不再承载业务逻辑，新代码不要在这里扩展

v1/io.py
    JSON/CSV、严格 evidence JSON 和统一 SHA-256

run_v1_prove.py
    V1.0 runner、candidate selection、artifact/report/trajectory 生成

run_v1_5_allocate.py
    部分 V1.5 的 PN × Kvco 设计空间、可行域、候选选择和 Graph audit

v1/specs.py
    SystemSpec、VCORequirement、CandidateDefinition

v1/contract.py
    VCO contract v0/v1、独立 observation holdout refinement evidence

v1/schema/
    canonical envelope 和基础 payload validators

v1/graph/
    typed graph model、V1 compatibility graph 和 semantic-role graph compiler/validators

v1/workflow/
    与 Block 无关的 spec-closure 编排；九个依赖注入阶段及当前 VCO adapters

v1/agent_actions.py
    Agent action 白名单与治理约束
```

SystemTB 的 `trajectory_envelope` 是仿真实际走过的轨迹；BlockTB 的
`characterization_window` 是声明并冻结的表征窗口。旧 artifact 中的 `context`
字段暂时保留为兼容别名，新代码应使用两个显式名称。

模型输出的 `effective_noise_shaping_bandwidth_hz` 是行为级 PN 噪声整形参数，
不是从闭环响应提取的物理环路带宽。历史字段 `loop_bandwidth_hz` 暂时保留为同值别名。

## 模块化 Spec Closure 主流程

`run_v1_prove.py` 保留为 V1.0 完整证明与兼容 runner；可扩展主入口是
`v1.workflow.run_spec_closure()`。它不直接导入 VCO 数值模型，所有 Block 专用行为都
通过模块插槽注入：

```text
SpecClosureRequest
  → BlockDefinitionProvider
  → BaselineEvaluator
  → ContextBuilder
  → AllocationModule
  → CandidateProvider
  → CandidateRealizer
  → AssignmentVerifier
  → CandidateSelector
  → EvidenceFinalizer
  → SpecClosureReport
```

各阶段的 protocol 定义在 `v1/workflow/protocols.py`，通用编排在
`v1/workflow/service.py`，当前 VCO 实现在 `v1/workflow/vco.py`。因此扩展时的修改边界是：

| 扩展目标 | 替换/新增模块 | 不需要修改 |
|---|---|---|
| `PN × Kvco × power` 多维分配 | `AllocationModule`、design-space provider/selector | workflow service |
| 新增 CP、LF、Divider Block | Block definition、realizer、verifier adapter | workflow service |
| 行为模型替换为 Spectre/SPICE | candidate realizer、verification backend | allocation/graph orchestration |
| Agent 构建 Block | `BlockDefinitionProvider` | deterministic schema validator |
| Agent 提议候选/搜索区间 | `CandidateProvider` / `AllocationModule` proposal adapter | BlockTB/SystemTB verdict |
| 新的排序/Pareto 策略 | `CandidateSelector` | evaluator/backend |

Agent 产出的 block definition 和 candidate 都只能以 `proposed` 身份进入；
`v1/schema/workflow.py` 先验证字段、单位、指标引用、design variable 和禁止权限，最终
PASS 只能由 deterministic verification 与 Graph audit 给出。

## 正向 allocation 与反向 verification 边界

这两个方向是两个独立的一等服务，不能混称为 verification：

```text
SystemSpec + allocation problem + base model/context
                ↓
      allocate_system_spec()
                ↓
       allocated BlockSpec
```

```text
SystemSpec + allocated BlockSpec + realized instance/context
                ↓
      verify_block_assignment()
                ↓
       BlockTB/SystemTB report
```

正向 allocation 的稳定边界：

```text
v1/api/allocation.py
    SpecAllocationRequest / SpecAllocationReport

v1/backends/protocol.py
    AllocationBackend

v1/backends/synthetic.py
    SyntheticVCOAllocationBackend（当前 V1.0 PN boundary allocator）

v1/allocation/service.py
    allocate_system_spec()
```

反向 verification 的稳定边界：

```text
v1/api/verification.py
    VerificationRequest / VerificationReport

v1/backends/
    backend protocol；当前 SyntheticVCOBackend，后续可替换 MATLAB、Spectre、SPICE 或 measurement backend

v1/verification/
    context coverage、BlockTB/SystemTB 编排和统一 verify_block_assignment()

v1/model/ + v1/pipeline.py
    当前 Python 行为模型和确定性数值内核

run_v1_prove.py / run_v1_5_allocate.py
    薄层 runner；负责 case、allocation、报告和 Graph artifact 投影

results/
    运行时 evidence，不属于源码树，默认被 Git 忽略
```

`run_v1_prove.py` 现在先写出 `spec_allocation_report.json`，再对每个
candidate 调用 verification；因此 candidate search 是 allocation 后的候选实现选择，
不是 allocation service 本身。V1.5 runner 继续负责二维 design-space allocation/search，
其中每个点的 BlockTB/SystemTB 复用同一个 verification service。

两条统一入口的输入/输出关系是：

```text
SpecAllocationRequest
  = SystemSpec + AllocationProblem + BaseInstance + OperatingContext + Backend
                         ↓
              allocate_system_spec()
                         ↓
SpecAllocationReport
  = AllocatedBlockSpec + BoundaryEvidence + Provenance

VerificationRequest
  = SystemSpec + BlockSpec + RealizedInstance + OperatingContext + Backend
                         ↓
              verify_block_assignment()
                         ↓
VerificationReport
  = BlockTB + validation-mode SystemTB + ContextCoverage + FailureReasons
```

V1.0 runner 先通过 allocation service 得到 BlockSpec，再通过 verification service
验证候选；V1.5 多参数 evaluator 负责设计空间 allocation/search，并复用 verification
执行每个点的 BlockTB/SystemTB。后续替换真实电路或真实搜索器时，优先新增 backend
adapter，不修改上层 request/report 和 verdict 规则。

## Jitter ↔ VCO PN round-trip demo

可以用下面的轻量 demo 检查“系统 jitter 分配到 VCO PN，再用 PN candidate 回代系统
jitter”的闭环：

```powershell
python run_jitter_pn_roundtrip_demo.py
```

它会依次执行两个方向：

```text
初始 SystemTB（jitter FAIL）
  → 正向 `allocate_system_spec()` 生成 VCO PN BlockSpec
  → candidate realization
  → 反向 `verify_block_assignment()` 执行 BlockTB + SystemTB
  → jitter PASS / round-trip PASS
```

这个 demo 已经通过完整的模块化主流程执行，而不是手工串接两个函数。输入是
`v1/cases/jitter_pn_roundtrip_01.json`，输出为：

```text
results/jitter_pn_roundtrip_demo/
  spec_closure_report.json       # 完整 workflow I/O
  allocation_report.json         # 正向 allocation 投影
  workflow_graph_v2.json         # allocation/verification 证据图
  workflow_graph_audit.json      # Schema + Graph 闭环审计
```

核心治理规则是：

```text
Workflow artifacts are objects, not Block Graph layers.
Deterministic tools validate every accepted numeric claim.
```

当前代码没有把 LLM 作为 V1/V1.5 数值内核，也没有让 Agent 修改 SystemSpec、猜测 sensitivity 或宣布 PASS。现阶段保留 deterministic baseline；未来 Agent 只能作为候选动作提出器，不能替换 SystemTB、BlockTB 和独立 evaluator。

## 图结构和 Schema 的定位

Schema 是固定的语法和规则，规定对象、字段、单位、上下文、证据和合法连接；Graph 是某一个具体 PLL 实例化后的关系地图。Block Graph 对外只使用四个 `semantic_role`：

```text
architecture  Block identity、physical/functional ports、signal/context connections
behavior      frequency_hz、phase_noise_1mhz_dbc_hz、kvco_hz_per_v、power_w
influence     source Behavior metric → target System metric 的机制和适用域
evidence      characterization、boundary search、BlockTB、SystemTB、audit/provenance
```

`SystemSpec`、`BlockRequirement`、`Candidate`、`RealizedInstance`、`DesignSpace`、`CapabilityRegion`、`Schema` 和 `Contract` 是 workflow objects/artifacts，不是 Block Graph layer。Graph v2 是记录/追溯 artifact，不是完全由图遍历驱动的执行引擎；它在不改变 V1 数值内核的前提下，把 requirement、candidate、measurement context、BlockTB/SystemTB 和 evidence 显式接入同一张 typed graph。

## 重要边界

V1 是 behavioral mapping proof，不是 transistor-level PLL signoff。当前模型：

- 使用 averaged reference-cycle phase-domain CPPLL；不采样 GHz 级 RF waveform；
- VCO 支持非线性 tuning、Kvco、context-dependent phase noise 和 power；
- 当前 jitter 只包含 VCO phase-noise contribution；CP、divider 和连续时间 loop-filter noise 尚未作为独立 signoff-quality source 建模；
- `cp_current`、R/C 参数已保留接口，但当前 effective loop gains 仍是简化模型；
- Python 是 V1 canonical runner，MATLAB 文件仅作为早期方程级交叉验证参考；
- Synthetic behavioral candidate 不能替代真实 PSS/PNOISE、SpectreRF 或 silicon measurement。

## 文档导航

| 文档 | 用途 |
|---|---|
| [`PROJECT_PLAN.md`](PROJECT_PLAN.md) | 当前状态、阶段目标、验收标准和后续推进路线 |
| [`doc/V1.0_BASELINE.md`](doc/V1.0_BASELINE.md) | V1.0 基线、复现命令、结果和 claim boundary |
| [`v1/V1_DEMO_README.md`](v1/V1_DEMO_README.md) | V1 runner 的详细步骤和产物 |
| [`docs/DOCUMENTATION_INDEX.md`](docs/DOCUMENTATION_INDEX.md) | 全部 prompt、review、architecture、model 文档的职责索引 |
| [`doc/project_understanding_and_literature_review.md`](doc/project_understanding_and_literature_review.md) | 项目理解、可行性和文献评审 |
| [`doc/v1_framework_architecture_reviewed.md`](doc/v1_framework_architecture_reviewed.md) | V1 语义边界和最小可信执行路径 |
| [`doc/initial_framework_architecture.md`](doc/initial_framework_architecture.md) | 面向 V2/V3 的长期架构蓝图 |
| [`doc/pll_behavioral_model_prototype_report.md`](doc/pll_behavioral_model_prototype_report.md) | Python/MATLAB 行为模型说明和原型结果 |
| [`doc/project_prompt.md`](doc/project_prompt.md) | 原始项目 charter 和问题定义，保留作历史输入 |

## 下一步

当前优先级是把已验证的 V1.5 数值能力逐步接入模块化 workflow。后续阶段包括：

1. 将现有 `PN × Kvco` design-space runner 封装为新的 `AllocationModule`，保留 V1 一维结果作为 regression control；
2. 将 sampled feasible points、constraint residual 和 Pareto candidate 统一投影到 `SpecClosureReport`；
3. 再引入 CP、Loop Filter、Divider 的 cross-block context；
4. 让 Agent 负责 contract/connection/search proposal，并由 deterministic tools 验证和升级 graph 状态。

详细路线见 [`PROJECT_PLAN.md`](PROJECT_PLAN.md)，新会话开发交接见
[`docs/V1.5_PROJECT_INTRODUCTION.md`](docs/V1.5_PROJECT_INTRODUCTION.md)，当前二维输入/输出和
正式 BlockSpec 见 [`docs/V1.5_CURRENT_INPUT_OUTPUT.md`](docs/V1.5_CURRENT_INPUT_OUTPUT.md)。
