# 名称迁移、兼容与来源合同

2026-11-24 标准连续域 M2 支持当前问题的正整数 N：请求 schema 保持 `pll-m2-verification-request-1.0`，适配身份升级为 `pll-continuous-m2-1.1`，派生协议身份为 `integer_n_metrics_1.0`，显式绑定 N、f_ref 和输出目标。旧 `verify.py`、`kernel.cpp`、`m2_protocol.json` 字节保留，冻结链和可选扩展保留其原范围。simulator/measure/experiments/run_suite/continuous 的旧新源码身份保存在 `configs/provenance/integer_n_m2.json`；Registry的simulator当前绑定据此更新，旧哈希和历史N=8证据保留。旧已执行请求的源码/协议身份不能冒充新版结果，复验须生成当前请求和新的实验目录。

## 2026-11-24 输入、输出与交接收口

- 新连续域入口与 VCO 文件输入共用严格 JSON 读取：重复字段、NaN/Infinity/浮点溢出和非对象配置会明确拒绝。文件缺失等 I/O 错误由 pipeline 返回结构化 `INPUT_OR_OUTPUT_ERROR` 和退出码2。
- 多候选运行新增 `pll-run-manifest-1.0` 的 `run_manifest.json`。它用相对路径和文件 SHA256 索引权威结果；旧结果字段、文件副本及 schema 保留。下游候选集合只有 `sizing_handoff.json.candidates`，不能读兼容 `recommended` 字段推断交付成功。
- `pll-sizing-targets-1.0` 的校验移到共享 `delivery.py`，生产端及 VCO 消费端复用。候选数、目标达成标志、状态、推荐身份及原有正式证据必须一致。空交付、TEST 和预算内部分交付仍合法；不能伪装 TARGET_REACHED。
- 交付协议校验按记录中的M2适配版本选择：1.0为原N=8协议，1.1为绑定候选N、f_ref、输出目标的 `integer_n_metrics_1.0`。旧交付可离线读取，不能将旧请求身份改成新版而沿用历史证据；两个版本都继续保留来源与完整SystemSpec未认证状态。
- M1 Handoff 必须同时 `ready_for_stage9=true`、`gate_status=READY`、无阻断原因。新生成 Handoff 附绑定在原摘要中的相对 context 路径；复制完整运行目录后优先读取复制的 context，不回退原目录绕过缺失/损坏证据。旧 Handoff 没有相对路径时仍按原绝对路径读取，历史文件不改写。单独复制一个 M1 Handoff JSON 仍不足以继续执行。
- 原数值公式、六份冻结分配源码、原生内核、测量协议和判决保持；新增校验不认证实验真实性，不升级 PM/jitter UNKNOWN。

2026-11-20 LLM Physics Tool 补充：`PhysicsRegionRequest 1.0` 的字段、校验及构造含义保留；可选 `pll-physics-region-request-1.1` 仅增加有序 `physical_objectives` 和当前 `tool_options_sha256`。按 noise/startup 开关分别开放目标，全部关闭时隐藏新增 State 与 Prompt。其余动作 schema、三模式与 Auto 切换规则保持。`CPRED` 仅为带候选/问题/模型/profile/适用条件的预测证据，不取得 M1 seed 或 M2 PASS 权限。`PROBE_REGION` 修复为直接执行原 Sobol，避免误走 SLSQP 预播种而拒绝合法的小预算；未改共享求解器。详见 [Spec Allocation](SPEC_ALLOCATION.md#llm-主动选择条件物理目标)。

2026-11-18 多点交付：新 `m2_target_count` 为可选字段，接口缺省1保留原首次通过停止；公开 `configs/agent/spec_allocation.json` 显式设3并将 M2预算设8。仅显式多点配置使用 `M2_JOINT_TARGET_REACHED` / `M2_JOINT_PARTIAL` 状态，原目标1状态保留。原反馈配置也可选此字段，多点目标须有候选池。`joint_status`、`joint_candidates`、到达时间与 `sizing_handoff.json` 是新增结果；旧 `recommended` 仍可能回退到 M1，不能作为多点交付集合。物理/协议/判决与历史证据均未重写。

主阅读路径按职责命名。核心物理公式、原反解/数值求解、测量算法和判决语义保持原实现。

2026-11-20 条件物理扩展：`pll-spec-allocation-1.0` 允许 `analytic_features_enabled`、`noise_allocation_enabled`、`initial_state_aware_enabled`、`physics_ranking_enabled` 及 `physics_options`，省略四开关为 false。嵌套候选池使用独立 `pll-conditional-physics-1.0` 工具选项，原 PhysicsRegionRequest 1.0 的字段与语义不变。原 nominal/tight 数值、原默认 agent 配置、所有 provenance 哈希、M1/M2 核心和模型身份保持。新增条件预测及排序证据是附加字段，既不升级正式 M2 jitter/PM 支持能力，也不改变已有联合交付状态语义。配置示例另存 `agent/noise_aware.json`、`agent/physics_enhanced.json`。

## 执行入口收口（2026-11-17）

新版连续域、多候选分配是默认主线。`pipeline --problem <problem> --out <fresh>` 默认加载 `configs/agent/spec_allocation.json`；只有 `--out` 时使用 nominal 示例及同一新版配置，并明确记录路径。仅提供 Provider、种子或旧策略参数不会自动选择问题，也不会隐式执行旧链。

|用途|明确入口|实际路由标识|
|---|---|---|
|新版三模式多候选|`pipeline --problem ... --out ...`，可选 `--allocator-config`|`CONTINUOUS_SPEC_ALLOCATION`|
|原连续域单点|显式 `--problem ... --allocator-config configs/agent/deterministic.json` 或 `llm_physics.json`|`CONTINUOUS_SINGLE_ALLOCATION`|
|连续域 M2/反馈|`--handoff --verification-problem --verification-config`|`CONTINUOUS_VERIFICATION`|
|冻结兼容分配|`pipeline --legacy-frozen --strategy analytical --out ...`|`LEGACY_FROZEN`|
|更早 v1 合同|`python -m pll_allocation --legacy-v1 run ...` / `suite ...`|历史 v1；不代表新版 Agent|
|可选研究/工具模式|`--multispec`、`--explore-problem` 等显式选择|各自独立路由；不隐式进入主分配链|

旧冻结 CLI 命令须增加 `--legacy-frozen`；Python `pipeline.run_pipeline` 仍保留同一冻结实现，供历史绑定与回归显式调用。旧 `--strategy llm_agent` 的反馈重分配仍未实现，结果会明确记录该能力限制，不借用新版能力作承诺。旧六参数/Proposal 不能直接绕过新版 Handoff/问题绑定。

所有模式在读输入或执行工具前检查参数是否实际被消费：例如新版不能带旧 `--m2-budget`、`--repair-budget`、`--strategy`；这些预算在新版 allocator JSON 中配置。显式传 `--strategy analytical` 也会报错，不能把它误当作新版策略覆盖。混用探索、Planner、子区域或冻结参数同样拒绝，零值预算也不例外。

CLI 启动在 stderr 打印 `EXECUTION_ROUTE_SELECTED`，结果目录保存 `execution_route.json`。新结果保留原 schema 和状态，补实际路由；候选池结果及逐轮决策记录真实策略来源，反馈结果的 `actual_execution` 区分原生/TEST、M2 是否执行与真实 API 次数。兼容的历史 `mode/strategy/scope` 标签不能代替调用证据。存在 Provider/控制器失败时即使保留了部分 M1 点，CLI 也以非零退出并保留结果。

例如显式连续域单点确定性配置仍可能保留 `status=STOPPED_BY_LLM` 这一历史停止标签，但 `actual_policy_execution=DETERMINISTIC_ONLY`、`cost.LLM_calls=0`、`cost.test_policy_calls=0` 明确说明实际执行；不要将旧标签用于统计真实调用。新版主线的三模式结果、实际路由、候选和真实调用成本是应优先读取的字段。

|旧称|新路径/概念|
|---|---|
|Stage7|exploration：物理探索/PhysicsContext|
|Stage8A|region_explorer：预算化工具执行|
|Stage8B|agent：真实决策闭环|
|Stage9 / agent/stage9.py|agent/feedback.py → run_feedback|
|verification/research.py|verification/continuous.py|
|Track A / Track B|allocation / verification|
|阶段化例题/配置|configs/problems、agent、providers|
|A+ / 多区域 / 消融编排|studies/initial_allocation、multi_region、ablation|

旧导入仅转发同一实现，旧 run_stage9_feedback 参数保持可用。没有另写一套反馈算法。

|推荐 CLI|旧别名继续支持|
|---|---|
|--problem|--initial-allocation-problem|
|--allocator-config|--initial-allocation-config|
|--initial-context|--initial-allocation-context|
|--feedback-input|--initial-allocation-feedback|
|--handoff|--stage9-handoff|
|--verification-problem|--stage9-problem|
|--verification-config|--stage9-config|

新结果名为 verification_handoff.json、verification_result.json、cost_summary.json、feedback_report.md；相应旧文件名仍输出，已有本地 GUI/脚本继续工作。序列化 schema、ready_for_stage9 等键、来源标签和模型版本不做全局文字替换；交接优先查看 gate_status。

configs 和 tools 已按职责整理，旧阶段目录及重复配置已移除，详见各目录 README。配置迁移保留数值载荷、冻结 ID 和来源字符串；`pipeline.json` 仅更新文件引用。哈希绑定文件可以迁移，但必须显式记录旧/新身份并重建依赖它的构建。本次收据为 `configs/provenance/config_paths.json`、`verification_profiles.json`，物理映射绑定也已更新。

非理想/噪声实现已迁至 `verification/nonideal.py`、`nonideal_noise_native.py`、`nonideal_noise_identity.py`、`nonideal_noise_kernel.cpp`；profile合同使用 `block_space/profiles.py`。相位阶跃使用 `phase_step*`。旧Python路径仅作同一模块的兼容转发，旧C++路径已移除；完整映射见 [命名说明](NAMING.md)。

`track_a` 仅保留兼容入口：首次分配执行迁至 `allocation/first_allocation.py`，基线与模拟修复迁至 `studies/`，历史档案工具迁至 `_legacy/`。新代码和测试使用职责路径；正式执行入口保持 `python -m pll_allocation pipeline`。

原生默认目录为 `build_phase_step/`、`build_return_ratio/`、`build_nonideal_noise/`。`PLL_NONIDEAL_NOISE_BUILD_DIR` 优先于旧 `PLL_STAGE6C_BUILD_DIR`；需要新建构建及其身份文件，不能改写旧身份绕过检查。

本次保留schema、protocol/model ID、strategy/source标签及旧序列化键。旧报告/结果文件仍有兼容副本，优先使用职责名称。全部21项迁移及源码身份变化另记录在 `configs/provenance/naming_migration.json`，原配置迁移收据不被冒充为此次结果。

configs/provenance 保存原实现 SHA 和物理关系绑定。data/behavioral_space_v1/reference 仅保留参考数值代码与来源合同，供独立回归；这些不是新实验数据。

`data/legacy` 只保留旧内核来源清单、输入模型及小型 MATLAB 锚点，`tests/fixtures` 保存合同/判决回归输入。它们是明确标注的历史测试夹具，不是本次运行产生的成果；大型轨迹和实验目录均不发布。

此次精简通过普通快进提交完成：最新版目录移除实验数据、冗余文档、GUI 和构建产物，本地历史不删除，Git 历史不改写。历史对象仍可在旧提交找到；浅克隆或下载源码仅获取最新版工作目录。
