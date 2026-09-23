# Modular Spec Closure Workflow

当前项目把 VCO jitter/PN demo 作为 reference adapter，而不是未来所有 Block 的主流程。
通用入口是 `v1.workflow.run_spec_closure()`。

## 输入边界

`SpecClosureRequest`（`v1/api/workflow.py`）包含：

```text
system_spec              immutable system requirements
base_instance            block/model seed，通用层视为 opaque
block_definition         设计变量、行为指标、系统影响和 requirement mapping
allocation_problem       多指标 allocation/search 问题
candidate_proposals      deterministic 或 Agent 提出的 candidate proposals
declared_operating_context
policy
```

`v1/schema/workflow.py` 在执行前/候选进入时检查字段、单位、引用闭合和权限。Agent
只能提交 `proposed` 对象，不能修改 immutable SystemSpec 或直接声明 PASS。

## 九个可替换阶段

`v1/workflow/protocols.py` 定义阶段协议，`WorkflowModules` 负责依赖注入：

```text
BlockDefinitionProvider
BaselineEvaluator
ContextBuilder
AllocationModule
CandidateProvider
CandidateRealizer
AssignmentVerifier
CandidateSelector
EvidenceFinalizer
```

核心编排 `v1/workflow/service.py` 不认识 VCO、PN、Kvco 或具体 simulator。当前 VCO
reference adapter 在 `v1/workflow/vco.py`，通用 provider/selector/finalizer 在
`v1/workflow/modules.py`。

## Graph/Schema 门禁

`GraphEvidenceFinalizer` 是 workflow 的最后一个 stage，而不是另一个打印脚本：

```text
allocation + candidate verification
        ↓
TypedGraph v2 compiler
        ↓
Graph/Schema audit
        ↓
EvidenceFinalizer.passed
```

它记录并审计：

```text
SystemSpec requirement → BlockRequirement.allocated
  → Candidate → RealizedInstance
  → BlockTB / SystemTB → SystemSpec.verdict
```

Graph/Schema audit 失败时，workflow 不允许返回 PASS。

## 扩展边界

| 目标 | 替换内容 |
|---|---|
| `PN × Kvco × power` | 新 `AllocationModule` 与 design-space candidate provider |
| CP/LF/Divider Block | 新 BlockDefinition、realizer、verifier adapter |
| Spectre/SPICE | `CandidateRealizer` 与 `AssignmentVerifier` backend |
| Agent 构建 Block | `BlockDefinitionProvider`，仍需通过 schema validator |
| Agent 提议候选 | `CandidateProvider`，proposal 不能宣告 PASS |
| Pareto/成本策略 | `CandidateSelector` |
| 新证据格式 | `EvidenceFinalizer` 或 Graph compiler adapter |

## Reference demo

```powershell
python run_jitter_pn_roundtrip_demo.py
```

输入：`v1/cases/jitter_pn_roundtrip_01.json`

输出：

```text
results/jitter_pn_roundtrip_demo/spec_closure_report.json
results/jitter_pn_roundtrip_demo/allocation_report.json
results/jitter_pn_roundtrip_demo/workflow_graph_v2.json
results/jitter_pn_roundtrip_demo/workflow_graph_audit.json
```

V1.0/V1.5 runners 暂时作为兼容 runner 保留；下一步将 V1.5 多维 evaluator 接入新的
`AllocationModule`，而不是继续把更多 VCO 特例写进 workflow core。
