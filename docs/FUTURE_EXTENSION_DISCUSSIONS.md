# 未来扩展讨论记录

> 用于记录项目从当前 V1/V1.5 demo 逐步演化到长期目标时的架构讨论、决策和待办问题。

## 1. 当前共识

当前阶段继续执行原计划，优先把以下两条确定性链路跑通并验证方法学：

```text
V1.0：SystemSpec
  → 一维 PN 分配
  → VCO BlockSpec
  → BlockTB
  → SystemTB
  → evidence / Graph audit
```

```text
V1.5：SystemSpec
  → PN × Kvco 多维 Design Space
  → sampled candidate
  → BlockTB/SystemTB 联合判定
  → Capability Region
  → System-feasible Region
  → candidate selection / replay / Graph audit
```

暂时不提前接入真实 Spectre/SPICE、真实工业 IP 数据或完整多 Block 生产化平台。当前目标是先把已经实现的 demo 跑通、复现稳定，并把其中的方法学、对象边界和证据闭环打磨清楚。

这个决定不会明显削弱后续扩展性，前提是继续保持下面的架构不变量：

- `SystemSpec` 和 pass criteria 保持不可被 candidate 或 Agent 修改；
- `DesignVector/internal knob` 不冒充 `BlockSpec Requirement`；
- BlockTB 和 SystemTB 使用同一个 realized instance；
- BlockTB/SystemTB 的结果都带 context、validity 和 provenance；
- V1.0 一维结果继续作为 regression control；
- Graph v2 的公开 semantic role 仍然是 `architecture`、`behavior`、`influence`、`evidence`；
- PASS 只能由 deterministic evaluation、BlockTB、SystemTB 和 Graph audit 产生。

## 2. 长期目标

项目的长期目标是建立一套可验证、可复现、可扩展的 PLL specification allocation 平台：

```text
不可修改的 PLL SystemSpec
        ↓
Behavioral Design Space
        ↓
多个 PLL Block 的 BlockSpec allocation
        ↓
candidate / circuit / IP / measurement realization
        ↓
context-aware BlockTB
        ↓
same-instance SystemTB
        ↓
带 validity、margin、provenance 和完整 evidence 的 preferred feasible BlockSpec
```

最终输出不应只是一个孤立参数，而应是包含以下内容的可追溯方案：

- 每个 Block 的 requirement 和 candidate；
- operating context、PVT/corner 和 validity domain；
- measurement contract 和约束 residual；
- BlockTB/SystemTB 结果；
- sensitivity、boundary/region、selection 和 replay evidence；
- simulator、模型、输入数据和版本 provenance。

Agent 的长期角色是提出 contract、search region、candidate 或 refinement 建议；它不能修改 SystemSpec，也不能替代确定性 evaluator、BlockTB、SystemTB 或 Graph audit。

## 3. 当前架构对未来扩展的判断

### 已经比较灵活的边界

- `v1/backends/protocol.py` 已经抽象出 Allocation、BlockTB 和 SystemTB backend；
- `v1/verification/service.py` 支持注入 backend，并统一组合 BlockTB、SystemTB 和 context coverage；
- `v1/api/verification.py` 中的 realized instance 是 opaque/可替换对象，不要求必须是 Python dataclass；
- `v1/workflow/protocols.py` 已经预留 `CandidateRealizer` 和 `AssignmentVerifier`；
- Graph artifact 已经保存 realized instance、measurement、evidence、provenance 和 artifact reference。

因此，未来接入真实 simulator 时，理论上的替换边界是：

```text
Synthetic backend
        ↓ replace
Spectre / SPICE / MATLAB / measurement backend
```

### 当前仍然 VCO/synthetic 专用的部分

- `v1/allocation/multidim_evaluator.py` 仍直接依赖 `VCOParams`、`measure_vco_behavior()` 和 synthetic constraint backend；
- V1.5 的 behavior vector 仍主要是 PN、Kvco、frequency、power 等 VCO 指标；
- `v1/verification/context.py` 仍然主要检查 Vctrl、temperature 和 VDD；
- V1.5 Graph compiler/audit 仍包含 VCO/PLL 特定节点和 requirement；
- `CandidateDefinition.overrides` 仍更接近 synthetic model parameter override，而不是工业 IP artifact reference；
- 当前真实 simulator 所需的任务调度、超时、失败、缓存、raw artifact 管理和重复运行策略还没有建立。

因此，当前结论是：

```text
外层 workflow/backend 骨架：已经写活
V1.0/V1.5 demo 方法学：当前优先完善
V1.5 内部 evaluator：仍有 synthetic VCO 绑定
真实 IP/simulator 数据契约：后续再抽象
```

## 4. 后续真正接入真实 IP 时的目标形态

未来不建议把真实 IP 数据继续塞进 `CandidateDefinition.overrides`。更合适的链路是：

```text
工业 IP / netlist / model card / characterization database
        ↓
Candidate / RealizedInstance Manifest
        ↓
CandidateRealizer
        ↓
Simulator or Measurement Backend Adapter
        ↓
BlockTB/SystemTB raw result
        ↓
Canonical Result Normalizer
        ↓
Behavior / Metric / Residual / Context / Provenance
        ↓
allocation / selection / Graph audit
```

届时至少需要补齐三个通用对象：

### `RealizedInstanceManifest`

描述真实实例及其身份，例如：

```text
instance_id
block_id
netlist/model/database reference
netlist hash / model hash
PVT/corner manifest
simulator and version
parameter source
```

### `MeasurementContract`

描述要测量的行为、单位、方向、有效域和约束，例如：

```text
metric_name
unit
measurement_method
required_context
validity_domain
upper/lower bound semantics
uncertainty policy
```

### `SimulationRunResult`

描述一次仿真或测量的标准化结果，例如：

```text
run_id
backend_id
instance_id
context
metrics
checks
residuals
passed
raw artifact references
provenance
failure/timeout status
```

这些对象成熟后，上层 allocation、selection、workflow 和 Graph audit 才能真正与具体 simulator 解耦。

## 5. 当前阶段不主动做的事情

在 V1.0/V1.5 demo 方法学没有稳定之前，暂不主动扩展：

- Spectre/SPICE/MATLAB 的生产级 adapter；
- CP、Loop Filter、Divider 的完整多 Block 联合模型；
- 真实工业 IP database schema；
- Monte Carlo、随机仿真和置信区间分配；
- 异步仿真任务调度、缓存和大规模并行搜索；
- 通用 Pareto optimizer；
- transistor-level signoff 或 silicon correlation。

这些不是被否定，而是延后到当前方法学已经被 V1/V1.5 demo 证明之后再做。

## 6. 当前推荐推进顺序

1. 保持 V1.0 `run_v1_prove.py` 可重复，冻结一维 baseline。
2. 保持 V1.5 `run_v1_5_allocate.py` 可重复，确认 Design Space、两个 Region、selection、replay 和 Graph audit 闭环。
3. 进一步完善 V1/V1.5 的术语、残差、validity、证据和失败分类。
4. 把已经证明的 V1.5 evaluator 能力逐步接入 block-agnostic workflow。
5. 在出现真实 simulator/IP 需求时，再新增 backend adapter 和上述三个通用数据对象。
6. 最后再扩展到多 Block、真实电路数据和 Agent-assisted proposal/search。

## 7. 讨论记录

### 2026-09-22：真实 simulator 和工业 IP 接入可扩展性

讨论结论：当前架构的 backend、verification 和 workflow 入口已经保留了可替换边界；但 V1.5 的具体 evaluator、behavior vector、context coverage 和 Graph compiler 仍然绑定 synthetic VCO。继续按老计划先跑通一维和多维 demo 是合理的，不需要为了未来真实 simulator 接入而提前重写当前实现。

当前应保护的方法学边界：

```text
SystemSpec 不可变
→ candidate/design vector
→ realized instance
→ measured behavior
→ BlockTB
→ SystemTB
→ evidence / audit
```

未来新增讨论时，优先回答以下问题：

1. 这个变化是在完善当前方法学，还是已经进入真实 backend/IP 接入阶段？
2. 新输入是 internal design knob、Block Requirement、realized instance 还是 observation？
3. 新的 simulator/measurement 是否能输出统一的 metrics、checks、residuals、context 和 provenance？
4. BlockTB/SystemTB 是否引用了同一个 realized instance 和同一组输入 artifact？
5. 该变化是否破坏 V1.0 regression control 或 Graph v2 语义？

## 8. 后续讨论模板

后续每次扩展讨论可以按以下格式追加：

```markdown
### YYYY-MM-DD：主题

背景：

希望解决的问题：

当前判断：

保持不变的边界：

需要新增/修改的接口：

暂不做的内容：

验证方式：

决定：
```

