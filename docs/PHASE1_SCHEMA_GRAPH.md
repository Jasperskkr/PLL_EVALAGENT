# Phase 1 Schema and Graph Design

本文记录当前 V1 的 Semantic Freeze 结果。它不是功能扩展，也不是新的执行引擎；目标是把 Block Graph 对外语义固定下来，并消除 Requirement、model knob、Behavior metric、measured metric 之间的命名混用。

## 1. 设计原则

```text
Schema is fixed grammar.
Graph is a system-specific instance.
Workflow artifacts are objects, not Block Graph layers.
Deterministic tools validate numeric claims.
```

Schema 固定对象类型、字段含义、单位、端口规则、合法边类型和证据要求。Graph 是某个具体 PLL case 的实例化关系地图。当前 V1 case 会把 VCO、SystemSpec、VCORequirement、Candidate、RealizedInstance、BlockTB、SystemTB 和 Evidence 放入同一张 typed graph，供追溯和查询。

Block Graph 对外唯一语义分类是：

```text
architecture
behavior
influence
evidence
```

`SystemSpec`、`BlockRequirement`、`Candidate`、`RealizedInstance`、`CapabilityRegion`、`DesignSpace`、`Schema` 和 `Contract` 都是 workflow object/artifact，不是 Block Graph layer。

## 2. BlockMetaSchema v1

BlockMeta 顶层固定为四部分：

```text
BlockMeta
├── architecture
├── behavior
├── influence
└── evidence
```

对应关系如下：

| 部分 | 回答的问题 | 当前 VCO 例子 |
|---|---|---|
| `architecture` | Block 是什么、怎么接 | VCO identity、`Vctrl`、oscillator output、temperature/VDD context |
| `behavior` | Block 在给定 context 下表现出什么 | `frequency_hz`、`phase_noise_1mhz_dbc_hz`、`kvco_hz_per_v`、`power_w` |
| `influence` | Block Behavior 如何影响 System Metric | VCO PN → PLL jitter，VCO Kvco → jitter/lock time |
| `evidence` | 上述结论凭什么可信 | characterization、sensitivity、boundary search、BlockTB、SystemTB、audit/provenance |

机器可读模板：[`../v1/schema/block_meta_schema_v1.json`](../v1/schema/block_meta_schema_v1.json)

运行时结构校验：[`../v1/schema/block_schema.py`](../v1/schema/block_schema.py)

当前 V1 实例化输出：`results/v1_vco_mapping_01/vco_block_meta_v1.json`。

### 2.1 Architecture

Architecture 只包含 block identity、真实物理/功能端口、signal connections、feedback connections 和 environment/context inputs。

VCO 的 architecture 例子：

```json
{
  "block_id": "VCO",
  "function": "Generate context-dependent oscillator output",
  "ports": [
    {"name": "Vctrl", "direction": "in", "signal_type": "control_voltage", "unit": "V"},
    {"name": "oscillation_output", "direction": "out", "signal_type": "oscillation", "unit": "Hz"}
  ],
  "context_inputs": [
    {"name": "temperature", "unit": "degC"},
    {"name": "vdd", "unit": "V"}
  ]
}
```

Phase noise、Kvco 和 power 不是 port。它们属于 Behavior。

### 2.2 Behavior

Behavior metric 是在给定 context 下实际可计算或可测量的 Block 表现。当前 VCO 正式 Behavior metrics 固定为：

```text
frequency_hz
phase_noise_1mhz_dbc_hz
kvco_hz_per_v
power_w
```

VCO 行为节点示例：

```json
{
  "node_id": "VCO.phase_noise_1mhz",
  "semantic_role": "behavior",
  "properties": {
    "metric_name": "phase_noise_1mhz_dbc_hz",
    "unit": "dBc/Hz",
    "depends_on": ["Vctrl", "temperature", "power_w", "realization"]
  }
}
```

Internal model coefficient / candidate knob 不能标记为 Behavior metric。比如 `pn_anchor_1mhz_dbc_hz`、`k1_hz_per_v`、`nominal_power_w` 是 candidate/model knobs，不是 measured Behavior。
`vdd_v` 可以保留为 Architecture/Context input；当前 behavioral equations 未使用 VDD，因此 Graph 不声明 `VDD -> frequency/PN` 行为依赖。

### 2.3 Influence

Influence 表达 Block Behavior 怎么影响 System Metric。Influence 必须明确：

```text
source_behavior_metric
target_system_metric
mechanism
evidence_refs
validity_domain
```

当前至少保留：

```text
VCO.phase_noise_1mhz -> PLL.integrated_jitter
VCO.kvco             -> PLL.integrated_jitter
VCO.kvco             -> PLL.lock_time
VCO.frequency        -> PLL.output_frequency
VCO.power            -> PLL.power
```

Block 内部的 `Vctrl -> phase_noise_1mhz_dbc_hz` 属于 behavioral dependency；Block 到 System 的 `phase_noise_1mhz_dbc_hz -> integrated_jitter_s` 属于 `system_influence`。两者不能混用。

### 2.4 Evidence

Evidence 是实际产生的结果，不是 schema 断言。当前 Evidence 包括：

```text
characterization
sensitivity
boundary-search records
BlockTB
SystemTB
context coverage
holdout
audit / provenance
```

Evidence node 必须带 provenance 和 measurement method。BlockTB evidence 还必须引用 frozen `VCOBlockContext.v1`。

## 3. TypedGraph v2

机器可读模板：[`../v1/graph/graph_schema_v2.json`](../v1/graph/graph_schema_v2.json)

运行时模型：[`../v1/graph/model.py`](../v1/graph/model.py)

Graph v2 node 对外使用 `semantic_role`，合法值只有：

```text
architecture
behavior
influence
evidence
```

Workflow artifacts 可以有 `node_type` / `artifact_type`，但不因此成为 graph layer。`VCORequirement`、`Candidate`、`RealizedInstance`、`DesignSpace`、`CapabilityRegion`、`MeasurementContract`、`ValidityDomain` 和 `Uncertainty` 都按对象身份记录。

当前 JSON 仍保留 `plane`、`authority`、`scope`、`mutability` 和 `provenance` 字段，用于实现侧的 provenance/authority 分组。`plane` 不是公开 Block Graph semantic layer，也不参与 `semantic_role` 的四角色解释。

### 3.1 当前 V1 的核心路径

System-to-Block requirement 路径：

```text
SystemSpec.integrated_jitter
        │ target_system_metric
        ▼
BoundarySearch.search_knob = pn_anchor_1mhz_dbc_hz
        │ bisection under SystemTB
        ▼
search_knob_boundary
        │ measure under frozen VCOBlockContext.v1
        ▼
worst_phase_noise_1mhz_dbc_hz
        │ compare / margin
        ▼
VCORequirement.phase_noise_1mhz_max_dbc_hz
```

Influence path:

```text
VCO.phase_noise_1mhz
        │ system_influence
        ▼
PLL.integrated_jitter
```

Candidate validation path:

```text
VCORequirement
        │ constrains
        ▼
Candidate
        │ compile
        ▼
RealizedInstance
        ├── BlockTB under VCOBlockContext.v1
        └── validation SystemTB
                ▼
          final PASS/FAIL Evidence
```

Candidate、RealizedInstance、Requirement 和 Evidence 是不同对象，不能因为数值相近而合并。

### 3.2 Context closure

VCO BlockTB 的 measurement context 在评估任何 candidate 之前冻结：

```text
Initial SystemTB operating envelope + declared guard
                    │ freeze
                    ▼
            VCOBlockContext.v1
              ├── boundary-point measurement
              ├── candidate BlockTB
              └── final context coverage check
```

所有 candidate 使用同一个 frozen Block Context。候选只有在 BlockTB PASS、SystemTB PASS 且实际 SystemTB context 被冻结合同覆盖时，才可参与最终选择。

### 3.3 DesignSpace 与 CapabilityRegion

DesignSpace 描述可以尝试哪些 candidate/model knobs，例如：

```text
pn_anchor_1mhz_dbc_hz
k1_hz_per_v
nominal_power_w
f0_hz
```

CapabilityRegion 描述经过 BlockTB Evidence 后，Block 在 Behavior space 中实际能做到什么。当前 capability axes 使用 measured Behavior aggregates：

```text
worst_phase_noise_1mhz_dbc_hz
frequency_min_hz / frequency_max_hz
kvco_min_hz_per_v / kvco_max_hz_per_v
worst_power_w
```

V1 仍是一维 proof case，不声称已有完整 `PN × Kvco` feasible region。

## 4. PN 命名冻结

PN 的四种身份固定如下：

| 身份 | 字段 | 含义 |
|---|---|---|
| internal model knob | `pn_anchor_1mhz_dbc_hz` | synthetic VCO realization knob |
| point Behavior metric | `phase_noise_1mhz_dbc_hz` | 给定 Vctrl/T/VDD/realization 下的 PN@1MHz |
| measured Block metric | `worst_phase_noise_1mhz_dbc_hz` | BlockTB 在 frozen context sweep 后的 max PN |
| allocated Block Requirement | `phase_noise_1mhz_max_dbc_hz` | requirement object 中对 measured worst PN 的上限 |

数据流固定为：

```text
pn_anchor_1mhz_dbc_hz
            ↓
phase_noise_1mhz_dbc_hz(context)
            ↓
worst_phase_noise_1mhz_dbc_hz
            ↓ compare / margin
phase_noise_1mhz_max_dbc_hz
```

旧字段 `pn_1mhz_dbc_hz` 只允许在 load boundary 作为 legacy alias 读取，并立即 normalize 为 `pn_anchor_1mhz_dbc_hz`。

## 5. BoundarySearch 输出语义

BoundarySearch 仍使用原来的 scalar bisection 算法，但输出字段必须说明它找的是 search knob boundary，而不是直接找到 Block Requirement。

当前 PN case 输出：

```text
search_knob:                      pn_anchor_1mhz_dbc_hz
search_knob_boundary:             -116.358121 dBc/Hz
target_system_metric:             integrated_jitter_s
target_system_metric_at_boundary: 7.999999e-14 s
block_metric_at_boundary:         -113.511151 dBc/Hz
validity_domain:                  bracket/domain metadata
history:                          deterministic bisection records
```

VCO PN requirement 来自 `block_metric_at_boundary`，再结合 margin：

```text
required phase_noise_1mhz_max_dbc_hz     = -113.511151 dBc/Hz
recommended phase_noise_1mhz_max_dbc_hz  = -115.011151 dBc/Hz
```

## 6. Semantic Validator

Graph validator 会拒绝以下错误，而不是只修改文档：

1. Architecture 中出现 Kvco / PN / Power 作为 port；
2. 同时存在 `VCO.Kvco` 和 `VCO.kvco`；
3. internal model knob 被标记为 Behavior metric；
4. Behavior → SystemMetric 的关系没有被标记为 Influence；
5. Requirement 没有明确对应 measured Behavior metric；
6. Candidate knob 被直接拿来判断 BlockRequirement；
7. PN anchor boundary 被直接写成 `phase_noise_1mhz_max_dbc_hz`；
8. BlockTB 没有使用 frozen `VCOBlockContext.v1`；
9. Evidence 没有 provenance / measurement method；
10. CapabilityRegion 使用未经 BlockTB 验证的点却声称 feasible。

测试会构造这些破坏用例，确认 semantic validator 必须 FAIL。

## 7. 当前实现和下一步

当前已实现：

- `BlockMetaSchema v1` 的 JSON 模板和 Python validator；
- VCO `architecture` / `behavior` / `influence` / `evidence` canonical instance builder；
- TypedGraph v2 的 `semantic_role` node/edge vocabulary；
- Graph v2 semantic validator；
- V1 runner 的 `vco_pll_graph_v2.json` artifact；
- V1 runner 的 `vco_block_meta_v1.json` VCO metadata instance；
- 正向/拒绝 case 的 `graph_audit.json` 与 `agent_goal_context.json`；
- 冻结的 `vco_environment_contract.json` 与独立 Final SystemTB context coverage；
- deterministic tests，包括非法图拒绝、端口单位检查、schema 结构检查、语义破坏审计和 legacy alias normalization。

下一步不是把 workflow artifact 升级成新的 graph layer，而是在已有语义冻结上继续增加 verified data：

1. 保持 V1 PN anchor boundary 作为 regression control；
2. 单独启动 `PN × Kvco` feasible-region 搜索时，仍以 BlockTB Evidence 判定 feasible points；
3. 再加入 CP/Loop Filter 的 cross-block context；
4. 任何 future action proposer 都只能提出候选动作，不能直接写入 validated Evidence。

明确边界：

```text
no Proposal layer
no Allocation layer in Block Graph
no Capability layer
no fifth Block Graph layer
```
