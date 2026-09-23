# V1.0 SystemSpec-to-VCO-Spec Demo

## 目标

这个 demo 用固定 Integer-N CPPLL 和确定性行为级 VCO 模型验证一条明确的双向链：

```text
正向 allocation：SystemSpec
    → PLL top-level metric / boundary
    → allocated VCO BlockSpec

反向 verification：allocated BlockSpec + realized VCO
    → BlockTB
    → same-instance SystemTB
    → PLL re-evaluation
```

当前第一条规格分配链路是：

```text
pn_anchor_1mhz_dbc_hz
    → phase_noise_1mhz_dbc_hz(context)
    → worst_phase_noise_1mhz_dbc_hz
    → integrated_jitter_s
```

其中 `pn_anchor_1mhz_dbc_hz` 只是 internal model knob；真正写入 VCO requirement 的是 frozen context 下测得的 `worst_phase_noise_1mhz_dbc_hz`，再加 engineering margin。`Kvco`、`tuning curve` 和 `Vctrl` envelope 同时作为 prove/sensitivity 证据输出。

## 运行

在仓库根目录执行：

```powershell
python run_v1_prove.py --case v1\cases\vco_mapping_01.json
python run_jitter_pn_roundtrip_demo.py
```

V1.0 主入口只保留单个 canonical case；如需保存结果，可通过 `--output-dir` 指定运行时目录。历史批量矩阵和测试产物不属于当前主干。

`run_jitter_pn_roundtrip_demo.py` 是模块化 reference case。它只负责把 JSON case
编译成 `SpecClosureRequest`、绑定 VCO adapters 并调用 `run_spec_closure()`；正向
allocation、candidate realization、反向 verification、selection 和 Graph audit 都是
可单独替换的 workflow stage。

默认运行时结果目录为（被 Git 忽略）：

```text
results/jitter_pn_roundtrip_demo/（运行时生成，不提交到源码树）
```

模块化 demo 的输入是 `v1/cases/jitter_pn_roundtrip_01.json`；主要输出是
`spec_closure_report.json`、`allocation_report.json`、`workflow_graph_v2.json` 和
`workflow_graph_audit.json`。

## 运行阶段

1. 读取 immutable `SystemSpec` 和 initial VCO requirement；
2. 运行 baseline SystemTB；
3. 生成 VCO characterization table；
4. 对 PN、K1 和 Vctrl 上限做确定性 sweep；
5. 用 bracketed bisection 搜索 `pn_anchor_1mhz_dbc_hz` boundary；
6. 冻结 `VCOBlockContext.v1` 并测量 boundary 对应的 `worst_phase_noise_1mhz_dbc_hz`；
7. 通过 allocation service 由 measured worst PN 生成 required/recommended VCO Spec；
8. 用同一个 frozen Block Context 运行所有 candidate 的 VCO BlockTB；
9. 通过 verification service 对可行 candidate 重用 realized instance 重跑 SystemTB；
10. 输出 before/after、trajectory 和 replayable evidence。

## 关键产物

```text
system_spec.json
initial_vco_spec.json
contract_v0.json
refined_vco_contract.json
vco_block_meta_v1.json
contract_validation.json
vco_characterization.csv
sensitivity.json
required_vco_spec_boundary.json
required_vco_spec.json
recommended_vco_spec.json
spec_allocation_report.json
block_feasibility.json
final_system_evaluation.json
trajectory.jsonl
summary.md
plots/
```

## V1.0 兼容扩展产物

现有 `v1/pipeline.py` 仍是确定性数值内核。当前 runner 额外输出：

```text
canonical_system_spec.json
canonical_initial_system_evaluation.json
vco_pll_graph.json
vco_pll_graph_v2.json
initial_vco_design_vector.json
recommended_requirement_evaluation.json
agent_action_policy.json
```

这些文件为后续扩展提供稳定接口：

- canonical envelope 为对象增加 `schema_version`、`object_type`、`object_id` 和 provenance；
- graph artifact 显式记录 architecture、behavioral dependency、system influence 和 evidence；
- Graph v2 对外只使用 `semantic_role = architecture | behavior | influence | evidence`；Requirement、Candidate、CapabilityRegion、BlockTB/SystemTB 是 workflow artifact，不是 Block Graph layer；
- `DesignVector` 只保存 candidate/internal knobs；Requirement 只由 frozen context 下的 measured Behavior 判断；
- Agent action policy 约束 Agent 只能提出带 evidence 的 contract/search action，不能修改 SystemSpec 或宣布 PASS。

默认运行仍然是 deterministic V1.0；模块化 round-trip 运行时输出
`spec_closure_report.json`、`allocation_report.json`、`workflow_graph_v2.json` 和
`workflow_graph_audit.json`。V1 runner 的 JSON/CSV/trajectory 仍只作为临时 evidence
生成，不提交到源码树。

`candidate_baseline` 被设计为对 jitter target 失败，`candidate_low_noise` 在 BlockTB 和最终 SystemTB 中通过。这是为了保证脚本实际经过一次可追溯的 allocation/validation 闭环，而不是默认点直接 PASS。

## 证据和边界

- 所有 sweep、residual、boundary search 和 PASS/FAIL 都由确定性 Python 代码产生；
- 每次运行没有随机数，核心 JSON/Markdown 产物可字节级 replay；
- Python 是 V1.0 canonical runner，现有 MATLAB 模型保持同方程交叉验证路径；
- 当前 PLL 是 reference-cycle sampled averaged model；`cp_current`、R/C 还不是完整连续时间 loop-filter 方程；
- 当前 jitter 只包含 VCO phase-noise contribution，不是 PSS/PNOISE signoff；
- 这是一份 behavioral mapping proof，不是 transistor-level PLL signoff。

## 后续扩展接口

下一步可以在不修改主闭环的前提下增加：

- 多温度/PVT context；
- 多维 VCO feasible/Pareto search；
- 更物理的 CP/loop-filter backend；
- MATLAB backend adapter 的自动一致性测试；
- 后续如单独启动 Agent 化，只能作为 action proposer；
- 真实 circuit/engineering-data candidate provider。
