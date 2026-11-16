# 名称迁移、兼容与来源合同

主阅读路径按职责命名。核心物理公式、原反解/数值求解、测量算法和判决语义保持原实现。

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
