# V1.0 SystemSpec-to-VCO-Spec Demo

## 目标

这个 demo 用固定 Integer-N CPPLL 和确定性行为级 VCO 模型验证：

```text
VCO behavioral metric
    → PLL top-level metric
    → VCO requirement boundary
    → realized VCO feasibility
    → PLL re-evaluation
```

当前第一条规格分配链路是：

```text
phase_noise_1mhz
    → integrated_jitter
```

`Kvco`、`tuning curve` 和 `Vctrl` envelope 同时作为 prove/sensitivity 证据输出。

## 运行

在仓库根目录执行：

```powershell
python run_v1_prove.py --case v1\cases\vco_mapping_01.json
```

默认结果目录为：

```text
results/v1_vco_mapping_01/
```

## 运行阶段

1. 读取 immutable `SystemSpec` 和 initial VCO requirement；
2. 运行 baseline SystemTB；
3. 生成 VCO characterization table；
4. 对 PN、K1 和 Vctrl 上限做确定性 sweep；
5. 用 bracketed bisection 搜索 Required PN Boundary；
6. 加入显式 margin 生成 Recommended VCO Spec；
7. 用每个 candidate 的 SystemTB context 运行 VCO BlockTB；
8. 对可行 candidate 重用 realized instance 重跑 SystemTB；
9. 输出 before/after、trajectory 和 replayable evidence。

## 关键产物

```text
system_spec.json
initial_vco_spec.json
contract_v0.json
refined_vco_contract.json
contract_validation.json
vco_characterization.csv
sensitivity.json
required_vco_spec_boundary.json
required_vco_spec.json
recommended_vco_spec.json
block_feasibility.json
final_system_evaluation.json
trajectory.jsonl
summary.md
plots/
```

## V1.0 兼容扩展层

现有 `v1/pipeline.py` 仍是确定性数值内核。当前 runner 额外输出：

```text
canonical_system_spec.json
canonical_initial_system_evaluation.json
vco_pll_graph.json
initial_vco_spec_vector.json
recommended_vco_spec_vector.json
recommended_spec_vector_evaluation.json
agent_action_policy.json
```

这些文件为后续扩展提供稳定接口：

- envelope 层为对象增加 `schema_version`、`object_type`、`object_id` 和 provenance；
- graph 层显式记录 signal flow、feedback、behavioral dependency、noise transfer、system influence 和 sensitivity evidence；
- `SpecVector` 为 PN、Kvco、tuning range、power 的联合规格表示预留入口；
- Agent action policy 约束 Agent 只能提出带 evidence 的 contract/search action，不能修改 SystemSpec 或宣布 PASS。

默认运行仍然是 deterministic V1.0；这些扩展不会改变现有 `SystemTB`、PN boundary search、BlockTB 或最终 candidate 选择逻辑。

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
- Problem 1/Problem 2 Agent 作为 action proposer；
- 真实 circuit/engineering-data candidate provider。
