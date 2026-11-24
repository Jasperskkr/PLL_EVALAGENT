# 架构与调用链

2026-11-24 标准连续域 M2 由候选的固定N构建 `integer_n_metrics_1.0` 频率计划：`simulator.validate_frequency_plan` 共享标准范围校验，`continuous.verification_request` 绑定计划/规格/来源，`measure.capture_metrics` 和 `run_suite.capture_pair` 使用N×f_ref与实际N提取捕获频率及ppm，频响启动点使用同一目标。仍复用原C++内核、四组频响收敛与区间判决；M2不会根据所需PASS修改硬规格。旧冻结和可选扩展保留独立范围，源码身份更新见 `configs/provenance/integer_n_m2.json`。

2026-11-24 接口整理：外部 JSON 经 `io_contracts.read_json` 拒绝重复键与非有限数；多候选输出用 `run_manifest.json` 标识权威文件。`delivery.validate_sizing_handoff` 由分配生产端及 VCO 消费端共用，检查交付摘要与原有 M1/M2 证据；不执行新仿真。M1 交接一致校验 READY/旧 ready 标志，新输出附相对 context 路径，完整运行目录可迁移。代码分类、已修复问题和保留边界见 [结构审核](STRUCTURE_AUDIT_20261124.md)。

Policy 提议动作，Runner 审查并执行，工具计算，验证器独立判决。Policy 不得修改硬规格、扩大用户域、越过预算或自行声明 PASS。

正式 CLI 默认是新版连续域多候选分配：`--problem` 指定当前 Spec，省略 allocator 时用 `agent/spec_allocation.json`；只有 `--out` 使用 nominal 示例。`_execution_route` 在任何输入读取/执行前互斥检查所有模式并拒绝未被消费的参数。冻结兼容链只由显式 `--legacy-frozen` 进入；Python 旧 `run_pipeline` 保留兼容用途。每次 CLI 启动及 `execution_route.json` 标明实际路由，详见 [COMPATIBILITY](COMPATIBILITY.md)。

`pll-spec-allocation-1.0` 配置由同一 `pipeline.main` 分派到 `agent/spec_allocation.py`。它给原 `run_initial_allocation` 添加 Cold Start 和候选池配置，再调用原 `run_feedback`；不增加第二套求解或验证实现。`PoolSearchLoop` 继承 `PhysicsToolSearchLoop`，只补池数量/质量停止、逆解近重复筛除和按需原 Sobol；`PoolDeterministicPolicy` 和受授权门禁约束的 `PoolLLMPolicy` 共用同一决策校验、构造、RegionExplorer 与正式 M1。M2 仍由原 controller 与 `verification.continuous` 执行和判决。

`candidate_pool.py` 在原问题的 log/linear 六轴归一化坐标中按距离去重，保留最佳 M1 裕量的代表点。M2 候选先满足配置质量门槛，首点按原 M1 rank，后续兼顾距已测点的距离。所有原始、失败、近重复证据仍保存在原账本，重复过滤不改变正式验证算法。`deterministic_feedback.py` 提取 V2 已有 BW 偏差修正与低调谐点探索规则，不将局部反馈解释为物理定理。

```mermaid
flowchart TD
    A[ResearchProblemV2] --> B[pipeline.main]
    B --> P[run_spec_allocation]
    P --> C[run_initial_allocation]
    C --> D[Cold Start 或显式小样本校准]
    D --> E[PhysicsToolSearchLoop]
    E --> F[确定性 Policy 或真实 LLM]
    F --> G[决策合同校验]
    G --> H[物理反解和区域构造]
    G --> I[RegionExplorer 工具执行]
    H --> I
    I --> J[正式 M1 和候选账本]
    J --> E
    J --> K[独立复核和 Verification Handoff]
    K --> L[run_feedback]
    L --> M[连续候选适配和真实原生 M2]
    M --> N[测量判决和反馈]
    N -->|需要重新分配| C
    N --> O[共享交付门禁与正式候选]
    O --> Q[权威产物与 run_manifest]
    Q -->|显式下游调用| V[VCO guidance / 实测反馈 / 再验证输入]
```

|模块|关键入口|产物与职责|
|---|---|---|
|`exploration/contracts.py`|resolve_problem / check_candidate / judge|问题、单位、域、必要条件、逐约束裕量|
|`agent/initial_allocation.py`|run_initial_allocation / PhysicsToolSearchLoop|校准、物理策略到工具的翻译|
|`agent/subregion_loop.py`|prepare_initial|有限 Sobol 校准和 PhysicsContext|
|`agent/physics_tool_policy.py`|build_state / adapt / make_policy|真实观察、物理先验、预算和合法工具动作|
|`agent/region_policy.py`、`llm_transport.py`|LLMRegionPolicy.decide|真实 API、严格 JSON、metadata 和错误|
|`agent/search_loop.py`|AgentSearchLoop.run / finish|观察→决策→执行→反馈；独立最终复核|
|`exploration/physics_region_builder.py`|build_physics_region / gain_tuning_interval|原域合法种子和未认证局部盒|
|`allocation/physics.py`|inverse_at_shape / pm_ceiling|当前拓扑条件反解及必要条件|
|`region_explorer/explorer.py`|RegionExplorer.execute / _sample|原 Sobol/SLSQP、缓存、边界和正式 M1 计费|
|`physics_mapping/model.py`|M1Evaluator.evaluate|连续 BW/UGF、名义 PM、调谐点|
|`agent/candidates.py`|CandidateArchive / rank|有效证据、M1 可行优先和 maximin 裕量排序|
|`agent/handoff.py`|build_handoff / validate_handoff|完整参数、当前问题和独立复核绑定|
|`agent/feedback.py`|run_feedback / feedback_summary|真实 M2、跨层预算、反馈与新候选复验|
|`verification/continuous.py`|verification_request / execute_request / judge_measurements|连续候选到原 TB 的适配、超时隔离、按来源判决|
|`verification/simulator.py`、`kernel.cpp`|simulate|PFD/CP/LF/VCO/Divider 真实行为闭环|

## 策略与工具

`vco_sizing/` 是正式输出的可选消费者，默认分配不导入其开发功能。`contract.py` 委托 `delivery.validate_sizing_handoff` 校验源交付，再构建/重建guidance和用户策略；`revalidation.py` 只准备f0/Kvco回填问题，不代替正式M1/M2。`region.py` 为显式研究调用保留原预算与原验证器。合同字段和实测确认规则见 [VCO合同](VCO_SIZING_CONTRACT.md)。

多点交付的 `m2_target_count` 与初始 M1 池 `target_count` 分离。原 `run_feedback` 累计质量及距离合格的联合通过点，首个通过不再必然停止；先换池内未测点，再预算内补点或修复。成功补点携带 `REPLENISH_JOINT_POOL` 和已通过点，不捏造失败。`spec_allocation` 再按原生来源筛选输出 `joint_candidates` / `sizing_handoff.json`，TEST、仅 M1、FAIL、UNKNOWN 点不得进入。旧配置默认目标1，原单点路径不变。

确定性 Policy 使用预先定义的物理构造和局部优化顺序；LLM 选择策略、BW 目标分数、调谐偏好、区域、活动变量和预算。共用原反解与正式评价器。

动作包括 BUILD_PHYSICS_REGION、OPTIMIZE_LOCAL、PROBE_REGION、MEASURE_LOCAL_SENSITIVITY、REVERIFY、STOP。非法提案只留档、不执行；Provider 失败不会冒充确定性成功。

反解依赖理想 CP、线性 VCO 和既定两电容一电阻滤波器：由形状和 BW 重建 Rz、Icp×Kvco，再求增益分解和调谐交集。包含标量数值求根，不是任意 PLL 的闭式逆。

`exploration/regions.py:sensitivity` 进行六轴局部有限差分，`agent/subregion_tools.py` 通过正式 M1 执行。输出局部矩阵、弹性、扰动点与证据 ID，再送 Planner State。它不是 M2 捕获梯度或全局单调性证明。

SLSQP 优化最差归一化 M1 裕量，动态捕获通过外层反馈参与。求解收敛、M1 可行和 M2 通过分别记录。

标准初始分配与联合验证不读取历史实验目录或报告。`studies/` 是可选对照编排，不能作为第二套正式 Pipeline。兼容路径和保留的旧版本键见 COMPATIBILITY。

新连续域 Agent 默认使用三模式配置，也可显式传旧单点 allocator。冻结兼容链使用 `allocation/AllocationStrategyPolicy`，其旧 `llm_agent` 反馈分支未实现；连续域的真实 LLM 反馈由 `agent/feedback.py` 接入 `run_initial_allocation`。候选池的实际决策来源、真实 API 次数与 M2 来源单独记录，不能仅从兼容标签判断。全部维护文件逐项职责见 [CODE_MAP](CODE_MAP.md)。

2026-11-20 可选共享物理增强：allocator 的四个开关默认关闭；独立 `physics_options` 配置经现有 Runner 校验和传递，原 PhysicsRegionRequest 1.0 不变。builder 继续原 inverse，在预算内枚举形状/电容/增益分解并加启动偏移点；RegionExplorer 使用原 SLSQP、原正式 M1 和原预算，添加条件 jitter 裕量及正式 M1 边界约束。原 `allocation/noise_optimization.py` / `multispec_search.py` 继续服务离散冻结配置的研究扩展，连续主线复用 RegionExplorer，避免另建求解器。解析描述和噪声预测均无正式判决权。

启用新排序时，`AgentSearchLoop.finish → PoolSearchLoop._select_recommendation → candidate_pool.select_m2 → physics_ranking` 与反馈选点共用一个入口，随后仍独立正式 M1 复核、Handoff gate 和原生 M2。条件噪声筛选先于距离打包，避免已满足 jitter 的邻点被只看 M1 裕量的代表点遮蔽；无适用动力学预测时保留候选并记录回退。`conditional_noise_summary` 与正式 `joint_status` 分开，标准 M2 PM/jitter 仍 UNKNOWN。全部开关关闭时走原推荐与工具路径；配置、归一化优先级和回退规则见 SPEC_ALLOCATION。
