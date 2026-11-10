# 真实工程架构

本说明以 `repo/` Stage6A字节快照为准；未来与Stage6B独立扩展另标。模块源码精确符号/行号见 SOURCE_INDEX。目录中的历史方案不优先于真实执行链。

```mermaid
flowchart TD
  S[SystemSpec / configs/SYSTEM_SPEC_STAGE1_5.json] --> C[Constraint Parsing: pipeline_contracts.load_inputs + scenarios.load_scenario]
  C --> P[Physics Mapping: block_space.check_parameters + allocation.physics.propagate]
  P --> I[Initial Allocation: AllocationStrategyPolicy.propose]
  I --> A[analytical / optimize / run_agent]
  A --> D[完整17输入候选先写盘]
  D --> E[M1 Evaluation: core.assess_m1 → M1Evaluator.evaluate]
  E --> B[Joint BlockSpec / AllocationProposal: core.proposal]
  B --> V[M2 Verification: verify 或 verify_research]
  V --> J[独立测量 + interval_judgment + check_result]
  J --> F[Feedback: pipeline_contracts.make_feedback]
  F --> R[Reallocation: policy.propose(history) → repair]
  R --> D
  J --> Z[Final Decision / result.json / trace / costs]
```

所有上述节点已有实现。图中反馈受预算、类别和策略限制，不表示真实LLM反馈闭环已经完成。Stage6A外层 `study.joint_judgment` 对研究阈值重新联合判决，不取代正式 M2 verdict。Stage6B另加 `run_multispec_pipeline`、统一研究约束及确定性局部搜索，位于独立源码变体。

## 模块与数据流

|节点|真实文件/主要符号（repo内）|输入 → 输出|
|---|---|---|
|基准加载|pipeline_contracts.py / load_inputs|pipeline_stage3a.json → config/model/spec/protocol；校验版本及内容哈希、kernel原字节SHA|
|场景覆盖|scenarios.py / validate_scenario, load_scenario|版本化BW/PM覆写+基准绑定 → 独立effective spec与scenario_binding|
|Block Space|block_space/contracts.py / load_model, validate_model, make_candidate, check_parameters|模型与17输入SI envelope → 声明域/模型有效域/派生量；不判SystemSpec可行|
|物理先验|allocation/physics.py / propagate, phase_interval, inverse_at_shape, raw_prediction|模型与规格 → 必要条件证书、条件反解/廉价预测；不是M2|
|策略|allocation/__init__.py / AllocationStrategyPolicy|模型、规格、Meter、历史 → 完整候选及metadata，或明确停止|
|M1与proposal|allocation/core.py / assess_m1, proposal, validate_proposal|完整候选 → 预测+独立M1规格判决+完整JointBlockSpec版本合同|
|预测核|physics_mapping/model.py / M1Evaluator.evaluate|MetricRequest → MappingResult，含状态、协议、因子、响应、metrics|
|M2准入|verification/verify.py / validate_proposal|候选与冻结绑定 → 合法输入；不信任proposal中的预测数值|
|研究M2适配|verification/scenario.py / validate_research_proposal, verify_research|研究阈值proposal → 原M2测量，重新绑定研究规格；不改积分器|
|完整TB|verification/verify.py / verify；run_suite.py / capture_pair；experiments.py / response_sweep|候选+protocol → 两步长捕获、四套实测频响、原始轨迹、结果|
|原生执行|verification/simulator.py / simulate；kernel.cpp / simulate|17参数+仿真设置 → ctypes/C++轨迹、边沿、成本；缺DLL明确失败|
|测量判决|verification/measure.py；verify.py / assemble_result, interval_judgment|轨迹/包络+SystemSpec → 独立M2 metrics/约束/FAIL或UNKNOWN|
|反馈|pipeline_contracts.py / make_feedback；allocation/repair.py / repair|可靠BW失败/捕获/不确定性+预算 → 结构化反馈/完整修复候选|
|总控|pipeline.py / run_pipeline|冻结输入/Policy/预算 → 首次与最终候选、attempts、trace、全部成本、正式结论|

## Mapping Registry 的准确地位

`physics_mapping/registry.py` 的 `load_registry/query/route` 读取 `docs/stage4_2/PHYSICS_MAPPING_REGISTRY.json`。注册表绑定14份原始来源，允许明确声明的CRLF/LF等价，检查单位、方程ID、适用域和启用指标。

注册表的 ANALYTICAL_INVERSE/NUMERICAL_INVERSE、PHYSICS_SCREENING、BEHAVIORAL_ONLY、UNSUPPORTED 是能力索引。`route`返回建议工具，`executes_solver=false`、`may_issue_behavioral_PASS=false`。它不是自动规划Agent，也没有自动调用任意新指标求解器。正式基准仅启用频率/BW/PM，UGF仍是诊断，不把所有注册指标升级为约束。

## 合同对象

1. `configs/BLOCK_SPACE_MODEL_V1.json` 是 behavior-block-space-1.0：17输入、41语义目录、7类联合约束、versions和experiment freeze。`configs/PLL_EQUATION_REGISTRY_V1.json`保存11条基础公式及来源，不是独立执行引擎。
2. SystemSpec 是指标列表，每项metric/unit/min/max/tolerance/evaluator/protocol/source。基准仍是version0/draft；场景哈希独立固定。
3. JointBlockSpec 的实际参数对象是 `pll-physics-mapping-2.0` envelope：`schema_version`、`conventions`、`values[name]={value,unit}`。必须有且仅有17项；固定PFD/Divider也显式保存。
4. AllocationProposal 包含候选、参数规范化JSON哈希、Block Space/SystemSpec哈希、versions、topology、operating_conditions、M1、margins、策略metadata，`verified_joint_block_spec=false`，M2尚未评价。
5. BehavioralVerificationResult 的独立字段含M2 metrics、每项constraints、overall_status、置信/包络、原始源哈希、execution_cost。M1_posthoc独立列示。
6. allocation-feedback-1.0 将候选/协议/规格绑定到反馈，带reliable标志、失败/未知/通过项和剩余预算。不能把上一候选的反馈套给另一个参数哈希。

## 测试、实验与构建入口

- 正式入口：`python -B -m pll_allocation pipeline`；`--help`仅查看参数。cli.py分派旧run/suite、pipeline及其他历史命令。
- Track A 独立入口：`python -B -m pll_allocation.track_a`。历史benchmark/LLM/模拟反馈与正式pipeline分开计成本。
- `tests/`包括合同、M1、域、Track A、pipeline、scenario、registry、native verifier以及Stage6A联合判决。`track_b/tests/`是历史对照，正式运行不依赖其历史包。
- Stage5驱动与汇总：`experiments/stage5/run_stage5.py`、collect_stage5.py、audit_stage5.py。
- Stage6A：`experiments/stage6a/study.py`做M2前分析；frozen_01保存首次proposal/计划；verifier_run_frozen.py为原实际驱动；collect.py/joint_judgment作研究汇总。历史驱动有固定路径，不能直接重启覆盖。
- 原生核：verification/build_kernel.cmd、build_return_ratio.cmd、build_closed_loop.cmd。Python读NumPy数组并ctypes加载Windows DLL；M1不需要native。

## 历史路径与未来节点

早期 `runner.py/contracts.py/policies.py/behavioral.py/_legacy/`保留40µs周期级旧模型和80/84MHz案例；它们有真实历史用途，不能删除，也不能据此认为当前M2是同一积分器。Track A六算法已正式归allocation，兼容路径不是另一套新算法。

未在Stage6A实现：LLM Region Planner、BO/TuRBO、多保真优化调度、器件模型接入、噪声/功耗认证、通用真实LLM反馈修复。Stage6B实现的确定性区域候选池与缓存不等于这些能力。更高保真参考、周期稳定性认证、模型误差建模仍是研究工作。
