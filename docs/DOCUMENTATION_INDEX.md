# Documentation Index

本文档说明各 Markdown 文件的职责、状态和阅读顺序。旧文档保留在仓库中，作为设计决策和历史输入的可追溯记录；当前实现状态以 README、PROJECT_PLAN 和代码为准。历史测试源码与运行产物已从主干清理，运行时 evidence 默认写入被忽略的 `results/` 目录。

## 推荐阅读顺序

1. [`../README.md`](../README.md)：项目入口、当前实现和边界。
2. [`MODULAR_WORKFLOW.md`](MODULAR_WORKFLOW.md)：当前已实现的模块化 spec-closure workflow、Agent 边界和 Graph/Schema 门禁。
3. [`V1.5_PROJECT_INTRODUCTION.md`](V1.5_PROJECT_INTRODUCTION.md)：V1.5 多参数行为级规格分配的新会话交接、Graph 支撑判断和验收标准。
4. [`FUTURE_EXTENSION_DISCUSSIONS.md`](FUTURE_EXTENSION_DISCUSSIONS.md)：未来真实 simulator/IP 接入、架构可扩展性和后续讨论记录。
5. [`../PROJECT_PLAN.md`](../PROJECT_PLAN.md)：当前状态、后续阶段和验收标准。
6. [`../doc/V1.0_BASELINE.md`](../doc/V1.0_BASELINE.md)：V1.0 固定基线和复现说明。
7. [`PHASE1_SCHEMA_GRAPH.md`](PHASE1_SCHEMA_GRAPH.md)：当前 Phase 1 的 BlockMetaSchema、TypedGraph v2、semantic roles 和 validator 规则。
8. [`../v1/V1_DEMO_README.md`](../v1/V1_DEMO_README.md)：V1 runner 的逐阶段说明。
9. [`../doc/v1_framework_architecture_reviewed.md`](../doc/v1_framework_architecture_reviewed.md)：V1 语义边界、allocation/validation path 和可信性约束。
10. [`../doc/pll_behavioral_model_prototype_report.md`](../doc/pll_behavioral_model_prototype_report.md)：早期行为级 PLL/VCO 模型说明。
11. [`../doc/project_understanding_and_literature_review.md`](../doc/project_understanding_and_literature_review.md)：项目理解、可行性、文献和实验设计评审。
12. [`../doc/initial_framework_architecture.md`](../doc/initial_framework_architecture.md)：面向 V2/V3 的长期架构蓝图。
13. [`../doc/project_prompt.md`](../doc/project_prompt.md)：原始项目 charter，保留问题定义和早期阶段约束。

## 当前有效性层级

```text
README / PROJECT_PLAN
    当前项目入口和推进规则

docs/MODULAR_WORKFLOW
    当前已实现的 block-agnostic workflow 入口和扩展边界

docs/V1.5_PROJECT_INTRODUCTION
    V1.5-A 的实现边界、代码落点和后续验收标准

doc/V1.0_BASELINE
    V1.0 的确定性流程、结果摘要和 claim boundary；运行产物按需重新生成

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
| `docs/V1.5_PROJECT_INTRODUCTION.md` | V1.5 交接 | 新会话上下文、Graph readiness、实现路线和完成标准 |
| `docs/FUTURE_EXTENSION_DISCUSSIONS.md` | 未来扩展讨论 | 记录真实 simulator/IP 接入判断、架构不变量和后续演化决策 |
| `PROJECT_PLAN.md` | 当前计划 | 阶段路线、验收和治理规则 |
| `doc/V1.0_BASELINE.md` | 已冻结 | Git baseline、复现命令和 V1 claim |
| `docs/PHASE1_SCHEMA_GRAPH.md` | Phase 1 semantic freeze 已实现 | BlockMetaSchema v1、Graph v2、semantic-role validator 规则 |
| `v1/V1_DEMO_README.md` | V1 运行说明 | runner 阶段和 artifact 清单 |
| `doc/project_prompt.md` | 历史 charter | 最初问题定义、Problem 1/2、V1/V2/V3 目标 |
| `doc/project_understanding_and_literature_review.md` | 历史 review | 可行性、相关工作、风险和 pilot 设计 |
| `doc/initial_framework_architecture.md` | 长期蓝图 | 平台化架构、backend、orchestrator 和未来扩展 |
| `doc/v1_framework_architecture_reviewed.md` | V1 设计记录 | Contract/Oracle/Requirement/Instance 等语义边界 |
| `doc/pll_behavioral_model_prototype_report.md` | 历史模型报告 | 早期 Python/MATLAB 行为模型、方程和已知限制 |

## 阅读时应特别注意

- “已设计”不等于“已实现”；长期蓝图中的模块不能自动视为当前能力。
- V1.0 的正式 allocation 仍是 PN@1MHz 单维映射；V1.5-A 已新增 PN anchor × k1 二维行为级分配，但尚未证明真实电路中的 PN–Kvco trade-off。
- `VCO Requirement`、`Candidate`、`Realized VCO Instance` 和 `Evaluation/Evidence` 是不同对象；它们不是 Block Graph layer。
- V1 的 PASS 是 synthetic behavioral mapping proof，不是 transistor-level signoff。
