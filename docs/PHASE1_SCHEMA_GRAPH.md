# Phase 1 Schema and Graph Design

本文是 Phase 1 的实现约定。它把早期讨论中的 Block 字段、System Graph 和 Agent 工作方式整理成一套可以逐步扩展、同时不破坏 V1.0 的结构。

## 1. 设计原则

```text
Schema is fixed grammar.
Graph is a system-specific instance.
Agent proposes.
Deterministic tools validate.
```

Schema 固定对象类型、字段含义、单位/端口规则、合法边类型和状态转换；它不固定每个未来 Block 的具体数值，也不替 Agent 猜测物理关系。

Graph 是某个具体 PLL case 的实例。当前 V1 case 会把 VCO、SystemSpec、VCORequirement、candidate、operator、BlockTB、SystemTB 和 evidence 放入同一张 typed graph，供追溯和查询。

## 2. BlockMetaSchema v1

Block 不再是简单的 `parameters + outputs`，而是四个互相分工的 contract：

```text
BlockMeta
├── InterfaceContract
├── BehaviorContract
├── CapabilityContract
└── VerificationContract
```

对应关系如下：

| Contract | 解决的问题 | 主要字段 |
|---|---|---|
| Interface | Block 做什么、怎么连接 | `function`, `ports`, `interaction_variables` |
| Behavior | 变量怎样依赖 context、如何影响 system | `search_variables`, `environment_contract`, `system_influence_factors` |
| Capability | Block 在 context 下能做到哪些组合 | `exported_specs`, `capability_region`, `tradeoffs` |
| Verification | 指标如何测、在哪些范围可信 | `measurement_contracts`, `validity_domain`, `uncertainty`, `evidence` |

机器可读模板：[`../v1/schema/block_meta_schema_v1.json`](../v1/schema/block_meta_schema_v1.json)

运行时结构校验：[`../v1/schema/block_schema.py`](../v1/schema/block_schema.py)

当前 V1 实例化输出：`results/v1_vco_mapping_01/vco_block_meta_v1.json`。

### 2.1 InterfaceContract

```json
{
  "function": "Generate context-dependent oscillator behavior",
  "ports": [
    {"name": "Vctrl", "direction": "in", "signal_type": "control_voltage", "unit": "V", "datatype": "float"},
    {"name": "phase_noise_profile", "direction": "out", "signal_type": "ssb_phase_noise", "unit": "dBc/Hz", "datatype": "function(offset_hz)"}
  ],
  "interaction_variables": ["VCO.vctrl", "VCO.phase_noise_profile", "VCO.Kvco"]
}
```

Port 规定方向、信号语义、单位和数据类型。`interaction_variables` 是跨 Block 的显式接口，避免 Agent 直接把所有内部参数连接到所有系统指标。

### 2.2 BehaviorContract

`search_variables` 是优化器可以调整的 behavioral knob；`environment_contract` 是外部条件；`system_influence_factors` 是带机制和 evidence 引用的影响声明。

```json
{
  "search_variables": [
    {
      "name": "phase_noise_1mhz_dbc_hz",
      "role": "design_variable",
      "unit": "dBc/Hz",
      "datatype": "float",
      "depends_on": ["Vctrl", "temperature", "power"],
      "evaluation_method": "deterministic PN parameter sweep",
      "description": "V1 allocation knob"
    }
  ],
  "environment_contract": {
    "variables": ["Vctrl", "temperature", "vdd_v"],
    "context_source": "SystemTB operating envelope"
  },
  "system_influence_factors": [
    {
      "source": "phase_noise_1mhz_dbc_hz",
      "target": "PLL.integrated_jitter",
      "mechanism": "VCO noise transfer followed by phase-noise integration",
      "evidence_id": "allocation:pn_1mhz_to_integrated_jitter"
    }
  ]
}
```

### 2.3 CapabilityContract

`exported_specs` 描述 System 可以向 Block 提出的要求；`capability_region` 描述 Block 实际可行的联合空间；`tradeoffs` 描述变量之间的制约。

V1 只正式承诺一维 capability：

```text
dimension = phase_noise_1mhz_dbc_hz
representation = sampled_feasible_points
status = v1_one_dimensional_only
```

`Kvco`、tuning range 和 power 已有 sensitivity/characterization evidence，但不能因为它们出现在 schema 中就声称已经完成多维分配。

### 2.4 VerificationContract

测量合同必须让两个 Block 的指标可比较。至少记录：

```text
metric
method
stimulus
context source
offset/integration band（如果适用）
aggregation rule
validity domain
uncertainty status
evidence id
```

`Environment contract` 表示 Block 对哪些外部条件作出承诺；`Validity domain` 表示模型在哪些范围内经过验证、可信。两者不能混为一个 range。

## 3. TypedGraph v2

机器可读模板：[`../v1/graph/graph_schema_v2.json`](../v1/graph/graph_schema_v2.json)

运行时模型：[`../v1/graph/model.py`](../v1/graph/model.py)

图分为四层：

```text
interface      Block / Port / Signal / Context / InteractionVariable
behavior       BehavioralOutput / DesignVariable / Operator / SystemMetric
allocation     SystemRequirement / BlockRequirement / Capability / Candidate
verification   Contract / Measurement / Validity / Evaluation / Evidence
```

### 3.1 当前 V1 的核心路径

```text
SystemSpec.integrated_jitter
        │ constrains
        ▼
PLL.integrated_jitter
        ▲ produces
        │
operator.Noise_Integration
        ▲ input_to
        │
operator.VCO_Noise_TF
        ▲ input_to
        │
VCO.phase_noise_profile
```

分配和验证路径：

```text
SystemSpec.integrated_jitter
        │ allocates
        ▼
VCORequirement.required
        │ derived_from + margin
        ▼
VCORequirement.recommended
        │ constrains
        ▼
VCO.capability_region
        │ provides sampled candidate
        ▼
Candidate.candidate_low_noise
        ├── validated_by → BlockTB.candidate_low_noise
        └── validated_by → SystemTB.candidate_low_noise
```

反向语义边 `Candidate → CapabilityRegion: candidate_of` 同时保留，便于查询候选属于哪个 capability region。

`VCORequirement`、`VCO capability`、`Candidate` 和 `Evaluation` 是不同对象，不能因为数值相近而合并。

### 3.2 Architecture Graph 与 Evaluation Graph

PLL 的反馈关系在架构图中保留：

```text
PLL → VCO.vctrl → VCO.oscillation → PLL
```

为了让数值执行路径可检查，Graph v2 把闭环内部封装成 operator：

```text
VCO_Noise_TF → Noise_Integration → System Jitter
Kvco / Icp / R / C / N → PLL_Dynamics → Lock Time / UGB / PM
```

因此：

- architecture layer 可以表达反馈；
- evaluation layer 沿 operator 形成可追溯的计算路径；
- Agent 不能在执行图中随意制造未验证的循环依赖。

## 4. Edge 生命周期

每条 Agent 提议的关系都应有状态：

```text
proposed
  → supported       有模型/文献/工程依据
  → tested          已运行局部 BlockTB 或 sensitivity
  → validated       已通过确定性 SystemTB/evaluator
  → rejected        验证失败或超出 validity domain
```

当前 V1 runner 编译出的关系来自固定模型、确定性 sweep 和验证结果，因此标记为 `validated`。未来 Agent 生成的 proposal 必须先进入 proposal graph 或以 `status=proposed` 存储，不能直接覆盖 canonical validated graph。

## 5. Agent 接口

Agent 的输入应是结构化 evidence，而不是一段自由文本：

```text
SystemSpec
Current BlockMeta
Current Graph subgraph
Metrics / Residuals
Sensitivity / Contribution
Operating Context
Candidate history
Validity / uncertainty
```

Agent 可以提出：

```text
add/remove variable
add/remove context
add/remove dependency
change scalar → function/profile
modify validity
select search region
propose candidate / Pareto preference
```

Agent 不可以：

```text
修改 SystemSpec 或 pass criteria
猜测 sensitivity 数值
把 requirement 当 capability
伪造 BlockTB/SystemTB 结果
直接宣布 PASS
```

标准动作链：

```text
Agent proposal
  → schema/type/unit/context checks
  → deterministic BlockTB / sweep / SystemTB
  → independent evaluator
  → evidence + status update
  → accepted graph instance or rejected proposal
```

结构化 proposal 模板：[`../v1/graph/graph_proposal_schema_v1.json`](../v1/graph/graph_proposal_schema_v1.json)

运行时 proposal validator：[`../v1/graph/proposals.py`](../v1/graph/proposals.py)。它只检查提议是否合法，不负责把提议直接写入 canonical graph；`validated` 状态只能由后续确定性验证流程产生。

## 6. 当前实现和下一步

Phase 1 当前已实现：

- `BlockMetaSchema v1` 的 JSON 模板和 Python validator；
- VCO 四类 contract 的 canonical instance builder；
- TypedGraph v2 的四层 node/edge vocabulary；
- Graph v2 semantic validator；
- V1 runner 的 `vco_pll_graph_v2.json` artifact；
- V1 runner 的 `vco_block_meta_v1.json` VCO contract instance；
- 13 个 deterministic tests，包括非法图拒绝、端口单位检查、schema 结构检查和 proposal 权限边界。
- read-only requirement/evidence 查询和非权威 Agent proposal validator。

下一步不是立刻让 Agent 自由发现所有关系，而是：

1. 在已有 requirement trace 和 evidence lookup 上补充 influence trace 与 context compatibility；
2. 将 sampled capability point 和 Pareto artifact 作为正式 allocation 对象；
3. 保持 `PN × Kvco` 作为第一个二维扩展，并用 V1 一维结果做 regression control；
4. 再加入 CP/Loop Filter 的 interaction contract；
5. 最后接入 Agent proposal/verification loop。
