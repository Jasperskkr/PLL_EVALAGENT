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
  → PN anchor boundary search
  → frozen-context VCO measurement
  → measured VCO requirement
  → candidate VCO
  → context-aware VCO BlockTB
  → realized-instance SystemTB validation
```

当前正式 deterministic case 仍是一维的，但命名已经拆开：

```text
target_system_metric:   integrated_jitter_s
search_knob:            pn_anchor_1mhz_dbc_hz
allocated_block_metric: worst_phase_noise_1mhz_dbc_hz
```

`pn_anchor_1mhz_dbc_hz` 是 synthetic VCO model 的 internal knob，不是 Block Requirement。VCO requirement 由 frozen `VCOBlockContext.v1` 下测得的 `worst_phase_noise_1mhz_dbc_hz` 推导。

`Kvco`、VCO tuning curve、Vctrl envelope、power 和 lock-time sensitivity 已作为 characterization/prove evidence 输出，但还没有进入正式的多参数联合 allocation。

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

V1.0 baseline 的原始测试为 10/10 通过；当前加入 semantic-role graph、schema、unit、semantic-freeze validator 和多类型标量映射测试后，核心 pytest 回归为 23/23 通过。V1 runner 的 SystemTB、BlockTB、scalar bisection 和 candidate replay 仍保持 deterministic。

## 快速运行

建议使用 Python 3.10+。从仓库根目录运行：

```powershell
python -m unittest discover -s tests -v
python run_v1_prove.py --case v1\cases\vco_mapping_01.json
python run_v1_spec_matrix.py
python run_v1_mapping_suite.py
```

结果写入：

```text
results/v1_vco_mapping_01/
results/v1_spec_matrix/
results/v1_scalar_mapping_suite/
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
vco_pll_graph_v2.json              # architecture/behavior/influence/evidence typed graph artifact
vco_block_meta_v1.json             # VCO 的四部分 BlockMetaSchema 实例
trajectory.jsonl                   # 可回放执行轨迹
```

`run_v1_spec_matrix.py` 另外执行 6 组完整正向 case 和 2 组负向控制 case，生成 SystemSpec → VCO PN 分配表、PN 边界两侧 PASS/FAIL 表、candidate 回代 BlockTB/SystemTB 表和一维分配拒绝表。

`run_v1_mapping_suite.py` 在不改变 PN baseline 的情况下，复用同一
SystemTB/BlockTB 执行四类一维映射：jitter→PN、lock time→VCO `k1`、
power→nominal power、frequency→`f0`/tuning coverage。每个 case 都要求初始
目标失败、边界两侧可辨识、candidate 通过冻结 context 下的 BlockTB，并由独立
SystemTB 回代。宽范围 probe 同时检查该关系是单边界还是仅在局部 validity
bracket 内成立。

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
    typed graph model、V1 compatibility graph 和 semantic-role graph compiler/validators

v1/allocation/
    DesignVector candidate-knob compiler 和 measured-Behavior evaluator

v1/agent_actions.py
    Agent action 白名单与治理约束
```

核心治理规则是：

```text
Workflow artifacts are objects, not Block Graph layers.
Deterministic tools validate every accepted numeric claim.
```

当前代码没有把 LLM 作为 V1 数值内核，也没有让 Agent 修改 SystemSpec、猜测 sensitivity 或宣布 PASS。V1 使用 deterministic baseline 证明流程；未来 Agent 只能作为候选动作提出器，不能替换 SystemTB、BlockTB 和独立 evaluator。

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
- Python 是 V1 canonical runner，MATLAB 用于方程级交叉验证；
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

近期优先级不是重写 V1，而是在已完成的 semantic-role schema/graph 上继续扩展。以下都是后续阶段，不属于本次 semantic freeze：

1. 实现 `PN × Kvco` 的二维 feasible-region 搜索，保留 V1 一维结果作为 regression control；
2. 将 sampled feasible points、constraint residual 和 Pareto candidate 纳入正式 allocation artifact；
3. 再引入 CP、Loop Filter、Divider 的 cross-block context；
4. 让 Agent 负责 contract/connection/search proposal，并由 deterministic tools 验证和升级 graph 状态。

详细路线见 [`PROJECT_PLAN.md`](PROJECT_PLAN.md)。
