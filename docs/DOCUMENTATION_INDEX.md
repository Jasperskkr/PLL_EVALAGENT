# Documentation Index

本文档说明各 Markdown 文件的职责、状态和阅读顺序。旧文档保留在仓库中，作为设计决策和历史输入的可追溯记录；当前实现状态以 README、PROJECT_PLAN、V1.0_BASELINE 和代码/测试为准。

## 推荐阅读顺序

1. [`../README.md`](../README.md)：项目入口、当前实现和边界。
2. [`../PROJECT_PLAN.md`](../PROJECT_PLAN.md)：当前状态、后续阶段和验收标准。
3. [`../doc/V1.0_BASELINE.md`](../doc/V1.0_BASELINE.md)：V1.0 固定基线和复现证据。
4. [`PHASE1_SCHEMA_GRAPH.md`](PHASE1_SCHEMA_GRAPH.md)：当前 Phase 1 的 BlockMetaSchema、TypedGraph v2、semantic roles 和 validator 规则。
5. [`../v1/V1_DEMO_README.md`](../v1/V1_DEMO_README.md)：V1 runner 的逐阶段说明。
6. [`../doc/v1_framework_architecture_reviewed.md`](../doc/v1_framework_architecture_reviewed.md)：V1 语义边界、allocation/validation path 和可信性约束。
7. [`../doc/pll_behavioral_model_prototype_report.md`](../doc/pll_behavioral_model_prototype_report.md)：行为级 PLL/VCO 模型和 Python/MATLAB 对照。
8. [`../doc/project_understanding_and_literature_review.md`](../doc/project_understanding_and_literature_review.md)：项目理解、可行性、文献和实验设计评审。
9. [`../doc/initial_framework_architecture.md`](../doc/initial_framework_architecture.md)：面向 V2/V3 的长期架构蓝图。
10. [`../doc/project_prompt.md`](../doc/project_prompt.md)：原始项目 charter，保留问题定义和早期阶段约束。

## 当前有效性层级

```text
README / PROJECT_PLAN
    当前项目入口和推进规则

doc/V1.0_BASELINE / results/v1_vco_mapping_01/summary.md
    已运行的确定性结果和 claim boundary

doc/v1_framework_architecture_reviewed.md
    V1 设计决策和语义边界

doc/initial_framework_architecture.md
    长期蓝图，不代表所有模块已实现

doc/project_prompt.md / doc/project_understanding_and_literature_review.md
    原始 charter 和历史 review；需要结合当前实现状态阅读
```

## 文件职责

| 文件 | 状态 | 作用 |
|---|---|---|
| `README.md` | 当前入口 | 快速理解项目、运行 V1、查看边界 |
| `PROJECT_PLAN.md` | 当前计划 | 阶段路线、验收和治理规则 |
| `doc/V1.0_BASELINE.md` | 已冻结 | Git baseline、复现命令和 V1 claim |
| `docs/PHASE1_SCHEMA_GRAPH.md` | Phase 1 semantic freeze 已实现 | BlockMetaSchema v1、Graph v2、semantic-role validator 规则 |
| `v1/V1_DEMO_README.md` | V1 运行说明 | runner 阶段和 artifact 清单 |
| `doc/project_prompt.md` | 历史 charter | 最初问题定义、Problem 1/2、V1/V2/V3 目标 |
| `doc/project_understanding_and_literature_review.md` | 历史 review | 可行性、相关工作、风险和 pilot 设计 |
| `doc/initial_framework_architecture.md` | 长期蓝图 | 平台化架构、backend、orchestrator 和未来扩展 |
| `doc/v1_framework_architecture_reviewed.md` | V1 设计记录 | Contract/Oracle/Requirement/Instance 等语义边界 |
| `doc/pll_behavioral_model_prototype_report.md` | 模型报告 | Python/MATLAB 行为模型、方程和已知限制 |
| `results/v1_vco_mapping_01/summary.md` | 运行产物 | 单次 benchmark 的 compact evidence |
| `results/v1_spec_matrix/SPEC_MATRIX_REPORT.md` | 运行产物 | 多组 SystemSpec 正向分配、PN 边界双向检查、candidate 回代与负向控制 |

## 阅读时应特别注意

- “已设计”不等于“已实现”；长期蓝图中的模块不能自动视为当前能力。
- “sensitivity/prove evidence”不等于“正式多维规格分配”；V1 正式 allocation 仍只有 PN@1MHz。
- `VCO Requirement`、`Candidate`、`Realized VCO Instance` 和 `Evaluation/Evidence` 是不同对象；它们不是 Block Graph layer。
- V1 的 PASS 是 synthetic behavioral mapping proof，不是 transistor-level signoff。
