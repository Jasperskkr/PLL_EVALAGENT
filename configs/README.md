# 配置目录

这里保存运行输入和来源合同，不存放实验结果。正常使用先修改 `problems/` 的 SystemSpec、六轴范围，再选择 `agent/` 策略和 `verification/` 验证预算。正式入口仍是 `python -m pll_allocation pipeline`。

可选共享物理增强另用 `agent/noise_aware.json`（条件噪声）或 `agent/physics_enhanced.json`（再加启动构造与统一排序）。两份均 K=5、M1上限96、M2上限3，无真实 API 授权；原 `spec_allocation.json` 及 nominal/tight 不改。四开关、profile、频带、条件可行与正式 UNKNOWN 的边界见 [SPEC_ALLOCATION](../docs/SPEC_ALLOCATION.md#可选条件噪声与启动排序2026-11-20)。

|路径|用途|使用建议|
|---|---|---|
|`problems/`|nominal、tight、infeasible_pm 三个 ResearchProblemV2 示例；规格、启用项、固定拓扑和六轴范围|复制后修改，合法输入不保证有解|
|`agent/`|确定性、LLM 物理工具策略、区域规划/搜索及预算|按所选 Policy 使用，不是六参数答案|
|`examples/spec_allocation.json`|多候选复现输入，含 tight LLM/Auto、联合部分交付与小池补点，继承默认策略配置|仅问题路径及预算覆盖，无实验输出；`tools/run_allocation_examples.py` 生成输入并调用正式 Pipeline|
|`providers/messages.json`|物理工具 Agent 的 Messages API 配置；4000 tokens、180s、thinking disabled|只记录环境变量名，凭据留在进程环境|
|`providers/messages_interactive.json`|原交互入口的独立 API 默认值；8000 tokens、60s|保留原预算差异，不与上一项合并|
|`verification/verify_only.json`、`feedback.json`|Handoff 后一次 M2，或有限反馈重分配|必须先取得 READY Handoff|
|`verification/m2_protocol.json`|冻结理想行为 TB 的测量和数值收敛基础协议|连续域请求据此派生绑定当前N的 `integer_n_metrics_1.0`，用户指标从问题Spec读取|
|`verification/phase_step_protocol.json`、`return_ratio_protocol.json`|可选相位阶跃、返回比实验协议|可选验证扩展，不代表完整 PM 已认证|
|`verification/noise_protocol.json`、`profiles/`|可选噪声/非理想验证协议及预声明环境|标准理想链不自动启用；profile 不是器件可实现性保证|
|`model/`|冻结 Block Space、方程、参考 SystemSpec 和 M1 实验合同|供模型/冻结兼容链和数值回归使用，不是一次成功设计的范围|
|`pipeline.json`|冻结兼容 Pipeline 的模型/协议路径与策略设置|仅在显式 `--legacy-frozen` 或相应冻结研究调用中使用；默认主线是 `agent/spec_allocation.json`|
|`baselines/`|确定性 M1、联合理想/非理想基线问题与对照设置|供基线/回归调用，不是历史运行结果|
|`provenance/`|原实现、物理绑定、配置迁移和可选 profile 的哈希清单|来源证据，不是实验指标，不手工伪造哈希|

六轴传入后端的单位依次为 A、Ohm、F、F、Hz、Hz/V。规格和变量域必须符合已有合同；当前反解要求启用正 BW 目标。修改问题不能扩大固定拓扑与测量能力。

标准连续域 M2 的分频比从 `fixed_parameters.N.value` 读取正整数，目标为 `N*f_ref`；参考频率仍为10MHz、电压轨仍为0–1.2V。不同N须通过同一调谐、步长/边沿分辨率及测量收敛检查。`provenance/integer_n_m2.json` 保留这次适配的旧新来源哈希，历史N=8证据不自动升级到其他N。

## 手工输入 SystemSpec 和六变量范围

复制 `configs/problems/nominal.json` 为自己的问题文件；修改 `problem_id`、`specs`（指标、启用项、上下限与验证来源）和 `parameters`（六轴 `min/max/default/unit/scale`）。六轴必须完整，`0 < min < max`，默认值在范围内，尺度为 `log` 或 `linear`；当前连续域合同不支持用相等上下限固定某一轴，也不使用旧的离散 `choices`。

```powershell
python -m pll_allocation pipeline --problem path/to/my_problem.json --allocator-config configs/agent/spec_allocation.json --out experiments/my_manual_run_01
```

仅校验输入而不调用求解器、M2或LLM：

```powershell
python -c "from pll_allocation.exploration.contracts import load_problem; p=load_problem('path/to/my_problem.json'); print(p['problem_id'], p['problem_sha256'])"
```

`fixed_parameters` 定义参考频率、N、电压轨等条件；M1解析范围不等于M2支持范围，标准M2仍只支持10MHz×8、0–1.2V及原理想模型。模式/目标点数/总预算放在 allocator 配置，任务指标与六轴范围放在问题文件，M2测量协议不是用户Spec。

`model/block_space.json` 的 `experiment.block_space.variables` 和顶层 `variables` 是相互校验的冻结兼容域；`model/reference_system_spec.json`、`model/m1_experiment.json` 和 `pipeline.json` 也是参考/回归或显式冻结路径的合同。它们不是新版用户输入，直接修改会破坏冻结身份，且不会替代当前问题的 `parameters/specs`。这些文件仍有调用及测试用途，不应作为无用文件删除。`model/equations.json` 仍供新版Agent组织物理先验。

`agent/deterministic.json`、`agent/llm_physics.json` 是保留的连续域单点接口；常规多点交付应使用 `agent/spec_allocation.json`，不要混淆二者的schema和输出。正常调用关系为：problem → `load_problem` → 物理工具/搜索与正式M1 → 候选池 → 原生M2与反馈 → `sizing_handoff.json`；结果中的 `problem_resolved.json` 和 `execution_route.json` 可核对实际输入及路径。

`agent/spec_allocation.json` 是多候选端到端入口：三种 `mode`、K、总 M1/M2/LLM 预算、质量和去重阈值。`minimum_distance` 使用当前六轴各自的 log/linear 归一化坐标，`minimum_margin` 使用原 M1 judge 的最小归一化裕量。真实 API 默认禁用。原 `agent/deterministic.json`、`llm_physics.json` 及其单点输出合同保持兼容。

`target_count=5` 是初始 M1 池目标，`m2_target_count=3` 是正式 M1＋原生 M2 已支持指标通过的交付目标；公开默认 M2 预算8。旧配置省略新字段仍为目标1。目标与预算独立，预算可不足；结果区分目标达成和部分交付。`sizing_handoff.json` 只输出合格的原生联合通过子集，不收录 TEST、仅 M1 或 UNKNOWN 点；不认证管级/PVT。`feedback` 单点案例显式设置目标1，避免默认配置变化破坏其用途。

嵌套 `candidate_pool.mode` 必须与初始分配 `policy` 一致：确定性对应 `DETERMINISTIC_PHYSICS_TOOL`，LLM/Auto 对应 `LLM_PHYSICS_TOOL`；冲突会在执行前拒绝，不能让反馈阶段的行为与配置标签相反。标准三模式入口自动生成一致配置。

本次移除了十份完全重复的阶段配置、旧 study 计划/重复输入、过期 manifest、旧版返回比协议及重复依赖表，共17个文件；32份有效配置按职责迁移。迁移记录见 `provenance/config_paths.json`。冻结 JSON 内的历史 ID、来源字符串保留原义，不是仍需读取的旧文件路径。可选扩展构建需生成新身份，不能拿旧 DLL 的身份记录冒充新源码。

职责命名迁移新增 `provenance/naming_migration.json`，记录源码和夹具路径迁移及旧/新身份；原有配置迁移收据保留并可追溯衔接。schema/profile/protocol ID保留历史值，不能从阶段字样推断它仍是活动文件路径。
