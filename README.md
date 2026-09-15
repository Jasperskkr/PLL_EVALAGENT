# PLL_EVALAGENT

面向 PLL 的行为级 **SystemSpec → BlockSpec** 分配与验证项目。

项目的核心问题不是“给定一个 VCO 参数后能不能模拟 PLL”，而是：

> 给定不可修改的 PLL SystemSpec，如何构造可测试的行为级 Block abstraction，在其中搜索可行的 BlockSpec，并用确定性仿真证明这组规格确实能满足系统指标。

当前仓库先用固定 Integer-N CPPLL 和 VCO 完成 V1.0 最小闭环。长期目标是扩展到多个 PLL Block，再研究由 Agent 协助构建 behavioral design space 和执行规格分配。

## 当前状态

当前 Git 基线为 [`v1.0-baseline`](https://github.com/Jasperskkr/PLL_EVALAGENT/releases/tag/v1.0-baseline)。

V1.0 已经真实运行并验证：

```text
SystemSpec
  → deterministic SystemTB
  → residual / finite-difference sensitivity
  → required VCO PN boundary search
  → candidate VCO
  → context-aware VCO BlockTB
  → realized-instance SystemTB validation
```

当前正式分配维度是一维的：

```text
VCO PN@1MHz  ↔  PLL integrated jitter
```

`Kvco`、VCO tuning curve、Vctrl envelope、power 和 lock-time sensitivity 已作为 characterization/prove evidence 输出，但还没有进入正式的多参数联合 allocation。

## V1.0 已验证的结果

固定 benchmark：[`v1/cases/vco_mapping_01.json`](v1/cases/vco_mapping_01.json)

| 项目 | 结果 |
|---|---:|
| System jitter limit | 80 fs |
| Initial jitter | 83.367 fs，FAIL |
| Required PN@1MHz boundary | -116.358121 dBc/Hz |
| Recommended PN（含 1.5 dB margin） | -117.858121 dBc/Hz |
| Selected candidate | `candidate_low_noise` |
| Final jitter | 41.783 fs |
| Final lock time | 36.520 us |
| Final frequency | 5.000 GHz |
| Final SystemTB | PASS |

V1.0 baseline 的测试套件为 10/10 通过；Phase 1 新增 schema、graph、unit 和 Agent proposal 边界测试后为 13/13 通过。V1 runner 的核心数值输出保持 deterministic replay。

## 快速运行

建议使用 Python 3.10+。从仓库根目录运行：

```powershell
python -m unittest discover -s tests -v
python run_v1_prove.py --case v1\cases\vco_mapping_01.json
python run_v1_spec_matrix.py
```

结果写入：

```text
results/v1_vco_mapping_01/
results/v1_spec_matrix/
```

最重要的输出包括：

```text
summary.md                         # before/after 和最终判定
sensitivity.json                   # 确定性 sweep 与局部导数
required_vco_spec_boundary.json   # PN boundary search 证据
required_vco_spec.json             # 无 margin 的 required spec
recommended_vco_spec.json         # 加 margin 后的推荐 spec
block_feasibility.json             # BlockTB + SystemTB candidate 结果
final_system_evaluation.json      # 最终 SystemTB 结果
vco_pll_graph.json                 # 当前图结构和 sensitivity evidence
vco_pll_graph_v2.json              # Phase 1 四层 typed graph artifact
vco_block_meta_v1.json             # VCO 的四类 BlockMetaSchema 实例
trajectory.jsonl                   # 可回放执行轨迹
```

`run_v1_spec_matrix.py` 另外执行 6 组完整正向 case 和 2 组负向控制 case，生成 SystemSpec → VCO PN 分配表、PN 边界两侧 PASS/FAIL 表、candidate 回代 BlockTB/SystemTB 表和一维分配拒绝表。

`initial_system_raw.json` 和 `system_raw_*.json` 等逐周期 raw trace 很大，按 `.gitignore` 忽略；它们由 runner 重新生成，摘要和关键证据仍被跟踪。

## 当前实现如何分工

```text
v1/model/pll_behavioral.py
    averaged reference-cycle Integer-N CPPLL + nonlinear/context-aware VCO

v1/pipeline.py
    SystemTB、residual、characterization、sweep、sensitivity、PN boundary、BlockTB

run_v1_prove.py
    V1 runner、candidate selection、artifact/report/trajectory 生成

v1/specs.py
    SystemSpec、VCORequirement、CandidateDefinition

v1/contract.py
    VCO contract v0/v1、独立 observation holdout refinement evidence

v1/schema/
    canonical envelope 和基础 payload validators

v1/graph/
    typed graph model、V1 compatibility graph 和 Phase 1 multilayer graph compiler

v1/allocation/
    SpecVector 和现有 SystemTB 的 forward-compatible adapter

v1/agent_actions.py
    Agent action 白名单与治理约束
```

核心治理规则是：

```text
Agent proposes; deterministic tools validate.
```

当前代码没有把 LLM 作为 V1 数值内核，也没有让 Agent 修改 SystemSpec、猜测 sensitivity 或宣布 PASS。V1 使用 deterministic baseline 证明流程，未来 Agent 可以替换“候选关系/搜索动作提出器”，但不能替换 SystemTB、BlockTB 和独立 evaluator。

## 图结构和 Schema 的定位

Schema 是固定的语法和规则，规定对象、字段、单位、上下文、证据和合法连接；Graph 是某一个具体 PLL 实例化后的关系地图。当前图已经记录 architecture、behavioral dependency、noise transfer、system influence 和 sensitivity evidence。

Graph v2 仍是“记录/追溯层”，不是完全由图遍历驱动的执行引擎；但 Phase 1 已经在不改变 V1 数值内核的前提下，把以下关键对象和执行证据显式接入同一张 typed graph：

```text
VCORequirement → Candidate → BlockTBResult → SystemTBResult
VCO Noise TF → Noise Integration → System Jitter
PLL Dynamics → UGB / PM / Lock Time
CapabilityRegion、MeasurementContract、ValidityDomain、Uncertainty
```

后续 Agent 的工作方式是：搜索或提出候选连接和 Block contract → schema/type/unit 检查 → deterministic BlockTB/Sensitivity/SystemTB 验证 → 通过后才把关系写入 validated graph。

## 重要边界

V1 是 behavioral mapping proof，不是 transistor-level PLL signoff。当前模型：

- 使用 averaged reference-cycle phase-domain CPPLL；不采样 GHz 级 RF waveform；
- VCO 支持非线性 tuning、Kvco、context-dependent phase noise 和 power；
- 当前 jitter 只包含 VCO phase-noise contribution；CP、divider 和连续时间 loop-filter noise 尚未作为独立 signoff-quality source 建模；
- `cp_current`、R/C 参数已保留接口，但当前 effective loop gains 仍是简化模型；
- Python 是 V1 canonical runner，MATLAB 用于方程级交叉验证；
- Synthetic behavioral candidate 不能替代真实 PSS/PNOISE、SpectreRF 或 silicon measurement。

## 文档导航

| 文档 | 用途 |
|---|---|
| [`PROJECT_PLAN.md`](PROJECT_PLAN.md) | 当前状态、阶段目标、验收标准和后续推进路线 |
| [`V1.0_BASELINE.md`](V1.0_BASELINE.md) | V1.0 基线、复现命令、结果和 claim boundary |
| [`v1/V1_DEMO_README.md`](v1/V1_DEMO_README.md) | V1 runner 的详细步骤和产物 |
| [`docs/DOCUMENTATION_INDEX.md`](docs/DOCUMENTATION_INDEX.md) | 全部 prompt、review、architecture、model 文档的职责索引 |
| [`project_understanding_and_literature_review.md`](project_understanding_and_literature_review.md) | 项目理解、可行性和文献评审 |
| [`v1_framework_architecture_reviewed.md`](v1_framework_architecture_reviewed.md) | V1 语义边界和最小可信执行路径 |
| [`initial_framework_architecture.md`](initial_framework_architecture.md) | 面向 V2/V3 的长期架构蓝图 |
| [`pll_behavioral_model_prototype_report.md`](pll_behavioral_model_prototype_report.md) | Python/MATLAB 行为模型说明和原型结果 |
| [`project_prompt.md`](project_prompt.md) | 原始项目 charter 和问题定义，保留作历史输入 |

## 下一步

近期优先级不是重写 V1，而是在已完成的 Phase 1 schema/graph 上继续扩展：

1. 实现 `PN × Kvco` 的二维 capability/feasible-region 搜索，保留 V1 一维结果作为 regression control；
2. 将 sampled feasible points、constraint residual 和 Pareto candidate 纳入正式 allocation artifact；
3. 再引入 CP、Loop Filter、Divider 的 cross-block context；
4. 让 Agent 负责 contract/connection/search proposal，并由 deterministic tools 验证和升级 graph 状态。

详细路线见 [`PROJECT_PLAN.md`](PROJECT_PLAN.md)。
