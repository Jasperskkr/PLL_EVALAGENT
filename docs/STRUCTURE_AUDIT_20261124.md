# 项目结构审核与接口清洗（2026-11-24）

## 结论

主线已经具备完整连续域多候选分配与正式验证能力。主要结构问题是兼容入口、共享算法、可选研究和来源绑定仍交织；不能通过删除名字显旧的目录完成清洗。本轮按用户优先级先整理输入、输出和交接，内部算法及目录搬迁留作后续。

审核以当前工作区为准，包含此前尚未提交的条件物理/噪声/启动排序改动。实际 Git 根目录是外层同名目录中的 `PLL_EVALAGENT-main/`。审核前包内142个 Python 文件；本轮新增两个接口模块，现144个。没有删除旧源码、配置、实验或构建。

审核期间另一个任务加入了正整数N的M2频率规划；按用户明确要求一并纳入验收。当前标准连续域仍固定参考10MHz与0–1.2V电压轨，N来自问题，目标为N×f_ref；nominal/冻结示例仍是N=8。旧冻结与可选验证扩展的范围保持独立。314份源码/配置/本地后端文件复制到独立快照，复制期间逐文件哈希无变化，避免把并行改动过程中的混合版本当作稳定验收。

## 1. 唯一正式主线

```text
python -m pll_allocation pipeline
  cli.main → pipeline.main
  problem + allocator → run_spec_allocation
    → run_initial_allocation
    → PoolSearchLoop → PhysicsToolSearchLoop → AgentSearchLoop
    → Policy提议 → 合同校验 → 物理反解/RegionExplorer
    → 正式M1 → 候选账本/去重/质量筛选 → 独立M1复核
    → verification_handoff → run_feedback
    → verification.continuous → 原生内核/测量/判决
    → 池内换点或预算内补点/修复
  → validate_sizing_handoff → 权威结果文件 → run_manifest.json
```

默认配置为 `configs/agent/spec_allocation.json`，用户问题位于 `configs/problems/`。M1池目标5、联合交付目标3、M1预算96、M2预算8。M1-only、确定性、真实LLM、Auto共用正式执行器与验证器。真实LLM仍须现有授权，不因接口清洗自动启用。

| 核心职责 | 源码 |
| --- | --- |
| 输入、路由与输出索引 | `cli.py`、`pipeline.py`、`io_contracts.py` |
| 问题/单位/参数域、物理构造 | `exploration/contracts.py`、`physics_region_builder.py`、`allocation/physics.py` |
| 决策循环、预算与实际工具执行 | `agent/spec_allocation.py`、`initial_allocation.py`、`pool_search.py`、`search_loop.py`、`physics_tool_policy.py`、`region_explorer/` |
| 正式M1与共享基础 | `physics_mapping/model.py`、`experiment.py`、`block_space/contracts.py`、`allocation/core.py` |
| 候选、独立复核与交接 | `agent/candidates.py`、`candidate_pool.py`、`handoff.py`、`delivery.py` |
| 正式M2与反馈 | `agent/feedback.py`、`deterministic_feedback.py`、`verification/continuous.py`、`experiments.py`、`run_suite.py`、`simulator.py`、`measure.py`、`kernel.cpp`、`build_identity.py` |

`region_policy.py`/`llm_transport.py` 是LLM分支需要的能力；`subregion_*`、`calibration.py` 中有主线共享函数，不能因为其原始用途是区域规划而整块删除。默认COLD模式不预做大规模校准；按需Sobol与旧单点的预校准应分别理解。

## 2. 本轮已清洗的输入、输出和交接

| 已复现问题 | 本轮处理 |
| --- | --- |
| 同一JSON字段重复时静默采用最后一个值 | 统一严格读取；重复键、非有限数与浮点溢出在合同解析前拒绝 |
| 缺少问题文件时CLI输出Python traceback | pipeline返回结构化 `INPUT_OR_OUTPUT_ERROR`，退出码2；不创建运行目录 |
| allocator 为null/数组时可能绕过对象合同而抛属性错误 | 执行前明确拒绝；Handoff消费者同样检查对象类型 |
| 重新计算摘要后，`gate_status=BLOCKED` 与 `ready_for_stage9=true` 仍能同时通过 | 必须READY、旧ready为true且无阻断原因，再执行原有证据校验 |
| 零候选交付可被标为TARGET_REACHED并附不存在的推荐身份 | 数量、目标、达成标志、状态与推荐身份一致校验 |
| 正式多点交付校验只在可选VCO模块中，生产端未共用 | 提取至 `delivery.py`，输出前和VCO消费时共用原有M1/M2绑定与重判逻辑；不新增求解/仿真 |
| 完整M1运行目录迁移后仍读原目录的绝对context路径 | 新交接附相对引用，复制完整运行目录后检查复制的context；旧绝对路径合同保留 |
| 多份结果与旧阶段名副本令消费者难判断权威文件 | 新增 `run_manifest.json`：只索引当前权威产物、相对路径与SHA256，指明正式下游集合 |

交接哈希表示记录一致性，不认证实验真实性。正式M2 PM/jitter仍保留UNKNOWN；条件预测和TEST注入仍不能进入原生联合交付。

新频率协议另按记录中的适配版本校验：旧 `pll-continuous-m2-1.0` 只接受N=8原协议；`1.1` 检查 `integer_n_metrics_1.0` 与候选N、f_ref、输出目标一致。读取旧交付不要求原DLL存在，不把旧协议/历史结果升级为新版证据。输入context在Windows另一盘符时保留原绝对引用，跨盘符接续不会因相对路径生成失败而退化；这类外部context仍须随交接另行提供。

### 干净的消费约定

| 对接方 | 应读内容 | 含义 |
| --- | --- | --- |
| 用户输入 | problem JSON、allocator JSON；LLM时另加provider配置 | 用户域/规格与策略预算分开；模型/协议不作为新问题配置修改 |
| 前端/自动脚本 | `run_manifest.json` → `allocation_result.json`、`cost_summary.json` | 一个权威索引；过程完成、质量、交付达标分别读取 |
| 后续sizing开发 | `sizing_handoff.json.candidates`，先调用 `validate_sizing_handoff` | 只含正式M1合格及原生M2已支持项通过的候选；允许部分/空交付 |
| 接续M2/反馈 | `initial/verification_handoff.json` 及其绑定context/证据 | M1已复核输入，不是已通过M2的下游交付 |
| 诊断研究 | `candidates.json`、`initial/`、`verification/` | 含失败、未测及近邻证据，不从中另选一个“成功”字段替代交付门禁 |

`allocation_result.recommended` 仍保留旧回退语义，可能只有M1通过。正式推荐读取 `recommended_M2_supported`；正式集合读取 `sizing_handoff.candidates`。旧 `stage9_*` 文件只在过程证据中保留兼容用途，不进入新权威索引。

## 3. 有后续价值，保留为可选能力

| 代码/输入 | 保留原因与边界 |
| --- | --- |
| `vco_sizing/` | 行为目标→VCO开发合同、实测回填与再验证；默认分配不依赖其开发功能 |
| `studies/ablation*`、`initial_allocation.py`、`multi_region.py`、`allocation_baselines.py` | 公平基线、等预算对照、消融与多区域研究；不再扩成第二套正式Pipeline |
| `agent/computational_window.py`、`window_contract.py` | 计算窗口与物理意图合同，研究分支仍有调用；非无用文件 |
| `analytic_features.py`、`predictors.py`、`physics_ranking.py`、`conditional_observation.py`、`conditional_physics.py` | 近期条件噪声/启动/排序扩展；显式开关、来源证据和适用条件保留，不赋予正式PASS权 |
| `verification/noise*`、`nonideal*`、`phase_step*`、`return_ratio*` 与独立构建/协议 | 扩展可测指标与模型研究，默认路径不自动启用 |
| `block_space/` 的采样、校准、事件参考、验证；`physics_mapping/validation.py` | 数值核对与模型回归；删除会削弱后续正确性验证 |
| `physics_mapping/registry.py`、`configs/model/`、`configs/provenance/` | 物理关系、冻结来源与哈希绑定；静态无业务导入不等于可以删除 |
| `tools/` 的例题、图谱、profiles/内核生成工具 | 可复现入口与维护；仍调用正式算法，不另建求解器 |

## 4. 对默认业务无直接帮助，可隔离/退役的代码

| 范围 | 当前依赖和建议 |
| --- | --- |
| `track_a/`；`agent/stage9.py`、旧study别名；`verification/stage6c*`/`closed_loop*`/`research.py`；`block_space/extensions.py`；旧构建别名 | 26个声明兼容路径，其中25个Python文件；主要是转发，不是重复算法。后续可统一隔离为compat层，停止外部支持后再删除；现有接口测试仍要求它们存在 |
| 根目录 `contracts.py`、`behavioral.py`、`policies.py`、`runner.py` 与其 `_legacy` evaluator/physics/units/schemas | v1 run/suite，当前连续域不执行其评价策略。但 `cli.py:6` 的顶层导入仍加载它们；先改为显式v1路由内加载，再考虑归档 |
| `allocation/first_allocation.py`、旧 `AllocationStrategyPolicy`、`pipeline.run_pipeline`/`pipeline_contracts.py`/`scenarios.py` | 冻结链与旧Proposal合同，不是默认分配；可搬入明确冻结编排层，保持公开入口转发 |
| `_legacy/archive_audit.py`、`archive_report.py` | 固定读取旧outputs实验路径，不能审查本次新运行；最适合归档，但其兼容入口/测试仍须一并处置 |
| `studies/simulated_repairs.py`、旧 `examples/*.json` | v1/冻结研究或模拟反馈演示，不可用作真实连续域策略成绩；可与旧入口一起收纳 |

不建议现在直接删除 `allocation/`、`block_space/`、`verification/verify.py` 或 `_legacy/` 整个目录。`allocation/core.py`、`physics.py` 是真共享核心；其余四份原分配实现受源码SHA保护且仍被来源清单读取；`verify.py` 的区间判决被连续M2复用；`_legacy/` 仍因v1入口提前导入而被加载。

## 5. 剩余结构债务与清理顺序

1. **已处理：输入/输出/交接门禁。** 后续接口以权威清单与正式交付集合为边界。
2. **后续：延迟加载兼容路由。** `cli.py` 先顶层加载v1模块，`pipeline.py:14` 和 `allocation/__init__.py` 又加载冻结策略。默认M1实跑加载72个项目模块；这不代表72个模块均执行了正式业务。把旧导入移进明确路由，比改内部文件名更有价值。
3. **后续：分离来源依赖与计算依赖。** `exploration/engine.py:21` 的AUDITED清单会读取registry、allocate、agent、multispec_search等源码；`agent/search_loop.py:56` 哈希整个agent目录，包括兼容别名。退役前先设计有版本的来源清单迁移，不能靠删文件后改哈希绕过绑定。
4. **后续：拓宽结构审计。** 当前 `tools/audit_architecture.py:44` 的依赖方向审查仅覆盖pipeline及allocation/verification/physics_mapping/block_space，共58份文件；未完整覆盖agent/exploration/region_explorer，也没有验证上述交接摘要。本轮用独立运行探针与新增边界回归补证据。已有审计PASS不等于全项目依赖干净。

本地最大体积来自被Git忽略的 `experiments/`：审核初始扫描约226,427个文件、15,148MiB；源码 `data/legacy` 仅约32KB。清理历史实验属于单独的数据归档工作，其中可能有仍被旧交接绝对路径引用的证据，不能把它当作删无用源码的一部分。

## 6. 验证与证据

- 清洗前完整回归：917 passed、10 skipped；跳过项均为未提供的历史档案/旧试验数据。
- 最终固定快照完整回归：**958 passed、10 skipped、0 failures、0 errors**（`-W error`，968项，468.90秒）。当前Python/C++/CMD/JSON与验收快照逐文件一致；`pyproject.toml` 仅行尾字节不同，TOML解析结果一致。
- 第一轮输入/交接/路由/兼容定向回归：97 passed；另新增非对象输入用例。
- 清洗后默认原生运行：联合交付3点，M1调用15次，M2验证5次，LLM调用0次，原生子运行530次。
- 合并当前频率规划后再跑默认N=8，仍交付3点、M1=15/M2=5；另以N=10的新问题运行，交付1个正式联合通过点，M1=9/M2=3/LLM=0。两者交付均通过共享门禁，PM/jitter仍UNKNOWN。
- 新旧协议、输入和频率规划的定向回归：41 passed；权威清单的文件SHA逐项核对通过。
- 清洗前后逐项对照：所有候选SI参数、M1指标/判决、M2测量/判决、交付候选哈希、实际调用计数一致。路径、源文件身份与墙钟时间不作为数值等价比较项。
- 六份冻结分配实现保持字节相同；结构/命名审计通过。未开展真实API效益实验。
- 最终固定快照全量回归与跳过原因以本地 `experiments/structure_audit_20261124_01/snapshot_pytest.log`、对应XML为准。此前 `final_pytest_02` 在并行M2改动期间出现3个原生候选夹具错误，不作为最终验收。

本地审核目录还保存 `architecture.json`、`final_architecture.json`、`dependencies.json`、`module_inventory_final.json`（逐文件分类）、`runtime_trace.json`、`io_probes.json`、`native_comparison.json`、`integrated_comparison.json`、`delivery_acceptance.json`、`snapshot_receipt.json` 与清洗前后新鲜运行。旧运行证据没有被改写。首次最终回归收集发现可选VCO模块仍引用旧私有辅助入口；已恢复该入口后重新运行，失败记录也保留。提交/远端状态与后续交接见 [代码状态](CODE_STATE_20261124.md)。
