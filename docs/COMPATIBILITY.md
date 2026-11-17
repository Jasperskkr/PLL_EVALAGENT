# 名称迁移、兼容与来源合同

主阅读路径按职责命名。核心物理公式、原反解/数值求解、测量算法和判决语义保持原实现。

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
