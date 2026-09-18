# PLL_EVALAGENT Project Plan

## 1. 项目目标

建立一条可验证、可复现、可扩展的：

```text
PLL SystemSpec
  → Behavioral Design Space
  → BlockSpec Allocation
  → Simulation / Engineering-Data Validation
  → Validated BlockSpecs
```

项目不假设 SystemSpec 对应唯一的 BlockSpec。目标是搜索：

```text
C* ∈ { block-spec candidates | PLL(C*) satisfies SystemSpec
                         and every block is feasible in context }
```

最终输出的是带有 context、measurement definition、validity domain 和 evidence 的 preferred feasible BlockSpec，而不是没有证据的单个数字。

## 2. 两个核心问题

### Problem 1：构造 Behavioral Design Space

输入是 PLL architecture、System context 和已有模型/工程知识；输出是机器可读、可测试、可优化的 Block behavioral contract：

```text
Blocks
Variables
Ports
Context
Dependencies
Capability region
Measurement contract
Validity / uncertainty
```

核心难点是找到“最小但足够”的变量和依赖。Contract 是 hypothesis，必须和 simulator 或 engineering-data observation 区分开。

### Problem 2：在空间中做 Specification Allocation

输入是 immutable SystemSpec 加上已验证或带状态的 behavioral abstraction；输出是满足系统指标且 BlockTB 可行的 BlockSpec candidate。

核心闭环是：

```text
SystemTB
  → metrics / residuals / operating context
  → deterministic sensitivity / contribution
  → allocator / search controller
  → candidate BlockSpec
  → context-aware BlockTB
  → SystemTB re-validation
```

如果搜索反复失败，要判断是数值空间中尚未找到解，还是 contract 缺少变量、context、dependency 或 validity。前者继续 Problem 2，后者回到 Problem 1。

## 3. 当前已完成：V1.0

V1 固定：

- Architecture：Integer-N CPPLL；
- Target Block：VCO；
- Backend：Python deterministic behavioral model，MATLAB equation-level cross-check；
- Search knob：VCO internal `pn_anchor_1mhz_dbc_hz`；
- Allocated measured metric：VCO `worst_phase_noise_1mhz_dbc_hz`；
- Top-level metrics：output frequency、integrated jitter、lock time、power；
- Search：deterministic finite-difference/grid sensitivity + bracketed bisection；
- Validation：context-aware VCO BlockTB + realized-instance SystemTB。

代码路径：

```text
SystemSpec                  v1/specs.py
SystemTB / allocation core  v1/pipeline.py
VCO model                   v1/model/pll_behavioral.py
V1 orchestration            run_v1_prove.py
Contract evidence           v1/contract.py
Graph/schema seam           v1/graph/, v1/schema/
Forward-compatible vector   v1/allocation/
```

V1 实际结果：

```text
Initial jitter:             83.367 fs  (limit 80 fs, FAIL)
PN anchor boundary:         -116.358121 dBc/Hz
Worst measured PN boundary: -113.511151 dBc/Hz
Required PN requirement:    -113.511151 dBc/Hz
Recommended phase-noise req:-115.011151 dBc/Hz
Selected candidate:         candidate_low_noise
Final jitter:               41.783 fs
Final lock time:            36.520 us
Final frequency:            5.000 GHz
Final SystemTB:             PASS
Core pytest regression:     23/23 PASS
```

V1 同时证明了两件事：

1. 一个不足的 VCO contract 可以被 observation holdout 发现，并通过添加 context/dependency 得到 refinement evidence；
2. 在 immutable SystemSpec 下，可以先搜索 internal PN anchor boundary，再用 frozen Block Context 测得 worst PN，生成 VCO PN requirement，经过 BlockTB 后再用同一个 realized instance 回到 SystemTB 验证。

在不改动该基线的附加映射实验中，现已用同一确定性 workflow 执行：

```text
jitter      → PN@1MHz upper bound
lock time   → VCO k1 local lower boundary
power       → VCO nominal-power upper bound
frequency   → VCO f0 / tuning-coverage local boundary
```

其中 PN 和 power 在已扫描范围表现为单边界；lock-time/Kvco 与 frequency/f0
在宽范围内表现为可行窗口，只能在记录的 validity bracket 内作为局部一维映射。
这一步增加的是多种“一维 proof case”，不是多个参数同时优化，因此不应标记为
Phase 2 多维 capability region 已完成。

## 4. 现阶段明确没有完成的内容

以下内容已预留接口或写入设计，但不应标记为已完成：

- Graph 完全驱动 allocation 和 simulation 的执行；
- `PN × Kvco × tuning range × power` 正式联合 allocation；
- CP、Loop Filter、Divider 的独立 noise source 和完整 cross-block model；
- transistor-level PSS/PNOISE signoff；
- Agent 自动发现 architecture、自动拆分/合并 Block；
- Agent 自主决定并确认 sensitivity 或 PASS；
- 从真实 circuit/measurement data 做 calibration/correlation。

## 5. 后续阶段路线

### Phase 0：V1.0 Baseline（已完成）

目标：冻结可复现的最小闭环。

验收：

- Git tag `v1.0-baseline`；
- 原有 10 个测试通过；
- benchmark 的 boundary、candidate、final SystemTB 结果稳定；
- summary、trajectory、provenance 和关键 JSON/CSV 可追溯。

### Phase 1：Semantic-role Schema 和 Graph v2（已完成）

目标：保留 V1 数值结果，把关系地图变成类型化、可检查的结构，同时冻结 Block Graph 对外语义。

当前 Phase 1 已落地的结构：

```text
BlockMetaSchema v1
  ├─ architecture
  ├─ behavior
  ├─ influence
  └─ evidence

TypedGraph v2 semantic_role
  ├─ architecture
  ├─ behavior
  ├─ influence
  └─ evidence
```

Workflow artifacts 仍然存在，但只作为对象记录：

```text
SystemSpec
BlockRequirement
Candidate
RealizedInstance
DesignSpace
CapabilityRegion
Schema
Contract
```

这些对象不是 Block Graph layer。runner 会继续生成兼容的 `vco_pll_graph.json`，并新增经过 validator 检查的 `vco_pll_graph_v2.json`。

本阶段完成的语义修正：

1. `layer` 对外替换为 `semantic_role`，合法值只允许 `architecture`、`behavior`、`influence`、`evidence`；
2. VCO architecture 只保留真实接口和 context input，不再把 phase noise、Kvco、power 当 port；
3. VCO Behavior metrics 固定为 `frequency_hz`、`phase_noise_1mhz_dbc_hz`、`kvco_hz_per_v`、`power_w`；
4. Influence 从 Behavior 中拆出，要求明确 source Behavior metric、target System metric、mechanism、evidence_refs 和 validity_domain；
5. PN 命名拆成 `pn_anchor_1mhz_dbc_hz`、`phase_noise_1mhz_dbc_hz`、`worst_phase_noise_1mhz_dbc_hz`、`phase_noise_1mhz_max_dbc_hz`；
6. BoundarySearch 输出 `search_knob_boundary`，并用 frozen `VCOBlockContext.v1` 测得 `block_metric_at_boundary` 后再生成 requirement；
7. Candidate/internal knobs 统一称为 `DesignVector`，不再使用旧 Spec 命名；
8. CapabilityRegion 使用 BlockTB 验证过的 Behavior aggregate，不把 internal anchor 当 capability。

验收：

- 原有 V1 SystemTB / BlockTB / scalar bisection 数值 replay 保持稳定；
- graph 能追溯 `SystemSpec → Requirement → Candidate → RealizedInstance → BlockTB/SystemTB → Evidence`；
- 每条 influence edge 都有模型、context 和 evidence 引用；
- semantic validator 会拒绝旧端口、旧 layer、knob-as-behavior、candidate-as-requirement、anchor-as-requirement 等破坏用例；
- 核心 pytest 回归 23/23 PASS；
- 明确没有 Proposal layer、没有 Allocation layer in Block Graph、没有 Capability layer、没有第五个 Block Graph layer。

### Phase 2：多参数 VCO Capability Region

目标：从一维 PN mapping 扩展到真实的联合可行域。

最小实验：

```text
PN@1MHz × Kvco
```

输出 sampled feasible points、constraint residual 和 Pareto candidates。随后再加入 tuning range 和 power。

验收：

- 每个点都有明确 context 和 BlockTB result；
- feasible/infeasible 由确定性 evaluator 判定；
- Pareto 规则和目标权重显式记录；
- 一维 V1 baseline 作为 regression control 保持不变。

### Phase 3：多 Block 固定架构（V2）

扩展到：

```text
PFD/CP + Loop Filter + VCO + Divider
```

重点不是自动发现架构，而是建立 cross-block interaction variables 和联合 sensitivity：

```text
CP noise → CP Noise TF → Noise Integration → Jitter
Icp / R / C / Kvco → PLL Dynamics → UGB / PM / Lock Time
```

验收：

- 每个 Block 都有 context-aware BlockTB；
- system metric 的贡献路径可追溯；
- 至少一个多 Block allocation case 可 replay；
- System PASS 和 Block feasibility 同时成立。

### Phase 4：Agent 化 contract/search proposal

Agent 负责：

- 提议变量、context、dependency 和 validity refinement；
- 提议 search region、candidate 和 Pareto preference；
- 根据 failure evidence 判断继续搜索还是回到 abstraction refinement。

Agent 不负责：

- 修改 SystemSpec/pass criteria；
- 直接计算 sensitivity；
- 伪造仿真结果；
- 直接宣布最终 PASS。

标准流程：

```text
Agent proposal
  → schema/type/unit checks
  → deterministic simulator / sweep / TB
  → independent evaluator
  → proposed / supported / tested / validated / rejected
```

### Phase 5：真实工程后端与 V3

保持上层 schema、graph、allocation、evaluator 尽量不变，只替换或增加：

- Spectre/SpectreRF、SPICE、Verilog-A backend；
- engineering data / silicon measurement backend；
- calibration 和 model-correlation flow；
- architecture decomposition、Block split/merge 和 adaptive partition。

V3 才研究从 architecture 自动构建 behavioral design space，不让这个长期目标阻塞 V1/V2。

## 6. 固定不变的治理规则

1. `SystemSpec` 是 immutable input，Agent 不可修改；
2. sensitivity 必须来自 deterministic sweep/finite difference/approved numerical method；
3. requirement、capability、realized instance、evaluation/evidence 必须分开；
4. BlockTB 必须使用 SystemTB 提取的 operating context，而不是任意 nominal point；
5. 最终输出必须同时满足 SystemSpec 和 Block feasibility；
6. 每个正式结论必须带 provenance、measurement contract、validity domain 和 evidence；
7. 代码改动必须通过 V1 regression/replay，不能用图结构升级改变 V1 数值结果。

## 7. 每个阶段的统一验收模板

每次扩展都要回答：

```text
What changed?
What deterministic evidence was added?
Did v1.0 replay remain identical?
Which claims are proven, proposed, or unsupported?
What failure would falsify the current abstraction?
```

这保证项目始终围绕：

```text
System Specification
  → Validated Behavioral Block Specification
```

而不是逐渐退化成只展示一个能 PASS 的候选点。
